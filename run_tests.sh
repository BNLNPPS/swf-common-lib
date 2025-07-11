#!/bin/bash
set -e

# This script runs the pytest tests for the swf-common-lib project.

# Check if a virtual environment is active
if [ -z "$VIRTUAL_ENV" ]; then
    echo "❌ Error: No Python virtual environment is active"
    echo "   Please activate the swf-testbed virtual environment first:"
    echo "   cd swf-testbed && source .venv/bin/activate"
    exit 1
fi

echo "Using Python environment: $VIRTUAL_ENV"
echo "Running pytest for swf-common-lib..."
python -m pytest
