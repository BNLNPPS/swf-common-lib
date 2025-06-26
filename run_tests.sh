#!/bin/bash
set -e

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
VENV_DIR="$SCRIPT_DIR/venv"

# If a virtual environment is already active, use it
if [ -n "$VIRTUAL_ENV" ]; then
    echo "Using already active Python environment: $VIRTUAL_ENV"
# Otherwise, try to activate the local venv if it exists
elif [ -d "$VENV_DIR" ]; then
    echo "Activating Python environment from $VENV_DIR"
    source "$VENV_DIR/bin/activate"
else
    echo "Error: No active Python environment found and no local venv at $VENV_DIR."
    echo "This script must be run with an active Python environment."
    exit 1
fi

echo "Running pytest for swf-common-lib..."
python -m pytest
