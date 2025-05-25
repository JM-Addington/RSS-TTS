"""Add voice field to Article model."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Migration to add voice field to Article model."""

    dependencies = [
        ("text_to_audio", "0009_article_summary"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="voice",
            field=models.CharField(
                choices=[
                    ("alloy", "Alloy"),
                    ("echo", "Echo"),
                    ("fable", "Fable"),
                    ("onyx", "Onyx"),
                    ("nova", "Nova"),
                    ("shimmer", "Shimmer"),
                ],
                default="alloy",
                help_text="The voice to use for text-to-speech conversion.",
                max_length=20,
            ),
        ),
    ]
