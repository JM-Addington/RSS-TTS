#!/bin/bash
set -e

# For development: install/update requirements if requirements.txt is newer
if [ -f requirements.txt ] && [ "$DJANGO_DEBUG" = "True" ]; then
    echo "Development mode: checking requirements..."
    pip install -r requirements.txt --quiet
fi

# Start worker - use $@ to pass through the original command
# Note: The worker will connect to the database when needed during task execution
exec "$@"
