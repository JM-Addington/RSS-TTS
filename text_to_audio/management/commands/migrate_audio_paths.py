"""Management command to migrate legacy audio files to canonical paths."""

import os
import shutil
import traceback
from pathlib import Path
from typing import Dict, List, Tuple

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from text_to_audio.models import Article


class Command(BaseCommand):
    """Command to migrate audio files from legacy paths to canonical locations."""

    help = "Migrates legacy audio files to canonical path structure: media/audio/{user_id}/{article_id}.mp3"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats = {
            'found': 0,
            'migrated': 0,
            'failed': 0,
            'skipped': 0,
        }
        self.rollback_operations = []

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without actually doing it',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite existing files at canonical locations',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=20,
            help='Number of articles to process in each batch (default: 20)',
        )
        parser.add_argument(
            '--rollback-on-error',
            action='store_true',
            help='Rollback all changes if any error occurs',
        )

    def handle(self, *args, **options):
        """Execute the migration command."""
        dry_run = options['dry_run']
        force = options['force']
        batch_size = options['batch_size']
        rollback_on_error = options['rollback_on_error']

        self.stdout.write("Starting audio path migration...")

        try:
            # Find articles that need migration
            articles_to_migrate = self._find_legacy_articles()
            self.stats['found'] = len(articles_to_migrate)

            if not articles_to_migrate:
                self.stdout.write(self.style.SUCCESS("No articles need migration."))
                return

            self.stdout.write(f"Found {len(articles_to_migrate)} articles to migrate")

            if dry_run:
                self._show_dry_run_preview(articles_to_migrate)
                return

            # Process articles in batches
            self._process_articles_in_batches(
                articles_to_migrate, batch_size, force, rollback_on_error
            )

            # Report final statistics
            self._report_statistics()

        except Exception as e:
            self.stderr.write(f"Migration failed: {e}")
            if rollback_on_error:
                self._rollback_changes()
            raise CommandError(f"Migration failed: {e}")

    def _find_legacy_articles(self) -> List[Article]:
        """Find articles with legacy audio file paths that need migration."""
        legacy_articles = []

        # Find completed articles with audio files that don't use canonical paths
        articles = Article.objects.filter(
            status=Article.COMPLETED,
            audio_file_path__isnull=False
        ).exclude(audio_file_path='').select_related('feed__user')

        for article in articles:
            # Check if it's already using canonical path format
            canonical_relative = os.path.join("audio", str(article.feed.user.id), f"{article.id}.mp3")

            if article.audio_file_path != canonical_relative:
                # This is a legacy path that needs migration
                legacy_articles.append(article)

        return legacy_articles

    def _show_dry_run_preview(self, articles: List[Article]) -> None:
        """Show what would be migrated in dry-run mode."""
        self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        for article in articles:
            legacy_path = os.path.join(settings.MEDIA_ROOT, article.audio_file_path)
            canonical_path = article.get_canonical_audio_path()

            self.stdout.write(f"Would migrate Article {article.id}:")
            self.stdout.write(f"  From: {legacy_path}")
            self.stdout.write(f"  To:   {canonical_path}")

            if os.path.exists(legacy_path):
                self.stdout.write(f"  Status: File exists, ready to migrate")
            else:
                self.stdout.write(f"  Status: Audio file not found")

    def _process_articles_in_batches(
        self, articles: List[Article], batch_size: int, force: bool, rollback_on_error: bool
    ) -> None:
        """Process articles in batches for better performance."""
        total_batches = (len(articles) + batch_size - 1) // batch_size

        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(articles))
            batch = articles[start_idx:end_idx]

            self.stdout.write(f"Processing batch {batch_num + 1}/{total_batches}")

            try:
                if rollback_on_error:
                    with transaction.atomic():
                        self._process_batch(batch, force, rollback_on_error)
                else:
                    self._process_batch(batch, force, rollback_on_error)
            except Exception as e:
                self.stderr.write(f"Error in batch {batch_num + 1}: {e}")
                if rollback_on_error:
                    self.stderr.write("Rolling back changes...")
                    self._rollback_changes()
                    raise

    def _process_batch(self, articles: List[Article], force: bool, rollback_on_error: bool = False) -> None:
        """Process a batch of articles."""
        for article in articles:
            try:
                self._migrate_single_article(article, force)
            except Exception as e:
                self.stderr.write(f"Failed to migrate article {article.id}: {e}")
                self.stats['failed'] += 1
                if rollback_on_error:
                    # Re-raise the exception to trigger rollback
                    raise

    def _migrate_single_article(self, article: Article, force: bool) -> None:
        """Migrate a single article's audio file to canonical location."""
        legacy_path = os.path.join(settings.MEDIA_ROOT, article.audio_file_path)
        canonical_path = article.get_canonical_audio_path()

        # Check if source file exists
        if not os.path.exists(legacy_path):
            self.stderr.write(f"Audio file not found for article {article.id}: {legacy_path}")
            self.stats['failed'] += 1
            return

        # Check if destination already exists
        if os.path.exists(canonical_path) and not force:
            self.stdout.write(f"Canonical file already exists for article {article.id}, skipping")
            self.stats['skipped'] += 1
            return

        try:
            # Ensure canonical directory exists
            article.ensure_canonical_directory_exists()

            # Store original file info for potential rollback
            original_stat = os.stat(legacy_path)

            # Move the file
            shutil.move(legacy_path, canonical_path)

            # Preserve file metadata (timestamps and permissions)
            os.utime(canonical_path, (original_stat.st_atime, original_stat.st_mtime))
            os.chmod(canonical_path, original_stat.st_mode)

            # Update database path
            article.set_canonical_audio_path()
            article.save(update_fields=['audio_file_path'])

            # Track for potential rollback
            self.rollback_operations.append({
                'type': 'move',
                'article_id': article.id,
                'from_path': canonical_path,
                'to_path': legacy_path,
                'old_db_path': article.audio_file_path,
                'new_db_path': os.path.join("audio", str(article.feed.user.id), f"{article.id}.mp3")
            })

            self.stats['migrated'] += 1
            self.stdout.write(f"Successfully migrated article {article.id}")

        except PermissionError as e:
            self.stderr.write(f"Permission denied migrating article {article.id}: {e}")
            self.stats['failed'] += 1
        except Exception as e:
            self.stderr.write(f"Error migrating article {article.id}: {e}")
            self.stderr.write(traceback.format_exc())
            self.stats['failed'] += 1

    def _rollback_changes(self) -> None:
        """Rollback all successful migrations."""
        self.stderr.write("Rolling back changes...")

        for operation in reversed(self.rollback_operations):
            try:
                if operation['type'] == 'move':
                    # Move file back
                    if os.path.exists(operation['from_path']):
                        shutil.move(operation['from_path'], operation['to_path'])

                    # Restore database path
                    article = Article.objects.get(id=operation['article_id'])
                    article.audio_file_path = operation['old_db_path']
                    article.save(update_fields=['audio_file_path'])

            except Exception as rollback_error:
                self.stderr.write(f"Error during rollback for article {operation['article_id']}: {rollback_error}")

    def _report_statistics(self) -> None:
        """Report migration statistics."""
        self.stdout.write("\nMigration completed!")
        self.stdout.write(f"Files found: {self.stats['found']}")
        self.stdout.write(f"{self.stats['migrated']} files migrated successfully")
        self.stdout.write(f"{self.stats['failed']} files failed")
        self.stdout.write(f"{self.stats['skipped']} files skipped")

        if self.stats['failed'] > 0:
            self.stdout.write(self.style.WARNING("Some files failed to migrate. Check error messages above."))
        else:
            self.stdout.write(self.style.SUCCESS("All files migrated successfully!"))
