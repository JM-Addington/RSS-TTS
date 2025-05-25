from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("text_to_audio", "0007_openaiusagestats"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="summary",
            field=models.TextField(
                blank=True,
                help_text="Summary of the article in 100 words or less.",
            ),
        ),
    ]
