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
If your `cwd` is `/app` or `/workspace`, you are already in docker. If not, you're home the host.

If the environmental variable `IN_DOCKER` is set to `True`, you are in docker.

## Anchor comments

Add specially formatted comments throughout the codebase, where appropriate, for yourself as inline knowledge that can be easily `grep`ped for.

### Guidelines:

- Use `AIDEV-NOTE:`, `AIDEV-TODO:`, or `AIDEV-QUESTION:` (all-caps prefix) for comments aimed at AI and developers.
- Keep them concise (≤ 120 chars).
- **Important:** Before scanning files, always first try to **locate existing anchors** `AIDEV-*` in relevant subdirectories.
- **Update relevant anchors** when modifying associated code.
- **Do not remove `AIDEV-NOTE`s** without explicit human instruction.
- Make sure to add relevant anchor comments, whenever a file or piece of code is:
  * too long, or
  * too complex, or
  * very important, or
  * confusing, or
  * could have a bug unrelated to the task you are currently working on.

Example:
```python
# AIDEV-NOTE: perf-hot-path; avoid extra allocations (see ADR-24)
async def render_feed(...):
    ...
```

## Commit discipline

*   **Granular commits**: One logical change per commit.
*   **Tag AI-generated commits**: e.g., `feat: optimise feed query [AI]`.
*   **Clear commit messages**: Explain the *why*; link to issues/ADRs if architectural.
*   **Review AI-generated code**: Never merge code you don't understand.

## Directory-Specific AGENTS.md Files

*   **Always check for `AGENTS.md` files in specific directories** before working on code within them. These files contain targeted context.
*   If a directory's `AGENTS.md` is outdated or incorrect, **update it**.
*   If you make significant changes to a directory's structure, patterns, or critical implementation details, **document these in its `AGENTS.md`**.
*   If a directory lacks a `AGENTS.md` but contains complex logic or patterns worth documenting for AI/humans, **suggest creating one**.

## Meta: Guidelines for updating AGENTS.md files

### Elements that would be helpful to add:

1. **Decision flowchart**: A simple decision tree for "when to use X vs Y" for key architectural choices would guide my recommendations.
2. **Reference links**: Links to key files or implementation examples that demonstrate best practices.
3. **Domain-specific terminology**: A small glossary of project-specific terms would help me understand domain language correctly.
4. **Versioning conventions**: How the project handles versioning, both for APIs and internal components.

### Format preferences:

1. **Consistent syntax highlighting**: Ensure all code blocks have proper language tags (`python`, `bash`, etc.).
2. **Hierarchical organization**: Consider using hierarchical numbering for subsections to make referencing easier.
3. **Tabular format for key facts**: The tables are very helpful - more structured data in tabular format would be valuable.
4. **Keywords or tags**: Adding semantic markers (like `#performance` or `#security`) to certain sections would help me quickly locate relevant guidance.

## Files to NOT modify

These files control which files should be ignored by AI tools and indexing systems:

*   @.agentignore : Specifies files that should be ignored by the Cursor IDE, including:
    *   Build and distribution directories
    *   Environment and configuration files
    *   Large data files (parquet, arrow, pickle, etc.)
    *   Generated documentation
    *   Package-manager files (lock files)
    *   Logs and cache directories
    *   IDE and editor files
    *   Compiled binaries and media files

*   @.agentindexignore : Controls which files are excluded from Cursor's indexing to improve performance, including:
    *   All files in `.agentignore`
    *   Files that may contain sensitive information
    *   Large JSON data files
    *   Generated TypeSpec outputs
    *   Memory-store migration files
    *   Docker templates and configuration files

**Never modify these ignore files** without explicit permission, as they're carefully configured to optimize IDE performance while ensuring all relevant code is properly indexed.

**When adding new files or directories**, check these ignore patterns to ensure your files will be properly included in the IDE's indexing and AI assistance features.

## AI Assistant Workflow: Step-by-Step Methodology

When responding to user instructions, the AI assistant (Claude, Cursor, GPT, etc.) should follow this process to ensure clarity, correctness, and maintainability:

1. **Consult Relevant Guidance**: When the user gives an instruction, consult the relevant instructions from `AGENTS.md` files (both root and directory-specific) for the request.
2. **Clarify Ambiguities**: Based on what you could gather, see if there's any need for clarifications. If so, ask the user targeted questions before proceeding.
3. **Break Down & Plan**: Break down the task at hand and chalk out a rough plan for carrying it out, referencing project conventions and best practices.
4. **Trivial Tasks**: If the plan/request is trivial, go ahead and get started immediately.
5. **Non-Trivial Tasks**: Otherwise, present the plan to the user for review and iterate based on their feedback.
6. **Track Progress**: Use a to-do list (internally, or optionally in a `TODOS.md` file) to keep track of your progress on multi-step or complex tasks.
7. **If Stuck, Re-plan**: If you get stuck or blocked, return to step 3 to re-evaluate and adjust your plan.
8. **Update Documentation**: Once the user's request is fulfilled, update relevant anchor comments (`AIDEV-NOTE`, etc.) and `AGENTS.md` files in the files and directories you touched.
9. **User Review**: After completing the task, ask the user to review what you've done, and repeat the process as needed.
10. **Session Boundaries**: If the user's request isn't directly related to the current context and can be safely started in a fresh session, suggest starting from scratch to avoid context confusion.

## The llm tool

You can use the bash tool 'llm' to ask questions of the codebase or the documentation, this is AMAZING for working with large
codebases, lists of files, or large documents.

Example:

```
 cat itglue.html|llm "What are the properties for the contacts entity?"
Based on the provided API documentation, here are the properties for the **Contacts** entity:

**Attributes (from `GET /contacts` example and `POST/PATCH /contacts` params):**

*   **`id`**: (String, Read-only) The unique identifier for the contact.
*   **`type`**: (String, Read-only) Always "contacts".
*   **`organization-id`**: (Integer) The ID of the organization this contact belongs to. (Required on create).
*   **`organization-name`**: (String, Read-only) The name of the organization this contact belongs to.
*   **`name`**: (String, Read-only) The full name of the contact (likely derived from `first-name` and `last-name`).
*   **`first-name`**: (String) The first name of the contact.
*   **`last-name`**: (String) The last name of the contact.
*   **`title`**: (String) The job title of the contact.
*   **`contact-type-id`**: (Integer, Optional) The ID of the contact type (e.g., Approver, Champion).
*   **`contact-type-name`**: (String, Read-only) The name of the contact type.
*   **`location-id`**: (Integer, Optional) The ID of the location associated with this contact.
*   **`location-name`**: (String, Read-only) The name of the location associated with this contact.
*   **`important`**: (Boolean, Optional) Whether the contact is marked as important.
*   **`notes`**: (String, Optional) Any notes related to the contact.
*   **`restricted`**: (Boolean, Optional) Whether the contact is restricted.
*   **`created-at`**: (String/Timestamp, Read-only) The date and time the contact was created.
*   **`updated-at`**: (String/Timestamp, Read-only) The date and time the contact was last updated.
*   **`contact-emails`**: (Array of Objects, Optional) A list of email addresses for the contact. Each object has:
    *   `value`: (String, Required) The email address.
    *   `primary`: (Boolean, Optional, defaults to false) Whether this is the primary email.
    *   `label-name`: (String, Required) The label for the email (e.g., Work, Home).
*   **`contact-phones`**: (Array of Objects, Optional) A list of phone numbers for the contact. Each object has:
    *   `value`: (String, Required) The phone number (stripped of separators).
    *   `extension`: (String, Optional) The phone extension (stripped of separators).
    *   `primary`: (Boolean, Optional, defaults to false) Whether this is the primary phone number.
    *   `label-name`: (String, Required) The label for the phone number (e.g., Work, Cell).
    *   `label-type`: (String, Optional, defaults to `phone`) Can be `phone` or `fax`.
    *   `formatted-value`: (String, Read-only) The phone number formatted for display.

**Relationships (from `GET /contacts/:id` `include` parameter):**

These are other resources that can be related to a contact and can be included in the response if specified:

*   `adapters_resources`
*   `location`
*   `passwords`
*   `attachments`
*   `tickets`
*   `distinct_remote_contacts`
*   `resource_fields`
*   `user_resource_accesses`
*   `group_resource_accesses`
*   `recent_versions`
*   `related_items`
*   `authorized_users`

When creating or updating a contact, you primarily work with the `attributes` (like `first-name`, `notes`, `contact-emails`, `contact-phones`) and the `organization-id`. The other `-name` fields are usually derived by the system.
```

example -- query code base --
```
find ./ -type f -name "*.py"  -exec cat {} \;|llm "What function syncs contacts with it glue?"
The primary function responsible for syncing contacts with IT Glue is:

1.  **`sync_contacts(self, organization_id=None, since=None)`**
    *   **File:** `tandem/itglue/tasks/tasks_itglue_sync_contacts.py`
    *   **Purpose:** This Celery task is designed for bulk synchronization. It can sync contacts for a specific organization (`organization_id`) or for all organizations if `organization_id` is not provided. It can also sync contacts updated since a specific time (`since`).
    *   It calls `_sync_organization_contacts` for each organization.

There is also a function to sync a single contact:

2.  **`sync_contact(self, contact_id)`**
    *   **File:** `tandem/itglue/tasks/tasks_itglue_sync_contacts.py`
    *   **Purpose:** This Celery task syncs a *specific* contact from IT Glue given its `contact_id`.

Both of these tasks rely on a helper function to perform the actual database update/create operation:

3.  **`_upsert_contact(contact_data, organization)`**
    *   **File:** `tandem/itglue/tasks/tasks_itglue_sync_contacts.py`
    *   **Purpose:** This function takes the contact data fetched from the IT Glue API (`contact_data`) and the corresponding local `Organizations` model instance. It then uses `Contacts.objects.update_or_create()` to save the contact to the local database, setting its `sync_status` to `"synced"`.
    *   It uses utilities like `snake_dict` and `safe_int_cast` from `tandem.itglue.utils.transformers` to process the incoming data.

In summary:
*   `sync_contacts` is for bulk syncing.
*   `sync_contact` is for syncing an individual contact.
*   `_upsert_contact` is the core local database interaction logic used by both.
```

Work as long as you can to knock out items on the list, most critical first.

Always follow TDD principles.
