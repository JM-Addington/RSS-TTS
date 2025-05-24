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

## OpenAI API Usage and Cost Tracking

To monitor costs and usage patterns associated with OpenAI API calls, it is crucial to log relevant statistics for every interaction with the API.

Specifically, for services like Text-to-Speech (TTS) or other token-based services:
- **Token Usage**: Always attempt to capture the number of tokens consumed by the request. This information is often available in the API response (e.g., in a `usage` object or specific headers). If the exact token count is not available, log this fact or use a clearly documented estimation method.
- **Processing Time**: Record the processing time for the API call. This can be the time reported by OpenAI (if available in the response) or measured client-side.
- **Associated Data**: Link the usage data to relevant entities, such as the user making the request and any specific content being processed (e.g., an `Article` ID).

The `OpenAIUsageStats` model has been created for this purpose and should be used to store these details. Consistent logging will help in analyzing costs, identifying performance bottlenecks, and understanding API consumption patterns.
