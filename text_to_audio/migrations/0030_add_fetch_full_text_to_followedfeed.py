from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("text_to_audio", "0027_alter_openaiusagestats_options_and_more"),
        ("text_to_audio", "0029_add_model_name_to_openaiusagestats"),
    ]

    operations = [
        migrations.AddField(
            model_name="followedfeed",
            name="fetch_full_text",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Fetch the full article text from the entry's URL instead of "
                    "using the feed-provided summary."
                ),
            ),
        ),
    ]
