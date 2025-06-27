import logging
import json
import psycopg2
from psycopg2 import extras
from pythonjsonlogger.json import JsonFormatter
import requests

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
                'timestamp', 'level_name', 'message', 'module',
                'func_name', 'line_no', 'process', 'thread'
            }
            extra_data = {k: v for k, v in log_dict.items() if k not in standard_fields}

            insert_sql = """
                INSERT INTO app_logs (
                    timestamp, level_name, message, module, func_name,
                    line_no, process, thread, extra_data
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            self.cursor.execute(insert_sql, (
                log_dict.get('timestamp'),
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
        '%(timestamp)s %(levelname)s %(name)s %(message)s '
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
