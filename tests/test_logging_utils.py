import pytest
import logging
from unittest.mock import patch, MagicMock
import psycopg2
from pythonjsonlogger import jsonlogger

from swf_common_lib.logging_utils import setup_logger, PostgresLogHandler

# Mock database parameters
DB_PARAMS = {
    'dbname': 'testdb',
    'user': 'testuser',
    'password': 'testpass',
    'host': 'localhost',
    'port': '5432'
}

@patch('swf_common_lib.logging_utils.psycopg2.connect')
def test_setup_logger(mock_connect):
    """Test that the logger is set up correctly."""
    # Arrange
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    # Act
    logger = setup_logger('test_logger', db_params=DB_PARAMS, level=logging.DEBUG)

    # Assert
    assert logger.name == 'test_logger'
    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], PostgresLogHandler)
    mock_connect.assert_called_once_with(**DB_PARAMS)
    mock_cursor.execute.assert_called_once() # For the CREATE TABLE IF NOT EXISTS
    mock_conn.commit.assert_called_once()

@patch('swf_common_lib.logging_utils.psycopg2.connect')
@patch('swf_common_lib.logging_utils.extras.Json')
def test_postgres_log_handler_emit(mock_json, mock_connect):
    """Test that the handler tries to insert a log record into the DB."""
    # Arrange
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    def json_side_effect(data):
        instance = MagicMock()
        instance.adapted = data
        return instance
    mock_json.side_effect = json_side_effect

    handler = PostgresLogHandler(db_params=DB_PARAMS)
    log_format = (
        '%(timestamp)s %(levelname)s %(name)s %(message)s '
        '%(module)s %(funcName)s %(lineno)d %(process)d %(thread)d'
    )
    rename_map = {
        "levelname": "level_name",
        "funcName": "func_name",
        "lineno": "line_no",
    }
    formatter = jsonlogger.JsonFormatter(log_format, rename_fields=rename_map)
    handler.setFormatter(formatter)

    logger = logging.getLogger('emit_test')
    # Clear existing handlers
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Act
    extra_info = {'request_id': '12345'}
    logger.info("This is a test message", extra=extra_info)

    # Assert
    # Check that execute was called twice: once for CREATE TABLE, once for INSERT
    assert mock_cursor.execute.call_count == 2
    insert_call_args = mock_cursor.execute.call_args[0][0]
    assert "INSERT INTO app_logs" in insert_call_args

    # Check that the log data was passed correctly
    insert_call_data = mock_cursor.execute.call_args[0][1]
    assert insert_call_data[1] == 'INFO'  # level_name
    assert insert_call_data[2] == 'This is a test message' # message
    # The last argument should be a Json object containing the extra data
    extra_data_json = insert_call_data[-1]
    assert extra_data_json.adapted['request_id'] == '12345'

@patch('swf_common_lib.logging_utils.psycopg2.connect')
def test_handler_connection_failure(mock_connect, capsys):
    """Test that a connection failure is handled gracefully."""
    # Arrange
    mock_connect.side_effect = psycopg2.Error("Connection failed")

    # Act
    handler = PostgresLogHandler(db_params=DB_PARAMS)
    logger = logging.getLogger('failure_test')
    logger.addHandler(handler)
    logger.info("This should not be logged to the db")

    # Assert
    captured = capsys.readouterr()
    assert "Could not connect to PostgreSQL for logging: Connection failed" in captured.err
    # The cursor should not have been called
    assert not handler.cursor
