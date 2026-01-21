#!/usr/bin/env python3
"""WMTS Fetcher - Downloads orthophoto tiles from Geoportal Poland WMTS service."""

import logging
import sys
from io import BytesIO

import httpx
import orjson
from PIL import Image

from config import settings

logger = logging.getLogger(__name__)

# EPSG:3857 Web Mercator origin (half of world extent in meters)
ORIGIN = 20037508.342787


def meters_to_tile(x: float, y: float, zoom: int) -> tuple[int, int]:
    """Convert EPSG:3857 coordinates (meters) to tile x/y."""
    tile_size_meters = 2 * ORIGIN / (2 ** zoom)
    tile_x = int((x + ORIGIN) / tile_size_meters)
    tile_y = int((ORIGIN - y) / tile_size_meters)
    return tile_x, tile_y


def tile_to_meters(tile_x: int, tile_y: int, zoom: int) -> tuple[float, float]:
    """Convert tile x/y to EPSG:3857 coordinates (NW corner)."""
    tile_size_meters = 2 * ORIGIN / (2 ** zoom)
    x = tile_x * tile_size_meters - ORIGIN
    y = ORIGIN - tile_y * tile_size_meters
    return x, y


def bbox_to_tiles(bbox: list[float], zoom: int) -> tuple[range, range]:
    """Convert bbox [min_x, min_y, max_x, max_y] in EPSG:3857 to tile ranges."""
    min_x, min_y, max_x, max_y = bbox

    # SW corner (min_x, min_y) -> tile with larger y (more south)
    sw_tile_x, sw_tile_y = meters_to_tile(min_x, min_y, zoom)
    # NE corner (max_x, max_y) -> tile with smaller y (more north)
    ne_tile_x, ne_tile_y = meters_to_tile(max_x, max_y, zoom)

    min_col, max_col = min(sw_tile_x, ne_tile_x), max(sw_tile_x, ne_tile_x)
    min_row, max_row = min(sw_tile_y, ne_tile_y), max(sw_tile_y, ne_tile_y)

    return range(min_row, max_row + 1), range(min_col, max_col + 1)


def get_tile_bbox(row: int, col: int, zoom: int) -> list[float]:
    """Get bbox [min_x, min_y, max_x, max_y] in EPSG:3857 for a tile."""
    # NW corner
    nw_x, nw_y = tile_to_meters(col, row, zoom)
    # SE corner (NW of next tile diagonally)
    se_x, se_y = tile_to_meters(col + 1, row + 1, zoom)

    return [nw_x, se_y, se_x, nw_y]  # [min_x, min_y, max_x, max_y]


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
    img_min_x, img_min_y, img_max_x, img_max_y = image_bbox
    tgt_min_x, tgt_min_y, tgt_max_x, tgt_max_y = target_bbox

    img_width, img_height = image.size
    x_per_pixel = (img_max_x - img_min_x) / img_width
    y_per_pixel = (img_max_y - img_min_y) / img_height

    left = max(0, int((tgt_min_x - img_min_x) / x_per_pixel))
    right = min(img_width, int((tgt_max_x - img_min_x) / x_per_pixel))
    top = max(0, int((img_max_y - tgt_max_y) / y_per_pixel))
    bottom = min(img_height, int((img_max_y - tgt_min_y) / y_per_pixel))

    if right <= left or bottom <= top:
        logger.warning("Invalid crop region, returning original image")
        return image, image_bbox

    cropped = image.crop((left, top, right, bottom))
    actual_bbox = [
        img_min_x + left * x_per_pixel,
        img_max_y - bottom * y_per_pixel,
        img_min_x + right * x_per_pixel,
        img_max_y - top * y_per_pixel,
    ]

    return cropped, actual_bbox


def select_zoom_level(bbox: list[float]) -> int:
    """Select zoom level that provides at least min_pixels for the bbox."""
    min_x, min_y, max_x, max_y = bbox

    for zoom in range(19, -1, -1):
        sw_tile_x, sw_tile_y = meters_to_tile(min_x, min_y, zoom)
        ne_tile_x, ne_tile_y = meters_to_tile(max_x, max_y, zoom)

        tiles_x = abs(ne_tile_x - sw_tile_x) + 1
        tiles_y = abs(ne_tile_y - sw_tile_y) + 1

        pixels = min(tiles_x, tiles_y) * settings.wmts.tile_size
        if pixels >= settings.min_pixels:
            return zoom

    return 19


def fetch_orthophoto() -> dict:
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    zoom = settings.zoom if settings.zoom else select_zoom_level(settings.bbox)

    logger.info(f"Fetching orthophoto for [bold]{settings.parking_name}[/] at zoom {zoom}")
    logger.debug(f"BBOX (EPSG:3857): {settings.bbox}")

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
        "crs": "EPSG:3857",
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
