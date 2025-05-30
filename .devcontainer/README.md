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
- The container starts with an interactive bash shell

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

Once the container is running, you can use the following commands:

- `start-server` - Start Django development server
- `start-worker` - Start Celery worker
- `start-all` - Start both server and worker
- `run-tests` - Run tests with mock
- `lint` - Run linters (flake8, black, mypy)
- `setup-db` - Setup database with migrations and create admin user
- `create-feed` - Create a test feed for the admin user
- `start-dev` - Start development environment with all services
- `generate-article` - Create a test article for processing

### Quick Start Development

For a quick start:

1. Run `setup-db` to initialize the database and create an admin user
2. Run `start-dev` to start both Django and Celery worker
3. Run `create-feed` to add a test feed
4. Run `generate-article` to create a test article
5. Access the app at http://localhost:9000 and admin at http://localhost:9000/admin

## Key URLs

- Django app: http://localhost:9000
- Django admin: http://localhost:9000/admin (user: admin, password: admin)
- Caddy proxy: http://localhost:9084

## Customization

You can customize the devcontainer by modifying:

- `devcontainer.json`: VS Code settings and extensions
- `docker-compose.yml`: Container configuration and port mappings
- `Dockerfile`: Container image definition
- `Caddyfile`: Caddy web server configuration
- `entrypoint.sh`: Container startup configuration
- `scripts/`: Helper scripts for development tasks
