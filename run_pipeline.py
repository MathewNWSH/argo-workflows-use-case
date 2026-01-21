#!/usr/bin/env python3
"""Local pipeline runner - processes all tiles for a parking."""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], env: dict | None = None) -> bool:
    """Run a command with optional environment variables."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    result = subprocess.run(cmd, env=full_env)
    return result.returncode == 0


def main():
    output_dir = Path(os.environ.get("OUTPUT_DIR", "./output"))
    parking_name = os.environ.get("PARKING_NAME", "test")
    model_path = os.environ.get("MODEL_PATH", "./containers/yolo-inference/yolo26m-obb.pt")

    tiles_dir = output_dir / parking_name

    # Step 1: Fetch tiles
    print(f"\n{'='*60}")
    print("STEP 1: Fetching WMTS tiles")
    print(f"{'='*60}")
    if not run_command([sys.executable, "containers/wmts-fetcher/fetch_tiles.py"]):
        print("ERROR: Failed to fetch tiles")
        sys.exit(1)

    # Step 2: Run YOLO inference on all tiles
    print(f"\n{'='*60}")
    print("STEP 2: Running YOLO inference on all tiles")
    print(f"{'='*60}")

    env = {
        "TILES_DIR": str(tiles_dir),
        "MODEL_PATH": model_path,
        "OUTPUT_DIR": str(output_dir),
    }

    if not run_command([sys.executable, "containers/yolo-inference/detect.py"], env=env):
        print("ERROR: Failed to run YOLO inference")
        sys.exit(1)

    # Step 3: Run geo-converter on all detections
    print(f"\n{'='*60}")
    print("STEP 3: Converting detections to GeoJSON")
    print(f"{'='*60}")

    env = {
        "TILES_DIR": str(tiles_dir),
        "DETECTIONS_DIR": str(output_dir),
        "OUTPUT_DIR": str(output_dir),
    }

    if not run_command([sys.executable, "containers/geo-converter/convert.py"], env=env):
        print("ERROR: Failed to convert detections")
        sys.exit(1)

    # Step 4: Aggregate results
    print(f"\n{'='*60}")
    print("STEP 4: Aggregating results")
    print(f"{'='*60}")

    env = {
        "INPUT_DIR": str(output_dir),
        "OUTPUT_DIR": str(output_dir),
    }

    if not run_command([sys.executable, "containers/aggregator/aggregate.py"], env=env):
        print("ERROR: Failed to aggregate results")
        sys.exit(1)

    # Summary
    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"Results saved to: {output_dir}/all_parkings.geojson")
    print(f"Stats saved to: {output_dir}/stats.csv")


if __name__ == "__main__":
    main()
