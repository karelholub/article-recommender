"""
Development configuration for the BERT-MVP project.
"""
from config.default import *

# Override default settings for development
API_DEBUG = True
LOG_LEVEL = "DEBUG"

# Development-specific settings
SCRAPER_MAX_ARTICLES = 5  # Limit articles for faster development 