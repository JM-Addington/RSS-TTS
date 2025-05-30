# DevContainer for RSS-TTS

This directory contains configuration files for developing the RSS-TTS project using VS Code's Dev Containers feature.

## Configuration

The devcontainer setup uses a modified version of the main project's Docker configuration with different port mappings to avoid conflicts:

- Django app: Port 9000 (instead of 8000/8085)
- Caddy reverse proxy: Port 9084 (instead of 8084/8086)

## Workspace Configuration

- The workspace is mounted at `/workspaces/RSS-TTS` inside the container
- Node.js 20.x is installed for frontend development and tooling
- Pre-commit hooks are automatically set up during container creation

## Services

The devcontainer includes the following services:

1. **app**: The main Django application container for development
2. **worker**: Celery worker for processing tasks
3. **caddy**: Web server for serving static files and proxying requests
4. **redis**: Message broker for Celery

## Getting Started

1. Install the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension in VS Code
2. Open the RSS-TTS project folder in VS Code
3. Click the green button in the bottom-left corner of VS Code or press F1 and select "Dev Containers: Reopen in Container"
4. VS Code will build and start the development container

## Usage

Once the container is running, you can:

- Access the Django app at http://localhost:9000
- Access the Caddy-served content at http://localhost:9084
- Run commands inside the container using VS Code's terminal
- Debug the application using VS Code's debugging features
- Run the development server with `python manage.py runserver 0.0.0.0:9000`
- Start the Celery worker with `python -m celery -A rss_tts worker --loglevel=info`

## Customization

You can customize the devcontainer by modifying:

- `devcontainer.json`: VS Code settings and extensions
- `docker-compose.yml`: Container configuration and port mappings
- `Dockerfile`: Container image definition
- `Caddyfile`: Caddy web server configuration
- `post-create.sh`: Commands to run after container creation
