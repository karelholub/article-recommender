from __future__ import annotations

import hashlib
import json
import logging
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
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
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

        try:
            if connector_type == "rss":
                candidates = self._collect_from_rss(config, max_articles)
            elif connector_type == "section_scraper":
                candidates = self._collect_from_section(config, max_articles)
            else:
                raise ValueError(f"Unsupported connector type: {connector_type}")
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
            cluster = self._cluster_for_text(content)
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

    def _collect_from_rss(self, config: Dict, max_articles: int) -> List[Dict]:
        feed_url = (config.get("feed_url") or "").strip()
        if not feed_url:
            raise ValueError("RSS connector requires config.feed_url")

        response = self.session.get(feed_url, timeout=12)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        items = root.findall(".//item")
        results: List[Dict] = []
        for item in items[:max_articles]:
            title = self._xml_text(item.find("title"))
            link = self._xml_text(item.find("link"))
            description = self._xml_text(item.find("description"))
            pub_date = self._xml_text(item.find("pubDate"))
            scraped_at = self._normalize_datetime(pub_date)
            body = self._extract_article_body(link) if link else description
            results.append(
                {
                    "title": title or "Untitled",
                    "url": link,
                    "content": body or description or "",
                    "scraped_at": scraped_at,
                }
            )
        return results

    def _collect_from_section(self, config: Dict, max_articles: int) -> List[Dict]:
        base_url = (config.get("base_url") or "").strip()
        if not base_url:
            raise ValueError("Section connector requires config.base_url")

        response = self.session.get(base_url, timeout=12)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        links = self._extract_links(soup, base_url)
        results: List[Dict] = []
        for link in links[:max_articles]:
            article = self._extract_article(link)
            if article:
                results.append(article)
        return results

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        base_host = urlparse(base_url).netloc
        deduped: List[str] = []
        seen = set()
        for anchor in soup.select("a[href]"):
            href = (anchor.get("href") or "").strip()
            if not href:
                continue
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if parsed.netloc != base_host:
                continue
            if parsed.path.count("/") < 2:
                continue
            if full_url in seen:
                continue
            seen.add(full_url)
            deduped.append(full_url)
        return deduped

    def _extract_article(self, url: str) -> Optional[Dict]:
        try:
            response = self.session.get(url, timeout=12)
            response.raise_for_status()
        except Exception:
            return None

        soup = BeautifulSoup(response.text, "lxml")
        title = self._clean_text(self._first_text(soup, ["h1.article-title", "h1.title", "h1"]))
        if not title:
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
            return None

        return {
            "title": title,
            "url": url,
            "content": content,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _extract_article_body(self, url: str) -> str:
        article = self._extract_article(url)
        return article["content"] if article else ""

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

    def _cluster_for_text(self, text: str) -> int:
        digest = hashlib.md5(text.encode("utf-8")).digest()  # nosec - non-cryptographic bucketing
        return int.from_bytes(digest[:2], "big") % 8

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
