import pytest
from recommend import RecommenderFactory
import json
from pathlib import Path

@pytest.fixture
def sample_articles():
    return {
        "article1": {
            "metadata": {
                "title": "Test Article 1",
                "content": "This is a test article content",
                "date": "2024-01-01"
            },
            "vector": [0.1, 0.2, 0.3]
        },
        "article2": {
            "metadata": {
                "title": "Test Article 2",
                "content": "Another test article content",
                "date": "2024-01-02"
            },
            "vector": [0.4, 0.5, 0.6]
        }
    }

@pytest.fixture
def recommender():
    return RecommenderFactory.create_recommender(
        "advanced",
        diversity_weight=0.3,
        time_decay_days=30
    )

def test_recommender_initialization(recommender):
    assert recommender is not None
    assert hasattr(recommender, 'diversity_weight')
    assert recommender.diversity_weight == 0.3

def test_recommendations_generation(recommender, sample_articles):
    # Mock the article vectors
    recommender.article_vectors = sample_articles
    
    # Test with one read article
    read_articles = ["article1"]
    recommendations = recommender.recommend_for_user(
        "test_user",
        sample_articles,
        read_articles,
        top_n=1
    )
    
    assert len(recommendations) == 1
    assert recommendations[0]['id'] == "article2"  # Should recommend the other article

def test_invalid_diversity_weight():
    with pytest.raises(ValueError):
        RecommenderFactory.create_recommender(
            "advanced",
            diversity_weight=1.5,  # Invalid weight
            time_decay_days=30
        )

def test_empty_article_list(recommender):
    with pytest.raises(ValueError):
        recommender.recommend_for_user(
            "test_user",
            {},
            [],
            top_n=1
        ) 