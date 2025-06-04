# Issues

## Progress Update (2025-06-02)

### ✅ Completed Critical Fixes (P0)
- [x] **Critical bug: editing voice presets brings up the voice preset page with no content in input elements** - FIXED: Modified voice_preset_edit view to preserve existing voice_id/speed when POST data is empty
- [x] **Article.clean() dual-voice field enforcement** - FIXED: Now enforces single source of truth by always resetting voice to default when voice_id is set, with proper logging
- [x] **Universal TTS speed clamping** - FIXED: _clamp_tts_speed() now called before every client.audio.speech.create() call
- [x] **Bug: Presets fail. In prod, choosing a preset, like "test echo" initially shows on the UI. However, post-processing the voice is nova, every time.** - FIXED: VoiceConfigurationService now short-circuits AI generation when preset is active
- [x] **Bug: presets should not use multi-voice, or at least, multiple voices should not be applied. We can still chunk for tone.** - FIXED: ChunkToneService now uses preset voice for all chunks when preset is active

### ✅ Completed High Priority Fixes (P1)
- [x] **TTS Speed Control**: Model-aware speed handling implemented - gpt-4o-mini-tts uses instructions, tts-1 uses speed param
- [x] **Celery Task ID**: Robust handling in batched dispatch - saves cleared task_id before dispatch, restores on failure
- [x] **Documentation**: Fixed misleading performance claims in PARALLEL_TTS_README.md - clarified speedup equals worker concurrency
- [x] **Repository hygiene**: .pytest_cache/ already properly ignored in .gitignore

### 🎯 Feature Requests (P2)
- [ ] ~~Fix: we should move to the tts-hd model.~~ **CLARIFIED**: Default is already `gpt-4o-mini-tts` which is the newest and most capable model. If users want to optionally use `tts-1-hd` for higher quality than `tts-1`, they should understand it doesn't support per-chunk `instructions` and will lose ChunkToneService's intelligent voice control capabilities.

[ ] feat: estimated cost. We should have an internal table that tracks the cost per 1m tokens per model, and then display the total cost of the article in the UI, so that users can see how much it  cost them to process the article. We will only show actual costs, we will not worry about predictive costs for now.

[ ] Text extraction. I want to change how we handle text extraction for URLs. Instead of picking what text to use, I want to remove obviously wrong text such as:

script tags
style tags
style-attributes of other elements

and then pass the remaining DOM to gpt4.1 and ask IT to select the main article text. This way, we can handle pages that don't have article tags, or are txt files and not html, or other oddities. gpt-4.1 should be instructed to choose the first article or blog post it sees, in the event of many on one page. It should remove ads, images and pull-quotes if the pull-quotes are also part of the main text.

From there, the text can enter the rest of the pipeline.

[ ] RESTful API for submissions. I want to have a RESTful API for submitting articles, so that we can use it from other apps, such as a browser extension to add articles, or Apple Shortcuts, or even curl. We'll need to support URLs, text, and titles, but all voices will be auto via the API, at least for now. We will have user-level API keys, and users can POST to api/v1/feeds/<uuid>/articles/ or a similar path.

We should just drf and drf-spectacular to generate the API docs.

[ ] Puppeteer or Playwright fallback. If a basic request to a site is blocked, we should fallback asynchronously to a headless browser like Puppeteer or Playwright to get the text. We will only change this one step in the pipeline, so that the rest of the pipeline can remain unchanged. This will allow us to handle sites that block requests from our servers, such as news sites that block requests from known bots or scrapers.
