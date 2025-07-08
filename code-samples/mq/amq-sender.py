import stomp
import ssl
from datetime import datetime

host = 'pandaserver02.sdcc.bnl.gov'
port = 61612
cafile = '<pathname to where full-chain.pem is>'

conn = stomp.Connection(host_and_ports=[(host, port)], vhost=host,try_loopback_connect=False)

conn.transport.set_ssl(
    for_hosts=[(host, port)],
    ca_certs=cafile,
    ssl_version=ssl.PROTOCOL_TLS_CLIENT
)

try:
    conn.connect(login='<username>', passcode='<userpasswd>', wait=True, version='1.2')
    conn.send(destination='epictopic', body=f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Hello from producer!")
    print("Message sent")
    conn.disconnect()
except Exception as e:
    print("Connection failed:", type(e).__name__, e)
