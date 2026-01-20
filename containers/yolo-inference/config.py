"""Configuration for YOLO Inference."""

import logging.config
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from rich.console import Console


VEHICLE_CLASSES: dict[int, str] = {
    2: "car",
    5: "bus",
    7: "truck",
}


@dataclass
class Settings:
    """Settings for YOLO inference."""
    
    image_path: Path = field(default_factory=lambda: Path(os.getenv("IMAGE_PATH", "/data/input/image.jpg")))
    model_path: Path = field(default_factory=lambda: Path(os.getenv("MODEL_PATH", "/model/yolo26n.pt")))
    parking_name: str = os.getenv("PARKING_NAME", "")
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "/data/output")))
    confidence_threshold: float = float(os.getenv("CONFIDENCE", "0.25"))
    save_annotated: bool = os.getenv("SAVE_ANNOTATED", "true").lower() == "true"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = os.getenv("LOG_LEVEL", "INFO")
    vehicle_classes: dict[int, str] = field(default_factory=lambda: VEHICLE_CLASSES)


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
