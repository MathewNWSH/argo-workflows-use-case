#!/usr/bin/env python3
"""Geo Converter - Converts pixel coordinates to geographic coordinates (EPSG:4326) for all tiles."""

import logging
import math
import sys

import orjson

from config import settings

logger = logging.getLogger(__name__)

# Web Mercator origin (half of world extent in meters)
ORIGIN = 20037508.342787


def epsg3857_to_epsg4326(x: float, y: float) -> tuple[float, float]:
    """Convert EPSG:3857 (Web Mercator meters) to EPSG:4326 (WGS84 degrees)."""
    lon = x * 180 / ORIGIN
    lat = math.atan(math.exp(y * math.pi / ORIGIN)) * 360 / math.pi - 90
    return lon, lat


def pixel_polygon_to_lonlat_polygon(polygon_pixel: list[list[float]], image_size: list[int], bbox_3857: list[float]) -> list[list[list[float]]]:
    """Convert OBB pixel polygon to GeoJSON Polygon coordinates in EPSG:4326."""
    width, height = image_size
    min_x, min_y, max_x, max_y = bbox_3857

    x_scale = (max_x - min_x) / width
    y_scale = (max_y - min_y) / height

    coords = []
    for px, py in polygon_pixel:
        # Convert pixel to EPSG:3857
        x = min_x + px * x_scale
        y = max_y - py * y_scale  # y is inverted: pixel 0 = max_y

        # Convert EPSG:3857 to EPSG:4326
        lon, lat = epsg3857_to_epsg4326(x, y)
        coords.append([round(lon, 7), round(lat, 7)])

    # Close the polygon ring
    coords.append(coords[0])

    return [coords]


def convert_tile_detections(tile_id: str, parking_name: str) -> dict | None:
    """Convert detections for a single tile to GeoJSON features."""
    tile_name = f"{parking_name}_{tile_id}"
    detections_path = settings.detections_dir / f"{tile_name}_detections.json"
    meta_path = settings.tiles_dir / f"tile_{tile_id}_meta.json"

    if not detections_path.exists():
        logger.debug(f"No detections file for tile {tile_id}, skipping")
        return None

    if not meta_path.exists():
        logger.warning(f"Meta file not found for tile {tile_id}: {meta_path}")
        return None

    with open(detections_path, "rb") as f:
        detections_data = orjson.loads(f.read())

    with open(meta_path, "rb") as f:
        meta = orjson.loads(f.read())

    image_size = meta["image_size"]
    bbox = meta["bbox"]

    features = []
    for det in detections_data.get("detections", []):
        polygon_coords = pixel_polygon_to_lonlat_polygon(det["polygon_pixel"], image_size, bbox)
        features.append({
            "type": "Feature",
            "properties": {
                "class": det["class_name"],
                "confidence": det["confidence"],
                "parking": parking_name,
                "tile_id": tile_id,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": polygon_coords,
            }
        })

    return {
        "tile_id": tile_id,
        "features": features,
    }


def process_all_tiles() -> dict:
    """Process all tiles for a parking and create GeoJSON files."""
    tiles_json_path = settings.tiles_dir / "tiles.json"

    if not tiles_json_path.exists():
        raise FileNotFoundError(f"tiles.json not found: {tiles_json_path}")

    with open(tiles_json_path, "rb") as f:
        tiles = orjson.loads(f.read())

    parking_name = tiles[0]["parking"] if tiles else "unknown"
    logger.info(f"Converting detections for parking: [bold]{parking_name}[/]")
    logger.info(f"Total tiles: [bold]{len(tiles)}[/]")

    settings.output_dir.mkdir(parents=True, exist_ok=True)

    all_features = []
    processed_count = 0
    total_vehicles = 0

    for tile in tiles:
        tile_id = tile["tile_id"]
        result = convert_tile_detections(tile_id, parking_name)

        if result is None:
            continue

        features = result["features"]
        all_features.extend(features)
        total_vehicles += len(features)
        processed_count += 1

        # Save individual tile GeoJSON
        tile_name = f"{parking_name}_{tile_id}"
        geojson = {
            "type": "FeatureCollection",
            "properties": {
                "parking": parking_name,
                "tile_id": tile_id,
                "total_vehicles": len(features),
                "crs": "EPSG:4326",
            },
            "features": features,
        }

        output_path = settings.output_dir / f"{tile_name}_vehicles.geojson"
        with open(output_path, "wb") as f:
            f.write(orjson.dumps(geojson, option=orjson.OPT_INDENT_2))

        logger.debug(f"  Tile {tile_id}: {len(features)} vehicles")

    logger.info(f"Processed [bold]{processed_count}[/] tiles, total vehicles: [bold]{total_vehicles}[/]")

    return {
        "parking": parking_name,
        "processed_tiles": processed_count,
        "total_vehicles": total_vehicles,
    }


def main():
    if not settings.tiles_dir.exists():
        logger.error(f"Tiles directory not found: {settings.tiles_dir}")
        sys.exit(1)

    try:
        result = process_all_tiles()
        logger.info(f"[bold green]Success![/] Converted {result['processed_tiles']} tiles, {result['total_vehicles']} vehicles")
    except Exception as e:
        logger.exception(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
