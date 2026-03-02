from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import fcntl
import hashlib
import hmac
import json
import logging
import os
import threading
import traceback
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, render_template, request

from store import RecommenderStore
from bootstrap_data import ensure_data_files
from connector_pipeline import ConnectorIngestionService
from meiro_adapter import MeiroAdapter
from config.logging_config import setup_logging
from recommend import RecommenderFactory

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

app = Flask(__name__)
store: Optional[RecommenderStore] = None
_connector_sync_executor = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("CONNECTOR_SYNC_WORKERS", "2")))
)
_recommender_reload_lock = threading.Lock()
_scheduler_state_lock = threading.Lock()
_scheduler_stop_event = threading.Event()
_scheduler_thread: Optional[threading.Thread] = None
_scheduler_lock_file_handle = None
_last_embed_mtime = 0.0
_rate_limit_lock = threading.Lock()
_rate_limit_counters: Dict[str, Dict] = {}
_cleanup_state_lock = threading.Lock()
_cleanup_thread: Optional[threading.Thread] = None
_cleanup_stop_event = threading.Event()
_cdp_state_lock = threading.Lock()
_cdp_thread: Optional[threading.Thread] = None
_cdp_stop_event = threading.Event()
_scheduler_state = {
    "enabled": False,
    "running": False,
    "interval_seconds": int(os.getenv("CONNECTOR_SCHEDULER_INTERVAL_SECONDS", "60")),
    "runs_total": 0,
    "errors_total": 0,
    "last_run_at": None,
    "last_duration_ms": None,
    "last_result": None,
    "last_error": None,
}

_cleanup_state = {
    "enabled": False,
    "running": False,
    "interval_seconds": int(os.getenv("CLEANUP_SCHEDULER_INTERVAL_SECONDS", "3600")),
    "runs_total": 0,
    "errors_total": 0,
    "last_run_at": None,
    "last_result": None,
    "last_error": None,
}

_cdp_state = {
    "enabled": False,
    "running": False,
    "interval_seconds": int(os.getenv("CDP_SYNC_INTERVAL_SECONDS", "900")),
    "runs_total": 0,
    "errors_total": 0,
    "last_run_at": None,
    "last_duration_ms": None,
    "last_result": None,
    "last_error": None,
}

_WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}
_MEIRO_PROVIDER = "meiro"
_DEFAULT_MEIRO_MAPPING = {
    "external_id_path": "customer_entity_id",
    "traits_path": "returned_attributes",
    "segments_path": "",
    "fixed_segments": [],
    "preferred_sources_trait": "preferred_sources",
    "excluded_sources_trait": "excluded_sources",
    "source_weights_trait": "source_weights",
    "source_weight_trait_prefix": "source_weight_",
    "scenario_segment_map": {},
    "config_segment_map": {},
    "segment_priority": [],
}


# Initialize recommender
try:
    ensure_data_files()
    recommender = RecommenderFactory.create_recommender(
        "advanced",
        diversity_weight=0.3,
        time_decay_days=30,
        cluster_weight=0.2,
    )
    store = RecommenderStore()
    _last_embed_mtime = recommender.embed_file.stat().st_mtime if recommender.embed_file.exists() else 0.0

    # Seed system configs from recommender presets.
    for cfg_id, cfg in recommender.get_ranking_configs().items():
        store.ensure_system_config(cfg_id, cfg)
    store.sync_sources([entry["source"] for entry in recommender.get_available_sources()])

    logger.info("Recommender initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize recommender: {str(e)}")
    logger.error(traceback.format_exc())
    recommender = None


def _parse_sources_param(value: str):
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _normalize_string_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        items = [str(part).strip() for part in value]
    else:
        return []
    return [item for item in items if item]


def _extract_sections(metadata: Dict, url: str) -> list:
    sections = []
    for key in ("section", "rubrika", "category", "categories"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            sections.append(value.strip().lower())
        elif isinstance(value, list):
            sections.extend(str(item).strip().lower() for item in value if str(item).strip())
    parsed = urlparse(url or "")
    path_parts = [segment for segment in parsed.path.split("/") if segment]
    if path_parts:
        sections.append(path_parts[0].lower())
    return sorted(set(sections))


def _safe_article_age_days(scraped_at: str) -> Optional[int]:
    if not scraped_at:
        return None
    try:
        ts = datetime.strptime(scraped_at, "%Y-%m-%d %H:%M:%S")
        return max(0, (datetime.now() - ts).days)
    except ValueError:
        return None


def _safe_parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _extract_error_code(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.split(":", 1)[0].strip().lower()


def _normalize_meiro_mapping(mapping: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(_DEFAULT_MEIRO_MAPPING)
    if isinstance(mapping, dict):
        for key, value in mapping.items():
            merged[str(key)] = value
    for key in (
        "external_id_path",
        "traits_path",
        "segments_path",
        "preferred_sources_trait",
        "excluded_sources_trait",
        "source_weights_trait",
        "source_weight_trait_prefix",
    ):
        merged[key] = str(merged.get(key, "")).strip()
    if not isinstance(merged.get("scenario_segment_map"), dict):
        merged["scenario_segment_map"] = {}
    if not isinstance(merged.get("config_segment_map"), dict):
        merged["config_segment_map"] = {}
    if not isinstance(merged.get("fixed_segments"), list):
        merged["fixed_segments"] = []
    if not isinstance(merged.get("segment_priority"), list):
        merged["segment_priority"] = []
    merged["fixed_segments"] = [str(item).strip() for item in merged["fixed_segments"] if str(item).strip()]
    merged["segment_priority"] = [str(item).strip() for item in merged["segment_priority"] if str(item).strip()]
    return merged


def _list_from_profile_trait(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _float_map_from_profile_trait(value: Any) -> Dict[str, float]:
    if not isinstance(value, dict):
        return {}
    out: Dict[str, float] = {}
    for key, raw in value.items():
        source = str(key).strip()
        if not source:
            continue
        try:
            out[source] = float(raw)
        except (TypeError, ValueError):
            continue
    return out


def _resolve_cdp_personalization(
    external_user_id: Optional[str],
    requested_sources: List[str],
    scenario_id: Optional[str],
    config_id: str,
    scenario_explicit: bool,
    config_explicit: bool,
) -> Dict[str, Any]:
    external = str(external_user_id or "").strip()
    base = {
        "applied": False,
        "provider": _MEIRO_PROVIDER,
        "external_user_id": external or None,
        "profile_found": False,
        "segments": [],
        "preferred_sources": [],
        "excluded_sources": [],
        "source_weight_overrides": {},
        "selected_scenario_id": scenario_id,
        "selected_config_id": config_id,
        "requested_sources": list(requested_sources or []),
        "mapping": _DEFAULT_MEIRO_MAPPING,
    }
    if not store:
        return base
    integration = store.get_cdp_integration(_MEIRO_PROVIDER)
    mapping = _normalize_meiro_mapping(integration.get("mapping"))
    base["mapping"] = mapping
    if not integration.get("enabled"):
        return base
    if not external:
        return base
    profile = store.get_cdp_profile(_MEIRO_PROVIDER, external)
    if not profile:
        return base
    base["profile_found"] = True
    traits = profile.get("traits") or {}
    if not isinstance(traits, dict):
        traits = {}
    segments = [str(item).strip() for item in (profile.get("segments") or []) if str(item).strip()]
    base["segments"] = segments

    preferred_sources = _list_from_profile_trait(traits.get(mapping.get("preferred_sources_trait")))
    excluded_sources = _list_from_profile_trait(traits.get(mapping.get("excluded_sources_trait")))
    source_weight_overrides = _float_map_from_profile_trait(traits.get(mapping.get("source_weights_trait")))
    prefix = mapping.get("source_weight_trait_prefix")
    if prefix:
        for key, value in traits.items():
            trait_key = str(key)
            if not trait_key.startswith(prefix):
                continue
            source = trait_key[len(prefix):].strip()
            if not source:
                continue
            try:
                source_weight_overrides[source] = float(value)
            except (TypeError, ValueError):
                continue

    source_set = set(requested_sources or [])
    source_set.update(preferred_sources)
    source_set.difference_update(excluded_sources)
    merged_sources = sorted(source_set)

    scenario_segment_map = {str(k): str(v).strip() for k, v in (mapping.get("scenario_segment_map") or {}).items() if str(v).strip()}
    config_segment_map = {str(k): str(v).strip() for k, v in (mapping.get("config_segment_map") or {}).items() if str(v).strip()}
    segment_priority = mapping.get("segment_priority") or []
    segment_order = segment_priority + [seg for seg in segments if seg not in segment_priority]

    selected_scenario_id = scenario_id
    if not scenario_explicit and not selected_scenario_id:
        for segment in segment_order:
            candidate = scenario_segment_map.get(segment)
            if candidate:
                selected_scenario_id = candidate
                break

    selected_config_id = config_id
    if not config_explicit:
        for segment in segment_order:
            candidate = config_segment_map.get(segment)
            if candidate:
                selected_config_id = candidate
                break

    base.update(
        {
            "applied": bool(profile),
            "preferred_sources": preferred_sources,
            "excluded_sources": excluded_sources,
            "source_weight_overrides": source_weight_overrides,
            "selected_scenario_id": selected_scenario_id,
            "selected_config_id": selected_config_id,
            "requested_sources": merged_sources,
            "profile_synced_at": profile.get("synced_at"),
        }
    )
    return base


def _resolve_experiment_assignment(
    experiment: Optional[Dict],
    effective_user_id: str,
) -> Optional[Dict]:
    if not isinstance(experiment, dict):
        return None
    experiment_id = str(experiment.get("experiment_id", "")).strip()
    variants = experiment.get("variants") or []
    if not experiment_id or not isinstance(variants, list) or not variants:
        return None

    normalized = []
    total_weight = 0.0
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        variant_id = str(variant.get("variant_id", "")).strip()
        weight = float(variant.get("weight", 0.0))
        if not variant_id or weight <= 0:
            continue
        normalized.append(
            {
                "variant_id": variant_id,
                "weight": weight,
                "config_id": str(variant.get("config_id", "")).strip() or None,
                "scenario_id": str(variant.get("scenario_id", "")).strip() or None,
                "source_overrides": _normalize_string_list(variant.get("sources")),
            }
        )
        total_weight += weight
    if not normalized or total_weight <= 0:
        return None

    token = f"{experiment_id}:{effective_user_id}"
    bucket = int(hashlib.sha1(token.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    cursor = 0.0
    selected = normalized[-1]
    for candidate in normalized:
        cursor += candidate["weight"] / total_weight
        if bucket <= cursor:
            selected = candidate
            break
    return {
        "experiment_id": experiment_id,
        "variant_id": selected["variant_id"],
        "bucket": round(bucket, 6),
        "selected_config_id": selected["config_id"],
        "selected_scenario_id": selected["scenario_id"],
        "selected_sources": selected["source_overrides"],
        "variants_total": len(normalized),
    }


def _resolve_article_source(article_id: Optional[str]) -> str:
    if not recommender or not article_id:
        return "unknown"
    article = recommender.article_vectors.get(article_id)
    if not article:
        return "unknown"
    url = article.get("metadata", {}).get("url", "")
    return recommender.extract_source(url)


def _resolve_event_source(event: Dict) -> str:
    metadata = event.get("metadata") or {}
    source = str(metadata.get("source") or "").strip()
    if source:
        return source
    return _resolve_article_source(event.get("article_id"))


def _validate_scenario_rule_set(rule_set: Dict) -> Dict:
    candidate = dict(rule_set or {})
    normalized = {
        "include_sources": _normalize_string_list(candidate.get("include_sources")),
        "exclude_sources": _normalize_string_list(candidate.get("exclude_sources")),
        "include_sections": [value.lower() for value in _normalize_string_list(candidate.get("include_sections"))],
        "exclude_sections": [value.lower() for value in _normalize_string_list(candidate.get("exclude_sections"))],
        "include_keywords": [value.lower() for value in _normalize_string_list(candidate.get("include_keywords"))],
        "exclude_keywords": [value.lower() for value in _normalize_string_list(candidate.get("exclude_keywords"))],
        "exclude_article_ids": _normalize_string_list(candidate.get("exclude_article_ids")),
        "max_age_days": candidate.get("max_age_days"),
        "min_score": candidate.get("min_score"),
        "source_boosts": {
            str(key): float(value)
            for key, value in (candidate.get("source_boosts") or {}).items()
        },
        "ranking_config_id": str(candidate.get("ranking_config_id", "")).strip() or None,
    }

    if normalized["max_age_days"] is not None:
        normalized["max_age_days"] = max(0, int(normalized["max_age_days"]))
    if normalized["min_score"] is not None:
        normalized["min_score"] = float(normalized["min_score"])
    for source, boost in normalized["source_boosts"].items():
        if boost <= 0:
            raise ValueError(f"source_boosts[{source}] must be greater than 0")

    return normalized


def _resolve_effective_user_id(user_id: str, external_user_id: Optional[str]) -> str:
    external = (external_user_id or "").strip()
    if external:
        return f"ext:{external}"
    return user_id


def _read_idempotency_key(payload: Optional[Dict]) -> Optional[str]:
    header_key = (request.headers.get("Idempotency-Key") or "").strip()
    if header_key:
        return header_key
    if payload and isinstance(payload, dict):
        body_key = str(payload.get("idempotency_key", "")).strip()
        if body_key:
            return body_key
    return None


def _request_actor_id(payload: Optional[Dict] = None) -> str:
    header_actor = (request.headers.get("X-Actor-Id") or "").strip()
    if header_actor:
        return header_actor
    if payload and isinstance(payload, dict):
        actor = str(payload.get("actor_id", "")).strip()
        if actor:
            return actor
    return "system"


def _is_protected_request() -> bool:
    protected_paths = (
        request.path.startswith("/api/v1/")
        or request.path.startswith("/api/recommendations/cms")
        or request.path.startswith("/api/events")
        or request.path.startswith("/api/scenarios")
        or request.path.startswith("/api/ranking-configs")
        or request.path.startswith("/api/connectors")
        or request.path.startswith("/api/source-settings")
        or request.path.startswith("/api/cdp")
        or request.path.startswith("/api/metrics/rollups")
    )
    return protected_paths and request.method in _WRITE_METHODS.union({"GET"})


def _enforce_api_key_if_enabled() -> Optional[Tuple[Dict, int]]:
    enabled = os.getenv("API_AUTH_ENABLED", "false").strip().lower() == "true"
    if not enabled:
        return None
    if not _is_protected_request():
        return None

    configured = [part.strip() for part in os.getenv("API_AUTH_KEYS", "").split(",") if part.strip()]
    if not configured:
        return {"error": "API auth enabled but API_AUTH_KEYS is empty"}, 503

    provided = (request.headers.get("X-API-Key") or "").strip()
    if not provided:
        return {"error": "Missing API key"}, 401
    if provided not in configured:
        return {"error": "Invalid API key"}, 403
    return None


def _enforce_hmac_signature_if_enabled() -> Optional[Tuple[Dict, int]]:
    enabled = os.getenv("API_SIGNATURE_ENABLED", "false").strip().lower() == "true"
    if not enabled:
        return None
    if request.method not in _WRITE_METHODS:
        return None
    if not _is_protected_request():
        return None

    secret = os.getenv("API_SIGNATURE_SECRET", "").strip()
    if not secret:
        return {"error": "API signature enabled but API_SIGNATURE_SECRET is empty"}, 503

    signature = (request.headers.get("X-Signature") or "").strip()
    timestamp = (request.headers.get("X-Timestamp") or "").strip()
    if not signature or not timestamp:
        return {"error": "Missing signature headers"}, 401

    try:
        ts = int(timestamp)
    except ValueError:
        return {"error": "Invalid X-Timestamp"}, 400

    skew = max(1, int(os.getenv("API_SIGNATURE_MAX_SKEW_SECONDS", "300")))
    now_ts = int(datetime.now().timestamp())
    if abs(now_ts - ts) > skew:
        return {"error": "Signature timestamp outside allowed skew"}, 401

    raw_body = request.get_data(cache=True) or b""
    payload = timestamp.encode("utf-8") + b"\n" + raw_body
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return {"error": "Invalid signature"}, 403
    return None


def _rate_limit_for_endpoint(path: str) -> int:
    default_limit = max(1, int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "120")))
    rules_env = os.getenv("API_RATE_LIMIT_RULES", "").strip()
    rules: Dict[str, int] = {}
    if rules_env:
        try:
            parsed = json.loads(rules_env)
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    rules[str(key)] = int(value)
        except Exception:
            logger.warning("Invalid API_RATE_LIMIT_RULES JSON; falling back to defaults")
    if not rules:
        rules = {
            "/api/recommendations/cms": 60,
            "/api/v1/recommendations/cms": 60,
            "/api/events": 120,
            "/api/v1/events": 120,
            "/api/scenarios": 30,
            "/api/ranking-configs": 30,
            "/api/cdp": 60,
            "/api/metrics/rollups": 10,
        }

    matched_limit = default_limit
    best_len = -1
    for prefix, limit in rules.items():
        if path.startswith(prefix) and len(prefix) > best_len:
            matched_limit = max(1, int(limit))
            best_len = len(prefix)
    return matched_limit


def _enforce_rate_limit_if_enabled() -> Optional[Tuple[Dict, int]]:
    enabled = os.getenv("API_RATE_LIMIT_ENABLED", "false").strip().lower() == "true"
    if not enabled:
        return None
    if not _is_protected_request():
        return None
    limit = _rate_limit_for_endpoint(request.path)
    actor = (request.headers.get("X-Actor-Id") or request.remote_addr or "unknown").strip() or "unknown"
    endpoint = request.path
    now = datetime.now()
    bucket = now.strftime("%Y-%m-%d %H:%M")
    key = f"{actor}|{endpoint}|{bucket}"

    with _rate_limit_lock:
        counter = _rate_limit_counters.get(key)
        if not counter:
            counter = {"count": 0, "created_at": now}
            _rate_limit_counters[key] = counter
        counter["count"] += 1
        count = counter["count"]

        stale_before = now - timedelta(minutes=2)
        stale_keys = [k for k, v in _rate_limit_counters.items() if v["created_at"] < stale_before]
        for stale_key in stale_keys:
            _rate_limit_counters.pop(stale_key, None)

    if count > limit:
        return {
            "error": "Rate limit exceeded",
            "limit_per_minute": limit,
            "actor": actor,
            "endpoint": endpoint,
        }, 429
    return None


def _run_cleanup_cycle() -> Dict:
    if not store:
        raise ValueError("Store unavailable")
    idempotency_hours = max(0, int(os.getenv("IDEMPOTENCY_RETENTION_HOURS", "72")))
    audit_days = max(0, int(os.getenv("AUDIT_RETENTION_DAYS", "90")))
    removed_idempotency = store.purge_idempotency_records(older_than_hours=idempotency_hours)
    removed_audit = store.purge_audit_events(older_than_days=audit_days)
    return {
        "idempotency_hours": idempotency_hours,
        "audit_days": audit_days,
        "removed_idempotency": removed_idempotency,
        "removed_audit_events": removed_audit,
    }


def _cleanup_loop() -> None:
    while not _cleanup_stop_event.is_set():
        try:
            result = _run_cleanup_cycle()
            with _cleanup_state_lock:
                _cleanup_state["runs_total"] += 1
                _cleanup_state["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _cleanup_state["last_result"] = result
                _cleanup_state["last_error"] = None
        except Exception as exc:
            with _cleanup_state_lock:
                _cleanup_state["runs_total"] += 1
                _cleanup_state["errors_total"] += 1
                _cleanup_state["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _cleanup_state["last_error"] = str(exc)
            logger.error(f"Cleanup cycle failed: {str(exc)}")
            logger.error(traceback.format_exc())
        _cleanup_stop_event.wait(_cleanup_state["interval_seconds"])


def _start_cleanup_scheduler_if_enabled() -> None:
    global _cleanup_thread
    enabled = os.getenv("CLEANUP_SCHEDULER_ENABLED", "true").strip().lower() == "true"
    with _cleanup_state_lock:
        _cleanup_state["enabled"] = enabled
    if not enabled:
        return
    if not store:
        return
    if _cleanup_thread and _cleanup_thread.is_alive():
        return
    _cleanup_thread = threading.Thread(target=_cleanup_loop, name="cleanup-scheduler", daemon=True)
    _cleanup_thread.start()
    with _cleanup_state_lock:
        _cleanup_state["running"] = True


def _collect_recent_external_user_ids(days: int = 30, limit_events: int = 20000, limit_runs: int = 5000) -> List[str]:
    if not store:
        return []
    external_ids = set()
    for event in store.list_events(limit=limit_events, days=max(1, days)):
        external = str(event.get("external_user_id") or "").strip()
        if external:
            external_ids.add(external)
    for run in store.list_runs_with_request(limit=limit_runs, offset=0, days=max(1, days)):
        external = str((run.get("request") or {}).get("external_user_id") or "").strip()
        if external:
            external_ids.add(external)
    return sorted(external_ids)


def _execute_cdp_sync_run(trigger: str = "manual", external_user_ids: Optional[List[str]] = None) -> Dict:
    if not store:
        raise ValueError("Store unavailable")
    integration = store.get_cdp_integration(_MEIRO_PROVIDER)
    if not integration.get("enabled"):
        return {
            "provider": _MEIRO_PROVIDER,
            "trigger": trigger,
            "status": "skipped_disabled",
            "attempted": 0,
            "synced": 0,
            "errors": [{"error": "Meiro integration is disabled"}],
        }

    requested_ids = [str(item).strip() for item in (external_user_ids or []) if str(item).strip()]
    if not requested_ids:
        requested_ids = _collect_recent_external_user_ids(
            days=max(1, int(os.getenv("CDP_SYNC_LOOKBACK_DAYS", "30"))),
            limit_events=max(100, int(os.getenv("CDP_SYNC_LOOKBACK_EVENTS_LIMIT", "20000"))),
            limit_runs=max(100, int(os.getenv("CDP_SYNC_LOOKBACK_RUNS_LIMIT", "5000"))),
        )
    max_ids = max(1, int(os.getenv("CDP_SYNC_MAX_IDS_PER_RUN", "200")))
    requested_ids = requested_ids[:max_ids]
    run_id = store.start_cdp_sync_run(_MEIRO_PROVIDER, trigger=trigger, requested_ids=requested_ids)
    if not requested_ids:
        finished = store.finish_cdp_sync_run(run_id, status="completed", attempted=0, synced=0, errors=[])
        return {"provider": _MEIRO_PROVIDER, "run_id": run_id, "run": finished, "synced": [], "errors": []}

    adapter = MeiroAdapter(integration.get("config") or {})
    mapping = _normalize_meiro_mapping(integration.get("mapping"))
    synced = []
    errors = []
    for external_user_id in requested_ids:
        try:
            raw_payload = adapter.fetch_profile_payload(external_user_id)
            profile = adapter.normalize_profile(
                raw_payload,
                mapping=mapping,
                fallback_external_user_id=external_user_id,
            )
            stored_profile = store.upsert_cdp_profile(
                provider=_MEIRO_PROVIDER,
                external_user_id=profile.external_user_id,
                traits=profile.traits,
                segments=profile.segments,
                raw_payload=profile.raw,
            )
            synced.append(stored_profile)
        except Exception as exc:
            errors.append({"external_user_id": external_user_id, "error": str(exc)})
    status = "completed" if not errors else "completed_with_errors"
    finished = store.finish_cdp_sync_run(
        run_id,
        status=status,
        attempted=len(requested_ids),
        synced=len(synced),
        errors=errors,
    )
    return {
        "provider": _MEIRO_PROVIDER,
        "run_id": run_id,
        "run": finished,
        "requested_ids": requested_ids,
        "synced": synced,
        "errors": errors,
        "attempted": len(requested_ids),
        "synced_count": len(synced),
        "error_count": len(errors),
    }


def _cdp_sync_loop() -> None:
    while not _cdp_stop_event.is_set():
        started_at = datetime.now()
        try:
            result = _execute_cdp_sync_run(trigger="scheduled", external_user_ids=None)
            duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
            with _cdp_state_lock:
                _cdp_state["runs_total"] += 1
                _cdp_state["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _cdp_state["last_duration_ms"] = duration_ms
                _cdp_state["last_result"] = {
                    "status": result.get("run", {}).get("status", result.get("status")),
                    "attempted": result.get("attempted", 0),
                    "synced_count": result.get("synced_count", 0),
                    "error_count": result.get("error_count", 0),
                }
                _cdp_state["last_error"] = None
        except Exception as exc:
            with _cdp_state_lock:
                _cdp_state["runs_total"] += 1
                _cdp_state["errors_total"] += 1
                _cdp_state["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _cdp_state["last_error"] = str(exc)
            logger.error(f"CDP sync cycle failed: {str(exc)}")
            logger.error(traceback.format_exc())
        _cdp_stop_event.wait(_cdp_state["interval_seconds"])


def _start_cdp_scheduler_if_enabled() -> None:
    global _cdp_thread
    enabled = os.getenv("CDP_SYNC_SCHEDULER_ENABLED", "false").strip().lower() == "true"
    with _cdp_state_lock:
        _cdp_state["enabled"] = enabled
    if not enabled:
        return
    if not store:
        return
    if _cdp_thread and _cdp_thread.is_alive():
        return
    _cdp_thread = threading.Thread(target=_cdp_sync_loop, name="cdp-sync-scheduler", daemon=True)
    _cdp_thread.start()
    with _cdp_state_lock:
        _cdp_state["running"] = True


def _record_audit(
    action: str,
    resource_type: str,
    resource_id: str,
    payload: Optional[Dict] = None,
    extra: Optional[Dict] = None,
) -> None:
    if not store:
        return
    actor_id = _request_actor_id(payload)
    metadata = {
        "method": request.method,
        "path": request.path,
        "remote_addr": request.remote_addr,
    }
    if extra:
        metadata.update(extra)
    try:
        store.record_audit_event(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
        )
    except Exception:
        logger.exception("Failed to record audit event")


def _compute_observability_snapshot(days: int) -> Dict:
    if not store:
        raise ValueError("Store unavailable")
    days = max(1, min(365, int(days)))
    rec_rows = store.list_runs(limit=2000, offset=0)
    duration_samples = []
    cutoff = datetime.now() - timedelta(days=days)
    rec_count_window = 0
    for run in rec_rows:
        created_at = datetime.strptime(run["created_at"], "%Y-%m-%d %H:%M:%S")
        if created_at < cutoff:
            continue
        rec_count_window += 1
        duration = run.get("summary", {}).get("duration_ms")
        if isinstance(duration, (int, float)):
            duration_samples.append(float(duration))
    duration_samples.sort()
    p95_idx = int(0.95 * (len(duration_samples) - 1)) if duration_samples else 0
    p95_ms = duration_samples[p95_idx] if duration_samples else None
    avg_ms = (sum(duration_samples) / len(duration_samples)) if duration_samples else None

    event_rows = store.list_events(limit=5000, offset=0, days=days)
    events_total = len(event_rows)
    events_by_type = {"impression": 0, "click": 0, "conversion": 0}
    for event in event_rows:
        if event["event_type"] in events_by_type:
            events_by_type[event["event_type"]] += 1

    connectors = store.list_connectors()
    connector_run_total = 0
    connector_failures = 0
    connector_attempted_total = 0
    connector_blocked_total = 0
    blocker_codes = {"blocked_cookie_wall", "blocked_paywall", "blocked_login_wall"}
    for connector in connectors:
        runs = store.list_connector_runs(connector["connector_id"], limit=100)
        for run in runs:
            started = run.get("started_at")
            if not started:
                continue
            started_at = _safe_parse_timestamp(started)
            if started_at is None:
                continue
            if started_at < cutoff:
                continue
            connector_run_total += 1
            connector_attempted_total += int(run.get("attempted", 0) or 0)
            if run["status"] == "failed":
                connector_failures += 1
            for error in (run.get("errors") or []):
                if _extract_error_code(error) in blocker_codes:
                    connector_blocked_total += 1

    ctr = round((events_by_type["click"] / events_by_type["impression"]), 4) if events_by_type["impression"] else 0.0
    connector_failure_rate = round((connector_failures / connector_run_total), 4) if connector_run_total else 0.0
    connector_blocker_rate = (
        round((connector_blocked_total / connector_attempted_total), 4) if connector_attempted_total else 0.0
    )
    rollup_rows = store.list_event_rollups(days=days)
    latest_rollup_at = None
    for row in rollup_rows:
        ts = _safe_parse_timestamp(str(row.get("updated_at", "")))
        if ts and (latest_rollup_at is None or ts > latest_rollup_at):
            latest_rollup_at = ts
    rollup_lag_hours = None
    if latest_rollup_at:
        rollup_lag_hours = max(0.0, round((datetime.now() - latest_rollup_at).total_seconds() / 3600.0, 2))
    thresholds = store.get_alert_thresholds()

    return {
        "api_version": "v1",
        "window_days": days,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "recommendation_api": {
            "runs": rec_count_window,
            "avg_duration_ms": round(avg_ms, 2) if avg_ms is not None else None,
            "p95_duration_ms": round(p95_ms, 2) if p95_ms is not None else None,
        },
        "events": {
            "total": events_total,
            "impressions": events_by_type["impression"],
            "clicks": events_by_type["click"],
            "conversions": events_by_type["conversion"],
            "ctr": ctr,
        },
        "connectors": {
            "total_connectors": len(connectors),
            "runs": connector_run_total,
            "failed_runs": connector_failures,
            "failure_rate": connector_failure_rate,
            "attempted_total": connector_attempted_total,
            "blocked_total": connector_blocked_total,
            "blocker_rate": connector_blocker_rate,
        },
        "rollups": {
            "rows": len(rollup_rows),
            "latest_updated_at": latest_rollup_at.strftime("%Y-%m-%d %H:%M:%S") if latest_rollup_at else None,
            "lag_hours": rollup_lag_hours,
        },
        "slo_targets": thresholds,
    }


def _build_sli_checks(snapshot: Dict) -> list:
    thresholds = snapshot.get("slo_targets", {})
    p95 = snapshot.get("recommendation_api", {}).get("p95_duration_ms")
    failure_rate = snapshot.get("connectors", {}).get("failure_rate", 0.0)
    blocker_rate = snapshot.get("connectors", {}).get("blocker_rate", 0.0)
    rollup_lag_hours = snapshot.get("rollups", {}).get("lag_hours")
    ctr = snapshot.get("events", {}).get("ctr", 0.0)
    return [
        {
            "metric": "recommendation_p95_ms",
            "value": p95,
            "target_max": float(thresholds.get("recommendation_p95_ms", 500.0)),
            "status": "pass" if (p95 is not None and p95 <= float(thresholds.get("recommendation_p95_ms", 500.0))) else "warn",
        },
        {
            "metric": "connector_failure_rate",
            "value": failure_rate,
            "target_max": float(thresholds.get("connector_failure_rate", 0.05)),
            "status": "pass" if failure_rate <= float(thresholds.get("connector_failure_rate", 0.05)) else "warn",
        },
        {
            "metric": "connector_blocker_rate",
            "value": blocker_rate,
            "target_max": float(thresholds.get("connector_blocker_rate", 0.2)),
            "status": "pass" if blocker_rate <= float(thresholds.get("connector_blocker_rate", 0.2)) else "warn",
        },
        {
            "metric": "max_rollup_lag_hours",
            "value": rollup_lag_hours,
            "target_max": float(thresholds.get("max_rollup_lag_hours", 24.0)),
            "status": (
                "pass"
                if (
                    rollup_lag_hours is not None
                    and rollup_lag_hours <= float(thresholds.get("max_rollup_lag_hours", 24.0))
                )
                else "warn"
            ),
        },
        {
            "metric": "ctr",
            "value": ctr,
            "target_min": float(thresholds.get("min_ctr", 0.01)),
            "status": "pass" if ctr >= float(thresholds.get("min_ctr", 0.01)) else "warn",
        },
    ]


def _sync_alert_incidents_from_checks(checks: list, actor_id: str = "system") -> Dict:
    if not store:
        return {"opened_or_updated": 0, "resolved": 0}
    opened_or_updated = 0
    resolved = 0
    for check in checks:
        metric = check.get("metric")
        value = check.get("value")
        threshold_value = check.get("target_max", check.get("target_min"))
        if check.get("status") == "warn":
            store.upsert_alert_incident(
                metric=metric,
                current_value=float(value) if value is not None else None,
                threshold_value=float(threshold_value) if threshold_value is not None else None,
                details={"check": check},
            )
            opened_or_updated += 1
        else:
            resolved += store.resolve_open_alert_incidents(
                metric=metric,
                resolved_by=actor_id,
                note="SLI back within threshold",
            )
    return {"opened_or_updated": opened_or_updated, "resolved": resolved}


def _apply_scenario_rules(
    recommendations: list,
    scenario: Optional[Dict],
    include_decisions: bool = False,
) -> Tuple[list, Dict]:
    if not scenario:
        trace = {"applied": False, "scenario_id": None, "filtered_out": 0, "reasons": {}}
        if include_decisions:
            trace["decisions"] = []
        return recommendations, trace

    rule_set = scenario.get("rule_set") or {}
    include_sources = set(_normalize_string_list(rule_set.get("include_sources")))
    exclude_sources = set(_normalize_string_list(rule_set.get("exclude_sources")))
    include_sections = set(value.lower() for value in _normalize_string_list(rule_set.get("include_sections")))
    exclude_sections = set(value.lower() for value in _normalize_string_list(rule_set.get("exclude_sections")))
    include_keywords = [value.lower() for value in _normalize_string_list(rule_set.get("include_keywords"))]
    exclude_keywords = [value.lower() for value in _normalize_string_list(rule_set.get("exclude_keywords"))]
    exclude_article_ids = set(_normalize_string_list(rule_set.get("exclude_article_ids")))
    source_boosts = {key: float(value) for key, value in (rule_set.get("source_boosts") or {}).items()}
    max_age_days = rule_set.get("max_age_days")
    min_score = rule_set.get("min_score")
    if max_age_days is not None:
        max_age_days = max(0, int(max_age_days))
    if min_score is not None:
        min_score = float(min_score)

    kept = []
    filtered = 0
    reasons: Dict[str, int] = {}
    decisions = []

    for rec in recommendations:
        article_id = rec.get("article_id")
        article_meta = recommender.article_vectors.get(article_id, {}).get("metadata", {})
        source = rec.get("source", "unknown")
        title = str(article_meta.get("title", rec.get("title", ""))).lower()
        content = str(article_meta.get("content", rec.get("content", ""))).lower()
        url = str(article_meta.get("url", rec.get("url", "")))
        sections = _extract_sections(article_meta, url)
        scraped_at = str(article_meta.get("scraped_at", ""))
        age_days = _safe_article_age_days(scraped_at)

        deny_reason = None
        if include_sources and source not in include_sources:
            deny_reason = "source_not_included"
        elif source in exclude_sources:
            deny_reason = "source_excluded"
        elif include_sections and not any(section in include_sections for section in sections):
            deny_reason = "section_not_included"
        elif exclude_sections and any(section in exclude_sections for section in sections):
            deny_reason = "section_excluded"
        elif exclude_article_ids and article_id in exclude_article_ids:
            deny_reason = "article_excluded"
        elif include_keywords and not any(keyword in f"{title} {content}" for keyword in include_keywords):
            deny_reason = "keyword_not_included"
        elif exclude_keywords and any(keyword in f"{title} {content}" for keyword in exclude_keywords):
            deny_reason = "keyword_excluded"
        elif max_age_days is not None and age_days is not None and age_days > max_age_days:
            deny_reason = "too_old"
        elif min_score is not None and float(rec.get("score", 0.0)) < min_score:
            deny_reason = "below_min_score"

        if deny_reason:
            filtered += 1
            reasons[deny_reason] = reasons.get(deny_reason, 0) + 1
            if include_decisions:
                decisions.append(
                    {
                        "article_id": article_id,
                        "source": source,
                        "status": "filtered",
                        "reason": deny_reason,
                        "score_before": round(float(rec.get("score", 0.0)), 4),
                    }
                )
            continue

        boost = float(source_boosts.get(source, 1.0))
        updated = dict(rec)
        original_score = float(updated.get("score", 0.0))
        boosted_score = original_score * boost
        updated["score_before_scenario"] = round(original_score, 4)
        updated["score"] = round(boosted_score, 4)
        updated["scenario_boost"] = round(boost, 4)
        updated["scenario_id"] = scenario["scenario_id"]
        kept.append(updated)
        if include_decisions:
            decisions.append(
                {
                    "article_id": article_id,
                    "source": source,
                    "status": "kept",
                    "reason": "passed",
                    "score_before": round(original_score, 4),
                    "score_after": round(boosted_score, 4),
                    "boost": round(boost, 4),
                }
            )

    kept.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    return kept, {
        "applied": True,
        "scenario_id": scenario["scenario_id"],
        "scenario_name": scenario.get("name"),
        "filtered_out": filtered,
        "remaining": len(kept),
        "reasons": reasons,
        "decisions": decisions if include_decisions else None,
    }


def _build_run_decision_flow(run: Dict) -> Dict:
    request_payload = run.get("request", {}) or {}
    scenario_trace = request_payload.get("scenario_trace") or {}
    decisions = scenario_trace.get("decisions")
    if not isinstance(decisions, list):
        decisions = []

    item_by_article = {item.get("article_id"): item for item in (run.get("items") or [])}
    rows = []
    for idx, decision in enumerate(decisions, start=1):
        article_id = decision.get("article_id")
        item = item_by_article.get(article_id, {})
        score_before = decision.get("score_before")
        score_after = decision.get("score_after")
        boost = decision.get("boost")
        if score_after is None and item:
            score_after = item.get("score")
        if score_before is None and score_after is not None and boost not in (None, 0):
            try:
                score_before = float(score_after) / float(boost)
            except (TypeError, ValueError, ZeroDivisionError):
                score_before = None
        rows.append(
            {
                "position": idx,
                "article_id": article_id,
                "source": decision.get("source") or item.get("source"),
                "status": decision.get("status") or ("kept" if item else "filtered"),
                "reason": decision.get("reason") or "n/a",
                "score_before": round(float(score_before), 4) if isinstance(score_before, (int, float)) else None,
                "score_after": round(float(score_after), 4) if isinstance(score_after, (int, float)) else None,
                "boost": round(float(boost), 4) if isinstance(boost, (int, float)) else None,
                "final_rank": item.get("rank"),
                "final_explanation": item.get("explanation"),
            }
        )

    if not rows:
        for item in run.get("items", []):
            rows.append(
                {
                    "position": item.get("rank"),
                    "article_id": item.get("article_id"),
                    "source": item.get("source"),
                    "status": "kept",
                    "reason": "no_scenario_decisions",
                    "score_before": None,
                    "score_after": item.get("score"),
                    "boost": None,
                    "final_rank": item.get("rank"),
                    "final_explanation": item.get("explanation"),
                }
            )

    return {
        "run_id": run.get("run_id"),
        "scenario_id": request_payload.get("scenario_id"),
        "scenario_trace_summary": {
            "applied": bool(scenario_trace.get("applied")),
            "filtered_out": int(scenario_trace.get("filtered_out") or 0),
            "remaining": int(scenario_trace.get("remaining") or 0),
            "reasons": scenario_trace.get("reasons") or {},
        },
        "decisions": rows,
    }


def _load_sources_with_settings() -> Tuple[list, Dict[str, Dict]]:
    if not recommender or not store:
        return [], {}
    sources = recommender.get_available_sources()
    source_names = [entry["source"] for entry in sources]
    store.sync_sources(source_names)
    settings = store.list_source_settings()
    return sources, settings


def _maybe_reload_recommender_if_changed() -> None:
    global _last_embed_mtime
    if not recommender:
        return
    embed_file = recommender.embed_file
    if not embed_file.exists():
        return
    try:
        mtime = embed_file.stat().st_mtime
    except OSError:
        return
    if mtime <= _last_embed_mtime:
        return
    with _recommender_reload_lock:
        try:
            mtime_now = embed_file.stat().st_mtime
        except OSError:
            return
        if mtime_now <= _last_embed_mtime:
            return
        recommender._load_data()
        _last_embed_mtime = mtime_now


def _merge_source_settings(sources: list, settings: Dict[str, Dict]) -> list:
    merged = []
    for entry in sources:
        source = entry["source"]
        source_setting = settings.get(source, {})
        merged.append(
            {
                "source": source,
                "article_count": entry.get("article_count", 0),
                "enabled": bool(source_setting.get("enabled", True)),
                "default_weight": float(source_setting.get("default_weight", 1.0)),
                "updated_at": source_setting.get("updated_at"),
            }
        )
    return merged


def _resolve_selected_sources(
    requested_sources: list,
    merged_sources: list,
) -> Tuple[list, Dict[str, float]]:
    available = {entry["source"] for entry in merged_sources}
    enabled = {entry["source"] for entry in merged_sources if entry.get("enabled", True)}

    if requested_sources:
        selected = [source for source in requested_sources if source in available and source in enabled]
    else:
        selected = sorted(enabled)

    defaults = {
        entry["source"]: float(entry.get("default_weight", 1.0))
        for entry in merged_sources
        if entry["source"] in selected
    }
    return selected, defaults


def _apply_source_weight_defaults(config: Optional[Dict], source_defaults: Dict[str, float]) -> Optional[Dict]:
    if config is None:
        return None

    updated = dict(config)
    merged_source_weights = dict(updated.get("source_weights", {}))
    for source, default_weight in source_defaults.items():
        merged_source_weights[source] = float(merged_source_weights.get(source, 1.0)) * float(default_weight)
    updated["source_weights"] = merged_source_weights
    return updated


def _resolve_ranking_config(
    config_id: str,
    ranking_config: Optional[Dict],
) -> Tuple[str, int, Optional[Dict]]:
    """Resolve config for scoring and trace metadata.

    Returns (effective_config_id, config_version, config_payload_for_recommender).
    """
    if not recommender:
        raise ValueError("Recommender not initialized")

    if ranking_config:
        effective_id = ranking_config.get("config_id", config_id or "inline_custom")
        return effective_id, 0, ranking_config

    if not store:
        raise ValueError("Config store unavailable")

    result = store.get_config(config_id)
    if not result:
        raise ValueError(f"Unknown ranking config: {config_id}")

    cfg, version, _is_system = result
    return config_id, version, cfg


def _acquire_scheduler_lock() -> bool:
    global _scheduler_lock_file_handle
    lock_path = os.getenv("CONNECTOR_SCHEDULER_LOCK_PATH", "/tmp/article_recommender_scheduler.lock")
    try:
        _scheduler_lock_file_handle = open(lock_path, "a+", encoding="utf-8")
        fcntl.flock(_scheduler_lock_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _run_scheduler_loop() -> None:
    while not _scheduler_stop_event.is_set():
        started_at = datetime.now()
        try:
            result = _enqueue_due_connector_syncs(trigger_label="scheduled_auto")
            duration = int((datetime.now() - started_at).total_seconds() * 1000)
            with _scheduler_state_lock:
                _scheduler_state["runs_total"] += 1
                _scheduler_state["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _scheduler_state["last_duration_ms"] = duration
                _scheduler_state["last_result"] = result
                _scheduler_state["last_error"] = None
        except Exception as exc:
            duration = int((datetime.now() - started_at).total_seconds() * 1000)
            with _scheduler_state_lock:
                _scheduler_state["runs_total"] += 1
                _scheduler_state["errors_total"] += 1
                _scheduler_state["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _scheduler_state["last_duration_ms"] = duration
                _scheduler_state["last_error"] = str(exc)
            logger.error(f"Connector scheduler cycle failed: {str(exc)}")
            logger.error(traceback.format_exc())
        _scheduler_stop_event.wait(_scheduler_state["interval_seconds"])


def _start_connector_scheduler_if_enabled() -> None:
    global _scheduler_thread
    enabled = os.getenv("CONNECTOR_SCHEDULER_ENABLED", "false").strip().lower() == "true"
    with _scheduler_state_lock:
        _scheduler_state["enabled"] = enabled
    if not enabled:
        return
    if not store or not recommender:
        logger.info("Scheduler enabled but recommender/store is not initialized; skipping scheduler thread.")
        return
    if not _acquire_scheduler_lock():
        logger.info("Scheduler lock already held by another process; skipping scheduler thread.")
        return
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _scheduler_thread = threading.Thread(target=_run_scheduler_loop, name="connector-scheduler", daemon=True)
    _scheduler_thread.start()
    with _scheduler_state_lock:
        _scheduler_state["running"] = True


def _normalize_connector_config(connector_type: str, config: Dict) -> Dict:
    candidate = dict(config or {})
    if connector_type == "rss":
        feed_url = str(candidate.get("feed_url", "")).strip()
        if not feed_url:
            raise ValueError("RSS connector requires config.feed_url")
        parsed = urlparse(feed_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("config.feed_url must be a valid http(s) URL")
        candidate["feed_url"] = feed_url
        candidate.pop("base_url", None)
    elif connector_type == "section_scraper":
        base_url = str(candidate.get("base_url", "")).strip()
        if not base_url:
            raise ValueError("Section connector requires config.base_url")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("config.base_url must be a valid http(s) URL")
        candidate["base_url"] = base_url
        candidate.pop("feed_url", None)
    else:
        raise ValueError("connector_type must be one of: section_scraper, rss")

    max_articles = int(candidate.get("max_articles", 10))
    sync_interval_minutes = int(candidate.get("sync_interval_minutes", 60))
    candidate["max_articles"] = max(1, min(50, max_articles))
    candidate["sync_interval_minutes"] = max(1, min(24 * 60, sync_interval_minutes))
    candidate["auto_sync_enabled"] = bool(candidate.get("auto_sync_enabled", False))
    return candidate


def _build_decision_context(
    requested_sources: list,
    config_id: str,
    ranking_config: Optional[Dict],
) -> Dict:
    effective_config_id, config_version, resolved_config = _resolve_ranking_config(config_id, ranking_config)
    available_sources, source_settings = _load_sources_with_settings()
    merged_sources = _merge_source_settings(available_sources, source_settings)
    selected_sources, source_defaults = _resolve_selected_sources(requested_sources, merged_sources)
    effective_ranking_config = _apply_source_weight_defaults(resolved_config, source_defaults)
    return {
        "requested_sources": requested_sources,
        "selected_sources": selected_sources,
        "source_defaults_applied": source_defaults,
        "effective_config_id": effective_config_id,
        "config_version": config_version,
        "effective_ranking_config": effective_ranking_config,
    }


@app.before_request
def before_request():
    if request.endpoint != "static":
        _maybe_reload_recommender_if_changed()

    auth_error = _enforce_api_key_if_enabled()
    if auth_error:
        body, status = auth_error
        return jsonify(body), status

    signature_error = _enforce_hmac_signature_if_enabled()
    if signature_error:
        body, status = signature_error
        return jsonify(body), status

    rate_error = _enforce_rate_limit_if_enabled()
    if rate_error:
        body, status = rate_error
        return jsonify(body), status

    if request.is_json:
        try:
            request.get_json(silent=False)
        except Exception as e:
            logger.error(f"Invalid JSON in request: {str(e)}")
            abort(400, description="Invalid JSON format")

    logger.info(f"Request: {request.method} {request.path} from {request.remote_addr}")


@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    return response


@app.route("/")
def index():
    return render_template("recommendations.html", active_page="recommendations", title="Recommendations")


@app.route("/recommendations")
def recommendations_page():
    return render_template("recommendations.html", active_page="recommendations", title="Recommendations")


@app.route("/reporting")
def reporting_page():
    return render_template("reporting.html", active_page="reporting", title="Reporting")


@app.route("/operations")
def operations_page():
    return render_template("operations.html", active_page="operations", title="Operations")


@app.route("/runs")
def runs_page():
    return render_template("runs.html", active_page="runs", title="Run Explorer")


@app.route("/cdp")
def cdp_page():
    return render_template("cdp.html", active_page="cdp", title="CDP Integration")


@app.route("/healthz")
def healthz():
    """Liveness probe: process is running."""
    return jsonify({"status": "ok"}), 200


@app.route("/readyz")
def readyz():
    """Readiness probe: app dependencies initialized."""
    if not recommender or not store:
        return jsonify({"status": "not_ready"}), 503
    return jsonify({"status": "ready"}), 200


@app.route("/api/articles")
def get_articles():
    if not recommender:
        return jsonify({"error": "Recommender not initialized"}), 500

    try:
        articles = []
        for article_id, data in recommender.article_vectors.items():
            metadata = data.get("metadata", {})
            if not metadata.get("title"):
                continue

            articles.append(
                {
                    "article_id": article_id,
                    "title": metadata.get("title", ""),
                    "content": metadata.get("content", ""),
                    "source": recommender.extract_source(metadata.get("url", "")),
                    "metadata": metadata,
                }
            )

        return jsonify(articles)
    except Exception as e:
        logger.error(f"Error getting articles: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/sources")
def get_sources():
    if not recommender or not store:
        return jsonify({"error": "Recommender not initialized"}), 500

    try:
        sources, settings = _load_sources_with_settings()
        merged_sources = _merge_source_settings(sources, settings)
        return jsonify({"sources": merged_sources, "total_sources": len(merged_sources)})
    except Exception as e:
        logger.error(f"Error getting sources: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/source-settings", methods=["GET"])
def get_source_settings():
    if not recommender or not store:
        return jsonify({"error": "Recommender not initialized"}), 500

    try:
        sources, settings = _load_sources_with_settings()
        merged_sources = _merge_source_settings(sources, settings)
        return jsonify({"sources": merged_sources, "count": len(merged_sources)})
    except Exception as e:
        logger.error(f"Error getting source settings: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/source-settings/<path:source>", methods=["PUT"])
def update_source_setting(source):
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    try:
        payload = request.get_json() or {}
        enabled = bool(payload.get("enabled", True))
        default_weight = float(payload.get("default_weight", 1.0))
        if default_weight <= 0:
            return jsonify({"error": "default_weight must be greater than 0"}), 400
        store.set_source_setting(source, enabled=enabled, default_weight=default_weight)
        _record_audit(
            action="update",
            resource_type="source_setting",
            resource_id=source,
            payload=payload,
            extra={"enabled": enabled, "default_weight": default_weight},
        )
        return jsonify({"source": source, "enabled": enabled, "default_weight": default_weight})
    except Exception as e:
        logger.error(f"Error updating source setting: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/cdp/meiro", methods=["GET", "PUT"])
def cdp_meiro_config():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        if request.method == "GET":
            integration = store.get_cdp_integration(_MEIRO_PROVIDER)
            config = dict(integration.get("config") or {})
            if config.get("api_key"):
                config["api_key"] = "***"
            return jsonify(
                {
                    "provider": _MEIRO_PROVIDER,
                    "enabled": bool(integration.get("enabled")),
                    "config": config,
                    "mapping": _normalize_meiro_mapping(integration.get("mapping")),
                    "updated_at": integration.get("updated_at"),
                }
            )

        payload = request.get_json() or {}
        integration = store.get_cdp_integration(_MEIRO_PROVIDER)
        current_config = dict(integration.get("config") or {})
        current_mapping = _normalize_meiro_mapping(integration.get("mapping"))
        next_enabled = payload.get("enabled")
        next_config = payload.get("config") if isinstance(payload.get("config"), dict) else current_config
        next_mapping = payload.get("mapping") if isinstance(payload.get("mapping"), dict) else current_mapping
        # Keep existing secret if UI sends masked value.
        if str(next_config.get("api_key", "")).strip() == "***":
            next_config["api_key"] = current_config.get("api_key", "")
        stored = store.upsert_cdp_integration(
            provider=_MEIRO_PROVIDER,
            config=next_config,
            mapping=_normalize_meiro_mapping(next_mapping),
            enabled=(bool(next_enabled) if next_enabled is not None else None),
        )
        _record_audit(
            action="update",
            resource_type="cdp_integration",
            resource_id=_MEIRO_PROVIDER,
            payload=payload,
            extra={"enabled": stored.get("enabled")},
        )
        safe_config = dict(stored.get("config") or {})
        if safe_config.get("api_key"):
            safe_config["api_key"] = "***"
        return jsonify(
            {
                "provider": _MEIRO_PROVIDER,
                "enabled": bool(stored.get("enabled")),
                "config": safe_config,
                "mapping": _normalize_meiro_mapping(stored.get("mapping")),
                "updated_at": stored.get("updated_at"),
            }
        )
    except Exception as e:
        logger.error(f"Error handling CDP config: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/cdp/meiro/profiles", methods=["GET"])
def cdp_meiro_profiles():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        limit = max(1, min(200, int(request.args.get("limit", 50))))
        offset = max(0, int(request.args.get("offset", 0)))
        rows = store.list_cdp_profiles(_MEIRO_PROVIDER, limit=limit + 1, offset=offset)
        has_more = len(rows) > limit
        profiles = rows[:limit]
        return jsonify(
            {
                "provider": _MEIRO_PROVIDER,
                "profiles": profiles,
                "count": len(profiles),
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": (offset + limit) if has_more else None,
            }
        )
    except Exception as e:
        logger.error(f"Error listing CDP profiles: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/cdp/meiro/profiles/<external_user_id>", methods=["GET"])
def cdp_meiro_profile_detail(external_user_id):
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    profile = store.get_cdp_profile(_MEIRO_PROVIDER, external_user_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify(profile)


@app.route("/api/cdp/meiro/profiles/upsert", methods=["POST"])
def cdp_meiro_profile_upsert():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        payload = request.get_json() or {}
        integration = store.get_cdp_integration(_MEIRO_PROVIDER)
        mapping = _normalize_meiro_mapping(integration.get("mapping"))
        adapter = MeiroAdapter(integration.get("config") or {})
        profile = adapter.normalize_profile(
            payload,
            mapping=mapping,
            fallback_external_user_id=str(payload.get("external_user_id", "")).strip(),
        )
        stored = store.upsert_cdp_profile(
            provider=_MEIRO_PROVIDER,
            external_user_id=profile.external_user_id,
            traits=profile.traits,
            segments=profile.segments,
            raw_payload=profile.raw,
        )
        _record_audit(
            action="upsert",
            resource_type="cdp_profile",
            resource_id=profile.external_user_id,
            payload=payload,
            extra={"provider": _MEIRO_PROVIDER},
        )
        return jsonify({"provider": _MEIRO_PROVIDER, "profile": stored}), 201
    except Exception as e:
        logger.error(f"Error upserting CDP profile: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/cdp/meiro/sync", methods=["POST"])
def cdp_meiro_sync_profiles():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        payload = request.get_json() or {}
        external_user_ids = [str(item).strip() for item in (payload.get("external_user_ids") or []) if str(item).strip()]
        if not external_user_ids and payload.get("use_recent_external_ids") is not True:
            return jsonify({"error": "external_user_ids is required (or set use_recent_external_ids=true)"}), 400
        result = _execute_cdp_sync_run(
            trigger="manual",
            external_user_ids=(external_user_ids if external_user_ids else None),
        )
        _record_audit(
            action="sync",
            resource_type="cdp_profile",
            resource_id=_MEIRO_PROVIDER,
            payload=payload,
            extra={
                "run_id": result.get("run_id"),
                "attempted": result.get("attempted", 0),
                "synced": result.get("synced_count", 0),
                "errors": result.get("error_count", 0),
            },
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error syncing CDP profiles: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/cdp/meiro/sync-runs", methods=["GET"])
def cdp_meiro_sync_runs():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        limit = max(1, min(100, int(request.args.get("limit", 20))))
        rows = store.list_cdp_sync_runs(_MEIRO_PROVIDER, limit=limit)
        return jsonify({"provider": _MEIRO_PROVIDER, "runs": rows, "count": len(rows)})
    except Exception as e:
        logger.error(f"Error listing CDP sync runs: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/cdp/meiro/sync-runs/<run_id>", methods=["GET"])
def cdp_meiro_sync_run_detail(run_id):
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    run = store.get_cdp_sync_run(run_id)
    if not run:
        return jsonify({"error": "Sync run not found"}), 404
    return jsonify(run)


@app.route("/api/cdp/meiro/scheduler/status", methods=["GET"])
def cdp_meiro_scheduler_status():
    with _cdp_state_lock:
        snapshot = dict(_cdp_state)
    snapshot["provider"] = _MEIRO_PROVIDER
    return jsonify(snapshot)


@app.route("/api/cdp/meiro/scheduler/run-now", methods=["POST"])
def cdp_meiro_scheduler_run_now():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        payload = request.get_json(silent=True) or {}
        requested_ids = [str(item).strip() for item in (payload.get("external_user_ids") or []) if str(item).strip()]
        result = _execute_cdp_sync_run(
            trigger="run_now",
            external_user_ids=(requested_ids if requested_ids else None),
        )
        with _cdp_state_lock:
            _cdp_state["runs_total"] += 1
            _cdp_state["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _cdp_state["last_result"] = {
                "status": result.get("run", {}).get("status", result.get("status")),
                "attempted": result.get("attempted", 0),
                "synced_count": result.get("synced_count", 0),
                "error_count": result.get("error_count", 0),
            }
            if result.get("error_count", 0) > 0:
                _cdp_state["errors_total"] += 1
                _cdp_state["last_error"] = f"{result.get('error_count')} errors"
            else:
                _cdp_state["last_error"] = None
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error executing CDP run-now: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/cdp/meiro/diagnostics", methods=["GET"])
def cdp_meiro_diagnostics():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        freshness_hours = max(1, min(24 * 30, int(request.args.get("freshness_hours", 24))))
        profile_limit = max(1, min(10000, int(request.args.get("profile_limit", 2000))))
        run_limit = max(1, min(10000, int(request.args.get("run_limit", 2000))))
        sync_run_limit = max(1, min(200, int(request.args.get("sync_run_limit", 50))))

        integration = store.get_cdp_integration(_MEIRO_PROVIDER)
        profiles = store.list_cdp_profiles(_MEIRO_PROVIDER, limit=profile_limit, offset=0)
        now = datetime.now()
        stale_cutoff = now - timedelta(hours=freshness_hours)
        freshness = {"fresh": 0, "stale": 0, "unknown": 0}
        for item in profiles:
            synced_at = _safe_parse_timestamp(str(item.get("synced_at", "")))
            if synced_at is None:
                freshness["unknown"] += 1
            elif synced_at >= stale_cutoff:
                freshness["fresh"] += 1
            else:
                freshness["stale"] += 1

        recent_runs = store.list_runs_with_request(limit=run_limit, offset=0, days=30)
        runs_with_external = 0
        cdp_profile_found = 0
        cdp_applied = 0
        for run in recent_runs:
            req = run.get("request") or {}
            external = str(req.get("external_user_id") or "").strip()
            if not external:
                continue
            runs_with_external += 1
            cdp_ctx = req.get("cdp_context") or {}
            if cdp_ctx.get("profile_found"):
                cdp_profile_found += 1
            if cdp_ctx.get("applied"):
                cdp_applied += 1

        sync_runs = store.list_cdp_sync_runs(_MEIRO_PROVIDER, limit=sync_run_limit)
        sync_attempted = sum(int(item.get("attempted") or 0) for item in sync_runs)
        sync_synced = sum(int(item.get("synced") or 0) for item in sync_runs)
        sync_errors = sum(int(item.get("error_count") or 0) for item in sync_runs)

        return jsonify(
            {
                "provider": _MEIRO_PROVIDER,
                "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "integration_enabled": bool(integration.get("enabled")),
                "profiles": {
                    "count": len(profiles),
                    "freshness_hours": freshness_hours,
                    "freshness": freshness,
                    "fresh_ratio": round((freshness["fresh"] / len(profiles)), 4) if profiles else 0.0,
                    "stale_ratio": round((freshness["stale"] / len(profiles)), 4) if profiles else 0.0,
                },
                "mapping_coverage": {
                    "runs_with_external_id": runs_with_external,
                    "runs_with_cdp_profile_found": cdp_profile_found,
                    "runs_with_cdp_applied": cdp_applied,
                    "profile_found_ratio": round((cdp_profile_found / runs_with_external), 4) if runs_with_external else 0.0,
                    "applied_ratio": round((cdp_applied / runs_with_external), 4) if runs_with_external else 0.0,
                },
                "sync_runs": {
                    "count": len(sync_runs),
                    "attempted_total": sync_attempted,
                    "synced_total": sync_synced,
                    "errors_total": sync_errors,
                    "success_ratio": round((sync_synced / sync_attempted), 4) if sync_attempted else 0.0,
                    "recent": sync_runs[:10],
                },
            }
        )
    except Exception as e:
        logger.error(f"Error building CDP diagnostics: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/connectors", methods=["GET", "POST"])
def connectors():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    if request.method == "GET":
        try:
            connectors_data = store.list_connectors()
            return jsonify({"connectors": connectors_data, "count": len(connectors_data)})
        except Exception as e:
            logger.error(f"Error listing connectors: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    try:
        payload = request.get_json() or {}
        name = (payload.get("name") or "").strip()
        connector_type = (payload.get("connector_type") or "").strip()
        config = payload.get("config") or {}
        enabled = bool(payload.get("enabled", True))

        if not name:
            return jsonify({"error": "name is required"}), 400
        if connector_type not in {"section_scraper", "rss"}:
            return jsonify({"error": "connector_type must be one of: section_scraper, rss"}), 400
        config = _normalize_connector_config(connector_type, config)

        connector = store.create_connector(
            name=name,
            connector_type=connector_type,
            config=config,
            enabled=enabled,
        )
        _record_audit(
            action="create",
            resource_type="connector",
            resource_id=connector.get("connector_id", ""),
            payload=payload,
            extra={"name": name, "connector_type": connector_type},
        )
        return jsonify(connector), 201
    except Exception as e:
        logger.error(f"Error creating connector: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/connectors/<connector_id>", methods=["PUT", "DELETE"])
def connector_detail(connector_id):
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    if request.method == "DELETE":
        deleted = store.delete_connector(connector_id)
        if not deleted:
            return jsonify({"error": "Connector not found"}), 404
        _record_audit(
            action="delete",
            resource_type="connector",
            resource_id=connector_id,
            extra={},
        )
        return jsonify({"deleted": True, "connector_id": connector_id})

    try:
        payload = request.get_json() or {}
        connector_type = payload.get("connector_type")
        if connector_type and connector_type not in {"section_scraper", "rss"}:
            return jsonify({"error": "connector_type must be one of: section_scraper, rss"}), 400
        current = store.get_connector(connector_id)
        if not current:
            return jsonify({"error": "Connector not found"}), 404
        effective_type = connector_type or current.get("connector_type")
        effective_config = payload.get("config")
        if effective_config is None:
            effective_config = current.get("config", {})
        effective_config = _normalize_connector_config(effective_type, effective_config)

        connector = store.update_connector(
            connector_id=connector_id,
            name=payload.get("name"),
            connector_type=effective_type,
            config=effective_config,
            enabled=payload.get("enabled"),
        )
        _record_audit(
            action="update",
            resource_type="connector",
            resource_id=connector_id,
            payload=payload,
            extra={"connector_type": effective_type},
        )
        return jsonify(connector)
    except Exception as e:
        logger.error(f"Error updating connector: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/connectors/<connector_id>/sync", methods=["POST"])
def connector_sync(connector_id):
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    try:
        connector = store.get_connector(connector_id)
        if not connector:
            return jsonify({"error": "Connector not found"}), 404
        if not connector.get("enabled", True):
            return jsonify({"error": "Connector is disabled"}), 400

        run_id = store.start_connector_run(connector_id, trigger="manual")
        outcome = _execute_connector_sync_run(run_id=run_id, connector_id=connector_id)
        updated = store.get_connector(connector_id)
        return jsonify(
            {
                "message": "Connector sync executed.",
                "connector": updated,
                "run_id": run_id,
                "run": outcome["run"],
                "ingestion": outcome["ingestion"],
            }
        )
    except Exception as e:
        if "run_id" in locals():
            store.finish_connector_run(
                run_id=run_id,
                status="failed",
                errors=[str(e)],
            )
        logger.error(f"Error syncing connector: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/connectors/<connector_id>/sync-async", methods=["POST"])
def connector_sync_async(connector_id):
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    connector = store.get_connector(connector_id)
    if not connector:
        return jsonify({"error": "Connector not found"}), 404
    if not connector.get("enabled", True):
        return jsonify({"error": "Connector is disabled"}), 400

    run_id = store.start_connector_run(connector_id, trigger="manual_async")
    _connector_sync_executor.submit(_execute_connector_sync_run, run_id, connector_id)
    return jsonify({"run_id": run_id, "connector_id": connector_id, "status": "running"}), 202


@app.route("/api/connectors/sync-due", methods=["POST"])
def connector_sync_due():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    try:
        result = _enqueue_due_connector_syncs(trigger_label="scheduled")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error running due connector syncs: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/connectors/scheduler/status", methods=["GET"])
def connector_scheduler_status():
    with _scheduler_state_lock:
        snapshot = dict(_scheduler_state)
    return jsonify(snapshot)


@app.route("/api/connectors/scheduler/run-now", methods=["POST"])
def connector_scheduler_run_now():
    try:
        started_at = datetime.now()
        result = _enqueue_due_connector_syncs(trigger_label="scheduled_manual")
        duration = int((datetime.now() - started_at).total_seconds() * 1000)
        with _scheduler_state_lock:
            _scheduler_state["runs_total"] += 1
            _scheduler_state["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _scheduler_state["last_duration_ms"] = duration
            _scheduler_state["last_result"] = result
            _scheduler_state["last_error"] = None
        return jsonify({"scheduler_run": result, "duration_ms": duration})
    except Exception as e:
        with _scheduler_state_lock:
            _scheduler_state["errors_total"] += 1
            _scheduler_state["last_error"] = str(e)
        logger.error(f"Error forcing scheduler run: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/connectors/<connector_id>/runs", methods=["GET"])
def connector_runs(connector_id):
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    try:
        limit = int(request.args.get("limit", 20))
        runs = store.list_connector_runs(connector_id, limit=limit)
        return jsonify({"connector_id": connector_id, "runs": runs, "count": len(runs)})
    except Exception as e:
        logger.error(f"Error listing connector runs: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/connectors/metrics", methods=["GET"])
def connector_metrics():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    try:
        connectors = store.list_connectors()
        per_connector = []
        total_runs = 0
        success_like = 0
        total_ingested = 0
        for connector in connectors:
            runs = store.list_connector_runs(connector["connector_id"], limit=50)
            run_count = len(runs)
            total_runs += run_count
            success_count = len([r for r in runs if r["status"] in ("completed", "completed_with_errors")])
            success_like += success_count
            ingested_sum = sum(int(r.get("ingested", 0)) for r in runs)
            total_ingested += ingested_sum
            last_run = runs[0] if runs else {}
            last_errors = last_run.get("errors") or []
            first_error = str(last_errors[0]) if last_errors else ""
            error_code = first_error.split(":", 1)[0] if first_error else None
            health_state = "healthy"
            if last_run.get("status") == "failed":
                health_state = "failing"
            elif last_run.get("status") == "completed_with_errors":
                health_state = "degraded"
            elif not runs:
                health_state = "idle"
            per_connector.append(
                {
                    "connector_id": connector["connector_id"],
                    "name": connector["name"],
                    "run_count": run_count,
                    "success_rate": round((success_count / run_count), 4) if run_count else 0.0,
                    "avg_ingested": round((ingested_sum / run_count), 4) if run_count else 0.0,
                    "last_status": last_run.get("status"),
                    "last_run_at": connector.get("last_run_at"),
                    "health_state": health_state,
                    "last_error_code": error_code,
                }
            )

        return jsonify(
            {
                "total_connectors": len(connectors),
                "total_runs": total_runs,
                "overall_success_rate": round((success_like / total_runs), 4) if total_runs else 0.0,
                "avg_ingested_per_run": round((total_ingested / total_runs), 4) if total_runs else 0.0,
                "connectors": per_connector,
            }
        )
    except Exception as e:
        logger.error(f"Error computing connector metrics: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/connector-runs/<run_id>", methods=["GET"])
def connector_run_detail(run_id):
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    run = store.get_connector_run(run_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(run)


def _execute_connector_sync_run(run_id: str, connector_id: str) -> Dict:
    if not store or not recommender:
        raise ValueError("Recommender not initialized")

    connector = store.get_connector(connector_id)
    if not connector:
        store.finish_connector_run(run_id=run_id, status="failed", errors=["Connector not found"])
        return {"run": store.get_connector_run(run_id), "ingestion": {}}
    if not connector.get("enabled", True):
        store.finish_connector_run(run_id=run_id, status="failed", errors=["Connector is disabled"])
        return {"run": store.get_connector_run(run_id), "ingestion": {}}

    try:
        ingestion_service = ConnectorIngestionService(recommender.embed_file)
        ingestion_result = ingestion_service.sync_connector(connector)
        status = "completed" if not ingestion_result.errors else "completed_with_errors"
        run = store.finish_connector_run(
            run_id=run_id,
            status=status,
            attempted=ingestion_result.attempted,
            ingested=ingestion_result.ingested,
            skipped_existing=ingestion_result.skipped_existing,
            errors=ingestion_result.errors,
        )
        if ingestion_result.ingested > 0:
            with _recommender_reload_lock:
                recommender._load_data()
                store.sync_sources([entry["source"] for entry in recommender.get_available_sources()])
        store.mark_connector_sync(connector_id)
        if ingestion_result.ingested > 0:
            run = store.get_connector_run(run_id)
        return {"run": run, "ingestion": ingestion_result.to_dict()}
    except Exception as e:
        store.finish_connector_run(
            run_id=run_id,
            status="failed",
            errors=[str(e)],
        )
        raise


def _enqueue_due_connector_syncs(trigger_label: str = "scheduled") -> Dict:
    if not store:
        raise ValueError("Store unavailable")
    now = datetime.now()
    triggered = []
    skipped = []
    connectors = store.list_connectors()
    for connector in connectors:
        config = connector.get("config") or {}
        if not connector.get("enabled", True):
            skipped.append({"connector_id": connector["connector_id"], "reason": "disabled"})
            continue
        if not bool(config.get("auto_sync_enabled", False)):
            skipped.append({"connector_id": connector["connector_id"], "reason": "auto_sync_disabled"})
            continue

        interval = int(config.get("sync_interval_minutes", 60))
        interval = max(1, interval)
        last_run_at = connector.get("last_run_at")
        due = True
        if last_run_at:
            try:
                last = datetime.strptime(last_run_at, "%Y-%m-%d %H:%M:%S")
                due = now - last >= timedelta(minutes=interval)
            except ValueError:
                due = True

        if not due:
            skipped.append({"connector_id": connector["connector_id"], "reason": "not_due"})
            continue

        run_id = store.start_connector_run(connector["connector_id"], trigger=trigger_label)
        _connector_sync_executor.submit(_execute_connector_sync_run, run_id, connector["connector_id"])
        triggered.append({"connector_id": connector["connector_id"], "run_id": run_id})

    return {
        "triggered": triggered,
        "skipped": skipped,
        "triggered_count": len(triggered),
        "skipped_count": len(skipped),
    }


_start_connector_scheduler_if_enabled()
_start_cleanup_scheduler_if_enabled()
_start_cdp_scheduler_if_enabled()


@app.route("/api/ranking-configs", methods=["GET", "POST"])
def ranking_configs():
    if not recommender or not store:
        return jsonify({"error": "Recommender not initialized"}), 500

    if request.method == "GET":
        try:
            configs = store.list_latest_configs()
            return jsonify(
                {
                    "default_config_id": "balanced",
                    "configs": configs,
                }
            )
        except Exception as e:
            logger.error(f"Error getting ranking configs: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    # POST create custom config
    try:
        payload = request.get_json() or {}
        config_id = payload.get("config_id", "").strip()
        if not config_id:
            return jsonify({"error": "config_id is required"}), 400

        config_payload = {
            "config_id": config_id,
            "weights": payload.get("weights", {}),
            "time_decay_days": int(payload.get("time_decay_days", 30)),
            "source_weights": payload.get("source_weights", {}),
        }
        # Validate via recommender logic
        recommender._resolve_config(config_id=config_id, ranking_config=config_payload)

        version = store.create_or_update_config(config_id, config_payload, is_system=False)
        _record_audit(
            action="create",
            resource_type="ranking_config",
            resource_id=config_id,
            payload=payload,
            extra={"version": version},
        )
        return jsonify({"config_id": config_id, "version": version}), 201
    except Exception as e:
        logger.error(f"Error creating ranking config: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/ranking-configs/<config_id>", methods=["PUT", "DELETE"])
def ranking_config_detail(config_id):
    if not recommender or not store:
        return jsonify({"error": "Recommender not initialized"}), 500

    if request.method == "DELETE":
        deleted = store.delete_config(config_id)
        if not deleted:
            return jsonify({"error": "Config not found or is system config"}), 400
        _record_audit(
            action="delete",
            resource_type="ranking_config",
            resource_id=config_id,
            extra={},
        )
        return jsonify({"deleted": True, "config_id": config_id})

    # PUT: create new version
    try:
        payload = request.get_json() or {}
        config_payload = {
            "config_id": config_id,
            "weights": payload.get("weights", {}),
            "time_decay_days": int(payload.get("time_decay_days", 30)),
            "source_weights": payload.get("source_weights", {}),
        }
        recommender._resolve_config(config_id=config_id, ranking_config=config_payload)

        version = store.create_or_update_config(config_id, config_payload, is_system=False)
        _record_audit(
            action="update",
            resource_type="ranking_config",
            resource_id=config_id,
            payload=payload,
            extra={"version": version},
        )
        return jsonify({"config_id": config_id, "version": version})
    except Exception as e:
        logger.error(f"Error updating ranking config: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/scenarios", methods=["GET", "POST"])
def scenarios():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    if request.method == "GET":
        include_disabled = request.args.get("include_disabled", "true").lower() == "true"
        scenario_items = store.list_scenarios(include_disabled=include_disabled)
        return jsonify({"scenarios": scenario_items, "count": len(scenario_items)})

    try:
        payload = request.get_json() or {}
        scenario_id = str(payload.get("scenario_id", "")).strip()
        name = str(payload.get("name", "")).strip()
        if not scenario_id:
            return jsonify({"error": "scenario_id is required"}), 400
        if not name:
            return jsonify({"error": "name is required"}), 400
        rule_set = _validate_scenario_rule_set(payload.get("rule_set") or {})
        scenario = store.upsert_scenario(
            scenario_id=scenario_id,
            name=name,
            description=str(payload.get("description", "")).strip(),
            enabled=bool(payload.get("enabled", True)),
            rule_set=rule_set,
            metadata=payload.get("metadata") or {},
        )
        _record_audit(
            action="create",
            resource_type="scenario",
            resource_id=scenario_id,
            payload=payload,
            extra={"enabled": bool(payload.get("enabled", True))},
        )
        return jsonify(scenario), 201
    except Exception as e:
        logger.error(f"Error creating scenario: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/scenarios/<scenario_id>", methods=["GET", "PUT", "DELETE"])
def scenario_detail(scenario_id):
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    if request.method == "GET":
        scenario = store.get_scenario(scenario_id)
        if not scenario:
            return jsonify({"error": "Scenario not found"}), 404
        return jsonify(scenario)

    if request.method == "DELETE":
        deleted = store.delete_scenario(scenario_id)
        if not deleted:
            return jsonify({"error": "Scenario not found"}), 404
        _record_audit(
            action="delete",
            resource_type="scenario",
            resource_id=scenario_id,
            extra={},
        )
        return jsonify({"deleted": True, "scenario_id": scenario_id})

    try:
        current = store.get_scenario(scenario_id)
        if not current:
            return jsonify({"error": "Scenario not found"}), 404
        payload = request.get_json() or {}
        scenario = store.upsert_scenario(
            scenario_id=scenario_id,
            name=str(payload.get("name", current["name"])).strip(),
            description=str(payload.get("description", current.get("description", ""))).strip(),
            enabled=bool(payload.get("enabled", current.get("enabled", True))),
            rule_set=_validate_scenario_rule_set(payload.get("rule_set") or current.get("rule_set") or {}),
            metadata=payload.get("metadata") if "metadata" in payload else current.get("metadata", {}),
        )
        _record_audit(
            action="update",
            resource_type="scenario",
            resource_id=scenario_id,
            payload=payload,
            extra={"enabled": scenario.get("enabled")},
        )
        return jsonify(scenario)
    except Exception as e:
        logger.error(f"Error updating scenario: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/recommendations/query", methods=["POST"])
def query_recommendations():
    if not recommender or not store:
        return jsonify({"error": "Recommender not initialized"}), 500

    try:
        started_at = datetime.now()
        payload = request.get_json() or {}
        user_id = payload.get("user_id", "demo_user")
        external_user_id = str(payload.get("external_user_id", "")).strip() or None
        effective_user_id = _resolve_effective_user_id(user_id, external_user_id)
        user_reads = payload.get("user_reads") or recommender.user_profiles.get(effective_user_id, [])
        if not user_reads:
            user_reads = recommender.user_profiles.get(user_id, [])
        top_n = int(payload.get("top_n", 5))
        requested_sources = payload.get("sources") or []
        config_explicit = bool(str(payload.get("config_id", "")).strip())
        config_id = str(payload.get("config_id", "balanced")).strip() or "balanced"
        ranking_config = payload.get("ranking_config")
        experiment = payload.get("experiment")
        scenario_id = (payload.get("scenario_id") or "").strip() or None
        scenario_explicit = bool(scenario_id)
        scenario_ids = payload.get("scenario_ids") or []
        if scenario_ids and not scenario_id:
            scenario_id = str(scenario_ids[0]).strip() or None
            scenario_explicit = bool(scenario_id)
        cdp_context = _resolve_cdp_personalization(
            external_user_id=external_user_id,
            requested_sources=requested_sources,
            scenario_id=scenario_id,
            config_id=config_id,
            scenario_explicit=scenario_explicit,
            config_explicit=config_explicit,
        )
        requested_sources = cdp_context.get("requested_sources") or requested_sources
        if not scenario_explicit and cdp_context.get("selected_scenario_id"):
            scenario_id = cdp_context.get("selected_scenario_id")
        if not config_explicit and cdp_context.get("selected_config_id"):
            config_id = cdp_context.get("selected_config_id")
        scenario = None
        if scenario_id:
            scenario = store.get_scenario(scenario_id)
            if not scenario:
                return jsonify({"error": f"Scenario not found: {scenario_id}"}), 404
            if not scenario.get("enabled", True):
                return jsonify({"error": f"Scenario is disabled: {scenario_id}"}), 400
            scenario_rule_set = scenario.get("rule_set") or {}
            if not requested_sources and scenario_rule_set.get("include_sources"):
                requested_sources = scenario_rule_set.get("include_sources") or []
            if not ranking_config and scenario_rule_set.get("ranking_config_id"):
                config_id = scenario_rule_set.get("ranking_config_id")

        experiment_assignment = _resolve_experiment_assignment(experiment, effective_user_id)
        if experiment_assignment:
            if experiment_assignment.get("selected_scenario_id"):
                scenario_id = experiment_assignment["selected_scenario_id"]
                scenario = store.get_scenario(scenario_id) if scenario_id else None
            if experiment_assignment.get("selected_config_id"):
                config_id = experiment_assignment["selected_config_id"]
            if experiment_assignment.get("selected_sources"):
                requested_sources = experiment_assignment["selected_sources"]

        decision_context = _build_decision_context(requested_sources, config_id, ranking_config)
        effective_config_id = decision_context["effective_config_id"]
        config_version = decision_context["config_version"]
        selected_sources = decision_context["selected_sources"]
        source_defaults = decision_context["source_defaults_applied"]
        effective_ranking_config = decision_context["effective_ranking_config"]
        cdp_source_overrides = cdp_context.get("source_weight_overrides") or {}
        if cdp_source_overrides:
            source_weights = dict(effective_ranking_config.get("source_weights") or {})
            for source, weight in cdp_source_overrides.items():
                if source in selected_sources and weight > 0:
                    source_weights[source] = float(weight)
            effective_ranking_config["source_weights"] = source_weights
        if scenario:
            excluded_sources = set(_normalize_string_list(scenario.get("rule_set", {}).get("exclude_sources")))
            if excluded_sources:
                selected_sources = [source for source in selected_sources if source not in excluded_sources]

        if selected_sources:
            recs = recommender.recommend_for_user(
                effective_user_id,
                recommender.article_vectors,
                user_reads,
                top_n=top_n,
                sources=selected_sources,
                config_id=effective_config_id,
                ranking_config=effective_ranking_config,
            )
        else:
            recs = []
        recs, scenario_trace = _apply_scenario_rules(recs, scenario, include_decisions=True)
        recs = recs[: max(1, top_n)]

        run_id = store.persist_recommendation_run(
            user_id=effective_user_id,
            config_id=effective_config_id,
            config_version=config_version,
            request_payload={
                "user_id": user_id,
                "effective_user_id": effective_user_id,
                "external_user_id": external_user_id,
                "user_reads": user_reads,
                "top_n": top_n,
                "sources": selected_sources,
                "config_id": effective_config_id,
                "effective_ranking_config": effective_ranking_config,
                "scenario_id": scenario_id,
                "scenario_trace": scenario_trace,
                "experiment_assignment": experiment_assignment,
                "cdp_context": cdp_context,
            },
            recommendations=recs,
            request_duration_ms=int((datetime.now() - started_at).total_seconds() * 1000),
        )
        track_impressions = bool(payload.get("track_impressions", True))
        if track_impressions and recs:
            store.record_events(
                [
                    {
                        "event_type": "impression",
                        "run_id": run_id,
                        "article_id": rec.get("article_id"),
                        "scenario_id": scenario_id,
                        "user_id": effective_user_id,
                        "external_user_id": external_user_id,
                        "rank_position": idx,
                        "metadata": {"score": rec.get("score"), "source": rec.get("source")},
                    }
                    for idx, rec in enumerate(recs, start=1)
                ]
            )

        return jsonify(
            {
                "run_id": run_id,
                "user_id": user_id,
                "effective_user_id": effective_user_id,
                "external_user_id": external_user_id,
                "top_n": top_n,
                "sources": selected_sources,
                "config_id": effective_config_id,
                "config_version": config_version,
                "source_defaults_applied": source_defaults,
                "effective_ranking_config": effective_ranking_config,
                "scenario_id": scenario_id,
                "scenario_trace": scenario_trace,
                "experiment_assignment": experiment_assignment,
                "cdp_context": cdp_context,
                "recommendations": recs,
            }
        )
    except Exception as e:
        logger.error(f"Error querying recommendations: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/recommendation-runs")
def list_recommendation_runs():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    try:
        limit = max(1, min(200, int(request.args.get("limit", 20))))
        offset = max(0, int(request.args.get("offset", 0)))
        rows = store.list_runs(limit=limit + 1, offset=offset)
        has_more = len(rows) > limit
        runs = rows[:limit]
        return jsonify(
            {
                "runs": runs,
                "count": len(runs),
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": (offset + limit) if has_more else None,
            }
        )
    except Exception as e:
        logger.error(f"Error listing runs: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/recommendation-runs/<run_id>")
def get_recommendation_run(run_id):
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    run = store.get_run(run_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(run)


@app.route("/api/recommendation-runs/<run_id>/decision-flow")
def get_recommendation_run_decision_flow(run_id):
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    run = store.get_run(run_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(_build_run_decision_flow(run))


@app.route("/api/recommendations/cms", methods=["POST"])
@app.route("/api/v1/recommendations/cms", methods=["POST"])
def recommendations_cms():
    """CMS-oriented recommendation endpoint with external ID + compact response payload."""
    if not recommender or not store:
        return jsonify({"error": "Recommender not initialized"}), 500

    try:
        started_at = datetime.now()
        payload = request.get_json() or {}
        idempotency_key = _read_idempotency_key(payload)
        if idempotency_key:
            cached = store.get_idempotency_record("recommendations_cms", idempotency_key)
            if cached:
                response = jsonify(cached["response"])
                response.headers["X-Idempotent-Replay"] = "true"
                return response, int(cached["status_code"])
        data = payload.get("request") if isinstance(payload.get("request"), dict) else payload
        user_id = str(data.get("user_id", "anonymous")).strip() or "anonymous"
        external_user_id = str(data.get("external_user_id", "")).strip() or None
        effective_user_id = _resolve_effective_user_id(user_id, external_user_id)
        top_n = max(1, min(20, int(data.get("limit", data.get("top_n", 5)))))
        user_reads = data.get("user_reads") or recommender.user_profiles.get(effective_user_id, [])
        if not user_reads:
            user_reads = recommender.user_profiles.get(user_id, [])
        requested_sources = data.get("sources") or []
        config_explicit = bool(str(data.get("config_id", "")).strip())
        config_id = str(data.get("config_id", "balanced")).strip() or "balanced"
        experiment = data.get("experiment")
        scenario_id = str(data.get("scenario_id", "")).strip() or None
        scenario_explicit = bool(scenario_id)
        cdp_context = _resolve_cdp_personalization(
            external_user_id=external_user_id,
            requested_sources=requested_sources,
            scenario_id=scenario_id,
            config_id=config_id,
            scenario_explicit=scenario_explicit,
            config_explicit=config_explicit,
        )
        requested_sources = cdp_context.get("requested_sources") or requested_sources
        if not scenario_explicit and cdp_context.get("selected_scenario_id"):
            scenario_id = cdp_context.get("selected_scenario_id")
        if not config_explicit and cdp_context.get("selected_config_id"):
            config_id = cdp_context.get("selected_config_id")
        scenario = store.get_scenario(scenario_id) if scenario_id else None
        if scenario and scenario.get("rule_set", {}).get("include_sources") and not requested_sources:
            requested_sources = scenario["rule_set"]["include_sources"]
        if scenario and scenario.get("rule_set", {}).get("ranking_config_id"):
            config_id = scenario["rule_set"]["ranking_config_id"]

        experiment_assignment = _resolve_experiment_assignment(experiment, effective_user_id)
        if experiment_assignment:
            if experiment_assignment.get("selected_scenario_id"):
                scenario_id = experiment_assignment["selected_scenario_id"]
                scenario = store.get_scenario(scenario_id) if scenario_id else None
            if experiment_assignment.get("selected_config_id"):
                config_id = experiment_assignment["selected_config_id"]
            if experiment_assignment.get("selected_sources"):
                requested_sources = experiment_assignment["selected_sources"]

        decision_context = _build_decision_context(requested_sources, config_id, None)
        selected_sources = decision_context["selected_sources"]
        effective_ranking_config = decision_context["effective_ranking_config"]
        cdp_source_overrides = cdp_context.get("source_weight_overrides") or {}
        if cdp_source_overrides:
            source_weights = dict(effective_ranking_config.get("source_weights") or {})
            for source, weight in cdp_source_overrides.items():
                if source in selected_sources and weight > 0:
                    source_weights[source] = float(weight)
            effective_ranking_config["source_weights"] = source_weights
        recs = recommender.recommend_for_user(
            effective_user_id,
            recommender.article_vectors,
            user_reads,
            top_n=top_n,
            sources=selected_sources,
            config_id=decision_context["effective_config_id"],
            ranking_config=effective_ranking_config,
        ) if selected_sources else []
        recs, scenario_trace = _apply_scenario_rules(recs, scenario, include_decisions=True)
        recs = recs[:top_n]

        run_id = store.persist_recommendation_run(
            user_id=effective_user_id,
            config_id=decision_context["effective_config_id"],
            config_version=decision_context["config_version"],
            request_payload={
                "user_id": user_id,
                "external_user_id": external_user_id,
                "effective_user_id": effective_user_id,
                "scenario_id": scenario_id,
                "sources": selected_sources,
                "top_n": top_n,
                "api_surface": "cms",
                "scenario_trace": scenario_trace,
                "experiment_assignment": experiment_assignment,
                "cdp_context": cdp_context,
            },
            recommendations=recs,
            request_duration_ms=int((datetime.now() - started_at).total_seconds() * 1000),
        )

        store.record_events(
            [
                {
                    "event_type": "impression",
                    "run_id": run_id,
                    "article_id": rec.get("article_id"),
                    "scenario_id": scenario_id,
                    "user_id": effective_user_id,
                    "external_user_id": external_user_id,
                    "rank_position": idx,
                    "metadata": {"surface": "cms", "placement": data.get("placement")},
                }
                for idx, rec in enumerate(recs, start=1)
            ]
        )

        response_payload = {
            "api_version": "v1",
            "request_id": run_id,
            "user": {
                "user_id": user_id,
                "external_user_id": external_user_id,
                "effective_user_id": effective_user_id,
            },
            "placement": data.get("placement"),
            "scenario_id": scenario_id,
            "config_id": decision_context["effective_config_id"],
            "config_version": decision_context["config_version"],
            "items": [
                {
                    "rank": idx,
                    "article_id": rec.get("article_id"),
                    "title": rec.get("title"),
                    "url": rec.get("url"),
                    "source": rec.get("source"),
                    "score": rec.get("score"),
                    "explanation": rec.get("explanation"),
                    "feature_contributions": rec.get("feature_contributions"),
                }
                for idx, rec in enumerate(recs, start=1)
            ],
            "trace": {
                "selected_sources": selected_sources,
                "source_defaults_applied": decision_context["source_defaults_applied"],
                "scenario_trace": scenario_trace,
                "experiment_assignment": experiment_assignment,
                "cdp_context": cdp_context,
            },
        }
        if idempotency_key:
            store.save_idempotency_record(
                endpoint="recommendations_cms",
                key=idempotency_key,
                status_code=200,
                response_payload=response_payload,
            )
        return jsonify(response_payload)
    except Exception as e:
        logger.error(f"Error in CMS recommendations endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/scenarios/<scenario_id>/simulate", methods=["POST"])
def simulate_scenario(scenario_id):
    if not recommender or not store:
        return jsonify({"error": "Recommender not initialized"}), 500
    scenario = store.get_scenario(scenario_id)
    if not scenario:
        return jsonify({"error": "Scenario not found"}), 404
    try:
        payload = request.get_json() or {}
        user_id = str(payload.get("user_id", "demo_user"))
        top_n = max(1, min(50, int(payload.get("top_n", 10))))
        requested_sources = payload.get("sources") or scenario.get("rule_set", {}).get("include_sources") or []
        config_id = scenario.get("rule_set", {}).get("ranking_config_id") or payload.get("config_id", "balanced")
        user_reads = payload.get("user_reads") or recommender.user_profiles.get(user_id, [])

        context = _build_decision_context(requested_sources, config_id, None)
        base = recommender.recommend_for_user(
            user_id,
            recommender.article_vectors,
            user_reads,
            top_n=top_n,
            sources=context["selected_sources"],
            config_id=context["effective_config_id"],
            ranking_config=context["effective_ranking_config"],
        ) if context["selected_sources"] else []
        reranked, scenario_trace = _apply_scenario_rules(base, scenario, include_decisions=True)
        return jsonify(
            {
                "scenario_id": scenario_id,
                "base_count": len(base),
                "scenario_count": len(reranked),
                "context": context,
                "scenario_trace": scenario_trace,
                "base_top": base[: min(5, len(base))],
                "scenario_top": reranked[: min(5, len(reranked))],
            }
        )
    except Exception as e:
        logger.error(f"Error simulating scenario: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/metrics/offline")
def get_offline_metrics():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    try:
        limit_runs = int(request.args.get("limit_runs", 100))
        metrics = store.compute_offline_metrics(limit_runs=limit_runs)
        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Error computing offline metrics: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/offline/snapshots", methods=["GET", "POST"])
def offline_quality_snapshots():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        if request.method == "GET":
            snapshot_type = str(request.args.get("snapshot_type", "offline_quality")).strip() or None
            limit = max(1, min(200, int(request.args.get("limit", 50))))
            offset = max(0, int(request.args.get("offset", 0)))
            rows = store.list_quality_snapshots(
                snapshot_type=snapshot_type,
                limit=limit + 1,
                offset=offset,
            )
            has_more = len(rows) > limit
            snapshots = rows[:limit]
            return jsonify(
                {
                    "api_version": "v1",
                    "snapshot_type": snapshot_type,
                    "snapshots": snapshots,
                    "count": len(snapshots),
                    "limit": limit,
                    "offset": offset,
                    "has_more": has_more,
                    "next_offset": (offset + limit) if has_more else None,
                }
            )

        payload = request.get_json(silent=True) or {}
        limit_runs = max(10, min(1000, int(payload.get("limit_runs", 100))))
        window_days = max(1, min(365, int(payload.get("window_days", 30))))
        snapshot_type = str(payload.get("snapshot_type", "offline_quality")).strip() or "offline_quality"
        label = str(payload.get("label", "")).strip()
        metrics = store.compute_offline_metrics(limit_runs=limit_runs)
        snapshot = store.create_quality_snapshot(
            snapshot_type=snapshot_type,
            window_days=window_days,
            metrics=metrics,
            metadata={"label": label, "limit_runs": limit_runs, "created_by": _request_actor_id(payload)},
        )
        _record_audit(
            action="create",
            resource_type="quality_snapshot",
            resource_id=snapshot["snapshot_id"],
            payload=payload,
            extra={"snapshot_type": snapshot_type},
        )
        return jsonify({"api_version": "v1", "snapshot": snapshot}), 201
    except Exception as e:
        logger.error(f"Error handling quality snapshots: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/offline/snapshots/compare", methods=["GET"])
def compare_offline_quality_snapshots():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        baseline_id = str(request.args.get("baseline_id", "")).strip()
        candidate_id = str(request.args.get("candidate_id", "")).strip()
        if not baseline_id or not candidate_id:
            return jsonify({"error": "baseline_id and candidate_id are required"}), 400

        baseline = store.get_quality_snapshot(baseline_id)
        candidate = store.get_quality_snapshot(candidate_id)
        if not baseline or not candidate:
            return jsonify({"error": "Snapshot not found"}), 404

        keys = sorted(set((baseline.get("metrics") or {}).keys()) | set((candidate.get("metrics") or {}).keys()))
        deltas = []
        for key in keys:
            base_value = (baseline.get("metrics") or {}).get(key)
            cand_value = (candidate.get("metrics") or {}).get(key)
            if isinstance(base_value, (int, float)) and isinstance(cand_value, (int, float)):
                delta = round(float(cand_value) - float(base_value), 6)
                pct = round((delta / float(base_value)), 6) if float(base_value) != 0 else None
            else:
                delta = None
                pct = None
            deltas.append(
                {
                    "metric": key,
                    "baseline": base_value,
                    "candidate": cand_value,
                    "delta": delta,
                    "delta_pct": pct,
                }
            )

        return jsonify(
            {
                "api_version": "v1",
                "baseline": baseline,
                "candidate": candidate,
                "deltas": deltas,
            }
        )
    except Exception as e:
        logger.error(f"Error comparing quality snapshots: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/similar/<article_id>")
def get_similar_articles(article_id):
    if not recommender:
        return jsonify({"error": "Recommender not initialized"}), 500

    try:
        top_n = int(request.args.get("top_n", 5))
        config_id = request.args.get("config_id", "balanced")
        requested_sources = _parse_sources_param(request.args.get("sources", ""))
        decision_context = _build_decision_context(requested_sources, config_id, None)
        effective_config_id = decision_context["effective_config_id"]
        selected_sources = decision_context["selected_sources"]
        effective_ranking_config = decision_context["effective_ranking_config"]

        if selected_sources:
            similar_articles = recommender.recommend_for_user(
                "demo_user",
                recommender.article_vectors,
                [article_id],
                top_n=top_n,
                sources=selected_sources,
                config_id=effective_config_id,
                ranking_config=effective_ranking_config,
            )
        else:
            similar_articles = []

        for article in similar_articles:
            similar_id = article["article_id"]
            if similar_id in recommender.article_vectors:
                article["content"] = recommender.article_vectors[similar_id]["metadata"].get("content", "")

        return jsonify(similar_articles)
    except Exception as e:
        logger.error(f"Error getting similar articles: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/recommendation-context", methods=["POST"])
def recommendation_context():
    if not recommender or not store:
        return jsonify({"error": "Recommender not initialized"}), 500

    try:
        payload = request.get_json() or {}
        requested_sources = payload.get("sources") or []
        config_explicit = bool(str(payload.get("config_id", "")).strip())
        config_id = str(payload.get("config_id", "balanced")).strip() or "balanced"
        ranking_config = payload.get("ranking_config")
        external_user_id = str(payload.get("external_user_id", "")).strip() or None
        scenario_id = (payload.get("scenario_id") or "").strip() or None
        scenario_explicit = bool(scenario_id)
        cdp_context = _resolve_cdp_personalization(
            external_user_id=external_user_id,
            requested_sources=requested_sources,
            scenario_id=scenario_id,
            config_id=config_id,
            scenario_explicit=scenario_explicit,
            config_explicit=config_explicit,
        )
        requested_sources = cdp_context.get("requested_sources") or requested_sources
        if not scenario_explicit and cdp_context.get("selected_scenario_id"):
            scenario_id = cdp_context.get("selected_scenario_id")
        if not config_explicit and cdp_context.get("selected_config_id"):
            config_id = cdp_context.get("selected_config_id")
        scenario = store.get_scenario(scenario_id) if scenario_id else None
        if scenario and scenario.get("rule_set", {}).get("include_sources") and not requested_sources:
            requested_sources = scenario["rule_set"]["include_sources"]
        if scenario and scenario.get("rule_set", {}).get("ranking_config_id") and not ranking_config:
            config_id = scenario["rule_set"]["ranking_config_id"]
        context = _build_decision_context(requested_sources, config_id, ranking_config)
        cdp_source_overrides = cdp_context.get("source_weight_overrides") or {}
        if cdp_source_overrides:
            source_weights = dict(context["effective_ranking_config"].get("source_weights") or {})
            for source, weight in cdp_source_overrides.items():
                if source in context["selected_sources"] and weight > 0:
                    source_weights[source] = float(weight)
            context["effective_ranking_config"]["source_weights"] = source_weights
        context["scenario_id"] = scenario_id
        context["scenario"] = scenario
        context["cdp_context"] = cdp_context
        if scenario:
            context["scenario_rule_set"] = scenario.get("rule_set", {})
        return jsonify(context)
    except Exception as e:
        logger.error(f"Error building recommendation context: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/events", methods=["GET", "POST"])
@app.route("/api/v1/events", methods=["GET", "POST"])
def recommendation_events():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    if request.method == "GET":
        try:
            limit = max(1, min(1000, int(request.args.get("limit", 100))))
            offset = max(0, int(request.args.get("offset", 0)))
            scenario_id = request.args.get("scenario_id")
            event_type = request.args.get("event_type")
            days = int(request.args.get("days")) if request.args.get("days") else None
            rows = store.list_events(
                limit=limit + 1,
                offset=offset,
                scenario_id=scenario_id,
                event_type=event_type,
                days=days,
            )
            has_more = len(rows) > limit
            events = rows[:limit]
            return jsonify(
                {
                    "api_version": "v1",
                    "events": events,
                    "count": len(events),
                    "limit": limit,
                    "offset": offset,
                    "has_more": has_more,
                    "next_offset": (offset + limit) if has_more else None,
                }
            )
        except Exception as e:
            logger.error(f"Error listing events: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    try:
        payload = request.get_json() or {}
        idempotency_key = _read_idempotency_key(payload)
        if idempotency_key:
            cached = store.get_idempotency_record("events_ingest", idempotency_key)
            if cached:
                response = jsonify(cached["response"])
                response.headers["X-Idempotent-Replay"] = "true"
                return response, int(cached["status_code"])
        raw_events = payload.get("events")
        if raw_events is None:
            raw_events = [payload]

        validated = []
        for event in raw_events:
            event_type = str(event.get("event_type", "")).strip()
            if event_type not in {"impression", "click", "conversion"}:
                raise ValueError("event_type must be one of: impression, click, conversion")
            user_id = str(event.get("user_id", "anonymous")).strip() or "anonymous"
            external_user_id = str(event.get("external_user_id", "")).strip() or None
            effective_user_id = _resolve_effective_user_id(user_id, external_user_id)
            validated.append(
                {
                    "event_type": event_type,
                    "run_id": event.get("run_id"),
                    "article_id": event.get("article_id"),
                    "scenario_id": event.get("scenario_id"),
                    "user_id": effective_user_id,
                    "external_user_id": external_user_id,
                    "rank_position": event.get("rank_position"),
                    "event_value": float(event.get("event_value", 1.0)),
                    "metadata": event.get("metadata") or {},
                }
            )

        inserted = store.record_events(validated)
        response_payload = {"api_version": "v1", "inserted": inserted}
        if idempotency_key:
            store.save_idempotency_record(
                endpoint="events_ingest",
                key=idempotency_key,
                status_code=201,
                response_payload=response_payload,
            )
        return jsonify(response_payload), 201
    except Exception as e:
        logger.error(f"Error recording events: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/metrics/scenarios", methods=["GET"])
def scenario_metrics():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        days = int(request.args.get("days", 30))
        top_articles = int(request.args.get("top_articles", 5))
        metrics = store.compute_scenario_metrics(days=days, top_articles=top_articles)
        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Error computing scenario metrics: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/scenarios/<scenario_id>/sources", methods=["GET"])
def scenario_source_metrics(scenario_id):
    if not recommender or not store:
        return jsonify({"error": "Recommender not initialized"}), 500
    try:
        days = int(request.args.get("days", 30))
        limit = int(request.args.get("limit", 2000))
        events = store.list_events(limit=limit, scenario_id=scenario_id, days=days)
        by_source: Dict[str, Dict] = {}
        for event in events:
            source = _resolve_event_source(event)
            bucket = by_source.setdefault(source, {"source": source, "impressions": 0, "clicks": 0, "conversions": 0})
            if event["event_type"] == "impression":
                bucket["impressions"] += 1
            elif event["event_type"] == "click":
                bucket["clicks"] += 1
            elif event["event_type"] == "conversion":
                bucket["conversions"] += 1
        items = []
        for row in by_source.values():
            impressions = row["impressions"]
            clicks = row["clicks"]
            row["ctr"] = round((clicks / impressions), 4) if impressions else 0.0
            row["conversion_rate"] = round((row["conversions"] / clicks), 4) if clicks else 0.0
            items.append(row)
        items.sort(key=lambda x: (x["impressions"], x["clicks"]), reverse=True)
        return jsonify({"scenario_id": scenario_id, "window_days": days, "sources": items})
    except Exception as e:
        logger.error(f"Error computing scenario source metrics: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/trends", methods=["GET"])
def metrics_trends():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        days = max(1, min(365, int(request.args.get("days", 30))))
        limit = max(1, min(100000, int(request.args.get("limit", 50000))))
        use_rollups = request.args.get("use_rollups", "true").lower() != "false"
        scenario_ids_raw = request.args.get("scenario_ids", "").strip()
        source_filter = request.args.get("source", "").strip().lower()
        scenario_filter = {part.strip() for part in scenario_ids_raw.split(",") if part.strip()}

        scenario_catalog = {entry["scenario_id"]: entry for entry in store.list_scenarios(include_disabled=True)}
        now = datetime.now()
        date_labels = [
            (now - timedelta(days=offset)).strftime("%Y-%m-%d")
            for offset in range(days - 1, -1, -1)
        ]
        daily: Dict[str, Dict] = {
            label: {"impressions": 0, "clicks": 0, "conversions": 0, "scenarios": {}}
            for label in date_labels
        }

        rollups_used = False
        if use_rollups:
            rollup_rows = store.list_event_rollups(
                days=days,
                scenario_ids=sorted(scenario_filter) if scenario_filter else None,
                source=source_filter or None,
            )
            if rollup_rows:
                rollups_used = True
                for row in rollup_rows:
                    day = row.get("day")
                    if day not in daily:
                        continue
                    scenario_id = row.get("scenario_id") or "default"
                    impressions = int(row.get("impressions") or 0)
                    clicks = int(row.get("clicks") or 0)
                    conversions = int(row.get("conversions") or 0)
                    daily[day]["impressions"] += impressions
                    daily[day]["clicks"] += clicks
                    daily[day]["conversions"] += conversions
                    scenario_bucket = daily[day]["scenarios"].setdefault(
                        scenario_id,
                        {"impressions": 0, "clicks": 0, "conversions": 0},
                    )
                    scenario_bucket["impressions"] += impressions
                    scenario_bucket["clicks"] += clicks
                    scenario_bucket["conversions"] += conversions

        if not rollups_used:
            events = store.list_events(limit=limit, days=days)
            for event in events:
                created_at = str(event.get("created_at") or "")
                try:
                    day = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
                except ValueError:
                    continue
                if day not in daily:
                    continue

                scenario_id = event.get("scenario_id") or "default"
                if scenario_filter and scenario_id not in scenario_filter:
                    continue

                if source_filter:
                    source = _resolve_event_source(event)
                    if source.lower() != source_filter:
                        continue

                event_type = event.get("event_type")
                if event_type not in {"impression", "click", "conversion"}:
                    continue
                daily[day][f"{event_type}s"] += 1
                scenario_bucket = daily[day]["scenarios"].setdefault(
                    scenario_id,
                    {"impressions": 0, "clicks": 0, "conversions": 0},
                )
                scenario_bucket[f"{event_type}s"] += 1

        totals = {"impressions": 0, "clicks": 0, "conversions": 0}
        by_scenario: Dict[str, Dict] = {}
        for label in date_labels:
            day_row = daily[label]
            totals["impressions"] += day_row["impressions"]
            totals["clicks"] += day_row["clicks"]
            totals["conversions"] += day_row["conversions"]
            for scenario_id, bucket in day_row["scenarios"].items():
                scenario_state = by_scenario.setdefault(
                    scenario_id,
                    {
                        "scenario_id": scenario_id,
                        "name": scenario_catalog.get(scenario_id, {}).get("name", "Default"),
                        "impressions": 0,
                        "clicks": 0,
                        "conversions": 0,
                        "points": [],
                    },
                )
                scenario_state["impressions"] += bucket["impressions"]
                scenario_state["clicks"] += bucket["clicks"]
                scenario_state["conversions"] += bucket["conversions"]

        for scenario_state in by_scenario.values():
            scenario_id = scenario_state["scenario_id"]
            points: List[Dict] = []
            for label in date_labels:
                bucket = daily[label]["scenarios"].get(
                    scenario_id,
                    {"impressions": 0, "clicks": 0, "conversions": 0},
                )
                impressions = bucket["impressions"]
                clicks = bucket["clicks"]
                points.append(
                    {
                        "date": label,
                        "impressions": impressions,
                        "clicks": clicks,
                        "conversions": bucket["conversions"],
                        "ctr": round((clicks / impressions), 4) if impressions else 0.0,
                    }
                )
            scenario_state["points"] = points
            scenario_state["ctr"] = round(
                (scenario_state["clicks"] / scenario_state["impressions"]),
                4,
            ) if scenario_state["impressions"] else 0.0

        totals_by_day = []
        for label in date_labels:
            row = daily[label]
            impressions = row["impressions"]
            clicks = row["clicks"]
            totals_by_day.append(
                {
                    "date": label,
                    "impressions": impressions,
                    "clicks": clicks,
                    "conversions": row["conversions"],
                    "ctr": round((clicks / impressions), 4) if impressions else 0.0,
                }
            )

        totals["ctr"] = round((totals["clicks"] / totals["impressions"]), 4) if totals["impressions"] else 0.0
        scenario_items = sorted(by_scenario.values(), key=lambda item: item["impressions"], reverse=True)
        return jsonify(
            {
                "window_days": days,
                "filters": {
                    "scenario_ids": sorted(scenario_filter),
                    "source": source_filter or None,
                },
                "summary": totals,
                "dates": date_labels,
                "totals_by_day": totals_by_day,
                "scenarios": scenario_items,
                "rollups_used": rollups_used,
            }
        )
    except Exception as e:
        logger.error(f"Error computing metric trends: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/attribution", methods=["GET"])
def metrics_attribution():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        days = max(1, min(365, int(request.args.get("days", 30))))
        limit = max(1, min(100000, int(request.args.get("limit", 50000))))
        top_runs = max(1, min(500, int(request.args.get("top_runs", 50))))
        scenario_ids_raw = request.args.get("scenario_ids", "").strip()
        source_filter = request.args.get("source", "").strip().lower()
        scenario_filter = {part.strip() for part in scenario_ids_raw.split(",") if part.strip()}
        scenario_catalog = {entry["scenario_id"]: entry for entry in store.list_scenarios(include_disabled=True)}

        events = store.list_events(limit=limit, days=days)
        run_stats: Dict[str, Dict] = {}
        source_stats: Dict[str, Dict] = {}
        scenario_stats: Dict[str, Dict] = {}
        totals = {"impressions": 0, "clicks": 0, "conversions": 0}
        user_ids = set()
        external_user_ids = set()
        article_source_cache: Dict[str, str] = {}

        for event in events:
            scenario_id = event.get("scenario_id") or "default"
            if scenario_filter and scenario_id not in scenario_filter:
                continue

            article_id = event.get("article_id")
            source = "unknown"
            if article_id:
                source = article_source_cache.get(article_id, "")
                if not source:
                    source = _resolve_event_source(event)
                    article_source_cache[article_id] = source
            else:
                source = _resolve_event_source(event)
            if source_filter and source.lower() != source_filter:
                continue

            event_type = event.get("event_type")
            if event_type not in {"impression", "click", "conversion"}:
                continue
            metric_key = f"{event_type}s"

            totals[metric_key] += 1
            user_value = str(event.get("user_id") or "").strip()
            if user_value:
                user_ids.add(user_value)
            external_user_value = str(event.get("external_user_id") or "").strip()
            if external_user_value:
                external_user_ids.add(external_user_value)

            source_bucket = source_stats.setdefault(
                source,
                {"source": source, "impressions": 0, "clicks": 0, "conversions": 0},
            )
            source_bucket[metric_key] += 1

            scenario_bucket = scenario_stats.setdefault(
                scenario_id,
                {
                    "scenario_id": scenario_id,
                    "name": scenario_catalog.get(scenario_id, {}).get("name", "Default"),
                    "impressions": 0,
                    "clicks": 0,
                    "conversions": 0,
                },
            )
            scenario_bucket[metric_key] += 1

            run_id = event.get("run_id") or "untracked"
            run_bucket = run_stats.setdefault(
                run_id,
                {
                    "run_id": run_id,
                    "scenario_id": scenario_id,
                    "impressions": 0,
                    "clicks": 0,
                    "conversions": 0,
                    "sources": set(),
                },
            )
            run_bucket[metric_key] += 1
            run_bucket["sources"].add(source)

        for bucket in source_stats.values():
            impressions = bucket["impressions"]
            clicks = bucket["clicks"]
            bucket["ctr"] = round((clicks / impressions), 4) if impressions else 0.0
            bucket["conversion_rate"] = round((bucket["conversions"] / clicks), 4) if clicks else 0.0

        for bucket in scenario_stats.values():
            impressions = bucket["impressions"]
            clicks = bucket["clicks"]
            bucket["ctr"] = round((clicks / impressions), 4) if impressions else 0.0
            bucket["conversion_rate"] = round((bucket["conversions"] / clicks), 4) if clicks else 0.0

        ranked_runs = sorted(
            run_stats.items(),
            key=lambda pair: (pair[1]["impressions"], pair[1]["clicks"], pair[1]["conversions"]),
            reverse=True,
        )[:top_runs]
        run_rows: List[Dict] = []
        for run_id, bucket in ranked_runs:
            run_meta = store.get_run(run_id) if run_id != "untracked" else None
            request_payload = run_meta.get("request", {}) if run_meta else {}
            selected_sources = request_payload.get("sources")
            if not selected_sources and request_payload.get("trace"):
                selected_sources = request_payload["trace"].get("selected_sources")
            impressions = bucket["impressions"]
            clicks = bucket["clicks"]
            run_rows.append(
                {
                    "run_id": run_id,
                    "created_at": run_meta.get("created_at") if run_meta else None,
                    "config_id": run_meta.get("config_id") if run_meta else None,
                    "config_version": run_meta.get("config_version") if run_meta else None,
                    "scenario_id": bucket["scenario_id"],
                    "scenario_name": scenario_catalog.get(bucket["scenario_id"], {}).get("name", "Default"),
                    "selected_sources": selected_sources or sorted(bucket["sources"]),
                    "event_sources": sorted(bucket["sources"]),
                    "impressions": impressions,
                    "clicks": clicks,
                    "conversions": bucket["conversions"],
                    "ctr": round((clicks / impressions), 4) if impressions else 0.0,
                    "conversion_rate": round((bucket["conversions"] / clicks), 4) if clicks else 0.0,
                }
            )

        source_rows = sorted(source_stats.values(), key=lambda item: (item["impressions"], item["clicks"]), reverse=True)
        scenario_rows = sorted(scenario_stats.values(), key=lambda item: (item["impressions"], item["clicks"]), reverse=True)
        summary = dict(totals)
        summary["ctr"] = round((totals["clicks"] / totals["impressions"]), 4) if totals["impressions"] else 0.0
        summary["conversion_rate"] = round((totals["conversions"] / totals["clicks"]), 4) if totals["clicks"] else 0.0
        summary["unique_users"] = len(user_ids)
        summary["unique_external_users"] = len(external_user_ids)
        return jsonify(
            {
                "window_days": days,
                "filters": {
                    "scenario_ids": sorted(scenario_filter),
                    "source": source_filter or None,
                },
                "summary": summary,
                "by_run": run_rows,
                "by_source": source_rows,
                "by_scenario": scenario_rows,
            }
        )
    except Exception as e:
        logger.error(f"Error computing attribution metrics: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/identity", methods=["GET"])
def metrics_identity():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        days = max(1, min(365, int(request.args.get("days", 30))))
        limit_events = max(1, min(200000, int(request.args.get("limit_events", 50000))))
        limit_runs = max(1, min(10000, int(request.args.get("limit_runs", 1000))))
        top_external = max(1, min(200, int(request.args.get("top_external", 25))))

        events = store.list_events(limit=limit_events, days=days)
        totals = {"events": 0, "impressions": 0, "clicks": 0, "conversions": 0}
        users = set()
        external_users = set()
        by_external: Dict[str, Dict] = {}
        by_scenario: Dict[str, Dict] = {}

        for event in events:
            event_type = event.get("event_type")
            if event_type not in {"impression", "click", "conversion"}:
                continue
            totals["events"] += 1
            totals[f"{event_type}s"] += 1

            user_id = str(event.get("user_id") or "").strip()
            external_user_id = str(event.get("external_user_id") or "").strip()
            scenario_id = event.get("scenario_id") or "default"
            if user_id:
                users.add(user_id)
            if external_user_id:
                external_users.add(external_user_id)
                ext_bucket = by_external.setdefault(
                    external_user_id,
                    {
                        "external_user_id": external_user_id,
                        "events": 0,
                        "impressions": 0,
                        "clicks": 0,
                        "conversions": 0,
                        "scenarios": set(),
                    },
                )
                ext_bucket["events"] += 1
                ext_bucket[f"{event_type}s"] += 1
                ext_bucket["scenarios"].add(scenario_id)

            scenario_bucket = by_scenario.setdefault(
                scenario_id,
                {"scenario_id": scenario_id, "events": 0, "external_events": 0},
            )
            scenario_bucket["events"] += 1
            if external_user_id:
                scenario_bucket["external_events"] += 1

        run_rows = store.list_runs_with_request(limit=limit_runs, offset=0, days=days)
        runs_total = 0
        runs_with_external = 0
        run_external_ids = set()
        for row in run_rows:
            runs_total += 1
            request_payload = row.get("request", {})
            external_user_id = str(request_payload.get("external_user_id") or "").strip()
            if external_user_id:
                runs_with_external += 1
                run_external_ids.add(external_user_id)

        external_rows = []
        for item in by_external.values():
            impressions = item["impressions"]
            clicks = item["clicks"]
            external_rows.append(
                {
                    "external_user_id": item["external_user_id"],
                    "events": item["events"],
                    "impressions": impressions,
                    "clicks": clicks,
                    "conversions": item["conversions"],
                    "ctr": round((clicks / impressions), 4) if impressions else 0.0,
                    "scenario_count": len(item["scenarios"]),
                }
            )
        external_rows.sort(key=lambda item: (item["events"], item["clicks"]), reverse=True)

        scenario_rows = []
        for item in by_scenario.values():
            events_total = item["events"]
            scenario_rows.append(
                {
                    "scenario_id": item["scenario_id"],
                    "events": events_total,
                    "external_events": item["external_events"],
                    "external_share": round((item["external_events"] / events_total), 4) if events_total else 0.0,
                }
            )
        scenario_rows.sort(key=lambda item: item["events"], reverse=True)

        return jsonify(
            {
                "window_days": days,
                "summary": {
                    **totals,
                    "unique_users": len(users),
                    "unique_external_users": len(external_users),
                    "external_event_share": round((sum(item["external_events"] for item in by_scenario.values()) / totals["events"]), 4) if totals["events"] else 0.0,
                    "runs_total": runs_total,
                    "runs_with_external": runs_with_external,
                    "run_external_share": round((runs_with_external / runs_total), 4) if runs_total else 0.0,
                    "unique_external_users_in_runs": len(run_external_ids),
                },
                "top_external_users": external_rows[:top_external],
                "by_scenario": scenario_rows,
            }
        )
    except Exception as e:
        logger.error(f"Error computing identity metrics: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/identity/diagnostics", methods=["GET"])
def metrics_identity_diagnostics():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        days = max(1, min(365, int(request.args.get("days", 30))))
        limit_events = max(1, min(200000, int(request.args.get("limit_events", 50000))))
        limit_runs = max(1, min(20000, int(request.args.get("limit_runs", 5000))))

        runs = store.list_runs_with_request(limit=limit_runs, offset=0, days=days)
        run_external: Dict[str, str] = {}
        run_ids = set()
        run_external_ids = set()
        for run in runs:
            run_id = run.get("run_id")
            if not run_id:
                continue
            run_ids.add(run_id)
            external = str((run.get("request", {}) or {}).get("external_user_id") or "").strip()
            if external:
                run_external[run_id] = external
                run_external_ids.add(external)

        events = store.list_events(limit=limit_events, days=days)
        orphan_external_events = 0
        unknown_run_external_events = 0
        run_external_mismatch = 0
        event_external_ids = set()
        mismatch_samples = []

        for event in events:
            external = str(event.get("external_user_id") or "").strip()
            if not external:
                continue
            event_external_ids.add(external)
            run_id = str(event.get("run_id") or "").strip()
            if not run_id:
                orphan_external_events += 1
                continue
            if run_id not in run_ids:
                unknown_run_external_events += 1
                continue
            run_external_id = run_external.get(run_id, "")
            if run_external_id and run_external_id != external:
                run_external_mismatch += 1
                if len(mismatch_samples) < 10:
                    mismatch_samples.append(
                        {
                            "run_id": run_id,
                            "event_external_user_id": external,
                            "run_external_user_id": run_external_id,
                        }
                    )

        return jsonify(
            {
                "window_days": days,
                "summary": {
                    "runs_analyzed": len(run_ids),
                    "events_analyzed": len(events),
                    "orphan_external_events": orphan_external_events,
                    "unknown_run_external_events": unknown_run_external_events,
                    "run_external_mismatch_events": run_external_mismatch,
                    "external_ids_only_in_events": len(event_external_ids - run_external_ids),
                    "external_ids_only_in_runs": len(run_external_ids - event_external_ids),
                },
                "mismatch_samples": mismatch_samples,
            }
        )
    except Exception as e:
        logger.error(f"Error computing identity diagnostics: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


def _compute_experiment_metrics(days: int, experiment_id: str, limit_runs: int, limit_events: int) -> Dict:
    if not store:
        return {
            "window_days": days,
            "experiment_id": experiment_id or None,
            "experiments_seen": [],
            "variants": [],
            "runs_with_assignment": 0,
        }

    runs = store.list_runs_with_request(limit=limit_runs, offset=0, days=days)
    run_assignments: Dict[str, Dict] = {}
    by_variant: Dict[str, Dict] = {}
    experiment_ids = set()
    for run in runs:
        assignment = (run.get("request", {}) or {}).get("experiment_assignment") or {}
        exp_id = str(assignment.get("experiment_id") or "").strip()
        variant_id = str(assignment.get("variant_id") or "").strip()
        if not exp_id or not variant_id:
            continue
        if experiment_id and exp_id != experiment_id:
            continue
        run_id = run.get("run_id")
        if not run_id:
            continue
        experiment_ids.add(exp_id)
        run_assignments[run_id] = {"experiment_id": exp_id, "variant_id": variant_id}
        bucket = by_variant.setdefault(
            variant_id,
            {
                "variant_id": variant_id,
                "runs": 0,
                "impressions": 0,
                "clicks": 0,
                "conversions": 0,
            },
        )
        bucket["runs"] += 1

    events = store.list_events(limit=limit_events, days=days)
    for event in events:
        run_id = event.get("run_id")
        assignment = run_assignments.get(run_id)
        if not assignment:
            continue
        event_type = event.get("event_type")
        if event_type not in {"impression", "click", "conversion"}:
            continue
        bucket = by_variant[assignment["variant_id"]]
        bucket[f"{event_type}s"] += 1

    variants = []
    for bucket in by_variant.values():
        impressions = bucket["impressions"]
        clicks = bucket["clicks"]
        variants.append(
            {
                **bucket,
                "ctr": round((clicks / impressions), 4) if impressions else 0.0,
                "conversion_rate": round((bucket["conversions"] / clicks), 4) if clicks else 0.0,
            }
        )
    variants.sort(key=lambda item: item["runs"], reverse=True)

    return {
        "window_days": days,
        "experiment_id": experiment_id or (next(iter(experiment_ids)) if len(experiment_ids) == 1 else None),
        "experiments_seen": sorted(experiment_ids),
        "variants": variants,
        "runs_with_assignment": len(run_assignments),
    }


@app.route("/api/metrics/experiments", methods=["GET"])
def metrics_experiments():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        days = max(1, min(365, int(request.args.get("days", 30))))
        experiment_id = str(request.args.get("experiment_id", "")).strip()
        limit_runs = max(1, min(20000, int(request.args.get("limit_runs", 5000))))
        limit_events = max(1, min(200000, int(request.args.get("limit_events", 100000))))
        return jsonify(
            _compute_experiment_metrics(
                days=days,
                experiment_id=experiment_id,
                limit_runs=limit_runs,
                limit_events=limit_events,
            )
        )
    except Exception as e:
        logger.error(f"Error computing experiment metrics: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/experiments/compare", methods=["GET"])
def metrics_experiments_compare():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        days = max(1, min(365, int(request.args.get("days", 30))))
        experiment_id = str(request.args.get("experiment_id", "")).strip()
        baseline_variant = str(request.args.get("baseline_variant", "")).strip()
        candidate_variant = str(request.args.get("candidate_variant", "")).strip()
        limit_runs = max(1, min(20000, int(request.args.get("limit_runs", 5000))))
        limit_events = max(1, min(200000, int(request.args.get("limit_events", 100000))))
        if not baseline_variant or not candidate_variant:
            return jsonify({"error": "baseline_variant and candidate_variant are required"}), 400

        metrics = _compute_experiment_metrics(
            days=days,
            experiment_id=experiment_id,
            limit_runs=limit_runs,
            limit_events=limit_events,
        )
        variants = {item["variant_id"]: item for item in metrics.get("variants", [])}
        baseline = variants.get(baseline_variant)
        candidate = variants.get(candidate_variant)
        if not baseline or not candidate:
            return jsonify({"error": "Requested variants were not found in selected window"}), 404

        compare_rows = []
        for key in ("runs", "impressions", "clicks", "conversions", "ctr", "conversion_rate"):
            b_val = baseline.get(key)
            c_val = candidate.get(key)
            delta = None
            delta_pct = None
            if isinstance(b_val, (int, float)) and isinstance(c_val, (int, float)):
                delta = round(float(c_val) - float(b_val), 6)
                delta_pct = round((delta / float(b_val)), 6) if float(b_val) != 0 else None
            compare_rows.append(
                {
                    "metric": key,
                    "baseline": b_val,
                    "candidate": c_val,
                    "delta": delta,
                    "delta_pct": delta_pct,
                }
            )

        return jsonify(
            {
                "api_version": "v1",
                "window_days": days,
                "experiment_id": metrics.get("experiment_id"),
                "baseline_variant": baseline_variant,
                "candidate_variant": candidate_variant,
                "comparison": compare_rows,
                "baseline": baseline,
                "candidate": candidate,
            }
        )
    except Exception as e:
        logger.error(f"Error comparing experiment variants: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/scenario-traces", methods=["GET"])
def metrics_scenario_traces():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        days = max(1, min(365, int(request.args.get("days", 30))))
        limit_runs = max(1, min(10000, int(request.args.get("limit_runs", 1000))))
        top_rules = max(1, min(200, int(request.args.get("top_rules", 25))))
        scenario_ids_raw = request.args.get("scenario_ids", "").strip()
        scenario_filter = {part.strip() for part in scenario_ids_raw.split(",") if part.strip()}
        scenario_catalog = {entry["scenario_id"]: entry for entry in store.list_scenarios(include_disabled=True)}

        rows = store.list_runs_with_request(limit=limit_runs, offset=0, days=days)
        summary = {"runs_total": 0, "runs_with_scenario": 0, "runs_with_trace": 0}
        by_scenario: Dict[str, Dict] = {}
        global_rules: Dict[str, int] = {}

        for row in rows:
            summary["runs_total"] += 1
            request_payload = row.get("request", {})
            scenario_id = request_payload.get("scenario_id") or "default"
            if scenario_filter and scenario_id not in scenario_filter:
                continue
            if scenario_id != "default":
                summary["runs_with_scenario"] += 1

            trace = request_payload.get("scenario_trace") or {}
            if not trace:
                continue
            summary["runs_with_trace"] += 1

            bucket = by_scenario.setdefault(
                scenario_id,
                {
                    "scenario_id": scenario_id,
                    "name": scenario_catalog.get(scenario_id, {}).get("name", "Default"),
                    "runs": 0,
                    "filtered_out": 0,
                    "remaining": 0,
                    "boosts_applied": 0,
                    "rules": {},
                },
            )
            bucket["runs"] += 1
            bucket["filtered_out"] += int(trace.get("filtered_out") or 0)
            bucket["remaining"] += int(trace.get("remaining") or 0)
            bucket["boosts_applied"] += int(trace.get("boosts_applied") or 0)

            reasons = trace.get("reasons") or {}
            for rule, count in reasons.items():
                count_value = int(count or 0)
                if count_value <= 0:
                    continue
                bucket["rules"][rule] = bucket["rules"].get(rule, 0) + count_value
                global_rules[rule] = global_rules.get(rule, 0) + count_value

        scenario_rows = []
        for bucket in by_scenario.values():
            base = bucket["filtered_out"] + bucket["remaining"]
            scenario_rows.append(
                {
                    "scenario_id": bucket["scenario_id"],
                    "name": bucket["name"],
                    "runs": bucket["runs"],
                    "filtered_out": bucket["filtered_out"],
                    "remaining": bucket["remaining"],
                    "boosts_applied": bucket["boosts_applied"],
                    "drop_rate": round((bucket["filtered_out"] / base), 4) if base else 0.0,
                    "top_rules": [
                        {"rule": rule, "count": count}
                        for rule, count in sorted(bucket["rules"].items(), key=lambda item: item[1], reverse=True)[:5]
                    ],
                }
            )
        scenario_rows.sort(key=lambda item: (item["runs"], item["filtered_out"]), reverse=True)

        return jsonify(
            {
                "window_days": days,
                "filters": {"scenario_ids": sorted(scenario_filter)},
                "summary": summary,
                "global_top_rules": [
                    {"rule": rule, "count": count}
                    for rule, count in sorted(global_rules.items(), key=lambda item: item[1], reverse=True)[:top_rules]
                ],
                "scenarios": scenario_rows,
            }
        )
    except Exception as e:
        logger.error(f"Error computing scenario trace metrics: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/rollups/daily", methods=["GET"])
def metrics_rollups_daily():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        days = max(1, min(365, int(request.args.get("days", 30))))
        scenario_ids_raw = request.args.get("scenario_ids", "").strip()
        source = request.args.get("source", "").strip() or None
        scenario_ids = [part.strip() for part in scenario_ids_raw.split(",") if part.strip()]
        rows = store.list_event_rollups(days=days, scenario_ids=scenario_ids or None, source=source)
        return jsonify(
            {
                "window_days": days,
                "filters": {
                    "scenario_ids": scenario_ids,
                    "source": source,
                },
                "rows": rows,
                "count": len(rows),
            }
        )
    except Exception as e:
        logger.error(f"Error reading event rollups: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/rollups/rebuild", methods=["POST"])
def metrics_rollups_rebuild():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        payload = request.get_json(silent=True) or {}
        days = max(1, min(365, int(payload.get("days", 30))))
        result = store.rebuild_event_rollups(days=days)
        _record_audit(
            action="rebuild",
            resource_type="event_rollups",
            resource_id=f"daily:{days}",
            payload=payload,
            extra=result,
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error rebuilding event rollups: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/observability/overview", methods=["GET"])
@app.route("/api/v1/observability/overview", methods=["GET"])
def observability_overview():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        days = int(request.args.get("days", 7))
        return jsonify(_compute_observability_snapshot(days))
    except Exception as e:
        logger.error(f"Error building observability overview: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/observability/sli", methods=["GET"])
@app.route("/api/v1/observability/sli", methods=["GET"])
def observability_sli():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        days = int(request.args.get("days", 7))
        snapshot = _compute_observability_snapshot(days)
        thresholds = snapshot.get("slo_targets", {})
        checks = _build_sli_checks(snapshot)
        persist = request.args.get("persist_incidents", "false").lower() == "true"
        incident_sync = None
        if persist:
            incident_sync = _sync_alert_incidents_from_checks(checks, actor_id=_request_actor_id())
        overall_status = "pass" if all(check["status"] == "pass" for check in checks) else "warn"
        return jsonify(
            {
                "api_version": "v1",
                "generated_at": snapshot.get("generated_at"),
                "window_days": snapshot.get("window_days"),
                "overall_status": overall_status,
                "checks": checks,
                "thresholds": thresholds,
                "incident_sync": incident_sync,
            }
        )
    except Exception as e:
        logger.error(f"Error building observability SLI: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/alerts/incidents", methods=["GET"])
@app.route("/api/v1/alerts/incidents", methods=["GET"])
def alert_incidents():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        limit = max(1, min(500, int(request.args.get("limit", 100))))
        offset = max(0, int(request.args.get("offset", 0)))
        status = request.args.get("status")
        metric = request.args.get("metric")
        rows = store.list_alert_incidents(limit=limit + 1, offset=offset, status=status, metric=metric)
        has_more = len(rows) > limit
        incidents = rows[:limit]
        return jsonify(
            {
                "api_version": "v1",
                "incidents": incidents,
                "count": len(incidents),
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": (offset + limit) if has_more else None,
            }
        )
    except Exception as e:
        logger.error(f"Error listing alert incidents: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/alerts/incidents/evaluate", methods=["POST"])
@app.route("/api/v1/alerts/incidents/evaluate", methods=["POST"])
def evaluate_alert_incidents():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        payload = request.get_json() or {}
        days = int(payload.get("days", 7))
        snapshot = _compute_observability_snapshot(days)
        checks = _build_sli_checks(snapshot)
        result = _sync_alert_incidents_from_checks(checks, actor_id=_request_actor_id(payload))
        _record_audit(
            action="evaluate",
            resource_type="alert_incidents",
            resource_id="global",
            payload=payload,
            extra=result,
        )
        return jsonify({"api_version": "v1", "window_days": days, "checks": checks, "incident_sync": result})
    except Exception as e:
        logger.error(f"Error evaluating alert incidents: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/alerts/incidents/<incident_id>/resolve", methods=["PUT"])
@app.route("/api/v1/alerts/incidents/<incident_id>/resolve", methods=["PUT"])
def resolve_alert_incident(incident_id):
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        payload = request.get_json() or {}
        actor_id = _request_actor_id(payload)
        note = str(payload.get("note", "")).strip()
        resolved = store.resolve_alert_incident(incident_id=incident_id, resolved_by=actor_id, note=note)
        if not resolved:
            return jsonify({"error": "Incident not found or already resolved"}), 404
        _record_audit(
            action="resolve",
            resource_type="alert_incident",
            resource_id=incident_id,
            payload=payload,
            extra={"resolved_by": actor_id},
        )
        return jsonify({"api_version": "v1", "resolved": True, "incident_id": incident_id})
    except Exception as e:
        logger.error(f"Error resolving alert incident: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/alerts/thresholds", methods=["GET", "PUT"])
@app.route("/api/v1/alerts/thresholds", methods=["GET", "PUT"])
def alerts_thresholds():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    if request.method == "GET":
        try:
            thresholds = store.get_alert_thresholds()
            return jsonify({"api_version": "v1", "thresholds": thresholds})
        except Exception as e:
            logger.error(f"Error reading alert thresholds: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    try:
        payload = request.get_json() or {}
        threshold_values = payload.get("thresholds", payload)
        current = store.get_alert_thresholds()
        validated = dict(current)
        if "recommendation_p95_ms" in threshold_values:
            validated["recommendation_p95_ms"] = float(threshold_values.get("recommendation_p95_ms"))
        if "connector_failure_rate" in threshold_values:
            validated["connector_failure_rate"] = float(threshold_values.get("connector_failure_rate"))
        if "min_ctr" in threshold_values:
            validated["min_ctr"] = float(threshold_values.get("min_ctr"))
        if "max_rollup_lag_hours" in threshold_values:
            validated["max_rollup_lag_hours"] = float(threshold_values.get("max_rollup_lag_hours"))
        if "connector_blocker_rate" in threshold_values:
            validated["connector_blocker_rate"] = float(threshold_values.get("connector_blocker_rate"))

        if float(validated["recommendation_p95_ms"]) <= 0:
            return jsonify({"error": "recommendation_p95_ms must be > 0"}), 400
        if not (0 <= float(validated["connector_failure_rate"]) <= 1):
            return jsonify({"error": "connector_failure_rate must be in [0, 1]"}), 400
        if not (0 <= float(validated["min_ctr"]) <= 1):
            return jsonify({"error": "min_ctr must be in [0, 1]"}), 400
        if float(validated.get("max_rollup_lag_hours", 24.0)) <= 0:
            return jsonify({"error": "max_rollup_lag_hours must be > 0"}), 400
        if not (0 <= float(validated.get("connector_blocker_rate", 0.2)) <= 1):
            return jsonify({"error": "connector_blocker_rate must be in [0, 1]"}), 400

        stored = store.upsert_alert_thresholds(validated)
        _record_audit(
            action="update",
            resource_type="alert_thresholds",
            resource_id="global",
            payload=payload,
            extra={"thresholds": stored},
        )
        return jsonify({"api_version": "v1", "thresholds": stored})
    except Exception as e:
        logger.error(f"Error updating alert thresholds: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/audit-logs", methods=["GET"])
@app.route("/api/v1/audit-logs", methods=["GET"])
def audit_logs():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        limit = max(1, min(500, int(request.args.get("limit", 100))))
        offset = max(0, int(request.args.get("offset", 0)))
        actor_id = request.args.get("actor_id")
        resource_type = request.args.get("resource_type")
        rows = store.list_audit_events(
            limit=limit + 1,
            offset=offset,
            actor_id=actor_id,
            resource_type=resource_type,
        )
        has_more = len(rows) > limit
        events = rows[:limit]
        return jsonify(
            {
                "api_version": "v1",
                "events": events,
                "count": len(events),
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": (offset + limit) if has_more else None,
            }
        )
    except Exception as e:
        logger.error(f"Error listing audit logs: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/maintenance/cleanup/status", methods=["GET"])
@app.route("/api/v1/maintenance/cleanup/status", methods=["GET"])
def cleanup_status():
    with _cleanup_state_lock:
        snapshot = dict(_cleanup_state)
    snapshot["api_version"] = "v1"
    return jsonify(snapshot)


@app.route("/api/maintenance/cleanup/run-now", methods=["POST"])
@app.route("/api/v1/maintenance/cleanup/run-now", methods=["POST"])
def cleanup_run_now():
    if not store:
        return jsonify({"error": "Store unavailable"}), 500
    try:
        result = _run_cleanup_cycle()
        with _cleanup_state_lock:
            _cleanup_state["runs_total"] += 1
            _cleanup_state["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _cleanup_state["last_result"] = result
            _cleanup_state["last_error"] = None
        _record_audit(
            action="run",
            resource_type="maintenance_cleanup",
            resource_id="manual",
            extra=result,
        )
        return jsonify({"api_version": "v1", "cleanup": result})
    except Exception as e:
        with _cleanup_state_lock:
            _cleanup_state["errors_total"] += 1
            _cleanup_state["last_error"] = str(e)
        logger.error(f"Error running cleanup: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/engine/config", methods=["GET"])
@app.route("/api/v1/engine/config", methods=["GET"])
def engine_config():
    if not recommender or not store:
        return jsonify({"error": "Recommender not initialized"}), 500
    try:
        sources, settings = _load_sources_with_settings()
        scenarios = store.list_scenarios(include_disabled=True)
        configs = store.list_latest_configs()
        cdp = store.get_cdp_integration(_MEIRO_PROVIDER)
        cdp_safe_config = dict(cdp.get("config") or {})
        if cdp_safe_config.get("api_key"):
            cdp_safe_config["api_key"] = "***"
        return jsonify(
            {
                "api_version": "v1",
                "ranking_configs": configs,
                "sources": _merge_source_settings(sources, settings),
                "scenarios": scenarios,
                "cdp": {
                    "provider": _MEIRO_PROVIDER,
                    "enabled": bool(cdp.get("enabled")),
                    "config": cdp_safe_config,
                    "mapping": _normalize_meiro_mapping(cdp.get("mapping")),
                },
                "cdp_scheduler": dict(_cdp_state),
                "scheduler": dict(_scheduler_state),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    except Exception as e:
        logger.error(f"Error reading engine config: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats")
def get_stats():
    if not recommender:
        return jsonify({"error": "Recommender not initialized"}), 500

    try:
        cluster_counts = {}
        for data in recommender.article_vectors.values():
            cluster = data.get("cluster", -1)
            cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1

        freshness_counts = {
            "today": 0,
            "this_week": 0,
            "this_month": 0,
            "older": 0,
        }

        for data in recommender.article_vectors.values():
            try:
                scraped_at = datetime.strptime(
                    data["metadata"]["scraped_at"],
                    "%Y-%m-%d %H:%M:%S",
                )
                days_old = (datetime.now() - scraped_at).days

                if days_old == 0:
                    freshness_counts["today"] += 1
                elif days_old <= 7:
                    freshness_counts["this_week"] += 1
                elif days_old <= 30:
                    freshness_counts["this_month"] += 1
                else:
                    freshness_counts["older"] += 1
            except (KeyError, ValueError):
                freshness_counts["older"] += 1

        cluster_topics = {}
        for data in recommender.article_vectors.values():
            cluster = data.get("cluster", -1)
            cluster_topics.setdefault(cluster, [])
            title = data.get("metadata", {}).get("title")
            if title:
                cluster_topics[cluster].append(title)

        for cluster in cluster_topics:
            if cluster_topics[cluster]:
                cluster_topics[cluster] = cluster_topics[cluster][:3]

        total_articles = len(recommender.article_vectors)
        clustered_total = sum(count for cluster, count in cluster_counts.items() if int(cluster) >= 0)
        largest_cluster = max((count for cluster, count in cluster_counts.items() if int(cluster) >= 0), default=0)
        cluster_quality = {
            "cluster_count": len([cluster for cluster in cluster_counts.keys() if int(cluster) >= 0]),
            "unclustered_count": int(cluster_counts.get(-1, 0)),
            "coverage_ratio": round((clustered_total / total_articles), 4) if total_articles else 0.0,
            "largest_cluster_share": round((largest_cluster / clustered_total), 4) if clustered_total else 0.0,
        }

        return jsonify(
            {
                "total_articles": total_articles,
                "cluster_distribution": cluster_counts,
                "freshness_distribution": freshness_counts,
                "cluster_topics": cluster_topics,
                "cluster_quality": cluster_quality,
            }
        )
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.errorhandler(400)
def bad_request_error(_error):
    return jsonify({"error": "Bad request"}), 400


@app.errorhandler(404)
def not_found_error(_error):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(_error):
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "5001"))
    debug = os.getenv("API_DEBUG", "True").lower() == "true"
    app.run(host=host, port=port, debug=debug)
