"""
Centralized logging configuration for the power manager application.
"""
import logging
import sys
from typing import Optional


def setup_logging(level: str = "INFO", format_string: Optional[str] = None) -> None:
    """
    Configure the root logger for the application.
    
    When run as a systemd service, journald will automatically capture stdout.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string for log messages
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Default format if none provided
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format=format_string,
        stream=sys.stdout,
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Set specific loggers to appropriate levels
    # Reduce noise from requests/urllib3
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    # Application loggers
    app_logger = logging.getLogger("powermgr")
    app_logger.setLevel(numeric_level)
    
    app_logger.info(f"Logging configured at level: {level}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.
    
    Args:
        name: Logger name, typically __name__ or class name
        
    Returns:
        logging.Logger: Configured logger instance
    """
    return logging.getLogger(name)
