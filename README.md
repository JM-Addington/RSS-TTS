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
- `SITE_URL`: Full URL of your site (e.g., "https://example.com") for RSS feed links

### Docker Development

We use Docker Compose for local development to ensure consistency across environments. The application uses Caddy as a reverse proxy to serve static MP3 files with proper byte-range support (required by Apple Podcasts) and to proxy other requests to Django.

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

#### Architecture

The application consists of the following services:
- **Caddy**: Web server that handles:
  - Static MP3 file serving with automatic byte-range support at `/audio/<uuid>/`
  - Reverse proxy for all other requests to Django
  - Automatic HTTPS in production
- **Web**: Django application server
- **Worker**: Celery worker for processing audio conversion tasks
- **Redis**: Message broker for Celery

Both the **web** and **worker** services invoke `/app/start-web.sh` which runs
`python manage.py migrate` before launching. This ensures database migrations
are automatically applied whenever new Docker images are deployed.

#### Media Files

MP3 files are stored in the `./media/articles/` directory and served directly by Caddy for optimal performance. The files are:
- Saved by the worker as `./media/articles/{uuid}.mp3`
- Accessible via HTTP at `/audio/{uuid}/`
- Shared between containers via a bind mount

To use Docker volumes instead of bind mounts for media files, uncomment the relevant sections in the docker-compose files.

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

Configuration for these tools lives in `setup.cfg`. Flake8 enforces a McCabe
complexity limit of 20, and mypy reads its options from the same file.

Install pre-commit hooks to automatically run these tools. You can run the
commands manually or execute the provided helper script. The script now also
sets up a pre-push hook so Black formatting and mypy checks run before pushing
changes to GitHub:

```bash
./setup_precommit.sh
```

The script installs the `pre-commit` package if needed and configures the git
hooks for you.

### Coding Standards

We follow the [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guide for Python code. All classes, methods and functions should include docstrings using the [Google Python style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings). See [CODING_STANDARDS.md](CODING_STANDARDS.md) for our complete coding guidelines.

### Branching Strategy

- `main` is for production code
- `dev/main` is for development
- Feature branches should follow the format `feature/description`
- See [AGENTS.md](AGENTS.md) for more details on branch management

## Features

### ChunkToneService (LLM-Driven Audio Processing)

The application includes an advanced LLM-driven text chunking and voice assignment system called ChunkToneService. This feature can replace the traditional chunking pipeline with intelligent, context-aware processing.

**Key Features:**
- **Intelligent Chunking**: Uses OpenAI GPT models to break text into logical segments
- **Voice Assignment**: Automatically assigns appropriate voices for different speakers/narrators
- **Character Recognition**: Identifies dialogue and assigns character-specific voices
- **Fallback Safety**: Always produces valid output, even when LLM processing fails

**Configuration:**
```bash
# Enable ChunkToneService (default: false)
ENABLE_CHUNK_TONE_LLM=true
```

**Available Voices:**
- `alloy` - Default narrator voice
- `echo` - Character dialogue
- `fable` - Storytelling
- `onyx` - Bold/dramatic characters
- `nova` - Casual/conversational
- `shimmer` - News/formal content

For detailed documentation, see [docs/chunk_tone_service.md](docs/chunk_tone_service.md).

## Tests

Activate the virtual environment and run:

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run tests
python -m unittest discover -s tests
```

### Running Tests Without Audio Dependencies

If you encounter issues with audio dependencies (pydub/audioop), you can use our test scripts with mocked audio dependencies:

```bash
# Run a specific test file
python run_single_test.py tests/test_models.py

# Run all tests with mocked audio dependencies
python run_all_tests_with_mock.py
```

For more details on testing approach, see [TESTING.md](TESTING.md).

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
