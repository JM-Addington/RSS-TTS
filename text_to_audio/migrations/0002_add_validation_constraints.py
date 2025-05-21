from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("text_to_audio", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="article",
            name="feed",
            field=models.ForeignKey(
                help_text="The feed this article belongs to.",
                null=False,
                blank=False,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="articles",
                to="text_to_audio.feed",
            ),
        ),
        migrations.AlterField(
            model_name="article",
            name="status",
            field=models.CharField(
                choices=[
                    ("PROCESSING", "Processing"),
                    ("COMPLETED", "Completed"),
                    ("FAILED", "Failed"),
                ],
                default="PROCESSING",
                help_text="The current status of the article.",
                max_length=20,
                null=False,
                blank=False,
            ),
        ),
        migrations.AlterField(
            model_name="article",
            name="text_content",
            field=models.TextField(
                help_text="The text content of the article.",
                null=False,
                blank=False,
            ),
        ),
        migrations.AlterField(
            model_name="article",
            name="title",
            field=models.CharField(
                help_text="The title of the article.",
                max_length=255,
                null=False,
                blank=False,
            ),
        ),
        migrations.AlterField(
            model_name="feed",
            name="name",
            field=models.CharField(
                help_text="The name of the feed.",
                max_length=100,
                null=False,
                blank=False,
            ),
        ),
        migrations.AlterField(
            model_name="feed",
            name="token",
            field=models.UUIDField(
                default="uuid.uuid4",
                help_text="Unique token for accessing the feed.",
                unique=True,
                null=False,
                blank=False,
            ),
        ),
        migrations.AlterField(
            model_name="feed",
            name="user",
            field=models.ForeignKey(
                help_text="The user who owns this feed.",
                null=False,
                blank=False,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="feeds",
                to="auth.user",
            ),
        ),
    ]