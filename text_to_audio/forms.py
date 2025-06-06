"""Forms for the text_to_audio app.

This module defines forms used for article submission and processing in the
RSS-TTS system.
"""

from django import forms
from django.core.exceptions import ValidationError

from .models import Article, Feed, FollowedFeed, UserVoicePreset, UserVoiceProfile
from .services.voice_configuration import VoiceConfigurationService


class ArticleSubmissionForm(forms.ModelForm):
    """Form for users to submit new articles."""

    voice_id = forms.ChoiceField(required=False, help_text="Voice for this article.")

    speed = forms.ChoiceField(required=False, help_text="Speed for this article.")

    voice_preset = forms.ChoiceField(
        required=False, help_text="Or select a saved voice preset."
    )

    document_file = forms.FileField(
        required=False,
        help_text="Upload a PDF or HTML file (max 10MB). Provide either a URL, text content, or a file - not multiple."
    )

    class Meta:
        """Meta options for the ArticleSubmissionForm."""

        model = Article
        fields = ["title", "source_url", "text_content", "document_file", "voice_id", "speed"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": "Optional (a title will be generated automatically)"
                }
            ),
            "text_content": forms.Textarea(
                attrs={
                    "rows": 8,
                    "placeholder": "Enter article text here (optional if URL provided)",
                }
            ),
            "source_url": forms.URLInput(
                attrs={"placeholder": "https://example.com/article (optional)"}
            ),
            "voice": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        """Initialize the form with dynamic choices for voice and speed."""
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        voice_service = VoiceConfigurationService()

        # Set choices for voice and speed fields
        voice_choices = [
            ("", "Auto (detect from tone)")
        ] + voice_service.get_available_voices()
        speed_choices = [
            ("", "Auto (detect from tone)")
        ] + voice_service.get_available_speeds()

        from typing import cast

        voice_field = cast(forms.ChoiceField, self.fields["voice_id"])
        voice_field.choices = voice_choices
        speed_field = cast(forms.ChoiceField, self.fields["speed"])
        speed_field.choices = speed_choices

        # Set user presets if user is provided
        preset_choices = [("", "Don't use a preset")]
        if user and user.is_authenticated:
            preset_choices += voice_service.get_user_presets(user)

        preset_field = cast(forms.ChoiceField, self.fields["voice_preset"])
        preset_field.choices = preset_choices

    def clean(self):
        """Validate that either source_url or text_content is provided."""
        cleaned_data = super().clean()
        if cleaned_data is None:
            return cleaned_data
        assert cleaned_data is not None

        source_url = cleaned_data.get("source_url", "")
        text_content = cleaned_data.get("text_content", "")
        document_file = cleaned_data.get("document_file")

        # Ensure that exactly one of source_url, text_content, or document_file is provided.
        provided_fields = [source_url, text_content, document_file]
        if sum(bool(field) for field in provided_fields) != 1:
            raise ValidationError(
                "You must provide exactly one of: a URL, text content, or a document file."
            )

        if document_file:
            # Validate file type
            content_type = document_file.content_type
            if content_type not in ["application/pdf", "text/html"]:
                raise ValidationError(
                    "Invalid file type. Only PDF and HTML files are allowed."
                )

            # Validate file size (10MB limit)
            MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB in bytes
            if document_file.size > MAX_UPLOAD_SIZE:
                raise ValidationError(
                    f"File is too large. Maximum file size is 10MB. Your file is {document_file.size / (1024 * 1024):.1f}MB."
                )

        # Enforce 30,000-word limit for pasted text content
        if text_content:
            word_count = len(text_content.split())
            if word_count > 30000:
                raise ValidationError(
                    f"Text content is too long ({word_count:,} words). "
                    f"Please limit to 30,000 words or less. "
                    f"Consider using a URL instead for longer articles."
                )

        voice_preset = cleaned_data.get("voice_preset")
        voice_id = cleaned_data.get("voice_id")
        speed = cleaned_data.get("speed")

        if voice_preset and (voice_id or speed):
            self.add_error(
                "voice_preset",
                (
                    "You cannot select both a voice preset and "
                    "individual voice/speed settings."
                ),
            )

        return cleaned_data

    def clean_speed(self) -> float | None:
        """Convert blank speed values to ``None``."""
        value = self.cleaned_data.get("speed")
        if value in ("", None):
            return None
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValidationError("Invalid speed value")


class UserVoicePreferenceForm(forms.ModelForm):
    """Form for user voice preferences."""

    class Meta:
        """Meta options for the UserVoicePreferenceForm."""

        model = UserVoiceProfile
        fields = ["preferred_voice", "preferred_speed"]

    def __init__(self, *args, **kwargs):
        """Initialize the form with dynamic choices for voice and speed."""
        super().__init__(*args, **kwargs)
        voice_service = VoiceConfigurationService()

        # Replace the fields with ChoiceFields
        voice_choices = [
            ("", "Auto (detect from tone)")
        ] + voice_service.get_available_voices()
        speed_choices = [
            ("", "Auto (detect from tone)")
        ] + voice_service.get_available_speeds()

        self.fields["preferred_voice"] = forms.ChoiceField(
            choices=voice_choices,
            required=False,
            help_text="Your preferred voice for all articles.",
        )

        self.fields["preferred_speed"] = forms.ChoiceField(
            choices=speed_choices,
            required=False,
            help_text="Your preferred speaking speed for all articles.",
        )

    def clean_preferred_speed(self) -> float | None:
        """Convert blank speed values to ``None`` and return float."""
        value = self.cleaned_data.get("preferred_speed")
        if value in ("", None):
            return None
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValidationError("Invalid speed value")


class ArticleVoiceForm(forms.Form):
    """Form for article-specific voice settings."""

    voice_id = forms.ChoiceField(
        required=False, help_text="Voice for this specific article."
    )

    speed = forms.ChoiceField(
        required=False, help_text="Speed for this specific article."
    )

    voice_preset = forms.ChoiceField(
        required=False, help_text="Or select a saved voice preset."
    )

    def __init__(self, *args, user=None, **kwargs):
        """Initialize the form with dynamic choices for voice and speed."""
        super().__init__(*args, **kwargs)
        voice_service = VoiceConfigurationService()

        # Set choices for voice and speed fields
        voice_choices = [
            ("", "Auto (detect from tone)")
        ] + voice_service.get_available_voices()
        speed_choices = [
            ("", "Auto (detect from tone)")
        ] + voice_service.get_available_speeds()

        # Need to check if field exists and has a choices attribute before setting
        if "voice_id" in self.fields:
            from typing import cast

            voice_field = cast(forms.ChoiceField, self.fields["voice_id"])
            voice_field.choices = voice_choices

        if "speed" in self.fields:
            from typing import cast

            speed_field = cast(forms.ChoiceField, self.fields["speed"])
            speed_field.choices = speed_choices

        # Set user presets if user is provided
        preset_choices = [("", "Don't use a preset")]
        if user and user.is_authenticated:
            preset_choices += voice_service.get_user_presets(user)

        if "voice_preset" in self.fields and hasattr(
            self.fields["voice_preset"], "choices"
        ):
            self.fields["voice_preset"].choices = preset_choices

    def clean(self):
        """Validate that preset and direct settings aren't both set."""
        cleaned_data = super().clean()
        assert cleaned_data is not None

        voice_preset = cleaned_data.get("voice_preset")
        voice_id = cleaned_data.get("voice_id")
        speed = cleaned_data.get("speed")

        if voice_preset and (voice_id or speed):
            self.add_error(
                "voice_preset",
                (
                    "You cannot select both a voice preset and "
                    "individual voice/speed settings."
                ),
            )

        return cleaned_data

    def clean_speed(self) -> float | None:
        """Convert blank speed values to ``None``."""
        value = self.cleaned_data.get("speed")
        if value in ("", None):
            return None
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValidationError("Invalid speed value")


class ArticleDetailForm(forms.ModelForm):
    """Form for editing article details when regenerating."""

    class Meta:
        """Meta options for the ArticleDetailForm."""

        model = Article
        fields = ["title", "text_content", "summary", "voice_id", "speed"]
        widgets = {
            "text_content": forms.Textarea(attrs={"rows": 8}),
            "summary": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        """Initialize form with dynamic voice options."""
        super().__init__(*args, **kwargs)
        voice_service = VoiceConfigurationService()
        voice_choices = [
            ("", "Auto (detect from tone)")
        ] + voice_service.get_available_voices()
        speed_choices = [
            ("", "Auto (detect from tone)")
        ] + voice_service.get_available_speeds()
        self.fields["voice_id"] = forms.ChoiceField(
            choices=voice_choices,
            required=False,
            help_text="Voice for this article.",
        )
        self.fields["speed"] = forms.ChoiceField(
            choices=speed_choices,
            required=False,
            help_text="Speed for this article.",
        )

    def clean_speed(self) -> float | None:
        """Convert blank speed values to ``None``."""
        value = self.cleaned_data.get("speed")
        if value in ("", None):
            return None
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValidationError("Invalid speed value")


class VoicePresetForm(forms.ModelForm):
    """Form for creating and editing voice presets."""

    class Meta:
        """Meta options for the VoicePresetForm."""

        model = UserVoicePreset
        fields = [
            "name",
            "voice_id",
            "speed",
            "prompt",
            "sample_input",
            "description",
        ]

    def __init__(self, *args, **kwargs):
        """Initialize the form with dynamic choices for voice and speed."""
        super().__init__(*args, **kwargs)
        voice_service = VoiceConfigurationService()

        # Set choices for voice and speed fields
        self.fields["voice_id"] = forms.ChoiceField(
            choices=voice_service.get_available_voices(),
            required=True,
            help_text="Voice for this preset.",
        )

        self.fields["speed"] = forms.ChoiceField(
            choices=voice_service.get_available_speeds(),
            required=True,
            help_text="Speed for this preset.",
        )

        # Add placeholder for name field
        self.fields["name"].widget.attrs.update(
            {"placeholder": "E.g., News Reader, Storyteller, etc."}
        )

        # Add placeholder for description field
        self.fields["description"].widget = forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Optional description of this voice preset.",
            }
        )

        self.fields["prompt"].widget = forms.Textarea(
            attrs={"rows": 3, "placeholder": "Style prompt (optional)"}
        )
        self.fields["sample_input"].widget = forms.Textarea(
            attrs={"rows": 3, "placeholder": "Sample text used for design (optional)"}
        )


class FeedForm(forms.ModelForm):
    """Form for creating and editing feeds with default voice preset."""

    default_voice_preset = forms.ModelChoiceField(
        queryset=UserVoicePreset.objects.none(),
        required=False,
        help_text="Preset applied to new articles in this feed by default.",
    )

    # Add voice_mode field to enable multi-voice functionality
    voice_mode = forms.ChoiceField(
        required=True,
        help_text="Select how voices are generated for articles in this feed.",
    )

    class Meta:
        """Meta options for the FeedForm."""

        model = Feed
        fields = ["name", "default_voice_preset", "voice_mode"]

    def __init__(self, *args, user=None, **kwargs):
        """Initialize form and limit presets to the current user."""
        super().__init__(*args, **kwargs)

        # Configure voice mode choices
        from typing import cast

        voice_service = VoiceConfigurationService()

        # Cast field to ChoiceField type to make mypy happy
        voice_mode_field = cast(forms.ChoiceField, self.fields["voice_mode"])
        voice_mode_field.choices = voice_service.get_available_voice_modes()
        voice_mode_field.initial = Feed.VOICE_MODE_AUTO
        self.fields["voice_mode"].help_text = (
            "Auto-generated voice enables multi-voice narration with different voices for "
            "quotes, characters, and distinct sections."
        )

        # Configure preset field
        if user and user.is_authenticated:
            from typing import cast

            preset_field = cast(
                forms.ModelChoiceField, self.fields["default_voice_preset"]
            )
            preset_field.queryset = UserVoicePreset.objects.filter(user=user).order_by(
                "name"
            )


class FollowedFeedForm(forms.ModelForm):
    """Form for creating and editing followed RSS feeds."""

    class Meta:
        """Meta options for the FollowedFeedForm."""

        model = FollowedFeed
        fields = ["url", "destination_feed", "is_active"]
        widgets = {
            "url": forms.URLInput(
                attrs={"placeholder": "https://example.com/rss_feed"}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        """Initialize form and limit destination feeds to the current user.

        Disables the form when user has no feeds and displays a helpful message.
        """
        super().__init__(*args, **kwargs)

        if user and user.is_authenticated:
            # Filter destination feeds to only show the user's feeds
            feeds = Feed.objects.filter(user=user).order_by("name")

            # Get the destination_feed field
            from typing import cast

            from django import forms

            # Cast to ModelChoiceField to make mypy happy
            dest_field = cast(forms.ModelChoiceField, self.fields["destination_feed"])
            dest_field.queryset = feeds

            # If the user has no feeds, disable the field and show a helpful message
            if feeds.count() == 0:
                self.fields["destination_feed"].widget.attrs["disabled"] = True
                self.fields["destination_feed"].help_text = (
                    "You don't have any feeds yet."
                )
