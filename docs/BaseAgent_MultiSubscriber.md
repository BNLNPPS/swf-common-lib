# BaseAgent Multi-Subscriber Architecture

## Overview

The `BaseAgent` class has been optimized to support **multiple subscribers**, enabling agents to:

- **Subscribe to multiple queues/topics simultaneously** - Receive messages from various sources
- **Publish to any destination** - Send messages flexibly
- **Dynamically manage subscriptions** - Add/remove subscriptions at runtime
- **Maintain backward compatibility** - Existing single-queue agents continue to work

---

## Key Features

### 1. Multiple Subscriptions

Agents can now subscribe to multiple ActiveMQ destinations (queues and/or topics) simultaneously:

```python
agent = BaseAgent(
    agent_type='HYBRID',
    subscription_queues=[
        '/queue/workflow_control',
        '/topic/system_events',
        '/queue/data_input'
    ]
)
```

**Benefits:**
- Single agent can handle multiple message streams
- Reduce process overhead (fewer agents needed)
- Centralized message processing logic

### 2. Flexible Publishing

Publish directly to any destination:

```python
# Send to queues
agent.send_message('/queue/workflow_control', {'msg_type': 'status_update'})

# Send to topics
agent.send_message('/topic/system_events', {'msg_type': 'event'})

# Maximum flexibility - no pre-configuration needed
agent.send_message('/queue/processing_results', {'msg_type': 'result', 'data': data})
```

### 3. Dynamic Subscription Management

Add or remove subscriptions at runtime:

```python
# Add new subscription
agent.add_subscription('/topic/emergency_alerts')

# Remove subscription
agent.remove_subscription('/queue/data_input')

# Query current subscriptions
subscriptions = agent.get_subscriptions()
print(f"Currently subscribed to: {subscriptions}")
```

---

## Usage Examples

### Example 1: Basic Multi-Queue Agent

```python
from swf_common_lib.base_agent import BaseAgent

class DataAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_type='DATA',
            subscription_queues=[
                '/queue/data_requests',
                '/topic/broadcast_commands'
            ]
        )
    
    def on_message(self, frame):
        message_data, msg_type = self.log_received_message(frame)
        if message_data is None:
            return  # Filtered by namespace
        
        # Handle messages from different sources
        if msg_type == 'data_request':
            self._process_data_request(message_data)
        elif msg_type == 'broadcast_command':
            self._handle_broadcast(message_data)
    
    def _process_data_request(self, data):
        with self.processing():
            # Do work...
            result = {'msg_type': 'data_response', 'data': 'processed'}
            self.send_message('/queue/data_results', result)
    
    def _handle_broadcast(self, data):
        # Quick action
        self.send_message('/topic/agent_status', {
            'msg_type': 'ack',
            'command': data.get('command')
        })

if __name__ == '__main__':
    agent = DataAgent()
    agent.run()
```

### Example 2: Dynamic Subscription Management

```python
class AdaptiveAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_type='ADAPTIVE',
            subscription_queues=['/queue/control']
        )
        self.active_workflows = set()
    
    def on_message(self, frame):
        message_data, msg_type = self.log_received_message(frame)
        if message_data is None:
            return
        
        if msg_type == 'enable_workflow':
            workflow_id = message_data.get('workflow_id')
            workflow_queue = f'/queue/workflow_{workflow_id}'
            
            # Dynamically subscribe to new workflow queue
            if self.add_subscription(workflow_queue):
                self.active_workflows.add(workflow_id)
                self.send_message('/topic/status', {
                    'msg_type': 'workflow_enabled',
                    'workflow_id': workflow_id
                })
        
        elif msg_type == 'disable_workflow':
            workflow_id = message_data.get('workflow_id')
            workflow_queue = f'/queue/workflow_{workflow_id}'
            
            # Remove subscription
            if self.remove_subscription(workflow_queue):
                self.active_workflows.discard(workflow_id)
                self.send_message('/topic/status', {
                    'msg_type': 'workflow_disabled',
                    'workflow_id': workflow_id
                })
```

### Example 3: Fan-out Publisher

```python
class NotificationAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_type='NOTIFIER',
            subscription_queues=['/queue/notifications']
        )
    
    def on_message(self, frame):
        message_data, msg_type = self.log_received_message(frame)
        if message_data is None:
            return
        
        if msg_type == 'notification':
            priority = message_data.get('priority', 'normal')
            
            with self.processing():
                notification = {
                    'msg_type': 'notification',
                    'message': message_data.get('message'),
                    'priority': priority
                }
                
                # Fan out to multiple destinations
                self.send_message('/queue/notification_archive', notification)
                
                if priority in ['high', 'critical']:
                    self.send_message('/queue/email_service', notification)
                    self.send_message('/queue/slack_service', notification)
                
                self.send_message('/topic/dashboard_updates', notification)
```

---

## API Reference

### Constructor

```python
BaseAgent(
    agent_type: str,
    subscription_queue: Optional[str] = None,  # DEPRECATED
    subscription_queues: Optional[List[str]] = None,
    debug: bool = False,
    config_path: Optional[str] = None
)
```

**Parameters:**

- `agent_type` (str): Type identifier for the agent (e.g., 'DATA', 'PROCESSING')
- `subscription_queue` (str, optional): **DEPRECATED** - Use `subscription_queues` instead
- `subscription_queues` (List[str], optional): List of ActiveMQ destinations to subscribe to
  - Each must start with `/queue/` or `/topic/`
  - Example: `['/queue/workflow_control', '/topic/events']`
- `debug` (bool): Enable debug logging
- `config_path` (str, optional): Path to testbed.toml configuration file

**Raises:**
- `ValueError`: If destinations don't have `/queue/` or `/topic/` prefix

### Publishing Method

#### `send_message(destination, message_body, headers=None)`

Send a message to a destination with optional custom headers.

```python
# Send to queue
agent.send_message('/queue/myqueue', {'msg_type': 'test'})

# Send to topic with custom headers
agent.send_message('/topic/events', 
                   {'msg_type': 'event'},
                   headers={'persistent': 'true', 'priority': '9'})
```

**Parameters:**
- `destination` (str): ActiveMQ destination (`/queue/...` or `/topic/...`)
- `message_body` (dict): Message payload (JSON-serializable)
- `headers` (dict, optional): STOMP headers to include with the message. If provided, they are merged with default headers (user headers take precedence).

**Auto-injected message body fields:**
- `sender`: Agent name
- `namespace`: Namespace (if configured)
- `created_at`: UTC timestamp in ISO 8601 format (if not already present)

**Default STOMP headers** (applied automatically, can be overridden):
- `persistent`: 'false'
- `vo`: 'eic'
- `msg_type`: Extracted from message body
- `namespace`: Extracted from message body
- `run_id`: Current run ID (or 'none')

**Examples:**

```python
# Basic message - uses all defaults
agent.send_message('/queue/output', {'msg_type': 'result', 'data': 'value'})
# Auto-adds: sender, namespace, created_at
# Default headers: persistent='false', vo='eic', etc.

# Override specific headers
agent.send_message('/queue/output', 
                   {'msg_type': 'important'},
                   headers={'persistent': 'true'})
# Merges: user's persistent='true' + other defaults

# Add custom headers
agent.send_message('/queue/output',
                   {'msg_type': 'data'},
                   headers={'priority': '9', 'custom-header': 'value'})
# Includes: all defaults + priority + custom-header
```

**Raises:**
- `ValueError`: If destination format is invalid

### Subscription Management Methods

#### `add_subscription(destination)`

Dynamically add a new subscription.

```python
agent.add_subscription('/queue/new_queue')
```

**Parameters:**
- `destination` (str): ActiveMQ destination (`/queue/...` or `/topic/...`)

**Returns:**
- `bool`: True if successful

#### `remove_subscription(destination)`

Remove an existing subscription.

```python
agent.remove_subscription('/queue/old_queue')
```

**Parameters:**
- `destination` (str): ActiveMQ destination to unsubscribe from

**Returns:**
- `bool`: True if successful

#### `get_subscriptions()`

Get current list of subscriptions.

```python
subs = agent.get_subscriptions()
print(f"Subscribed to: {subs}")
```

**Returns:**
- `list`: Copy of current subscription destinations

---

## Migration Guide

### Migrating from Single-Queue Agents

**Old Code (Deprecated but still works):**

```python
agent = BaseAgent(
    agent_type='DATA',
    subscription_queue='/queue/workflow_control'
)

agent.send_message('/queue/results', {'msg_type': 'result'})
```

**New Code (Recommended):**

```python
agent = BaseAgent(
    agent_type='DATA',
    subscription_queues=['/queue/workflow_control']  # Now a list
)

agent.send_message('/queue/results', {'msg_type': 'result'})  # Same
```

### Migration Steps

1. **Update constructor call:**
   - Change `subscription_queue=` to `subscription_queues=[...]`
   - Make it a list even if you have only one queue

2. **Publishing stays the same:**
   - `send_message()` works exactly as before
   - No changes needed to publishing code

3. **Test thoroughly:**
   - Verify all messages are received and sent correctly
   - Check logs for deprecation warnings

---

## Best Practices

### 1. Use Explicit Destination Formats

✅ **Good:**
```python
agent.send_message('/queue/workflow_control', message)
agent.send_message('/topic/events', message)
```

❌ **Avoid:**
```python
agent.send_message('workflow_control', message)  # Missing prefix
```

### 2. Organize Subscriptions by Purpose

```python
# Clear separation of concerns
subscription_queues=[
    '/queue/workflow_commands',    # Control messages
    '/topic/system_broadcasts',    # System-wide events
    '/queue/data_stream'           # Data processing
]
```

### 3. Document Message Flow

```python
class MyAgent(BaseAgent):
    """
    Agent for processing workflows.
    
    Subscribes to:
        - /queue/workflow_commands: Workflow control messages
        - /topic/system_events: System broadcast events
    
    Publishes to:
        - /queue/workflow_control: Status updates
        - /queue/workflow_results: Processing results
    """
```

### 4. Handle Namespace Filtering

```python
def on_message(self, frame):
    message_data, msg_type = self.log_received_message(frame)
    if message_data is None:
        return  # Filtered by namespace - don't process
    
    # Process message...
```

### 5. Use Processing Context

```python
def on_message(self, frame):
    message_data, msg_type = self.log_received_message(frame)
    if message_data is None:
        return
    
    if msg_type == 'process_data':
        with self.processing():
            # Automatically sets PROCESSING state
            self._do_work(message_data)
            self.send_message('/queue/results', result)
        # Automatically returns to READY state
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                         BaseAgent                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Subscriptions (Input)          Publications (Output)       │
│  ┌──────────────────┐           ┌──────────────────┐       │
│  │ /queue/control   │           │ Any destination  │       │
│  │ /topic/events    │───────────│ /queue/*         │       │
│  │ /queue/data_in   │  Agent    │ /topic/*         │       │
│  └──────────────────┘  Logic    └──────────────────┘       │
│         │                                 ↑                 │
│         ↓                                 │                 │
│  on_message(frame)                       │                 │
│         │                                 │                 │
│         └─────────────────────────────────┘                 │
│              (Message Processing)                            │
│                                                              │
│  Dynamic Management:                                         │
│  - add_subscription(dest)                                    │
│  - remove_subscription(dest)                                 │
│  - get_subscriptions()                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Common Patterns

### Pattern 1: Fan-out Publisher
Receive from one queue, publish to multiple destinations:
```python
def on_message(self, frame):
    message_data, msg_type = self.log_received_message(frame)
    
    # Publish to multiple destinations
    self.send_message('/queue/dest1', message_data)
    self.send_message('/queue/dest2', message_data)
    self.send_message('/topic/broadcast', {'msg_type': 'notification'})
```

### Pattern 2: Message Aggregator
Subscribe to multiple sources, aggregate and publish:
```python
def __init__(self):
    self.message_buffer = []
    super().__init__(
        subscription_queues=['/queue/source1', '/queue/source2']
    )

def on_message(self, frame):
    message_data, msg_type = self.log_received_message(frame)
    self.message_buffer.append(message_data)
    
    if len(self.message_buffer) >= 10:
        self.send_message('/queue/aggregated', {
            'msg_type': 'batch',
            'messages': self.message_buffer
        })
        self.message_buffer = []
```

### Pattern 3: Conditional Subscriber
Add subscriptions based on runtime conditions:
```python
def _enable_feature(self, feature_name):
    feature_queues = {
        'monitoring': '/queue/monitoring',
        'analytics': '/queue/analytics',
        'alerts': '/topic/alerts'
    }
    
    if feature_name in feature_queues:
        self.add_subscription(feature_queues[feature_name])
```

---

## Performance Considerations

### Connection Management

- All subscriptions share a **single STOMP connection**
- Reconnection automatically re-subscribes to all queues
- Subscription IDs are internally tracked and managed

### Message Throughput

- Multiple subscriptions don't significantly impact performance
- Each subscription has its own message handler
- Messages are processed sequentially in the order received

### Resource Usage

- **Memory**: Minimal overhead per subscription (~few KB)
- **Network**: Single connection regardless of subscription count
- **CPU**: Message processing is sequential, not parallel

---

## Troubleshooting

### Issue: Messages not received from new subscription

**Solution:** Check subscription format and connection status

```python
# Verify subscription was added
subs = agent.get_subscriptions()
print(f"Current subscriptions: {subs}")

# Check connection
if not agent.mq_connected:
    print("MQ not connected - subscriptions pending reconnection")
```

### Issue: Published messages not reaching destination

**Solution:** Verify destination format

```python
# Correct format
agent.send_message('/queue/my_queue', message)  # ✅
agent.send_message('/topic/my_topic', message)  # ✅

# Incorrect format
agent.send_message('my_queue', message)  # ❌ Missing prefix
```

### Issue: Multiple agents on same queue

**Solution:** Agent names are automatically unique

```python
# Agent names are unique: {agent_type}-agent-{username}-{id}
print(f"My agent name: {agent.agent_name}")
```

---

## Testing

### Unit Test Example

```python
import unittest
from swf_common_lib.base_agent import BaseAgent

class TestMultiSubscriber(unittest.TestCase):
    def test_multiple_subscriptions(self):
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=[
                '/queue/test1',
                '/queue/test2',
                '/topic/test3'
            ]
        )
        
        self.assertEqual(len(agent.subscription_queues), 3)
        self.assertIn('/queue/test1', agent.subscription_queues)
    
    def test_dynamic_subscription(self):
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=['/queue/test']
        )
        
        # Mock for testing
        agent.subscription_queues = []
        agent._subscription_ids = {}
        agent.mq_connected = False
        
        success = agent.add_subscription('/queue/new')
        self.assertTrue(success)
        self.assertIn('/queue/new', agent.subscription_queues)

if __name__ == '__main__':
    unittest.main()
```

---

## Changelog

### Version 2.0 (February 2026)

- ✨ Added support for multiple subscriptions
- ✨ Added dynamic subscription management
- 🔄 Deprecated single `subscription_queue` parameter
- 📚 Added comprehensive documentation
- ✅ Maintained backward compatibility
- 🎯 Simplified publishing (no mapping needed)

---

## Support

For questions or issues:
1. Check this documentation
2. Review code examples above
3. Check agent logs for detailed error messages
4. Contact development team

---

## License

Copyright © 2026 - Scientific Workflow System
