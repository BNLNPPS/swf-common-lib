"""
Testbed configuration utilities.

Provides loading and validation of testbed instance configuration (testbed.toml).
"""

import getpass
import tomllib
from pathlib import Path


def testbed_namespace(config: dict) -> str:
    """The namespace a testbed configuration names: its [testbed]
    namespace, or the user's own login name when that is unset or empty.
    A user who starts without a configuration of their own therefore works
    in their own namespace, never in another user's. Every reader of the
    namespace goes through this function."""
    return ((config or {}).get('testbed') or {}).get('namespace') or getpass.getuser()


class TestbedConfigError(Exception):
    """Raised when testbed configuration is invalid or missing."""
    pass


class TestbedConfig:
    """
    Testbed instance configuration.

    Loads configuration from testbed.toml and provides access to settings.
    """

    def __init__(self, namespace: str):
        """
        Initialize with validated namespace.

        Args:
            namespace: The testbed namespace
        """
        self.namespace = namespace

    @classmethod
    def load(cls, config_path: str) -> 'TestbedConfig':
        """
        Load testbed configuration from file.

        Args:
            config_path: Path to config file

        Returns:
            TestbedConfig instance

        Raises:
            TestbedConfigError: If config file not found or invalid
        """
        config_file = Path(config_path)

        # Check file exists
        if not config_file.exists():
            raise TestbedConfigError(
                f"Testbed config not found: {config_file}\n"
                f"Create testbed.toml with [testbed] section and namespace setting."
            )

        # Load TOML
        try:
            with open(config_file, 'rb') as f:
                config_data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise TestbedConfigError(f"Invalid TOML in {config_file}: {e}")

        return cls(namespace=testbed_namespace(config_data))

    def __repr__(self) -> str:
        return f"TestbedConfig(namespace='{self.namespace}')"


def load_testbed_config(config_path: str) -> TestbedConfig:
    """
    Load testbed configuration from file.

    Args:
        config_path: Path to config file

    Returns:
        TestbedConfig instance

    Raises:
        TestbedConfigError: If config is missing or invalid
    """
    return TestbedConfig.load(config_path=config_path)
