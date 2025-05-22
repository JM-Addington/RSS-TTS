# GitHub Actions Workflows

This directory contains GitHub Actions workflows for the RSS-TTS project.

## Workflow Order

1. **00-lint.yml**: Runs formatters and linters, auto-fixes and commits formatting issues
2. **10-type-check.yml**: Runs mypy for type checking
3. **20-test.yml**: Runs all tests with proper database setup
4. **90-pr-review.yml**: Runs automated PR review with Qodo AI

## Key Features

1. **Consistent Naming**: All workflows have numeric prefixes to ensure they run in a logical order
2. **Reduced Redundancy**: Separated workflows for formatting/linting, type checking, testing, and PR reviewing
3. **Auto-formatting**: The lint workflow now commits formatting fixes back to PR branches
4. **Improved PR Review**: Only runs on non-draft PRs and after other checks
