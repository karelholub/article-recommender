import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Flask settings
FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
DEBUG = FLASK_ENV == 'development'
PORT = int(os.environ.get('PORT', 5001))

# File paths
EMBEDDINGS_DIR = BASE_DIR / 'embeddings'
ARTICLES_DIR = BASE_DIR / 'articles'
LOGS_DIR = BASE_DIR / 'logs'

# Create necessary directories
for directory in [EMBEDDINGS_DIR, ARTICLES_DIR, LOGS_DIR]:
    directory.mkdir(exist_ok=True)

# Available sections for scraping
AVAILABLE_SECTIONS = {
    'ekonomika': 'https://www.e15.cz/ekonomika',
    'geopolitika': 'https://www.e15.cz/geopolitika',
    'byznys': 'https://www.e15.cz/byznys',
    'burzy-a-trhy': 'https://www.e15.cz/byznys/burzy-a-trhy'
}

# Recommender settings
DEFAULT_DIVERSITY_WEIGHT = 0.3
DEFAULT_TIME_DECAY_DAYS = 30
DEFAULT_RECOMMENDATIONS_COUNT = 3

# Scraping settings
SCRAPING_DELAY = 1  # Delay between requests in seconds
MAX_RETRIES = 3  # Maximum number of retries for failed requests 