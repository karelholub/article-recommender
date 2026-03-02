from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


def parse_sources_param(value: str) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(',') if part.strip()]


def normalize_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(',')]
    elif isinstance(value, list):
        items = [str(part).strip() for part in value]
    else:
        return []
    return [item for item in items if item]


def extract_sections(metadata: Dict[str, Any], url: str) -> List[str]:
    sections: List[str] = []
    for key in ('section', 'rubrika', 'category', 'categories'):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            sections.append(value.strip().lower())
        elif isinstance(value, list):
            sections.extend(str(item).strip().lower() for item in value if str(item).strip())
    parsed = urlparse(url or '')
    path_parts = [segment for segment in parsed.path.split('/') if segment]
    if path_parts:
        sections.append(path_parts[0].lower())
    return sorted(set(sections))


def safe_article_age_days(scraped_at: str) -> Optional[int]:
    if not scraped_at:
        return None
    try:
        ts = datetime.strptime(scraped_at, '%Y-%m-%d %H:%M:%S')
        return max(0, (datetime.now() - ts).days)
    except ValueError:
        return None


def safe_parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None


def extract_error_code(value: str) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    return text.split(':', 1)[0].strip().lower()
