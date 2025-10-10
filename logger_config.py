"""
Logger Configuration for OZZY SIMPLE Trading Bot

Sets up structured logging with loguru for console and file outputs.
"""
from loguru import logger
import sys
import os


def setup_logger():
    """
    Configure loguru logger with console and file handlers.
    
    - Console: INFO and above with colors
    - File: DEBUG and above with daily rotation
    - Error file: ERROR and above with 90-day retention
    """
    # Remove default handler
    logger.remove()
    
    # Console handler (INFO and above)
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True
    )
    
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # File handler (DEBUG and above, with rotation)
    logger.add(
        "logs/bot_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="00:00",  # New file at midnight
        retention="30 days",  # Keep logs for 30 days
        compression="zip"  # Compress old logs
    )
    
    # Error file handler (ERROR and above)
    logger.add(
        "logs/errors_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation="00:00",
        retention="90 days"
    )
    
    logger.info("Logger initialized successfully")
