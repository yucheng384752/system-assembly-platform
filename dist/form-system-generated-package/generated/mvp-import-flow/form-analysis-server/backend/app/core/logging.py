"""
Logging configuration for the application.

Provides structured logging with JSON formatting for production
and human-readable format for development.
"""

import logging
import sys

import structlog
from structlog.typing import FilteringBoundLogger


def setup_logging(level: str = "INFO", format_type: str = "json") -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Format type ("json" for production, "console" for development)
    """
    import os
    from logging.handlers import RotatingFileHandler

    from dotenv import load_dotenv

    # Load logging configuration from environment
    load_dotenv(".env.logging")

    # Get configuration from environment variables with defaults
    log_level_str = os.getenv("LOG_LEVEL", level).upper()
    log_format = os.getenv("LOG_FORMAT", format_type)
    log_dir = os.getenv("LOG_DIR", "logs")
    max_log_size = int(os.getenv("MAX_LOG_SIZE", "10485760"))  # 10MB
    backup_count = int(os.getenv("BACKUP_COUNT", "5"))
    log_encoding = os.getenv("LOG_ENCODING", "utf-8")

    # Create logs directory if it doesn't exist
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Configure standard library logging with file handler
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # File handler with rotation
    app_log_file = os.getenv("APP_LOG_FILE", "app.log")
    file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, app_log_file),
        maxBytes=max_log_size,
        backupCount=backup_count,
        encoding=log_encoding,
    )
    file_handler.setLevel(log_level)

    # Error file handler for errors only
    error_log_file = os.getenv("ERROR_LOG_FILE", "error.log")
    error_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, error_log_file),
        maxBytes=max_log_size,
        backupCount=backup_count,
        encoding=log_encoding,
    )
    error_handler.setLevel(logging.ERROR)

    # Clear existing handlers to avoid duplicates
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Configure root logger
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=[console_handler, file_handler, error_handler],
        force=True,  # Force reconfiguration
    )

    # Configure processors based on format
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # Add performance logging processor if enabled
    if os.getenv("ENABLE_PERFORMANCE_LOGGING", "true").lower() == "true":
        processors.append(structlog.processors.CallsiteParameterAdder())

    # Add request ID processor if enabled
    if os.getenv("ENABLE_REQUEST_ID", "true").lower() == "true":
        processors.append(structlog.contextvars.merge_contextvars)

    if log_format == "json":
        # Production: JSON formatting
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Development: Human readable
        processors.extend(
            [
                structlog.dev.ConsoleRenderer(colors=True),
            ]
        )

    # Configure structlog to use standard library logging
    # This ensures logs go to both console and files
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),  # 使用標準 logging
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> FilteringBoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        FilteringBoundLogger: Configured logger instance

    Example:
        ```python
        logger = get_logger(__name__)
        logger.info("User logged in", user_id=123, ip="192.168.1.1")
        ```
    """
    return structlog.get_logger(name)
