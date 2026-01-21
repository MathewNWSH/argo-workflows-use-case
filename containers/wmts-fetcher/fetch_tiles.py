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


def fetch_orthophoto_tiles() -> dict:
    """Fetch tiles individually without merging - for per-tile YOLO inference."""
    parking_dir = settings.output_dir / settings.parking_name
    parking_dir.mkdir(parents=True, exist_ok=True)

    zoom = settings.zoom if settings.zoom else select_zoom_level(settings.bbox)

    logger.info(f"Fetching tiles for [bold]{settings.parking_name}[/] at zoom {zoom}")
    logger.debug(f"BBOX (EPSG:3857): {settings.bbox}")

    row_range, col_range = bbox_to_tiles(settings.bbox, zoom)
    total_tiles = len(row_range) * len(col_range)
    logger.info(f"Tiles: rows {row_range.start}-{row_range.stop-1}, cols {col_range.start}-{col_range.stop-1}")
    logger.info(f"Total tiles to fetch: {total_tiles}")

    tiles_list = []
    fetched_count = 0

    with httpx.Client() as client:
        for row_idx, row in enumerate(row_range):
            for col_idx, col in enumerate(col_range):
                tile_id = f"{row_idx}_{col_idx}"
                logger.debug(f"Fetching tile ({row}, {col}) -> {tile_id}")

                tile_img = fetch_tile(row, col, zoom, client)
                if tile_img is None:
                    logger.warning(f"Failed to fetch tile ({row}, {col}), skipping")
                    continue

                # Save tile image
                tile_image_path = parking_dir / f"tile_{tile_id}.jpg"
                tile_img.save(tile_image_path, "JPEG", quality=95)

                # Get tile bbox
                tile_bbox = get_tile_bbox(row, col, zoom)

                # Save tile metadata
                tile_meta = {
                    "parking": settings.parking_name,
                    "tile_id": tile_id,
                    "tile_row": row,
                    "tile_col": col,
                    "bbox": tile_bbox,
                    "image_size": [tile_img.width, tile_img.height],
                    "crs": "EPSG:3857",
                    "zoom_level": zoom,
                }

                tile_meta_path = parking_dir / f"tile_{tile_id}_meta.json"
                with open(tile_meta_path, "wb") as f:
                    f.write(orjson.dumps(tile_meta, option=orjson.OPT_INDENT_2))

                # Add to tiles list for Argo fanout
                tiles_list.append({
                    "tile_id": tile_id,
                    "parking": settings.parking_name,
                    "image_path": str(tile_image_path.relative_to(settings.output_dir.parent)),
                    "meta_path": str(tile_meta_path.relative_to(settings.output_dir.parent)),
                })

                fetched_count += 1

    if not tiles_list:
        raise RuntimeError("No tiles were fetched successfully")

    logger.info(f"Fetched [bold]{fetched_count}/{total_tiles}[/] tiles")

    # Save tiles list for Argo workflow fanout
    tiles_json_path = parking_dir / "tiles.json"
    with open(tiles_json_path, "wb") as f:
        f.write(orjson.dumps(tiles_list, option=orjson.OPT_INDENT_2))
    logger.info(f"Saved tiles list: {tiles_json_path}")

    # Return summary metadata
    summary = {
        "parking": settings.parking_name,
        "total_tiles": fetched_count,
        "zoom_level": zoom,
        "bbox": settings.bbox,
        "tiles_json": str(tiles_json_path),
        "tiles": tiles_list,
    }

    return summary


def main():
    try:
        result = fetch_orthophoto_tiles()
        logger.info(f"[bold green]Success![/] Fetched {result['total_tiles']} tiles")
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
