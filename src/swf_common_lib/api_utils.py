"""
API utility functions for swf-monitor communication.

These utilities are shared between BaseAgent and other components that need
to interact with the swf-monitor REST API but don't inherit from BaseAgent.
"""

import time
import logging
import requests


RETRY_DELAYS = (2, 5, 10, 20, 40, 60)
RETRYABLE_STATUS_CODES = {404, 500, 502, 503, 504}


def api_request_with_retry(method, url, session=None, logger=None, **kwargs):
    """
    Make an HTTP request with exponential backoff retry on transient failures.

    Retries on: ConnectionError, Timeout, 502/503/504.
    Fails immediately on: 4xx, redirects, other errors.

    Args:
        method: HTTP method ('get', 'post', etc.)
        url: Full URL
        session: requests.Session to use (falls back to requests module)
        logger: Logger instance
        **kwargs: Passed to requests (json, timeout, etc.)

    Returns:
        requests.Response on success

    Raises:
        requests.exceptions.RequestException on final failure
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    if session is None:
        session = requests

    kwargs.setdefault('timeout', 10)

    last_exception = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            response = session.request(method, url, **kwargs)

            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt < len(RETRY_DELAYS):
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"Retryable HTTP {response.status_code} from {method.upper()} {url}, "
                        f"retry {attempt + 1}/{len(RETRY_DELAYS)} in {delay}s"
                    )
                    time.sleep(delay)
                    continue
                else:
                    response.raise_for_status()

            return response

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exception = e
            if attempt < len(RETRY_DELAYS):
                delay = RETRY_DELAYS[attempt]
                logger.warning(
                    f"{type(e).__name__} on {method.upper()} {url}, "
                    f"retry {attempt + 1}/{len(RETRY_DELAYS)} in {delay}s"
                )
                time.sleep(delay)
            else:
                raise

    raise last_exception


def get_next_agent_id(monitor_url, api_session, logger=None):
    """
    Get the next agent ID from persistent state API.

    Retries indefinitely with capped backoff so that a transient API outage
    does not permanently kill the agent (supervisord would hit startretries
    and mark the process FATAL).

    Args:
        monitor_url (str): Base URL of the swf-monitor service
        api_session (requests.Session): Configured session with auth headers
        logger (logging.Logger, optional): Logger for output, defaults to root logger

    Returns:
        str: Next agent ID as string
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    url = f"{monitor_url}/api/state/next-agent-id/"
    attempt = 0
    while True:
        try:
            response = api_request_with_retry('post', url, session=api_session, logger=logger)
            response.raise_for_status()

            data = response.json()
            if data.get('status') == 'success':
                agent_id = data.get('agent_id')
                logger.info(f"Got next agent ID from persistent state: {agent_id}")
                return str(agent_id)
            else:
                raise RuntimeError(f"API returned error: {data.get('error', 'Unknown error')}")

        except Exception as e:
            attempt += 1
            delay = min(60, 5 * attempt)  # 5, 10, 15, ... capped at 60s
            logger.warning(
                f"Failed to get agent ID (attempt {attempt}): {e} — retrying in {delay}s"
            )
            time.sleep(delay)


def get_next_run_number(monitor_url, api_session, logger=None):
    """
    Get the next run number from persistent state API.

    Args:
        monitor_url (str): Base URL of the swf-monitor service
        api_session (requests.Session): Configured session with auth headers
        logger (logging.Logger, optional): Logger for output, defaults to root logger

    Returns:
        str: Next run number as string

    Raises:
        RuntimeError: If API call fails or returns error
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    try:
        url = f"{monitor_url}/api/state/next-run-number/"
        response = api_request_with_retry('post', url, session=api_session, logger=logger)
        response.raise_for_status()

        data = response.json()
        if data.get('status') == 'success':
            run_number = data.get('run_number')
            logger.info(f"Got next run number from persistent state: {run_number}")
            return str(run_number)
        else:
            raise RuntimeError(f"API returned error: {data.get('error', 'Unknown error')}")

    except Exception as e:
        logger.error(f"Failed to get next run number from API: {e}")
        raise RuntimeError(f"Critical failure getting run number: {e}") from e


def ensure_namespace(monitor_url, api_session, name, owner=None, logger=None):
    """
    Ensure a namespace exists in the database, creating it if not.

    Args:
        monitor_url (str): Base URL of the swf-monitor service
        api_session (requests.Session): Configured session with auth headers
        name (str): Namespace name
        owner (str, optional): Owner username, defaults to current user
        logger (logging.Logger, optional): Logger for output

    Returns:
        dict: Namespace info with keys: name, owner, description, created (bool)

    Raises:
        RuntimeError: If API call fails or returns error
    """
    import os

    if logger is None:
        logger = logging.getLogger(__name__)

    if owner is None:
        owner = os.getenv('USER', 'unknown')

    try:
        url = f"{monitor_url}/api/namespaces/ensure/"
        payload = {'name': name, 'owner': owner}
        response = api_request_with_retry('post', url, session=api_session, logger=logger, json=payload)
        response.raise_for_status()

        data = response.json()
        if data.get('status') == 'success':
            if data.get('created'):
                logger.info(f"Created namespace '{name}' with owner '{owner}'")
            return data
        else:
            raise RuntimeError(f"API returned error: {data.get('error', 'Unknown error')}")

    except Exception as e:
        logger.warning(f"Failed to ensure namespace '{name}': {e}")
        raise