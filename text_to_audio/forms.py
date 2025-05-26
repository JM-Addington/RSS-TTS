"""Forms for the text_to_audio app.

This module defines forms used for article submission and processing in the
RSS-TTS system.
"""

from django import forms
from django.core.exceptions import ValidationError

from .models import Article, Feed, UserVoicePreset, UserVoiceProfile
from .services.voice_configuration import VoiceConfigurationService


class ArticleSubmissionForm(forms.ModelForm):
    """Form for users to submit new articles."""

    voice_id = forms.ChoiceField(required=False, help_text="Voice for this article.")

    speed = forms.ChoiceField(required=False, help_text="Speed for this article.")

    voice_preset = forms.ChoiceField(
        required=False, help_text="Or select a saved voice preset."
    )

    class Meta:
        """Meta options for the ArticleSubmissionForm."""

        model = Article
        fields = ["title", "source_url", "text_content", "voice_id", "speed"]
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

        self.fields["voice_id"].choices = voice_choices
        self.fields["speed"].choices = speed_choices

        # Set user presets if user is provided
        preset_choices = [("", "Don't use a preset")]
        if user and user.is_authenticated:
            preset_choices += voice_service.get_user_presets(user)

        self.fields["voice_preset"].choices = preset_choices

    def clean(self):
        """Validate that either source_url or text_content is provided."""
        cleaned_data = super().clean()
        if cleaned_data is None:
            return cleaned_data

        source_url = cleaned_data.get("source_url", "")
        text_content = cleaned_data.get("text_content", "")

        if not source_url and not text_content:
            raise ValidationError("You must provide either a URL or text content.")

        voice_preset = cleaned_data.get("voice_preset")
        voice_id = cleaned_data.get("voice_id")
        speed = cleaned_data.get("speed")

        if voice_preset and (voice_id or speed):
            self.add_error(
                "voice_preset",
                "You cannot select both a voice preset and individual voice/speed settings.",
            )

        return cleaned_data


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
        if "voice_id" in self.fields and hasattr(self.fields["voice_id"], "choices"):
            self.fields["voice_id"].choices = voice_choices
        if "speed" in self.fields and hasattr(self.fields["speed"], "choices"):
            self.fields["speed"].choices = speed_choices

        # Set user presets if user is provided
        preset_choices = [("", "Don't use a preset")]
        if user and user.is_authenticated:
            preset_choices += voice_service.get_user_presets(user)

        if "voice_preset" in self.fields and hasattr(
            self.fields["voice_preset"], "choices"
        ):
            self.fields["voice_preset"].choices = preset_choices

    def clean(self):
        """Validate that voice preset and direct voice/speed settings are not both set."""
        cleaned_data = super().clean()

        voice_preset = cleaned_data.get("voice_preset")
        voice_id = cleaned_data.get("voice_id")
        speed = cleaned_data.get("speed")

        if voice_preset and (voice_id or speed):
            self.add_error(
                "voice_preset",
                "You cannot select both a voice preset and individual voice/speed settings.",
            )

        return cleaned_data


class ArticleDetailForm(forms.ModelForm):
    """Form for editing article details when regenerating."""

    class Meta:
        model = Article
        fields = ["title", "text_content", "summary", "voice_id", "speed"]
        widgets = {
            "text_content": forms.Textarea(attrs={"rows": 8}),
            "summary": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
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

    class Meta:
        model = Feed
        fields = ["name", "default_voice_preset"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.is_authenticated:
            self.fields["default_voice_preset"].queryset = (
                UserVoicePreset.objects.filter(user=user).order_by("name")
            )
