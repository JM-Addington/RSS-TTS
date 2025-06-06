## Test driven development

You should write tests for your code before you write the code itself. This is called test driven development (TDD). TDD is a software development process that relies on the repetition of a very short development cycle: write a failing automated test case that defines a desired improvement or new function, produce the minimum amount of code to pass that test, and refactor the code to pass all tests. The cycle is repeated for each new feature or improvement.

## Branches

`main` is production code. It should always be in a working state. You should never commit code directly to `main`. Instead, you should create a new branch for each new feature or improvement you are working on. The branch name should be descriptive and follow the format `feature/description` or `bugfix/description`. For example, if you are working on a new feature that adds a new agent, you might name your branch `feature/add-new-agent`.


Dev branches are `dev/main` which is the main development branch. It should usually be in a working state. Typically, you will squash commit bugfix and feature branches into `dev/main` before merging them into `main`. You should rarely commit code directly to `dev/main`, but you can as needed.

PR branches are `pr/description` which are branches that are created for pull requests. They should be used to review code before it is merged into `dev/main` or `main`.

By the time you are ready to merge your code into `main`, you should have a working version of your code that has been tested and reviewed, and the final PR is just a final safety check.

## Commit messages

You should write clear and descriptive commit messages. A good commit message should explain what the commit does and why it is necessary. It should be written in the imperative mood, as if you are giving a command. For example, instead of writing "fixed a bug", you should write "fix bug".

Use semantic commit messages. Semantic commit messages are a convention for writing commit messages that convey the meaning of the changes made in the commit. They are structured in a way that makes it easy to understand what the commit does and why it is necessary.

Here are some examples of semantic commit messages for this project:

*   `feat: Implement user authentication` - This commit adds user authentication functionality to the project.
*   `fix: Resolve issue with TTS API integration` - This commit fixes an issue with the TTS API integration that was causing errors.
*   `refactor: Improve code structure for article processing` - This commit refactors the code structure for article processing to improve readability and maintainability.

## Coding Standards

Please follow our project's detailed coding standards documented in [CODING_STANDARDS.md](CODING_STANDARDS.md). This includes:

- Python style guide (PEP 8)
- Django best practices
- Documentation requirements
- Testing approach
- Code quality tools configuration

We use pre-commit hooks to enforce these standards. Set them up using the instructions in the README.md file.

## Project Information

Here's a summary of key information from other files in the repository:

### Technology Stack

*   Django 5 + DRF
*   Celery 6 + Redis
*   SQLite
*   OpenAI TTS (`tts-1-hd` / `gpt-4o-mini-tts`)
*   OpenAI o3-mini & GPT-4.1 for tone/extraction
*   Docker Compose dev/prod
*   Bootstrap 5 for UI

### Key Constraints

*   URL/text length hard-cap = 30 000 words.
*   Local storage of MP3s (no external bucket in Phase 0-2).
*   One TTS chunk ≤ 4 096 chars.
*   Private feeds via unguessable UUID tokens (no auth headers).

## Documentation

You should always read these other files in the repo:
- README.md (if it exists)
- CLAUDE.md (if it exists)
- PROJECT_PLAN.md (if it exists)
- CODING_STANDARDS.md (if it exists)
