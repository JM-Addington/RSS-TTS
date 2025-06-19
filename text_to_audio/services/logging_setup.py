"""Logging setup utilities for the RSS-TTS application.

This module provides utilities for safely setting up logging even when
log directories don't exist, which is especially useful in CI/CD environments.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Optional


class SafeFileHandler(logging.FileHandler):
    """A file handler that ensures its directory exists before writing.

    This handler automatically creates the log directory if it doesn't exist,
    which prevents errors in CI/CD environments or when deploying to new systems.
    """

    def __init__(
        self,
        filename: str,
        mode: str = "a",
        encoding: Optional[str] = None,
        delay: bool = False,
    ):
        """Initialize the handler with a filename.

        Args:
            filename: Path to the log file
            mode: File opening mode ('a' for append, 'w' for write)
            encoding: File encoding
            delay: Whether to delay opening the file until the first log record
        """
        # Create the directory if it doesn't exist
        directory = os.path.dirname(filename)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        super().__init__(filename, mode, encoding, delay)


class SafeRotatingFileHandler(RotatingFileHandler):
    """A rotating file handler that ensures its directory exists before writing.

    This handler automatically creates the log directory if it doesn't exist,
    and provides rotating file capabilities to prevent log files from growing
    indefinitely.
    """

    def __init__(
        self,
        filename: str,
        mode: str = "a",
        maxBytes: int = 0,
        backupCount: int = 0,
        encoding: Optional[str] = None,
        delay: bool = False,
    ):
        """Initialize the handler with a filename and rotation parameters.

        Args:
            filename: Path to the log file
            mode: File opening mode ('a' for append, 'w' for write)
            maxBytes: Maximum file size before rotating
            backupCount: Number of backup files to keep
            encoding: File encoding
            delay: Whether to delay opening the file until the first log record
        """
        # Create the directory if it doesn't exist
        directory = os.path.dirname(filename)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)


def configure_logging(config: Dict, base_dir: Path) -> Dict:
    """Configure the logging settings with safe file handlers.

    This function takes the logging configuration dictionary and replaces any
    standard FileHandler instances with SafeFileHandler instances to ensure
    the log directories exist.

    Args:
        config: The logging configuration dictionary
        base_dir: The base directory for log files (usually the project root)

    Returns:
        The modified logging configuration dictionary
    """
    # Check if the config has a 'handlers' section
    if "handlers" not in config:
        return config

    # Iterate through the handlers and replace FileHandler with SafeFileHandler
    for handler_name, handler_config in config["handlers"].items():
        if handler_config.get("class") == "logging.FileHandler":
            # Replace with SafeFileHandler
            handler_config["class"] = "text_to_audio.services.logging_setup.SafeFileHandler"
        elif handler_config.get("class") == "logging.handlers.RotatingFileHandler":
            # Replace with SafeRotatingFileHandler
            handler_config["class"] = "text_to_audio.services.logging_setup.SafeRotatingFileHandler"

        # Ensure log directory exists if there's a filename
        if "filename" in handler_config:
            # Create the directory if it doesn't exist
            log_dir = os.path.dirname(handler_config["filename"])
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

    return config
