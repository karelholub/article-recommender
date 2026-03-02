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


PRESET_RANKING_CONFIGS: Dict[str, RankingConfig] = {
    "balanced": RankingConfig(
        config_id="balanced",
        weights={"semantic": 0.45, "freshness": 0.2, "topic": 0.25, "source": 0.1},
        time_decay_days=30,
        source_weights={},
    ),
    "semantic_heavy": RankingConfig(
        config_id="semantic_heavy",
        weights={"semantic": 0.65, "freshness": 0.1, "topic": 0.2, "source": 0.05},
        time_decay_days=45,
        source_weights={},
    ),
    "freshness_heavy": RankingConfig(
        config_id="freshness_heavy",
        weights={"semantic": 0.3, "freshness": 0.45, "topic": 0.15, "source": 0.1},
        time_decay_days=14,
        source_weights={},
    ),
    "topic_heavy": RankingConfig(
        config_id="topic_heavy",
        weights={"semantic": 0.3, "freshness": 0.15, "topic": 0.45, "source": 0.1},
        time_decay_days=30,
        source_weights={},
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
        } for name, cfg in PRESET_RANKING_CONFIGS.items()}

        configs[self.legacy_default_config.config_id] = {
            "config_id": self.legacy_default_config.config_id,
            "weights": self.legacy_default_config.weights,
            "time_decay_days": self.legacy_default_config.time_decay_days,
            "source_weights": self.legacy_default_config.source_weights,
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
            self._validate_weights(weights)
            if time_decay_days <= 0:
                raise ValueError("time_decay_days must be greater than 0")
            return RankingConfig(
                config_id=ranking_config.get("config_id", "custom"),
                weights=weights,
                time_decay_days=time_decay_days,
                source_weights=source_weights,
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

    def recommend_for_user(
        self,
        user_id: str,
        article_vectors: Dict[str, Dict],
        user_reads: List[str],
        top_n: int = 5,
        sources: Optional[List[str]] = None,
        config_id: str = "balanced",
        ranking_config: Optional[Dict] = None,
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
        for aid, semantic_sim, cluster in zip(candidate_ids, semantic_similarities, candidate_clusters):
            freshness = self._calculate_time_decay(aid, config.time_decay_days)
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
                    },
                    "features": {k: round(v, 4) for k, v in features.items()},
                    "feature_contributions": {k: round(v, 4) for k, v in contributions.items()},
                    "config_id": config.config_id,
                    "explanation": self._compose_explanation(contributions, source),
                }
            )

        recommendations.sort(key=lambda x: x["score"], reverse=True)
        return recommendations[:top_n]


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
