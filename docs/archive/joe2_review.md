<joe2_review>
FINAL ACTION ITEMS
(Consolidated from all reviews – this will be the single source of truth for the “Phase-1 Clean-up” milestone)

────────────────────────────────────────
🔴  CRITICAL ‑ Must land before next deploy
1. Canonical media path refactor
   • Only valid path: `MEDIA_ROOT/articles/<article_uuid>.mp3`
   • `tasks.process_article` writes to that path and saves `article.audio_file_path = 'articles/<uuid>.mp3'` (relative).
   • Replace all path-guessing helpers with one simple helper: `os.path.join(settings.MEDIA_ROOT, article.audio_file_path)`.
   • Management command `migrate_audio_paths` to move legacy files and patch DB rows.
   • After migration remove legacy-path logic; leave `DeprecationWarning` for 30 days.

2. Article deletion safety
   • After (1) the helper should be ≤ 10 lines and never traverse parents.
   • In `ArticleDeleteView.delete()` add `assert not os.path.isdir(path)` before `os.unlink(path)`.
   • Unit-test: deleting an article unlinks only its own file; siblings stay.

3. `voice` vs `voice_id` single source-of-truth
   • Treat `voice_id` as canonical.
   • Add `Article.clean()` to raise `ValidationError` if the two fields diverge.
   • Data-migration  ❯  sync existing rows.
   • Plan: drop legacy `voice` field in Phase-2 once codebase is purged.

4. `_chunk_text` performance
   • Profile with a 30 000-word sample; target < 80 ms on M1/3 GHz.
   • Optimise (use list/`"".join()` if needed).
   • Add pytest benchmark in `tests/perf/test_chunk_text.py` (marked `slow`).

────────────────────────────────────────
🟡  MAJOR – land in next sprint (still Phase-1 scope)
5. `UserVoicePreset.voice_id`
   • Add `choices=VOICE_CHOICES`.
   • Data migration: validate & fix existing invalid values.

6. Constant caching / refactor
   • Move `get_available_voice_modes()` & `get_available_speeds()` outputs to module-level constants (or `@lru_cache`).

7. README / Ops docs
   • Add “Running in production with PostgreSQL” section, example `DATABASE_URL`, sample `docker-compose.override.yml`.
   • Note SQLite is dev-only.

8. Golden-path integration test
   • Mock OpenAI & Celery-eager.
   • Submit article, ensure MP3 appears at canonical path, RSS feed contains enclosure.

────────────────────────────────────────
🧹  CLEAN-UP / BACKLOG  (work as time allows)
9. `.gitignore`
   • Add `/.pytest_cache/` and `/media/*`.

10. Repo hygiene
    • Remove duplicates:
      ‑ `text_to_audio/forms_improved.py`
      ‑ `test_signup_logic.py`
      ‑ `run_tests_with_mock.py` (keep only `run_all_tests_with_mock.py`)
      ‑ `test_specific_multi_voice.py` (tests live in main suite)
    • Archive to `docs/archive/` (or delete) markdown files that are now historical:
      VOICE_TONE_SUMMARY_IMPLEMENTATION.md, multi_voice_implementation_plan.md, voice_selection_issue_analysis.md, voice_fix_implementation.md, github-issue-auto-formatter.md, github-actions-improvements.md, MULTIPLE_FEEDS_IMPLEMENTATION.md, old review logs, PR_REVIEW_ACTION_PLAN.md (after checklist complete).

11. `Article.voice` model field
    • Decide: set `blank=True` OR always force a value via forms/service; align with validation logic.

12. Extra guards in `process_article`
    • Wrap `final_audio_path.relative_to(media_root)` in try/except; on `ValueError` store basename and log critical.

13. OpenAI token logging
    • If token info missing, store `None` not `0`.  (`tokens_used` should be `null=True`).

14. `ContentAnalysisService` robustness
    • Implement JSON-repair logic (fill missing keys, default narrator, etc.) and add unit tests.

────────────────────────────────────────
📋  NEXT STEPS
• Create individual GitHub issues for each bullet; attach to “Phase-1 Clean-up” milestone.
• Assign owners:
  – 1-2 ➜ backend-lead
  – 3   ➜ data-migration specialist
  – 4   ➜ perf-focus dev
  – 5-7 ➜ models / docs owner
  – 8   ➜ QA / integration
  – 9-14 ➜ backlog / whoever free
• Once the four critical items are merged & deployed, Phase-1 can be declared “done-done”.

— Joe
</joe2_review>
