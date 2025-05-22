#!/bin/sh
set -e

# Install pre-commit if not available
if ! command -v pre-commit >/dev/null 2>&1; then
  echo "Installing pre-commit..."
  pip install pre-commit
fi

# Install git hooks
pre-commit install

# Update to the latest hooks defined in config
pre-commit autoupdate

echo "Pre-commit hooks installed and updated."
