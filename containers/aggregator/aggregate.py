#!/usr/bin/env python3
"""Aggregator - Combines GeoJSON results from all parkings into final outputs."""

import csv
import logging
import sys
from datetime import datetime, timezone

import orjson

from config import settings

logger = logging.getLogger(__name__)


def aggregate_geojson_files() -> tuple[dict, list[dict]]:
    geojson_files = list(settings.input_dir.glob("*_vehicles.geojson"))
    
    if not geojson_files:
        logger.warning(f"No *_vehicles.geojson files found in {settings.input_dir}")
        geojson_files = list(settings.input_dir.glob("*.geojson"))
    
    logger.info(f"Found [bold]{len(geojson_files)}[/] GeoJSON files to aggregate")
    
    all_features = []
    parking_stats = []
    
    for geojson_path in sorted(geojson_files):
        logger.debug(f"Processing: {geojson_path.name}")
        
        with open(geojson_path, "rb") as f:
            data = orjson.loads(f.read())
        
        parking_name = data.get("properties", {}).get("parking") or geojson_path.stem.replace("_vehicles", "")
        features = data.get("features", [])
        
        all_features.extend(features)
        parking_stats.append({"parking": parking_name, "vehicles": len(features)})
        
        logger.info(f"  {parking_name}: [bold]{len(features)}[/] vehicles")
    
    combined = {
        "type": "FeatureCollection",
        "properties": {
            "total_parkings": len(parking_stats),
            "total_vehicles": len(all_features),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "crs": "EPSG:4326",
        },
        "features": all_features,
    }
    
    return combined, parking_stats


def save_stats_csv(stats: list[dict]) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    csv_path = settings.output_dir / "stats.csv"
    
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["parking", "vehicles", "timestamp"])
        for stat in stats:
            writer.writerow([stat["parking"], stat["vehicles"], timestamp])
    
    logger.info(f"Saved stats CSV: {csv_path}")


def main():
    if not settings.input_dir.exists():
        logger.error(f"Input directory not found: {settings.input_dir}")
        sys.exit(1)
    
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        combined_geojson, parking_stats = aggregate_geojson_files()
        
        geojson_path = settings.output_dir / "all_parkings.geojson"
        with open(geojson_path, "wb") as f:
            f.write(orjson.dumps(combined_geojson, option=orjson.OPT_INDENT_2))
        logger.info(f"Saved combined GeoJSON: {geojson_path}")
        
        save_stats_csv(parking_stats)
        
        logger.info("")
        logger.info("[bold green]AGGREGATION COMPLETE[/]")
        logger.info(f"Total parkings: [bold]{len(parking_stats)}[/]")
        logger.info(f"Total vehicles: [bold]{combined_geojson['properties']['total_vehicles']}[/]")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
