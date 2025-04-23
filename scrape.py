import requests
from bs4 import BeautifulSoup
import json
from pathlib import Path
import logging
from typing import List, Dict
import time
import re
import random
import unicodedata
import argparse

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ArticleScraper:
    def __init__(self, base_url: str = "https://www.e15.cz/geopolitika"):
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
        self.articles_dir = Path("articles")
        self.articles_dir.mkdir(exist_ok=True)
        
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
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        # Remove multiple spaces and newlines
        text = re.sub(r'\s+', ' ', text)
        # Keep alphanumeric, spaces, and basic punctuation
        text = re.sub(r'[^a-zA-ZěščřžýáíéúůďťňóĚŠČŘŽÝÁÍÉÚŮĎŤŇÓ\s.,!?0-9-]', '', text)
        return text.strip()
    
    def _sanitize_filename(self, filename: str) -> str:
        """Create a safe filename from text"""
        # Remove diacritics
        filename = unicodedata.normalize('NFKD', filename)
        filename = ''.join(c for c in filename if not unicodedata.combining(c))
        
        # Replace spaces with underscores and remove invalid characters
        filename = re.sub(r'[^\w\s-]', '', filename)
        filename = re.sub(r'[-\s]+', '_', filename)
        
        return filename.lower()[:50]
    
    def _is_valid_article_url(self, url: str) -> bool:
        """Check if URL is a valid article URL"""
        # Exclude non-article URLs
        excluded_patterns = [
            '/aplikace',
            '/instagram',
            '/facebook',
            '/twitter',
            '/youtube',
            '/business-club',
            '/flow',
            '/kalendar',
            '/svatky',
            '/mistrovstvi',
            '/program',
            '/vysledky'
        ]
        
        # Must be a valid e15.cz URL
        if not url.startswith('https://www.e15.cz/'):
            return False
            
        # Check for excluded patterns
        for pattern in excluded_patterns:
            if pattern in url.lower():
                return False
                
        return True
    
    def _get_article_links(self) -> List[str]:
        """Get all article links from the main page"""
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
            
            # More specific selectors for e15.cz articles
            selectors = [
                'article.article-item a',  # Main article items
                'div.article-list article a',  # Article list items
                'div.content article a',  # Content area articles
                'div.article-box a'  # Article boxes
            ]
            
            for selector in selectors:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href', '')
                    if href and not href.endswith(self.base_url.split('/')[-1]):
                        full_url = f"https://www.e15.cz{href}" if not href.startswith('http') else href
                        if self._is_valid_article_url(full_url):
                            article_links.append(full_url)
            
            # Log the HTML if no links found
            if not article_links:
                logger.debug(f"HTML content: {response.text[:1000]}")
                logger.warning("No article links found")
            
            return list(set(article_links))  # Remove duplicates
            
        except Exception as e:
            logger.error(f"Error fetching article links: {str(e)}")
            return []
    
    def _scrape_article(self, url: str) -> Dict:
        """Scrape content from a single article"""
        try:
            # Add random delay
            time.sleep(random.uniform(2, 4))
            
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
            # More specific content selectors for e15.cz
            content_selectors = [
                'div.article-content p',  # Main article content
                'div.article-body p',     # Article body
                'div.content p',          # Generic content
                'article p'               # Fallback
            ]
            
            for selector in content_selectors:
                paragraphs = soup.select(selector)
                if paragraphs:
                    for p in paragraphs:
                        text = p.text.strip()
                        # Skip non-content elements
                        if text and not any(text.startswith(prefix) for prefix in [
                            'Foto:', 'Zdroj:', 'Související:', 'Autor:', 
                            'Sdílet:', 'Komentáře:', 'Tagy:', 'Kategorie:'
                        ]):
                            content.append(text)
                    break
            
            if not title or not content:
                logger.warning(f"Missing content for {url}")
                return None
                
            # Validate content length
            full_content = ' '.join(content)
            if len(full_content.split()) < 100:  # Require at least 100 words
                logger.warning(f"Content too short for {url}")
                return None
            
            return {
                'title': self._clean_text(title),
                'content': self._clean_text(full_content),
                'url': url,
                'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            logger.error(f"Error scraping article {url}: {str(e)}")
            return None
    
    def scrape_and_save(self, max_articles: int = 10):
        """Scrape articles and save them to files"""
        article_links = self._get_article_links()
        logger.info(f"Found {len(article_links)} articles")
        
        scraped_count = 0
        for url in article_links[:max_articles]:
            try:
                article = self._scrape_article(url)
                if article and article['content']:  # Only save if we got content
                    # Create a safe filename from the URL
                    filename = self._sanitize_filename(url.split('/')[-1])
                    if not filename:
                        filename = self._sanitize_filename(article['title'])
                    
                    # Save article as JSON
                    article_file = self.articles_dir / f"{filename}.txt"
                    with open(article_file, 'w', encoding='utf-8') as f:
                        json.dump(article, f, indent=2, ensure_ascii=False)
                    
                    scraped_count += 1
                    logger.info(f"Saved article: {article['title']}")
                    
                    if scraped_count >= max_articles:
                        break
                        
            except Exception as e:
                logger.error(f"Error processing article {url}: {str(e)}")
                continue
        
        logger.info(f"Successfully scraped {scraped_count} articles")

def main():
    parser = argparse.ArgumentParser(description='Scrape articles from e15.cz')
    parser.add_argument('--url', required=True, help='URL of the section to scrape')
    args = parser.parse_args()
    
    scraper = ArticleScraper(base_url=args.url)
    try:
        scraper.scrape_and_save(max_articles=10)
    except Exception as e:
        logger.error(f"Error in scraping process: {str(e)}")
        raise

if __name__ == "__main__":
    main() 