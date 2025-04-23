import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging():
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            RotatingFileHandler('logs/app.log', maxBytes=10000000, backupCount=5),
            logging.StreamHandler()
        ]
    )

    # Create logger
    logger = logging.getLogger(__name__)
    return logger 