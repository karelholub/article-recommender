"""
Article model for the BERT-MVP project.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional


@dataclass
class Article:
    """Article model representing a news article."""
    
    id: str
    title: str
    content: str
    url: str
    scraped_at: datetime
    vector: Optional[List[float]] = None
    labels: List[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Article':
        """
        Create an Article instance from a dictionary.
        
        Args:
            data: Dictionary containing article data
            
        Returns:
            An Article instance
        """
        # Parse scraped_at datetime
        scraped_at = datetime.strptime(
            data.get('scraped_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            '%Y-%m-%d %H:%M:%S'
        )
        
        # Determine labels based on content characteristics
        labels = []
        content = data.get('content', '')
        
        # Add labels based on content length
        if len(content.split()) > 2000:  # Long read
            labels.append('Long Read')
        elif len(content.split()) < 500:  # Short read
            labels.append('Short Read')
            
        # Add labels based on title keywords
        title_lower = data.get('title', '').lower()
        if any(word in title_lower for word in ['analysis', 'analyze', 'study', 'research']):
            labels.append('Analysis')
        if any(word in title_lower for word in ['interview', 'q&a', 'qa', 'conversation']):
            labels.append('Interview')
        
        return cls(
            id=data.get('id', ''),
            title=data.get('title', ''),
            content=content,
            url=data.get('url', ''),
            scraped_at=scraped_at,
            vector=data.get('vector'),
            labels=labels
        )
    
    def to_dict(self) -> Dict:
        """
        Convert the Article instance to a dictionary.
        
        Returns:
            A dictionary representation of the Article
        """
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'url': self.url,
            'scraped_at': self.scraped_at.strftime('%Y-%m-%d %H:%M:%S'),
            'vector': self.vector,
            'labels': self.labels
        } 