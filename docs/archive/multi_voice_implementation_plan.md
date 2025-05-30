# Multi-Voice Implementation Plan

## Overview

The multi-voice feature in RSS-TTS creates more engaging audio by using different voices for different parts of an article (narration, quotes, characters, etc.). While the core functionality is already implemented, it isn't accessible to users because of missing UI elements and is set as non-default. This plan outlines the steps to make multi-voice the standard experience.

## Improvements

### 1. Add Voice Mode to Feed Form

**File**: `text_to_audio/forms.py`

Update the `FeedForm` class to include the voice_mode field:

```python
class FeedForm(forms.ModelForm):
    # Add voice_mode field to enable multi-voice functionality
    voice_mode = forms.ChoiceField(
        required=True,
        help_text="Select how voices are generated for articles in this feed.",
    )

    class Meta:
        model = Feed
        fields = ["name", "default_voice_preset", "voice_mode"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Configure voice mode choices
        voice_service = VoiceConfigurationService()
        self.fields["voice_mode"].choices = voice_service.get_available_voice_modes()
        self.fields["voice_mode"].initial = Feed.VOICE_MODE_AUTO
        self.fields["voice_mode"].help_text = (
            "Auto-generated voice enables multi-voice narration with different voices for "
            "quotes, characters, and distinct sections."
        )
```

### 2. Update Feed Template to Include Voice Mode

**File**: `text_to_audio/templates/feed_form.html`

Add the voice_mode field to the form:

```html
<!-- New Voice Mode Selector -->
<div class="mb-3">
    <label for="{{ form.voice_mode.id_for_label }}" class="form-label">Voice Generation Mode</label>
    {{ form.voice_mode|add_class:"form-select" }}
    <div class="form-text">{{ form.voice_mode.help_text }}</div>
</div>
```

Add information about multi-voice:

```html
<!-- Multi-Voice Feature Info -->
<div class="card bg-light mb-4">
    <div class="card-body">
        <h5 class="card-title"><i class="bi bi-people-fill"></i> Multi-Voice Technology</h5>
        <p class="card-text">
            Our auto-generated voice mode uses AI to analyze your content and create more engaging audio by:
        </p>
        <ul>
            <li>Using different voices for narration vs. quotes</li>
            <li>Distinguishing between different speakers</li>
            <li>Adapting to changes in tone and style</li>
        </ul>
    </div>
</div>
```

### 3. Create Migration to Update Existing Feeds

**File**: `text_to_audio/migrations/0003_set_feeds_to_auto_voice.py`

```python
def update_feeds_to_auto_voice(apps, schema_editor):
    """
    Change all feeds to use auto-generated voice mode which enables multi-voice functionality.
    """
    Feed = apps.get_model("text_to_audio", "Feed")
    VOICE_MODE_AUTO = "auto"

    # Update all feeds to use auto-generated voice
    Feed.objects.all().update(voice_mode=VOICE_MODE_AUTO)

class Migration(migrations.Migration):
    dependencies = [("text_to_audio", "0002_sync_voice_fields")]
    operations = [migrations.RunPython(update_feeds_to_auto_voice)]
```

### 4. Add Multi-Voice Indicator to Article List

**File**: `text_to_audio/templates/article_list.html`

Add an indicator for articles using multi-voice:

```html
{% if article.multi_voice_data %}
<span class="badge bg-info" title="Uses multiple AI voices for a more dynamic experience">
    <i class="bi bi-people-fill"></i> Multi-Voice
</span>
{% endif %}
```

### 5. Improve Error Handling in ContentAnalysisService

**File**: `text_to_audio/services/content_analysis.py`

Add better error handling for LLM responses:

```python
# Add voice names if missing from segments
valid_voice_names = [voice["name"] for voice in result["voices"]]
for segment in result["audio_segments"]:
    if "voice_name" not in segment or segment["voice_name"] not in valid_voice_names:
        segment["voice_name"] = valid_voice_names[0]  # Use first voice as fallback
```

### 6. Add Multi-Voice Settings Section to User Voice Preferences

**File**: `text_to_audio/templates/text_to_audio/voice_preferences.html`

Add a section about multi-voice to the voice preferences page:

```html
<div class="card mt-4">
    <div class="card-header">
        <h3>Multi-Voice Settings</h3>
    </div>
    <div class="card-body">
        <p>Multi-voice technology automatically assigns different voices to:</p>
        <ul>
            <li>Quotations and dialogue</li>
            <li>Different characters or speakers</li>
            <li>Narration vs. direct statements</li>
        </ul>
        <p>This is enabled by default for all feeds using the "Auto-generated voice" mode.</p>
        <p>
            <a href="{% url 'feed-list' %}" class="btn btn-outline-primary">
                <i class="bi bi-gear-fill"></i> Manage Feed Settings
            </a>
        </p>
    </div>
</div>
```

## Testing Plan

1. **Unit Tests**: Add tests for multi-voice form fields and validation
2. **Integration Tests**: Test the full multi-voice flow from content analysis to TTS
3. **UI Tests**: Verify multi-voice controls appear correctly in the UI
4. **Migration Test**: Verify feeds are properly updated to auto voice mode

## Rollout Plan

1. Make code changes to add UI controls
2. Apply migrations to update existing feeds
3. Test with sample content to verify multi-voice works
4. Monitor for any increase in error rates after deployment
5. Collect user feedback on the multi-voice experience

## Success Metrics

1. Percentage of articles successfully processed with multi-voice
2. User engagement metrics (time spent listening)
3. User feedback on multi-voice quality

## Future Enhancements

1. Allow users to customize which types of content get different voices
2. Add manual voice assignment for specific sections
3. Provide preview of multi-voice segments before processing
4. Add more detailed analytics on multi-voice usage and effectiveness
