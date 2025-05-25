"""Forms for the text_to_audio app.

This module defines forms used for article submission and processing in the
RSS-TTS system.
"""

from django import forms
from django.core.exceptions import ValidationError

from .models import Article, UserVoiceProfile
from .services.voice_configuration import VoiceConfigurationService


class ArticleSubmissionForm(forms.ModelForm):
    """Form for users to submit new articles."""

    voice_id = forms.ChoiceField(
        required=False, help_text="Voice for this specific article."
    )

    speed = forms.ChoiceField(
        required=False, help_text="Speed for this specific article."
    )

    class Meta:
        """Meta options for the ArticleSubmissionForm."""

        model = Article
        fields = ["title", "source_url", "text_content", "voice_id", "speed"]
        widgets = {
            "title": forms.TextInput(
                attrs={"placeholder": "Optional if URL is provided"}
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
        }

    def __init__(self, *args, **kwargs):
        """Initialize the form with dynamic choices for voice and speed."""
        super().__init__(*args, **kwargs)
        voice_service = VoiceConfigurationService()

        voice_choices = [
            ("", "Auto (detect from tone)")
        ] + voice_service.get_available_voices()
        speed_choices = [
            ("", "Auto (detect from tone)")
        ] + voice_service.get_available_speeds()

        if "voice_id" in self.fields:
            self.fields["voice_id"].choices = voice_choices
        if "speed" in self.fields:
            self.fields["speed"].choices = speed_choices

    def clean(self):
        """Validate that either source_url or text_content is provided."""
        cleaned_data = super().clean()
        if cleaned_data is None:
            return cleaned_data

        source_url = cleaned_data.get("source_url", "")
        text_content = cleaned_data.get("text_content", "")

        if not source_url and not text_content:
            raise ValidationError("You must provide either a URL or text content.")

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

    def __init__(self, *args, **kwargs):
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
