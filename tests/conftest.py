"""
This conftest.py ensures that if pytest is run directly on a test file (not via the test script or project root),
it will gently fail with a clear message instructing the user to use the correct test runner for robustness.

Test files should be located in tests/ directory and discovered automatically by the test runner.
"""
import os
import pytest

def pytest_configure(config):
    # Only check for direct invocation, not when run via the test script or project root
    # For swf-common-lib, check that we're in the repo root directory
    if os.path.basename(os.getcwd()) != "swf-common-lib":
        pytest.exit(
            "\n[SWF-COMMON-LIB TEST SUITE]\n\n"
            "You are running pytest in a way that does not use the robust test runner.\n"
            "For robust and reliable results, always run tests using:\n"
            "  ./run_tests.sh   (from swf-common-lib repo root directory)\n"
            "or\n"
            "  ./run_all_tests.sh   (from the umbrella/testbed repo root)\n\n"
            "Test files should be in tests/ directory and will be discovered automatically.\n"
            "Direct invocation of pytest on a test file or from the wrong directory is not supported.\n",
            returncode=4
        )
