#!/bin/bash
set -e

# Setup the environment
export PATH="/home/vscode/.npm-global/bin:$PATH"
cd /workspaces/RSS-TTS

# Print welcome message
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║                 Welcome to RSS-TTS Development                 ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Project directory: /workspaces/RSS-TTS"
echo "Development server: http://localhost:9000"
echo "Caddy proxy: http://localhost:9084"
echo ""
echo "Available commands:"
echo "  start-server     - Start Django development server"
echo "  start-worker     - Start Celery worker"
echo "  start-all        - Start both server and worker"
echo "  run-tests        - Run tests with mock"
echo "  lint             - Run linters (flake8, black, mypy)"
echo "  setup-db         - Setup database with migrations and create admin user"
echo "  create-feed      - Create a test feed for the admin user"
echo "  start-dev        - Start development environment with all services"
echo "  generate-article - Create a test article for processing"
echo ""

# Create aliases for common commands
echo "Setting up development aliases..."
echo "alias start-server='python manage.py runserver 0.0.0.0:9000'" >> ~/.bashrc
echo "alias start-worker='python -m celery -A rss_tts worker --loglevel=info'" >> ~/.bashrc
echo "alias start-all='start-server & start-worker'" >> ~/.bashrc
echo "alias run-tests='python run_all_tests_with_mock.py'" >> ~/.bashrc
echo "alias lint='flake8 && black --check . && mypy .'" >> ~/.bashrc
echo "alias setup-db='/workspaces/RSS-TTS/.devcontainer/scripts/setup-db.sh'" >> ~/.bashrc
echo "alias create-feed='/workspaces/RSS-TTS/.devcontainer/scripts/create-feed.sh'" >> ~/.bashrc
echo "alias start-dev='/workspaces/RSS-TTS/.devcontainer/start-dev.sh'" >> ~/.bashrc
echo "alias generate-article='/workspaces/RSS-TTS/.devcontainer/scripts/generate-test-article.sh'" >> ~/.bashrc
source ~/.bashrc

# Keep container running with a proper interactive shell
exec "$@"
sleep infinity
