"""Reconcile the validated Sentinel-1 production pair without network access."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ACQUIRE_PATH = Path(__file__).with_name("phase10d_acquire.py")
_ACQUIRE_SPEC = importlib.util.spec_from_file_location("rescuex_phase10d_acquire", _ACQUIRE_PATH)
_ACQUIRE = importlib.util.module_from_spec(_ACQUIRE_SPEC)
sys.modules[_ACQUIRE_SPEC.name] = _ACQUIRE
_ACQUIRE_SPEC.loader.exec_module(_ACQUIRE)
AFTER_ID = _ACQUIRE.AFTER_ID
BEFORE_ID = _ACQUIRE.BEFORE_ID
DEFAULT_AOI = _ACQUIRE.DEFAULT_AOI
DEFAULT_OUTPUT = _ACQUIRE.DEFAULT_OUTPUT
MANIFEST = _ACQUIRE.MANIFEST
build_grid = _ACQUIRE.build_grid
extract_geometry = _ACQUIRE.extract_geometry
from floodlens.satellite.process_api import compare_raster_grids, validate_acquired_raster
from floodlens.satellite.models import AOI
from floodlens.satellite.errors import IntegrityError


def _validate_production(
    path: Path,
    expected_sha256: str,
    scene_id: str,
    geometry: dict,
    grid,
) -> dict:
    if not path.is_file():
        raise IntegrityError(f"production raster is missing: {path}")
    actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise IntegrityError(
            f"{scene_id} SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )
    validation = validate_acquired_raster(path, geometry, scene_id, grid)
    if not validation["valid"]:
        raise IntegrityError(f"{scene_id} failed strict validation: {validation['errors']}")
    return {
        "status": "VALIDATED",
        "scene_id": scene_id,
        "output": str(path),
        "path": str(path),
        "file_size": path.stat().st_size,
        "sha256": actual_sha256,
        "validation": validation,
        "grid": {
            "crs": grid.crs,
            "width": grid.width,
            "height": grid.height,
            "resolution_m": grid.resolution_m,
            "transform": list(grid.transform),
            "bounds": list(grid.bounds),
        },
        "network_request": False,
        "revalidated": True,
    }


def reconcile_pair(
    manifest_path: Path,
    aoi_path: Path,
    output_dir: Path,
    expected_before_sha256: str,
    expected_after_sha256: str,
) -> dict:
    """Validate and record the pair; this function performs no network I/O."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    geometry = extract_geometry(json.loads(aoi_path.read_text(encoding="utf-8")))
    aoi = AOI(geometry=geometry)
    grid = build_grid(aoi.geometry)
    scenes = manifest.get("scenes", {})
    if scenes.get("before", {}).get("scene_id") != BEFORE_ID:
        raise IntegrityError("manifest BEFORE scene provenance is not the verified candidate")
    if scenes.get("after", {}).get("scene_id") != AFTER_ID:
        raise IntegrityError("manifest AFTER scene provenance is not the verified candidate")

    before = _validate_production(
        output_dir / "before_vv_vh.tif", expected_before_sha256, BEFORE_ID, aoi.geometry, grid
    )
    after = _validate_production(
        output_dir / "after_vv_vh.tif", expected_after_sha256, AFTER_ID, aoi.geometry, grid
    )
    comparison = compare_raster_grids(
        output_dir / "before_vv_vh.tif", output_dir / "after_vv_vh.tif"
    )
    if not comparison["aligned"]:
        raise IntegrityError(f"production pair grids are not aligned: {comparison}")

    historical = {}
    for key in ("status", "failures", "exception_type", "request_diagnostics"):
        if key in manifest:
            historical[key] = manifest[key]
    if historical:
        manifest.setdefault("attempt_history", []).append({
            "kind": "prior_manifest_attempt_evidence",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            **historical,
        })
    manifest["scenes"]["before"] = before
    manifest["scenes"]["after"] = after
    manifest["grid_comparison"] = comparison
    manifest["status"] = "PAIR_ACQUIRED_AND_VALIDATED"
    manifest["failures"] = []
    manifest["reconciliation"] = {
        "kind": "local_pair_manifest_reconciliation",
        "performed_at": datetime.now(timezone.utc).isoformat(),
        "network_request": False,
        "authenticated_request": False,
        "production_artifacts_modified": False,
        "historical_diagnostics_retained_separately": True,
        "combined_storage_bytes": before["file_size"] + after["file_size"],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_suffix(manifest_path.suffix + ".part")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--expected-before-sha256", required=True)
    parser.add_argument("--expected-after-sha256", required=True)
    args = parser.parse_args()
    try:
        manifest = reconcile_pair(
            args.manifest,
            args.aoi,
            args.output_dir,
            args.expected_before_sha256,
            args.expected_after_sha256,
        )
    except Exception as exc:
        print(f"PAIR_RECONCILIATION_FAILED: {type(exc).__name__}: {exc}")
        return 1
    print("PAIR_RECONCILIATION_VALIDATED")
    print(f"status={manifest['status']}")
    print("network_request=False")
    print(f"before_sha256={manifest['scenes']['before']['sha256']}")
    print(f"after_sha256={manifest['scenes']['after']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
