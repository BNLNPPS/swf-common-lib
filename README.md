# swf-common-lib

Common libraries and utilities for the swf-testbed ePIC streaming workflow testbed project.

## Overview

This library provides shared functionality for SWF agents, including logging utilities and REST API
integration for the swf-monitor service. Also included are utility classes wrapping MQ and Rucio communications.

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

**`setup_rest_logging(app_name, instance_name, base_url='http://localhost:8000', timeout=10)`**

Sets up REST logging for an agent.

**Parameters:**
- `app_name` (str): Name of your application/agent
- `instance_name` (str): Unique identifier for this instance  
- `base_url` (str): URL of swf-monitor service (default: 'http://localhost:8000')
- `timeout` (int): Timeout in seconds for REST requests (default: 10)

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

## BaseAgent (`swf_common_lib.base_agent`)

`BaseAgent` is the shared base class for SWF agents: a STOMP consumer that
connects to ActiveMQ, registers and heartbeats to the monitor, applies namespace
filtering, and dispatches messages to the subclass's `on_message`. (BaseAgent's
design choices are recorded in
`swf-testbed/docs/architecture_and_design_choices.md`; this section documents the
background-execution API.)

### Background execution (`BaseAgent.run_in_background`)

`BaseAgent` delivers messages on a single STOMP receiver thread, sequentially,
so a handler that blocks — a subprocess, or a long REST / Rucio / xrootd call —
stalls every later message, including liveness pings. `run_in_background`
offloads such work to a bounded thread pool and returns the receiver thread to
the dispatch loop at once, so the agent stays responsive and can have several
actions in flight.

It is **opt-in**: an agent that never calls it behaves exactly as before.
Threads (not asyncio) are used deliberately — the work is blocking
subprocess/socket I/O and the stack (stomp.py, subprocess) is thread-based.

**`run_in_background(fn, *args, dedup_key=None, label=None, **kwargs)`**

Submit `fn(*args, **kwargs)` to the agent's worker pool and return immediately.
The wrapper:

- drives **reentrant PROCESSING state** — the agent reports PROCESSING while any
  background work is in flight and READY when none is;
- **catches and logs every exception**, so a worker never dies silently;
- **skips** the call when `dedup_key` names a unit already running, avoiding the
  duplicate-work race that concurrency introduces.

Control messages (liveness, shutdown) should stay inline on the receiver thread;
only long-running work is offloaded. Shutdown drains in-flight workers. See
`swf-monitor/docs/EPICPROD_OPS_AGENT.md` for the first consumer.

## MQ and Rucio Utility packages

The *mq_comms* and *rucio_comms* packages provide convenient encapsulation of interactions
with the ActiveMQ and Rucio systems, respectively. Each folder contains it's own README file
with more details.
