"""
Default configuration for the BERT-MVP project.
"""
import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Data directories
DATA_DIR = BASE_DIR / "data"
ARTICLES_DIR = DATA_DIR / "articles"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
PROFILES_DIR = DATA_DIR / "profiles"

# File paths
EMBED_FILE = EMBEDDINGS_DIR / "article_vectors.json"
PROFILE_FILE = PROFILES_DIR / "user_profiles.json"
RECOMMENDATIONS_FILE = DATA_DIR / "recommendations.json"

# API configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "5001"))
API_DEBUG = os.getenv("API_DEBUG", "True").lower() == "true"

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = BASE_DIR / "logs" / "app.log"

# Recommender configuration
RECOMMENDER_TYPE = os.getenv("RECOMMENDER_TYPE", "advanced")
DIVERSITY_WEIGHT = float(os.getenv("DIVERSITY_WEIGHT", "0.3"))
TIME_DECAY_DAYS = int(os.getenv("TIME_DECAY_DAYS", "30"))
CACHE_SIZE = int(os.getenv("CACHE_SIZE", "128"))

# Scraper configuration
SCRAPER_DELAY_MIN = float(os.getenv("SCRAPER_DELAY_MIN", "2.0"))
SCRAPER_DELAY_MAX = float(os.getenv("SCRAPER_DELAY_MAX", "4.0"))
SCRAPER_MAX_ARTICLES = int(os.getenv("SCRAPER_MAX_ARTICLES", "10"))

# Available sections for scraping
AVAILABLE_SECTIONS = {
    'ekonomika': 'https://www.e15.cz/ekonomika',
    'geopolitika': 'https://www.e15.cz/geopolitika',
    'byznys': 'https://www.e15.cz/byznys',
    'burzy-a-trhy': 'https://www.e15.cz/byznys/burzy-a-trhy'
} 