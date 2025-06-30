# swf-common-lib

Common utilities and shared libraries for the SWF (Streaming Workflow) testbed
ePIC streaming workflow testbed project.

## Overview

This library provides shared utilities and common functionality used across
multiple SWF repositories, including logging utilities, database helpers,
and other common components.

## Components

### Logging Utilities

The `logging_utils.py` module provides standardized logging configuration
and utilities for consistent logging across all SWF components.

**Features:**
- Structured JSON logging support
- Consistent log formatting
- Configuration helpers

## Installation

This package is designed to be installed as a development dependency alongside
other SWF components:

```bash
# Install in development mode (recommended for SWF development)
pip install -e .

# Install with test dependencies
pip install -e .[test]
```

## Usage

### Logging

```python
from swf_common_lib.logging_utils import setup_logging

# Set up standardized logging for your SWF component
logger = setup_logging(__name__)
logger.info("Your SWF component is running")
```

## Development

### Running Tests

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=swf_common_lib
```

### Testing with Django Integration

This library is designed to work seamlessly with Django-based SWF components.
Tests use the `django_db` marker for compatibility:

```python
import pytest

@pytest.mark.django_db
def test_with_django_models():
    # Test code that may interact with Django models
    pass
```

## Project Structure

```
swf-common-lib/
├── src/
│   └── swf_common_lib/
│       ├── __init__.py
│       └── logging_utils.py
├── tests/
│   ├── conftest.py
│   └── test_logging_utils.py
├── pyproject.toml
├── pytest.ini
└── README.md
```

## Contributing

This library follows the SWF testbed development workflow. See the
[swf-testbed README](https://github.com/BNLNPPS/swf-testbed) for detailed
development guidelines and the coordinated multi-repository workflow.

## Integration

This library is part of the SWF testbed ecosystem:

- **[swf-testbed](https://github.com/BNLNPPS/swf-testbed)**: Core infrastructure and CLI
- **[swf-monitor](https://github.com/BNLNPPS/swf-monitor)**: Django monitoring application  
- **swf-common-lib**: Shared utilities (this repository)

All three repositories should be cloned as siblings and developed together.
