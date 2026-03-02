from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


def _get_by_path(payload: Dict[str, Any], path: str, default: Any) -> Any:
    if not path:
        return default
    current: Any = payload
    for part in path.split("."):
        key = part.strip()
        if not key:
            continue
        if not isinstance(current, dict) or key not in current:
            return default
        current = current.get(key)
    return current


@dataclass
class MeiroProfile:
    external_user_id: str
    traits: Dict[str, Any]
    segments: List[str]
    raw: Dict[str, Any]


class MeiroAdapter:
    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        timeout_seconds = float(self.config.get("timeout_seconds", 5))
        self.timeout_seconds = max(1.0, min(30.0, timeout_seconds))
        retries = int(self.config.get("request_retries", 2))
        self.request_retries = max(0, min(5, retries))

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        api_key = str(self.config.get("api_key", "")).strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        extra = self.config.get("headers") or {}
        if isinstance(extra, dict):
            for key, value in extra.items():
                headers[str(key)] = str(value)
        return headers

    def _fetch_json(self, url: str) -> Dict[str, Any]:
        last_exc: Optional[Exception] = None
        for _ in range(self.request_retries + 1):
            try:
                resp = requests.get(url, headers=self._headers(), timeout=self.timeout_seconds)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # pragma: no cover - network failures depend on runtime
                last_exc = exc
        raise RuntimeError(f"Meiro request failed: {last_exc}")

    def fetch_profile_payload(self, external_user_id: str) -> Dict[str, Any]:
        request_url_template = str(self.config.get("request_url_template", "")).strip()
        if request_url_template:
            return self._fetch_json(
                request_url_template.format(
                    external_user_id=external_user_id,
                    value=external_user_id,
                )
            )

        base_url = str(self.config.get("base_url", "")).strip().rstrip("/")
        if not base_url:
            raise ValueError("Meiro base_url is required")
        endpoint_template = str(
            self.config.get("profile_endpoint_template", "/profiles/{external_user_id}")
        ).strip()
        if "{external_user_id}" not in endpoint_template:
            raise ValueError("profile_endpoint_template must contain {external_user_id}")
        endpoint = endpoint_template.format(external_user_id=external_user_id)
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        return self._fetch_json(f"{base_url}{endpoint}")

    def normalize_profile(
        self,
        payload: Dict[str, Any],
        mapping: Optional[Dict[str, Any]] = None,
        fallback_external_user_id: str = "",
    ) -> MeiroProfile:
        cfg = mapping or {}
        external_id_path = str(cfg.get("external_id_path", "customer_entity_id")).strip()
        traits_path = str(cfg.get("traits_path", "returned_attributes")).strip()
        segments_path = str(cfg.get("segments_path", "")).strip()
        fixed_segments = cfg.get("fixed_segments") or []
        if not isinstance(fixed_segments, list):
            fixed_segments = []

        external_user_id = str(_get_by_path(payload, external_id_path, fallback_external_user_id) or "").strip()
        if not external_user_id:
            raise ValueError("Unable to resolve external user ID from payload")

        traits = _get_by_path(payload, traits_path, {})
        if not isinstance(traits, dict):
            traits = {}

        segments_raw = _get_by_path(payload, segments_path, [])
        segments: List[str] = []
        if isinstance(segments_raw, list):
            segments = [str(item).strip() for item in segments_raw if str(item).strip()]
        elif isinstance(segments_raw, str):
            segments = [part.strip() for part in segments_raw.split(",") if part.strip()]
        for segment in fixed_segments:
            value = str(segment).strip()
            if value and value not in segments:
                segments.append(value)

        return MeiroProfile(
            external_user_id=external_user_id,
            traits=traits,
            segments=segments,
            raw=payload or {},
        )
