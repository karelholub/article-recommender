from datetime import datetime
import logging
import os
import traceback
from typing import Dict, Optional, Tuple

from flask import Flask, abort, jsonify, render_template, request

from store import RecommenderStore
from bootstrap_data import ensure_data_files
from connector_pipeline import ConnectorIngestionService
from config.logging_config import setup_logging
from recommend import RecommenderFactory

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

app = Flask(__name__)
store: Optional[RecommenderStore] = None


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


def _load_sources_with_settings() -> Tuple[list, Dict[str, Dict]]:
    if not recommender or not store:
        return [], {}
    sources = recommender.get_available_sources()
    source_names = [entry["source"] for entry in sources]
    store.sync_sources(source_names)
    settings = store.list_source_settings()
    return sources, settings


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
    return render_template("index.html")


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
        return jsonify({"source": source, "enabled": enabled, "default_weight": default_weight})
    except Exception as e:
        logger.error(f"Error updating source setting: {str(e)}")
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

        connector = store.create_connector(
            name=name,
            connector_type=connector_type,
            config=config,
            enabled=enabled,
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
        return jsonify({"deleted": True, "connector_id": connector_id})

    try:
        payload = request.get_json() or {}
        connector_type = payload.get("connector_type")
        if connector_type and connector_type not in {"section_scraper", "rss"}:
            return jsonify({"error": "connector_type must be one of: section_scraper, rss"}), 400

        connector = store.update_connector(
            connector_id=connector_id,
            name=payload.get("name"),
            connector_type=connector_type,
            config=payload.get("config"),
            enabled=payload.get("enabled"),
        )
        if not connector:
            return jsonify({"error": "Connector not found"}), 404
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
            recommender._load_data()
            store.sync_sources([entry["source"] for entry in recommender.get_available_sources()])

        updated = store.mark_connector_sync(connector_id)
        return jsonify(
            {
                "message": "Connector sync executed.",
                "connector": updated,
                "run_id": run_id,
                "run": run,
                "ingestion": ingestion_result.to_dict(),
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


@app.route("/api/connector-runs/<run_id>", methods=["GET"])
def connector_run_detail(run_id):
    if not store:
        return jsonify({"error": "Store unavailable"}), 500

    run = store.get_connector_run(run_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(run)


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
        return jsonify({"config_id": config_id, "version": version})
    except Exception as e:
        logger.error(f"Error updating ranking config: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@app.route("/api/recommendations/query", methods=["POST"])
def query_recommendations():
    if not recommender or not store:
        return jsonify({"error": "Recommender not initialized"}), 500

    try:
        payload = request.get_json() or {}
        user_id = payload.get("user_id", "demo_user")
        user_reads = payload.get("user_reads") or recommender.user_profiles.get(user_id, [])
        top_n = int(payload.get("top_n", 5))
        requested_sources = payload.get("sources") or []
        config_id = payload.get("config_id", "balanced")
        ranking_config = payload.get("ranking_config")
        decision_context = _build_decision_context(requested_sources, config_id, ranking_config)
        effective_config_id = decision_context["effective_config_id"]
        config_version = decision_context["config_version"]
        selected_sources = decision_context["selected_sources"]
        source_defaults = decision_context["source_defaults_applied"]
        effective_ranking_config = decision_context["effective_ranking_config"]

        if selected_sources:
            recs = recommender.recommend_for_user(
                user_id,
                recommender.article_vectors,
                user_reads,
                top_n=top_n,
                sources=selected_sources,
                config_id=effective_config_id,
                ranking_config=effective_ranking_config,
            )
        else:
            recs = []

        run_id = store.persist_recommendation_run(
            user_id=user_id,
            config_id=effective_config_id,
            config_version=config_version,
            request_payload={
                "user_id": user_id,
                "user_reads": user_reads,
                "top_n": top_n,
                "sources": selected_sources,
                "config_id": effective_config_id,
                "effective_ranking_config": effective_ranking_config,
            },
            recommendations=recs,
        )

        return jsonify(
            {
                "run_id": run_id,
                "user_id": user_id,
                "top_n": top_n,
                "sources": selected_sources,
                "config_id": effective_config_id,
                "config_version": config_version,
                "source_defaults_applied": source_defaults,
                "effective_ranking_config": effective_ranking_config,
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
        limit = int(request.args.get("limit", 20))
        runs = store.list_runs(limit=limit)
        return jsonify({"runs": runs, "count": len(runs)})
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
        config_id = payload.get("config_id", "balanced")
        ranking_config = payload.get("ranking_config")
        context = _build_decision_context(requested_sources, config_id, ranking_config)
        return jsonify(context)
    except Exception as e:
        logger.error(f"Error building recommendation context: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


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

        return jsonify(
            {
                "total_articles": len(recommender.article_vectors),
                "cluster_distribution": cluster_counts,
                "freshness_distribution": freshness_counts,
                "cluster_topics": cluster_topics,
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
