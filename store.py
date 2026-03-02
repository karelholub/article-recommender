"""Persistence layer for ranking configs and recommendation traces.

Backends:
- sqlite (default): file-backed, zero setup
- postgres: requires psycopg and DATABASE_URL
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class BaseRecommenderStore:
    def create_or_update_config(self, config_id: str, config: Dict, is_system: bool = False) -> int:
        raise NotImplementedError

    def ensure_system_config(self, config_id: str, config: Dict) -> int:
        raise NotImplementedError

    def get_config(self, config_id: str, version: Optional[int] = None) -> Optional[Tuple[Dict, int, bool]]:
        raise NotImplementedError

    def list_latest_configs(self) -> Dict[str, Dict]:
        raise NotImplementedError

    def delete_config(self, config_id: str) -> bool:
        raise NotImplementedError

    def persist_recommendation_run(
        self,
        user_id: str,
        config_id: str,
        config_version: int,
        request_payload: Dict,
        recommendations: List[Dict],
        request_duration_ms: Optional[int] = None,
    ) -> str:
        raise NotImplementedError

    def list_runs(self, limit: int = 20, offset: int = 0) -> List[Dict]:
        raise NotImplementedError

    def list_runs_with_request(
        self,
        limit: int = 100,
        offset: int = 0,
        days: Optional[int] = None,
    ) -> List[Dict]:
        raise NotImplementedError

    def get_run(self, run_id: str) -> Optional[Dict]:
        raise NotImplementedError

    def sync_sources(self, sources: List[str]) -> None:
        raise NotImplementedError

    def list_source_settings(self) -> Dict[str, Dict]:
        raise NotImplementedError

    def set_source_setting(self, source: str, enabled: bool, default_weight: float) -> None:
        raise NotImplementedError

    def list_connectors(self) -> List[Dict]:
        raise NotImplementedError

    def get_connector(self, connector_id: str) -> Optional[Dict]:
        raise NotImplementedError

    def create_connector(self, name: str, connector_type: str, config: Dict, enabled: bool = True) -> Dict:
        raise NotImplementedError

    def update_connector(
        self,
        connector_id: str,
        name: Optional[str] = None,
        connector_type: Optional[str] = None,
        config: Optional[Dict] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[Dict]:
        raise NotImplementedError

    def delete_connector(self, connector_id: str) -> bool:
        raise NotImplementedError

    def mark_connector_sync(self, connector_id: str) -> Optional[Dict]:
        raise NotImplementedError

    def start_connector_run(self, connector_id: str, trigger: str = "manual") -> str:
        raise NotImplementedError

    def finish_connector_run(
        self,
        run_id: str,
        status: str,
        attempted: int = 0,
        ingested: int = 0,
        skipped_existing: int = 0,
        errors: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        raise NotImplementedError

    def get_connector_run(self, run_id: str) -> Optional[Dict]:
        raise NotImplementedError

    def list_connector_runs(self, connector_id: str, limit: int = 20) -> List[Dict]:
        raise NotImplementedError

    def list_scenarios(self, include_disabled: bool = True) -> List[Dict]:
        raise NotImplementedError

    def get_scenario(self, scenario_id: str) -> Optional[Dict]:
        raise NotImplementedError

    def upsert_scenario(
        self,
        scenario_id: str,
        name: str,
        rule_set: Dict,
        description: str = "",
        enabled: bool = True,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        raise NotImplementedError

    def delete_scenario(self, scenario_id: str) -> bool:
        raise NotImplementedError

    def record_events(self, events: List[Dict]) -> int:
        raise NotImplementedError

    def list_events(
        self,
        limit: int = 100,
        offset: int = 0,
        scenario_id: Optional[str] = None,
        event_type: Optional[str] = None,
        days: Optional[int] = None,
    ) -> List[Dict]:
        raise NotImplementedError

    def get_idempotency_record(self, endpoint: str, key: str, max_age_hours: int = 24) -> Optional[Dict]:
        raise NotImplementedError

    def save_idempotency_record(
        self,
        endpoint: str,
        key: str,
        status_code: int,
        response_payload: Dict,
    ) -> None:
        raise NotImplementedError

    def record_audit_event(
        self,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        raise NotImplementedError

    def list_audit_events(
        self,
        limit: int = 100,
        offset: int = 0,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> List[Dict]:
        raise NotImplementedError

    def purge_idempotency_records(self, older_than_hours: int) -> int:
        raise NotImplementedError

    def purge_audit_events(self, older_than_days: int) -> int:
        raise NotImplementedError

    def get_alert_thresholds(self) -> Dict:
        raise NotImplementedError

    def upsert_alert_thresholds(self, thresholds: Dict) -> Dict:
        raise NotImplementedError

    def upsert_alert_incident(
        self,
        metric: str,
        current_value: Optional[float],
        threshold_value: Optional[float],
        details: Optional[Dict] = None,
    ) -> Dict:
        raise NotImplementedError

    def list_alert_incidents(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
        metric: Optional[str] = None,
    ) -> List[Dict]:
        raise NotImplementedError

    def resolve_alert_incident(self, incident_id: str, resolved_by: str, note: str = "") -> bool:
        raise NotImplementedError

    def resolve_open_alert_incidents(self, metric: str, resolved_by: str, note: str = "") -> int:
        raise NotImplementedError

    def compute_scenario_metrics(self, days: int = 30, top_articles: int = 5) -> Dict:
        raise NotImplementedError

    def compute_offline_metrics(self, limit_runs: int = 100) -> Dict:
        runs = self.list_runs(limit=limit_runs)
        if not runs:
            return {
                "runs_analyzed": 0,
                "avg_score": 0.0,
                "avg_source_diversity": 0.0,
                "avg_recommendation_count": 0.0,
                "feature_averages": {},
            }

        avg_score = sum(r["summary"].get("avg_score", 0.0) for r in runs) / len(runs)
        avg_diversity = sum(r["summary"].get("source_diversity", 0.0) for r in runs) / len(runs)
        avg_count = sum(r["summary"].get("count", 0.0) for r in runs) / len(runs)

        feature_totals: Dict[str, float] = {}
        feature_count = 0
        for run in runs:
            detail = self.get_run(run["run_id"])
            if not detail:
                continue
            for item in detail["items"]:
                features = item.get("features", {})
                for key, value in features.items():
                    feature_totals[key] = feature_totals.get(key, 0.0) + float(value)
                feature_count += 1

        feature_averages = {
            key: (value / feature_count if feature_count else 0.0)
            for key, value in feature_totals.items()
        }

        return {
            "runs_analyzed": len(runs),
            "avg_score": round(avg_score, 4),
            "avg_source_diversity": round(avg_diversity, 4),
            "avg_recommendation_count": round(avg_count, 4),
            "feature_averages": {k: round(v, 4) for k, v in feature_averages.items()},
        }

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


class SQLiteRecommenderStore(BaseRecommenderStore):
    DEFAULT_ALERT_THRESHOLDS = {
        "recommendation_p95_ms": 500.0,
        "connector_failure_rate": 0.05,
        "min_ctr": 0.01,
    }

    def __init__(self, db_path: str = "data/recommender.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _managed_connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._managed_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ranking_configs (
                    config_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    config_json TEXT NOT NULL,
                    is_system INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (config_id, version)
                );

                CREATE TABLE IF NOT EXISTS recommendation_runs (
                    run_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    config_id TEXT NOT NULL,
                    config_version INTEGER NOT NULL,
                    request_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS recommendation_items (
                    run_id TEXT NOT NULL,
                    rank_position INTEGER NOT NULL,
                    article_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    source TEXT,
                    features_json TEXT,
                    contributions_json TEXT,
                    explanation TEXT,
                    PRIMARY KEY (run_id, rank_position),
                    FOREIGN KEY (run_id) REFERENCES recommendation_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS source_settings (
                    source TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    default_weight REAL NOT NULL DEFAULT 1.0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS source_connectors (
                    connector_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    connector_type TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_run_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS connector_sync_runs (
                    run_id TEXT PRIMARY KEY,
                    connector_id TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempted INTEGER NOT NULL DEFAULT 0,
                    ingested INTEGER NOT NULL DEFAULT 0,
                    skipped_existing INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    errors_json TEXT NOT NULL DEFAULT '[]',
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS recommendation_scenarios (
                    scenario_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    rule_set_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS recommendation_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    run_id TEXT,
                    article_id TEXT,
                    scenario_id TEXT,
                    user_id TEXT NOT NULL,
                    external_user_id TEXT,
                    rank_position INTEGER,
                    event_value REAL NOT NULL DEFAULT 1.0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS api_idempotency_keys (
                    endpoint TEXT NOT NULL,
                    key TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (endpoint, key)
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    actor_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alert_thresholds (
                    threshold_id TEXT PRIMARY KEY,
                    thresholds_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alert_incidents (
                    incident_id TEXT PRIMARY KEY,
                    metric TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_value REAL,
                    threshold_value REAL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    occurrences INTEGER NOT NULL DEFAULT 1,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    resolved_at TEXT,
                    resolved_by TEXT,
                    resolution_note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_recommendation_events_created_at
                    ON recommendation_events(created_at);

                CREATE INDEX IF NOT EXISTS idx_recommendation_events_scenario_type
                    ON recommendation_events(scenario_id, event_type, created_at);

                CREATE INDEX IF NOT EXISTS idx_recommendation_events_article
                    ON recommendation_events(article_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_recommendation_events_run
                    ON recommendation_events(run_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_recommendation_events_external_user
                    ON recommendation_events(external_user_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_recommendation_runs_created_at
                    ON recommendation_runs(created_at);

                CREATE INDEX IF NOT EXISTS idx_api_idempotency_created_at
                    ON api_idempotency_keys(created_at);

                CREATE INDEX IF NOT EXISTS idx_audit_events_created_at
                    ON audit_events(created_at);

                CREATE INDEX IF NOT EXISTS idx_audit_events_actor
                    ON audit_events(actor_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_alert_incidents_status_metric
                    ON alert_incidents(status, metric, updated_at);
                """
            )

    def _latest_version(self, config_id: str) -> int:
        with self._managed_connection() as conn:
            row = conn.execute(
                "SELECT MAX(version) AS max_version FROM ranking_configs WHERE config_id = ?",
                (config_id,),
            ).fetchone()
            return int(row["max_version"] or 0)

    def create_or_update_config(self, config_id: str, config: Dict, is_system: bool = False) -> int:
        version = self._latest_version(config_id) + 1
        with self._managed_connection() as conn:
            conn.execute(
                """
                INSERT INTO ranking_configs (config_id, version, config_json, is_system, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (config_id, version, json.dumps(config, ensure_ascii=False), 1 if is_system else 0, self._now()),
            )
        return version

    def ensure_system_config(self, config_id: str, config: Dict) -> int:
        latest = self.get_config(config_id)
        if latest and latest[0] == config:
            return latest[1]
        return self.create_or_update_config(config_id, config, is_system=True)

    def get_config(self, config_id: str, version: Optional[int] = None) -> Optional[Tuple[Dict, int, bool]]:
        with self._managed_connection() as conn:
            if version is None:
                row = conn.execute(
                    """
                    SELECT config_json, version, is_system
                    FROM ranking_configs
                    WHERE config_id = ?
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    (config_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT config_json, version, is_system
                    FROM ranking_configs
                    WHERE config_id = ? AND version = ?
                    """,
                    (config_id, version),
                ).fetchone()

        if not row:
            return None
        return json.loads(row["config_json"]), int(row["version"]), bool(row["is_system"])

    def list_latest_configs(self) -> Dict[str, Dict]:
        with self._managed_connection() as conn:
            rows = conn.execute(
                """
                SELECT rc.config_id, rc.version, rc.config_json, rc.is_system, rc.created_at
                FROM ranking_configs rc
                INNER JOIN (
                    SELECT config_id, MAX(version) AS latest_version
                    FROM ranking_configs
                    GROUP BY config_id
                ) latest
                  ON rc.config_id = latest.config_id AND rc.version = latest.latest_version
                ORDER BY rc.config_id ASC
                """
            ).fetchall()

        configs = {}
        for row in rows:
            cfg = json.loads(row["config_json"])
            cfg["config_id"] = row["config_id"]
            configs[row["config_id"]] = {
                "config": cfg,
                "version": int(row["version"]),
                "is_system": bool(row["is_system"]),
                "created_at": row["created_at"],
            }
        return configs

    def delete_config(self, config_id: str) -> bool:
        with self._managed_connection() as conn:
            row = conn.execute(
                "SELECT MAX(is_system) as is_system FROM ranking_configs WHERE config_id = ?",
                (config_id,),
            ).fetchone()
            if not row or row["is_system"] is None:
                return False
            if int(row["is_system"]) == 1:
                return False

            conn.execute("DELETE FROM ranking_configs WHERE config_id = ?", (config_id,))
            return True

    def persist_recommendation_run(
        self,
        user_id: str,
        config_id: str,
        config_version: int,
        request_payload: Dict,
        recommendations: List[Dict],
        request_duration_ms: Optional[int] = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        scores = [float(item.get("score", 0.0)) for item in recommendations]
        unique_sources = len({item.get("source", "unknown") for item in recommendations}) if recommendations else 0
        summary = {
            "count": len(recommendations),
            "avg_score": (sum(scores) / len(scores)) if scores else 0.0,
            "source_diversity": (unique_sources / len(recommendations)) if recommendations else 0.0,
            "duration_ms": int(request_duration_ms) if request_duration_ms is not None else None,
        }

        with self._managed_connection() as conn:
            conn.execute(
                """
                INSERT INTO recommendation_runs
                (run_id, user_id, config_id, config_version, request_json, summary_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    user_id,
                    config_id,
                    int(config_version),
                    json.dumps(request_payload, ensure_ascii=False),
                    json.dumps(summary, ensure_ascii=False),
                    self._now(),
                ),
            )

            for idx, rec in enumerate(recommendations, start=1):
                conn.execute(
                    """
                    INSERT INTO recommendation_items
                    (run_id, rank_position, article_id, score, source, features_json, contributions_json, explanation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        idx,
                        rec.get("article_id", ""),
                        float(rec.get("score", 0.0)),
                        rec.get("source", "unknown"),
                        json.dumps(rec.get("features", {}), ensure_ascii=False),
                        json.dumps(rec.get("feature_contributions", {}), ensure_ascii=False),
                        rec.get("explanation", ""),
                    ),
                )

        return run_id

    def list_runs(self, limit: int = 20, offset: int = 0) -> List[Dict]:
        with self._managed_connection() as conn:
            rows = conn.execute(
                """
                SELECT run_id, user_id, config_id, config_version, summary_json, created_at
                FROM recommendation_runs
                ORDER BY created_at DESC
                LIMIT ?
                OFFSET ?
                """,
                (int(limit), int(offset)),
            ).fetchall()

        return [
            {
                "run_id": row["run_id"],
                "user_id": row["user_id"],
                "config_id": row["config_id"],
                "config_version": int(row["config_version"]),
                "summary": json.loads(row["summary_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def list_runs_with_request(
        self,
        limit: int = 100,
        offset: int = 0,
        days: Optional[int] = None,
    ) -> List[Dict]:
        clauses = []
        params: List = []
        if days is not None:
            cutoff = (datetime.now(UTC) - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d %H:%M:%S")
            clauses.append("created_at >= ?")
            params.append(cutoff)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._managed_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT run_id, user_id, config_id, config_version, request_json, summary_json, created_at
                FROM recommendation_runs
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                OFFSET ?
                """,
                (*params, int(limit), int(offset)),
            ).fetchall()

        return [
            {
                "run_id": row["run_id"],
                "user_id": row["user_id"],
                "config_id": row["config_id"],
                "config_version": int(row["config_version"]),
                "request": json.loads(row["request_json"] or "{}"),
                "summary": json.loads(row["summary_json"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def purge_idempotency_records(self, older_than_hours: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(hours=max(0, int(older_than_hours)))).strftime("%Y-%m-%d %H:%M:%S")
        with self._managed_connection() as conn:
            cur = conn.execute(
                "DELETE FROM api_idempotency_keys WHERE created_at <= ?",
                (cutoff,),
            )
            return int(cur.rowcount or 0)

    def purge_audit_events(self, older_than_days: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=max(0, int(older_than_days)))).strftime("%Y-%m-%d %H:%M:%S")
        with self._managed_connection() as conn:
            cur = conn.execute(
                "DELETE FROM audit_events WHERE created_at <= ?",
                (cutoff,),
            )
            return int(cur.rowcount or 0)

    def get_alert_thresholds(self) -> Dict:
        with self._managed_connection() as conn:
            row = conn.execute(
                """
                SELECT thresholds_json
                FROM alert_thresholds
                WHERE threshold_id = 'global'
                """,
            ).fetchone()
        if not row:
            return dict(self.DEFAULT_ALERT_THRESHOLDS)
        thresholds = json.loads(row["thresholds_json"] or "{}")
        merged = dict(self.DEFAULT_ALERT_THRESHOLDS)
        merged.update({k: float(v) for k, v in thresholds.items()})
        return merged

    def upsert_alert_thresholds(self, thresholds: Dict) -> Dict:
        merged = dict(self.get_alert_thresholds())
        merged.update({str(k): float(v) for k, v in (thresholds or {}).items()})
        with self._managed_connection() as conn:
            conn.execute(
                """
                INSERT INTO alert_thresholds (threshold_id, thresholds_json, updated_at)
                VALUES ('global', ?, ?)
                ON CONFLICT(threshold_id) DO UPDATE SET
                    thresholds_json = excluded.thresholds_json,
                    updated_at = excluded.updated_at
                """,
                (json.dumps(merged, ensure_ascii=False), self._now()),
            )
        return merged

    def upsert_alert_incident(
        self,
        metric: str,
        current_value: Optional[float],
        threshold_value: Optional[float],
        details: Optional[Dict] = None,
    ) -> Dict:
        now = self._now()
        with self._managed_connection() as conn:
            existing = conn.execute(
                """
                SELECT incident_id, occurrences
                FROM alert_incidents
                WHERE metric = ? AND status = 'open'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (metric,),
            ).fetchone()
            if existing:
                incident_id = existing["incident_id"]
                conn.execute(
                    """
                    UPDATE alert_incidents
                    SET current_value = ?, threshold_value = ?, details_json = ?, occurrences = ?, last_seen_at = ?, updated_at = ?
                    WHERE incident_id = ?
                    """,
                    (
                        float(current_value) if current_value is not None else None,
                        float(threshold_value) if threshold_value is not None else None,
                        json.dumps(details or {}, ensure_ascii=False),
                        int(existing["occurrences"]) + 1,
                        now,
                        now,
                        incident_id,
                    ),
                )
            else:
                incident_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO alert_incidents
                    (incident_id, metric, status, current_value, threshold_value, details_json, occurrences, first_seen_at, last_seen_at, resolved_at, resolved_by, resolution_note, created_at, updated_at)
                    VALUES (?, ?, 'open', ?, ?, ?, 1, ?, ?, NULL, NULL, NULL, ?, ?)
                    """,
                    (
                        incident_id,
                        metric,
                        float(current_value) if current_value is not None else None,
                        float(threshold_value) if threshold_value is not None else None,
                        json.dumps(details or {}, ensure_ascii=False),
                        now,
                        now,
                        now,
                        now,
                    ),
                )

            row = conn.execute(
                """
                SELECT incident_id, metric, status, current_value, threshold_value, details_json, occurrences,
                       first_seen_at, last_seen_at, resolved_at, resolved_by, resolution_note, created_at, updated_at
                FROM alert_incidents
                WHERE incident_id = ?
                """,
                (incident_id,),
            ).fetchone()
        return {
            "incident_id": row["incident_id"],
            "metric": row["metric"],
            "status": row["status"],
            "current_value": float(row["current_value"]) if row["current_value"] is not None else None,
            "threshold_value": float(row["threshold_value"]) if row["threshold_value"] is not None else None,
            "details": json.loads(row["details_json"] or "{}"),
            "occurrences": int(row["occurrences"]),
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "resolved_at": row["resolved_at"],
            "resolved_by": row["resolved_by"],
            "resolution_note": row["resolution_note"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_alert_incidents(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
        metric: Optional[str] = None,
    ) -> List[Dict]:
        clauses = []
        params: List = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if metric:
            clauses.append("metric = ?")
            params.append(metric)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._managed_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT incident_id, metric, status, current_value, threshold_value, details_json, occurrences,
                       first_seen_at, last_seen_at, resolved_at, resolved_by, resolution_note, created_at, updated_at
                FROM alert_incidents
                {where}
                ORDER BY updated_at DESC
                LIMIT ?
                OFFSET ?
                """,
                (*params, int(limit), int(offset)),
            ).fetchall()
        return [
            {
                "incident_id": row["incident_id"],
                "metric": row["metric"],
                "status": row["status"],
                "current_value": float(row["current_value"]) if row["current_value"] is not None else None,
                "threshold_value": float(row["threshold_value"]) if row["threshold_value"] is not None else None,
                "details": json.loads(row["details_json"] or "{}"),
                "occurrences": int(row["occurrences"]),
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
                "resolved_at": row["resolved_at"],
                "resolved_by": row["resolved_by"],
                "resolution_note": row["resolution_note"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def resolve_alert_incident(self, incident_id: str, resolved_by: str, note: str = "") -> bool:
        now = self._now()
        with self._managed_connection() as conn:
            cur = conn.execute(
                """
                UPDATE alert_incidents
                SET status = 'resolved', resolved_at = ?, resolved_by = ?, resolution_note = ?, updated_at = ?
                WHERE incident_id = ? AND status = 'open'
                """,
                (now, resolved_by, note, now, incident_id),
            )
            return (cur.rowcount or 0) > 0

    def resolve_open_alert_incidents(self, metric: str, resolved_by: str, note: str = "") -> int:
        now = self._now()
        with self._managed_connection() as conn:
            cur = conn.execute(
                """
                UPDATE alert_incidents
                SET status = 'resolved', resolved_at = ?, resolved_by = ?, resolution_note = ?, updated_at = ?
                WHERE metric = ? AND status = 'open'
                """,
                (now, resolved_by, note, now, metric),
            )
            return int(cur.rowcount or 0)

    def upsert_alert_incident(
        self,
        metric: str,
        current_value: Optional[float],
        threshold_value: Optional[float],
        details: Optional[Dict] = None,
    ) -> Dict:
        now = self._now()
        with self._managed_connection() as conn:
            existing = conn.execute(
                """
                SELECT incident_id, occurrences, first_seen_at
                FROM alert_incidents
                WHERE metric = ? AND status = 'open'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (metric,),
            ).fetchone()
            if existing:
                incident_id = existing["incident_id"]
                conn.execute(
                    """
                    UPDATE alert_incidents
                    SET current_value = ?, threshold_value = ?, details_json = ?, occurrences = ?, last_seen_at = ?, updated_at = ?
                    WHERE incident_id = ?
                    """,
                    (
                        float(current_value) if current_value is not None else None,
                        float(threshold_value) if threshold_value is not None else None,
                        json.dumps(details or {}, ensure_ascii=False),
                        int(existing["occurrences"]) + 1,
                        now,
                        now,
                        incident_id,
                    ),
                )
            else:
                incident_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO alert_incidents
                    (incident_id, metric, status, current_value, threshold_value, details_json, occurrences, first_seen_at, last_seen_at, resolved_at, resolved_by, resolution_note, created_at, updated_at)
                    VALUES (?, ?, 'open', ?, ?, ?, 1, ?, ?, NULL, NULL, NULL, ?, ?)
                    """,
                    (
                        incident_id,
                        metric,
                        float(current_value) if current_value is not None else None,
                        float(threshold_value) if threshold_value is not None else None,
                        json.dumps(details or {}, ensure_ascii=False),
                        now,
                        now,
                        now,
                        now,
                    ),
                )

            row = conn.execute(
                """
                SELECT incident_id, metric, status, current_value, threshold_value, details_json, occurrences,
                       first_seen_at, last_seen_at, resolved_at, resolved_by, resolution_note, created_at, updated_at
                FROM alert_incidents
                WHERE incident_id = ?
                """,
                (incident_id,),
            ).fetchone()
        return {
            "incident_id": row["incident_id"],
            "metric": row["metric"],
            "status": row["status"],
            "current_value": float(row["current_value"]) if row["current_value"] is not None else None,
            "threshold_value": float(row["threshold_value"]) if row["threshold_value"] is not None else None,
            "details": json.loads(row["details_json"] or "{}"),
            "occurrences": int(row["occurrences"]),
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "resolved_at": row["resolved_at"],
            "resolved_by": row["resolved_by"],
            "resolution_note": row["resolution_note"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_alert_incidents(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
        metric: Optional[str] = None,
    ) -> List[Dict]:
        clauses = []
        params: List = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if metric:
            clauses.append("metric = ?")
            params.append(metric)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._managed_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT incident_id, metric, status, current_value, threshold_value, details_json, occurrences,
                       first_seen_at, last_seen_at, resolved_at, resolved_by, resolution_note, created_at, updated_at
                FROM alert_incidents
                {where}
                ORDER BY updated_at DESC
                LIMIT ?
                OFFSET ?
                """,
                (*params, int(limit), int(offset)),
            ).fetchall()
        return [
            {
                "incident_id": row["incident_id"],
                "metric": row["metric"],
                "status": row["status"],
                "current_value": float(row["current_value"]) if row["current_value"] is not None else None,
                "threshold_value": float(row["threshold_value"]) if row["threshold_value"] is not None else None,
                "details": json.loads(row["details_json"] or "{}"),
                "occurrences": int(row["occurrences"]),
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
                "resolved_at": row["resolved_at"],
                "resolved_by": row["resolved_by"],
                "resolution_note": row["resolution_note"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def resolve_alert_incident(self, incident_id: str, resolved_by: str, note: str = "") -> bool:
        now = self._now()
        with self._managed_connection() as conn:
            cur = conn.execute(
                """
                UPDATE alert_incidents
                SET status = 'resolved', resolved_at = ?, resolved_by = ?, resolution_note = ?, updated_at = ?
                WHERE incident_id = ? AND status = 'open'
                """,
                (now, resolved_by, note, now, incident_id),
            )
            return (cur.rowcount or 0) > 0

    def resolve_open_alert_incidents(self, metric: str, resolved_by: str, note: str = "") -> int:
        now = self._now()
        with self._managed_connection() as conn:
            cur = conn.execute(
                """
                UPDATE alert_incidents
                SET status = 'resolved', resolved_at = ?, resolved_by = ?, resolution_note = ?, updated_at = ?
                WHERE metric = ? AND status = 'open'
                """,
                (now, resolved_by, note, now, metric),
            )
            return int(cur.rowcount or 0)

    def get_run(self, run_id: str) -> Optional[Dict]:
        with self._managed_connection() as conn:
            run = conn.execute(
                """
                SELECT run_id, user_id, config_id, config_version, request_json, summary_json, created_at
                FROM recommendation_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if not run:
                return None

            items = conn.execute(
                """
                SELECT rank_position, article_id, score, source, features_json, contributions_json, explanation
                FROM recommendation_items
                WHERE run_id = ?
                ORDER BY rank_position ASC
                """,
                (run_id,),
            ).fetchall()

        return {
            "run_id": run["run_id"],
            "user_id": run["user_id"],
            "config_id": run["config_id"],
            "config_version": int(run["config_version"]),
            "request": json.loads(run["request_json"]),
            "summary": json.loads(run["summary_json"]),
            "created_at": run["created_at"],
            "items": [
                {
                    "rank": int(item["rank_position"]),
                    "article_id": item["article_id"],
                    "score": float(item["score"]),
                    "source": item["source"],
                    "features": json.loads(item["features_json"] or "{}"),
                    "feature_contributions": json.loads(item["contributions_json"] or "{}"),
                    "explanation": item["explanation"],
                }
                for item in items
            ],
        }

    def sync_sources(self, sources: List[str]) -> None:
        unique_sources = sorted({s for s in sources if s})
        if not unique_sources:
            return

        with self._managed_connection() as conn:
            for source in unique_sources:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO source_settings (source, enabled, default_weight, updated_at)
                    VALUES (?, 1, 1.0, ?)
                    """,
                    (source, self._now()),
                )

    def list_source_settings(self) -> Dict[str, Dict]:
        with self._managed_connection() as conn:
            rows = conn.execute(
                """
                SELECT source, enabled, default_weight, updated_at
                FROM source_settings
                ORDER BY source ASC
                """
            ).fetchall()

        return {
            row["source"]: {
                "enabled": bool(row["enabled"]),
                "default_weight": float(row["default_weight"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        }

    def set_source_setting(self, source: str, enabled: bool, default_weight: float) -> None:
        with self._managed_connection() as conn:
            conn.execute(
                """
                INSERT INTO source_settings (source, enabled, default_weight, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    enabled = excluded.enabled,
                    default_weight = excluded.default_weight,
                    updated_at = excluded.updated_at
                """,
                (source, 1 if enabled else 0, float(default_weight), self._now()),
            )

    def list_connectors(self) -> List[Dict]:
        with self._managed_connection() as conn:
            rows = conn.execute(
                """
                SELECT connector_id, name, connector_type, config_json, enabled, last_run_at, created_at, updated_at
                FROM source_connectors
                ORDER BY created_at DESC
                """
            ).fetchall()

        return [
            {
                "connector_id": row["connector_id"],
                "name": row["name"],
                "connector_type": row["connector_type"],
                "config": json.loads(row["config_json"] or "{}"),
                "enabled": bool(row["enabled"]),
                "last_run_at": row["last_run_at"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_connector(self, connector_id: str) -> Optional[Dict]:
        with self._managed_connection() as conn:
            row = conn.execute(
                """
                SELECT connector_id, name, connector_type, config_json, enabled, last_run_at, created_at, updated_at
                FROM source_connectors
                WHERE connector_id = ?
                """,
                (connector_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "connector_id": row["connector_id"],
            "name": row["name"],
            "connector_type": row["connector_type"],
            "config": json.loads(row["config_json"] or "{}"),
            "enabled": bool(row["enabled"]),
            "last_run_at": row["last_run_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_connector(self, name: str, connector_type: str, config: Dict, enabled: bool = True) -> Dict:
        connector_id = str(uuid.uuid4())
        now = self._now()
        with self._managed_connection() as conn:
            conn.execute(
                """
                INSERT INTO source_connectors
                (connector_id, name, connector_type, config_json, enabled, last_run_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    connector_id,
                    name,
                    connector_type,
                    json.dumps(config, ensure_ascii=False),
                    1 if enabled else 0,
                    now,
                    now,
                ),
            )
        return self.get_connector(connector_id) or {}

    def update_connector(
        self,
        connector_id: str,
        name: Optional[str] = None,
        connector_type: Optional[str] = None,
        config: Optional[Dict] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[Dict]:
        current = self.get_connector(connector_id)
        if not current:
            return None

        next_name = name if name is not None else current["name"]
        next_type = connector_type if connector_type is not None else current["connector_type"]
        next_config = config if config is not None else current["config"]
        next_enabled = bool(enabled) if enabled is not None else current["enabled"]

        with self._managed_connection() as conn:
            conn.execute(
                """
                UPDATE source_connectors
                SET name = ?, connector_type = ?, config_json = ?, enabled = ?, updated_at = ?
                WHERE connector_id = ?
                """,
                (
                    next_name,
                    next_type,
                    json.dumps(next_config, ensure_ascii=False),
                    1 if next_enabled else 0,
                    self._now(),
                    connector_id,
                ),
            )
        return self.get_connector(connector_id)

    def delete_connector(self, connector_id: str) -> bool:
        with self._managed_connection() as conn:
            cur = conn.execute(
                "DELETE FROM source_connectors WHERE connector_id = ?",
                (connector_id,),
            )
            return cur.rowcount > 0

    def mark_connector_sync(self, connector_id: str) -> Optional[Dict]:
        with self._managed_connection() as conn:
            cur = conn.execute(
                """
                UPDATE source_connectors
                SET last_run_at = ?, updated_at = ?
                WHERE connector_id = ?
                """,
                (self._now(), self._now(), connector_id),
            )
            if cur.rowcount == 0:
                return None
        return self.get_connector(connector_id)

    def start_connector_run(self, connector_id: str, trigger: str = "manual") -> str:
        run_id = str(uuid.uuid4())
        now = self._now()
        with self._managed_connection() as conn:
            conn.execute(
                """
                INSERT INTO connector_sync_runs
                (run_id, connector_id, trigger, status, attempted, ingested, skipped_existing, error_count, errors_json, started_at, finished_at, created_at)
                VALUES (?, ?, ?, ?, 0, 0, 0, 0, '[]', ?, NULL, ?)
                """,
                (run_id, connector_id, trigger, "running", now, now),
            )
        return run_id

    def finish_connector_run(
        self,
        run_id: str,
        status: str,
        attempted: int = 0,
        ingested: int = 0,
        skipped_existing: int = 0,
        errors: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        errors_list = errors or []
        now = self._now()
        with self._managed_connection() as conn:
            cur = conn.execute(
                """
                UPDATE connector_sync_runs
                SET status = ?, attempted = ?, ingested = ?, skipped_existing = ?, error_count = ?, errors_json = ?, finished_at = ?
                WHERE run_id = ?
                """,
                (
                    status,
                    int(attempted),
                    int(ingested),
                    int(skipped_existing),
                    len(errors_list),
                    json.dumps(errors_list, ensure_ascii=False),
                    now,
                    run_id,
                ),
            )
            if cur.rowcount == 0:
                return None
        return self.get_connector_run(run_id)

    def get_connector_run(self, run_id: str) -> Optional[Dict]:
        with self._managed_connection() as conn:
            row = conn.execute(
                """
                SELECT run_id, connector_id, trigger, status, attempted, ingested, skipped_existing, error_count, errors_json, started_at, finished_at, created_at
                FROM connector_sync_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "run_id": row["run_id"],
            "connector_id": row["connector_id"],
            "trigger": row["trigger"],
            "status": row["status"],
            "attempted": int(row["attempted"]),
            "ingested": int(row["ingested"]),
            "skipped_existing": int(row["skipped_existing"]),
            "error_count": int(row["error_count"]),
            "errors": json.loads(row["errors_json"] or "[]"),
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "created_at": row["created_at"],
        }

    def list_connector_runs(self, connector_id: str, limit: int = 20) -> List[Dict]:
        with self._managed_connection() as conn:
            rows = conn.execute(
                """
                SELECT run_id, connector_id, trigger, status, attempted, ingested, skipped_existing, error_count, errors_json, started_at, finished_at, created_at
                FROM connector_sync_runs
                WHERE connector_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (connector_id, int(limit)),
            ).fetchall()
        return [
            {
                "run_id": row["run_id"],
                "connector_id": row["connector_id"],
                "trigger": row["trigger"],
                "status": row["status"],
                "attempted": int(row["attempted"]),
                "ingested": int(row["ingested"]),
                "skipped_existing": int(row["skipped_existing"]),
                "error_count": int(row["error_count"]),
                "errors": json.loads(row["errors_json"] or "[]"),
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def list_scenarios(self, include_disabled: bool = True) -> List[Dict]:
        with self._managed_connection() as conn:
            if include_disabled:
                rows = conn.execute(
                    """
                    SELECT scenario_id, name, description, enabled, rule_set_json, metadata_json, created_at, updated_at
                    FROM recommendation_scenarios
                    ORDER BY name ASC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT scenario_id, name, description, enabled, rule_set_json, metadata_json, created_at, updated_at
                    FROM recommendation_scenarios
                    WHERE enabled = 1
                    ORDER BY name ASC
                    """
                ).fetchall()

        return [
            {
                "scenario_id": row["scenario_id"],
                "name": row["name"],
                "description": row["description"],
                "enabled": bool(row["enabled"]),
                "rule_set": json.loads(row["rule_set_json"] or "{}"),
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_scenario(self, scenario_id: str) -> Optional[Dict]:
        with self._managed_connection() as conn:
            row = conn.execute(
                """
                SELECT scenario_id, name, description, enabled, rule_set_json, metadata_json, created_at, updated_at
                FROM recommendation_scenarios
                WHERE scenario_id = ?
                """,
                (scenario_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "scenario_id": row["scenario_id"],
            "name": row["name"],
            "description": row["description"],
            "enabled": bool(row["enabled"]),
            "rule_set": json.loads(row["rule_set_json"] or "{}"),
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def upsert_scenario(
        self,
        scenario_id: str,
        name: str,
        rule_set: Dict,
        description: str = "",
        enabled: bool = True,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        now = self._now()
        with self._managed_connection() as conn:
            conn.execute(
                """
                INSERT INTO recommendation_scenarios
                (scenario_id, name, description, enabled, rule_set_json, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    enabled = excluded.enabled,
                    rule_set_json = excluded.rule_set_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    scenario_id,
                    name,
                    description or "",
                    1 if enabled else 0,
                    json.dumps(rule_set or {}, ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get_scenario(scenario_id) or {}

    def delete_scenario(self, scenario_id: str) -> bool:
        with self._managed_connection() as conn:
            cur = conn.execute(
                "DELETE FROM recommendation_scenarios WHERE scenario_id = ?",
                (scenario_id,),
            )
            return cur.rowcount > 0

    def record_events(self, events: List[Dict]) -> int:
        if not events:
            return 0
        with self._managed_connection() as conn:
            for event in events:
                conn.execute(
                    """
                    INSERT INTO recommendation_events
                    (event_id, event_type, run_id, article_id, scenario_id, user_id, external_user_id, rank_position, event_value, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        event.get("event_type"),
                        event.get("run_id"),
                        event.get("article_id"),
                        event.get("scenario_id"),
                        event.get("user_id") or "anonymous",
                        event.get("external_user_id"),
                        event.get("rank_position"),
                        float(event.get("event_value", 1.0)),
                        json.dumps(event.get("metadata", {}), ensure_ascii=False),
                        event.get("created_at") or self._now(),
                    ),
                )
        return len(events)

    def list_events(
        self,
        limit: int = 100,
        offset: int = 0,
        scenario_id: Optional[str] = None,
        event_type: Optional[str] = None,
        days: Optional[int] = None,
    ) -> List[Dict]:
        clauses = []
        params: List = []
        if scenario_id is not None:
            clauses.append("scenario_id = ?")
            params.append(scenario_id)
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        if days is not None:
            cutoff = (datetime.now(UTC) - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d %H:%M:%S")
            clauses.append("created_at >= ?")
            params.append(cutoff)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._managed_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT event_id, event_type, run_id, article_id, scenario_id, user_id, external_user_id, rank_position, event_value, metadata_json, created_at
                FROM recommendation_events
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                OFFSET ?
                """,
                (*params, int(limit), int(offset)),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "run_id": row["run_id"],
                "article_id": row["article_id"],
                "scenario_id": row["scenario_id"],
                "user_id": row["user_id"],
                "external_user_id": row["external_user_id"],
                "rank_position": int(row["rank_position"]) if row["rank_position"] is not None else None,
                "event_value": float(row["event_value"]),
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def compute_scenario_metrics(self, days: int = 30, top_articles: int = 5) -> Dict:
        cutoff = (datetime.now(UTC) - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d %H:%M:%S")
        with self._managed_connection() as conn:
            rows = conn.execute(
                """
                SELECT scenario_id, article_id, event_type
                FROM recommendation_events
                WHERE created_at >= ?
                """,
                (cutoff,),
            ).fetchall()

        scenarios = {entry["scenario_id"]: entry for entry in self.list_scenarios(include_disabled=True)}
        bucketed: Dict[str, Dict] = {}
        for row in rows:
            key = row["scenario_id"] or "default"
            bucket = bucketed.setdefault(
                key,
                {
                    "scenario_id": key,
                    "name": scenarios.get(key, {}).get("name", "Default"),
                    "enabled": scenarios.get(key, {}).get("enabled", True),
                    "impressions": 0,
                    "clicks": 0,
                    "conversions": 0,
                    "article_stats": {},
                },
            )
            event_type = row["event_type"]
            article_id = row["article_id"] or "unknown"
            article_bucket = bucket["article_stats"].setdefault(
                article_id,
                {"article_id": article_id, "impressions": 0, "clicks": 0, "conversions": 0},
            )
            if event_type == "impression":
                bucket["impressions"] += 1
                article_bucket["impressions"] += 1
            elif event_type == "click":
                bucket["clicks"] += 1
                article_bucket["clicks"] += 1
            elif event_type == "conversion":
                bucket["conversions"] += 1
                article_bucket["conversions"] += 1

        scenarios_out = []
        totals = {"impressions": 0, "clicks": 0, "conversions": 0}
        for item in bucketed.values():
            impressions = item["impressions"]
            clicks = item["clicks"]
            conversions = item["conversions"]
            totals["impressions"] += impressions
            totals["clicks"] += clicks
            totals["conversions"] += conversions
            top = sorted(
                item["article_stats"].values(),
                key=lambda x: (x["clicks"], x["impressions"], x["conversions"]),
                reverse=True,
            )[: max(1, int(top_articles))]
            scenarios_out.append(
                {
                    "scenario_id": item["scenario_id"],
                    "name": item["name"],
                    "enabled": item["enabled"],
                    "impressions": impressions,
                    "clicks": clicks,
                    "conversions": conversions,
                    "ctr": round((clicks / impressions), 4) if impressions else 0.0,
                    "conversion_rate": round((conversions / clicks), 4) if clicks else 0.0,
                    "top_articles": top,
                }
            )

        return {
            "window_days": max(1, int(days)),
            "generated_at": self._now(),
            "scenarios": sorted(scenarios_out, key=lambda x: x["impressions"], reverse=True),
            "totals": {
                "impressions": totals["impressions"],
                "clicks": totals["clicks"],
                "conversions": totals["conversions"],
                "ctr": round((totals["clicks"] / totals["impressions"]), 4) if totals["impressions"] else 0.0,
                "conversion_rate": round((totals["conversions"] / totals["clicks"]), 4) if totals["clicks"] else 0.0,
            },
        }

    def get_idempotency_record(self, endpoint: str, key: str, max_age_hours: int = 24) -> Optional[Dict]:
        cutoff = (datetime.now(UTC) - timedelta(hours=max(1, int(max_age_hours)))).strftime("%Y-%m-%d %H:%M:%S")
        with self._managed_connection() as conn:
            row = conn.execute(
                """
                SELECT endpoint, key, status_code, response_json, created_at
                FROM api_idempotency_keys
                WHERE endpoint = ? AND key = ? AND created_at >= ?
                """,
                (endpoint, key, cutoff),
            ).fetchone()
        if not row:
            return None
        return {
            "endpoint": row["endpoint"],
            "key": row["key"],
            "status_code": int(row["status_code"]),
            "response": json.loads(row["response_json"] or "{}"),
            "created_at": row["created_at"],
        }

    def save_idempotency_record(
        self,
        endpoint: str,
        key: str,
        status_code: int,
        response_payload: Dict,
    ) -> None:
        with self._managed_connection() as conn:
            conn.execute(
                """
                INSERT INTO api_idempotency_keys (endpoint, key, status_code, response_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(endpoint, key) DO UPDATE SET
                    status_code = excluded.status_code,
                    response_json = excluded.response_json,
                    created_at = excluded.created_at
                """,
                (
                    endpoint,
                    key,
                    int(status_code),
                    json.dumps(response_payload, ensure_ascii=False),
                    self._now(),
                ),
            )

    def record_audit_event(
        self,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        with self._managed_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_events
                (event_id, actor_id, action, resource_type, resource_id, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    actor_id or "unknown",
                    action,
                    resource_type,
                    resource_id,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    self._now(),
                ),
            )
        return event_id

    def list_audit_events(
        self,
        limit: int = 100,
        offset: int = 0,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> List[Dict]:
        clauses = []
        params: List = []
        if actor_id:
            clauses.append("actor_id = ?")
            params.append(actor_id)
        if resource_type:
            clauses.append("resource_type = ?")
            params.append(resource_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._managed_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT event_id, actor_id, action, resource_type, resource_id, metadata_json, created_at
                FROM audit_events
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                OFFSET ?
                """,
                (*params, int(limit), int(offset)),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "actor_id": row["actor_id"],
                "action": row["action"],
                "resource_type": row["resource_type"],
                "resource_id": row["resource_id"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]


class PostgresRecommenderStore(BaseRecommenderStore):
    DEFAULT_ALERT_THRESHOLDS = {
        "recommendation_p95_ms": 500.0,
        "connector_failure_rate": 0.05,
        "min_ctr": 0.01,
    }

    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("DATABASE_URL is required for postgres backend")
        try:
            import psycopg
        except ImportError as exc:
            raise ImportError("psycopg is required for postgres backend") from exc

        self.psycopg = psycopg
        self.database_url = database_url
        self._init_db()

    @contextmanager
    def _managed_connection(self):
        conn = self.psycopg.connect(self.database_url)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                # Prevent concurrent schema bootstrap across multiple gunicorn workers.
                cur.execute("SELECT pg_advisory_lock(%s)", (987654321,))
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ranking_configs (
                        config_id TEXT NOT NULL,
                        version INTEGER NOT NULL,
                        config_json JSONB NOT NULL,
                        is_system BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (config_id, version)
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recommendation_runs (
                        run_id UUID PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        config_id TEXT NOT NULL,
                        config_version INTEGER NOT NULL,
                        request_json JSONB NOT NULL,
                        summary_json JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recommendation_items (
                        run_id UUID NOT NULL,
                        rank_position INTEGER NOT NULL,
                        article_id TEXT NOT NULL,
                        score DOUBLE PRECISION NOT NULL,
                        source TEXT,
                        features_json JSONB,
                        contributions_json JSONB,
                        explanation TEXT,
                        PRIMARY KEY (run_id, rank_position),
                        FOREIGN KEY (run_id) REFERENCES recommendation_runs(run_id)
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS source_settings (
                        source TEXT PRIMARY KEY,
                        enabled BOOLEAN NOT NULL DEFAULT TRUE,
                        default_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                        updated_at TIMESTAMPTZ NOT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS source_connectors (
                        connector_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        connector_type TEXT NOT NULL,
                        config_json JSONB NOT NULL,
                        enabled BOOLEAN NOT NULL DEFAULT TRUE,
                        last_run_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS connector_sync_runs (
                        run_id UUID PRIMARY KEY,
                        connector_id TEXT NOT NULL,
                        trigger TEXT NOT NULL,
                        status TEXT NOT NULL,
                        attempted INTEGER NOT NULL DEFAULT 0,
                        ingested INTEGER NOT NULL DEFAULT 0,
                        skipped_existing INTEGER NOT NULL DEFAULT 0,
                        error_count INTEGER NOT NULL DEFAULT 0,
                        errors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        started_at TIMESTAMPTZ NOT NULL,
                        finished_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recommendation_scenarios (
                        scenario_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        enabled BOOLEAN NOT NULL DEFAULT TRUE,
                        rule_set_json JSONB NOT NULL,
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recommendation_events (
                        event_id UUID PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        run_id UUID,
                        article_id TEXT,
                        scenario_id TEXT,
                        user_id TEXT NOT NULL,
                        external_user_id TEXT,
                        rank_position INTEGER,
                        event_value DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS api_idempotency_keys (
                        endpoint TEXT NOT NULL,
                        key TEXT NOT NULL,
                        status_code INTEGER NOT NULL,
                        response_json JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (endpoint, key)
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_events (
                        event_id UUID PRIMARY KEY,
                        actor_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        resource_type TEXT NOT NULL,
                        resource_id TEXT NOT NULL,
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alert_thresholds (
                        threshold_id TEXT PRIMARY KEY,
                        thresholds_json JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alert_incidents (
                        incident_id UUID PRIMARY KEY,
                        metric TEXT NOT NULL,
                        status TEXT NOT NULL,
                        current_value DOUBLE PRECISION,
                        threshold_value DOUBLE PRECISION,
                        details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        occurrences INTEGER NOT NULL DEFAULT 1,
                        first_seen_at TIMESTAMPTZ NOT NULL,
                        last_seen_at TIMESTAMPTZ NOT NULL,
                        resolved_at TIMESTAMPTZ,
                        resolved_by TEXT,
                        resolution_note TEXT,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_recommendation_events_created_at
                    ON recommendation_events(created_at);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_recommendation_events_scenario_type
                    ON recommendation_events(scenario_id, event_type, created_at);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_recommendation_events_article
                    ON recommendation_events(article_id, created_at);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_recommendation_events_run
                    ON recommendation_events(run_id, created_at);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_recommendation_events_external_user
                    ON recommendation_events(external_user_id, created_at);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_recommendation_runs_created_at
                    ON recommendation_runs(created_at);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_api_idempotency_created_at
                    ON api_idempotency_keys(created_at);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_audit_events_created_at
                    ON audit_events(created_at);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_audit_events_actor
                    ON audit_events(actor_id, created_at);
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_alert_incidents_status_metric
                    ON alert_incidents(status, metric, updated_at);
                    """
                )
                cur.execute("SELECT pg_advisory_unlock(%s)", (987654321,))

    def _latest_version(self, config_id: str) -> int:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM ranking_configs WHERE config_id = %s",
                    (config_id,),
                )
                row = cur.fetchone()
                return int(row[0] if row else 0)

    def create_or_update_config(self, config_id: str, config: Dict, is_system: bool = False) -> int:
        version = self._latest_version(config_id) + 1
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ranking_configs (config_id, version, config_json, is_system, created_at)
                    VALUES (%s, %s, %s::jsonb, %s, %s)
                    """,
                    (config_id, version, json.dumps(config, ensure_ascii=False), bool(is_system), datetime.now(UTC)),
                )
        return version

    def ensure_system_config(self, config_id: str, config: Dict) -> int:
        latest = self.get_config(config_id)
        if latest and latest[0] == config:
            return latest[1]
        return self.create_or_update_config(config_id, config, is_system=True)

    def get_config(self, config_id: str, version: Optional[int] = None) -> Optional[Tuple[Dict, int, bool]]:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                if version is None:
                    cur.execute(
                        """
                        SELECT config_json::text, version, is_system
                        FROM ranking_configs
                        WHERE config_id = %s
                        ORDER BY version DESC
                        LIMIT 1
                        """,
                        (config_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT config_json::text, version, is_system
                        FROM ranking_configs
                        WHERE config_id = %s AND version = %s
                        """,
                        (config_id, int(version)),
                    )
                row = cur.fetchone()

        if not row:
            return None
        return json.loads(row[0]), int(row[1]), bool(row[2])

    def list_latest_configs(self) -> Dict[str, Dict]:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT rc.config_id, rc.version, rc.config_json::text, rc.is_system, rc.created_at
                    FROM ranking_configs rc
                    INNER JOIN (
                        SELECT config_id, MAX(version) AS latest_version
                        FROM ranking_configs
                        GROUP BY config_id
                    ) latest
                      ON rc.config_id = latest.config_id AND rc.version = latest.latest_version
                    ORDER BY rc.config_id ASC
                    """
                )
                rows = cur.fetchall()

        configs = {}
        for row in rows:
            cfg = json.loads(row[2])
            cfg["config_id"] = row[0]
            configs[row[0]] = {
                "config": cfg,
                "version": int(row[1]),
                "is_system": bool(row[3]),
                "created_at": row[4].strftime("%Y-%m-%d %H:%M:%S"),
            }
        return configs

    def delete_config(self, config_id: str) -> bool:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT MAX(CASE WHEN is_system THEN 1 ELSE 0 END) FROM ranking_configs WHERE config_id = %s",
                    (config_id,),
                )
                row = cur.fetchone()
                if not row or row[0] is None:
                    return False
                if int(row[0]) == 1:
                    return False
                cur.execute("DELETE FROM ranking_configs WHERE config_id = %s", (config_id,))
                return cur.rowcount > 0

    def persist_recommendation_run(
        self,
        user_id: str,
        config_id: str,
        config_version: int,
        request_payload: Dict,
        recommendations: List[Dict],
        request_duration_ms: Optional[int] = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        scores = [float(item.get("score", 0.0)) for item in recommendations]
        unique_sources = len({item.get("source", "unknown") for item in recommendations}) if recommendations else 0
        summary = {
            "count": len(recommendations),
            "avg_score": (sum(scores) / len(scores)) if scores else 0.0,
            "source_diversity": (unique_sources / len(recommendations)) if recommendations else 0.0,
            "duration_ms": int(request_duration_ms) if request_duration_ms is not None else None,
        }

        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO recommendation_runs
                    (run_id, user_id, config_id, config_version, request_json, summary_json, created_at)
                    VALUES (%s::uuid, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                    """,
                    (
                        run_id,
                        user_id,
                        config_id,
                        int(config_version),
                        json.dumps(request_payload, ensure_ascii=False),
                        json.dumps(summary, ensure_ascii=False),
                        datetime.now(UTC),
                    ),
                )

                for idx, rec in enumerate(recommendations, start=1):
                    cur.execute(
                        """
                        INSERT INTO recommendation_items
                        (run_id, rank_position, article_id, score, source, features_json, contributions_json, explanation)
                        VALUES (%s::uuid, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                        """,
                        (
                            run_id,
                            idx,
                            rec.get("article_id", ""),
                            float(rec.get("score", 0.0)),
                            rec.get("source", "unknown"),
                            json.dumps(rec.get("features", {}), ensure_ascii=False),
                            json.dumps(rec.get("feature_contributions", {}), ensure_ascii=False),
                            rec.get("explanation", ""),
                        ),
                    )

        return run_id

    def list_runs(self, limit: int = 20, offset: int = 0) -> List[Dict]:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id::text, user_id, config_id, config_version, summary_json::text, created_at
                    FROM recommendation_runs
                    ORDER BY created_at DESC
                    LIMIT %s
                    OFFSET %s
                    """,
                    (int(limit), int(offset)),
                )
                rows = cur.fetchall()

        return [
            {
                "run_id": row[0],
                "user_id": row[1],
                "config_id": row[2],
                "config_version": int(row[3]),
                "summary": json.loads(row[4]),
                "created_at": row[5].strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        ]

    def list_runs_with_request(
        self,
        limit: int = 100,
        offset: int = 0,
        days: Optional[int] = None,
    ) -> List[Dict]:
        clauses = []
        params: List = []
        if days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=max(1, int(days)))
            clauses.append("created_at >= %s")
            params.append(cutoff)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT run_id::text, user_id, config_id, config_version, request_json::text, summary_json::text, created_at
                    FROM recommendation_runs
                    {where}
                    ORDER BY created_at DESC
                    LIMIT %s
                    OFFSET %s
                    """,
                    (*params, int(limit), int(offset)),
                )
                rows = cur.fetchall()

        return [
            {
                "run_id": row[0],
                "user_id": row[1],
                "config_id": row[2],
                "config_version": int(row[3]),
                "request": json.loads(row[4] or "{}"),
                "summary": json.loads(row[5] or "{}"),
                "created_at": row[6].strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        ]

    def get_run(self, run_id: str) -> Optional[Dict]:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id::text, user_id, config_id, config_version, request_json::text, summary_json::text, created_at
                    FROM recommendation_runs
                    WHERE run_id = %s::uuid
                    """,
                    (run_id,),
                )
                run = cur.fetchone()
                if not run:
                    return None

                cur.execute(
                    """
                    SELECT rank_position, article_id, score, source, features_json::text, contributions_json::text, explanation
                    FROM recommendation_items
                    WHERE run_id = %s::uuid
                    ORDER BY rank_position ASC
                    """,
                    (run_id,),
                )
                items = cur.fetchall()

        return {
            "run_id": run[0],
            "user_id": run[1],
            "config_id": run[2],
            "config_version": int(run[3]),
            "request": json.loads(run[4]),
            "summary": json.loads(run[5]),
            "created_at": run[6].strftime("%Y-%m-%d %H:%M:%S"),
            "items": [
                {
                    "rank": int(item[0]),
                    "article_id": item[1],
                    "score": float(item[2]),
                    "source": item[3],
                    "features": json.loads(item[4] or "{}"),
                    "feature_contributions": json.loads(item[5] or "{}"),
                    "explanation": item[6],
                }
                for item in items
            ],
        }

    def sync_sources(self, sources: List[str]) -> None:
        unique_sources = sorted({s for s in sources if s})
        if not unique_sources:
            return

        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                for source in unique_sources:
                    cur.execute(
                        """
                        INSERT INTO source_settings (source, enabled, default_weight, updated_at)
                        VALUES (%s, TRUE, 1.0, %s)
                        ON CONFLICT (source) DO NOTHING
                        """,
                        (source, datetime.now(UTC)),
                    )

    def list_source_settings(self) -> Dict[str, Dict]:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT source, enabled, default_weight, updated_at
                    FROM source_settings
                    ORDER BY source ASC
                    """
                )
                rows = cur.fetchall()

        return {
            row[0]: {
                "enabled": bool(row[1]),
                "default_weight": float(row[2]),
                "updated_at": row[3].strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        }

    def set_source_setting(self, source: str, enabled: bool, default_weight: float) -> None:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO source_settings (source, enabled, default_weight, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (source) DO UPDATE SET
                        enabled = excluded.enabled,
                        default_weight = excluded.default_weight,
                        updated_at = excluded.updated_at
                    """,
                    (source, bool(enabled), float(default_weight), datetime.now(UTC)),
                )

    def list_connectors(self) -> List[Dict]:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT connector_id, name, connector_type, config_json::text, enabled, last_run_at, created_at, updated_at
                    FROM source_connectors
                    ORDER BY created_at DESC
                    """
                )
                rows = cur.fetchall()

        return [
            {
                "connector_id": row[0],
                "name": row[1],
                "connector_type": row[2],
                "config": json.loads(row[3] or "{}"),
                "enabled": bool(row[4]),
                "last_run_at": row[5].strftime("%Y-%m-%d %H:%M:%S") if row[5] else None,
                "created_at": row[6].strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": row[7].strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        ]

    def get_connector(self, connector_id: str) -> Optional[Dict]:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT connector_id, name, connector_type, config_json::text, enabled, last_run_at, created_at, updated_at
                    FROM source_connectors
                    WHERE connector_id = %s
                    """,
                    (connector_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return {
            "connector_id": row[0],
            "name": row[1],
            "connector_type": row[2],
            "config": json.loads(row[3] or "{}"),
            "enabled": bool(row[4]),
            "last_run_at": row[5].strftime("%Y-%m-%d %H:%M:%S") if row[5] else None,
            "created_at": row[6].strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": row[7].strftime("%Y-%m-%d %H:%M:%S"),
        }

    def create_connector(self, name: str, connector_type: str, config: Dict, enabled: bool = True) -> Dict:
        connector_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO source_connectors
                    (connector_id, name, connector_type, config_json, enabled, last_run_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s, NULL, %s, %s)
                    """,
                    (connector_id, name, connector_type, json.dumps(config, ensure_ascii=False), bool(enabled), now, now),
                )
        return self.get_connector(connector_id) or {}

    def update_connector(
        self,
        connector_id: str,
        name: Optional[str] = None,
        connector_type: Optional[str] = None,
        config: Optional[Dict] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[Dict]:
        current = self.get_connector(connector_id)
        if not current:
            return None
        next_name = name if name is not None else current["name"]
        next_type = connector_type if connector_type is not None else current["connector_type"]
        next_config = config if config is not None else current["config"]
        next_enabled = bool(enabled) if enabled is not None else current["enabled"]

        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE source_connectors
                    SET name = %s, connector_type = %s, config_json = %s::jsonb, enabled = %s, updated_at = %s
                    WHERE connector_id = %s
                    """,
                    (
                        next_name,
                        next_type,
                        json.dumps(next_config, ensure_ascii=False),
                        bool(next_enabled),
                        datetime.now(UTC),
                        connector_id,
                    ),
                )
        return self.get_connector(connector_id)

    def delete_connector(self, connector_id: str) -> bool:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM source_connectors WHERE connector_id = %s", (connector_id,))
                return cur.rowcount > 0

    def mark_connector_sync(self, connector_id: str) -> Optional[Dict]:
        now = datetime.now(UTC)
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE source_connectors
                    SET last_run_at = %s, updated_at = %s
                    WHERE connector_id = %s
                    """,
                    (now, now, connector_id),
                )
                if cur.rowcount == 0:
                    return None
        return self.get_connector(connector_id)

    def start_connector_run(self, connector_id: str, trigger: str = "manual") -> str:
        run_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO connector_sync_runs
                    (run_id, connector_id, trigger, status, attempted, ingested, skipped_existing, error_count, errors_json, started_at, finished_at, created_at)
                    VALUES (%s::uuid, %s, %s, %s, 0, 0, 0, 0, '[]'::jsonb, %s, NULL, %s)
                    """,
                    (run_id, connector_id, trigger, "running", now, now),
                )
        return run_id

    def finish_connector_run(
        self,
        run_id: str,
        status: str,
        attempted: int = 0,
        ingested: int = 0,
        skipped_existing: int = 0,
        errors: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        errors_list = errors or []
        now = datetime.now(UTC)
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE connector_sync_runs
                    SET status = %s,
                        attempted = %s,
                        ingested = %s,
                        skipped_existing = %s,
                        error_count = %s,
                        errors_json = %s::jsonb,
                        finished_at = %s
                    WHERE run_id = %s::uuid
                    """,
                    (
                        status,
                        int(attempted),
                        int(ingested),
                        int(skipped_existing),
                        len(errors_list),
                        json.dumps(errors_list, ensure_ascii=False),
                        now,
                        run_id,
                    ),
                )
                if cur.rowcount == 0:
                    return None
        return self.get_connector_run(run_id)

    def get_connector_run(self, run_id: str) -> Optional[Dict]:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id::text, connector_id, trigger, status, attempted, ingested, skipped_existing, error_count, errors_json::text, started_at, finished_at, created_at
                    FROM connector_sync_runs
                    WHERE run_id = %s::uuid
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return {
            "run_id": row[0],
            "connector_id": row[1],
            "trigger": row[2],
            "status": row[3],
            "attempted": int(row[4]),
            "ingested": int(row[5]),
            "skipped_existing": int(row[6]),
            "error_count": int(row[7]),
            "errors": json.loads(row[8] or "[]"),
            "started_at": row[9].strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": row[10].strftime("%Y-%m-%d %H:%M:%S") if row[10] else None,
            "created_at": row[11].strftime("%Y-%m-%d %H:%M:%S"),
        }

    def list_connector_runs(self, connector_id: str, limit: int = 20) -> List[Dict]:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id::text, connector_id, trigger, status, attempted, ingested, skipped_existing, error_count, errors_json::text, started_at, finished_at, created_at
                    FROM connector_sync_runs
                    WHERE connector_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (connector_id, int(limit)),
                )
                rows = cur.fetchall()
        return [
            {
                "run_id": row[0],
                "connector_id": row[1],
                "trigger": row[2],
                "status": row[3],
                "attempted": int(row[4]),
                "ingested": int(row[5]),
                "skipped_existing": int(row[6]),
                "error_count": int(row[7]),
                "errors": json.loads(row[8] or "[]"),
                "started_at": row[9].strftime("%Y-%m-%d %H:%M:%S"),
                "finished_at": row[10].strftime("%Y-%m-%d %H:%M:%S") if row[10] else None,
                "created_at": row[11].strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        ]

    def list_scenarios(self, include_disabled: bool = True) -> List[Dict]:
        query = """
            SELECT scenario_id, name, description, enabled, rule_set_json::text, metadata_json::text, created_at, updated_at
            FROM recommendation_scenarios
        """
        params: tuple = ()
        if not include_disabled:
            query += " WHERE enabled = TRUE"
        query += " ORDER BY name ASC"
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return [
            {
                "scenario_id": row[0],
                "name": row[1],
                "description": row[2],
                "enabled": bool(row[3]),
                "rule_set": json.loads(row[4] or "{}"),
                "metadata": json.loads(row[5] or "{}"),
                "created_at": row[6].strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": row[7].strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        ]

    def get_scenario(self, scenario_id: str) -> Optional[Dict]:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT scenario_id, name, description, enabled, rule_set_json::text, metadata_json::text, created_at, updated_at
                    FROM recommendation_scenarios
                    WHERE scenario_id = %s
                    """,
                    (scenario_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return {
            "scenario_id": row[0],
            "name": row[1],
            "description": row[2],
            "enabled": bool(row[3]),
            "rule_set": json.loads(row[4] or "{}"),
            "metadata": json.loads(row[5] or "{}"),
            "created_at": row[6].strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": row[7].strftime("%Y-%m-%d %H:%M:%S"),
        }

    def upsert_scenario(
        self,
        scenario_id: str,
        name: str,
        rule_set: Dict,
        description: str = "",
        enabled: bool = True,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        now = datetime.now(UTC)
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO recommendation_scenarios
                    (scenario_id, name, description, enabled, rule_set_json, metadata_json, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                    ON CONFLICT (scenario_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        enabled = EXCLUDED.enabled,
                        rule_set_json = EXCLUDED.rule_set_json,
                        metadata_json = EXCLUDED.metadata_json,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        scenario_id,
                        name,
                        description or "",
                        bool(enabled),
                        json.dumps(rule_set or {}, ensure_ascii=False),
                        json.dumps(metadata or {}, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
        return self.get_scenario(scenario_id) or {}

    def delete_scenario(self, scenario_id: str) -> bool:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM recommendation_scenarios WHERE scenario_id = %s", (scenario_id,))
                return cur.rowcount > 0

    def record_events(self, events: List[Dict]) -> int:
        if not events:
            return 0
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                for event in events:
                    cur.execute(
                        """
                        INSERT INTO recommendation_events
                        (event_id, event_type, run_id, article_id, scenario_id, user_id, external_user_id, rank_position, event_value, metadata_json, created_at)
                        VALUES (%s::uuid, %s, %s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                        """,
                        (
                            str(uuid.uuid4()),
                            event.get("event_type"),
                            event.get("run_id"),
                            event.get("article_id"),
                            event.get("scenario_id"),
                            event.get("user_id") or "anonymous",
                            event.get("external_user_id"),
                            event.get("rank_position"),
                            float(event.get("event_value", 1.0)),
                            json.dumps(event.get("metadata", {}), ensure_ascii=False),
                            datetime.strptime(event["created_at"], "%Y-%m-%d %H:%M:%S")
                            if event.get("created_at")
                            else datetime.now(UTC),
                        ),
                    )
        return len(events)

    def list_events(
        self,
        limit: int = 100,
        offset: int = 0,
        scenario_id: Optional[str] = None,
        event_type: Optional[str] = None,
        days: Optional[int] = None,
    ) -> List[Dict]:
        clauses = []
        params: List = []
        if scenario_id is not None:
            clauses.append("scenario_id = %s")
            params.append(scenario_id)
        if event_type is not None:
            clauses.append("event_type = %s")
            params.append(event_type)
        if days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=max(1, int(days)))
            clauses.append("created_at >= %s")
            params.append(cutoff)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT event_id::text, event_type, run_id::text, article_id, scenario_id, user_id, external_user_id, rank_position, event_value, metadata_json::text, created_at
                    FROM recommendation_events
                    {where}
                    ORDER BY created_at DESC
                    LIMIT %s
                    OFFSET %s
                    """,
                    (*params, int(limit), int(offset)),
                )
                rows = cur.fetchall()
        return [
            {
                "event_id": row[0],
                "event_type": row[1],
                "run_id": row[2],
                "article_id": row[3],
                "scenario_id": row[4],
                "user_id": row[5],
                "external_user_id": row[6],
                "rank_position": int(row[7]) if row[7] is not None else None,
                "event_value": float(row[8]),
                "metadata": json.loads(row[9] or "{}"),
                "created_at": row[10].strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        ]

    def compute_scenario_metrics(self, days: int = 30, top_articles: int = 5) -> Dict:
        cutoff = datetime.now(UTC) - timedelta(days=max(1, int(days)))
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT scenario_id, article_id, event_type
                    FROM recommendation_events
                    WHERE created_at >= %s
                    """,
                    (cutoff,),
                )
                rows = cur.fetchall()

        scenarios = {entry["scenario_id"]: entry for entry in self.list_scenarios(include_disabled=True)}
        bucketed: Dict[str, Dict] = {}
        for row in rows:
            key = row[0] or "default"
            bucket = bucketed.setdefault(
                key,
                {
                    "scenario_id": key,
                    "name": scenarios.get(key, {}).get("name", "Default"),
                    "enabled": scenarios.get(key, {}).get("enabled", True),
                    "impressions": 0,
                    "clicks": 0,
                    "conversions": 0,
                    "article_stats": {},
                },
            )
            event_type = row[2]
            article_id = row[1] or "unknown"
            article_bucket = bucket["article_stats"].setdefault(
                article_id,
                {"article_id": article_id, "impressions": 0, "clicks": 0, "conversions": 0},
            )
            if event_type == "impression":
                bucket["impressions"] += 1
                article_bucket["impressions"] += 1
            elif event_type == "click":
                bucket["clicks"] += 1
                article_bucket["clicks"] += 1
            elif event_type == "conversion":
                bucket["conversions"] += 1
                article_bucket["conversions"] += 1

        scenarios_out = []
        totals = {"impressions": 0, "clicks": 0, "conversions": 0}
        for item in bucketed.values():
            impressions = item["impressions"]
            clicks = item["clicks"]
            conversions = item["conversions"]
            totals["impressions"] += impressions
            totals["clicks"] += clicks
            totals["conversions"] += conversions
            top = sorted(
                item["article_stats"].values(),
                key=lambda x: (x["clicks"], x["impressions"], x["conversions"]),
                reverse=True,
            )[: max(1, int(top_articles))]
            scenarios_out.append(
                {
                    "scenario_id": item["scenario_id"],
                    "name": item["name"],
                    "enabled": item["enabled"],
                    "impressions": impressions,
                    "clicks": clicks,
                    "conversions": conversions,
                    "ctr": round((clicks / impressions), 4) if impressions else 0.0,
                    "conversion_rate": round((conversions / clicks), 4) if clicks else 0.0,
                    "top_articles": top,
                }
            )

        return {
            "window_days": max(1, int(days)),
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            "scenarios": sorted(scenarios_out, key=lambda x: x["impressions"], reverse=True),
            "totals": {
                "impressions": totals["impressions"],
                "clicks": totals["clicks"],
                "conversions": totals["conversions"],
                "ctr": round((totals["clicks"] / totals["impressions"]), 4) if totals["impressions"] else 0.0,
                "conversion_rate": round((totals["conversions"] / totals["clicks"]), 4) if totals["clicks"] else 0.0,
            },
        }

    def get_idempotency_record(self, endpoint: str, key: str, max_age_hours: int = 24) -> Optional[Dict]:
        cutoff = datetime.now(UTC) - timedelta(hours=max(1, int(max_age_hours)))
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT endpoint, key, status_code, response_json::text, created_at
                    FROM api_idempotency_keys
                    WHERE endpoint = %s AND key = %s AND created_at >= %s
                    """,
                    (endpoint, key, cutoff),
                )
                row = cur.fetchone()
        if not row:
            return None
        return {
            "endpoint": row[0],
            "key": row[1],
            "status_code": int(row[2]),
            "response": json.loads(row[3] or "{}"),
            "created_at": row[4].strftime("%Y-%m-%d %H:%M:%S"),
        }

    def save_idempotency_record(
        self,
        endpoint: str,
        key: str,
        status_code: int,
        response_payload: Dict,
    ) -> None:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO api_idempotency_keys (endpoint, key, status_code, response_json, created_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (endpoint, key) DO UPDATE SET
                        status_code = EXCLUDED.status_code,
                        response_json = EXCLUDED.response_json,
                        created_at = EXCLUDED.created_at
                    """,
                    (
                        endpoint,
                        key,
                        int(status_code),
                        json.dumps(response_payload, ensure_ascii=False),
                        datetime.now(UTC),
                    ),
                )

    def record_audit_event(
        self,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_events
                    (event_id, actor_id, action, resource_type, resource_id, metadata_json, created_at)
                    VALUES (%s::uuid, %s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        event_id,
                        actor_id or "unknown",
                        action,
                        resource_type,
                        resource_id,
                        json.dumps(metadata or {}, ensure_ascii=False),
                        datetime.now(UTC),
                    ),
                )
        return event_id

    def list_audit_events(
        self,
        limit: int = 100,
        offset: int = 0,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> List[Dict]:
        clauses = []
        params: List = []
        if actor_id:
            clauses.append("actor_id = %s")
            params.append(actor_id)
        if resource_type:
            clauses.append("resource_type = %s")
            params.append(resource_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT event_id::text, actor_id, action, resource_type, resource_id, metadata_json::text, created_at
                    FROM audit_events
                    {where}
                    ORDER BY created_at DESC
                    LIMIT %s
                    OFFSET %s
                    """,
                    (*params, int(limit), int(offset)),
                )
                rows = cur.fetchall()
        return [
            {
                "event_id": row[0],
                "actor_id": row[1],
                "action": row[2],
                "resource_type": row[3],
                "resource_id": row[4],
                "metadata": json.loads(row[5] or "{}"),
                "created_at": row[6].strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        ]

    def purge_idempotency_records(self, older_than_hours: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=max(0, int(older_than_hours)))
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM api_idempotency_keys WHERE created_at <= %s",
                    (cutoff,),
                )
                return int(cur.rowcount or 0)

    def purge_audit_events(self, older_than_days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=max(0, int(older_than_days)))
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM audit_events WHERE created_at <= %s",
                    (cutoff,),
                )
                return int(cur.rowcount or 0)

    def get_alert_thresholds(self) -> Dict:
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT thresholds_json::text
                    FROM alert_thresholds
                    WHERE threshold_id = 'global'
                    """,
                )
                row = cur.fetchone()
        if not row:
            return dict(self.DEFAULT_ALERT_THRESHOLDS)
        thresholds = json.loads(row[0] or "{}")
        merged = dict(self.DEFAULT_ALERT_THRESHOLDS)
        merged.update({k: float(v) for k, v in thresholds.items()})
        return merged

    def upsert_alert_thresholds(self, thresholds: Dict) -> Dict:
        merged = dict(self.get_alert_thresholds())
        merged.update({str(k): float(v) for k, v in (thresholds or {}).items()})
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO alert_thresholds (threshold_id, thresholds_json, updated_at)
                    VALUES ('global', %s::jsonb, %s)
                    ON CONFLICT (threshold_id) DO UPDATE SET
                        thresholds_json = EXCLUDED.thresholds_json,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (json.dumps(merged, ensure_ascii=False), datetime.now(UTC)),
                )
        return merged

    def upsert_alert_incident(
        self,
        metric: str,
        current_value: Optional[float],
        threshold_value: Optional[float],
        details: Optional[Dict] = None,
    ) -> Dict:
        now = datetime.now(UTC)
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT incident_id::text, occurrences
                    FROM alert_incidents
                    WHERE metric = %s AND status = 'open'
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (metric,),
                )
                row = cur.fetchone()
                if row:
                    incident_id = row[0]
                    cur.execute(
                        """
                        UPDATE alert_incidents
                        SET current_value = %s, threshold_value = %s, details_json = %s::jsonb, occurrences = %s,
                            last_seen_at = %s, updated_at = %s
                        WHERE incident_id = %s::uuid
                        """,
                        (
                            float(current_value) if current_value is not None else None,
                            float(threshold_value) if threshold_value is not None else None,
                            json.dumps(details or {}, ensure_ascii=False),
                            int(row[1]) + 1,
                            now,
                            now,
                            incident_id,
                        ),
                    )
                else:
                    incident_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO alert_incidents
                        (incident_id, metric, status, current_value, threshold_value, details_json, occurrences, first_seen_at, last_seen_at, resolved_at, resolved_by, resolution_note, created_at, updated_at)
                        VALUES (%s::uuid, %s, 'open', %s, %s, %s::jsonb, 1, %s, %s, NULL, NULL, NULL, %s, %s)
                        """,
                        (
                            incident_id,
                            metric,
                            float(current_value) if current_value is not None else None,
                            float(threshold_value) if threshold_value is not None else None,
                            json.dumps(details or {}, ensure_ascii=False),
                            now,
                            now,
                            now,
                            now,
                        ),
                    )

                cur.execute(
                    """
                    SELECT incident_id::text, metric, status, current_value, threshold_value, details_json::text, occurrences,
                           first_seen_at, last_seen_at, resolved_at, resolved_by, resolution_note, created_at, updated_at
                    FROM alert_incidents
                    WHERE incident_id = %s::uuid
                    """,
                    (incident_id,),
                )
                incident = cur.fetchone()
        return {
            "incident_id": incident[0],
            "metric": incident[1],
            "status": incident[2],
            "current_value": float(incident[3]) if incident[3] is not None else None,
            "threshold_value": float(incident[4]) if incident[4] is not None else None,
            "details": json.loads(incident[5] or "{}"),
            "occurrences": int(incident[6]),
            "first_seen_at": incident[7].strftime("%Y-%m-%d %H:%M:%S"),
            "last_seen_at": incident[8].strftime("%Y-%m-%d %H:%M:%S"),
            "resolved_at": incident[9].strftime("%Y-%m-%d %H:%M:%S") if incident[9] else None,
            "resolved_by": incident[10],
            "resolution_note": incident[11],
            "created_at": incident[12].strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": incident[13].strftime("%Y-%m-%d %H:%M:%S"),
        }

    def list_alert_incidents(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
        metric: Optional[str] = None,
    ) -> List[Dict]:
        clauses = []
        params: List = []
        if status:
            clauses.append("status = %s")
            params.append(status)
        if metric:
            clauses.append("metric = %s")
            params.append(metric)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT incident_id::text, metric, status, current_value, threshold_value, details_json::text, occurrences,
                           first_seen_at, last_seen_at, resolved_at, resolved_by, resolution_note, created_at, updated_at
                    FROM alert_incidents
                    {where}
                    ORDER BY updated_at DESC
                    LIMIT %s
                    OFFSET %s
                    """,
                    (*params, int(limit), int(offset)),
                )
                rows = cur.fetchall()
        return [
            {
                "incident_id": row[0],
                "metric": row[1],
                "status": row[2],
                "current_value": float(row[3]) if row[3] is not None else None,
                "threshold_value": float(row[4]) if row[4] is not None else None,
                "details": json.loads(row[5] or "{}"),
                "occurrences": int(row[6]),
                "first_seen_at": row[7].strftime("%Y-%m-%d %H:%M:%S"),
                "last_seen_at": row[8].strftime("%Y-%m-%d %H:%M:%S"),
                "resolved_at": row[9].strftime("%Y-%m-%d %H:%M:%S") if row[9] else None,
                "resolved_by": row[10],
                "resolution_note": row[11],
                "created_at": row[12].strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": row[13].strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        ]

    def resolve_alert_incident(self, incident_id: str, resolved_by: str, note: str = "") -> bool:
        now = datetime.now(UTC)
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE alert_incidents
                    SET status = 'resolved', resolved_at = %s, resolved_by = %s, resolution_note = %s, updated_at = %s
                    WHERE incident_id = %s::uuid AND status = 'open'
                    """,
                    (now, resolved_by, note, now, incident_id),
                )
                return (cur.rowcount or 0) > 0

    def resolve_open_alert_incidents(self, metric: str, resolved_by: str, note: str = "") -> int:
        now = datetime.now(UTC)
        with self._managed_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE alert_incidents
                    SET status = 'resolved', resolved_at = %s, resolved_by = %s, resolution_note = %s, updated_at = %s
                    WHERE metric = %s AND status = 'open'
                    """,
                    (now, resolved_by, note, now, metric),
                )
                return int(cur.rowcount or 0)


class RecommenderStore(BaseRecommenderStore):
    """Factory-wrapper that instantiates backend-specific store.

    Env vars:
    - RECOMMENDER_DB_BACKEND: sqlite|postgres (default sqlite)
    - DATABASE_URL: required for postgres
    - RECOMMENDER_SQLITE_PATH: override sqlite db path
    """

    def __new__(cls, db_path: str = "data/recommender.db"):
        backend = os.getenv("RECOMMENDER_DB_BACKEND", "sqlite").strip().lower()
        if backend == "postgres":
            database_url = os.getenv("DATABASE_URL", "").strip()
            return PostgresRecommenderStore(database_url=database_url)

        sqlite_path = os.getenv("RECOMMENDER_SQLITE_PATH", db_path)
        return SQLiteRecommenderStore(db_path=sqlite_path)
