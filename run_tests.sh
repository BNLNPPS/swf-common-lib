#!/bin/bash
set -e

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Define the virtual environment directory
# Assumes a venv is created in the swf-common-lib directory
VENV_DIR="$SCRIPT_DIR/venv"

# Check if the virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found at $VENV_DIR."
    echo "Please run the setup procedure to create it."
    exit 1
fi

# Activate the virtual environment and run tests
echo "Activating Python environment from $VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "Running pytest for swf-common-lib..."
python -m pytest
