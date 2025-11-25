"""Add Mailgun email ingestion fields to Feed model."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Migration to add inbound_email and mailgun_route_id fields to Feed."""

    dependencies = [
        ("text_to_audio", "0033_alter_openaiusagestats_model_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="feed",
            name="inbound_email",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Email address for sending content to this feed (e.g., happy-river-42@mg.example.com)",
                max_length=255,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="feed",
            name="mailgun_route_id",
            field=models.CharField(
                blank=True,
                help_text="Mailgun route ID for this feed's inbound email",
                max_length=255,
                null=True,
            ),
        ),
    ]
