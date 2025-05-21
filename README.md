# RSS-TTS

This project converts web articles and text into audio files using Django and Django REST Framework. It allows users to submit URLs or text and receive audio versions through a private RSS feed, suitable for podcast applications.

## Project Overview

| Area | Summary |
| --- | --- |
| **Vision** | Turn web articles, blog posts, or text into high-quality audio available through a private podcast-style RSS feed. |
| **Technology Stack** | Django 5 + DRF • Celery 6 + Redis • SQLite • OpenAI TTS • Bootstrap 5 for UI. |

For more details, see [PROJECT_PLAN.md](PROJECT_PLAN.md).
Each user manages one or more **Feeds**. A feed groups a user's converted articles and is accessed via a unique token-based URL, e.g. `/feeds/<feed_token>/`. The token is generated using UUID4 when the feed is created so the RSS feed remains private.

## Setup

### Local Development

Install dependencies in a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the development server:

```bash
python manage.py runserver
```

### Environment Configuration

The project uses environment variables for configuration. Copy the example file and adjust as needed:

```bash
cp .env.example .env
# Edit .env with your settings
```

Key environment variables:
- `DJANGO_SECRET_KEY`: Secret key for Django (required)
- `DJANGO_DEBUG`: Set to "True" for development
- `SQLITE_DATA_DIR`: Directory to store SQLite database (optional)
- `CELERY_BROKER_URL`: Redis URL for Celery

### Docker Development

We use Docker Compose for local development to ensure consistency across environments:

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down

# For production
# First, ensure you've set up your .env file with appropriate production values
cp .env.example .env
# Edit .env with production settings
docker-compose -f docker-compose.prod.yml up -d
```

Redis runs inside the worker container. Its data lives in `/data/redis` which is
mapped to the named volume `redis-data`. If you want to persist Redis data on
your host machine, replace that volume mapping with a bind mount:

```yaml
services:
  worker:
    volumes:
      - ./redis-data:/data/redis
```

### Environment Configuration

Copy `.env.sample` to `.env` and update the values with your local secrets:

```bash
cp .env.sample .env
```

The application and Docker Compose will load environment variables from this file.

### GitHub Codespaces

This project is configured to work with GitHub Codespaces:

1. In GitHub, click the "Code" button on the repository
2. Select the "Codespaces" tab
3. Click "Create codespace on main"

The Codespace will automatically build the Docker environment and provide a full development setup with all dependencies installed.

## Development

### Code Quality

We use several tools to maintain code quality:

- **Black**: For code formatting
- **isort**: For import sorting
- **Flake8**: For linting
- **mypy**: For type checking

Install pre-commit hooks to automatically run these tools:

```bash
pip install pre-commit
pre-commit install
```

### Coding Standards

We follow the [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guide for Python code. All classes, methods and functions should include docstrings using the [Google Python style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings). See [CODING_STANDARDS.md](CODING_STANDARDS.md) for our complete coding guidelines.

### Branching Strategy

- `main` is for production code
- `dev/main` is for development
- Feature branches should follow the format `feature/description`
- See [AGENTS.md](AGENTS.md) for more details on branch management

## Tests

Activate the virtual environment and run:

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run tests
python -m unittest discover -s tests
```

## Continuous Integration

We use GitHub Actions for continuous integration. On each push to `main` or `dev/main`, and for pull requests to these branches, the CI will:

- Run all tests
- Check code formatting with Black
- Run linting with Flake8
- Perform type checking with mypy

See `.github/workflows/` directory for workflow files:
- `00-lint.yml`: Runs code formatting and linting
- `10-type-check.yml`: Performs type checking with mypy
- `20-test.yml`: Runs the test suite
- `90-pr-review.yml`: Provides automated PR reviews
