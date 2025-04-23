import os
import json
import logging
from pathlib import Path
from sentence_transformers import SentenceTransformer
import numpy as np
from typing import Dict, List, Tuple
import time
import re
from sklearn.cluster import KMeans
from sklearn.preprocessing import normalize

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ArticleEmbedder:
    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-mpnet-base-v2",  # More powerful multilingual model
        cache_dir: str = "embeddings",
        max_length: int = 512,  # BERT's max sequence length
        batch_size: int = 16    # Smaller batch size for larger model
    ):
        self.model = SentenceTransformer(model_name)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.embedding_cache = {}
        self.max_length = max_length
        self.batch_size = batch_size
        
    def _preprocess_text(self, text: str) -> str:
        """Clean and normalize text for better embedding quality"""
        # Remove special characters and extra whitespace
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s.,!?-]', '', text)
        
        # Truncate to max length while preserving sentence boundaries
        if len(text) > self.max_length:
            # Find the last sentence boundary before max_length
            last_period = text[:self.max_length].rfind('.')
            if last_period > 0:
                text = text[:last_period + 1]
            else:
                text = text[:self.max_length]
        
        return text.strip()
    
    def _load_cache(self) -> Dict[str, Dict]:
        cache_file = self.cache_dir / "article_vectors.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.warning("Cache file corrupted, starting fresh")
        return {}
    
    def _save_cache(self, embeddings: Dict[str, Dict]):
        cache_file = self.cache_dir / "article_vectors.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(embeddings, f, indent=2)
            logger.info(f"Successfully saved {len(embeddings)} embeddings to cache")
        except Exception as e:
            logger.error(f"Error saving cache: {str(e)}")
    
    def _process_batch(self, texts: List[str]) -> List[List[float]]:
        """Process texts in batches for better performance"""
        # Preprocess texts
        processed_texts = [self._preprocess_text(text) for text in texts]
        
        # Generate embeddings
        embeddings = []
        for i in range(0, len(processed_texts), self.batch_size):
            batch = processed_texts[i:i + self.batch_size]
            batch_embeddings = self.model.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=True
            )
            embeddings.extend(batch_embeddings.tolist())
        
        return embeddings
    
    def _cluster_embeddings(self, embeddings: List[List[float]], n_clusters: int = 5) -> List[int]:
        """Cluster similar articles together"""
        # Normalize embeddings
        normalized_embeddings = normalize(np.array(embeddings))
        
        # Perform clustering
        kmeans = KMeans(n_clusters=min(n_clusters, len(embeddings)), random_state=42)
        clusters = kmeans.fit_predict(normalized_embeddings)
        
        return clusters.tolist()
    
    def _load_article(self, filepath: Path) -> Dict:
        """Load and parse article from JSON file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                article = json.load(f)
            return article
        except Exception as e:
            logger.error(f"Error reading {filepath}: {str(e)}")
            return None
    
    def embed_articles(self, article_dir: str, force_update: bool = False) -> Dict[str, Dict]:
        """Generate embeddings for all articles in the directory"""
        article_dir = Path(article_dir)
        if not article_dir.exists():
            raise ValueError(f"Article directory {article_dir} does not exist")
        
        # Load existing cache
        if not force_update:
            self.embedding_cache = self._load_cache()
        
        # Find new or updated articles
        new_articles = {}
        for filepath in article_dir.glob("*.txt"):
            article_id = filepath.stem
            if force_update or article_id not in self.embedding_cache:
                article = self._load_article(filepath)
                if article and article.get('content'):
                    new_articles[article_id] = {
                        'text': article['content'],
                        'metadata': {
                            'title': article.get('title', ''),
                            'content': article.get('content', ''),
                            'url': article.get('url', ''),
                            'scraped_at': article.get('scraped_at', '')
                        }
                    }
        
        if new_articles:
            logger.info(f"Processing {len(new_articles)} new/updated articles")
            start_time = time.time()
            
            # Process in batches
            article_ids = list(new_articles.keys())
            texts = [article['text'] for article in new_articles.values()]
            embeddings = self._process_batch(texts)
            
            # Cluster similar articles
            clusters = self._cluster_embeddings(embeddings)
            
            # Update cache with metadata and clusters
            for article_id, embedding, cluster, article_data in zip(
                article_ids, embeddings, clusters, new_articles.values()
            ):
                self.embedding_cache[article_id] = {
                    'vector': embedding,
                    'cluster': int(cluster),
                    'metadata': article_data['metadata']
                }
            
            # Save updated cache
            self._save_cache(self.embedding_cache)
            
            duration = time.time() - start_time
            logger.info(f"Processed {len(new_articles)} articles in {duration:.2f} seconds")
        
        return self.embedding_cache

def main():
    embedder = ArticleEmbedder()
    try:
        # Force update to regenerate all embeddings
        embeddings = embedder.embed_articles("articles", force_update=True)
        logger.info(f"Total articles processed: {len(embeddings)}")
    except Exception as e:
        logger.error(f"Error in embedding process: {str(e)}")
        raise

if __name__ == "__main__":
    main()