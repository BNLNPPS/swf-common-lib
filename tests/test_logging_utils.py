import pytest
import logging
from unittest.mock import patch, MagicMock
import requests
from pythonjsonlogger.json import JsonFormatter

from swf_common_lib.logging_utils import setup_rest_logging, RestLogHandler


@patch('swf_common_lib.logging_utils.requests.post')
def test_rest_log_handler_emit(mock_post):
    """Test that the REST handler sends log records to the API endpoint."""
    # Arrange
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    handler = RestLogHandler('http://localhost:8002/api/v1/logs/', token='test-token')
    
    # Use JsonFormatter to match production setup
    log_format = '%(asctime)s %(name)s %(levelname)s %(module)s %(funcName)s %(lineno)d %(message)s'
    formatter = JsonFormatter(log_format, rename_fields={'funcName': 'funcname'})
    handler.setFormatter(formatter)

    logger = logging.getLogger('rest_test')
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Act
    logger.info("This is a test message")

    # Assert
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    
    # Check URL (first positional argument)
    assert call_args[0][0] == 'http://localhost:8002/api/v1/logs/'
    
    # Check headers (keyword argument)
    expected_headers = {
        'Content-type': 'application/json',
        'Authorization': 'Token test-token'
    }
    assert call_args[1]['headers'] == expected_headers
    
    # Check that data contains JSON log entry
    log_data = call_args[1]['data']
    assert 'This is a test message' in log_data
    assert 'INFO' in log_data


@patch('swf_common_lib.logging_utils.requests.post')
def test_rest_log_handler_no_token(mock_post):
    """Test that the handler works without authentication token."""
    # Arrange
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    handler = RestLogHandler('http://localhost:8002/api/v1/logs/')
    
    log_format = '%(asctime)s %(name)s %(levelname)s %(message)s'
    formatter = JsonFormatter(log_format)
    handler.setFormatter(formatter)

    logger = logging.getLogger('no_token_test')
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Act
    logger.info("Test without token")

    # Assert
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    
    # Check headers (should not include Authorization)
    expected_headers = {'Content-type': 'application/json'}
    assert call_args[1]['headers'] == expected_headers


@patch('swf_common_lib.logging_utils.requests.post')
def test_rest_log_handler_request_exception(mock_post, capsys):
    """Test that request exceptions are handled gracefully."""
    # Arrange
    mock_post.side_effect = requests.RequestException("Connection failed")
    
    handler = RestLogHandler('http://localhost:8002/api/v1/logs/')
    formatter = JsonFormatter('%(message)s')
    handler.setFormatter(formatter)

    logger = logging.getLogger('exception_test')
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Act
    logger.info("This should fail to send")

    # Assert
    captured = capsys.readouterr()
    assert "Failed to send log to http://localhost:8002/api/v1/logs/: Connection failed" in captured.err


def test_setup_rest_logging():
    """Test that setup_rest_logging creates a properly configured logger."""
    # Act
    logger = setup_rest_logging(
        app_name='test_app',
        instance_name='test_instance',
        base_url='http://localhost:8002',
        token='test-token',
        level=logging.DEBUG
    )

    # Assert
    assert logger.name == 'test_app.test_instance'
    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], RestLogHandler)
    
    # Check handler configuration
    handler = logger.handlers[0]
    assert handler.url == 'http://localhost:8002/api/v1/logs/'
    assert handler.token == 'test-token'
    
    # Check formatter
    formatter = handler.formatter
    assert isinstance(formatter, JsonFormatter)


@patch('swf_common_lib.logging_utils.requests.post')
def test_setup_rest_logging_integration(mock_post):
    """Test the complete setup_rest_logging integration."""
    # Arrange
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    # Act
    logger = setup_rest_logging(
        app_name='integration_test',
        instance_name='instance_1',
        base_url='http://localhost:8002'
    )
    
    logger.info("Integration test message", extra={'custom_field': 'custom_value'})

    # Assert
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    
    # Verify the log data contains expected fields
    log_data = call_args[1]['data']
    assert 'Integration test message' in log_data
    assert 'integration_test.instance_1' in log_data
    assert 'custom_field' in log_data
    assert 'funcname' in log_data  # Should be renamed from funcName