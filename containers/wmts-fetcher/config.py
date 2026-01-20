"""Configuration for WMTS Fetcher."""

import logging.config
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from rich.console import Console


@dataclass
class WMTSConfig:
    """WMTS service configuration."""
    
    base_url: str = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMTS/StandardResolution"
    layer: str = "ORTOFOTOMAPA"
    tile_matrix_set: str = "EPSG:4326"
    style: str = "default"
    format: str = "image/jpeg"
    tile_size: int = 512
    top_left_lat: float = 56.0
    top_left_lon: float = 12.0
    zoom_14_min_row: int = 916
    zoom_14_max_row: int = 5817
    zoom_14_min_col: int = 1489
    zoom_14_max_col: int = 10428
    poland_min_lon: float = 13.8
    poland_max_lon: float = 24.4
    poland_min_lat: float = 48.8
    poland_max_lat: float = 55.0


@dataclass
class Settings:
    """Main settings for WMTS fetcher."""
    
    parking_json: str = os.getenv("PARKING_JSON", '{"name":"default","bbox":[20.996,52.229,21.001,52.232]}')
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "/data/output")))
    zoom: int | None = field(default_factory=lambda: int(os.getenv("ZOOM", "0")) or None)
    min_pixels: int = int(os.getenv("MIN_PIXELS", "1024"))
    http_timeout: float = float(os.getenv("HTTP_TIMEOUT", "30.0"))
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = os.getenv("LOG_LEVEL", "INFO")
    wmts: WMTSConfig = field(default_factory=WMTSConfig)
    
    parking_name: str = field(init=False, default="")
    bbox: list[float] = field(init=False, default_factory=list)
    
    def __post_init__(self):
        import orjson
        parking = orjson.loads(self.parking_json)
        self.parking_name = parking["name"]
        self.bbox = parking["bbox"]
        if self.zoom == 0:
            self.zoom = None
    
    @property
    def tile_span_lon_z14(self) -> float:
        return (self.wmts.poland_max_lon - self.wmts.poland_min_lon) / (
            self.wmts.zoom_14_max_col - self.wmts.zoom_14_min_col
        )
    
    @property
    def tile_span_lat_z14(self) -> float:
        return (self.wmts.poland_max_lat - self.wmts.poland_min_lat) / (
            self.wmts.zoom_14_max_row - self.wmts.zoom_14_min_row
        )


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
            **{module: {"handlers": [], "level": "WARNING"} for module in ("httpx", "httpcore", "PIL")},
        },
    })


settings = Settings()
configure_logging(settings.log_level)
