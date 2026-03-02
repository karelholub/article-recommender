import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse
import re

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RankingConfig:
    config_id: str
    weights: Dict[str, float]
    time_decay_days: int
    source_weights: Dict[str, float]
    max_per_source: Optional[int] = None
    max_per_topic: Optional[int] = None
    max_per_section: Optional[int] = None
    hard_max_age_days: Optional[int] = None
    min_freshness: Optional[float] = None
    recent_boost_days: int = 0
    recent_boost_factor: float = 1.0
    dedup_by_title: bool = False
    dedup_by_url: bool = False


PRESET_RANKING_CONFIGS: Dict[str, RankingConfig] = {
    "balanced": RankingConfig(
        config_id="balanced",
        weights={"semantic": 0.45, "freshness": 0.2, "topic": 0.25, "source": 0.1},
        time_decay_days=30,
        source_weights={},
        max_per_source=2,
        max_per_topic=3,
        max_per_section=3,
        hard_max_age_days=None,
        min_freshness=None,
        recent_boost_days=2,
        recent_boost_factor=1.08,
        dedup_by_title=True,
        dedup_by_url=True,
    ),
    "semantic_heavy": RankingConfig(
        config_id="semantic_heavy",
        weights={"semantic": 0.65, "freshness": 0.1, "topic": 0.2, "source": 0.05},
        time_decay_days=45,
        source_weights={},
        max_per_source=3,
        max_per_topic=4,
        max_per_section=4,
        recent_boost_days=1,
        recent_boost_factor=1.03,
        dedup_by_title=True,
        dedup_by_url=True,
    ),
    "freshness_heavy": RankingConfig(
        config_id="freshness_heavy",
        weights={"semantic": 0.3, "freshness": 0.45, "topic": 0.15, "source": 0.1},
        time_decay_days=14,
        source_weights={},
        max_per_source=2,
        max_per_topic=3,
        max_per_section=3,
        hard_max_age_days=7,
        min_freshness=0.35,
        recent_boost_days=3,
        recent_boost_factor=1.12,
        dedup_by_title=True,
        dedup_by_url=True,
    ),
    "topic_heavy": RankingConfig(
        config_id="topic_heavy",
        weights={"semantic": 0.3, "freshness": 0.15, "topic": 0.45, "source": 0.1},
        time_decay_days=30,
        source_weights={},
        max_per_source=2,
        max_per_topic=2,
        max_per_section=3,
        recent_boost_days=2,
        recent_boost_factor=1.05,
        dedup_by_title=True,
        dedup_by_url=True,
    ),
}


class BaseRecommender(ABC):
    """Base class for article recommenders"""

    def __init__(
        self,
        embed_file: str = "embeddings/article_vectors.json",
        profile_file: str = "profiles/user_profiles.json",
        output_file: str = "recommendations.json",
        cache_size: int = 128,
    ):
        self.embed_file = Path(embed_file)
        self.profile_file = Path(profile_file)
        self.output_file = Path(output_file)

        self._load_data()
        self._initialize_caches(cache_size)

    def _load_data(self):
        """Load embeddings and user profiles"""
        try:
            with open(self.embed_file, encoding="utf-8") as f:
                self.article_vectors = json.load(f)
            with open(self.profile_file, encoding="utf-8") as f:
                self.user_profiles = json.load(f)

            valid_articles = {}
            for aid, data in self.article_vectors.items():
                if "vector" in data and isinstance(data["vector"], list) and len(data["vector"]) > 0:
                    valid_articles[aid] = data

            self.article_vectors = valid_articles
            self.article_ids = list(self.article_vectors.keys())

            if not self.article_ids:
                logger.error("No valid articles found with vectors")
                raise ValueError("No valid articles found with vectors")

            expected_length = len(self.article_vectors[self.article_ids[0]]["vector"])
            logger.info(f"Expected vector length: {expected_length}")

            vectors = []
            for aid in self.article_ids:
                vector = self.article_vectors[aid]["vector"]
                if len(vector) != expected_length:
                    logger.warning(
                        f"Vector length mismatch for article {aid}: {len(vector)} vs {expected_length}"
                    )
                    if len(vector) < expected_length:
                        vector = vector + [0] * (expected_length - len(vector))
                    else:
                        vector = vector[:expected_length]
                    # Persist normalized dimensionality back into canonical in-memory payload.
                    self.article_vectors[aid]["vector"] = vector
                vectors.append(vector)

            self.vector_array = np.array(vectors, dtype=np.float32)
            logger.info(f"Loaded {len(self.article_vectors)} valid article vectors")
        except Exception as e:
            logger.error(f"Error loading data: {str(e)}")
            raise

    def _initialize_caches(self, cache_size: int):
        self._get_article_vector = lru_cache(maxsize=cache_size)(self._get_article_vector)

    def _get_article_vector(self, article_id: str) -> np.ndarray:
        return np.array(self.article_vectors[article_id]["vector"])

    @abstractmethod
    def recommend_for_user(
        self,
        user_id: str,
        article_vectors: Dict[str, Dict],
        user_reads: List[str],
        top_n: int = 5,
    ) -> List[Dict[str, float]]:
        pass

    def generate_all_recommendations(self, top_n: int = 5):
        all_recommendations = {}
        start_time = time.time()

        for user_id, read_articles in self.user_profiles.items():
            try:
                recs = self.recommend_for_user(
                    user_id,
                    self.article_vectors,
                    read_articles,
                    top_n=top_n,
                )
                all_recommendations[user_id] = recs
            except Exception as e:
                logger.error(f"Error generating recommendations for user {user_id}: {str(e)}")

        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(all_recommendations, f, indent=2, ensure_ascii=False)

        duration = time.time() - start_time
        logger.info(
            f"Generated recommendations for {len(all_recommendations)} users in {duration:.2f} seconds"
        )
        logger.info(f"Recommendations written to {self.output_file}")


class SimpleRecommender(BaseRecommender):
    """Simple recommender based on cosine similarity"""

    def recommend_for_user(
        self,
        user_id: str,
        article_vectors: Dict[str, Dict],
        user_reads: List[str],
        top_n: int = 5,
    ) -> List[Dict[str, float]]:
        if not user_reads:
            return []

        user_vecs = []
        for aid in user_reads:
            if aid in article_vectors:
                vector = self._get_article_vector(aid)
                if vector is not None:
                    user_vecs.append(vector)

        if not user_vecs:
            return []

        user_profile_vector = np.mean(user_vecs, axis=0)

        candidate_ids = []
        candidate_vectors = []
        for aid in self.article_ids:
            if aid not in user_reads:
                candidate_ids.append(aid)
                candidate_vectors.append(self._get_article_vector(aid))

        if not candidate_ids:
            return []

        candidate_vectors = np.array(candidate_vectors)
        similarities = cosine_similarity([user_profile_vector], candidate_vectors)[0]

        recommendations = []
        for aid, score in zip(candidate_ids, similarities):
            article_data = article_vectors[aid]
            recommendations.append(
                {
                    "article_id": aid,
                    "title": article_data["metadata"].get("title", ""),
                    "url": article_data["metadata"].get("url", ""),
                    "score": round(float(score), 4),
                }
            )

        recommendations.sort(key=lambda x: x["score"], reverse=True)
        return recommendations[:top_n]


class AdvancedRecommender(BaseRecommender):
    """Configurable recommender with explainable feature contributions"""

    def __init__(
        self,
        embed_file: str = "embeddings/article_vectors.json",
        profile_file: str = "profiles/user_profiles.json",
        output_file: str = "recommendations.json",
        diversity_weight: float = 0.3,
        time_decay_days: int = 30,
        cluster_weight: float = 0.2,
        cache_size: int = 128,
    ):
        super().__init__(embed_file, profile_file, output_file, cache_size)
        self.diversity_weight = diversity_weight
        self.time_decay_days = time_decay_days
        self.cluster_weight = cluster_weight

        semantic_weight = max(0.0, 1.0 - diversity_weight - cluster_weight)
        self.legacy_default_config = RankingConfig(
            config_id="legacy_compatible",
            weights={
                "semantic": semantic_weight,
                "freshness": max(0.0, diversity_weight),
                "topic": max(0.0, cluster_weight),
                "source": 0.0,
            },
            time_decay_days=max(1, time_decay_days),
            source_weights={},
            max_per_source=None,
            max_per_topic=None,
            max_per_section=None,
            hard_max_age_days=None,
            min_freshness=None,
            recent_boost_days=0,
            recent_boost_factor=1.0,
            dedup_by_title=False,
            dedup_by_url=False,
        )

    @staticmethod
    def _validate_weights(weights: Dict[str, float]) -> None:
        required = {"semantic", "freshness", "topic", "source"}
        if set(weights.keys()) != required:
            raise ValueError(f"Weights must include exactly {required}")

        total = sum(weights.values())
        if not np.isclose(total, 1.0):
            raise ValueError(f"Weights must sum to 1.0 (got {total:.4f})")

        for key, value in weights.items():
            if value < 0 or value > 1:
                raise ValueError(f"Weight {key} must be between 0 and 1")

    @staticmethod
    def extract_source(url: str) -> str:
        if not url:
            return "unknown"
        parsed = urlparse(url)
        return parsed.netloc or "unknown"

    def get_available_sources(self) -> List[Dict[str, int]]:
        counts: Dict[str, int] = {}
        for article_data in self.article_vectors.values():
            source = self.extract_source(article_data.get("metadata", {}).get("url", ""))
            counts[source] = counts.get(source, 0) + 1

        return [
            {"source": source, "article_count": count}
            for source, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def get_ranking_configs(self) -> Dict[str, Dict]:
        configs = {name: {
            "config_id": cfg.config_id,
            "weights": cfg.weights,
            "time_decay_days": cfg.time_decay_days,
            "source_weights": cfg.source_weights,
            "max_per_source": cfg.max_per_source,
            "max_per_topic": cfg.max_per_topic,
            "max_per_section": cfg.max_per_section,
            "hard_max_age_days": cfg.hard_max_age_days,
            "min_freshness": cfg.min_freshness,
            "recent_boost_days": cfg.recent_boost_days,
            "recent_boost_factor": cfg.recent_boost_factor,
            "dedup_by_title": cfg.dedup_by_title,
            "dedup_by_url": cfg.dedup_by_url,
        } for name, cfg in PRESET_RANKING_CONFIGS.items()}

        configs[self.legacy_default_config.config_id] = {
            "config_id": self.legacy_default_config.config_id,
            "weights": self.legacy_default_config.weights,
            "time_decay_days": self.legacy_default_config.time_decay_days,
            "source_weights": self.legacy_default_config.source_weights,
            "max_per_source": self.legacy_default_config.max_per_source,
            "max_per_topic": self.legacy_default_config.max_per_topic,
            "max_per_section": self.legacy_default_config.max_per_section,
            "hard_max_age_days": self.legacy_default_config.hard_max_age_days,
            "min_freshness": self.legacy_default_config.min_freshness,
            "recent_boost_days": self.legacy_default_config.recent_boost_days,
            "recent_boost_factor": self.legacy_default_config.recent_boost_factor,
            "dedup_by_title": self.legacy_default_config.dedup_by_title,
            "dedup_by_url": self.legacy_default_config.dedup_by_url,
        }
        return configs

    def _resolve_config(
        self,
        config_id: str = "balanced",
        ranking_config: Optional[Dict] = None,
    ) -> RankingConfig:
        if ranking_config:
            weights = ranking_config.get("weights", {})
            time_decay_days = int(ranking_config.get("time_decay_days", self.time_decay_days))
            source_weights = ranking_config.get("source_weights", {})
            max_per_source = ranking_config.get("max_per_source")
            max_per_topic = ranking_config.get("max_per_topic")
            max_per_section = ranking_config.get("max_per_section")
            hard_max_age_days = ranking_config.get("hard_max_age_days")
            min_freshness = ranking_config.get("min_freshness")
            recent_boost_days = int(ranking_config.get("recent_boost_days", 0))
            recent_boost_factor = float(ranking_config.get("recent_boost_factor", 1.0))
            dedup_by_title = bool(ranking_config.get("dedup_by_title", False))
            dedup_by_url = bool(ranking_config.get("dedup_by_url", False))
            self._validate_weights(weights)
            if time_decay_days <= 0:
                raise ValueError("time_decay_days must be greater than 0")
            for key, raw in (
                ("max_per_source", max_per_source),
                ("max_per_topic", max_per_topic),
                ("max_per_section", max_per_section),
            ):
                if raw is not None and int(raw) < 1:
                    raise ValueError(f"{key} must be >= 1 when provided")
            if hard_max_age_days is not None and int(hard_max_age_days) < 0:
                raise ValueError("hard_max_age_days must be >= 0 when provided")
            if min_freshness is not None:
                min_freshness = float(min_freshness)
                if min_freshness < 0 or min_freshness > 1:
                    raise ValueError("min_freshness must be between 0 and 1")
            if recent_boost_days < 0:
                raise ValueError("recent_boost_days must be >= 0")
            if recent_boost_factor < 0.5 or recent_boost_factor > 5:
                raise ValueError("recent_boost_factor must be between 0.5 and 5")
            return RankingConfig(
                config_id=ranking_config.get("config_id", "custom"),
                weights=weights,
                time_decay_days=time_decay_days,
                source_weights=source_weights,
                max_per_source=(int(max_per_source) if max_per_source is not None else None),
                max_per_topic=(int(max_per_topic) if max_per_topic is not None else None),
                max_per_section=(int(max_per_section) if max_per_section is not None else None),
                hard_max_age_days=(int(hard_max_age_days) if hard_max_age_days is not None else None),
                min_freshness=min_freshness,
                recent_boost_days=recent_boost_days,
                recent_boost_factor=recent_boost_factor,
                dedup_by_title=dedup_by_title,
                dedup_by_url=dedup_by_url,
            )

        if config_id == self.legacy_default_config.config_id:
            return self.legacy_default_config
        if config_id in PRESET_RANKING_CONFIGS:
            return PRESET_RANKING_CONFIGS[config_id]

        raise ValueError(f"Unknown ranking config: {config_id}")

    def _calculate_time_decay(self, article_id: str, time_decay_days: int) -> float:
        try:
            scraped_at = datetime.strptime(
                self.article_vectors[article_id]["metadata"]["scraped_at"],
                "%Y-%m-%d %H:%M:%S",
            )
            days_old = max(0, (datetime.now() - scraped_at).days)
            return float(np.exp(-days_old / max(1, time_decay_days)))
        except (KeyError, ValueError):
            return 1.0

    def _article_age_days(self, article_id: str) -> Optional[int]:
        try:
            scraped_at = datetime.strptime(
                self.article_vectors[article_id]["metadata"]["scraped_at"],
                "%Y-%m-%d %H:%M:%S",
            )
            return max(0, (datetime.now() - scraped_at).days)
        except (KeyError, ValueError):
            return None

    @staticmethod
    def _calculate_cluster_similarity(user_clusters: List[int], article_cluster: int) -> float:
        if not user_clusters:
            return 0.0
        cluster_count = user_clusters.count(article_cluster)
        return cluster_count / len(user_clusters)

    def _calculate_source_score(self, article_id: str, source_weights: Dict[str, float]) -> float:
        url = self.article_vectors.get(article_id, {}).get("metadata", {}).get("url", "")
        source = self.extract_source(url)
        return float(source_weights.get(source, 1.0))

    @staticmethod
    def _compose_explanation(contributions: Dict[str, float], source: str) -> str:
        ordered = sorted(contributions.items(), key=lambda item: item[1], reverse=True)
        top = ordered[:2]
        top_txt = ", ".join(f"{name}={value:.3f}" for name, value in top)
        return f"Top drivers: {top_txt}. Source: {source}."

    @staticmethod
    def _normalize_title_key(title: str) -> str:
        text = re.sub(r"\s+", " ", str(title or "").strip().lower())
        text = re.sub(r"[^a-z0-9 ]+", "", text)
        return text

    @staticmethod
    def _extract_primary_section(article_data: Dict) -> str:
        metadata = article_data.get("metadata", {}) or {}
        for key in ("section", "rubrika", "category"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        categories = metadata.get("categories")
        if isinstance(categories, list) and categories:
            first = str(categories[0]).strip().lower()
            if first:
                return first
        url = str(metadata.get("url", ""))
        parsed = urlparse(url)
        path_parts = [part for part in parsed.path.split("/") if part.strip()]
        return (path_parts[0].strip().lower() if path_parts else "unknown")

    def recommend_for_user(
        self,
        user_id: str,
        article_vectors: Dict[str, Dict],
        user_reads: List[str],
        top_n: int = 5,
        sources: Optional[List[str]] = None,
        config_id: str = "balanced",
        ranking_config: Optional[Dict] = None,
        diagnostics: Optional[Dict[str, List[Dict]]] = None,
    ) -> List[Dict[str, float]]:
        if not user_reads:
            return []

        config = self._resolve_config(config_id=config_id, ranking_config=ranking_config)

        user_vecs = []
        user_clusters = []
        for aid in user_reads:
            if aid in article_vectors:
                vector = self._get_article_vector(aid)
                if vector is not None:
                    user_vecs.append(vector)
                    if "cluster" in article_vectors[aid]:
                        user_clusters.append(article_vectors[aid]["cluster"])

        if not user_vecs:
            return []

        user_profile_vector = np.mean(user_vecs, axis=0)

        source_filter = {s.strip() for s in sources or [] if s and s.strip()}
        candidate_ids = []
        candidate_vectors = []
        candidate_clusters = []

        for aid in self.article_ids:
            if aid in user_reads:
                continue

            source = self.extract_source(article_vectors.get(aid, {}).get("metadata", {}).get("url", ""))
            if source_filter and source not in source_filter:
                continue

            candidate_ids.append(aid)
            candidate_vectors.append(self._get_article_vector(aid))
            candidate_clusters.append(article_vectors.get(aid, {}).get("cluster", -1))

        if not candidate_ids:
            return []

        candidate_vectors = np.array(candidate_vectors)
        semantic_similarities = cosine_similarity([user_profile_vector], candidate_vectors)[0]

        recommendations = []
        excluded = []
        for aid, semantic_sim, cluster in zip(candidate_ids, semantic_similarities, candidate_clusters):
            freshness = self._calculate_time_decay(aid, config.time_decay_days)
            age_days = self._article_age_days(aid)
            if config.hard_max_age_days is not None and age_days is not None and age_days > config.hard_max_age_days:
                excluded.append({"article_id": aid, "reason_code": "hard_max_age_days", "age_days": age_days})
                continue
            if config.min_freshness is not None and freshness < config.min_freshness:
                excluded.append({"article_id": aid, "reason_code": "min_freshness", "freshness": round(float(freshness), 4)})
                continue
            topic = self._calculate_cluster_similarity(user_clusters, cluster)
            source_score = self._calculate_source_score(aid, config.source_weights)
            source = self.extract_source(article_vectors[aid].get("metadata", {}).get("url", ""))

            features = {
                "semantic": float(semantic_sim),
                "freshness": float(freshness),
                "topic": float(topic),
                "source": float(source_score),
            }
            contributions = {
                key: float(features[key] * config.weights[key])
                for key in config.weights.keys()
            }
            final_score = float(sum(contributions.values()))
            if config.recent_boost_days and config.recent_boost_factor > 0 and age_days is not None and age_days <= config.recent_boost_days:
                final_score = float(final_score * config.recent_boost_factor)
                contributions["freshness"] = float(contributions.get("freshness", 0.0) * config.recent_boost_factor)

            article_data = article_vectors[aid]
            recommendations.append(
                {
                    "article_id": aid,
                    "title": article_data["metadata"].get("title", ""),
                    "content": article_data["metadata"].get("content", ""),
                    "url": article_data["metadata"].get("url", ""),
                    "source": source,
                    "score": round(final_score, 4),
                    "similarity_components": {
                        "semantic": round(features["semantic"], 4),
                        "freshness": round(features["freshness"], 4),
                        "topic": round(features["topic"], 4),
                        "source": round(features["source"], 4),
                    },
                    "features": {k: round(v, 4) for k, v in features.items()},
                    "feature_contributions": {k: round(v, 4) for k, v in contributions.items()},
                    "config_id": config.config_id,
                    "age_days": age_days,
                    "topic_cluster": int(cluster) if isinstance(cluster, (int, np.integer)) else cluster,
                    "section": self._extract_primary_section(article_data),
                    "explanation_details": {
                        "schema_version": "v2",
                        "reason_codes": sorted(contributions.keys(), key=lambda key: contributions[key], reverse=True),
                        "feature_values": {k: round(v, 4) for k, v in features.items()},
                        "feature_contributions": {k: round(v, 4) for k, v in contributions.items()},
                        "constraints": {
                            "hard_max_age_days": config.hard_max_age_days,
                            "min_freshness": config.min_freshness,
                            "max_per_source": config.max_per_source,
                            "max_per_topic": config.max_per_topic,
                            "max_per_section": config.max_per_section,
                            "dedup_by_title": config.dedup_by_title,
                            "dedup_by_url": config.dedup_by_url,
                        },
                    },
                    "explanation": self._compose_explanation(contributions, source),
                }
            )

        recommendations.sort(key=lambda x: x["score"], reverse=True)
        source_counts: Dict[str, int] = {}
        topic_counts: Dict[str, int] = {}
        section_counts: Dict[str, int] = {}
        seen_titles: set = set()
        seen_urls: set = set()
        selected: List[Dict[str, float]] = []
        for rec in recommendations:
            source = str(rec.get("source", "unknown"))
            topic = str(rec.get("topic_cluster", "unknown"))
            section = str(rec.get("section", "unknown"))
            title_key = self._normalize_title_key(rec.get("title", ""))
            url_key = str(rec.get("url", "")).strip().lower()

            if config.dedup_by_title and title_key and title_key in seen_titles:
                excluded.append({"article_id": rec.get("article_id"), "reason_code": "dedup_title", "title_key": title_key})
                continue
            if config.dedup_by_url and url_key and url_key in seen_urls:
                excluded.append({"article_id": rec.get("article_id"), "reason_code": "dedup_url", "url": url_key})
                continue
            if config.max_per_source is not None and source_counts.get(source, 0) >= config.max_per_source:
                excluded.append({"article_id": rec.get("article_id"), "reason_code": "cap_source", "source": source})
                continue
            if config.max_per_topic is not None and topic_counts.get(topic, 0) >= config.max_per_topic:
                excluded.append({"article_id": rec.get("article_id"), "reason_code": "cap_topic", "topic": topic})
                continue
            if config.max_per_section is not None and section_counts.get(section, 0) >= config.max_per_section:
                excluded.append({"article_id": rec.get("article_id"), "reason_code": "cap_section", "section": section})
                continue

            source_counts[source] = source_counts.get(source, 0) + 1
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
            section_counts[section] = section_counts.get(section, 0) + 1
            if title_key:
                seen_titles.add(title_key)
            if url_key:
                seen_urls.add(url_key)
            selected.append(rec)
            if len(selected) >= top_n:
                break

        if diagnostics is not None:
            diagnostics["selected"] = [
                {
                    "article_id": item.get("article_id"),
                    "score": item.get("score"),
                    "source": item.get("source"),
                    "topic_cluster": item.get("topic_cluster"),
                    "section": item.get("section"),
                }
                for item in selected
            ]
            diagnostics["excluded"] = excluded[:500]
            diagnostics["counts"] = {
                "candidate_scored": len(recommendations),
                "selected": len(selected),
                "excluded": len(excluded),
            }

        return selected[:top_n]


class RecommenderFactory:
    """Factory for creating recommenders"""

    @staticmethod
    def create_recommender(recommender_type: str = "advanced", **kwargs) -> BaseRecommender:
        if recommender_type.lower() == "simple":
            return SimpleRecommender(**kwargs)
        if recommender_type.lower() == "advanced":
            return AdvancedRecommender(**kwargs)
        raise ValueError(f"Unknown recommender type: {recommender_type}")


if __name__ == "__main__":
    simple_recommender = RecommenderFactory.create_recommender("simple")
    simple_recs = simple_recommender.recommend_for_user(
        "user_1",
        simple_recommender.article_vectors,
        simple_recommender.user_profiles.get("user_1", []),
        top_n=3,
    )
    print("Simple recommendations:")
    for rec in simple_recs:
        print(f"{rec['score']:.3f} -> {rec['title']}")

    advanced_recommender = RecommenderFactory.create_recommender(
        "advanced",
        diversity_weight=0.3,
        time_decay_days=30,
    )
    advanced_recs = advanced_recommender.recommend_for_user(
        "user_1",
        advanced_recommender.article_vectors,
        advanced_recommender.user_profiles.get("user_1", []),
        top_n=3,
    )
    print("\nAdvanced recommendations:")
    for rec in advanced_recs:
        print(
            f"{rec['score']:.3f} (semantic: {rec['similarity_components']['semantic']:.3f}, "
            f"freshness: {rec['similarity_components']['freshness']:.3f}) -> {rec['title']}"
        )
