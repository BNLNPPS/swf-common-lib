"""
API utility functions for swf-monitor communication.

These utilities are shared between BaseAgent and other components that need
to interact with the swf-monitor REST API but don't inherit from BaseAgent.
"""

import logging


def get_next_agent_id(monitor_url, api_session, logger=None):
    """
    Get the next agent ID from persistent state API.

    Args:
        monitor_url (str): Base URL of the swf-monitor service
        api_session (requests.Session): Configured session with auth headers
        logger (logging.Logger, optional): Logger for output, defaults to root logger

    Returns:
        str: Next agent ID as string

    Raises:
        RuntimeError: If API call fails or returns error
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    try:
        url = f"{monitor_url}/api/state/next-agent-id/"
        response = api_session.post(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        if data.get('status') == 'success':
            agent_id = data.get('agent_id')
            logger.info(f"Got next agent ID from persistent state: {agent_id}")
            return str(agent_id)  # Return as string for consistency
        else:
            raise RuntimeError(f"API returned error: {data.get('error', 'Unknown error')}")

    except Exception as e:
        logger.error(f"Failed to get next agent ID from API: {e}")
        raise RuntimeError(f"Critical failure getting agent ID: {e}") from e


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
        response = api_session.post(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        if data.get('status') == 'success':
            run_number = data.get('run_number')
            logger.info(f"Got next run number from persistent state: {run_number}")
            return str(run_number)  # Return as string for consistency
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
        response = api_session.post(url, json=payload, timeout=10)
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