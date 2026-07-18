"""
logger.py — Structured Logging Utility
========================================
Provides a configured logger for every module in the project.

WHY STRUCTURED LOGGING?
------------------------
Without proper logging, when something breaks at 2 AM you have NO idea what happened.
With structured logging:
  - Every error has a timestamp, file name, and context
  - You can filter logs by severity (DEBUG / INFO / WARNING / ERROR)
  - You can see EXACTLY which API call failed, with which customer, at what time

HOW TO USE:
-----------
In any file, instead of using the default logger:

    import logging
    logger = logging.getLogger(__name__)

Just import our pre-configured version and it inherits all settings.
The __name__ variable automatically becomes the module path 
(e.g., "backend.ai.email_generator") which makes log lines easier to trace.
"""

import logging
import sys
from datetime import datetime


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configures the root logger for the entire application.
    
    Call this ONCE in main.py at startup.
    All other modules use logging.getLogger(__name__) and inherit this config.
    
    Parameters:
    -----------
    log_level : str
        Minimum log level to show: DEBUG | INFO | WARNING | ERROR | CRITICAL
        Set to "DEBUG" during development to see all messages.
        Set to "INFO" or "WARNING" in production to reduce noise.
    """
    
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Format: time | level | module | message
    # Example: 10:22:45 | INFO     | backend.ai.email_generator | ✅ Email generated
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    
    # Console handler — prints to terminal
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    
    # Quieten noisy third-party libraries
    # aiohttp floods logs with connection details we don't need
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    # uvicorn has its own logging, don't duplicate it
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Returns a named logger.
    
    Usage:
    ------
    from backend.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Something happened")
    logger.error("Something broke")
    logger.debug("Detailed trace info")  # Only shows when log_level=DEBUG
    """
    return logging.getLogger(name)
