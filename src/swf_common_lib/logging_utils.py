import logging
import json
import psycopg2
from psycopg2 import extras
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

class PostgresLogHandler(logging.Handler):
    """
    A logging handler that writes log records to a PostgreSQL database.
    """
    def __init__(self, db_params):
        """
        Initializes the handler with database connection parameters.
        `db_params` should be a dictionary suitable for psycopg2.connect().
        """
        super().__init__()
        self.db_params = db_params
        self.conn = None
        self.cursor = None
        self._connect()

    def _connect(self):
        """Establishes the database connection."""
        try:
            self.conn = psycopg2.connect(**self.db_params)
            self.cursor = self.conn.cursor()
            # It's good practice to create the table if it doesn't exist
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_logs (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL,
                    level_name VARCHAR(50),
                    message TEXT,
                    module VARCHAR(255),
                    func_name VARCHAR(255),
                    line_no INT,
                    process INT,
                    thread INT,
                    extra_data JSONB
                );
            """)
            self.conn.commit()
        except psycopg2.Error as e:
            # If we can't connect, we can't log to the DB.
            # For now, we'll print to stderr. A more robust solution
            # might involve a fallback handler.
            import sys
            sys.stderr.write(f"Could not connect to PostgreSQL for logging: {e}\n")
            self.conn = None
            self.cursor = None

    def _parse_timestamp(self, timestamp_str):
        """
        Parse timestamp string with robust handling of different formats.
        
        Handles:
        - Python logging format with comma: "2025-07-18 09:52:47,308"
        - Python logging format with dot: "2025-07-18 09:52:47.308"  
        - ISO format with Z: "2025-07-18T09:52:47.308Z"
        - ISO format with timezone: "2025-07-18T09:52:47.308+00:00"
        
        Args:
            timestamp_str: The timestamp string to parse
            
        Returns:
            datetime object or None if parsing fails
        """
        import re
        import warnings
        
        # Try Python logging format with comma (milliseconds)
        try:
            return datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
        except ValueError:
            pass
            
        # Try Python logging format with dot (milliseconds)
        try:
            return datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            pass
            
        # Handle milliseconds that might not be padded to 6 digits
        # Match formats like "2025-07-18 09:52:47.123" or "2025-07-18 09:52:47,123"
        match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,.](\d+)', timestamp_str)
        if match:
            base_time_str, fraction_str = match.groups()
            # Pad or truncate to 6 digits (microseconds)
            fraction_padded = fraction_str.ljust(6, '0')[:6]
            full_timestamp = f"{base_time_str}.{fraction_padded}"
            try:
                return datetime.strptime(full_timestamp, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                pass
        
        # Try ISO formats
        try:
            if timestamp_str.endswith('Z'):
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                return datetime.fromisoformat(timestamp_str)
        except ValueError:
            pass
            
        # Last resort: use current time and warn
        warnings.warn(f"Could not parse timestamp '{timestamp_str}', using current time")
        return datetime.now()

    def emit(self, record):
        """
        Emits a log record to the database.
        """
        if not self.conn or not self.cursor:
            return  # Can't log if not connected

        try:
            log_entry = self.format(record)
            # The formatter will produce a JSON string, we need to parse it back to a dict
            log_dict = self.json_loads(log_entry)

            # Separate standard fields from extra data
            standard_fields = {
                'asctime', 'level_name', 'message', 'module',
                'func_name', 'line_no', 'process', 'thread'
            }
            extra_data = {k: v for k, v in log_dict.items() if k not in standard_fields}

            # Parse timestamp string to datetime object
            timestamp_str = log_dict.get('asctime')
            timestamp_obj = None
            if timestamp_str:
                timestamp_obj = self._parse_timestamp(timestamp_str)

            insert_sql = """
                INSERT INTO app_logs (
                    timestamp, level_name, message, module, func_name,
                    line_no, process, thread, extra_data
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            self.cursor.execute(insert_sql, (
                timestamp_obj,
                log_dict.get('level_name'),
                log_dict.get('message'),
                log_dict.get('module'),
                log_dict.get('func_name'),
                log_dict.get('line_no'),
                log_dict.get('process'),
                log_dict.get('thread'),
                extras.Json(extra_data) if extra_data else None
            ))
            self.conn.commit()
        except (psycopg2.Error, TypeError) as e:
            # Handle potential reconnection logic or other errors
            import sys
            sys.stderr.write(f"Failed to write log to PostgreSQL: {e}\n")
            self._connect() # Attempt to reconnect

    def close(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
        super().close()

    def json_loads(self, log_entry_str):
        return json.loads(log_entry_str)

def setup_logger(name, db_params, level=logging.INFO):
    """
    Sets up a logger that sends records to PostgreSQL.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    handler = PostgresLogHandler(db_params)

    log_format = (
        '%(asctime)s %(levelname)s %(name)s %(message)s '
        '%(module)s %(funcName)s %(lineno)d %(process)d %(thread)d'
    )
    rename_map = {
        "levelname": "level_name",
        "funcName": "func_name",
        "lineno": "line_no",
    }

    formatter = JsonFormatter(log_format, rename_fields=rename_map)
    handler.setFormatter(formatter)

    if not any(isinstance(h, PostgresLogHandler) for h in logger.handlers):
        logger.addHandler(handler)

    return logger
