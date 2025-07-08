import stomp
import ssl
import time

class MyListener(stomp.ConnectionListener):
    def on_connected(self, frame):
        print("Connected to broker:", frame.headers)

    def on_message(self, frame):
        print(f"Received message:\n{frame.body}")

    def on_error(self, frame):
        print(f"Error from broker: {frame.body}")

    def on_disconnected(self):
        print("Disconnected from broker")

# Broker config
host = 'pandaserver02.sdcc.bnl.gov'
port = 61612
cafile = '<pathname to where full-chain.pem is>'

# Durable subscription config
client_id = 'test-client'
subscription_name = 'test-durable-sub'

# Set up STOMP over SSL connection
conn = stomp.Connection(
    host_and_ports=[(host, port)],
    vhost=host,
    try_loopback_connect=False
)

# SSL settings
conn.transport.set_ssl(
    for_hosts=[(host, port)],
    ca_certs=cafile,
    ssl_version=ssl.PROTOCOL_TLS_CLIENT
)

# Code above this localtion is common for both sender and receiver

# Attach listener
conn.set_listener('', MyListener())
#conn.set_listener('debug', stomp.PrintingListener())

# Connect with a durable client-id
conn.connect(
    login='<username>',
    passcode='<userpasswd>',
    wait=True,
    version='1.2',
    headers={'client-id': client_id}
)

# Subscribe with durable subscription name
conn.subscribe(
    destination='epictopic',
    id='sub-test-001',
    ack='auto',
    headers={'activemq.subscriptionName': 'test-durable-sub'}
)

print(f"Listening for messages on 'epictopic' (durable queue: {client_id}.{subscription_name})...")

# Loop forever
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Exiting...")
    conn.disconnect()
