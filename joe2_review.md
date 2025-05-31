<joe2_review>
🎯  FINAL ACTION PLAN
(ordered by priority – tackle the 🔴 block before moving on)

────────────────────────────────────────
🔴  Critical ‑ must land before next deploy
────────────────────────────────────────
1. Pass `instructions` to every TTS call
   • In `tasks.py` (single-voice, ChunkTone, legacy multi-voice loops) add
   ```python
   if settings.OPENAI_TTS_MODEL in {"gpt-4o-mini-tts", "tts-1-hd"} and voice_prompt:
       tts_args["instructions"] = voice_prompt
   ```
   • Add unit test that asserts this arg is forwarded.

2. De-duplicate `ContentAnalysisService` calls
   • When `Feed.voice_mode == AUTO`, reuse the analysis result produced inside `VoiceParameterGenerationService` instead of calling the service a second time.
   • Return that result to the task (or cache it on the `Article`) so `article.multi_voice_data` and `article.voice_parameters` stay in sync.

3. Long-article loss in legacy multi-voice path
   a) Preferred: deprecate legacy path → set `ENABLE_CHUNK_TONE_LLM = True` by default and remove legacy branch.
   b) If legacy must stay: after LLM-segmented prefix, chunk the remaining text with narrator voice so 100 % of the article is synthesised.

4. Single source of truth for voice fields
   • Canonical field = **`voice_id`**.
   • Update `Article.clean()`, services, forms to write **only** `voice_id`.
   • Migrations:
     – If `voice_id` empty → copy from `voice`.
     – If both set → keep `voice_id`, clear `voice`.
   • Remove “set both fields” lines throughout services/tasks.

5. Remove unsupported voice `"verse"` from `VOICE_CHOICES` and from forms.

────────────────────────────────────────
🟧  Major ‑ fix during the same sprint
────────────────────────────────────────
6. Token/size mismatch in legacy multi-voice
   • If legacy path kept: either reduce `MAX_ANALYSIS_WORDS` (≈2 000) **or** raise `max_completion_tokens` to ≥ 2000.

7. Clamp `speed` just before every TTS call (`0.25 ≤ speed ≤ 4.0`).

8. `Article.prompt` reference but no field
   • Option A: drop the write to `article.prompt`.
   • Option B: add `prompt = models.TextField(blank=True)` if you want to preserve it.

9. Database story
   • Decide: SQLite everywhere or PostgreSQL for prod.
   • Bring `settings.py`, `README.md`, `.env.sample` into agreement.

10. README – fix Redis description (stands alone container).

11. Add `.pytest_cache/` to `.gitignore`.

────────────────────────────────────────
🟩  Minor / polish
────────────────────────────────────────
12. Centralise supported-voice list in one constant and reuse in model, forms, services.

13. `VoiceConfigurationService.get_available_voice_modes()` → `@cached_property` or module constant.

14. Speed-clamp helper used in ChunkTone + legacy code paths.

15. Once `voice` field is deprecated, remove remaining writes to it.

16. Align hard-coded model fallback strings (use `"gpt-4o-mini"` everywhere).

17. CI: add `pytest -q` smoke run to `20-test.yml`.

18. Docs – note about Caddy base URL in `APPLE_PODCASTS_TEST.md`.

19. Optional UI banner if running on SQLite in production.

────────────────────────────────────────
Implementation order
────────────────────────────────────────
1.  Critical block (items 1–5)
2.  Major block (items 6–11)
3.  Minor / polish (items 12–19)

When the Critical fixes are merged, run the full test suite plus a manual end-to-end check (long article → Apple Podcasts) before deploying.
</joe2_review>
