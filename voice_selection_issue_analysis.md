# RSS-TTS Voice Selection Issue Analysis

## Problem Description

Despite users selecting different voice presets or voice settings, all audio is being generated with the "alloy" voice instead of the selected voice.

## Root Causes

After thorough investigation, I've identified several related issues that could cause this behavior:

### 1. Dual Field Synchronization Issue

The system uses two parallel fields for voice selection:
- `article.voice` - Original voice field (CharField)
- `article.voice_id` - Newer explicit voice field (CharField)

Recent commits (de95a99, 9029d5b) attempted to fix synchronization issues between these fields, but there are still cases where only one field is updated:

- `VoiceParameterGenerationService.generate_voice_parameters()` only sets `article.voice_id` but not `article.voice`
- When applying feed presets, both fields should be synchronized but might not be in all code paths

### 2. Voice Selection Priority Chain

The voice selection logic was recently updated in commit 9029d5b to correctly prioritize the `article.voice` field first, but the changes may not have been comprehensive:

```python
# In tasks.py
fallback_voice = (
    article.voice
    or article.voice_parameters.get("voice_id")
    or article.voice_id
    or getattr(settings, "OPENAI_TTS_VOICE", "alloy")
)
```

This code correctly prioritizes `article.voice` first, but if this field isn't being properly populated in all code paths, it won't help.

### 3. Missing Default Voice Setting

The system falls back to a default voice setting that may not be properly configured:

```python
getattr(settings, "OPENAI_TTS_VOICE", "alloy")
```

If `OPENAI_TTS_VOICE` is not defined in `settings.py`, this will always default to "alloy".

### 4. Auto-Voice Configuration Issues

When using auto-voice mode, voice parameters are generated but may not be correctly applied:

```python
# In voice_parameter_generation.py
if "voice_id" in voice_parameters:
    article.voice_id = voice_parameters["voice_id"]
    # Missing: article.voice = voice_parameters["voice_id"]
```

This could cause the `voice` field to remain as the default "alloy" even when `voice_id` is set to something else.

### 5. Edge Cases in Voice Preset Application

When applying voice presets, both fields should be updated, but there might be edge cases where this isn't happening:

```python
# In user_preferences.py
if voice_preset is not None:
    article.voice_preset = voice_preset
    article.voice_id = voice_preset.voice_id
    article.voice = voice_preset.voice_id  # This line was recently added
    article.speed = voice_preset.speed
```

If an older version of the code is running or if there's an edge case not covered by the fix, this could cause issues.

## Recent Fixes

Two recent commits have addressed parts of this problem:

1. **Commit 9029d5b**: "fix: prioritize article.voice field when selecting TTS voice"
   - Changed the priority order to check article.voice field first
   - This indicates there was previously an issue where article.voice was being ignored

2. **Commit de95a99**: "fix: ensure both voice and voice_id fields are set when selecting a voice"
   - Updated code to set both fields together
   - Added `voice` to the `update_fields` lists in save operations

These fixes are steps in the right direction but may not fully resolve the issue across all code paths.

## Recommended Solutions

To ensure the correct voice is always used, the following fixes are recommended:

1. **Complete Field Synchronization**:
   - Update `VoiceParameterGenerationService.generate_voice_parameters()` to set both fields:
     ```python
     if "voice_id" in voice_parameters:
         article.voice_id = voice_parameters["voice_id"]
         article.voice = voice_parameters["voice_id"]  # Add this line
     ```
   - Ensure all code paths that modify one field also modify the other

2. **Add Default Voice Setting**:
   - Add `OPENAI_TTS_VOICE = os.environ.get("OPENAI_TTS_VOICE", "alloy")` to `settings.py`
   - This makes the default configurable and explicit

3. **Create Data Migration**:
   - Add a migration to sync any existing mismatched records
   - Set `voice = voice_id` for all articles where they differ

4. **Add Debug Logging**:
   - Log the selected voice in key locations to track voice selection
   - Example: `logger.debug(f"Using voice: {fallback_voice} for article {article_id}")`

5. **Comprehensive Testing**:
   - Create test cases for each voice selection path
   - Ensure each voice mode (single_default, single_custom, auto) works correctly

By implementing these changes, the system should correctly use the selected voice in all scenarios rather than defaulting to "alloy".

## Immediate Next Steps

1. Fix `VoiceParameterGenerationService.generate_voice_parameters()` to set both voice fields
2. Add default voice setting to `settings.py`
3. Update `VoiceConfigurationService.configure_article_voice()` to ensure both fields are updated
4. Add debug logging to trace voice selection
5. Create a data migration to fix existing records