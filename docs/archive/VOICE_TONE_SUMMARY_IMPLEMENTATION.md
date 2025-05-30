# Voice Tone Detection, Speed Customization, and Article Summarization Implementation Plan

## Overview

This document outlines the implementation plan for three related features:
1. **Voice Tone Detection** (Issue #44): Analyze article content to detect tone and select appropriate voice
2. **Speed Customization** (Issue #45): Allow users to customize TTS playback speed
3. **Article Summarization** (Issue #48): Generate concise summaries of articles

The implementation uses a service-oriented architecture to combine these features efficiently while providing flexibility and user control.

## Service-Oriented Architecture

### Directory Structure

```
text_to_audio/
├── services/
│   ├── __init__.py
│   ├── content_analysis.py      # Tone detection & summarization
│   ├── voice_configuration.py   # Voice & speed mapping
│   └── user_preferences.py      # User voice profile management
```

### Service Components

#### A. ContentAnalysisService (`content_analysis.py`)

This service handles all content analysis through a unified API call:

```python
class ContentAnalysisService:
    """Service for analyzing article content."""

    def __init__(self, openai_api_key=None):
        """Initialize with optional API key override."""
        self.openai_api_key = openai_api_key
        self._client = None

    @property
    def client(self):
        """Lazily initialize OpenAI client."""
        if self._client is None:
            from django.conf import settings
            import openai
            self._client = openai.OpenAI(
                api_key=self.openai_api_key or settings.OPENAI_API_KEY
            )
        return self._client

    def analyze_content(self, text, title=None, max_tokens=500):
        """
        Analyze article content to detect tone and generate summary.

        Args:
            text: The article text to analyze
            title: Optional article title for context
            max_tokens: Maximum tokens for the response

        Returns:
            dict with keys:
                - tone: Detected tone of the article
                - summary: Generated summary
                - voice_recommendation: Recommended voice settings
        """
        # Prepare a sample of the text for analysis (first 2000 chars)
        text_sample = text[:2000]

        # Create the unified prompt
        prompt = self._create_analysis_prompt(text_sample, title)

        # Call OpenAI API with JSON mode
        response = self.client.chat.completions.create(
            model=self._get_analysis_model(),
            messages=[
                {"role": "system", "content": "You are an expert content analyzer."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        # Parse the response
        try:
            content = response.choices[0].message.content
            result = json.loads(content)
            return {
                "tone": result.get("tone", "neutral"),
                "summary": result.get("summary", ""),
                "voice_recommendation": result.get("voice_recommendation", {})
            }
        except (json.JSONDecodeError, AttributeError, IndexError) as e:
            logger.error(f"Error parsing content analysis response: {e}")
            # Return sensible defaults
            return {
                "tone": "neutral",
                "summary": "",
                "voice_recommendation": {"voice": "alloy", "speed": 1.0}
            }

    def _create_analysis_prompt(self, text, title):
        """Create the unified prompt for content analysis."""
        title_context = f" titled '{title}'" if title else ""
        return f"""
        Analyze the following article{title_context} and provide:

        1. A concise 2-3 sentence summary of the main points
        2. The overall tone of the article (e.g., formal, casual, technical, storytelling)
        3. A recommendation for voice parameters that would be appropriate for narrating this content

        Return your analysis in the following JSON format:
        {{
            "summary": "2-3 sentence summary here",
            "tone": "detected tone (one of: formal, casual, technical, storytelling, narrative, news, conversational)",
            "voice_recommendation": {{
                "voice": "recommended voice (one of: alloy, echo, fable, onyx, nova, shimmer)",
                "speed": recommended speed (float between 0.75 and 1.5)
            }}
        }}

        Article:
        {text}
        """

    def _get_analysis_model(self):
        """Get the model to use for content analysis."""
        from django.conf import settings
        return getattr(settings, "OPENAI_ANALYSIS_MODEL", "o4-mini")
```

#### B. VoiceConfigurationService (`voice_configuration.py`)

This service handles mapping tones to voices and applying user preferences:

```python
class VoiceConfigurationService:
    """Service for configuring TTS voice parameters."""

    # Default voice mappings by tone
    DEFAULT_VOICE_MAPPINGS = {
        "formal": {"voice": "onyx", "speed": 1.0},
        "casual": {"voice": "nova", "speed": 1.1},
        "technical": {"voice": "alloy", "speed": 0.9},
        "storytelling": {"voice": "echo", "speed": 0.95},
        "narrative": {"voice": "fable", "speed": 1.0},
        "news": {"voice": "shimmer", "speed": 1.1},
        "conversational": {"voice": "nova", "speed": 1.05},
        # Fallback
        "neutral": {"voice": "alloy", "speed": 1.0}
    }

    def __init__(self, voice_mappings=None):
        """Initialize with optional voice mappings override."""
        self.voice_mappings = voice_mappings or self.DEFAULT_VOICE_MAPPINGS

    def get_voice_config(self,
                        detected_tone,
                        user_preferences=None,
                        article_preferences=None,
                        voice_recommendation=None):
        """
        Determine the final voice configuration based on tone and preferences.

        Args:
            detected_tone: The detected tone of the article
            user_preferences: Dict with user's default preferences
            article_preferences: Dict with article-specific preferences
            voice_recommendation: Dict with AI-recommended voice settings

        Returns:
            Dict with final voice config: {"voice": "voice_id", "speed": float}
        """
        # Start with the default mapping for the detected tone
        base_config = self.voice_mappings.get(
            detected_tone,
            self.voice_mappings["neutral"]
        ).copy()

        # Apply AI recommendation if available
        if voice_recommendation:
            if "voice" in voice_recommendation:
                base_config["voice"] = voice_recommendation["voice"]
            if "speed" in voice_recommendation:
                base_config["speed"] = voice_recommendation["speed"]

        # Apply user preferences if available
        if user_preferences:
            if user_preferences.get("voice"):
                base_config["voice"] = user_preferences["voice"]
            if user_preferences.get("speed"):
                base_config["speed"] = user_preferences["speed"]

        # Apply article-specific preferences (highest priority)
        if article_preferences:
            if article_preferences.get("voice"):
                base_config["voice"] = article_preferences["voice"]
            if article_preferences.get("speed"):
                base_config["speed"] = article_preferences["speed"]

        # Validate and constrain values
        base_config["speed"] = max(0.75, min(1.5, base_config["speed"]))

        return base_config

    def get_available_voices(self):
        """
        Get list of available voices with labels.

        Returns:
            List of tuples: [(voice_id, display_name), ...]
        """
        return [
            ("alloy", "Alloy (Neutral)"),
            ("echo", "Echo (Narrative)"),
            ("fable", "Fable (Expressive)"),
            ("onyx", "Onyx (Authoritative)"),
            ("nova", "Nova (Friendly)"),
            ("shimmer", "Shimmer (Energetic)")
        ]

    def get_available_speeds(self):
        """
        Get list of available speed presets with labels.

        Returns:
            List of tuples: [(speed_value, display_name), ...]
        """
        return [
            (0.75, "Very Slow (0.75x)"),
            (0.9, "Slow (0.9x)"),
            (1.0, "Normal (1.0x)"),
            (1.1, "Slightly Fast (1.1x)"),
            (1.25, "Fast (1.25x)"),
            (1.5, "Very Fast (1.5x)")
        ]
```

#### C. UserPreferencesService (`user_preferences.py`)

This service manages user voice profiles:

```python
class UserPreferencesService:
    """Service for managing user voice preferences."""

    def get_user_preferences(self, user):
        """
        Get voice preferences for a user.

        Args:
            user: Django User object

        Returns:
            Dict with user preferences: {"voice": "voice_id", "speed": float}
        """
        from text_to_audio.models import UserVoiceProfile

        try:
            profile = UserVoiceProfile.objects.get(user=user)
            return {
                "voice": profile.preferred_voice,
                "speed": profile.preferred_speed
            }
        except (UserVoiceProfile.DoesNotExist, AttributeError):
            return None

    def save_user_preferences(self, user, voice=None, speed=None):
        """
        Save voice preferences for a user.

        Args:
            user: Django User object
            voice: Voice ID to save
            speed: Speed value to save

        Returns:
            UserVoiceProfile object
        """
        from text_to_audio.models import UserVoiceProfile

        profile, created = UserVoiceProfile.objects.get_or_create(user=user)

        if voice is not None:
            profile.preferred_voice = voice

        if speed is not None:
            profile.preferred_speed = float(speed)

        profile.save()
        return profile

    def get_article_preferences(self, article):
        """
        Get article-specific voice preferences.

        Args:
            article: Article object

        Returns:
            Dict with article preferences: {"voice": "voice_id", "speed": float}
        """
        preferences = {}

        if hasattr(article, 'voice_id') and article.voice_id:
            preferences['voice'] = article.voice_id

        if hasattr(article, 'speed') and article.speed is not None:
            preferences['speed'] = article.speed

        return preferences if preferences else None

    def save_article_preferences(self, article, voice=None, speed=None):
        """
        Save voice preferences for a specific article.

        Args:
            article: Article object
            voice: Voice ID to save
            speed: Speed value to save

        Returns:
            Updated Article object
        """
        if voice is not None:
            article.voice_id = voice

        if speed is not None:
            article.speed = float(speed)

        article.save(update_fields=['voice_id', 'speed'])
        return article
```

## Model Changes

### 1. Article Model Changes

```python
# In text_to_audio/models.py - Add to Article model

class Article(models.Model):
    # Existing fields...

    # New fields for tone detection and voice settings
    detected_tone = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="AI-detected tone of the article content."
    )
    voice_id = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Voice ID used for text-to-speech conversion."
    )
    speed = models.FloatField(
        null=True,
        blank=True,
        help_text="Speed multiplier for text-to-speech conversion."
    )

    # summary field already exists from migration 0009

    # Existing methods...
```

### 2. New UserVoiceProfile Model

```python
# In text_to_audio/models.py - Add new model

class UserVoiceProfile(models.Model):
    """Model for storing user voice preferences."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="voice_profile",
        help_text="The user these voice preferences belong to."
    )
    preferred_voice = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="User's preferred TTS voice."
    )
    preferred_speed = models.FloatField(
        default=1.0,
        help_text="User's preferred TTS speed multiplier."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the profile was created."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the profile was last updated."
    )

    def __str__(self):
        """Return a string representation of the profile."""
        return f"Voice profile for {self.user.username}"
```

### 3. Voice Mapping Configuration Model

```python
# In text_to_audio/models.py - Add new model

class VoiceMapping(models.Model):
    """Model for mapping tones to voice settings."""

    tone = models.CharField(
        max_length=50,
        unique=True,
        help_text="Tone category name."
    )
    voice_id = models.CharField(
        max_length=50,
        help_text="Voice ID to use for this tone."
    )
    speed = models.FloatField(
        default=1.0,
        help_text="Speed multiplier to use for this tone."
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this tone category."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this mapping is active."
    )

    def __str__(self):
        """Return a string representation of the mapping."""
        return f"{self.tone} → {self.voice_id} ({self.speed}x)"

    class Meta:
        ordering = ['tone']
```

## Task Updates

Update the Celery task to use our new services:

```python
# In text_to_audio/tasks.py

from text_to_audio.services.content_analysis import ContentAnalysisService
from text_to_audio.services.voice_configuration import VoiceConfigurationService
from text_to_audio.services.user_preferences import UserPreferencesService

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_article(self, article_id: int) -> str:
    # Existing beginning of function...

    try:
        # After extracting text content...

        # Initialize services
        content_service = ContentAnalysisService()
        voice_service = VoiceConfigurationService()
        pref_service = UserPreferencesService()

        # Analyze content to get tone, summary, and voice recommendation
        # Use existing text extraction logic but add analysis
        if article.text_content:
            # Use a sample of the text for analysis
            analysis_text = article.text_content
            if len(analysis_text) > 2000:
                analysis_text = analysis_text[:2000]

            analysis_result = content_service.analyze_content(
                analysis_text,
                title=article.title
            )

            # Save results to article
            article.detected_tone = analysis_result["tone"]
            article.summary = analysis_result["summary"]
            article.save(update_fields=["detected_tone", "summary"])

            # Get voice configuration
            user_preferences = pref_service.get_user_preferences(article.feed.user)
            article_preferences = pref_service.get_article_preferences(article)

            voice_config = voice_service.get_voice_config(
                detected_tone=analysis_result["tone"],
                user_preferences=user_preferences,
                article_preferences=article_preferences,
                voice_recommendation=analysis_result["voice_recommendation"]
            )

            # Save final voice config to article
            article.voice_id = voice_config["voice"]
            article.speed = voice_config["speed"]
            article.save(update_fields=["voice_id", "speed"])

        # Update the TTS API call to use configured voice and speed
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

        for i, chunk in enumerate(text_chunks):
            # Existing chunk processing...

            try:
                start_time = time.monotonic()
                # Update to include voice_id and speed
                response = client.audio.speech.create(
                    model=getattr(settings, "OPENAI_TTS_MODEL", "tts-1"),
                    voice=article.voice_id or getattr(settings, "OPENAI_TTS_VOICE", "alloy"),
                    input=chunk,
                    speed=article.speed or 1.0,  # Apply speed if set
                )
                # Rest of existing processing...

        # Rest of function...
```

## UI Implementation

### Forms for Voice Preferences

```python
# In text_to_audio/forms.py

from django import forms
from text_to_audio.models import UserVoiceProfile
from text_to_audio.services.voice_configuration import VoiceConfigurationService

class UserVoicePreferenceForm(forms.ModelForm):
    """Form for user voice preferences."""

    class Meta:
        model = UserVoiceProfile
        fields = ['preferred_voice', 'preferred_speed']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        voice_service = VoiceConfigurationService()

        # Add choices for voice and speed
        self.fields['preferred_voice'] = forms.ChoiceField(
            choices=voice_service.get_available_voices(),
            required=False,
            help_text="Your preferred voice for all articles."
        )

        self.fields['preferred_speed'] = forms.ChoiceField(
            choices=voice_service.get_available_speeds(),
            required=False,
            help_text="Your preferred speaking speed for all articles."
        )

class ArticleVoiceForm(forms.Form):
    """Form for article-specific voice settings."""

    voice_id = forms.ChoiceField(
        required=False,
        help_text="Voice for this specific article."
    )

    speed = forms.ChoiceField(
        required=False,
        help_text="Speed for this specific article."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        voice_service = VoiceConfigurationService()

        # Add choices for voice and speed
        self.fields['voice_id'].choices = [('', 'Auto (detect from tone)')] + voice_service.get_available_voices()
        self.fields['speed'].choices = [('', 'Auto (detect from tone)')] + voice_service.get_available_speeds()
```

### Views for Voice Preferences

```python
# In text_to_audio/views.py (additions)

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import UpdateView
from django.urls import reverse_lazy
from django.contrib import messages

from text_to_audio.models import UserVoiceProfile, Article
from text_to_audio.forms import UserVoicePreferenceForm, ArticleVoiceForm
from text_to_audio.services.user_preferences import UserPreferencesService

@login_required
def voice_preferences(request):
    """View for managing user voice preferences."""
    pref_service = UserPreferencesService()

    # Get or create profile
    profile, created = UserVoiceProfile.objects.get_or_create(
        user=request.user
    )

    if request.method == 'POST':
        form = UserVoicePreferenceForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Voice preferences updated successfully.")
            return redirect('voice_preferences')
    else:
        form = UserVoicePreferenceForm(instance=profile)

    return render(request, 'text_to_audio/voice_preferences.html', {
        'form': form,
    })

@login_required
def article_voice_settings(request, article_id):
    """View for managing article-specific voice settings."""
    article = get_object_or_404(Article, id=article_id, feed__user=request.user)
    pref_service = UserPreferencesService()

    if request.method == 'POST':
        form = ArticleVoiceForm(request.POST)
        if form.is_valid():
            voice = form.cleaned_data.get('voice_id')
            speed = form.cleaned_data.get('speed')

            # Save preferences
            pref_service.save_article_preferences(
                article=article,
                voice=voice if voice else None,
                speed=float(speed) if speed else None
            )

            messages.success(request, "Article voice settings updated.")
            return redirect('article_detail', pk=article.id)
    else:
        # Pre-fill form with current settings
        initial_data = {
            'voice_id': article.voice_id or '',
            'speed': article.speed or ''
        }
        form = ArticleVoiceForm(initial=initial_data)

    return render(request, 'text_to_audio/article_voice_settings.html', {
        'form': form,
        'article': article
    })
```

## Implementation Roadmap

### Phase 1: Service Implementation
1. Set up services directory structure
2. Implement ContentAnalysisService
3. Implement VoiceConfigurationService
4. Implement UserPreferencesService
5. Write unit tests for services

### Phase 2: Model Implementation
1. Add fields to Article model
2. Create UserVoiceProfile model
3. Create VoiceMapping model
4. Generate and apply migrations
5. Write model tests

### Phase 3: Task Updates
1. Modify process_article task to use services
2. Update TTS API calls to use voice and speed settings
3. Write task tests

### Phase 4: UI Implementation
1. Create forms for voice preferences
2. Implement views for voice preferences
3. Create templates for voice preferences
4. Update URL configuration
5. Write UI tests

### Phase 5: Final Integration and Testing
1. Populate initial voice mappings
2. Write end-to-end integration tests
3. Create documentation

## Advantages of This Approach

1. **Efficiency**: By using a unified API call for content analysis, we reduce token usage and API costs.

2. **Flexibility**: The service-oriented design allows each component to evolve independently.

3. **User Control**: The preference hierarchy (article > user > AI recommendation > default) gives users full control while providing smart defaults.

4. **Maintainability**: Clean separation of concerns makes the codebase easier to maintain and extend.

5. **Testing**: Each component can be thoroughly unit tested in isolation.

## Next Steps

1. Create a branch for implementation
2. Implement services first, with tests
3. Add models and update the Celery task
4. Implement UI components
5. Conduct thorough testing before merging
