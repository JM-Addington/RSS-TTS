"""Tests for the logging setup functionality."""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from text_to_audio.services.logging_setup import (
    SafeFileHandler,
    SafeRotatingFileHandler,
    configure_logging,
)


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for log files."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Clean up
    shutil.rmtree(temp_dir)


def test_safe_file_handler_creates_directory(temp_log_dir):
    """Test that SafeFileHandler creates the log directory if it doesn't exist."""
    # Create a subdirectory path that doesn't exist
    log_dir = os.path.join(temp_log_dir, "logs", "subdir")
    log_file = os.path.join(log_dir, "test.log")

    # Directory shouldn't exist yet
    assert not os.path.exists(log_dir)

    # Creating the handler should create the directory
    handler = SafeFileHandler(log_file)
    assert os.path.exists(log_dir)

    # Clean up
    handler.close()


def test_safe_rotating_file_handler_creates_directory(temp_log_dir):
    """Test that SafeRotatingFileHandler creates the log directory if it doesn't exist."""
    # Create a subdirectory path that doesn't exist
    log_dir = os.path.join(temp_log_dir, "logs", "subdir")
    log_file = os.path.join(log_dir, "test.log")

    # Directory shouldn't exist yet
    assert not os.path.exists(log_dir)

    # Creating the handler should create the directory
    handler = SafeRotatingFileHandler(log_file, maxBytes=1024, backupCount=3)
    assert os.path.exists(log_dir)

    # Clean up
    handler.close()


def test_configure_logging():
    """Test that configure_logging correctly updates the logging configuration."""
    # Use a temporary directory for the base_dir
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)

        # Create a sample logging config
        logging_config = {
            "version": 1,
            "handlers": {
                "file1": {
                    "class": "logging.FileHandler",
                    "filename": base_dir / "logs" / "file1.log",
                },
                "file2": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": base_dir / "logs" / "file2.log",
                },
                "console": {
                    "class": "logging.StreamHandler",
                },
            },
        }

        # Configure logging
        updated_config = configure_logging(logging_config, base_dir)

        # Check that FileHandler has been replaced with SafeFileHandler
        assert (
            updated_config["handlers"]["file1"]["class"]
            == "text_to_audio.services.logging_setup.SafeFileHandler"
        )

        # Check that RotatingFileHandler has been replaced with SafeRotatingFileHandler
        assert (
            updated_config["handlers"]["file2"]["class"]
            == "text_to_audio.services.logging_setup.SafeRotatingFileHandler"
        )

        # Check that StreamHandler hasn't been changed
        assert updated_config["handlers"]["console"]["class"] == "logging.StreamHandler"


def test_handler_works_with_missing_directory():
    """Test that SafeFileHandler correctly logs messages when directory was missing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        log_dir = os.path.join(temp_dir, "missing_dir")
        log_file = os.path.join(log_dir, "test.log")

        # Ensure directory doesn't exist
        assert not os.path.exists(log_dir)

        # Create handler
        handler = SafeFileHandler(log_file)

        # Create a real logger and add our handler
        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        # Log a message
        test_message = "Test log message"
        logger.info(test_message)
        handler.flush()

        # Verify the file was created and contains the message
        assert os.path.exists(log_file)
        with open(log_file, "r") as f:
            content = f.read()
            assert test_message in content

        # Clean up
        handler.close()
