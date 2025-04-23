import pytest
from embed import ArticleEmbedder
import numpy as np
from pathlib import Path
import json

@pytest.fixture
def embedder():
    return ArticleEmbedder()

@pytest.fixture
def sample_article():
    return {
        "metadata": {
            "title": "Test Article",
            "content": "This is a test article content for embedding generation.",
            "date": "2024-01-01"
        }
    }

def test_embedder_initialization(embedder):
    assert embedder is not None
    assert hasattr(embedder, 'model')
    assert embedder.model is not None

def test_embedding_generation(embedder, sample_article):
    # Generate embedding
    embedding = embedder.generate_embedding(sample_article)
    
    # Check embedding properties
    assert isinstance(embedding, list)
    assert len(embedding) > 0
    assert all(isinstance(x, float) for x in embedding)

def test_embedding_saving(embedder, tmp_path):
    # Create temporary directories
    articles_dir = tmp_path / "articles"
    embeddings_dir = tmp_path / "embeddings"
    articles_dir.mkdir()
    embeddings_dir.mkdir()
    
    # Create a test article file
    article_id = "test_article"
    article_file = articles_dir / f"{article_id}.json"
    with open(article_file, 'w') as f:
        json.dump({
            "metadata": {
                "title": "Test Article",
                "content": "Test content",
                "date": "2024-01-01"
            }
        }, f)
    
    # Generate and save embedding
    embedder.process_article(article_id, articles_dir, embeddings_dir)
    
    # Check if embedding file exists
    embedding_file = embeddings_dir / f"{article_id}.json"
    assert embedding_file.exists()
    
    # Check embedding content
    with open(embedding_file) as f:
        data = json.load(f)
        assert 'vector' in data
        assert isinstance(data['vector'], list)
        assert len(data['vector']) > 0

def test_invalid_article(embedder, tmp_path):
    # Create temporary directories
    articles_dir = tmp_path / "articles"
    embeddings_dir = tmp_path / "embeddings"
    articles_dir.mkdir()
    embeddings_dir.mkdir()
    
    # Create an invalid article file
    article_id = "invalid_article"
    article_file = articles_dir / f"{article_id}.json"
    with open(article_file, 'w') as f:
        json.dump({"invalid": "data"}, f)
    
    # Should raise ValueError for invalid article
    with pytest.raises(ValueError):
        embedder.process_article(article_id, articles_dir, embeddings_dir) 