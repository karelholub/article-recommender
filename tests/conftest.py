import pytest
import os
from pathlib import Path
import json

@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory):
    """Create a temporary directory for test data."""
    return tmp_path_factory.mktemp("test_data")

@pytest.fixture(scope="session")
def sample_articles(test_data_dir):
    """Create sample articles for testing."""
    articles_dir = test_data_dir / "articles"
    articles_dir.mkdir()
    
    articles = {
        "article1": {
            "metadata": {
                "title": "Test Article 1",
                "content": "This is a test article content",
                "date": "2024-01-01"
            }
        },
        "article2": {
            "metadata": {
                "title": "Test Article 2",
                "content": "Another test article content",
                "date": "2024-01-02"
            }
        }
    }
    
    for article_id, data in articles.items():
        with open(articles_dir / f"{article_id}.json", 'w') as f:
            json.dump(data, f)
    
    return articles

@pytest.fixture(scope="session")
def sample_embeddings(test_data_dir):
    """Create sample embeddings for testing."""
    embeddings_dir = test_data_dir / "embeddings"
    embeddings_dir.mkdir()
    
    embeddings = {
        "article1": {
            "vector": [0.1, 0.2, 0.3],
            "metadata": {
                "title": "Test Article 1",
                "date": "2024-01-01"
            }
        },
        "article2": {
            "vector": [0.4, 0.5, 0.6],
            "metadata": {
                "title": "Test Article 2",
                "date": "2024-01-02"
            }
        }
    }
    
    with open(embeddings_dir / "article_vectors.json", 'w') as f:
        json.dump(embeddings, f)
    
    return embeddings 