"""Tests for Django settings logging configuration."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from django.conf import settings


@pytest.fixture
def clear_logs_dir():
    """Remove the logs directory if it exists, then recreate it after the test."""
    logs_dir = Path(settings.BASE_DIR) / "logs"
    logs_existed = logs_dir.exists()

    if logs_existed:
        # Save the original directory
        temp_dir = tempfile.mkdtemp()
        temp_logs = Path(temp_dir) / "logs_backup"
        shutil.copytree(logs_dir, temp_logs)
        shutil.rmtree(logs_dir)

    yield

    # Clean up and restore original logs if they existed
    if logs_dir.exists():
        shutil.rmtree(logs_dir)

    if logs_existed:
        shutil.copytree(temp_logs, logs_dir)
        shutil.rmtree(temp_dir)


def test_django_logging_handlers():
    """Test that the logging handlers are correctly configured."""
    # Check that django logger has the right handlers
    django_logger = settings.LOGGING["loggers"]["django"]
    assert "console" in django_logger["handlers"]
    assert "django_file" in django_logger["handlers"]

    # Check that the file handlers use our safe handlers
    django_file_handler = settings.LOGGING["handlers"]["django_file"]
    assert "SafeFileHandler" in django_file_handler["class"]


def test_log_file_paths():
    """Test that log file paths are correctly set in settings."""
    base_dir = settings.BASE_DIR

    # Check django.log path
    django_log_path = settings.LOGGING["handlers"]["django_file"]["filename"]
    assert str(base_dir / "logs" / "django.log") in str(django_log_path)

    # Check worker.log path
    worker_log_path = settings.LOGGING["handlers"]["worker_file"]["filename"]
    assert str(base_dir / "logs" / "worker.log") in str(worker_log_path)

    # Check tts_api.log path
    tts_log_path = settings.LOGGING["handlers"]["tts_file"]["filename"]
    assert str(base_dir / "logs" / "tts_api.log") in str(tts_log_path)
