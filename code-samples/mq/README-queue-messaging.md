# Queue-Based Messaging for Fast Processing Workflow

New capabilities added to `BaseAgent` for point-to-point messaging with manual acknowledgment, supporting the fast processing workflow architecture.

## Overview

### Broadcast vs Queue Messaging

**Broadcast (Topics)** - Existing pattern:
- All subscribers receive all messages
- Auto-acknowledgment
- Used for: workflow events, run control, notifications

**Queue (Point-to-Point)** - New pattern:
- Each message consumed by exactly one worker
- Manual acknowledgment (ack/nack)
- Used for: work distribution, TF slice assignments, results

## New BaseAgent Methods

### Subscribing to Queues

```python
def subscribe_to_queue(self, queue_name, ack_mode='client-individual',
                       prefetch_size=1, selector=None, subscription_id=None)
```

**Example:**
```python
# Worker subscribes to slice queue with task-id filtering
self.subscribe_to_queue(
    queue_name='/queue/panda.transformer.slices',
    ack_mode='client-individual',  # Requires manual ack
    prefetch_size=1,               # Only fetch one at a time
    selector="task-id = 'task-12345'"  # Header-based filtering
)
```

**Parameters:**
- `ack_mode`: `'client-individual'` (default), `'client'`, or `'auto'`
- `prefetch_size`: Number of messages to prefetch (default=1, allows small numbers >1)
- `selector`: SQL-style selector for header filtering (e.g., `"task-id = '12345'"`)

### Subscribing to Topics

```python
def subscribe_to_topic(self, topic_name, subscription_id=None)
```

**Example:**
```python
# Worker subscribes to control topic for broadcast messages
self.subscribe_to_topic('/topic/panda.transformer')
```

### Sending to Queues

```python
def send_to_queue(self, queue_name, message_body, headers=None)
```

**Example:**
```python
# Dispatcher sends slice with task-id header
self.send_to_queue(
    queue_name='/queue/panda.transformer.slices',
    message_body={'slice_id': 'slice-001', 'stf_id': 'stf-123'},
    headers={'task-id': 'task-12345'}
)
```

### Message Acknowledgment

```python
def ack_message(self, frame)   # Success - remove from queue
def nack_message(self, frame)  # Failure - return to queue for retry
```

**Example:**
```python
def on_message(self, frame):
    try:
        # Process message
        result = process_slice(frame.body)

        # Send result
        self.send_to_queue('/queue/panda.results', result)

        # Acknowledge - removes from queue
        self.ack_message(frame)

    except Exception as e:
        # Negative acknowledge - returns to queue
        self.nack_message(frame)
```

## Usage Patterns

### Pattern 1: Worker with Multiple Subscriptions

Workers need both slice queue (point-to-point) and control topic (broadcast):

```python
class TransformerWorker(BaseAgent):
    def __init__(self, task_id):
        super().__init__(
            agent_type='transformer',
            subscription_queue='/topic/workflow'  # Primary broadcast
        )
        self.task_id = task_id

    def run(self):
        # Connect to broker
        self.conn.connect(...)

        # Primary subscription (auto-ack broadcast)
        self.conn.subscribe(destination=self.subscription_queue, id=1, ack='auto')

        # Queue subscription for slice assignments (manual ack)
        self.subscribe_to_queue(
            '/queue/panda.transformer.slices',
            selector=f"task-id = '{self.task_id}'",
            prefetch_size=1
        )

        # Topic subscription for control messages (auto-ack broadcast)
        self.subscribe_to_topic('/topic/panda.transformer')

        # Main loop...
```

### Pattern 2: Dispatcher with Results Queue

Dispatchers send work and receive results:

```python
class SliceDispatcher(BaseAgent):
    def __init__(self, task_id):
        super().__init__(
            agent_type='dispatcher',
            subscription_queue='/queue/panda.results.sub2'  # Results consumer
        )
        self.task_id = task_id

    def dispatch_slice(self, slice_id):
        # Send with task-id header for worker filtering
        self.send_to_queue(
            '/queue/panda.transformer.slices',
            message_body={'slice_id': slice_id, 'task_id': self.task_id},
            headers={'task-id': self.task_id}
        )

    def send_run_end(self):
        # Broadcast to all workers via topic
        self.send_message(
            '/topic/panda.transformer',
            {'msg_type': 'transformer_end', 'task_id': self.task_id}
        )
```

### Pattern 3: Dual Result Subscription

Results queue configured with dual consumers (PA and iDDS):

```python
# Worker sends result once - automatically duplicated
self.send_to_queue('/queue/panda.results', result)

# PA consumes from sub1
class ProcessingAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_type='processing',
            subscription_queue='/queue/panda.results.sub1'
        )

# iDDS consumes from sub2
class iDDSHandler(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_type='idds',
            subscription_queue='/queue/panda.results.sub2'
        )
```

## Message Flow Examples

### Fast Processing Slice Assignment

```
1. PA creates TF slice, sends to /queue/tf.slices
2. iDDS consumes, assigns to worker via /queue/panda.transformer.slices (with task-id header)
3. Transformer consumes (prefetch=1, filters by task-id)
4. Transformer processes, sends to /queue/panda.results
5. Result duplicated to sub1 (PA) and sub2 (iDDS)
6. Transformer acks message (removed from queue)
```

### Run End Notification

```
1. PA sends to /queue/tf.slices: run_end
2. iDDS broadcasts to /topic/panda.transformer: transformer_end (all workers receive)
3. Workers enter soft-ending mode (finish queue, then quit)
```

## Key Concepts

### Prefetch Size

- `prefetch_size=1`: Worker only receives one message at a time
- Ensures workers only get work they can process immediately
- Prevents message hoarding by slow workers
- Small numbers >1 allowed for batching optimization

### Manual Acknowledgment

- `ack='client-individual'`: Each message acknowledged separately
- Unacknowledged messages return to queue on disconnect
- `ack()`: Success - removes message
- `nack()`: Failure - returns message for retry
- Critical for reliable work distribution

### Header Filtering

- Workers filter by `task-id` to receive only their assigned work
- Multiple tasks can share same queue
- Selector syntax: `"task-id = 'task-12345'"`

### Reconnection

- All subscriptions (primary + queues + topics) automatically restored on reconnect
- Unacknowledged messages redelivered after reconnect
- Subscription configs tracked in `self._subscriptions`

## Examples

Run the example scripts to see queue messaging in action:

```bash
# Terminal 1: Start a worker for task-12345
cd swf-common-lib
source .venv/bin/activate && source ~/.env
python code-samples/mq/queue_worker_example.py task-12345

# Terminal 2: Start dispatcher to send work
python code-samples/mq/queue_dispatcher_example.py task-12345
```

## Fast Processing Workflow Queues

### Queues

- `/queue/tf.slices` - PA → iDDS (slice notifications, run control)
- `/queue/panda.transformer.slices` - iDDS → Transformers (slice assignments)
- `/queue/panda.results` - Transformers → PA + iDDS (processing results)
  - `/queue/panda.results.sub1` - PA consumer
  - `/queue/panda.results.sub2` - iDDS consumer
- `/queue/panda.harvester` - iDDS → Harvester (worker scaling)

### Topics

- `/topic/panda.transformer` - iDDS → All Transformers (broadcast control messages)

## References

- [Fast Processing Workflow Documentation](../../../swf-testbed/docs/fast-processing.md)
- [BaseAgent API](../../src/swf_common_lib/base_agent.py)
