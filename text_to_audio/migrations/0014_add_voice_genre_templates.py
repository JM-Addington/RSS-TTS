"""Add VoiceGenreTemplate model and auto-voice configuration fields."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Migration for adding the VoiceGenreTemplate model and related fields."""

    dependencies = [
        ("text_to_audio", "0013_fix_missing_voice_column"),
    ]

    operations = [
        migrations.CreateModel(
            name="VoiceGenreTemplate",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "genre",
                    models.CharField(
                        help_text="Genre category name", max_length=50, unique=True
                    ),
                ),
                (
                    "voice_id",
                    models.CharField(
                        help_text="Voice ID to use for this genre", max_length=50
                    ),
                ),
                (
                    "speed",
                    models.FloatField(
                        default=1.0, help_text="Speed multiplier to use for this genre"
                    ),
                ),
                (
                    "affect",
                    models.CharField(
                        blank=True,
                        help_text="Emotional affect for the voice",
                        max_length=50,
                    ),
                ),
                (
                    "tone",
                    models.CharField(
                        blank=True,
                        help_text="Tone descriptor for the voice",
                        max_length=100,
                    ),
                ),
                (
                    "pacing",
                    models.CharField(
                        blank=True,
                        help_text="Pacing style for the voice",
                        max_length=50,
                    ),
                ),
                (
                    "pitch_variation",
                    models.CharField(
                        blank=True, help_text="Amount of pitch variation", max_length=50
                    ),
                ),
                (
                    "speaking_style",
                    models.TextField(
                        blank=True,
                        help_text="Detailed description of the speaking style",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True, help_text="Description of this genre category"
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True, help_text="Whether this template is active"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, help_text="When the template was created"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, help_text="When the template was last updated"
                    ),
                ),
            ],
            options={
                "ordering": ["genre"],
            },
        ),
        # Add new fields to UserVoicePreset
        migrations.AddField(
            model_name="uservoicepreset",
            name="affect",
            field=models.CharField(
                blank=True,
                help_text="Emotional affect for the voice",
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="uservoicepreset",
            name="pacing",
            field=models.CharField(
                blank=True,
                help_text="Pacing style for the voice",
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="uservoicepreset",
            name="pitch_variation",
            field=models.CharField(
                blank=True,
                help_text="Amount of pitch variation",
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="uservoicepreset",
            name="speaking_style",
            field=models.TextField(
                blank=True,
                help_text="Detailed description of the speaking style",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="uservoicepreset",
            name="tone",
            field=models.CharField(
                blank=True,
                help_text="Tone descriptor for the voice",
                max_length=100,
                null=True,
            ),
        ),
        # Add genre and other fields to Article
        migrations.AddField(
            model_name="article",
            name="detected_genre",
            field=models.CharField(
                blank=True,
                help_text="AI-detected genre of the article content",
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="article",
            name="voice_parameters",
            field=models.JSONField(
                blank=True,
                help_text="Detailed voice parameters for text-to-speech conversion",
                null=True,
            ),
        ),
        # Add feed voice configuration preference
        migrations.AddField(
            model_name="feed",
            name="voice_mode",
            field=models.CharField(
                choices=[
                    ("single_default", "Single voice from defaults"),
                    ("single_custom", "Single voice from custom preset"),
                    ("auto", "Auto-generated voice"),
                ],
                default="single_default",
                help_text="Voice mode preference for this feed",
                max_length=20,
            ),
        ),
    ]
