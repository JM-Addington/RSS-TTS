"""Forms for the text_to_audio app.

This module defines forms used for article submission and processing in the
RSS-TTS system.
"""

from django import forms
from django.core.exceptions import ValidationError

from .models import Article


class ArticleSubmissionForm(forms.ModelForm):
    """Form for users to submit new articles."""

    class Meta:
        """Meta options for the ArticleSubmissionForm."""

        model = Article
        fields = ["title", "source_url", "text_content"]
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
