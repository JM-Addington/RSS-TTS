"""
Management command to migrate environment variables to database configuration.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from appconfig.models import GlobalConfig


class Command(BaseCommand):
    help = "Migrate environment variables to database configuration"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be migrated without making changes",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing database values with environment variables",
        )

    def get_env_mappings(self):
        """Return mapping of field names to environment variables and defaults."""
        return {
            "openai_api_key": ("OPENAI_API_KEY", None),
            "openai_title_model": ("OPENAI_TITLE_MODEL", "gpt-4o-mini"),
            "openai_tts_model": ("OPENAI_TTS_MODEL", "tts-1-hd"),
            "openai_tts_voice": ("OPENAI_TTS_VOICE", "alloy"),
            "openai_tts_response_format": ("OPENAI_TTS_RESPONSE_FORMAT", "wav"),
            "openai_analysis_model": ("OPENAI_ANALYSIS_MODEL", "gpt-4.1"),
            "openai_classification_model": (
                "OPENAI_CLASSIFICATION_MODEL",
                "gpt-4o-mini",
            ),
            "use_gpt_for_url_extraction": ("USE_GPT_FOR_URL_EXTRACTION", True),
            "max_analysis_words": ("MAX_ANALYSIS_WORDS", 8000),
            "firecrawl_api_key": ("FIRECRAWL_API_KEY", None),
            "use_firecrawl_by_default": ("USE_FIRECRAWL_BY_DEFAULT", False),
            "enable_chunk_tone_llm": ("ENABLE_CHUNK_TONE_LLM", True),
            "default_tts_provider": ("DEFAULT_TTS_PROVIDER", "openai"),
            "podcast_image_url": ("PODCAST_IMAGE_URL", None),
            "site_url": ("SITE_URL", "http://localhost:8000"),
            "rss_external_hostname": ("RSS_EXTERNAL_HOSTNAME", None),
        }

    def process_environment_value(self, env_value, default):
        """Convert environment value to proper type."""
        if isinstance(default, bool) and isinstance(env_value, str):
            return env_value.lower() in ("true", "1", "yes", "on")
        elif isinstance(default, int) and isinstance(env_value, str):
            try:
                return int(env_value)
            except ValueError:
                return None
        return env_value

    def analyze_migrations(self, config, force):
        """Analyze what migrations are needed."""
        env_mappings = self.get_env_mappings()
        migrations = []
        conflicts = []
        skipped = []

        for field_name, (env_var, default) in env_mappings.items():
            env_value = getattr(settings, env_var, default)
            db_value = getattr(config, field_name)

            # Skip if no environment value or it's the default
            if env_value is None or env_value == default:
                continue

            # Convert types for comparison
            processed_env_value = self.process_environment_value(env_value, default)
            if processed_env_value is None:
                self.stdout.write(
                    self.style.ERROR(f"❌ Invalid value for {env_var}: {env_value}")
                )
                continue

            # Check for conflicts
            if db_value and str(db_value) != str(processed_env_value):
                if force:
                    conflicts.append(
                        (field_name, env_var, db_value, processed_env_value)
                    )
                else:
                    skipped.append((field_name, env_var, db_value, processed_env_value))
                    continue

            # Only migrate if environment variable has a non-default value
            if processed_env_value != default:
                migrations.append((field_name, env_var, processed_env_value))

        return migrations, conflicts, skipped

    def display_migration_plan(self, migrations, conflicts, skipped):
        """Display what will be migrated."""
        if migrations:
            self.stdout.write(self.style.SUCCESS("📝 Settings to migrate:"))
            for field_name, env_var, value in migrations:
                human_name = field_name.replace("_", " ").title()
                self.stdout.write(f"  • {human_name}: {env_var} = {value}")

        if conflicts:
            self.stdout.write(self.style.WARNING("⚠️  Conflicts (will overwrite):"))
            for field_name, env_var, old_value, new_value in conflicts:
                human_name = field_name.replace("_", " ").title()
                self.stdout.write(
                    f"  • {human_name}: {old_value} → {new_value} (from {env_var})"
                )

        if skipped:
            self.stdout.write(
                self.style.ERROR("🚫 Skipped conflicts (use --force to override):")
            )
            for field_name, env_var, old_value, new_value in skipped:
                human_name = field_name.replace("_", " ").title()
                self.stdout.write(
                    f"  • {human_name}: DB has '{old_value}', ENV has '{new_value}' (from {env_var})"
                )

    def apply_migrations(self, config, migrations, conflicts):
        """Apply the migration changes."""
        for field_name, env_var, value in migrations:
            setattr(config, field_name, value)

        for field_name, env_var, old_value, new_value in conflicts:
            setattr(config, field_name, new_value)

        if migrations or conflicts:
            config.save()
            return len(migrations) + len(conflicts)
        return 0

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]

        self.stdout.write(self.style.SUCCESS("🔄 Environment Variable Migration Tool"))
        self.stdout.write("")

        # Get or create config
        config, created = GlobalConfig.objects.get_or_create()
        if created:
            self.stdout.write(
                self.style.SUCCESS("✅ Created new GlobalConfig instance")
            )

        # Analyze what needs to be migrated
        migrations, conflicts, skipped = self.analyze_migrations(config, force)

        # Display migration plan
        self.display_migration_plan(migrations, conflicts, skipped)

        if not migrations and not conflicts:
            self.stdout.write(
                self.style.SUCCESS("✅ No environment variables to migrate")
            )
            return

        if dry_run:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "🔍 DRY RUN - No changes made. Remove --dry-run to apply."
                )
            )
            return

        # Apply migrations
        total_changed = self.apply_migrations(config, migrations, conflicts)
        if total_changed > 0:
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Successfully migrated {total_changed} settings!"
                )
            )

            if skipped:
                self.stdout.write("")
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠️  {len(skipped)} settings were skipped due to conflicts. "
                        "Use --force to override database values."
                    )
                )
