"""Create minimal demo data so the app can start from a clean clone."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict

EMBED_FILE = Path("embeddings/article_vectors.json")
PROFILE_FILE = Path("profiles/user_profiles.json")
MAX_ARTIFACT_EMBEDDINGS = 5
ARTIFACT_RE = re.compile(r"(^|[_-])(demo|test|sample|mock)([_-]|$)", re.IGNORECASE)


def _has_valid_embeddings(data: object) -> bool:
    if not isinstance(data, dict) or not data:
        return False
    for item in data.values():
        if not isinstance(item, dict):
            return False
        vector = item.get("vector")
        if not isinstance(vector, list) or not vector:
            return False
    return True


def _demo_embeddings() -> Dict[str, Dict]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "demo_global_markets": {
            "vector": [0.91, 0.12, 0.22, 0.33, 0.44, 0.21, 0.78, 0.05],
            "cluster": 0,
            "metadata": {
                "title": "Global markets react to inflation outlook",
                "content": "Investors are recalibrating expectations after new inflation data and central bank commentary.",
                "url": "https://example.com/global-markets",
                "scraped_at": now,
            },
        },
        "demo_energy_transition": {
            "vector": [0.14, 0.82, 0.19, 0.27, 0.08, 0.54, 0.10, 0.76],
            "cluster": 1,
            "metadata": {
                "title": "Energy transition costs and industrial policy",
                "content": "Governments are balancing climate targets with competitiveness and supply chain resilience.",
                "url": "https://example.com/energy-transition",
                "scraped_at": now,
            },
        },
        "demo_ai_regulation": {
            "vector": [0.35, 0.25, 0.87, 0.11, 0.40, 0.73, 0.05, 0.22],
            "cluster": 2,
            "metadata": {
                "title": "Regulators debate new AI model disclosure rules",
                "content": "Policy makers are discussing transparency requirements and deployment safeguards.",
                "url": "https://example.com/ai-regulation",
                "scraped_at": now,
            },
        },
    }


def _looks_like_artifact(article_id: str, item: object) -> bool:
    if ARTIFACT_RE.search(article_id or ""):
        return True
    if not isinstance(item, dict):
        return False
    metadata = item.get("metadata") or {}
    title = str(metadata.get("title", ""))
    url = str(metadata.get("url", ""))
    if ARTIFACT_RE.search(title):
        return True
    # Keep this conservative: test artifacts often use synthetic domains.
    if "example.com" in url.lower():
        return True
    return False


def _safe_scraped_at(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    metadata = item.get("metadata") or {}
    return str(metadata.get("scraped_at", "") or "")


def _trim_artifact_embeddings(embeddings: Dict[str, Dict]) -> Dict[str, Dict]:
    artifact_ids = [article_id for article_id, item in embeddings.items() if _looks_like_artifact(article_id, item)]
    if len(artifact_ids) <= MAX_ARTIFACT_EMBEDDINGS:
        return embeddings

    artifact_ids.sort(key=lambda aid: _safe_scraped_at(embeddings.get(aid)), reverse=True)
    keep = set(artifact_ids[:MAX_ARTIFACT_EMBEDDINGS])
    return {aid: item for aid, item in embeddings.items() if (aid not in artifact_ids) or (aid in keep)}


def ensure_data_files() -> None:
    EMBED_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)

    embeddings = None
    if EMBED_FILE.exists():
        try:
            embeddings = json.loads(EMBED_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            embeddings = None

    if not _has_valid_embeddings(embeddings):
        embeddings = _demo_embeddings()
    else:
        embeddings = _trim_artifact_embeddings(embeddings)

    EMBED_FILE.write_text(
        json.dumps(embeddings, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    profiles = None
    if PROFILE_FILE.exists():
        try:
            profiles = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            profiles = None

    if not isinstance(profiles, dict) or not profiles:
        article_ids = list(embeddings.keys()) if isinstance(embeddings, dict) else []
        demo_reads = article_ids[:2] if len(article_ids) >= 2 else article_ids
        profiles = {"demo_user": demo_reads}
    else:
        valid_article_ids = set(embeddings.keys()) if isinstance(embeddings, dict) else set()
        normalized_profiles = {}
        for user_id, reads in profiles.items():
            if not isinstance(reads, list):
                continue
            filtered_reads = [article_id for article_id in reads if article_id in valid_article_ids]
            normalized_profiles[user_id] = filtered_reads
        profiles = normalized_profiles or {"demo_user": []}

    PROFILE_FILE.write_text(
        json.dumps(profiles, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    ensure_data_files()
    print("Ensured data files:", EMBED_FILE, PROFILE_FILE)
