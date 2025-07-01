# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Testing
- `./run_tests.sh` - Run tests with automatic virtual environment management
- Uses pytest framework with comprehensive mocking
- Test runner enforces execution from repository root for consistency

### Building and Installation
**CRITICAL: Always activate virtual environment first: `source venv/bin/activate`**
- `source venv/bin/activate && pip install -e .` - Install in development mode (editable install)
- `source venv/bin/activate && python -m build` - Build distribution packages
- `source venv/bin/activate && pip install .[test]` - Install with test dependencies

### Publishing
- Automated publishing to TestPyPI on version tags (v*)
- Manual publishing: `twine upload dist/*`

## Architecture Overview

### Shared Utility Library
This is the common utilities library for the SWF (Streaming Workflow) testbed ecosystem. It provides reusable components that are shared across multiple SWF projects including swf-testbed, swf-monitor, and various agent repositories.

### Core Functionality

#### Logging Infrastructure
The primary purpose of this library is to provide specialized logging capabilities for distributed systems:

- **RestLogHandler**: Sends log records to REST API endpoints with authentication
- **PostgresLogHandler**: Writes structured log records directly to PostgreSQL database  
- **setup_logger()**: Convenience function for setting up PostgreSQL logging
- **JSON Formatting**: Structured logging with field renaming and extra data support

#### Key Features
- Graceful error handling for network failures and database connection issues
- Automatic database table creation for PostgreSQL logging
- Authentication support for REST API logging
- Configurable field mapping and JSON structure
- Fallback error reporting when primary logging fails

## Code Organization

### Package Structure
```
src/swf_common_lib/
└── logging_utils.py  # Main logging utilities module
```

### Core Modules
- **logging_utils.py**: Contains all logging handler classes and utility functions
  - `RestLogHandler` class for HTTP-based logging
  - `PostgresLogHandler` class for database logging
  - `setup_logger()` convenience function
  - Error handling and connection management utilities

## Development Practices

### Multi-Repository Integration
- **Always use infrastructure branches**: `infra/baseline-v1`, `infra/baseline-v2`, etc.
- Coordinate changes with dependent repositories (swf-testbed, swf-monitor)
- Never push directly to main - always use branches and pull requests
- Test integration across all dependent projects

### Code Quality Standards
- Comprehensive unit testing with mock objects for external dependencies
- PEP 8 compliance for code formatting
- Docstrings for all public functions and classes
- Type hints where appropriate

### Testing Strategy
- Mock all external dependencies (PostgreSQL connections, HTTP requests)
- Test both success and failure scenarios
- Verify proper error handling and fallback behavior
- Integration testing with actual SWF components

## Configuration and Dependencies

### Core Dependencies
- `python-json-logger` - JSON log formatting capabilities
- `psycopg2-binary` - PostgreSQL database connectivity
- `requests` - HTTP client for REST API logging

### Test Dependencies
- `pytest` - Testing framework
- `pytest-mock` - Mocking utilities
- Various mocking libraries for database and HTTP testing

### Configuration Files
- `pyproject.toml` - Modern Python packaging configuration with build system, dependencies, and metadata
- `pytest.ini` - Test configuration with source paths and test discovery settings
- `run_tests.sh` - Standardized test execution with environment management

## Usage Patterns

### PostgreSQL Logging Setup
```python
from swf_common_lib.logging_utils import setup_logger

logger = setup_logger(
    name="my_service",
    db_host="localhost",
    db_name="swfdb", 
    db_user="admin",
    db_password="password"
)
```

### REST API Logging
```python
from swf_common_lib.logging_utils import RestLogHandler
import logging

handler = RestLogHandler(
    url="https://api.example.com/logs",
    auth_token="bearer_token"
)
logger = logging.getLogger("my_service")
logger.addHandler(handler)
```

## External Integration

### Database Schema
PostgresLogHandler automatically creates required database tables:
- Standard log fields (timestamp, level, message, logger name)
- JSON extra data field for additional structured information
- Proper indexing for performance

### Error Handling
- Connection failures are handled gracefully with fallback logging to stderr
- Database schema creation is automatic and idempotent
- REST API failures fall back to local logging

## CI/CD Pipeline

### Automated Publishing
- GitHub Actions workflow publishes to TestPyPI on version tags
- Trigger with tags matching pattern `v*` (e.g., `v1.0.0`)
- Automatic PyPI publishing for stable releases

### Version Management
- Semantic versioning (major.minor.patch)
- Version specified in `pyproject.toml`
- Git tags used for release triggers

## Security Considerations

### Database Connections
- Supports SSL connections to PostgreSQL
- Credential management via environment variables
- Connection pooling and proper connection cleanup

### API Authentication
- Bearer token authentication for REST logging
- Secure credential handling
- HTTPS enforcement for API endpoints