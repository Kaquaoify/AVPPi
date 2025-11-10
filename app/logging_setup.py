"""Logging configuration for AVPPi."""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path


def setup_logging(log_directory: Path) -> None:
    """Configure application logging targets."""
    log_directory.mkdir(parents=True, exist_ok=True)
    for filename in ("app.log", "playback.log", "rclone.log"):
        target = log_directory / filename
        try:
            target.write_text("", encoding="utf-8")
        except OSError:
            target.touch(exist_ok=True)

    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            },
            "brief": {
                "format": "%(levelname)s | %(name)s | %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "brief",
                "level": "INFO",
            },
            "app_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "level": "DEBUG",
                "filename": str(log_directory / "app.log"),
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 5,
            },
            "playback_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "level": "DEBUG",
                "filename": str(log_directory / "playback.log"),
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 3,
            },
            "rclone_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "level": "DEBUG",
                "filename": str(log_directory / "rclone.log"),
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 3,
            },
        },
        "loggers": {
            "avppi": {
                "handlers": ["console", "app_file"],
                "level": "INFO",
                "propagate": False,
            },
            "avppi.playback": {
                "handlers": ["playback_file", "console"],
                "level": "INFO",
                "propagate": False,
            },
            "avppi.rclone": {
                "handlers": ["rclone_file", "console"],
                "level": "INFO",
                "propagate": False,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "WARNING",
        },
    }

    logging.config.dictConfig(log_config)
    logging.getLogger("avppi").info("Logging initialised; log directory: %s", log_directory)
