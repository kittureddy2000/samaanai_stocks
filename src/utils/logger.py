"""Logging configuration for the trading agent."""

import sys
from loguru import logger

import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config, LOGS_DIR


def setup_logger():
    """Configure the logger for the application."""
    # Remove default handler
    logger.remove()
    
    # Console handler with color
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=config.log_level,
        colorize=True
    )
    
    # File handler for all logs
    logger.add(
        LOGS_DIR / "trading.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="zip"
    )
    
    # Separate file for trades only
    logger.add(
        LOGS_DIR / "trades.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
        level="INFO",
        filter=lambda record: "TRADE" in record["message"] or "ORDER" in record["message"].upper(),
        rotation="5 MB",
        retention="90 days"
    )
    
    # Separate file for errors
    logger.add(
        LOGS_DIR / "errors.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation="5 MB",
        retention="30 days"
    )
    
    logger.info("Logger initialized")
    return logger


# Initialize on import
setup_logger()
