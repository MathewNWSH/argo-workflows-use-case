#!/usr/bin/env python3
"""Geo Converter - Converts pixel coordinates to geographic coordinates (EPSG:4326)."""

import logging
import sys

import orjson

from config import settings

logger = logging.getLogger(__name__)


def pixel_bbox_to_lonlat_polygon(bbox_pixel: list[float], image_size: list[int], bbox: list[float]) -> list[list[list[float]]]:
    """Convert pixel bbox [x1, y1, x2, y2] to GeoJSON Polygon coordinates."""
    x1, y1, x2, y2 = bbox_pixel
    width, height = image_size
    min_lon, min_lat, max_lon, max_lat = bbox
    
    lon_scale = (max_lon - min_lon) / width
    lat_scale = (max_lat - min_lat) / height
    
    # Convert corners (y is inverted: pixel 0 = max_lat)
    lon1 = round(min_lon + x1 * lon_scale, 7)
    lon2 = round(min_lon + x2 * lon_scale, 7)
    lat1 = round(max_lat - y2 * lat_scale, 7)  # bottom
    lat2 = round(max_lat - y1 * lat_scale, 7)  # top
    
    # GeoJSON Polygon: exterior ring, counter-clockwise
    return [[[lon1, lat1], [lon2, lat1], [lon2, lat2], [lon1, lat2], [lon1, lat1]]]


def convert_detections_to_geojson() -> dict:
    with open(settings.detections_path, "rb") as f:
        detections_data = orjson.loads(f.read())
    
    with open(settings.meta_path, "rb") as f:
        meta = orjson.loads(f.read())
    
    parking_name = detections_data["parking"]
    image_size = meta["image_size"]
    bbox = meta["bbox"]
    
    logger.info(f"Converting [bold]{len(detections_data['detections'])}[/] detections for '{parking_name}'")
    logger.debug(f"Image size: {image_size}, BBOX: {bbox}")
    
    features = []
    for det in detections_data["detections"]:
        polygon_coords = pixel_bbox_to_lonlat_polygon(det["bbox_pixel"], image_size, bbox)
        features.append({
            "type": "Feature",
            "properties": {
                "class": det["class_name"],
                "confidence": det["confidence"],
                "parking": parking_name,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": polygon_coords,
            }
        })
    
    geojson = {
        "type": "FeatureCollection",
        "properties": {
            "parking": parking_name,
            "total_vehicles": len(features),
            "crs": meta["crs"],
        },
        "features": features,
    }
    
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = settings.output_dir / f"{parking_name}_vehicles.geojson"
    with open(output_path, "wb") as f:
        f.write(orjson.dumps(geojson, option=orjson.OPT_INDENT_2))
    
    logger.info(f"Saved GeoJSON: {output_path}")
    logger.info(f"Total features: [bold]{len(features)}[/]")
    
    return geojson


def main():
    if not settings.detections_path.exists():
        logger.error(f"Detections file not found: {settings.detections_path}")
        sys.exit(1)
    
    if not settings.meta_path.exists():
        logger.error(f"Meta file not found: {settings.meta_path}")
        sys.exit(1)
    
    try:
        geojson = convert_detections_to_geojson()
        logger.info(f"[bold green]Success![/] Generated {len(geojson['features'])} GeoJSON features")
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
