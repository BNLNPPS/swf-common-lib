# The ActiveMQ communications

## Purpose

This is a general purpose package created to facilitate
the interface with the _ActiveMQ_ broker. It is agnostic
with regards to the contents of the messages sent and received.

## Environment variables

`MQ_USER` and `MQ_PASSWD` environment variables need to be set
for the package to work. Same goes for `MQ_CAFILE`, this needs
to be the full path to the CA file.

`MQ_HOST` and `MQ_PORT` have default values in the code which will work
for testing right away.

## Classes

The _Sender_ and _Receiver_ classes inherit their common
functionality from the _Messenger_, the base class. They can
be instantiated separately as needed, in a single or multiple
applications and are agnostic with
regards to the logic of the simulation.

## Messages

Currently, the _base agent_ class in **common-lib** contains
a set defined as follows:

```python
    WORKFLOW_MESSAGE_TYPES = {
        'run_imminent', 'start_run', 'pause_run', 'resume_run', 'end_run',
        'stf_gen', 'data_ready'
    }
```

## Basic Durable Subscription Example

```python
import stomp
import time

class MyListener(stomp.ConnectionListener):
    def on_error(self, frame):
        print(f'Received an error: {frame.body}')
    
    def on_message(self, frame):
        print(f'Received message: {frame.body}')
        print(f'Headers: {frame.headers}')

# Connection parameters
host = 'localhost'
port = 61613  # Default STOMP port for ActiveMQ
client_id = 'my-client-id'  # Must be unique and persistent
subscription_name = 'my-durable-sub'
topic = '/topic/my.topic'

# Create connection
conn = stomp.Connection([(host, port)])

# Set client ID for durable subscription (must be done before connect)
conn.set_listener('', MyListener())

# Connect with client-id header (required for durable subscriptions)
conn.connect(wait=True, headers={'client-id': client_id})

# Subscribe with durable subscription
conn.subscribe(
    destination=topic,
    id=subscription_name,
    ack='auto',
    headers={
        'activemq.subscriptionName': subscription_name,
        'client-id': client_id
    }
)

print(f'Durable subscription created: {subscription_name}')
print('Waiting for messages...')

try:
    # Keep the connection alive
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print('\nDisconnecting...')
    conn.disconnect()
```

## Key Points for Durable Subscriptions

1. **Client ID**: Must be set and unique. This identifies the client across connections.

2. **Subscription Name**: Use the `activemq.subscriptionName` header to name your durable subscription.

3. **Topic (not Queue)**: Durable subscriptions only work with topics, not queues.

4. **Persistence**: Messages sent to the topic while the subscriber is disconnected will be delivered when it reconnects (as long as it uses the same client-id and subscription name).

## Unsubscribing from a Durable Subscription

To permanently remove a durable subscription:

```python
conn.unsubscribe(
    id=subscription_name,
    headers={'activemq.subscriptionName': subscription_name}
)
```

## Using ActiveMQ Artemis

If you're using ActiveMQ Artemis (the newer version), the syntax is slightly different:

```python
conn.subscribe(
    destination=topic,
    id=subscription_name,
    ack='auto',
    headers={
        'durable': 'true',
        'subscription-name': subscription_name
    }
)
```

