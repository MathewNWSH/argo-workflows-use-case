"""Configuration for WMTS Fetcher."""

import logging.config
from pathlib import Path
from typing import Annotated, Any, Literal
from pydantic import field_validator

import orjson
from pydantic_settings import BaseSettings, NoDecode
from rich.console import Console



class WMTSConfig:
    """WMTS service configuration."""

    base_url: str = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMTS/StandardResolution"
    layer: str = "ORTOFOTOMAPA"
    tile_matrix_set: str = "EPSG:3857"
    style: str = "default"
    format: str = "image/jpeg"
    tile_size: int = 256  # EPSG:3857 uses 256x256 tiles


class Settings(BaseSettings):
    """Main settings for WMTS fetcher."""

    parking_json: Annotated[dict[str, Any], NoDecode]
    output_dir: Path = Path("/data/output")
    zoom: int | None = None
    min_pixels: int = 1024
    http_timeout: float = 30.0
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "DEBUG"
    wmts: WMTSConfig = WMTSConfig()

    @field_validator("parking_json", mode="before")
    @classmethod
    def parse_parking_json(cls, v: str | dict) -> dict:
        """Parse parking JSON from string or dict."""
        if isinstance(v, str):
            return orjson.loads(v)
        return v

    @property
    def parking_name(self) -> str:
        return self.parking_json["name"]

    @property
    def bbox(self) -> list[float]:
        return self.parking_json["bbox"]


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
