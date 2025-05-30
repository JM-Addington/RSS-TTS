"""Merge migration to resolve conflicts between branches.

This migration merges the following branches:
- Branch 0003_enable_auto_voice_mode
- Branch 0003_set_feeds_to_auto_voice
- Branch 0013_fix_missing_voice_column (adding voice fields)
"""

from django.db import migrations


class Migration(migrations.Migration):
    """Merge migration to resolve conflicting branches."""

    dependencies = [
        ("text_to_audio", "0003_enable_auto_voice_mode"),
        ("text_to_audio", "0003_set_feeds_to_auto_voice"),
        ("text_to_audio", "0013_fix_missing_voice_column"),
    ]

    operations = [
        # No operations needed, just merging migrations
    ]
