from __future__ import annotations

import hashlib
import json
import logging
import time
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import numpy as np
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    connector_id: str
    attempted: int
    ingested: int
    skipped_existing: int
    errors: List[str]

    def to_dict(self) -> Dict:
        return {
            "connector_id": self.connector_id,
            "attempted": self.attempted,
            "ingested": self.ingested,
            "skipped_existing": self.skipped_existing,
            "errors": self.errors,
        }


class ConnectorIngestionService:
    def __init__(self, embed_file: Path, vector_dim: int = 64):
        self.embed_file = Path(embed_file)
        self.vector_dim = vector_dim
        self.cluster_count = 8
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
            }
        )

    def sync_connector(self, connector: Dict) -> IngestResult:
        connector_id = connector.get("connector_id", "unknown")
        connector_type = (connector.get("connector_type") or "").strip()
        config = connector.get("config") or {}
        max_articles = int(config.get("max_articles", 10))
        max_articles = max(1, min(50, max_articles))

        existing = self._load_vectors()
        existing_urls = {
            (item.get("metadata") or {}).get("url", "")
            for item in existing.values()
            if isinstance(item, dict)
        }

        errors: List[str] = []
        attempted = 0
        ingested = 0
        skipped_existing = 0
        retries = max(0, int(config.get("request_retries", 2)))
        backoff_ms = max(0, int(config.get("request_backoff_ms", 300)))

        try:
            if connector_type == "rss":
                candidates, collection_errors = self._collect_from_rss(config, max_articles, retries, backoff_ms)
            elif connector_type == "section_scraper":
                candidates, collection_errors = self._collect_from_section(config, max_articles, retries, backoff_ms)
            else:
                raise ValueError(f"Unsupported connector type: {connector_type}")
            errors.extend(collection_errors)
        except Exception as exc:
            errors.append(str(exc))
            return IngestResult(connector_id, attempted, ingested, skipped_existing, errors)

        for article in candidates:
            attempted += 1
            url = article.get("url", "")
            if not url:
                errors.append("Skipping article with missing URL")
                continue
            if url in existing_urls:
                skipped_existing += 1
                continue

            article_id = self._article_id_from_url(url)
            if article_id in existing:
                skipped_existing += 1
                continue

            content = (article.get("content") or "").strip()
            title = (article.get("title") or "").strip()
            if not title or len(content.split()) < 20:
                errors.append(f"Skipping low-content article: {url}")
                continue

            vector = self._embed_text(f"{title}\n{content}")
            cluster = self._cluster_for_vector(vector)
            existing[article_id] = {
                "vector": vector,
                "cluster": cluster,
                "metadata": {
                    "title": title,
                    "content": content,
                    "url": url,
                    "scraped_at": article.get("scraped_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            }
            existing_urls.add(url)
            ingested += 1

        if ingested > 0:
            self._save_vectors(existing)

        return IngestResult(connector_id, attempted, ingested, skipped_existing, errors)

    def _load_vectors(self) -> Dict[str, Dict]:
        if not self.embed_file.exists():
            return {}
        try:
            return json.loads(self.embed_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Invalid embedding file. Starting from empty dataset.")
            return {}

    def _save_vectors(self, vectors: Dict[str, Dict]) -> None:
        self.embed_file.parent.mkdir(parents=True, exist_ok=True)
        self.embed_file.write_text(
            json.dumps(vectors, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _collect_from_rss(
        self,
        config: Dict,
        max_articles: int,
        retries: int = 2,
        backoff_ms: int = 300,
    ) -> tuple[List[Dict], List[str]]:
        feed_url = (config.get("feed_url") or "").strip()
        if not feed_url:
            raise ValueError("RSS connector requires config.feed_url")

        collection_errors: List[str] = []
        response = self._http_get(feed_url, timeout=12, retries=retries, backoff_ms=backoff_ms)
        root = ElementTree.fromstring(response.content)
        items = root.findall(".//item")
        results: List[Dict] = []
        for item in items[:max_articles]:
            title = self._xml_text(item.find("title"))
            link = self._xml_text(item.find("link"))
            description = self._xml_text(item.find("description"))
            pub_date = self._xml_text(item.find("pubDate"))
            scraped_at = self._normalize_datetime(pub_date)
            body = self._extract_article_body(link, collection_errors, retries, backoff_ms) if link else description
            results.append(
                {
                    "title": title or "Untitled",
                    "url": link,
                    "content": body or description or "",
                    "scraped_at": scraped_at,
                }
            )
        return results, collection_errors

    def _collect_from_section(
        self,
        config: Dict,
        max_articles: int,
        retries: int = 2,
        backoff_ms: int = 300,
    ) -> tuple[List[Dict], List[str]]:
        base_url = (config.get("base_url") or "").strip()
        if not base_url:
            raise ValueError("Section connector requires config.base_url")

        collection_errors: List[str] = []
        self._prime_consent(base_url)
        response = self._http_get(base_url, timeout=12, retries=retries, backoff_ms=backoff_ms)
        soup = BeautifulSoup(response.text, "lxml")
        self._strip_overlays(soup)
        links = self._extract_links(soup, base_url)
        results: List[Dict] = []
        for link in links[:max_articles]:
            article = self._extract_article(link, collection_errors, retries, backoff_ms)
            if article:
                results.append(article)
        return results, collection_errors

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        base_host = urlparse(base_url).netloc
        deduped: List[str] = []
        seen = set()
        selectors = ["article a[href]", "main a[href]", "[data-testid*='article'] a[href]", "a[href]"]
        anchors = []
        for selector in selectors:
            anchors = soup.select(selector)
            if anchors:
                break

        for anchor in anchors:
            href = (anchor.get("href") or "").strip()
            if not href:
                continue
            if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:"):
                continue
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if parsed.netloc != base_host:
                continue
            if parsed.path.count("/") < 2:
                continue
            if self._is_non_article_path(parsed.path):
                continue
            text = self._clean_text(anchor.get_text(" ", strip=True)).lower()
            if self._looks_like_navigation_tab(text):
                continue
            if full_url in seen:
                continue
            seen.add(full_url)
            deduped.append(full_url)
        return deduped

    def _extract_article(
        self,
        url: str,
        errors: Optional[List[str]] = None,
        retries: int = 2,
        backoff_ms: int = 300,
    ) -> Optional[Dict]:
        try:
            self._prime_consent(url)
            response = self._http_get(url, timeout=12, retries=retries, backoff_ms=backoff_ms)
        except Exception as exc:
            if errors is not None:
                errors.append(f"http_error:{url}:{str(exc)}")
            return None

        soup = BeautifulSoup(response.text, "lxml")
        self._strip_overlays(soup)
        blocker = self._classify_blocker_page(soup)
        if blocker and errors is not None:
            errors.append(f"{blocker}:{url}")
        title = self._clean_text(self._first_text(soup, ["h1.article-title", "h1.title", "h1"]))
        if not title:
            if errors is not None:
                errors.append(f"missing_title:{url}")
            return None

        paragraphs = []
        selectors = ["div.article-content p", "article p", "div.content p", "p"]
        for selector in selectors:
            parts = [self._clean_text(p.get_text(" ", strip=True)) for p in soup.select(selector)]
            parts = [p for p in parts if p and len(p.split()) >= 5]
            if parts:
                paragraphs = parts
                break

        content = " ".join(paragraphs).strip()
        if len(content.split()) < 20:
            if errors is not None:
                errors.append(f"low_content:{url}")
            return None

        return {
            "title": title,
            "url": url,
            "content": content,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _extract_article_body(
        self,
        url: str,
        errors: Optional[List[str]] = None,
        retries: int = 2,
        backoff_ms: int = 300,
    ) -> str:
        article = self._extract_article(url, errors=errors, retries=retries, backoff_ms=backoff_ms)
        return article["content"] if article else ""

    def _http_get(self, url: str, timeout: int = 12, retries: int = 2, backoff_ms: int = 300):
        last_exc: Optional[Exception] = None
        attempts = max(1, retries + 1)
        for attempt in range(attempts):
            try:
                response = self.session.get(url, timeout=timeout)
                response.raise_for_status()
                return response
            except Exception as exc:
                last_exc = exc
                if attempt >= attempts - 1:
                    break
                delay = (backoff_ms / 1000.0) * (2**attempt)
                time.sleep(min(5.0, delay))
        raise RuntimeError(f"request_failed_after_retries:{url}:{last_exc}")

    @staticmethod
    def _classify_blocker_page(soup: BeautifulSoup) -> Optional[str]:
        text = soup.get_text(" ", strip=True).lower()
        if any(token in text for token in ["cookie", "cookies", "consent", "souhlas", "gdpr"]):
            return "blocked_cookie_wall"
        if any(token in text for token in ["subscribe", "předplatné", "predplatne", "paywall"]):
            return "blocked_paywall"
        if any(token in text for token in ["sign in", "login", "přihlásit", "prihlasit"]):
            return "blocked_login_wall"
        return None

    def _embed_text(self, text: str) -> List[float]:
        vec = np.zeros(self.vector_dim, dtype=np.float32)
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.vector_dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = float(np.linalg.norm(vec))
        if norm == 0:
            vec[0] = 1.0
            norm = 1.0
        vec = vec / norm
        return [float(x) for x in vec.tolist()]

    def _cluster_for_vector(self, vector: List[float]) -> int:
        vec = np.array(vector, dtype=np.float32)
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        best_cluster = 0
        best_score = -1.0
        for idx in range(self.cluster_count):
            centroid = self._cluster_anchor(idx, len(vec))
            score = float(np.dot(vec, centroid))
            if score > best_score:
                best_score = score
                best_cluster = idx
        return int(best_cluster)

    @staticmethod
    def _cluster_anchor(idx: int, dim: int) -> np.ndarray:
        seed = hashlib.sha1(f"cluster-anchor-{idx}".encode("utf-8")).digest()
        values = np.frombuffer(seed * ((dim // len(seed)) + 1), dtype=np.uint8)[:dim]
        vec = values.astype(np.float32) - 127.5
        norm = float(np.linalg.norm(vec))
        if norm == 0:
            vec[0] = 1.0
            norm = 1.0
        return vec / norm

    @staticmethod
    def _looks_like_navigation_tab(text: str) -> bool:
        if not text:
            return False
        tab_tokens = {
            "cookie",
            "cookies",
            "souhlas",
            "nastaveni",
            "nastavení",
            "preference",
            "preferences",
            "privacy",
            "gdpr",
            "menu",
            "domu",
            "domů",
            "home",
            "rubriky",
            "sections",
            "tema",
            "téma",
            "video",
        }
        return any(token in text for token in tab_tokens)

    @staticmethod
    def _is_non_article_path(path: str) -> bool:
        lowered = path.lower()
        blocked = (
            "/tag/",
            "/autor/",
            "/autori/",
            "/predplatne",
            "/predplatné",
            "/subscribe",
            "/login",
            "/prihlaseni",
            "/přihlášení",
            "/nastaveni",
            "/nastavení",
            "/preferences",
            "/privacy",
            "/cookies",
            "/kontakt",
            "/about",
            "/newsletter",
            "/rss",
        )
        return any(token in lowered for token in blocked)

    def _prime_consent(self, url: str) -> None:
        """Seed common consent cookies to reduce CMP overlay blocking."""
        parsed = urlparse(url)
        domain = parsed.netloc
        for name, value in (
            ("cookie_consent", "accepted"),
            ("cookies_accepted", "true"),
            ("cmpconsent", "yes"),
            ("euconsent-v2", "accepted"),
        ):
            self.session.cookies.set(name, value, domain=domain)

    @staticmethod
    def _strip_overlays(soup: BeautifulSoup) -> None:
        selectors = [
            "[id*='cookie']",
            "[class*='cookie']",
            "[id*='consent']",
            "[class*='consent']",
            "[id*='privacy']",
            "[class*='privacy']",
            "[id*='gdpr']",
            "[class*='gdpr']",
            "[role='dialog']",
            ".modal",
            ".overlay",
        ]
        for selector in selectors:
            for node in soup.select(selector):
                node.decompose()

    @staticmethod
    def _normalize_datetime(raw: str) -> str:
        if not raw:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _xml_text(element) -> str:
        if element is None or element.text is None:
            return ""
        return element.text.strip()

    @staticmethod
    def _article_id_from_url(url: str) -> str:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        return f"connector_{digest}"

    @staticmethod
    def _first_text(soup: BeautifulSoup, selectors: List[str]) -> str:
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(" ", strip=True)
                if text:
                    return text
        return ""

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        return text.strip()
