Use as many subtasks as you can.

Work as independently as possible, this project is 100% AI driven.

Remember to use TDD.

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
