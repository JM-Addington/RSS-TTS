#!/bin/bash
set -e

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate

# Start web server - use $@ to pass through the original command
exec "$@"
