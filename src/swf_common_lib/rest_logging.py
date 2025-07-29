"""
REST logging module for swf-monitor agents.

This module provides a simple way for agents to send logs to the swf-monitor
database via REST API using standard Python logging.
"""

import logging
import requests
from datetime import datetime


class RestLogHandler(logging.Handler):
    """Logging handler that sends logs to swf-monitor REST API."""
    
    def __init__(self, base_url, app_name, instance_name, fallback_handler=None, timeout=5):
        super().__init__()
        self.logs_url = f"{base_url.rstrip('/')}/api/v1/logs/"
        self.app_name = app_name
        self.instance_name = instance_name
        self.session = requests.Session()
        self.connection_failed = False
        self.fallback_handler = fallback_handler
        self.timeout = timeout
        
    def emit(self, record):
        """Send log record to REST API."""
        try:
            log_data = {
                'app_name': self.app_name,
                'instance_name': self.instance_name,
                'timestamp': datetime.fromtimestamp(record.created).isoformat(),
                'level': record.levelno,
                'level_name': record.levelname,
                'message': record.getMessage(),
                'module': record.module or 'unknown',
                'func_name': record.funcName or 'unknown',
                'line_no': record.lineno or 0,
                'process': record.process or 0,
                'thread': record.thread or 0,
            }
            
            response = self.session.post(self.logs_url, json=log_data, timeout=self.timeout)
            response.raise_for_status()
            
        except Exception as e:
            # Print warning and fall back to standard logging on first failure
            if not self.connection_failed:
                print(f"WARNING: REST logging failed to send log to swf-monitor at {self.logs_url}: {e}")
                print("WARNING: REST logging falling back to standard console logging")
                self.connection_failed = True
            
            # Fall back to console handler if available
            if self.fallback_handler:
                self.fallback_handler.emit(record)
            else:
                # This should not happen if setup_rest_logging() was used correctly
                print(f"WARNING: REST logging has no fallback handler configured")
                print(f"{record.levelname}: {record.getMessage()}")


def setup_rest_logging(app_name, instance_name, base_url='http://localhost:8000', timeout=5):
    """
    Setup REST logging for an agent.
    
    Args:
        app_name: Name of your application/agent
        instance_name: Unique identifier for this instance
        base_url: URL of swf-monitor service
        timeout: Timeout in seconds for REST requests (default: 5)
    
    Returns:
        Configured logger ready to use
    """
    logger = logging.getLogger(app_name)
    
    # Clear existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    logger.setLevel(logging.DEBUG)
    
    # Create console fallback handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(formatter)
    
    # Add REST handler with fallback capability
    rest_handler = RestLogHandler(base_url, app_name, instance_name, console_handler, timeout)
    logger.addHandler(rest_handler)
    
    return logger