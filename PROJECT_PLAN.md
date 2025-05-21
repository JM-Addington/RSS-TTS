# 🗺️ Project Overview

| Area                 | Summary                                                                                                                                                                                                                                                  |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Vision**           | Let any user turn web articles, blog posts, or pasted text into high-quality audio they can consume hands-free—driving, exercising, doing chores, etc.—and access that audio through a private podcast-style RSS feed.                                   |
| **Core Value Props** | 1. **Friction-free audio** of any article in seconds.<br>2. **Smart narration** (tone & speed) that suits the content but is override-able.<br>3. **Offline listening** through any podcast player (RSS).<br>4. **Usage transparency** for cost control. |
| **Target Personas**  | • Busy CEO • College student • Teen reader • Parent multi-tasker • CEO creating internal podcast.                                                                                                                                                        |
| **Technology Stack** | Django 5 + DRF • Celery 6 + Redis • SQLite • OpenAI TTS (`tts-1` / `gpt-4o-mini-tts`) • OpenAI o3-mini & GPT-4.1 for tone/extraction • Docker Compose dev/prod • Bootstrap 5 for UI.                                                                 |
| **Key Constraints**  | • URL/text length hard-cap = 30 000 words.<br>• Local storage of MP3s (no external bucket in Phase 0-2).<br>• One TTS chunk ≤ 4 096 chars.<br>• Private feeds via unguessable UUID tokens (no auth headers).                                             |
| **Success Criteria** | MVP user can: (1) register/login, (2) submit URL, (3) receive MP3 in ≤ 2 min (typical 2 000-word article), (4) subscribe to feed in Apple/Google Podcasts and hear episode, (5) see monthly token usage on dashboard (Phase 2).                          |

---

## 📑 User-Story Backlog (Phases 1 & 2)

> *All stories use the “As a \[persona] I want … so that …” pattern and include acceptance criteria (AC).  The Phase column references the roadmap phases you already have.*

| #     | User Story                                                                                                                                                                                                   | Phase | Acceptance Criteria (A C)                                                                                                                                                                                                                                             |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1** | **As a CEO driving to work, I want to paste today’s WSJ URL and have it show up in my private feed within about 2 minutes**, so that I can listen during the commute.                                        | **1** | AC-1: After submitting URL, dashboard shows status = Processing.<br>AC-2: Within 2 min (test with 2 000 words), Article status = Completed and MP3 exists.<br>AC-3: Episode appears in user’s RSS feed and streams in a podcast app.                                  |
| **2** | **As a student, I want to paste a professor’s 10-page lecture PDF text and choose 1.25× speed**, so that I can review faster while walking to class.                                                         | **2** | AC-1: Submission form accepts pasted plain text block (\~5 000 words).<br>AC-2: User sets speed to 1.25× in profile or per-article override.<br>AC-3: Resulting audio is \~20 % shorter in duration than default voice and intelligible.                              |
| **3** | **As a 14-year-old fan of long stories, I want each article automatically voiced in an engaging, “discovery” tone**, so that it’s fun to follow complex plots.                                               | **2** | AC-1: Tone classifier labels article as *“fiction/discovery”* and picks matching voice (per mapping table).<br>AC-2: Audio voice differs from the default “news” voice when tone ≠ news.<br>AC-3: User can still override voice in UI; override wins over classifier. |
| **4** | **As a busy mom folding laundry, I want to queue multiple blog URLs to my “Lifestyle” feed in one session**, so that I can catch up later without repeating the process.                                     | **1** | AC-1: Dashboard lets user add a URL, form stays ready for next entry (no page reload if possible).<br>AC-2: Articles appear in chronological order in the “Lifestyle” feed.<br>AC-3: Feed token URL stays constant; new episodes append automatically.                |
| **5** | **As a CEO producing an internal industry podcast, I want to create separate feeds (e.g., “Cyber-News”, “Fin-Reg”) and share the tokens with my team**, so that employees subscribe only to what’s relevant. | **2** | AC-1: Feed-management page lets user create/edit/delete feeds, each with unique token.<br>AC-2: Submission form has dropdown to select feed.<br>AC-3: Each feed’s RSS only lists its own articles; deleting a feed removes its RSS endpoint.                          |
| **6** | **As any user, I want to see how many characters/tokens I’ve used this month**, so that I understand potential costs.                                                                                        | **2** | AC-1: Dashboard shows “This month: X chars (Y TTS tokens, Z GPT tokens)”.<br>AC-2: Values update nightly via celery aggregation.<br>AC-3: Admin view lists all users with same stats.                                                                                 |
| **7** | **As an admin/dev, I want failed extractions or TTS errors logged with stack trace and article ID**, so that we can debug quickly.                                                                           | **1** | AC-1: Failures move Article to status = Failed and store error message.<br>AC-2: Error appears in Sentry/logs with article ID and URL.<br>AC-3: Dashboard shows “Failed – retry” action link (manual).                                                                |
| **8** | **As any user, I want to paste extremely long text (≤ 30 000 words) and still get one stitched MP3**, so that I can listen to full whitepapers.                                                              | **1** | AC-1: System chunks text at ≤ 4 096 chars boundaries.<br>AC-2: All chunks stitched into one MP3; no missing content.<br>AC-3: If over 30 000 words, submission rejected with friendly error.                                                                          |
| **9** | **As a QA tester, I want the RSS feed to validate against W3C Feed validator and Apple Podcasts spec**, so that subscribers have no playback issues.                                                         | **1** | AC-1: Feed passes W3C validator (no errors).<br>AC-2: Contains enclosure tags with correct length/mime.<br>AC-3: Tested in Apple & Google Podcast apps successfully.                                                                                                  |

---

### Linking stories to roadmap phases

* **Phase 0** stories are purely team-setup tasks (they have no user-facing stories).
* **Phase 1** covers Stories 1, 4, 7, 8, 9 (core loop, single default feed).
* **Phase 2** adds Stories 2, 3, 5, 6 (tone/speed, multiple feeds, analytics).

Break each story into finer tasks (e.g., Celery task, feed endpoint, UI form) and group them by Phase milestones.

With this overview and backlog, the roadmap is now fully self-contained for a two-developer team.



# Roadmap for Django-Based TTS RSS Project

This roadmap outlines a **phase-wise development plan** for a Django application that converts webpages or text into speech (MP3) and serves them via private RSS feeds. We break down **Phase 0 (Setup)**, **Phase 1 (MVP Core Loop)**, and **Phase 2 (Enhanced Features)** with clear epics, tasks (as GitHub issues), time estimates, and guidance for a **2-developer team**. Each task is described in a GitHub-issue style, including what to do and the expected outcome. We also indicate which tasks can be done in parallel to maximize team efficiency.

## Phase 0: Initial Setup and Infrastructure

*Milestone Goal:* Establish the development environment, repository, and base project structure so the team can start coding with Dockerized services and essential tools in place. *(Estimated time: \~3 days total for two developers working in parallel.)*

* **Epic 0.1: Repository & Project Management Setup** – *Set up version control and project tracking.*

  * **Initialize GitHub Repository:** Create a monorepo for the project with a proper README and license. Set up a GitHub Project board to track issues by phase/milestone (Phase 0, Phase 1, Phase 2). Define milestones for each phase and epics (feature groups) within the project for clarity. *(Est.: 0.5 day)*
  * **Define Coding Standards & CI:** Add a basic Continuous Integration workflow (e.g., GitHub Actions) for running tests and linters on pushes. Document code style guidelines (PEP8, docstrings) in the README so both developers follow a consistent style. *(Est.: 0.5 day)*

* **Epic 0.2: Dockerized Development Environment** – *Containerize the app and services for consistent dev and prod environments.*

  * **Write Dockerfile for Django App:** Create a Dockerfile that sets up Python (choose a version, e.g. 3.11), installs Django, Celery, and other dependencies. Ensure the container can run the Django server. *(Est.: 0.5 day)*
  * **Write Dockerfile for Celery Worker:** (Optional if using separate image; could reuse Django image.) Configure a Docker image for Celery that loads the Django project and can execute tasks. *(Est.: 0.5 day)*
  * **Docker Compose Configuration:** Write a `docker-compose.yml` to define services: Django web app, Celery worker, message broker (Redis), and a database (SQLite). Include a Redis service for Celery’s broker (Redis is a common choice for Celery message backend) and ensure that running `docker-compose up` will launch all containers for local development. *(Est.: 1 day)*
  * **Environment Variables & Config:** Set up a `.env` file or Docker Compose secrets to manage sensitive config (e.g., OpenAI API key, database credentials). Modify Django settings to load these values (don’t commit actual secrets). *(Est.: 0.5 day)*

* **Epic 0.3: Base Django Project Initialization** – *Scaffold the Django project with core apps and libraries.*

  * **Start Django Project:** Use `django-admin startproject` to create the project (e.g., `tts_rss_project`). Create a core Django app (e.g., `text_to_audio`) for our functionality. Add this app to `INSTALLED_APPS`. *(Est.: 0.5 day)*
  * **User Authentication Setup:** Enable Django’s built-in auth system. Run `startapp accounts` if a custom app is needed or use default. Configure the auth model (use default `User` for now) and create initial migrations. *(Est.: 0.5 day)*
  * **Bootstrap Frontend Integration:** Download and include Bootstrap CSS/JS in the project (e.g., via CDN in base template or as static files). Create a base HTML template with Bootstrap navbar and empty content block for extending in other pages. This ensures a consistent UI foundation. *(Est.: 0.5 day)*
  * **Initial GitHub Issues & Milestone:** As a project management step, create GitHub issues for all Phase 0 tasks (including this setup) and mark them under the Phase 0 milestone. Ensure each issue has a clear description (as above) and time estimate, ready for assignment. *(Est.: 0.5 day)*

**Phase 0 Parallelization:** Developer 1 can focus on **Docker and infrastructure** (Dockerfiles, docker-compose, CI) while Developer 2 **scaffolds the Django project** (startproject, setting up apps and Bootstrap). These streams can happen in parallel. After both are done, do an integration test: Developer 1 and 2 run the app via Docker to verify that the web container can serve a Django “Hello World” page and Celery/Redis are up. This completes the setup milestone.

## Phase 1: MVP – Core Functionality and Private RSS

*Milestone Goal:* Deliver a Minimum Viable Product where users can log in, submit a URL or text, have it converted to an MP3 via OpenAI’s TTS, and access their audio via a private RSS feed. This includes the core pipeline (URL -> text -> speech), background processing with Celery, and basic UI. *(Estimated time: \~2–3 weeks for 2 developers.)*

### Epic 1.1: User Accounts & Feed Models

*Objective:* Implement user authentication and create models for feeds and articles, laying the groundwork for per-user content management.

* **Implement User Registration & Login:** Using Django’s auth, create views/templates for user signup, login, and logout. Use `django.contrib.auth` views or custom ones for better control. Ensure pages are styled with Bootstrap and that only logged-in users can access the main app features (use login required decorators). *(Est.: 1 day)*
* **Design Data Models (Feed & Article):** Define a `Feed` model (representing a user’s collection of articles, e.g., fields: user (FK), name, token for private access) and an `Article` model (fields: feed (FK) or user (FK), title, source\_url, text\_content, audio\_file\_path, status, created\_at, etc.). Initially, assume one default feed per user (the user is associated with a private feed). Generate and store a unique **feed token** (UUID or similar) for each feed to use in the feed URL for privacy. *(Est.: 1 day)*
* **Migrations & Admin Setup:** Create and apply migrations for the new models. Register models in Django admin for debugging. *(Est.: 0.5 day)*
* **GitHub Issue Tracking:** Create issues for each model and auth task, detailing acceptance (e.g., “User can register and login with username/password, password hashed, etc.”). Link them under a Phase 1 “Accounts & Models” epic in the project board. *(Est.: 0.25 day)*

### Epic 1.2: Article Submission & Text Extraction

*Objective:* Allow users to submit URLs or text, fetch the content, and extract clean text for conversion.

* **Article Submission Form:** Create a Django view and template where a logged-in user can input either a URL or paste a block of text. On submission, create an `Article` record with status “Processing” and associate it with the user’s feed. If URL is provided, store it; if raw text is provided, store that directly for processing. *(Est.: 1 day)*
* **Fetch Webpage Content (if URL):** In the Celery task (see next epic), use `requests` to retrieve the page HTML and `BeautifulSoup` (bs4) to parse it. Extract the main content text from the HTML (e.g., find the article’s `<div>` or `<p>` container). This may require customizing for different sites; for MVP, handle simple cases or use a library like Readability if needed. *For now, assume the user provides well-structured pages or use a fixed strategy (such as grabbing `<body>` text).* *(Est.: 1 day)*
  **↪ Implementation note:** You can target a specific container or just get all paragraph texts on the page. Confirm the approach on a test URL (e.g., a medium article).
* **Basic Content Cleaning:** Strip out HTML tags, scripts, nav elements, etc., leaving only the article text. Ensure the text is reasonably clean for TTS input (remove extra whitespace or newlines). *(Est.: 0.5 day)*
* **Handling Direct Text Input:** If the user submitted a text block instead of URL, skip fetching and use that text as content. Still create an Article record and proceed to TTS conversion. *(Est.: 0.25 day)*
* **Error Handling for Extraction:** Implement basic error catching: if the URL fetch fails or no content is extracted (e.g., unsupported site), mark the Article as “Failed” and maybe store an error message. The user should see that status in the UI. *(Est.: 0.5 day)*

### Epic 1.3: Text-to-Speech Conversion Pipeline (Celery Background Task)

*Objective:* Convert extracted text to speech using OpenAI’s TTS API. Handle chunking large text and stitching audio, all in a background job to keep the web responsive.

* **Configure Celery in Django:** Set up Celery in the Django project (as per standard practice: create `celery.py`, load it in `__init__.py`). Configure the broker URL (use Redis from Phase 0) and result backend if needed. Ensure the Django settings have `CELERY_BROKER_URL` pointing to Redis (from docker-compose). *(Est.: 0.5 day)*
* **Define Celery Task for Article Processing:** Write a Celery task (e.g., `tasks.process_article(article_id)`) that performs the following sub-tasks in sequence: *(Est.: 2 days total)*

  1. **Fetch & Extract Text:** If the Article has a URL, fetch and parse it (from Epic 1.2). If the Article already has raw text, use it. (Reuse the extraction code within the task or call a helper function.)
  2. **Chunk Text for TTS:** Because OpenAI’s TTS API has a limit of \~4096 characters per request, split the text into manageable chunks. Ideally split at sentence or paragraph boundaries near the limit so as not to cut off sentences. Each chunk will be converted separately.
  3. **Call OpenAI TTS API for Each Chunk:** Use OpenAI’s Python SDK to call the text-to-speech endpoint for each chunk. For example: `openai.audio.speech.create(model="tts-1", voice=VOICE, input=chunk)` to get an audio stream. Use an appropriate voice (e.g., "nova" or "alloy" as default) and capture the audio. Stream each response to a temporary MP3 file. Include error handling (e.g., API errors or timeouts).
  4. **Stitch Chunks into One MP3:** If multiple chunks were processed, concatenate the resulting audio files in order. Use a library like `pydub` to merge MP3s seamlessly. The result is one combined MP3 file for the full article. Name the file deterministically (e.g., `article_<id>.mp3`) and save it to a media folder.
  5. **Update Article Record:** Mark the Article as “Completed”, save the file path/URL, and store additional metadata (e.g., the article’s title if extracted from HTML `<title>` or given by user, and the duration or size of audio if needed for RSS).
* **Celery Worker & Monitoring:** Run the Celery worker in the Docker environment and test the pipeline with a sample URL. Verify that the task runs to completion and the MP3 is saved. Use Flower (optional) to monitor tasks or simply check logs. *(Est.: 0.5 day)*
* **Token Usage Logging (Basic):** In this MVP phase, log how many characters or tokens were sent to the TTS API for each article (and GPT usage if any). This can be as simple as capturing length of text or parsing the API response usage fields. Store this in the Article or a simple log model (to be expanded in Phase 2 for per-user aggregate). *(Est.: 0.5 day)*
* **GitHub Issues:** Break the above into smaller issues: e.g., “Celery setup”, “TTS chunking”, “TTS API integration”, “Audio stitching”, “Article model update after task”. Each issue should reference the acceptance criteria (e.g., MP3 saved, article marked complete) and any known constraints (like the 4096 char chunk limit). *(Est.: 0.25 day)*

### Epic 1.4: RSS Feed Generation

*Objective:* Provide users with a private RSS feed URL that lists their converted articles as podcast episodes (MP3 enclosures).

* **Implement RSS Feed Endpoint:** Leverage Django’s **syndication feed framework** to create an RSS feed for articles. Create a Feed class (e.g., `UserFeed`) that subclasses `django.contrib.syndication.views.Feed`. It should filter the latest completed articles for the requesting user (or for a given feed token) and format each as an RSS item. *(Est.: 1 day)*

  * **Feed URL & Access Control:** Define a unique feed URL scheme, e.g. `/feeds/<feed_token>/`. The feed view will use the token to identify the user or feed without requiring login (a secret token in the URL ensures privacy). For example, `LatestEntriesFeed` can be connected to `/feeds/<token>/` via URLconf. *(Est.: 0.5 day)*
* **Feed Item Content:** For each Article in the feed, supply at least: title (article title or a truncated text), link to original article (optional), and description (perhaps an excerpt or a note like "Audio version of the article"). Use the **enclosure** fields to attach the MP3 file URL so podcast apps recognize it. Ensure `item_enclosure_url` points to a Django view or static URL serving the MP3, and provide `item_enclosure_length` (file size) and `item_enclosure_mime_type` ("audio/mpeg"). *(Est.: 1 day)*
* **Serve MP3 Files Securely:** Decide how to serve the MP3s. For simplicity, during MVP store them in a directory accessible by Django’s static/media serve (in development) and have the enclosure URL point directly to that file path. (In production, these might be behind authenticated views or a CDN, but for MVP a direct link with a long token in the filename or URL is acceptable.) *(Est.: 0.5 day)*
* **Verify Feed with Podcast App:** Manually validate the RSS feed by subscribing in a podcast player (or using an RSS validator) to ensure the format is correct and the MP3 enclosures are recognized. Adjust as needed (e.g., add pubDate or GUID if required). *(Est.: 0.5 day)*
* **GitHub Issues:** Create an epic “RSS Feed” and issues like “Create Feed class for user’s articles” (with steps to produce title/link/description) and “Add enclosures to RSS items” with reference to Django docs. *(Est.: 0.25 day)*

### Epic 1.5: Frontend UI & UX

*Objective:* Build basic pages for users to interact with the system – submit content, view status, and get their feed link.

* **Dashboard Page:** After login, direct users to a dashboard showing a form to add a new article and a list of their articles/feed items. Implement this view to fetch the user’s Article records from the database and display their title, status (Processing/Completed/Failed), and perhaps a link to play or download the MP3. *(Est.: 1 day)*
* **Submit Form UI:** Integrate the submission form (from Epic 1.2) into the dashboard page or a separate page. Use proper Bootstrap form styling. After submission, show a message like "Your article is being processed" and redirect back to the dashboard where the new article appears with status. *(Est.: 0.5 day)*
* **Feed Info Display:** On the dashboard (or a profile page), display the user’s private RSS feed URL along with a copy button and a warning to keep it secret. Provide a short explanation for how to use the URL in podcast apps. *(Est.: 0.5 day)*
* **Status Updates:** Use simple polling or page refresh to update article status, or encourage user to refresh. (Real-time updates with WebSocket can be a future improvement but not in MVP.) Ensure that when an article’s status changes to Completed, the page shows a link to the MP3 (so user can test listen) and it will automatically appear in their RSS feed. *(Est.: 0.5 day)*
* **Basic Styling & Usability:** Apply Bootstrap classes to make the UI clean. Navigation bar with app name, and a logout button. Ensure pages are mobile-friendly (Bootstrap’s responsive grid). *(Est.: 0.5 day)*
* **Testing & QA:** Both developers test the entire loop: create account, submit URL, wait for processing, check RSS feed in an external app. Identify and fix any blockers. Write a few basic unit tests or integration tests (for example, test that feed returns 200 OK and contains expected XML elements, test that submitting a known text returns an MP3 of non-zero size). *(Est.: 1 day)*

**Phase 1 Parallelization:** Developer 1 can concentrate on **backend tasks** (Celery task, integration with OpenAI API, models, feed generation) while Developer 2 works on the **frontend and user-facing features** (auth pages, dashboard, forms, feed display). Key integration points: the submission form triggering the Celery task, and the RSS feed consuming the output. To manage this, ensure early on that Developer 1 defines the interface for creating an Article and launching the Celery task (so Developer 2 can call it from the form handler). In parallel, Developer 2 can build the UI using dummy data until the real data flows in. Midway through Phase 1, have an integration session where both parts come together: hooking the form view to actually call the Celery task, and verifying the end-to-end flow (this might require both devs to pair program briefly). After integration, tasks like testing, bug-fixing, and feed validation can be shared. The team should aim to close all Phase 1 GitHub issues before considering Phase 2.

## Phase 2: Enhanced Features and Refinements

*Milestone Goal:* Build on the MVP to add voice customization (tone detection and speed control), advanced parsing, usage analytics, and multi-feed support. These features improve the quality of the output and provide users more control. *(Estimated time: \~2–3 weeks for 2 developers.)*

### Epic 2.1: Voice Tone Detection & Customization

*Objective:* Use AI to detect the tone of articles and adjust the TTS voice or style accordingly, and allow user overrides for speed and tone.

* **Tone Detection via OpenAI (o3-mini):** Utilize the OpenAI **o3-mini** model to analyze the article text and determine an appropriate tone or style. For example, classify the content as *formal*, *informal*, *excited*, *informative*, etc. (Define a set of tone categories relevant to voice selection). This likely involves prompting the model with the article text or a summary and asking for a tone classification. *Note:* OpenAI’s default tone analysis is very limited (essentially just positive/negative sentiment), so we will craft a custom prompt for o3-mini to get a more useful classification (e.g., *“Is the writing style formal/academic, casual/blog-like, or conversational?”*). *(Est.: 1 day)*
* **Map Tone to Voice/Pitch:** Decide on a mapping from detected tone to TTS voice parameters. For instance, if tone is *formal*, use a specific voice (say “Alloy” voice at normal speed); if *excited* or *casual*, maybe use a more lively voice or slightly faster speed. Document this mapping for consistency. *(Est.: 0.5 day)*
* **Integrate Tone Analysis in Pipeline:** Update the Celery `process_article` task to include a tone analysis step **before** calling TTS. Use o3-mini (via OpenAI API) to get the tone classification result for the article text. This is an extra API call per article, but o3-mini is chosen for cost-efficiency and speed. Parse the result and decide voice settings (voice name, pitch, speaking rate). *(Est.: 1 day)*
* **User Override for Voice/Speed:** Extend the UI to let users set default voice and speed preferences (e.g., on their profile or feed settings). For example, a user might prefer a faster speech rate or a particular voice regardless of tone. Provide a dropdown of available voices and a slider or select for speed (normal, 1.25×, 1.5×, etc.). *(Est.: 1 day)*

  * In the backend, store these preferences (add fields in the User profile or Feed model, e.g., `preferred_voice`, `preferred_speed`). If a user has override settings, skip tone-based voice selection and use their choices.
* **TTS Call with Custom Parameters:** Modify the TTS API call to include the speed and any other tone parameters. OpenAI’s TTS allows adjusting voice speed and pitch via parameters in the API request. For instance, pass `speed=1.2` for 1.2× speed if the user selected faster playback, or a different voice ID as needed. Test with a sample to verify the API applies the speed (some early versions had distortion issues at non-1x speeds). *(Est.: 0.5 day)*
* **Testing Voice Outputs:** Try a few articles with distinct tones to see if the tone detection picks different voices. E.g., a formal news article vs. a casual blog post – confirm the voice or speed differs if expected. Allow some iteration on the tone categories and mapping if results aren’t satisfactory initially. *(Est.: 1 day)*

### Epic 2.2: Smarter Content Parsing

*Objective:* Improve the extraction of article text, handling a wider range of websites and cleaning the content for better audio output.

* **Advanced HTML Parsing:** Integrate an article parsing library (such as **readability** or **Newspaper3k**) to automatically extract main content from HTML. This can complement or replace the simple BeautifulSoup approach for sites where the content is buried among ads or navigation. Test with a few known news/blog sites to ensure it grabs the right content. *(Est.: 1 day)*
* **GPT-4.1 Assisted Extraction:** For particularly hard cases, use GPT-4.1 to assist. For example, if the raw text is extremely long or contains clutter (navigation text, unrelated content), send a prompt to GPT-4.1 with a snippet of the text asking it to **extract the main article text** or to **summarize and remove extraneous content**. This AI-based cleaning can help when the structure isn’t easily parseable. Use GPT sparingly (maybe for very long texts or as a fallback) to control token usage. *(Est.: 1 day)*

  * *Example:* If an HTML page’s main content couldn’t be found by rules, feed the HTML to GPT-4.1 with instructions to return only the article’s body text. This ensures the audio is focused on the article itself.
* **Chunking Improvements:** Refine the text chunking logic used in Phase 1. Instead of splitting purely by character count, split by **sentence or paragraph boundaries** near the 4096-char limit to avoid cutting in the middle of sentences. Implement a function that scans for the last period or whitespace before the limit and splits there. This will make the final audio more natural. *(Est.: 0.5 day)*
* **Text Preprocessing for Audio:** Clean up some textual patterns that might not read well in audio. For example, strip out URLs or replace them with a phrase like “link”, convert common abbreviations (maybe optional), and possibly handle lists or code blocks (maybe by summarizing them). This could be guided by GPT as well (see MLQ guide’s suggestion to manually edit transcripts). For now, implement simple rules like: remove HTML entities, ensure punctuation spacing is correct, etc. *(Est.: 1 day)*
* **Regression Testing:** Re-run the extraction on a few Phase 1 test URLs and some new ones to ensure the improvements don’t break basic cases. For sites that gave trouble in Phase 1, verify if they’re fixed now. *(Est.: 0.5 day)*

### Epic 2.3: Usage Analytics & Monitoring

*Objective:* Track API usage per user for cost monitoring and potentially limit overuse. Provide admin or users insight into their usage.

* **Token/Character Counting:** Expand the logging from Phase 1 to record **token usage** more systematically. For each Article processed, capture the number of characters sent to TTS (and ideally the number of *audio tokens* the API returned, if available). Also capture tokens used by GPT-4.1 and o3-mini calls (OpenAI responses typically include token usage info in API responses). *(Est.: 0.5 day)*
* **Usage Model:** Create a model or extend the User model to accumulate usage stats: e.g., total characters converted, total tokens consumed, total articles processed, etc. Alternatively, create a separate `UsageLog` that records each job’s usage and aggregate per user via queries. *(Est.: 0.5 day)*
* **Admin Dashboard for Usage:** In the Django admin (or a simple staff-only view), display a report of usage per user. Show fields like total tokens used this month, number of articles, etc. This will help in identifying heavy users and estimating costs. *(Est.: 0.5 day)*
* **(Optional) User Usage Page:** If desired, show logged-in users their own usage stats (e.g., “You converted X articles totaling Y characters this month.”). This transparency can help them self-moderate and is useful if in future a pricing model or quota is introduced. *(Est.: 0.5 day)*
* **Alerts or Limits (Optional):** Not strictly required now, but consider adding a configurable alert if a user exceeds a certain token count (just log a warning or send an email). This keeps the system sustainable. *(Est.: 0.5 day)*
* **GitHub Issues:** Split into tasks like “Implement UsageLog model”, “Calculate and store token counts from API responses”, “Admin view for usage”. Reference OpenAI pricing docs for context on tokens (e.g., TTS charges by characters and audio output tokens). *(Est.: 0.25 day)*

### Epic 2.4: Multiple Feeds & Organization

*Objective:* Allow each user to create and manage multiple feeds, grouping articles by topic or any categorization, rather than one flat list.

* **Feed Management UI:** Create a page where users can create new feeds (e.g., “Tech News”, “My Favorite Blogs”). A feed has a name and its own private token/URL. On this page, list existing feeds and allow deletion or editing the name. *(Est.: 1 day)*
* **Associate Articles with Feeds:** Update the article submission flow to let the user choose which feed to add the new article to (e.g., a dropdown of their feeds when adding a URL). The Article model already has a feed foreign key from Phase 1; now the UI will utilize it. By default, if the user has only one feed, it’s auto-selected; if multiple, they must choose. *(Est.: 0.5 day)*
* **RSS Feed per Feed:** Adjust the RSS Feed implementation to handle multiple feeds. Instead of one feed per user, it’s one feed per Feed object. For example, `/feeds/<feed_token>/` will query articles for that specific Feed only. Ensure the Feed class uses the token to find the correct Feed record and its articles. *(Est.: 0.5 day)*
* **Unique Feed Tokens:** When creating new feeds, generate unique tokens (ensure no collision with others). Possibly reuse the UUID approach. The feed URL should include this token as implemented. No authentication is needed to fetch the feed if the token is unguessable. *(Est.: 0.25 day)*
* **Backward Compatibility:** If Phase 1 had a single feed per user, you might migrate that to an explicit Feed object (e.g., create a default feed for each existing user and move their articles under it). Write a data migration or script if needed. *(Est.: 0.5 day)*
* **UI Updates:** Update the dashboard to display articles grouped by feed or allow filtering by feed. Alternatively, have a separate page per feed. At minimum, show the feed name for each article or group the list by feed. Also, show each feed’s RSS URL. *(Est.: 0.5 day)*
* **Test Multi-Feed Workflow:** Create two feeds for a user, add articles to both, and ensure each feed’s RSS shows only its articles. Verify that the correct number of articles appear in each and that managing feeds (add/delete) works without issues (e.g., deleting a feed might also delete or reassign its articles). *(Est.: 1 day)*

### Epic 2.5: Polishing and Documentation

*Objective:* Finalize the phase by fixing bugs, improving performance, and documenting the system for future maintainers or deployment.

* **Performance Tuning:** Evaluate if any part of the pipeline is slow (e.g., large articles might take time). Possibilities: enable Celery concurrency if many tasks, increase Celery worker count, or prefetch some content. Also consider using Celery results or notifications to update the UI in real-time eventually (not in scope now). *(Est.: 0.5 day)*
* **Error Handling and Logging:** Go through the code and ensure all external calls (OpenAI API, requests) have proper try/except and clear logging. For instance, log an error if TTS fails mid-way but also handle partial results (maybe mark article failed and clean up partial files). This will aid debugging in production. *(Est.: 0.5 day)*
* **Security Review:** Ensure the private feed URLs truly stay private (they contain long tokens and are not listed anywhere publicly). Double-check that user A cannot access user B’s data through any view (including feeds, which are token-protected). Also, add `LOGIN_REQUIRED` where appropriate and use Django’s security best practices for deployment (allowed hosts, HTTPS, etc.). *(Est.: 0.5 day)*
* **User Documentation:** Write a Markdown file or wiki page for users (and testers) explaining how to use the app: how to log in, add content, and subscribe to the RSS feed in a podcast app. Also include any limitations (e.g., “beta version, may not parse every site correctly, currently supports English text-to-speech”, etc.). *(Est.: 0.5 day)*
* **Developer Documentation:** Update the README with instructions to run the Dockerized app, how to set environment variables (OpenAI API key, etc.), and how to run tests. Document the architecture briefly (Django app, Celery workers, Redis, how RSS feed is structured). This makes onboarding new developers or handoff easier. *(Est.: 0.5 day)*
* **Milestone Completion:** Review all Phase 2 GitHub issues and ensure they are closed after testing. Perform final integration testing covering all new features together (e.g., try an article with tone detection, custom speed, in a non-default feed, and see that usage is logged). Prepare a Phase 2 milestone report (could be just a GitHub Projects summary or a short write-up) to hand off with the code. *(Est.: 1 day)*

**Phase 2 Parallelization:** There are several independent improvements here. Developer 1 could focus on **voice & audio features** (Epic 2.1 and 2.2: tone detection, speed control, parsing improvements) while Developer 2 handles **feeds and analytics** (Epic 2.3 and 2.4: usage tracking, multiple feeds UI). They should coordinate on any overlapping areas: for instance, changes to the Article model or Feed model should be communicated (if one adds fields for tone or voice, the other should be aware for migrations). Merging the multi-feed support will touch how articles are created (Developer 1’s code in Celery might be creating articles under a feed – ensure it still works when multiple feeds exist). Frequent communication and use of feature branches will help. By the end of Phase 2, the two developers can jointly do a thorough test of the entire system, possibly with one acting as a “user” and the other observing the server logs to ensure everything is smooth. After Phase 2, the product should be robust, feature-complete, and ready for beta launch.
