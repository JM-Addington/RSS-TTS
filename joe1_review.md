<joe1_review>
Joe’s second-pass review
=======================
I focused on the three areas you asked about: (a) the new automatic-tone / voice pipeline, (b) TTS integration against the latest OpenAI spec, and (c) general correctness / maintainability for a single-instance basement deployment that might grow modestly.

Below is **Mike’s original action-item list with my additions, clarifications and status updates**. Items marked ✅ are already fixed on `main`; items marked 🟥 / 🟧 / 🟩 are new or still open.

--------------------------------------------------------------------
Updated action-items tracker
--------------------------------------------------------------------

🔴 Critical (ship-stoppers / data-loss / obviously broken paths)
--------------------------------------------------------------------
1. 🟥 **Single-voice code never passes `instructions` to the TTS endpoint**
   • `voice_prompt` is built in `process_article` but never used.
   • Fix: when `OPENAI_TTS_MODEL in {"gpt-4o-mini-tts","tts-1-hd"}` call
     `client.audio.speech.create(..., instructions=voice_prompt)`.
   • Do the same inside the Chunk-Tone and legacy multi-voice loops.

2. 🟥 **Duplicate (and inconsistent) calls to `ContentAnalysisService`**
   • When `Feed.voice_mode == AUTO`, `configure_article_voice()` **already** triggers one analysis through `VoiceParameterGenerationService`, but `process_article()` calls `ContentAnalysisService.analyze_content()` again.
   • Results can disagree + you’re paying twice.
   • Refactor: return the first result up the stack or inject it into the task context so the second call is skipped.

3. 🟥 **Legacy multi-voice path drops the tail of long articles**
   • Only the first `MAX_ANALYSIS_WORDS` words (< 8 000) are given to the LLM; later, `audio_segments` are iterated verbatim, so the remainder of the article is silently lost.
   • Either:
     a) Deprecate the legacy path and force `ENABLE_CHUNK_TONE_LLM=True`, or
     b) Re-chunk any leftover text after the analysed prefix and stitch it with narrator voice.

4. 🟥 **`Article.clean()` conflicts with services that set both `voice` and `voice_id`**
   • Services now set both fields (“nova” → both columns).
   • Validation fails when a model/form runs `full_clean`.
   • Decide on a single canonical field (recommend: **always use `voice_id`**).
   • Update `Article.clean()`, services and migrations accordingly.

5. 🟥 **Unsupported voice id `verse` shipped in `VOICE_CHOICES`**
   • Not in OpenAI docs – remove or guard against selection.

🟧 Major (bugs, big perf/cost hits, confusing for users)
--------------------------------------------------------------------
6. 🟧 `MAX_ANALYSIS_WORDS` + `max_completion_tokens` mismatch
   • 8 000-word sample can return > 500 tokens. Either lower word cap (≈2 000) or raise `max_completion_tokens` to ~2 000.

7. 🟧 Speed clamping is missing in TTS calls inside single-voice fallback
   • Small typo: clamp logic exists earlier but isn’t reapplied after `fallback_speed` is read. Add `max(0.25, min(4.0, float(speed)))` before the API call.

8. 🟧 `prompt` field referenced but doesn’t exist on `Article`
   • Either add a `prompt` TextField (and expose in admin) or drop that save.

9. 🟧 SQLite vs. PostgreSQL docs inconsistent
   • README suggests Postgres option, `settings.py` hard-codes SQLite.
   • Pick one story and update docs/settings/env defaults.

10. 🟧 Redis description in README is stale – worker no longer “contains” Redis.

11. 🟧 `.pytest_cache/` not in `.gitignore`.

🟩 Minor / polish / tech-debt
--------------------------------------------------------------------
12. 🟩 Add global list of **supported voices** in one place (service constant) and reuse in model choices & forms.

13. 🟩 `VoiceConfigurationService.get_available_voice_modes()` can be `@cached_property`.

14. 🟩 Clamp speed everywhere (including multi-voice & Chunk-Tone).

15. 🟩 Remove stale code that still sets `voice` field when the canonical choice becomes `voice_id`.

16. 🟩 Align default LLM names: internal fallback uses `"gpt-4.1"` but settings default is `"gpt-4o-mini"`.

17. 🟩 Add unit test that verifies `instructions` is forwarded to the TTS SDK for every generated chunk.

18. 🟩 CI: add `pytest -q` smoke-run to the 20-test.yml workflow (today only Django-test runner is used in helpers).

19. 🟩 Docs: in `APPLE_PODCASTS_TEST.md` add note that the *Caddy* container must be reachable on the same BASE_URL used in feed URLs.

20. 🟩 Consider warning banner in UI when running on SQLite (“single-user mode – may dead-lock under heavy parallel jobs”).

--------------------------------------------------------------------
Status of Mike’s earlier items
--------------------------------------------------------------------
✅ 1-5 (Mike’s critical fixes) are merged on `main`: destructive delete, missing settings, bad kwarg, etc.
✅ Feed default changed to `VOICE_MODE_AUTO` and migration is present.
✅ `MAX_ANALYSIS_WORDS` already reduced from 750 k → 8 k, but now we need the token alignment fix (see item 6).

--------------------------------------------------------------------
Recommended next steps (in order)
--------------------------------------------------------------------
1. Implement items 1-4 (red).
2. While there, roll in items 6-8 (orange) to avoid another code-touch in task pipeline.
3. Cut a tiny data-migration that normalises `voice`/`voice_id` (choose one) to avoid admin/editor grief.
4. Sweep through green items when convenient.

That should stabilise automatic voice tone generation and keep TTS costs/pain down while the app is still running from your basement server.

Let me know if you’d like code-snippets for any specific fix.
</joe1_review>
