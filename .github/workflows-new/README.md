# Improved GitHub Actions Workflows

This directory contains improved versions of GitHub Actions workflows for the RSS-TTS project.

## Key Improvements

1. **Consistent Naming**: All workflows have numeric prefixes to ensure they run in a logical order
2. **Reduced Redundancy**: Separated workflows for formatting/linting, type checking, testing, and PR reviewing
3. **Auto-formatting**: The lint workflow now commits formatting fixes back to PR branches
4. **Improved PR Review**: Only runs on non-draft PRs and after other checks

## Workflow Order

1. **00-lint.yml**: Runs formatters and linters, auto-fixes and commits formatting issues
2. **10-type-check.yml**: Runs mypy for type checking
3. **20-test.yml**: Runs all tests with proper database setup
4. **90-pr-review.yml**: Runs automated PR review with Qodo AI

## Implementation Steps

1. Create a directory `.github/workflows-new/`
2. Copy these files into that directory 
3. After testing, rename the directory to `.github/workflows/` to replace the existing workflows

## Note

These workflows eliminate the need for the existing `ci.yml` workflow, as its functionality is now split into separate, specialized workflows.