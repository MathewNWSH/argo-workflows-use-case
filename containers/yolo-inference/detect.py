#!/usr/bin/env python3
"""YOLO Inference - Detects vehicles on all tiles for a parking."""

import logging
import sys

import orjson
from PIL import Image
from ultralytics import YOLO

from config import settings

logger = logging.getLogger(__name__)


def detect_vehicles_on_tile(model: YOLO, image_path: str, tile_name: str) -> dict:
    """Run detection on a single tile."""
    logger.info(f"Processing tile: [bold]{tile_name}[/]")

    results = model(image_path, conf=settings.confidence_threshold, verbose=False)

    detections = []

    for result in results:
        obb = result.obb

        if obb is None:
            continue

        for i in range(len(obb)):
            class_id = int(obb.cls[i].item())

            if class_id not in settings.vehicle_classes:
                continue

            confidence = float(obb.conf[i].item())
            polygon = obb.xyxyxyxy[i].tolist()

            center_x = sum(p[0] for p in polygon) / 4
            center_y = sum(p[1] for p in polygon) / 4

            detections.append({
                "class_name": settings.vehicle_classes[class_id],
                "class_id": class_id,
                "confidence": round(confidence, 4),
                "polygon_pixel": [[round(p[0], 2), round(p[1], 2)] for p in polygon],
                "center_pixel": [round(center_x, 2), round(center_y, 2)],
            })

    logger.info(f"  Found [bold]{len(detections)}[/] vehicles")

    # Save annotated image if enabled
    if settings.save_annotated and results:
        annotated_path = settings.output_dir / f"{tile_name}_annotated.jpg"
        annotated_img = results[0].plot()
        img = Image.fromarray(annotated_img[..., ::-1])
        img.save(annotated_path, "JPEG", quality=95)

    return {
        "tile": tile_name,
        "total_vehicles": len(detections),
        "detections": detections,
    }


def process_all_tiles() -> dict:
    """Process all tiles for a parking from tiles.json."""
    tiles_json_path = settings.tiles_dir / "tiles.json"

    if not tiles_json_path.exists():
        raise FileNotFoundError(f"tiles.json not found: {tiles_json_path}")

    with open(tiles_json_path, "rb") as f:
        tiles = orjson.loads(f.read())

    parking_name = tiles[0]["parking"] if tiles else "unknown"
    logger.info(f"Processing parking: [bold]{parking_name}[/]")
    logger.info(f"Total tiles: [bold]{len(tiles)}[/]")

    logger.info(f"Loading model from [bold]{settings.model_path}[/]")
    model = YOLO(str(settings.model_path))

    settings.output_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    total_vehicles = 0

    for tile in tiles:
        tile_id = tile["tile_id"]
        tile_name = f"{parking_name}_{tile_id}"
        image_path = settings.tiles_dir / f"tile_{tile_id}.jpg"

        if not image_path.exists():
            logger.warning(f"Tile image not found: {image_path}, skipping")
            continue

        result = detect_vehicles_on_tile(model, str(image_path), tile_name)
        total_vehicles += result["total_vehicles"]

        # Save detections for this tile
        detections_path = settings.output_dir / f"{tile_name}_detections.json"
        with open(detections_path, "wb") as f:
            f.write(orjson.dumps({
                "parking": parking_name,
                "tile_id": tile_id,
                "total_vehicles": result["total_vehicles"],
                "class_counts": _count_classes(result["detections"]),
                "detections": result["detections"],
            }, option=orjson.OPT_INDENT_2))

        all_results.append(result)

    logger.info(f"[bold green]Done![/] Total vehicles across all tiles: [bold]{total_vehicles}[/]")

    return {
        "parking": parking_name,
        "total_tiles": len(tiles),
        "processed_tiles": len(all_results),
        "total_vehicles": total_vehicles,
    }


def _count_classes(detections: list[dict]) -> dict[str, int]:
    """Count detections by class."""
    counts = {}
    for det in detections:
        cls = det["class_name"]
        counts[cls] = counts.get(cls, 0) + 1
    return counts


def main():
    if not settings.tiles_dir.exists():
        logger.error(f"Tiles directory not found: {settings.tiles_dir}")
        sys.exit(1)

    if not settings.model_path.exists():
        logger.error(f"Model not found: {settings.model_path}")
        sys.exit(1)

    try:
        result = process_all_tiles()
        logger.info(f"[bold green]Success![/] Processed {result['processed_tiles']} tiles, found {result['total_vehicles']} vehicles")
    except Exception as e:
        logger.exception(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
