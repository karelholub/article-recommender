"""
User model for the BERT-MVP project.
"""
from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class User:
    """User model representing a user of the recommendation system."""
    
    id: str
    read_articles: List[str]
    preferences: Optional[Dict] = None
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'User':
        """
        Create a User instance from a dictionary.
        
        Args:
            data: Dictionary containing user data
            
        Returns:
            A User instance
        """
        return cls(
            id=data.get('id', ''),
            read_articles=data.get('read_articles', []),
            preferences=data.get('preferences', {})
        )
    
    def to_dict(self) -> Dict:
        """
        Convert the User instance to a dictionary.
        
        Returns:
            A dictionary representation of the User
        """
        return {
            'id': self.id,
            'read_articles': self.read_articles,
            'preferences': self.preferences or {}
        } 