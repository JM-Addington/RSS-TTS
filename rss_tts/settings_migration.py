"""
Settings for migration reset.
"""

from .settings import *  # noqa

# Rename the original migration directory
MIGRATION_MODULES = {
    "text_to_audio": "text_to_audio.migrations_new",
}
