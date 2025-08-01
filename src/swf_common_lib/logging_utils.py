import logging
import json
from pythonjsonlogger.json import JsonFormatter
import requests
from datetime import datetime

class RestLogHandler(logging.Handler):
    """
    A logging handler that sends log records to a REST API endpoint.
    """
    def __init__(self, url, token=None):
        """
        Initializes the handler with the endpoint URL and an optional auth token.
        """
        super().__init__()
        self.url = url
        self.token = token

    def emit(self, record):
        """
        Emits a log record to the REST endpoint.
        """
        try:
            log_entry = self.format(record)
            headers = {'Content-type': 'application/json'}
            if self.token:
                headers['Authorization'] = f'Token {self.token}'
            
            response = requests.post(self.url, data=log_entry, headers=headers, timeout=5)
            response.raise_for_status() # Raise an exception for bad status codes
        except requests.RequestException as e:
            # Handle exceptions during the request (e.g., connection error, timeout)
            import sys
            sys.stderr.write(f"Failed to send log to {self.url}: {e}\n")

def setup_rest_logging(app_name, instance_name, base_url, token=None, level=logging.INFO):
    """
    Sets up a logger that sends records to a REST API endpoint.
    
    Args:
        app_name: Name of the application (e.g., 'example_agent')
        instance_name: Specific instance name (e.g., 'data-agent-1')
        base_url: Base URL of the REST API (e.g., 'http://localhost:8002')
        token: Optional authentication token
        level: Logging level (default: INFO)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(f"{app_name}.{instance_name}")
    logger.setLevel(level)
    logger.propagate = False

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    # Set up REST handler
    rest_url = f"{base_url}/api/v1/logs/"
    handler = RestLogHandler(rest_url, token=token)

    log_format = (
        '%(asctime)s %(name)s %(levelname)s %(module)s %(funcName)s %(lineno)d %(message)s'
    )

    formatter = JsonFormatter(log_format, rename_fields={
        'funcName': 'funcname'  # Rename to avoid SQL mixed-case issues
    })
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger
