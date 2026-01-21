"""Configuration for YOLO Inference."""

import logging.config
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings
from rich.console import Console


VEHICLE_CLASSES: dict[int, str] = {
    4: "small-vehicle",
    5: "large-vehicle",
}


class Settings(BaseSettings):
    """Settings for YOLO inference."""

    image_path: Path = Path("/data/input/image.jpg")
    model_path: Path = Path("/model/yolo26n.pt")
    parking_name: str = ""
    output_dir: Path = Path("/data/output")
    confidence_threshold: float = 0.25
    save_annotated: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    vehicle_classes: dict[int, str] = VEHICLE_CLASSES


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
            **{module: {"handlers": [], "level": "WARNING"} for module in ("ultralytics", "PIL")},
        },
    })


settings = Settings()
configure_logging(settings.log_level)
