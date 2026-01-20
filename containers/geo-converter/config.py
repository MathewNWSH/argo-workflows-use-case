"""Configuration for Geo Converter."""

import logging.config
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from rich.console import Console


@dataclass
class Settings:
    """Settings for geo converter."""
    
    detections_path: Path = field(default_factory=lambda: Path(os.getenv("DETECTIONS_PATH", "/data/input/detections.json")))
    meta_path: Path = field(default_factory=lambda: Path(os.getenv("META_PATH", "/data/input/meta.json")))
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "/data/output")))
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = os.getenv("LOG_LEVEL", "INFO")


def configure_logging(log_level: str = "INFO") -> None:
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "[dark_cyan]%(name)s[/] %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "rich.logging.RichHandler",
                "console": Console(stderr=True),
                "omit_repeated_times": False,
                "markup": True,
            },
        },
        "loggers": {
            "root": {"handlers": ["default"], "level": log_level},
        },
    })


settings = Settings()
configure_logging(settings.log_level)
