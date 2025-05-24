Use as many subtasks as you can.

Work as independently as possible, this project is 100% AI driven.

Remember to use TDD.

## Architectural Decisions

### Media File Serving with Caddy (2025-05-24)

We use Caddy as a reverse proxy to serve MP3 files directly instead of Django for the following reasons:

1. **Apple Podcasts Requirement**: Apple Podcasts requires byte-range request support for streaming MP3 files. When Apple Podcasts requests part of a file, the server must return HTTP 206 (Partial Content), not HTTP 200.

2. **Automatic Byte-Range Support**: Caddy handles byte-range requests automatically without any custom code, while Django's FileResponse doesn't properly support this out of the box.

3. **Better Performance**: Static file serving through a web server like Caddy is significantly more performant than serving through Django/Python.

4. **Cleaner Architecture**: Separation of concerns - Caddy handles static files, Django handles application logic.

5. **Automatic HTTPS**: In production, Caddy provides automatic SSL/TLS certificate management.

The implementation:
- MP3 files are saved to `./media/articles/{uuid}.mp3` by the Celery worker
- Caddy serves these files at `/audio/{uuid}/` with proper byte-range support
- Django continues to handle authentication and generates the RSS feeds
- Files are shared between containers via a bind mount for easy filesystem access

## Documentation

You should always read these other files in the repo:
- README.md (if it exists)
- CLAUDE.md (if it exists)
- PROJECT_PLAN.md (if it exists)
- CODING_STANDARDS.md (if it exists)

## Project Setup

When setting up the project for development, make sure to:

1. Read the README.md for basic setup instructions
2. Follow the coding standards in CODING_STANDARDS.md
3. Set up pre-commit hooks to enforce code quality
4. Reference the PROJECT_PLAN.md for the overall roadmap

## PR Reviews

PR reviews should be thorough and constructive.

You should:
- Review the code for correctness, readability, and adherence to coding standards
- Review all comments. Keep in mind that many are AI generated and may not be relevant. They _usually_
  are, but not always.
- Check for any potential security issues
- Ensure that the code is well-documented and includes tests
- Ensure that all automated tests run and pass
- Comment "/review" as the last time, and review the automated comments afterwards (takes 2-3 minutes)

## Committing

Always run pre-commit before committing. If the hooks are set up correctly, they will run automatically but your commit may fail depending on the errors.

## Testing

All tests must be run inside docker. The local environment does NOT have all of the dependencies installed and the tests WILL fail.
