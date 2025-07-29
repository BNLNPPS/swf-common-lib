# swf-common-lib

Common libraries and utilities for the swf-testbed ePIC streaming workflow testbed project.

## Overview

This library provides shared functionality for SWF agents, including logging utilities and REST API integration for the swf-monitor service.

## Installation

```bash
pip install swf-common-lib
```

For development:
```bash
pip install -e /path/to/swf-common-lib
```

## Components

### REST Logging (`swf_common_lib.rest_logging`)

A simple logging module that allows agents to send logs to the swf-monitor database via REST API using standard Python logging.

#### Quick Start

```python
import logging
from swf_common_lib.rest_logging import setup_rest_logging

# Setup logging - this is all you need!
logger = setup_rest_logging(
    app_name='my_agent',
    instance_name='agent_001'
)

# Now just use standard Python logging
logger.info("Agent starting up")
logger.warning("Something needs attention")
logger.error("An error occurred")
```

#### Features

- **Simple Setup**: Single function call to configure REST logging
- **Fallback Support**: Automatically falls back to console logging if monitor is unavailable
- **Standard Interface**: Uses Python's standard logging module
- **Configurable**: Supports custom timeouts and monitor URLs
- **Error Handling**: Graceful degradation when network issues occur

#### API Reference

**`setup_rest_logging(app_name, instance_name, base_url='http://localhost:8000', timeout=5)`**

Sets up REST logging for an agent.

**Parameters:**
- `app_name` (str): Name of your application/agent
- `instance_name` (str): Unique identifier for this instance  
- `base_url` (str): URL of swf-monitor service (default: 'http://localhost:8000')
- `timeout` (int): Timeout in seconds for REST requests (default: 5)

**Returns:**
- Configured logger ready to use

**Example with custom configuration:**
```python
logger = setup_rest_logging(
    app_name='processing_agent',
    instance_name='proc_001',
    base_url='https://monitor.example.com',
    timeout=10
)
```

#### Behavior

When the monitor service is available, logs are sent to the database via REST API. When unavailable:

1. Shows a warning message on first failure
2. Falls back to standard console logging
3. Continues working normally for the application

### Logging Utils (`swf_common_lib.logging_utils`)

Traditional logging utilities for PostgreSQL database integration.

