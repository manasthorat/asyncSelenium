"""
Logging configuration for the web scraper.

This module sets up structured logging with both file and console output,
including session tracking and performance metrics.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import json
from datetime import datetime
from colorlog import ColoredFormatter
import structlog
from contextlib import contextmanager
import time

from ..config.settings import get_settings

# Get settings
settings = get_settings()


class SessionLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that adds session context to all log messages."""
    
    def process(self, msg, kwargs):
        """Add session_id to the log record."""
        if 'extra' not in kwargs:
            kwargs['extra'] = {}
        kwargs['extra']['session_id'] = self.extra.get('session_id', 'MAIN')
        return msg, kwargs


class PerformanceLogger:
    """Logger for tracking performance metrics."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.metrics = {}
    
    @contextmanager
    def track_duration(self, operation: str, **extra_fields):
        """Context manager to track operation duration."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.logger.info(
                f"Performance metric: {operation}",
                extra={
                    'operation': operation,
                    'duration_seconds': round(duration, 3),
                    'metric_type': 'duration',
                    **extra_fields
                }
            )
    
    def log_metric(self, metric_name: str, value: float, unit: str = '', **extra_fields):
        """Log a custom metric."""
        self.logger.info(
            f"Performance metric: {metric_name}",
            extra={
                'metric_name': metric_name,
                'value': value,
                'unit': unit,
                'metric_type': 'gauge',
                **extra_fields
            }
        )


def setup_logging():
    """Configure logging for the entire application."""
    
    # Create logs directory if it doesn't exist
    settings.logging.ensure_log_dir()
    
    # Configure structlog for structured logging
    structlog.configure(
        processors=[
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.logging.log_level.upper()))
    
    # Remove existing handlers
    root_logger.handlers = []
    
    # Create formatters
    file_formatter = logging.Formatter(
        settings.logging.log_format,
        datefmt=settings.logging.date_format
    )
    
    # Console formatter with colors
    console_formatter = ColoredFormatter(
        '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - [%(session_id)s] - %(message)s%(reset)s',
        datefmt=settings.logging.date_format,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        settings.logging.log_file_path,
        maxBytes=settings.logging.log_max_size_mb * 1024 * 1024,
        backupCount=settings.logging.log_backup_count
    )
    file_handler.setLevel(logging.DEBUG)  # Log everything to file
    file_handler.setFormatter(file_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.logging.log_level.upper()))
    console_handler.setFormatter(console_formatter)
    
    # Error file handler for ERROR and above
    error_file_handler = logging.handlers.RotatingFileHandler(
        settings.logging.log_file_path.parent / 'errors.log',
        maxBytes=settings.logging.log_max_size_mb * 1024 * 1024,
        backupCount=settings.logging.log_backup_count
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(file_formatter)
    
    # Add handlers to root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(error_file_handler)
    
    # Add default session_id to records that don't have one
    old_factory = logging.getLogRecordFactory()
    
    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        if not hasattr(record, 'session_id'):
            record.session_id = 'SYSTEM'
        return record
    
    logging.setLogRecordFactory(record_factory)
    
    # Log startup message
    logger = get_logger('setup')
    logger.info("Logging system initialized", extra={
        'log_level': settings.logging.log_level,
        'log_file': str(settings.logging.log_file_path),
        'settings': {
            'max_concurrent_sessions': settings.scraping.max_concurrent_sessions,
            'genres': settings.scraping.genres_to_scrape
        }
    })


def get_logger(name: str, session_id: Optional[str] = None) -> SessionLoggerAdapter:
    """
    Get a logger instance with optional session context.
    
    Args:
        name: Logger name (usually __name__)
        session_id: Optional session ID for context
    
    Returns:
        Logger adapter with session context
    """
    logger = logging.getLogger(name)
    if session_id:
        return SessionLoggerAdapter(logger, {'session_id': session_id})
    return SessionLoggerAdapter(logger, {'session_id': 'MAIN'})


def get_performance_logger(name: str) -> PerformanceLogger:
    """Get a performance logger instance."""
    return PerformanceLogger(logging.getLogger(f"{name}.performance"))


def log_exception(logger: logging.Logger, exc: Exception, context: Dict[str, Any] = None):
    """
    Log an exception with context.
    
    Args:
        logger: Logger instance
        exc: Exception to log
        context: Additional context information
    """
    error_details = {
        'error_type': type(exc).__name__,
        'error_message': str(exc),
        'timestamp': datetime.utcnow().isoformat()
    }
    
    if context:
        error_details.update(context)
    
    logger.error(
        f"Exception occurred: {type(exc).__name__}: {str(exc)}",
        exc_info=True,
        extra={'error_details': error_details}
    )


def create_audit_logger() -> logging.Logger:
    """Create a separate audit logger for tracking important events."""
    audit_logger = logging.getLogger('audit')
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False  # Don't propagate to root logger
    
    # Create audit file handler
    audit_handler = logging.handlers.RotatingFileHandler(
        settings.logging.log_file_path.parent / 'audit.log',
        maxBytes=settings.logging.log_max_size_mb * 1024 * 1024,
        backupCount=settings.logging.log_backup_count
    )
    
    # JSON formatter for audit logs
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_obj = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': record.levelname,
                'event': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
            }
            if hasattr(record, 'event_data'):
                log_obj['event_data'] = record.event_data
            return json.dumps(log_obj)
    
    audit_handler.setFormatter(JSONFormatter())
    audit_logger.addHandler(audit_handler)
    
    return audit_logger


# Initialize logging when module is imported
setup_logging()

# Create module-level loggers
logger = get_logger(__name__)
performance_logger = get_performance_logger(__name__)
audit_logger = create_audit_logger()