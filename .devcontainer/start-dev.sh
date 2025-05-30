#!/bin/bash
set -e

# Setup script for auto-starting development servers
echo "Starting RSS-TTS development environment..."

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Function to start Django development server
start_django_server() {
  echo "Starting Django development server on port 9000..."
  python manage.py runserver 0.0.0.0:9000
}

# Function to start Celery worker
start_celery_worker() {
  echo "Starting Celery worker..."
  python -m celery -A rss_tts worker --loglevel=info
}

# Check if screen or tmux is available for session management
if command_exists screen; then
  echo "Using screen for session management..."

  # Start Django server in a screen session
  screen -dmS django bash -c "cd /workspaces/RSS-TTS && start_django_server; exec bash"
  echo "Django server started in screen session 'django'"

  # Start Celery worker in a screen session
  screen -dmS celery bash -c "cd /workspaces/RSS-TTS && start_celery_worker; exec bash"
  echo "Celery worker started in screen session 'celery'"

  echo "Use 'screen -r django' or 'screen -r celery' to attach to sessions"
elif command_exists tmux; then
  echo "Using tmux for session management..."

  # Start a new tmux session for Django
  tmux new-session -d -s django "cd /workspaces/RSS-TTS && python manage.py runserver 0.0.0.0:9000"
  echo "Django server started in tmux session 'django'"

  # Start a new tmux session for Celery
  tmux new-session -d -s celery "cd /workspaces/RSS-TTS && python -m celery -A rss_tts worker --loglevel=info"
  echo "Celery worker started in tmux session 'celery'"

  echo "Use 'tmux attach -t django' or 'tmux attach -t celery' to attach to sessions"
else
  echo "No session manager (screen/tmux) found. Starting in current terminal..."
  echo "Note: This will block the current terminal. Use Ctrl+C to stop."
  echo "Starting Django server in 5 seconds... Press Ctrl+C to cancel."
  sleep 5

  # Start Django server in foreground
  start_django_server
fi

echo "Development environment started!"
