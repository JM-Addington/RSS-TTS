# Generated manually for cost tracking feature

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("text_to_audio", "0024_alter_article_title"),
    ]

    operations = [
        # Add model_name field
        migrations.AddField(
            model_name="openaiusagestats",
            name="model_name",
            field=models.CharField(
                max_length=100,
                default="gpt-4o-mini",
                blank=True,
                help_text="The OpenAI model used for this operation.",
            ),
        ),
        # Add operation_type field
        migrations.AddField(
            model_name="openaiusagestats",
            name="operation_type",
            field=models.CharField(
                max_length=10,
                choices=[("LLM", "Language Model"), ("TTS", "Text-to-Speech")],
                default="LLM",
                help_text="Type of operation performed.",
            ),
        ),
        # Add input_tokens field
        migrations.AddField(
            model_name="openaiusagestats",
            name="input_tokens",
            field=models.IntegerField(
                null=True,
                blank=True,
                help_text="Number of input tokens used.",
            ),
        ),
        # Add output_tokens field
        migrations.AddField(
            model_name="openaiusagestats",
            name="output_tokens",
            field=models.IntegerField(
                null=True,
                blank=True,
                help_text="Number of output tokens generated.",
            ),
        ),
        # Add estimated_cost field
        migrations.AddField(
            model_name="openaiusagestats",
            name="estimated_cost",
            field=models.DecimalField(
                max_digits=10,
                decimal_places=6,
                null=True,
                blank=True,
                help_text="Estimated cost in USD for this operation.",
            ),
        ),
        # Add indexes for better query performance
        migrations.AddIndex(
            model_name="openaiusagestats",
            index=models.Index(
                fields=["user", "request_timestamp"],
                name="text_to_aud_user_cost_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="openaiusagestats",
            index=models.Index(
                fields=["operation_type"],
                name="text_to_aud_op_type_idx",
            ),
        ),
    ]
