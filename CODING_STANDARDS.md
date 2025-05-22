# Coding Standards

This document outlines the coding standards and best practices for the RSS-TTS project.

## Python Style Guide

We follow the [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guide for Python code. Key points include:

- Use 4 spaces for indentation (no tabs)
- Maximum line length of 88 characters (following Black's default)
- Use snake_case for variable, function, and method names
- Use CamelCase for class names
- Use UPPER_CASE for constants
- Use descriptive variable and function names

## Django Best Practices

- Follow the [Django coding style](https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/coding-style/)
- Use Django's ORM features instead of raw SQL when possible
- Keep views lightweight, moving business logic to models and services
- Use Django forms for data validation
- Follow REST principles in API design with Django REST Framework

## Documentation

- Use docstrings for all classes, methods, and functions
- Follow [Google's Python Style Guide](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings) for docstring format
- Include type hints where appropriate (using Python's typing module)
- Maintain up-to-date documentation in README.md and other markdown files

## Testing

- Write tests before implementing features (TDD approach)
- Aim for high test coverage, especially for core functionality
- Use Django's testing framework for views and models
- Use pytest for more complex test scenarios
- Mock external services (e.g., OpenAI API) in tests

## Version Control

- Follow the branching strategy outlined in AGENTS.md
- Use semantic commit messages (feat, fix, refactor, docs, etc.)
- Keep commits small and focused on a single change
- Write clear commit messages in the imperative mood

## Code Quality Tools

We use the following tools to maintain code quality:

- **Black**: For automatic code formatting
- **isort**: For sorting imports
- **Flake8**: For linting
- **mypy**: For static type checking

## Pre-commit Hooks

Set up pre-commit hooks to automatically run:
- Black for formatting
- isort for import sorting
- Flake8 for linting
- Tests for critical functionality

## Continuous Integration

We use GitHub Actions for CI to:
- Run all tests
- Check code formatting
- Verify type hints
- Ensure all checks pass before merging to main branches

## Security Best Practices

- Never commit API keys or secrets (use environment variables)
- Validate all user inputs
- Use Django's security features (CSRF protection, XSS prevention)
- Follow OWASP security guidelines for web applications
