from django import forms

from .models import Article


class ArticleSubmissionForm(forms.ModelForm):
    """Form for users to submit new articles."""

    class Meta:
        model = Article
        fields = ["title", "source_url", "text_content"]
