<joe1_review>
Updated Action-Item Tracker (“Phase-3” review – Joe)

Legend 🔴 Critical 🟡 Major 🟢 Minor / Cleanup ✅ Done (verified in code base)

────────────────────────────────────────
🔴 CRITICAL (blockers – must land before next deploy)
1. Canonical-media-path refactor
   • Define the ONLY valid storage path as `MEDIA_ROOT/articles/<uuid>.mp3`.
   • tasks.process_article must always write here and save `article.audio_file_path = 'articles/<uuid>.mp3'`.
   • Replace `_resolve_path()` and `_get_article_audio_file_path()` with a single helper that just joins the two pieces.
   • Add a management command (`migrate_audio_paths`) to move legacy files & patch DB rows.
   • Remove all legacy-path guesses after migration; keep a 30-day DeprecationWarning.

2. ArticleDeleteView safety audit
   • After the refactor above, `_get_article_audio_file_path()` should be ≤10 lines and impossible to walk up directories.
   • Add `assert not os.path.isdir(file_path)` before `os.unlink`.
   • Unit-test: deleting an article only unlinks its file and leaves siblings intact.

3. `voice` / `voice_id` single source of truth
   • Decision (team): treat `voice_id` as canonical. Make `voice` a @property wrapper or migrate DB to drop it after Phase 2.
   • Until then: create `models.Article.clean()` that guarantees both fields match before save. Fail loudly in admin/tests.

4. Performance of `_chunk_text`
   • Profile with 30 000-word lorem ipsum; target < 80 ms on M1/3.0 GHz.
   • Replace repeated string concat with list/`join` if necessary.
   • Add a benchmark test in `tests/perf/test_chunk_text.py` (pytest-marked `slow`).

────────────────────────────────────────
🟡 MAJOR (Phase-next sprint)
5. `UserVoicePreset.voice_id` – add `choices=VOICE_CHOICES`, create data-migration fixing bad values.

6. Cache constants
   • Move `VoiceConfigurationService.get_available_voice_modes()` and `.get_available_speeds()` to module-level tuples; annotate with `@lru_cache` if dynamic in the future.

7. README / Ops
   • Add “Running in production with PostgreSQL” subsection; show `DATABASE_URL` + sample `docker-compose.override.yml`.
   • Mention that local SQLite is NOT recommended for > 2 GB DB / multi-container.

8. .gitignore
   • Append `/.pytest_cache/` and `/media/*` (dev artefacts).

9. Test scaffolding clean-up
   • Delete duplicates:
     ‑ `text_to_audio/forms_improved.py` (identical to forms.py)
     ‑ `test_signup_logic.py` (covered by Django tests)
     ‑ `run_tests_with_mock.py` (same as run_all_tests_with_mock.py)
     ‑ `test_specific_multi_voice.py` (subset of main suite)

10. One golden-path integration test
    (mock OpenAI) : submit URL ➜ celery runs eagerly ➜ RSS endpoint returns enclosure.

────────────────────────────────────────
🟢 MINOR / NICE-TO-HAVE
11. Cache `get_available_voice_modes` (if not handled in #6).

12. `Article.voice` default: presently `blank=False` yet form allows empty ⇒ add `blank=True` **or** keep non-blank & enforce setting in `save_article_preferences`.

13. process_article edge-case
    `final_audio_path.relative_to(media_root)` raises `ValueError` if path escapes root; wrap in `try/except` and fall back to basename.

14. Token logging – if `usage.total_tokens` missing & header absent, record `None` not `0` (to distinguish “unknown” vs “zero”).

15. ContentAnalysisService – repair logic already drafted by Joe; implement + unit tests (malformed JSON, missing keys).

────────────────────────────────────────
✅ ALREADY FIXED / VERIFIED DURING THIS PASS
• `OPENAI_ANALYSIS_MODEL` & `OPENAI_CLASSIFICATION_MODEL` settings exist.
• `voice_instructions` param removed.
• `Feed.voice_mode` default = `auto`; migration 0003 present.
• `MAX_ANALYSIS_WORDS` configurable (8000 default).
• Destructive `shutil.rmtree` removed; `os.unlink` in use.

────────────────────────────────────────
Documentation & File-Pruning

Move the following to `docs/archive/` (or delete after verification):
  – VOICE_TONE_SUMMARY_IMPLEMENTATION.md
  – multi_voice_implementation_plan.md
  – voice_selection_issue_analysis.md
  – voice_fix_implementation.md
  – github-issue-auto-formatter.md
  – github-actions-improvements.md
  – MULTIPLE_FEEDS_IMPLEMENTATION.md
  – past review logs (`mike*.md`, `joe*.md`) once all tasks landed
  – PR_REVIEW_ACTION_PLAN.md after its own checklist is 100 % complete.

Keep & update: PROJECT_PLAN.md, README.md, TESTING.md, voice_flow_diagram.md (sync with current code).

────────────────────────────────────────
Next-Step Ownership (suggested)

| Item | Owner | ETA |
| ---- | ----- | --- |
| 1,2  | @backend-lead | 2 d |
| 3    | @data-migration | 1 d |
| 4    | @perf-focus | 1 d |
| 5-7  | @models-guru | 1 d |
| 8-10 | @qa/dev-ops  | 1 d |
| 11-15| open | backlog |

Please create GitHub issues linked to this checklist and move them to the “Phase 1 clean-up” milestone. Once the critical quartet is merged and deployed we can mark Phase 1 as truly “done-done”.

— Joe
</joe1_review>
