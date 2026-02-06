import json
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from typing import Dict, List, Tuple, Optional, Union
import logging
from datetime import datetime
from pathlib import Path
import time
from functools import lru_cache
from abc import ABC, abstractmethod

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseRecommender(ABC):
    """Base class for article recommenders"""
    
    def __init__(
        self,
        embed_file: str = "embeddings/article_vectors.json",
        profile_file: str = "profiles/user_profiles.json",
        output_file: str = "recommendations.json",
        cache_size: int = 128
    ):
        self.embed_file = Path(embed_file)
        self.profile_file = Path(profile_file)
        self.output_file = Path(output_file)
        
        # Initialize caches
        self._load_data()
        self._initialize_caches(cache_size)
    
    def _load_data(self):
        """Load embeddings and user profiles"""
        try:
            with open(self.embed_file) as f:
                self.article_vectors = json.load(f)
            with open(self.profile_file) as f:
                self.user_profiles = json.load(f)
            
            # Filter out articles with no vectors or zero-length vectors
            valid_articles = {}
            for aid, data in self.article_vectors.items():
                if 'vector' in data and isinstance(data['vector'], list) and len(data['vector']) > 0:
                    valid_articles[aid] = data
            
            self.article_vectors = valid_articles
            self.article_ids = list(self.article_vectors.keys())
            
            if not self.article_ids:
                logger.error("No valid articles found with vectors")
                raise ValueError("No valid articles found with vectors")
            
            # Get the expected vector length from the first valid article
            expected_length = len(self.article_vectors[self.article_ids[0]]['vector'])
            logger.info(f"Expected vector length: {expected_length}")
            
            # Create a list of vectors, ensuring they're all the same length
            vectors = []
            for aid in self.article_ids:
                vector = self.article_vectors[aid]['vector']
                if len(vector) != expected_length:
                    logger.warning(f"Vector length mismatch for article {aid}: {len(vector)} vs {expected_length}")
                    # Pad or truncate to match expected length
                    if len(vector) < expected_length:
                        vector = vector + [0] * (expected_length - len(vector))
                    else:
                        vector = vector[:expected_length]
                vectors.append(vector)
            
            # Convert to numpy array
            self.vector_array = np.array(vectors, dtype=np.float32)
            
            logger.info(f"Loaded {len(self.article_vectors)} valid article vectors")
        except Exception as e:
            logger.error(f"Error loading data: {str(e)}")
            raise
    
    def _initialize_caches(self, cache_size: int):
        """Initialize LRU caches for expensive operations"""
        self._get_article_vector = lru_cache(maxsize=cache_size)(self._get_article_vector)
    
    def _get_article_vector(self, article_id: str) -> np.ndarray:
        """Get article vector with caching"""
        return np.array(self.article_vectors[article_id]['vector'])
    
    @abstractmethod
    def recommend_for_user(
        self,
        user_id: str,
        article_vectors: Dict[str, Dict],
        user_reads: List[str],
        top_n: int = 5
    ) -> List[Dict[str, float]]:
        """Generate recommendations for a user"""
        pass
    
    def generate_all_recommendations(self, top_n: int = 5):
        """Generate recommendations for all users"""
        all_recommendations = {}
        start_time = time.time()
        
        for user_id, read_articles in self.user_profiles.items():
            try:
                recs = self.recommend_for_user(
                    user_id,
                    self.article_vectors,
                    read_articles,
                    top_n=top_n
                )
                all_recommendations[user_id] = recs
            except Exception as e:
                logger.error(f"Error generating recommendations for user {user_id}: {str(e)}")
        
        # Save recommendations
        with open(self.output_file, "w") as f:
            json.dump(all_recommendations, f, indent=2)
        
        duration = time.time() - start_time
        logger.info(f"Generated recommendations for {len(all_recommendations)} users in {duration:.2f} seconds")
        logger.info(f"Recommendations written to {self.output_file}")


class SimpleRecommender(BaseRecommender):
    """Simple recommender based on cosine similarity"""
    
    def recommend_for_user(
        self,
        user_id: str,
        article_vectors: Dict[str, Dict],
        user_reads: List[str],
        top_n: int = 5
    ) -> List[Dict[str, float]]:
        """Generate recommendations for a user using simple cosine similarity"""
        if not user_reads:
            return []
        
        # Compute user's profile vector from articles they've read
        user_vecs = []
        for aid in user_reads:
            if aid in article_vectors:
                vector = self._get_article_vector(aid)
                if vector is not None:
                    user_vecs.append(vector)
        
        if not user_vecs:
            return []
        
        user_profile_vector = np.mean(user_vecs, axis=0)
        
        # Get candidate articles
        candidate_ids = []
        candidate_vectors = []
        for aid in self.article_ids:
            if aid not in user_reads:
                candidate_ids.append(aid)
                candidate_vectors.append(self._get_article_vector(aid))
        
        if not candidate_ids:
            return []
        
        candidate_vectors = np.array(candidate_vectors)
        
        # Calculate similarities
        similarities = cosine_similarity([user_profile_vector], candidate_vectors)[0]
        
        # Build recommendations
        recommendations = []
        for i, (aid, score) in enumerate(zip(candidate_ids, similarities)):
            article_data = article_vectors[aid]
            recommendations.append({
                'article_id': aid,
                'title': article_data['metadata'].get('title', ''),
                'url': article_data['metadata'].get('url', ''),
                'score': round(score, 4)
            })
        
        # Sort by score and return top N
        recommendations.sort(key=lambda x: x['score'], reverse=True)
        return recommendations[:top_n]


class AdvancedRecommender(BaseRecommender):
    """Advanced recommender with diversity, time decay, and semantic clustering"""
    
    def __init__(
        self,
        embed_file: str = "embeddings/article_vectors.json",
        profile_file: str = "profiles/user_profiles.json",
        output_file: str = "recommendations.json",
        diversity_weight: float = 0.3,
        time_decay_days: int = 30,
        cluster_weight: float = 0.2,
        cache_size: int = 128
    ):
        super().__init__(embed_file, profile_file, output_file, cache_size)
        self.diversity_weight = diversity_weight
        self.time_decay_days = time_decay_days
        self.cluster_weight = cluster_weight
    
    def _calculate_time_decay(self, article_id: str) -> float:
        """Calculate time decay factor for an article"""
        try:
            scraped_at = datetime.strptime(
                self.article_vectors[article_id]['metadata']['scraped_at'],
                '%Y-%m-%d %H:%M:%S'
            )
            days_old = (datetime.now() - scraped_at).days
            return np.exp(-days_old / self.time_decay_days)
        except (KeyError, ValueError):
            return 1.0
    
    def _calculate_cluster_similarity(self, user_clusters: List[int], article_cluster: int) -> float:
        """Calculate similarity based on article clusters"""
        if not user_clusters:
            return 0.0
        # Count how many times the article's cluster appears in user's history
        cluster_count = user_clusters.count(article_cluster)
        return cluster_count / len(user_clusters)
    
    def _maximal_marginal_relevance(
        self,
        query_vector: np.ndarray,
        candidate_vectors: np.ndarray,
        candidate_ids: List[str],
        lambda_param: float = 0.5,
        top_n: int = 5
    ) -> List[Tuple[str, float]]:
        """Select diverse recommendations using MMR"""
        selected = []
        remaining = list(range(len(candidate_ids)))
        
        # Get the most similar item first
        similarities = cosine_similarity([query_vector], candidate_vectors)[0]
        selected_idx = np.argmax(similarities)
        selected.append(selected_idx)
        remaining.remove(selected_idx)
        
        # Select remaining items using MMR
        while len(selected) < top_n and remaining:
            # Calculate relevance and diversity scores
            relevance = cosine_similarity([query_vector], candidate_vectors[remaining])[0]
            diversity = np.zeros(len(remaining))
            
            for i, idx in enumerate(remaining):
                diversity[i] = np.mean([
                    cosine_similarity([candidate_vectors[idx]], [candidate_vectors[j]])[0][0]
                    for j in selected
                ])
            
            # Combine scores
            mmr_scores = lambda_param * relevance - (1 - lambda_param) * diversity
            selected_idx = remaining[np.argmax(mmr_scores)]
            selected.append(selected_idx)
            remaining.remove(selected_idx)
        
        return [(candidate_ids[i], similarities[i]) for i in selected]
    
    def recommend_for_user(
        self,
        user_id: str,
        article_vectors: Dict[str, Dict],
        user_reads: List[str],
        top_n: int = 5
    ) -> List[Dict[str, float]]:
        """Generate recommendations for a user using advanced features"""
        if not user_reads:
            return []
        
        # Compute user's profile vector and cluster history
        user_vecs = []
        user_clusters = []
        for aid in user_reads:
            if aid in article_vectors:
                vector = self._get_article_vector(aid)
                if vector is not None:
                    user_vecs.append(vector)
                    if 'cluster' in article_vectors[aid]:
                        user_clusters.append(article_vectors[aid]['cluster'])
        
        if not user_vecs:
            return []
        
        user_profile_vector = np.mean(user_vecs, axis=0)
        
        # Get candidate articles
        candidate_ids = []
        candidate_vectors = []
        candidate_clusters = []
        for aid in self.article_ids:
            if aid not in user_reads:
                candidate_ids.append(aid)
                candidate_vectors.append(self._get_article_vector(aid))
                if 'cluster' in article_vectors[aid]:
                    candidate_clusters.append(article_vectors[aid]['cluster'])
                else:
                    candidate_clusters.append(-1)
        
        if not candidate_ids:
            return []
        
        candidate_vectors = np.array(candidate_vectors)
        
        # Calculate base semantic similarity
        semantic_similarities = cosine_similarity([user_profile_vector], candidate_vectors)[0]
        
        # Calculate time decay and cluster similarity
        time_decays = []
        cluster_similarities = []
        for i, (aid, cluster) in enumerate(zip(candidate_ids, candidate_clusters)):
            # Time decay
            time_factor = self._calculate_time_decay(aid)
            time_decays.append(time_factor)
            
            # Cluster similarity
            cluster_sim = self._calculate_cluster_similarity(user_clusters, cluster)
            cluster_similarities.append(cluster_sim)
        
        # Build recommendations with all similarity components
        recommendations = []
        for i, (aid, semantic_sim, time_decay, cluster_sim) in enumerate(zip(
            candidate_ids, semantic_similarities, time_decays, cluster_similarities
        )):
            article_data = article_vectors[aid]
            
            # Calculate final score using weights
            final_score = (
                semantic_sim * (1 - self.diversity_weight - self.cluster_weight) +
                time_decay * self.diversity_weight +
                cluster_sim * self.cluster_weight
            )
            
            recommendations.append({
                'article_id': aid,
                'title': article_data['metadata'].get('title', ''),
                'content': article_data['metadata'].get('content', ''),
                'url': article_data['metadata'].get('url', ''),
                'score': round(final_score, 4),
                'similarity_components': {
                    'semantic': round(semantic_sim, 4),
                    'freshness': round(time_decay, 4),
                    'topic': round(cluster_sim, 4)
                }
            })
        
        # Sort by final score and return top N
        recommendations.sort(key=lambda x: x['score'], reverse=True)
        return recommendations[:top_n]


class RecommenderFactory:
    """Factory for creating recommenders"""
    
    @staticmethod
    def create_recommender(
        recommender_type: str = "advanced",
        **kwargs
    ) -> BaseRecommender:
        """
        Create a recommender of the specified type
        
        Args:
            recommender_type: Type of recommender to create ("simple" or "advanced")
            **kwargs: Additional arguments to pass to the recommender constructor
            
        Returns:
            A recommender instance
        """
        if recommender_type.lower() == "simple":
            return SimpleRecommender(**kwargs)
        elif recommender_type.lower() == "advanced":
            return AdvancedRecommender(**kwargs)
        else:
            raise ValueError(f"Unknown recommender type: {recommender_type}")


# Example usage
if __name__ == "__main__":
    # Create a simple recommender
    simple_recommender = RecommenderFactory.create_recommender("simple")
    simple_recs = simple_recommender.recommend_for_user(
        "user_1",
        simple_recommender.article_vectors,
        simple_recommender.user_profiles.get("user_1", []),
        top_n=3
    )
    print("Simple recommendations:")
    for rec in simple_recs:
        print(f"{rec['score']:.3f} → {rec['title']}")
    
    # Create an advanced recommender
    advanced_recommender = RecommenderFactory.create_recommender(
        "advanced",
        diversity_weight=0.3,
        time_decay_days=30
    )
    advanced_recs = advanced_recommender.recommend_for_user(
        "user_1",
        advanced_recommender.article_vectors,
        advanced_recommender.user_profiles.get("user_1", []),
        top_n=3
    )
    print("\nAdvanced recommendations:")
    for rec in advanced_recs:
        print(f"{rec['score']:.3f} (semantic: {rec['similarity_components']['semantic']:.3f}, freshness: {rec['similarity_components']['freshness']:.3f}) → {rec['title']}")