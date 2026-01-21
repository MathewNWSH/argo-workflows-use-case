#!/usr/bin/env python3
"""YOLO Inference - Detects vehicles on parking orthophotos."""

import logging
import sys

import orjson
from PIL import Image
from ultralytics import YOLO

from config import settings

logger = logging.getLogger(__name__)


def detect_vehicles() -> dict:
    logger.info(f"Loading model from [bold]{settings.model_path}[/]")
    model = YOLO(str(settings.model_path))
    
    logger.info(f"Running inference on [bold]{settings.image_path}[/]")
    results = model(str(settings.image_path), conf=settings.confidence_threshold, verbose=False)
    
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
            # OBB returns 4 corner points: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            polygon = obb.xyxyxyxy[i].tolist()

            # Calculate center as average of 4 corners
            center_x = sum(p[0] for p in polygon) / 4
            center_y = sum(p[1] for p in polygon) / 4

            detections.append({
                "class_name": settings.vehicle_classes[class_id],
                "class_id": class_id,
                "confidence": round(confidence, 4),
                "polygon_pixel": [[round(p[0], 2), round(p[1], 2)] for p in polygon],
                "center_pixel": [round(center_x, 2), round(center_y, 2)],
            })
    
    logger.info(f"Found [bold]{len(detections)}[/] vehicles")
    
    class_counts = {}
    for det in detections:
        cls = det["class_name"]
        class_counts[cls] = class_counts.get(cls, 0) + 1
    
    for cls, count in sorted(class_counts.items()):
        logger.debug(f"  {cls}: {count}")
    
    result_data = {
        "parking": settings.parking_name,
        "total_vehicles": len(detections),
        "class_counts": class_counts,
        "detections": detections,
    }
    
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    
    detections_path = settings.output_dir / f"{settings.parking_name}_detections.json"
    with open(detections_path, "wb") as f:
        f.write(orjson.dumps(result_data, option=orjson.OPT_INDENT_2))
    logger.info(f"Saved detections: {detections_path}")
    
    if settings.save_annotated and results:
        annotated_path = settings.output_dir / f"{settings.parking_name}_annotated.jpg"
        annotated_img = results[0].plot()
        img = Image.fromarray(annotated_img[..., ::-1])
        img.save(annotated_path, "JPEG", quality=95)
        logger.info(f"Saved annotated image: {annotated_path}")
    
    return result_data


def main():
    if not settings.image_path.exists():
        logger.error(f"Image not found: {settings.image_path}")
        sys.exit(1)
    
    if not settings.model_path.exists():
        logger.error(f"Model not found: {settings.model_path}")
        sys.exit(1)
    
    try:
        result = detect_vehicles()
        logger.info(f"[bold green]Success![/] Total vehicles: {result['total_vehicles']}")
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
