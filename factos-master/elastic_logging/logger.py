import logging
from django.conf import settings
from django.utils import timezone
from elasticsearch import Elasticsearch
from celery import current_task
from datetime import datetime

import json

class ElasticLogger:
    """
    ElasticSearch logger for application.

    Automatically captures task_id from Celery context and timestamps
    in Bogota timezone. Falls back to standard Python logging if
    ElasticSearch is unavailable.

    Features automatic reconnection with exponential backoff if ES fails.

    Usage:
        from elastic_logging.logger import ElasticLogger
        logger = ElasticLogger()
        logger.info("Processing started")
        logger.error("Something went wrong")
    """

    def __init__(self):
        self.es_client = None
        self.fallback_logger = logging.getLogger(__name__)
        self.last_connection_attempt = None
        self.retry_delay = 60  # Initial retry delay in seconds
        self.max_retry_delay = 3600  # Maximum retry delay (1 hour)
        self._setup_elasticsearch()

    def _should_retry_connection(self):
        """Check if enough time has passed to retry ES connection."""
        if self.last_connection_attempt is None:
            return True

        elapsed = (datetime.now() - self.last_connection_attempt).total_seconds()
        return elapsed >= self.retry_delay

    def _increase_retry_delay(self):
        """Exponential backoff for retries."""
        self.retry_delay = min(self.retry_delay * 2, self.max_retry_delay)
        self.fallback_logger.info(f"Next ES connection attempt in {self.retry_delay}s")

    def _setup_elasticsearch(self):
        """Initialize ElasticSearch client if enabled."""
        self.last_connection_attempt = datetime.now()

        try:
            if not settings.CONFIG_ELASTICSEARCH['ENABLED']:
                self.fallback_logger.info("ElasticSearch logging is disabled")
                return

            self.es_client = Elasticsearch(
                [settings.CONFIG_ELASTICSEARCH['HOST']],
                basic_auth=(
                    settings.CONFIG_ELASTICSEARCH['USERNAME'],
                    settings.CONFIG_ELASTICSEARCH['PASSWORD']
                ),
                verify_certs=True,
                timeout=10
            )

            # Test connection
            if self.es_client.ping():
                self.fallback_logger.info("ElasticSearch connection established")
                self.retry_delay = 60  # Reset delay on success
            else:
                self.fallback_logger.warning("ElasticSearch ping failed, will retry later")
                self.es_client = None
                self._increase_retry_delay()

        except Exception as e:
            self.fallback_logger.error(f"Failed to setup ElasticSearch: {str(e)}")
            self.es_client = None
            self._increase_retry_delay()

    def _get_task_id(self):
        """Get current Celery task ID or None if not in task context."""
        try:
            if current_task and current_task.request:
                return current_task.request.id
        except (AttributeError, RuntimeError):
            pass
        return None

    def _log(self, level, message, extra=None):
        """
        Send log to ElasticSearch with fallback to standard logging.

        Automatically retries connection if ES was previously unavailable.

        Args:
            level (str): Log level (INFO, ERROR, WARNING, DEBUG)
            message (str): Log message
            extra (dict, optional): Additional fields to include in log entry
        """
        # Retry connection if enough time has passed
        if self.es_client is None and self._should_retry_connection():
            self._setup_elasticsearch()

        # Create log entry
        log_entry = {
            'message': message,
            'level': level,
            'task_id': self._get_task_id(),
            'timestamp': timezone.now().isoformat()
        }

        # Add extra fields if provided
        if extra and isinstance(extra, dict):
            log_entry['extra_data'] = json.dumps(extra)

        # Try to send to ElasticSearch
        if self.es_client:
            try:
                response = self.es_client.index(
                    index=settings.CONFIG_ELASTICSEARCH['INDEX'],
                    body=log_entry
                )
                # Optionally log successful ES indexing at debug level
                if response.get('result') == 'created':
                    pass  # ES log successful
                return  # Success, don't use fallback

            except Exception as e:
                # ES failed, mark as unavailable and increase retry delay
                self.fallback_logger.error(f"ElasticSearch logging failed: {str(e)}")
                self.es_client = None
                self._increase_retry_delay()

        # Use fallback logging
        self._fallback_log(level, message, log_entry)

    def _fallback_log(self, level, message, log_entry=None):
        """Fallback to standard Python logging."""
        log_msg = f"[{log_entry.get('task_id', 'NO_TASK')}] {message}"

        if level == 'ERROR':
            self.fallback_logger.error(log_msg)
        elif level == 'WARNING':
            self.fallback_logger.warning(log_msg)
        elif level == 'DEBUG':
            self.fallback_logger.debug(log_msg)
        else:  # INFO and others
            self.fallback_logger.info(log_msg)

    def info(self, message, extra=None):
        """Log info level message."""
        self._log('INFO', message, extra)

    def error(self, message, extra=None):
        """Log error level message."""
        self._log('ERROR', message, extra)

    def warning(self, message, extra=None):
        """Log warning level message."""
        self._log('WARNING', message, extra)

    def debug(self, message, extra=None):
        """Log debug level message."""
        self._log('DEBUG', message, extra)


# Convenience instance - can be imported directly
elastic_logger = ElasticLogger()