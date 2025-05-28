#!/bin/bash
set -e

echo "Setting up RSS-TTS development environment..."

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt
pip install -r requirements-test.txt

# Setup pre-commit hooks
echo "Setting up pre-commit hooks..."
./setup_precommit.sh

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from example..."
    if [ -f .env.example ]; then
        cp .env.example .env
    elif [ -f .env.sample ]; then
        cp .env.sample .env
    else
        echo "No .env template found. Creating basic .env file..."
        cat > .env << EOF
DJANGO_SECRET_KEY=codespace-dev-secret-key
DJANGO_DEBUG=True
CELERY_BROKER_URL=redis://redis:6379/0
SITE_URL=https://${CODESPACE_NAME}-8084.app.github.dev
EOF
    fi
    echo "Please update .env with your settings"
fi

npm install -g @anthropic-ai/claude-code

echo "Setup complete! You can now run the development server with:"
echo "python manage.py runserver 0.0.0.0:8000"
