"""
Testbed configuration utilities.

Provides loading and validation of testbed instance configuration (testbed.toml).
"""

import tomllib
from pathlib import Path


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
            namespace: The testbed namespace (must not be empty)
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
            TestbedConfigError: If config file not found, invalid, or namespace empty
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

        # Extract testbed section
        testbed_section = config_data.get('testbed')
        if not testbed_section:
            raise TestbedConfigError(
                f"Missing [testbed] section in {config_file}"
            )

        # Extract and validate namespace
        namespace = testbed_section.get('namespace')
        if namespace is None:
            raise TestbedConfigError(
                f"Missing 'namespace' in [testbed] section of {config_file}"
            )

        if namespace == '':
            raise TestbedConfigError(
                f"Namespace not configured in {config_file}\n"
                f"Edit the file and set namespace to your testbed instance name.\n"
                f"Examples: 'epic-fastmon-dev', 'collab-dec29', 'mytest1'"
            )

        return cls(namespace=namespace)

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
        TestbedConfigError: If config is missing, invalid, or namespace empty
    """
    return TestbedConfig.load(config_path=config_path)
