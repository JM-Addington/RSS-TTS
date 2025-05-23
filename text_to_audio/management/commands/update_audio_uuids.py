"""Management command to update articles with missing audio_uuid values."""

import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from text_to_audio.models import Article


class Command(BaseCommand):
    """Command to update Article objects that have missing audio_uuid values."""

    help = "Updates articles with missing audio_uuid values"

    def handle(self, *args, **options):
        """Execute the command to update article audio_uuid values."""
        # Get all articles that have completed status but no audio_uuid
        articles_without_uuid = Article.objects.filter(
            status=Article.COMPLETED,
            audio_uuid__isnull=True,
        ).select_related("feed")

        self.stdout.write(
            self.style.WARNING(
                f"Found {articles_without_uuid.count()} articles without UUID"
            )
        )

        updated_count = 0
        for article in articles_without_uuid:
            # Generate a new UUID
            article.audio_uuid = uuid.uuid4()

            # Update audio_file_path if it exists and uses the old path format
            if article.audio_file_path:
                # Check if it's using the old ID-based format
                if f"article_{article.pk}.mp3" in article.audio_file_path:
                    old_path = Path(settings.BASE_DIR) / article.audio_file_path
                    if os.path.exists(old_path):
                        # Create new path using UUID
                        new_filename = f"article_{article.audio_uuid}.mp3"
                        new_path = old_path.parent / new_filename

                        try:
                            # Rename the file
                            os.rename(old_path, new_path)

                            # Update the path in the database
                            article.audio_file_path = str(
                                new_path.relative_to(settings.BASE_DIR)
                            )
                            msg = f"Renamed article {article.pk} file to {new_filename}"
                            self.stdout.write(msg)
                        except OSError as e:
                            self.stdout.write(
                                self.style.ERROR(
                                    f"Error renaming file for article {article.pk}: {e}"
                                )
                            )
                            # Keep going, but with the original file path
                            pass

            # Save the article with the new UUID
            article.save(update_fields=["audio_uuid", "audio_file_path"])
            updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Successfully updated {updated_count} articles")
        )
