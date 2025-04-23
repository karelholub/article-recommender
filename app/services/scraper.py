"""
Scraper service for the BERT-MVP project.
"""
import requests
from bs4 import BeautifulSoup
import json
import time
import random
import re
import unicodedata
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from app.utils.logger import setup_logger
from app.models.article import Article
from config.default import (
    SCRAPER_DELAY_MIN,
    SCRAPER_DELAY_MAX,
    SCRAPER_MAX_ARTICLES,
    ARTICLES_DIR,
    EMBEDDINGS_DIR
)

logger = setup_logger(__name__)

class Scraper:
    """Service for scraping articles from the web."""
    
    def __init__(self, base_url: str = "https://www.e15.cz/geopolitika"):
        """
        Initialize the scraper.
        
        Args:
            base_url: The base URL to scrape from
        """
        self.base_url = base_url
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }
        
        # Initialize session
        self._init_session()
    
    def _init_session(self):
        """Initialize session with cookies and initial request"""
        try:
            # Make initial request to get cookies
            response = self.session.get(self.base_url, headers=self.headers)
            response.raise_for_status()
            
            # Update headers with referer
            self.headers['Referer'] = self.base_url
            
            logger.info("Session initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing session: {str(e)}")
            raise
    
    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize text.
        
        Args:
            text: The text to clean
            
        Returns:
            The cleaned text
        """
        if not text:
            return ""
        # Remove multiple spaces and newlines
        text = re.sub(r'\s+', ' ', text)
        # Keep alphanumeric, spaces, and basic punctuation
        text = re.sub(r'[^a-zA-ZěščřžýáíéúůďťňóĚŠČŘŽÝÁÍÉÚŮĎŤŇÓ\s.,!?0-9-]', '', text)
        return text.strip()
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Create a safe filename from text.
        
        Args:
            filename: The text to convert to a filename
            
        Returns:
            A safe filename
        """
        # Remove diacritics
        filename = unicodedata.normalize('NFKD', filename)
        filename = ''.join(c for c in filename if not unicodedata.combining(c))
        
        # Replace spaces with underscores and remove invalid characters
        filename = re.sub(r'[^\w\s-]', '', filename)
        filename = re.sub(r'[-\s]+', '_', filename)
        
        return filename.lower()[:50]
    
    def _get_article_links(self) -> List[str]:
        """
        Get all article links from the main page.
        
        Returns:
            A list of article URLs
        """
        try:
            # Add random delay
            time.sleep(random.uniform(1, 2))
            
            response = self.session.get(
                self.base_url,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            
            if 'text/html' not in response.headers.get('Content-Type', ''):
                logger.error("Response is not HTML")
                return []
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Find all article links
            article_links = []
            
            # Try different selectors
            selectors = [
                'article h2 a',  # Common pattern for article headlines
                '.article-title a',  # Another common pattern
                '.article-list a',  # List of articles
                '.content a'  # Generic content area
            ]
            
            for selector in selectors:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href', '')
                    if href and not href.endswith(self.base_url.split('/')[-1]):
                        full_url = f"https://www.e15.cz{href}" if not href.startswith('http') else href
                        article_links.append(full_url)
            
            # Log the HTML if no links found
            if not article_links:
                logger.debug(f"HTML content: {response.text[:1000]}")
                logger.warning("No article links found")
            
            return list(set(article_links))  # Remove duplicates
            
        except Exception as e:
            logger.error(f"Error fetching article links: {str(e)}")
            return []
    
    def _scrape_article(self, url: str) -> Optional[Article]:
        """
        Scrape content from a single article.
        
        Args:
            url: The URL of the article to scrape
            
        Returns:
            An Article instance or None if scraping failed
        """
        try:
            # Add random delay
            time.sleep(random.uniform(SCRAPER_DELAY_MIN, SCRAPER_DELAY_MAX))
            
            response = self.session.get(
                url,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            
            if 'text/html' not in response.headers.get('Content-Type', ''):
                logger.error(f"Response for {url} is not HTML")
                return None
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Extract article content with multiple selector attempts
            title = None
            for selector in ['h1.article-title', 'h1.title', 'h1']:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.text.strip()
                    break
            
            content = []
            # Try different content selectors
            content_selectors = [
                'div.article-content p',
                'div.content p',
                'article p'
            ]
            
            for selector in content_selectors:
                paragraphs = soup.select(selector)
                if paragraphs:
                    for p in paragraphs:
                        text = p.text.strip()
                        if text and not text.startswith(('Foto:', 'Zdroj:', 'Související:', 'Autor:')):
                            content.append(text)
                    break
            
            if not title or not content:
                logger.warning(f"Missing content for {url}")
                return None
            
            # Create article ID from URL
            article_id = self._sanitize_filename(title)
            
            # Create article instance
            article = Article(
                id=article_id,
                title=self._clean_text(title),
                content=self._clean_text(' '.join(content)),
                url=url,
                scraped_at=datetime.now(),
                vector=None,
                labels=None
            )
            
            return article
            
        except Exception as e:
            logger.error(f"Error scraping article {url}: {str(e)}")
            return None
    
    def scrape_and_save(self, max_articles: int = SCRAPER_MAX_ARTICLES) -> int:
        """
        Scrape articles and save them to files.
        
        Args:
            max_articles: Maximum number of articles to scrape
            
        Returns:
            Number of articles scraped
        """
        article_links = self._get_article_links()
        logger.info(f"Found {len(article_links)} articles")
        
        # Load existing articles
        output_file = EMBEDDINGS_DIR / 'article_vectors.json'
        existing_articles = {}
        if output_file.exists():
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_articles = json.load(f)
        
        scraped_count = 0
        for url in article_links[:max_articles]:
            try:
                article = self._scrape_article(url)
                if article and article.content:  # Only save if we got content
                    if article.id not in existing_articles:
                        existing_articles[article.id] = {
                            'metadata': article.to_dict(),
                            'vector': []  # Vector will be added by the embedding script
                        }
                        scraped_count += 1
                        logger.info(f"Saved article: {article.title}")
                    
                    # Be nice to the server
                    time.sleep(random.uniform(SCRAPER_DELAY_MIN, SCRAPER_DELAY_MAX))
            except Exception as e:
                logger.error(f"Error processing article {url}: {str(e)}")
        
        # Save all articles
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(existing_articles, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Successfully scraped and saved {scraped_count} new articles")
        return scraped_count 