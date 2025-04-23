"""
Embedder service for the BERT-MVP project.
"""
import os
import json
import time
from pathlib import Path
from typing import Dict, List
from sentence_transformers import SentenceTransformer

from app.utils.logger import setup_logger
from config.default import EMBEDDINGS_DIR, EMBED_FILE

logger = setup_logger(__name__)

class Embedder:
    """Service for generating embeddings for articles."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize the embedder.
        
        Args:
            model_name: The name of the sentence transformer model to use
        """
        self.model = SentenceTransformer(model_name)
        self.embedding_cache = {}
        
    def _load_cache(self) -> Dict[str, Dict]:
        """
        Load the embedding cache from disk.
        
        Returns:
            The embedding cache
        """
        if EMBED_FILE.exists():
            try:
                with open(EMBED_FILE, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.warning("Cache file corrupted, starting fresh")
        return {}
    
    def _save_cache(self, embeddings: Dict[str, Dict]):
        """
        Save the embedding cache to disk.
        
        Args:
            embeddings: The embedding cache to save
        """
        try:
            with open(EMBED_FILE, "w") as f:
                json.dump(embeddings, f, indent=2)
            logger.info(f"Successfully saved {len(embeddings)} embeddings to cache")
        except Exception as e:
            logger.error(f"Error saving cache: {str(e)}")
    
    def _process_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Process texts in batches for better performance.
        
        Args:
            texts: The texts to process
            batch_size: The batch size to use
            
        Returns:
            A list of embeddings
        """
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = self.model.encode(batch, normalize_embeddings=True)
            embeddings.extend(batch_embeddings.tolist())
        return embeddings
    
    def embed_articles(self, force_update: bool = False) -> Dict[str, Dict]:
        """
        Generate embeddings for all articles.
        
        Args:
            force_update: Whether to force update all embeddings
            
        Returns:
            The updated embedding cache
        """
        # Load existing cache
        if not force_update:
            self.embedding_cache = self._load_cache()
        
        # Find new or updated articles
        new_articles = {}
        for article_id, data in self.embedding_cache.items():
            if force_update or not data.get('vector'):
                new_articles[article_id] = {
                    'text': data['metadata']['content'],
                    'metadata': data['metadata']
                }
        
        if new_articles:
            logger.info(f"Processing {len(new_articles)} new/updated articles")
            start_time = time.time()
            
            # Process in batches
            article_ids = list(new_articles.keys())
            texts = [article['text'] for article in new_articles.values()]
            embeddings = self._process_batch(texts)
            
            # Update cache with metadata
            for article_id, embedding, article_data in zip(article_ids, embeddings, new_articles.values()):
                self.embedding_cache[article_id] = {
                    'vector': embedding,
                    'metadata': article_data['metadata']
                }
            
            # Save updated cache
            self._save_cache(self.embedding_cache)
            
            duration = time.time() - start_time
            logger.info(f"Processed {len(new_articles)} articles in {duration:.2f} seconds")
        
        return self.embedding_cache 