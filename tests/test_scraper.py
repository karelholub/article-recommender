import pytest
from scrape import ArticleScraper
import os
from pathlib import Path
import json

@pytest.fixture
def scraper():
    return ArticleScraper()

@pytest.fixture
def test_url():
    return "https://www.e15.cz/ekonomika"

def test_scraper_initialization(scraper):
    assert scraper is not None
    assert hasattr(scraper, 'headers')
    assert 'User-Agent' in scraper.headers

def test_article_saving(scraper, tmp_path):
    # Create a temporary articles directory
    articles_dir = tmp_path / "articles"
    articles_dir.mkdir()
    
    # Test article data
    article_data = {
        "title": "Test Article",
        "content": "Test content",
        "url": "https://test.com/article",
        "date": "2024-01-01"
    }
    
    # Save the article
    article_id = scraper._save_article(article_data, articles_dir)
    
    # Check if file exists
    article_file = articles_dir / f"{article_id}.json"
    assert article_file.exists()
    
    # Check content
    with open(article_file) as f:
        saved_data = json.load(f)
        assert saved_data['metadata']['title'] == article_data['title']
        assert saved_data['metadata']['content'] == article_data['content']

def test_invalid_url(scraper):
    with pytest.raises(ValueError):
        scraper.scrape_articles("invalid_url")

def test_empty_content(scraper, tmp_path):
    # Create a temporary articles directory
    articles_dir = tmp_path / "articles"
    articles_dir.mkdir()
    
    # Test article with empty content
    article_data = {
        "title": "Test Article",
        "content": "",
        "url": "https://test.com/article",
        "date": "2024-01-01"
    }
    
    # Should raise ValueError for empty content
    with pytest.raises(ValueError):
        scraper._save_article(article_data, articles_dir) 