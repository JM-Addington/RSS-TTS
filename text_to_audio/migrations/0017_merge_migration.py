"""Merge migration to resolve conflicts between branches.

This migration merges the following branches:
- Branch 0012_fix_migration_conflicts
- Branch 0015_add_voice_fields (adding voice fields)
- Branch 0016_followedfeed (adding FollowedFeed model)
"""

from django.db import migrations


class Migration(migrations.Migration):
    """Merge migration to resolve conflicting branches."""

    dependencies = [
        ("text_to_audio", "0012_fix_migration_conflicts"),
        ("text_to_audio", "0014_add_voice_genre_templates"),
        ("text_to_audio", "0015_add_voice_fields"),
        ("text_to_audio", "0016_followedfeed"),
    ]

    operations = [
        # No operations needed, just merging migrations
    ]
