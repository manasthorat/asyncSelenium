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
from contextlib import contextmanager
import time

# We'll initialize these after setup_logging is called
_settings = None
_setup_complete = False


class SessionContext:
    """Thread-local storage for session context."""
    import threading
    _local = threading.local()
    
    @classmethod
    def set_session_id(cls, session_id: str):
        cls._local.session_id = session_id
    
    @classmethod
    def get_session_id(cls) -> str:
        return getattr(cls._local, 'session_id', 'SYSTEM')


class SessionFilter(logging.Filter):
    """Filter that adds session_id to log records."""
    
    def filter(self, record):
        record.session_id = SessionContext.get_session_id()
        return True


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
    global _settings, _setup_complete
    
    if _setup_complete:
        return
    
    # Import settings here to avoid circular import
    from ..config.settings import get_settings
    _settings = get_settings()
    
    # Create logs directory if it doesn't exist
    _settings.logging.ensure_log_dir()
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, _settings.logging.log_level.upper()))
    
    # Remove existing handlers
    root_logger.handlers = []
    
    # Create formatters - using simpler format without session_id in formatter
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(session_id)s] - %(message)s',
        datefmt=_settings.logging.date_format
    )
    
    # Console formatter without colors for simplicity (you can add colorlog back later)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(session_id)s] - %(message)s',
        datefmt=_settings.logging.date_format
    )
    
    # Create session filter
    session_filter = SessionFilter()
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        _settings.logging.log_file_path,
        maxBytes=_settings.logging.log_max_size_mb * 1024 * 1024,
        backupCount=_settings.logging.log_backup_count
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(session_filter)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, _settings.logging.log_level.upper()))
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(session_filter)
    
    # Error file handler
    error_file_handler = logging.handlers.RotatingFileHandler(
        _settings.logging.log_file_path.parent / 'errors.log',
        maxBytes=_settings.logging.log_max_size_mb * 1024 * 1024,
        backupCount=_settings.logging.log_backup_count
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(file_formatter)
    error_file_handler.addFilter(session_filter)
    
    # Add handlers to root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(error_file_handler)
    
    _setup_complete = True
    
    # Log startup message
    logger = logging.getLogger('setup')
    logger.info("Logging system initialized", extra={
        'config': {
            'log_level': _settings.logging.log_level,
            'log_file': str(_settings.logging.log_file_path),
            'max_concurrent_sessions': _settings.scraping.max_concurrent_sessions,
            'genres': _settings.scraping.genres_to_scrape
        }
    })


def get_logger(name: str, session_id: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance with optional session context.
    
    Args:
        name: Logger name (usually __name__)
        session_id: Optional session ID for context
    
    Returns:
        Logger instance
    """
    if not _setup_complete:
        setup_logging()
    
    if session_id:
        # Store session ID in thread-local storage
        SessionContext.set_session_id(session_id)
    
    return logging.getLogger(name)


def set_session_id(session_id: str):
    """Set the session ID for the current thread."""
    SessionContext.set_session_id(session_id)


def get_performance_logger(name: str) -> PerformanceLogger:
    """Get a performance logger instance."""
    if not _setup_complete:
        setup_logging()
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
    if not _setup_complete:
        setup_logging()
    
    audit_logger = logging.getLogger('audit')
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    
    # Create audit file handler
    audit_handler = logging.handlers.RotatingFileHandler(
        _settings.logging.log_file_path.parent / 'audit.log',
        maxBytes=_settings.logging.log_max_size_mb * 1024 * 1024,
        backupCount=_settings.logging.log_backup_count
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
                'session_id': getattr(record, 'session_id', 'SYSTEM')
            }
            if hasattr(record, 'event_data'):
                log_obj['event_data'] = record.event_data
            return json.dumps(log_obj)
    
    audit_handler.setFormatter(JSONFormatter())
    audit_handler.addFilter(SessionFilter())
    audit_logger.addHandler(audit_handler)
    
    return audit_logger


# Don't auto-initialize on import to avoid circular dependency
# setup_logging will be called when first logger is requested