"""Configuration for Geo Converter."""

import logging.config
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings
from rich.console import Console


class Settings(BaseSettings):
    """Settings for geo converter."""

    detections_path: Path = Path("/data/input/detections.json")
    meta_path: Path = Path("/data/input/meta.json")
    output_dir: Path = Path("/data/output")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


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
