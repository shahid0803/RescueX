from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .raster import PIPELINE_VERSION, RasterMetadata


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_processing_manifest(
    output_path: Path,
    *,
    run_id: str,
    scene_id: str,
    sensor: str,
    input_path: Path,
    output_raster: Path,
    source: RasterMetadata,
    output: RasterMetadata,
    configuration: dict[str, Any],
    steps: list[str],
    provenance: dict[str, Any],
) -> Path:
    payload = {
        "run_id": run_id,
        "scene_id": scene_id,
        "sensor": sensor,
        "input_path": str(input_path),
        "output_path": str(output_raster),
        "source_crs": source.crs,
        "output_crs": output.crs,
        "source_bounds": source.bounds,
        "output_bounds": output.bounds,
        "source_resolution": source.resolution,
        "output_resolution": output.resolution,
        "bands": output.count,
        "nodata_policy": configuration.get("nodata_value"),
        "resampling_method": configuration.get("resampling"),
        "preprocessing_steps": steps,
        "configuration": configuration,
        "processing_timestamp": datetime.now(timezone.utc).isoformat(),
        "software": {"python": sys.version.split()[0], "platform": platform.platform()},
        "provenance": provenance,
        "pipeline_version": PIPELINE_VERSION,
        "input_sha256": sha256(input_path),
        "output_sha256": sha256(output_raster),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return output_path
