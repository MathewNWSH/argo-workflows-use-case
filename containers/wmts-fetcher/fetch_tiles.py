#!/usr/bin/env python3
"""WMTS Fetcher - Downloads orthophoto tiles from Geoportal Poland WMTS service."""

import logging
import sys
from io import BytesIO
from pathlib import Path

import httpx
import orjson
from PIL import Image

from config import settings

logger = logging.getLogger(__name__)


def get_tile_span_degrees(zoom: int) -> tuple[float, float]:
    zoom_diff = 14 - zoom
    factor = 2 ** zoom_diff
    return settings.tile_span_lon_z14 * factor, settings.tile_span_lat_z14 * factor


def bbox_to_tiles(bbox: list[float], zoom: int) -> tuple[range, range]:
    min_lon, min_lat, max_lon, max_lat = bbox
    lon_span, lat_span = get_tile_span_degrees(zoom)
    wmts = settings.wmts
    
    min_col = int((min_lon - wmts.top_left_lon) / lon_span)
    max_col = int((max_lon - wmts.top_left_lon) / lon_span)
    min_row = int((wmts.top_left_lat - max_lat) / lat_span)
    max_row = int((wmts.top_left_lat - min_lat) / lat_span)
    
    return range(max(0, min_row), max_row + 1), range(max(0, min_col), max_col + 1)


def get_tile_bbox(row: int, col: int, zoom: int) -> list[float]:
    lon_span, lat_span = get_tile_span_degrees(zoom)
    wmts = settings.wmts
    
    min_lon = wmts.top_left_lon + col * lon_span
    max_lon = min_lon + lon_span
    max_lat = wmts.top_left_lat - row * lat_span
    min_lat = max_lat - lat_span
    
    return [min_lon, min_lat, max_lon, max_lat]


def fetch_tile(row: int, col: int, zoom: int, client: httpx.Client) -> Image.Image | None:
    wmts = settings.wmts
    params = {
        "SERVICE": "WMTS",
        "REQUEST": "GetTile",
        "VERSION": "1.0.0",
        "LAYER": wmts.layer,
        "STYLE": wmts.style,
        "FORMAT": wmts.format,
        "TILEMATRIXSET": wmts.tile_matrix_set,
        "TILEMATRIX": f"{wmts.tile_matrix_set}:{zoom}",
        "TILEROW": str(row),
        "TILECOL": str(col),
    }
    
    try:
        response = client.get(wmts.base_url, params=params, timeout=settings.http_timeout)
        response.raise_for_status()
        
        if "image" not in response.headers.get("content-type", ""):
            logger.error(f"WMTS error for tile ({row}, {col}): {response.text[:300]}")
            return None
        
        return Image.open(BytesIO(response.content))
    except Exception as e:
        logger.error(f"Error fetching tile ({row}, {col}): {e}")
        return None


def merge_tiles(tiles: dict, row_range: range, col_range: range) -> Image.Image:
    tile_size = settings.wmts.tile_size
    merged = Image.new("RGB", (len(col_range) * tile_size, len(row_range) * tile_size))
    
    for row_idx, row in enumerate(row_range):
        for col_idx, col in enumerate(col_range):
            if tile := tiles.get((row, col)):
                merged.paste(tile, (col_idx * tile_size, row_idx * tile_size))
    
    return merged


def crop_to_bbox(image: Image.Image, image_bbox: list[float], target_bbox: list[float]) -> tuple[Image.Image, list[float]]:
    img_min_lon, img_min_lat, img_max_lon, img_max_lat = image_bbox
    tgt_min_lon, tgt_min_lat, tgt_max_lon, tgt_max_lat = target_bbox
    
    img_width, img_height = image.size
    lon_per_pixel = (img_max_lon - img_min_lon) / img_width
    lat_per_pixel = (img_max_lat - img_min_lat) / img_height
    
    left = max(0, int((tgt_min_lon - img_min_lon) / lon_per_pixel))
    right = min(img_width, int((tgt_max_lon - img_min_lon) / lon_per_pixel))
    top = max(0, int((img_max_lat - tgt_max_lat) / lat_per_pixel))
    bottom = min(img_height, int((img_max_lat - tgt_min_lat) / lat_per_pixel))
    
    if right <= left or bottom <= top:
        logger.warning("Invalid crop region, returning original image")
        return image, image_bbox
    
    cropped = image.crop((left, top, right, bottom))
    actual_bbox = [
        img_min_lon + left * lon_per_pixel,
        img_max_lat - bottom * lat_per_pixel,
        img_min_lon + right * lon_per_pixel,
        img_max_lat - top * lat_per_pixel,
    ]
    
    return cropped, actual_bbox


def select_zoom_level(bbox: list[float]) -> int:
    lon_span = bbox[2] - bbox[0]
    lat_span = bbox[3] - bbox[1]
    
    for zoom in range(16, -1, -1):
        tile_lon_span, tile_lat_span = get_tile_span_degrees(zoom)
        if min((lon_span / tile_lon_span), (lat_span / tile_lat_span)) * settings.wmts.tile_size >= settings.min_pixels:
            return zoom
    
    return 16


def fetch_orthophoto() -> dict:
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    
    zoom = settings.zoom if settings.zoom else select_zoom_level(settings.bbox)
    
    logger.info(f"Fetching orthophoto for [bold]{settings.parking_name}[/] at zoom {zoom}")
    logger.debug(f"BBOX: {settings.bbox}")
    
    row_range, col_range = bbox_to_tiles(settings.bbox, zoom)
    logger.info(f"Tiles: rows {row_range.start}-{row_range.stop-1}, cols {col_range.start}-{col_range.stop-1}")
    logger.info(f"Total tiles: {len(row_range) * len(col_range)}")
    
    tiles = {}
    with httpx.Client() as client:
        for row in row_range:
            for col in col_range:
                logger.debug(f"Fetching tile ({row}, {col})")
                if tile := fetch_tile(row, col, zoom, client):
                    tiles[(row, col)] = tile
                else:
                    logger.warning(f"Failed to fetch tile ({row}, {col})")
    
    if not tiles:
        raise RuntimeError("No tiles were fetched successfully")
    
    logger.info("Merging tiles...")
    merged = merge_tiles(tiles, row_range, col_range)
    
    first_tile_bbox = get_tile_bbox(row_range.start, col_range.start, zoom)
    last_tile_bbox = get_tile_bbox(row_range.stop - 1, col_range.stop - 1, zoom)
    merged_bbox = [first_tile_bbox[0], last_tile_bbox[1], last_tile_bbox[2], first_tile_bbox[3]]
    
    logger.info("Cropping to target BBOX...")
    cropped, actual_bbox = crop_to_bbox(merged, merged_bbox, settings.bbox)
    
    image_path = settings.output_dir / f"{settings.parking_name}.jpg"
    meta_path = settings.output_dir / f"{settings.parking_name}_meta.json"
    
    cropped.save(image_path, "JPEG", quality=95)
    logger.info(f"Saved image: {image_path} ({cropped.size[0]}x{cropped.size[1]} px)")
    
    metadata = {
        "name": settings.parking_name,
        "bbox": actual_bbox,
        "image_size": list(cropped.size),
        "crs": "EPSG:4326",
        "zoom_level": zoom,
    }
    
    with open(meta_path, "wb") as f:
        f.write(orjson.dumps(metadata, option=orjson.OPT_INDENT_2))
    logger.info(f"Saved metadata: {meta_path}")
    
    return metadata


def main():
    try:
        metadata = fetch_orthophoto()
        logger.info("[bold green]Success![/]")
        logger.debug(orjson.dumps(metadata, option=orjson.OPT_INDENT_2).decode())
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
