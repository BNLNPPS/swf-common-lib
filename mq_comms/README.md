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

## Subscription

For the _Receiver_ class, it's important to create a unique subscription for
reliable delivery of messages. This is done via the argument *client_id*.
