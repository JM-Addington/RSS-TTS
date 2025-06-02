"""Management command to backfill costs for existing OpenAI usage records."""

import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from text_to_audio.models import OpenAIUsageStats

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Backfill cost estimates for existing OpenAI usage records."""

    help = 'Calculate and save cost estimates for existing OpenAI usage records'

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of records to process in each batch (default: 100)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes'
        )

    def handle(self, *args, **options):
        """Execute the command."""
        batch_size = options['batch_size']
        dry_run = options['dry_run']

        # Find records without cost estimates
        records_without_cost = OpenAIUsageStats.objects.filter(estimated_cost__isnull=True)
        total_count = records_without_cost.count()

        if total_count == 0:
            self.stdout.write(
                self.style.SUCCESS('No usage records need cost backfilling.')
            )
            return

        self.stdout.write(
            f'Found {total_count} usage records without cost estimates.'
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN: No changes will be made.')
            )

        processed = 0
        updated = 0
        failed = 0

        # Process records in batches
        while processed < total_count:
            with transaction.atomic():
                # Get next batch
                batch = list(
                    records_without_cost[processed:processed + batch_size]
                )

                for record in batch:
                    try:
                        if not dry_run:
                            # Calculate and save cost
                            record.calculate_cost()
                            if record.estimated_cost:
                                updated += 1
                            else:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'No cost calculated for record {record.id} '
                                        f'(operation_type: {record.operation_type})'
                                    )
                                )
                        else:
                            # Dry run - just show what would be updated
                            from text_to_audio.services.cost_calculator import (
                                estimate_cost_from_total_tokens
                            )
                            if record.operation_type == 'LLM' and record.tokens_used:
                                estimated_cost = estimate_cost_from_total_tokens(
                                    record.model_name,
                                    record.tokens_used
                                )
                                self.stdout.write(
                                    f'Would update record {record.id}: '
                                    f'{record.tokens_used} tokens → ${estimated_cost}'
                                )
                                updated += 1

                        processed += 1

                    except Exception as e:
                        failed += 1
                        logger.error(f'Failed to process record {record.id}: {e}')
                        self.stdout.write(
                            self.style.ERROR(
                                f'Failed to process record {record.id}: {e}'
                            )
                        )

                # Progress update
                if processed % (batch_size * 10) == 0 or processed >= total_count:
                    self.stdout.write(
                        f'Processed {processed}/{total_count} records... '
                        f'({updated} updated, {failed} failed)'
                    )

        # Final summary
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'DRY RUN COMPLETE: Would update {updated} records '
                    f'({failed} failures)'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'BACKFILL COMPLETE: Updated {updated} records '
                    f'({failed} failures)'
                )
            )

            if updated > 0:
                # Show some statistics
                from django.db.models import Sum, Count
                stats = OpenAIUsageStats.objects.aggregate(
                    total_cost=Sum('estimated_cost'),
                    total_records=Count('id'),
                    records_with_cost=Count('estimated_cost')
                )

                self.stdout.write(
                    f'Database now contains {stats["records_with_cost"]} records '
                    f'with cost estimates out of {stats["total_records"]} total. '
                    f'Total estimated cost: ${stats["total_cost"] or 0}'
                )
