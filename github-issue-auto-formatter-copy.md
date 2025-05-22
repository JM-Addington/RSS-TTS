# Add Automatic Formatting and Commit to PR Builds

## Description
Currently, our CI pipeline checks code formatting using autopep8, but fails if code doesn't meet standards without fixing the issues. This creates friction in the development process, as developers must manually fix formatting issues before their PRs can be merged.

## Proposed Solution
Enhance the lint workflow to:
1. Run the autopep8 formatter
2. Automatically commit formatting changes back to the PR branch
3. Allow the build to continue instead of failing on formatting issues

This approach will:
- Reduce developer friction
- Ensure consistent code style
- Maintain code quality while improving workflow efficiency
- Allow developers to focus on writing functionality rather than formatting details

## Implementation Details

### 1. Update the lint.yml workflow:

```yaml
name: 00 - Lint and Format

on:
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v3
        with:
          ref: ${{ github.head_ref }}
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install autopep8

      - name: Run formatter
        run: |
          autopep8 --in-place --recursive .

      - name: Check for changes
        id: git-check
        run: |
          git status --porcelain
          echo "::set-output name=modified::$(if git status --porcelain | grep .; then echo true; else echo false; fi)"

      - name: Commit formatting changes
        if: steps.git-check.outputs.modified == 'true'
        run: |
          git config --local user.email "github-actions[bot]@users.noreply.github.com"
          git config --local user.name "github-actions[bot]"
          git add -A
          git commit -m "style: Auto-format code with autopep8 [skip ci]"
          git push
```

### 2. Key Changes:

- Add write permissions for the job to allow commits
- Use the PR's head_ref to check out the branch
- Run autopep8 with the --in-place flag to modify files
- Check if any files were changed
- Commit and push changes back to the PR branch with an appropriate commit message
- Add [skip ci] to prevent triggering another workflow run

### 3. Special Considerations:

- We need to set the checkout action with the PR's head_ref
- Using [skip ci] in the commit message prevents an infinite loop of CI jobs
- The workflow only runs on pull_request events, not on pushes to main

## Testing Plan

1. Create a test PR with code that doesn't meet autopep8 standards
2. Confirm the workflow:
   - Runs successfully
   - Formats the code
   - Commits changes back to the PR branch
   - Adds an appropriate commit message
3. Verify the changes appear in the PR as a new commit
4. Ensure subsequent workflow runs don't create additional commits if no formatting is needed
5. Test edge cases:
   - PRs with no formatting issues
   - PRs with multiple files needing formatting
   - PRs from forks (may need additional token handling)

## Dependencies
- Access to GitHub token with write permissions
- Proper GitHub Actions configuration
