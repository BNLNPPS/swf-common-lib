"""
This module contains the base class for all agents.
"""

import os
import sys
import time
import stomp
import requests
import json
import logging
from pathlib import Path


class APIError(Exception):
    """Exception raised for API-related failures."""
    
    def __init__(self, message, response=None, url=None, method=None):
        super().__init__(message)
        self.response = response
        self.url = url
        self.method = method

def setup_environment():
    """Auto-activate venv and load environment variables."""
    script_dir = Path(__file__).resolve().parent.parent.parent.parent / "swf-testbed"
    
    # Auto-activate virtual environment if not already active
    if "VIRTUAL_ENV" not in os.environ:
        venv_path = script_dir / ".venv"
        if venv_path.exists():
            print("🔧 Auto-activating virtual environment...")
            venv_python = venv_path / "bin" / "python"
            if venv_python.exists():
                os.environ["VIRTUAL_ENV"] = str(venv_path)
                os.environ["PATH"] = f"{venv_path}/bin:{os.environ['PATH']}"
                sys.executable = str(venv_python)
        else:
            print("❌ Error: No Python virtual environment found")
            return False
    
    # Load ~/.env environment variables (they're already exported)
    env_file = Path.home() / ".env"
    if env_file.exists():
        print("🔧 Loading environment variables from ~/.env...")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    if line.startswith('export '):
                        line = line[7:]  # Remove 'export '
                    key, value = line.split('=', 1)
                    os.environ[key] = value.strip('"\'')
    
    # Unset proxy variables to prevent localhost routing through proxy
    for proxy_var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
        if proxy_var in os.environ:
            del os.environ[proxy_var]
    
    return True

# Auto-setup environment when module is imported (unless already done)
if not os.getenv('SWF_ENV_LOADED'):
    setup_environment()
    os.environ['SWF_ENV_LOADED'] = 'true'

# Import the centralized logging from swf-common-lib
from swf_common_lib.rest_logging import setup_rest_logging

# Configure base logging level with environment overrides
_quiet = os.getenv('SWF_AGENT_QUIET', 'false').lower() in ('1', 'true', 'yes', 'on')
_level_name = os.getenv('SWF_LOG_LEVEL', 'WARNING' if _quiet else 'INFO').upper()

# Validate log level and provide clear error for invalid values
# Use Python's built-in logging level definitions for maintainability
_valid_levels = set(logging._nameToLevel.keys()) - {'NOTSET'}  # Exclude NOTSET from display
if _level_name not in logging._nameToLevel:
    print(f"WARNING: Invalid SWF_LOG_LEVEL '{_level_name}'. Valid levels: {', '.join(sorted(_valid_levels))}. Using INFO.")
    _level = logging.INFO
else:
    _level = logging._nameToLevel[_level_name]

logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

# STOMP logging is very chatty; enable only if explicitly requested
stomp_logger = logging.getLogger('stomp')
if os.getenv('SWF_STOMP_DEBUG', 'false').lower() in ('1', 'true', 'yes', 'on'):
    stomp_logger.setLevel(logging.DEBUG)
    _stomp_handler = logging.StreamHandler()
    _stomp_handler.setLevel(logging.DEBUG)
    _stomp_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
    stomp_logger.addHandler(_stomp_handler)
else:
    stomp_logger.setLevel(logging.WARNING)


class BaseAgent(stomp.ConnectionListener):
    """
    A base class for creating standalone STF workflow agents.

    This class handles the common tasks of:
    - Connecting to the ActiveMQ message broker (and inheriting from stomp.ConnectionListener).
    - Communicating with the swf-monitor REST API.
    - Running a persistent process with graceful shutdown.
    """

    # Standard workflow message types
    WORKFLOW_MESSAGE_TYPES = {
        'run_imminent', 'start_run', 'pause_run', 'resume_run', 'end_run',
        'stf_gen', 'data_ready'
    }

    def __init__(self, agent_type, subscription_queue, debug=False):
        self.agent_type = agent_type
        self.subscription_queue = subscription_queue
        self.DEBUG = debug

        # Create unique agent name with username and sequential ID
        import getpass
        username = getpass.getuser()
        agent_id = self.get_next_agent_id()
        self.agent_name = f"{self.agent_type.lower()}-agent-{username}-{agent_id}"

        # Configuration from environment variables
        self.monitor_url = os.getenv('SWF_MONITOR_URL', 'http://localhost:8002').rstrip('/')
        # Use HTTP URL for REST logging (no auth required)
        self.base_url = os.getenv('SWF_MONITOR_HTTP_URL', 'http://localhost:8002').rstrip('/')
        self.api_token = os.getenv('SWF_API_TOKEN')
        self.mq_host = os.getenv('ACTIVEMQ_HOST', 'localhost')
        self.mq_port = int(os.getenv('ACTIVEMQ_PORT', 61612))  # STOMP port for Artemis on this system
        self.mq_user = os.getenv('ACTIVEMQ_USER', 'admin')
        self.mq_password = os.getenv('ACTIVEMQ_PASSWORD', 'admin')
        
        # SSL configuration
        self.use_ssl = os.getenv('ACTIVEMQ_USE_SSL', 'False').lower() == 'true'
        self.ssl_ca_certs = os.getenv('ACTIVEMQ_SSL_CA_CERTS', '')
        self.ssl_cert_file = os.getenv('ACTIVEMQ_SSL_CERT_FILE', '')
        self.ssl_key_file = os.getenv('ACTIVEMQ_SSL_KEY_FILE', '')
        
        # Set up centralized REST logging
        self.logger = setup_rest_logging('base_agent', self.agent_name, self.base_url)

        # Create connection matching swf-common-lib working example
        self.conn = stomp.Connection(
            host_and_ports=[(self.mq_host, self.mq_port)],
            vhost=self.mq_host,
            try_loopback_connect=False
        )
        
        # Configure SSL if enabled - must be done before set_listener
        if self.use_ssl:
            import ssl
            logging.info(f"Configuring SSL connection with CA certs: {self.ssl_ca_certs}")
            
            if self.ssl_ca_certs:
                # Configure SSL transport
                self.conn.transport.set_ssl(
                    for_hosts=[(self.mq_host, self.mq_port)],
                    ca_certs=self.ssl_ca_certs,
                    ssl_version=ssl.PROTOCOL_TLS_CLIENT
                )
                logging.info("SSL transport configured successfully")
            else:
                logging.warning("SSL enabled but no CA certificate file specified")
        
        self.conn.set_listener('', self)
        self.api = requests.Session()
        if self.api_token:
            self.api.headers.update({'Authorization': f'Token {self.api_token}'})
        
        # For localhost development, disable SSL verification and proxy
        if 'localhost' in self.monitor_url or '127.0.0.1' in self.monitor_url:
            self.api.verify = False
            # Disable proxy for localhost connections
            self.api.proxies = {
                'http': None,
                'https': None
            }
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def run(self):
        """
        Connects to the message broker and runs the agent's main loop.
        """
        logging.info(f"Starting {self.agent_name}...")
        logging.info(f"Connecting to ActiveMQ at {self.mq_host}:{self.mq_port} with user '{self.mq_user}'")
        
        # Track MQ connection status
        self.mq_connected = False
        
        try:
            logging.debug("Attempting STOMP connection with version 1.1...")
            # Use STOMP version 1.1 with client-id and longer heartbeat for development
            self.conn.connect(
                self.mq_user, 
                self.mq_password, 
                wait=True, 
                version='1.1',
                headers={
                    'client-id': self.agent_name,
                    'heart-beat': '10000,30000'  # Send heartbeat every 10sec, expect server timeout after 30sec
                }
            )
            self.mq_connected = True

            self.conn.subscribe(destination=self.subscription_queue, id=1, ack='auto')
            logging.info(f"Subscribed to queue: '{self.subscription_queue}'")
            
            # Register as subscriber in monitor
            self.register_subscriber()
            
            # Initial registration/heartbeat
            self.send_heartbeat()

            logging.info(f"{self.agent_name} is running. Press Ctrl+C to stop.")
            while True:
                time.sleep(60) # Keep the main thread alive, heartbeats can be added here
                
                # Check connection status and attempt reconnection if needed
                if not self.mq_connected:
                    self._attempt_reconnect()
                    
                self.send_heartbeat()

        except KeyboardInterrupt:
            logging.info(f"Stopping {self.agent_name}...")
        except stomp.exception.ConnectFailedException as e:
            self.mq_connected = False
            logging.error(f"Failed to connect to ActiveMQ: {e}")
            logging.error("Please check the connection details and ensure ActiveMQ is running.")
        except Exception as e:
            self.mq_connected = False
            logging.error(f"An unexpected error occurred: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.conn and self.conn.is_connected():
                self.conn.disconnect()
                self.mq_connected = False
                logging.info("Disconnected from ActiveMQ.")

    def on_connected(self, frame):
        """Handle successful connection to ActiveMQ."""
        logging.info(f"Successfully connected to ActiveMQ: {frame.headers}")
        self.mq_connected = True
    
    def on_error(self, frame):
        logging.error(f'Received an error from ActiveMQ: {frame.body}')
        self.mq_connected = False
    
    def on_disconnected(self):
        """Handle disconnection from ActiveMQ."""
        logging.warning("Disconnected from ActiveMQ - will attempt reconnection")
        self.mq_connected = False
        # Send heartbeat to update status, but don't let failures crash the receiver thread
        try:
            self.send_heartbeat()
        except Exception as e:
            logging.warning(f"Heartbeat failed during disconnect: {e}")

    def _attempt_reconnect(self):
        """Attempt to reconnect to ActiveMQ."""
        if self.mq_connected:
            return True
            
        try:
            logging.info("Attempting to reconnect to ActiveMQ...")
            if self.conn.is_connected():
                self.conn.disconnect()
            
            self.conn.connect(
                self.mq_user,
                self.mq_password,
                wait=True,
                version='1.1',
                headers={
                    'client-id': self.agent_name,
                    'heart-beat': '10000,30000'  # Send heartbeat every 10sec, expect server timeout after 30sec
                }
            )
            
            self.conn.subscribe(destination=self.subscription_queue, id=1, ack='auto')
            self.mq_connected = True
            logging.info("Successfully reconnected to ActiveMQ")
            return True
            
        except Exception as e:
            logging.warning(f"Reconnection attempt failed: {e}")
            self.mq_connected = False
            return False

    def on_message(self, frame):
        """
        Callback for handling incoming messages.
        This method must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement on_message")

    def log_received_message(self, frame, known_types=None):
        """
        Helper method to log received messages with type information.
        Agents can call this at the start of their on_message method.

        Args:
            frame: The STOMP message frame
            known_types: Optional set/list of known message types (defaults to WORKFLOW_MESSAGE_TYPES)

        Returns:
            tuple: (message_data, msg_type) for convenience

        Raises:
            RuntimeError: If message parsing fails
        """
        if known_types is None:
            known_types = self.WORKFLOW_MESSAGE_TYPES

        try:
            import json
            message_data = json.loads(frame.body)
            msg_type = message_data.get('msg_type', 'unknown')

            if msg_type not in known_types:
                logging.info(f"{self.agent_type} agent received unknown message type: {msg_type}", extra={"msg_type": msg_type})
            else:
                logging.info(f"{self.agent_type} agent received message: {msg_type}")

            return message_data, msg_type
        except json.JSONDecodeError as e:
            logging.error(f"CRITICAL: Failed to parse message JSON: {e}")
            raise RuntimeError(f"Message parsing failed - agent cannot continue: {e}") from e

    def get_next_agent_id(self):
        """Get the next agent ID from persistent state API."""
        try:
            url = f"{self.monitor_url}/api/state/next-agent-id/"
            response = self.api.post(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            if data.get('status') == 'success':
                agent_id = data.get('agent_id')
                logging.info(f"Got next agent ID from persistent state: {agent_id}")
                return str(agent_id)  # Return as string for consistency
            else:
                raise RuntimeError(f"API returned error: {data.get('error', 'Unknown error')}")

        except Exception as e:
            logging.error(f"Failed to get next agent ID from API: {e}")
            raise RuntimeError(f"Critical failure getting agent ID: {e}") from e

    def send_message(self, destination, message_body):
        """
        Sends a JSON message to a specific destination.
        """
        try:
            self.conn.send(body=json.dumps(message_body), destination=destination)
            logging.info(f"Sent message to '{destination}': {message_body}")
        except Exception as e:
            logging.error(f"Failed to send message to '{destination}': {e}")
            
            # Check for SSL/connection errors that indicate disconnection
            if any(error_type in str(e).lower() for error_type in ['ssl', 'eof', 'connection', 'broken pipe']):
                logging.warning("Connection error detected - attempting recovery")
                self.mq_connected = False
                time.sleep(1)  # Brief pause before retry
                if self._attempt_reconnect():
                    try:
                        self.conn.send(body=json.dumps(message_body), destination=destination)
                        logging.info(f"Message sent successfully after reconnection to '{destination}'")
                    except Exception as retry_e:
                        logging.error(f"Retry failed after reconnection: {retry_e}")
                else:
                    logging.error("Reconnection failed - message lost")

    def _api_request(self, method, endpoint, json_data=None):
        """
        Helper method to make a request to the monitor API.
        FAILS FAST - raises exception on any API error.
        """
        url = f"{self.monitor_url}/api{endpoint}"
        try:
            # Do not follow redirects; 3xx usually indicates upstream auth middleware (e.g., OIDC)
            response = self.api.request(method, url, json=json_data, timeout=10, allow_redirects=False)
            # Treat redirect as auth/config problem with a clear message
            if 300 <= response.status_code < 400:
                loc = response.headers.get('Location', 'unknown')
                msg = (f"API redirect (HTTP {response.status_code}) to {loc}. "
                       f"If behind Apache/OIDC, ensure API requests aren't redirected and Authorization is forwarded.")
                logging.error(msg)
                raise APIError(msg, response=response, url=url, method=method.upper())
            response.raise_for_status()  # Raise an exception for bad status codes
            return response.json()
        except requests.exceptions.RequestException as e:
            # Check for "already exists" error in subscriber registration
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 400:
                response_text = e.response.text.lower()
                if "already exists" in response_text and "subscriber" in response_text:
                    # This is a normal "already exists" case for subscriber registration
                    logging.info(f"Resource already exists (normal): {method.upper()} {url}")
                    return {"status": "already_exists"}
            
            logging.error(f"API request FAILED: {method.upper()} {url} - {e}")
            if hasattr(e, 'response') and e.response is not None:
                logging.error(f"Response status: {e.response.status_code}")
                logging.error(f"Response body: {e.response.text}")
            raise APIError(f"Critical API failure - agent cannot continue: {method.upper()} {url} - {e}", 
                          response=getattr(e, 'response', None), url=url, method=method.upper()) from e

    def send_heartbeat(self):
        """Registers the agent and sends a heartbeat to the monitor."""
        if self.DEBUG:
            logging.info("Sending heartbeat to monitor...")
        
        # Determine overall status based on MQ connection
        status = "OK" if getattr(self, 'mq_connected', False) else "WARNING"
        
        # Build description with connection details
        mq_status = "connected" if getattr(self, 'mq_connected', False) else "disconnected"
        description = f"{self.agent_type} agent. MQ: {mq_status}"
        
        payload = {
            "instance_name": self.agent_name,
            "agent_type": self.agent_type,
            "status": status,
            "description": description,
            "mq_connected": getattr(self, 'mq_connected', False)  # Include MQ status in payload
        }
        
        result = self._api_request('post', '/systemagents/heartbeat/', payload)
        if result:
            if self.DEBUG:
                logging.info(f"Heartbeat sent successfully. Status: {status}, MQ: {mq_status}")
        else:
            logging.warning("Failed to send heartbeat to monitor")
    
    def send_enhanced_heartbeat(self, workflow_metadata=None):
        """Send heartbeat with optional workflow metadata."""
        if self.DEBUG:
            logging.info("Sending heartbeat to monitor...")
        
        # Determine overall status based on MQ connection
        status = "OK" if getattr(self, 'mq_connected', False) else "WARNING"
        
        # Build description with connection details
        mq_status = "connected" if getattr(self, 'mq_connected', False) else "disconnected"
        description_parts = [f"{self.agent_type} agent", f"MQ: {mq_status}"]
        
        # Add workflow context if provided
        if workflow_metadata:
            for key, value in workflow_metadata.items():
                description_parts.append(f"{key}: {value}")
        
        description = ". ".join(description_parts)
        
        payload = {
            "instance_name": self.agent_name,
            "agent_type": self.agent_type,
            "status": status,
            "description": description,
            "mq_connected": getattr(self, 'mq_connected', False),
            # Include workflow metadata in agent record
            "workflow_enabled": True if workflow_metadata else False,
            "current_stf_count": workflow_metadata.get('active_tasks', 0) if workflow_metadata else 0,
            "total_stf_processed": workflow_metadata.get('completed_tasks', 0) if workflow_metadata else 0
        }
        
        result = self._api_request('post', '/systemagents/heartbeat/', payload)
        if result:
            if self.DEBUG:
                logging.info(f"Heartbeat sent successfully")
            return True
        else:
            logging.warning("Failed to send heartbeat to monitor")
            return False
    
    def report_agent_status(self, status, message=None, error_details=None):
        """Report agent status change to monitor."""
        logging.info(f"Reporting agent status: {status}")
        
        description_parts = [f"{self.agent_type} agent"]
        if message:
            description_parts.append(message)
        if error_details:
            description_parts.append(f"Error: {error_details}")
        
        payload = {
            "instance_name": self.agent_name,
            "agent_type": self.agent_type,
            "status": status,
            "description": ". ".join(description_parts),
            "mq_connected": getattr(self, 'mq_connected', False)
        }
        
        result = self._api_request('post', '/systemagents/heartbeat/', payload)
        if result:
            logging.info(f"Status reported successfully: {status}")
            return True
        else:
            logging.warning(f"Failed to report status: {status}")
            return False
    
    def check_monitor_health(self):
        """Check if monitor API is available."""
        try:
            result = self._api_request('get', '/systemagents/', None)
            if result is not None:
                logging.info("Monitor API is healthy")
                return True
            else:
                logging.warning("Monitor API is not responding")
                return False
        except Exception as e:
            logging.error(f"Monitor health check failed: {e}")
            return False
    
    def call_monitor_api(self, method, endpoint, json_data=None):
        """Generic monitor API call method for agent-specific implementations."""
        return self._api_request(method.lower(), endpoint, json_data)
    
    def register_subscriber(self):
        """Register this agent as a subscriber to its ActiveMQ queue."""
        logging.info(f"Registering subscriber for queue '{self.subscription_queue}'...")
        
        subscriber_data = {
            "subscriber_name": f"{self.agent_name}-{self.subscription_queue}",
            "description": f"{self.agent_type} agent subscribing to {self.subscription_queue}",
            "is_active": True,
            "fraction": 1.0  # Receives all messages
        }
        
        try:
            result = self._api_request('post', '/subscribers/', subscriber_data)
            if result:
                if result.get('status') == 'already_exists':
                    logging.info(f"Subscriber already registered: {subscriber_data['subscriber_name']}")
                    return True
                else:
                    logging.info(f"Subscriber registered successfully: {result.get('subscriber_name')}")
                    return True
            else:
                logging.error("Failed to register subscriber")
                return False
        except Exception as e:
            # Other registration failures are critical
            logging.error(f"Critical subscriber registration failure: {e}")
            raise e