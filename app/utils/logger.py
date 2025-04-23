"""
Logging configuration for the BERT-MVP project.
"""
import logging
import logging.handlers
import os
from pathlib import Path
from config.default import LOG_LEVEL, LOG_FORMAT, LOG_FILE

def setup_logger(name: str) -> logging.Logger:
    """
    Set up a logger with the specified name.
    
    Args:
        name: The name of the logger
        
    Returns:
        A configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL))
    
    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Create file handler
    log_dir = Path(LOG_FILE).parent
    os.makedirs(log_dir, exist_ok=True)
    
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger 