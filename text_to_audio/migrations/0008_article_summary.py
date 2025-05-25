"""Migration to add summary field to Article model."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add summary field to Article model for AI-generated summaries."""

    dependencies = [
        ("text_to_audio", "0007_openaiusagestats"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="summary",
            field=models.TextField(
                blank=True,
                help_text="AI-generated summary of the article content.",
                null=True,
            ),
        ),
    ]
