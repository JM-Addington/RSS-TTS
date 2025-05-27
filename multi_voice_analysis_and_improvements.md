# Multi-Voice Feature Analysis and Improvements

## Current Multi-Voice Implementation

The RSS-TTS system has a sophisticated multi-voice feature that allows different parts of an article to be read by different AI voices. This creates a more engaging and dynamic listening experience, especially for articles with dialog or distinct sections.

### How Multi-Voice Works

1. **Content Analysis**: When an article is processed with the "auto" voice mode, the system analyzes the text using `ContentAnalysisService.analyze_content()` which:
   - Calls OpenAI's GPT-4.1 model with a detailed prompt
   - Asks the LLM to segment the text into parts that should be read by different voices
   - Expects a JSON response with voice definitions and text segments

2. **Voice Assignment**: The LLM returns:
   - `voices`: A list of voice definitions (e.g., narrator, quoted expert, etc.)
   - `audio_segments`: Text segments with assigned voices

3. **TTS Processing**: The system then:
   - Processes each segment with its assigned voice
   - Combines the audio segments into a seamless MP3
   - Falls back to single-voice if multi-voice processing fails

## Why Multi-Voice Isn't Working

The multi-voice feature is implemented but not working for most users because:

1. **Missing UI Controls**: There's no UI element for users to select the "auto" voice mode that activates multi-voice
2. **Default Settings Issue**: The default voice_mode is "single_default", which bypasses multi-voice processing
3. **Validation Requirements**: The multi-voice data structure must pass strict validation

## Key Issues Identified

### 1. No UI to Enable Multi-Voice

The `FeedForm` doesn't include the `voice_mode` field, so users can't switch to "auto" mode which enables multi-voice:

```python
# forms.py
class FeedForm(forms.ModelForm):
    class Meta:
        model = Feed
        fields = ["name", "default_voice_preset"]  # voice_mode is missing
```

### 2. Voice Mode Not Exposed in Templates

The feed_form.html template doesn't include any control for voice_mode:

```html
<!-- No voice_mode field in the template -->
<div class="mb-3">
    <label for="{{ form.default_voice_preset.id_for_label }}" class="form-label">Default Voice Preset</label>
    {{ form.default_voice_preset|add_class:"form-select" }}
</div>
```

### 3. LLM Response Validation

The `_is_valid_multi_voice_data` function enforces strict requirements for the multi-voice data structure. If the LLM doesn't format the response correctly, multi-voice processing is skipped.

## Recommendations

### 1. Add Voice Mode UI Controls

Update the `FeedForm` to include voice_mode:

```python
class FeedForm(forms.ModelForm):
    class Meta:
        model = Feed
        fields = ["name", "default_voice_preset", "voice_mode"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        voice_service = VoiceConfigurationService()
        self.fields["voice_mode"] = forms.ChoiceField(
            choices=voice_service.get_available_voice_modes(),
            initial=Feed.VOICE_MODE_AUTO,  # Change the default to auto
            help_text="Select how voices should be generated for articles in this feed."
        )
```

### 2. Update Templates to Include Voice Mode

Update feed_form.html to include the voice_mode field:

```html
<div class="mb-3">
    <label for="{{ form.voice_mode.id_for_label }}" class="form-label">Voice Mode</label>
    {{ form.voice_mode|add_class:"form-select" }}
    <div class="form-text">{{ form.voice_mode.help_text }}</div>
</div>
```

### 3. Change the Default Voice Mode

To make multi-voice the default experience, update the Feed model:

```python
voice_mode: models.CharField = models.CharField(
    max_length=20,
    choices=VOICE_MODE_CHOICES,
    default=VOICE_MODE_AUTO,  # Change this from VOICE_MODE_SINGLE_DEFAULT
    help_text="Voice mode preference for this feed",
)
```

### 4. Add Migration for Existing Feeds

Create a migration to update existing feeds to use auto voice mode:

```python
def update_feeds_to_auto_voice(apps, schema_editor):
    Feed = apps.get_model("text_to_audio", "Feed")
    Feed.objects.all().update(voice_mode="auto")

class Migration(migrations.Migration):
    dependencies = [("text_to_audio", "0002_sync_voice_fields")]
    operations = [migrations.RunPython(update_feeds_to_auto_voice)]
```

### 5. Add More Robust Error Handling

Improve error handling for LLM responses to recover from common formatting issues:

```python
def analyze_content(self, text, title=None, max_completion_tokens=500):
    # Existing code...
    try:
        content = response.choices[0].message.content
        result = json.loads(content)

        # Try to repair common issues
        if "voices" not in result or not result["voices"]:
            result["voices"] = [{"name": "narrator", "tone": "neutral", "tts_model": "alloy", "tts_speed": 1.0}]

        if "audio_segments" not in result or not result["audio_segments"]:
            result["audio_segments"] = [{"text": text, "voice_name": "narrator"}]

        # Ensure all required fields exist
        for voice in result["voices"]:
            if "name" not in voice:
                voice["name"] = "voice_" + str(result["voices"].index(voice))
            if "tts_model" not in voice:
                voice["tts_model"] = "alloy"  # Default voice
            if "tts_speed" not in voice:
                voice["tts_speed"] = 1.0  # Default speed

        # Ensure all segments reference defined voices
        valid_voice_names = [voice["name"] for voice in result["voices"]]
        for segment in result["audio_segments"]:
            if "voice_name" not in segment or segment["voice_name"] not in valid_voice_names:
                segment["voice_name"] = valid_voice_names[0]  # Use first voice as fallback

        # Continue with validation...
```

### 6. Add Better Visualization for Multi-Voice Articles

Add an indicator in the article list to show which articles use multi-voice:

```html
<span class="badge bg-info" title="Uses multiple AI voices for a more dynamic experience">
    <i class="bi bi-people-fill"></i> Multi-Voice
</span>
```

### 7. Add Multi-Voice Demo in User Interface

Add a demonstration feature that shows the benefits of multi-voice:

```html
<div class="card mb-4">
    <div class="card-header">
        <h5>Multi-Voice Example</h5>
    </div>
    <div class="card-body">
        <p>The <strong>Auto-generated voice</strong> setting enables our AI to analyze your content and use different voices for:</p>
        <ul>
            <li>Narration vs. quotations</li>
            <li>Different speakers or characters</li>
            <li>Changes in tone or style</li>
        </ul>
        <audio controls src="/static/examples/multi_voice_demo.mp3"></audio>
    </div>
</div>
```

## Implementation Plan

1. Add voice_mode to FeedForm and templates
2. Create a migration to set existing feeds to "auto" mode
3. Add helpful documentation and examples in the UI
4. Improve error recovery for LLM responses
5. Add visual indicators for multi-voice articles
6. Create tests for the complete multi-voice flow

By implementing these changes, the multi-voice functionality will become the default experience for users, creating more engaging audio content.
