"""Build or explicitly execute the isolated Phase 11D Sentinel-1 candidate pair."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from floodlens.satellite.auth import CopernicusAuthenticator
from floodlens.satellite.models import AOI
from floodlens.satellite.process_api import (
    MAX_STORAGE_BYTES,
    PROCESS_URL,
    ProcessAPIClient,
    AcquisitionGrid,
    build_candidate_process_payload,
    validate_candidate_raster,
    verify_stac_candidate,
)

ACQUISITION_MANIFEST = Path("data/manifests/trishuli_sentinel1_acquisition_manifest.json")
DEFAULT_AOI = Path("configs/case_studies/trishuli_2026_aoi.geojson")
DEFAULT_OUTPUT = Path("data/raw/satellite/sentinel-1/trishuli_2026/candidate_sigma0_10m")
OUTPUT_MANIFEST = Path("data/manifests/trishuli_candidate_preprocessing_manifest.json")
BEFORE_SHA256 = "28e6dd9fef265db3ec4d203e5f7b80d2de06993455a4844f91625559275740fa"
AFTER_SHA256 = "c4df94426a9be90e5dcf20b7d14d09165880fd36ae85c0ef34dc9bf1c2663a2b"
WINDOWS = {
    "before": (datetime(2026, 8, 16, 12, 21, 41, tzinfo=timezone.utc),
               datetime(2026, 8, 16, 12, 22, 6, tzinfo=timezone.utc)),
    "after": (datetime(2026, 8, 28, 12, 21, 41, tzinfo=timezone.utc),
              datetime(2026, 8, 28, 12, 22, 6, tzinfo=timezone.utc)),
}


def extract_geometry(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("type") == "FeatureCollection":
        features = document.get("features", [])
        if len(features) != 1:
            raise ValueError("AOI FeatureCollection must contain exactly one feature")
        document = features[0]
    if document.get("type") == "Feature":
        document = document.get("geometry")
    if not isinstance(document, dict) or document.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("AOI must contain a Polygon or MultiPolygon geometry")
    return document


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scene_ids() -> dict[str, str]:
    document = json.loads(ACQUISITION_MANIFEST.read_text(encoding="utf-8"))
    scenes = document.get("scenes", {})
    ids = {role: scenes.get(role, {}).get("scene_id") for role in ("before", "after")}
    if not all(ids.values()):
        raise ValueError("reconciled acquisition manifest does not contain both scene IDs")
    return ids


def build_manifest(aoi_path: Path, output_dir: Path, grid: Any, scene_ids: dict[str, str]) -> dict[str, Any]:
    return {
        "phase": "11D",
        "status": "CANDIDATE_PROFILE_IMPLEMENTED",
        "candidate_label": "CANDIDATE PREPROCESSING — NOT VALIDATED MODEL INPUT",
        "live_acquisition_performed": False,
        "network_request_performed": False,
        "aoi_path": str(aoi_path),
        "output_dir": str(output_dir),
        "process_api_endpoint": PROCESS_URL,
        "scenes": {role: {"scene_id": scene_id, "window": {
            "from": WINDOWS[role][0].isoformat().replace("+00:00", "Z"),
            "to": WINDOWS[role][1].isoformat().replace("+00:00", "Z"),
        }} for role, scene_id in scene_ids.items()},
        "grid": {
            "crs": grid.crs, "width": grid.width, "height": grid.height,
            "resolution_m": grid.resolution_m, "bounds": list(grid.bounds),
            "transform": list(grid.transform),
        },
        "processing": {
            "backCoeff": "SIGMA0_ELLIPSOID",
            "orthorectify": True,
            "speckle_filter": {"api_type": "LEE", "window_size": 3,
                               "snap_comparison": "SNAP Lee Sigma; not equivalent"},
            "radiometric_terrain_correction": False,
            "output_bands": ["VV", "VH", "dataMask"],
            "sample_type": "FLOAT32",
        },
        "source_provenance": {
            "dataset_repository": "orion-ai-lab/Kuro-Siwo-Webdataset",
            "dataset_revision": "e8e61b7b1254b04bfa2b5e26d43db90cb86b5004",
            "github_config_path": "configs/grd_preprocessing.xml",
            "github_config_blob": "09f180da6e803d4a5c389903e42ed059215e01e3",
            "github_to_dataset_link": "UNPROVEN",
            "candidate_is_not_claimed_equivalent_to_snap": True,
            "cdse_documentation": [
                "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html",
                "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Process/Examples/S1GRD.html",
            ],
        },
        "validation": {"performed": False, "status": "NOT_EXECUTED"},
        "storage_budget_bytes": MAX_STORAGE_BYTES,
        "warnings": [
            "Candidate outputs are exploratory compatibility evidence only.",
            "dataMask is not claimed equivalent to Kuro Siwo valid_mask or land/sea labels.",
            "No candidate acquisition is performed unless --execute is supplied.",
        ],
    }


def _acquire_one(client: ProcessAPIClient, role: str, scene_id: str, aoi: dict[str, Any],
                 grid: Any, destination: Path, existing_bytes: int) -> dict[str, Any]:
    start, end = WINDOWS[role]
    payload = build_candidate_process_payload(scene_id, aoi, grid, start, end)
    content = client.request_raster(scene_id, payload)
    if existing_bytes + len(content) > MAX_STORAGE_BYTES:
        raise RuntimeError("candidate response exceeds the aggregate 512 MiB storage budget")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(content)
    try:
        validation = validate_candidate_raster(temporary, aoi, scene_id, grid)
        if not validation["valid"]:
            raise RuntimeError(f"candidate failed strict validation: {validation['errors']}")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "status": "VALIDATED",
        "path": str(destination),
        "file_size": destination.stat().st_size,
        "sha256": _sha256(destination),
        "request": payload,
        "validation": validation,
    }


def run(aoi_path: Path, output_dir: Path, execute: bool) -> dict[str, Any]:
    scene_ids = _scene_ids()
    document = json.loads(aoi_path.read_text(encoding="utf-8"))
    aoi = AOI(geometry=extract_geometry(document))
    grid = AcquisitionGrid(
        crs="EPSG:32645",
        resolution_m=10.0,
        width=830,
        height=496,
        bounds=(313843.864892112, 3084291.802767885, 322143.864892112, 3089251.802767885),
    )
    manifest = build_manifest(aoi_path, output_dir, grid, scene_ids)
    if not execute:
        return manifest
    if not os.getenv("RESCUEX_CDSE_CLIENT_ID") or not os.getenv("RESCUEX_CDSE_CLIENT_SECRET"):
        raise RuntimeError("candidate execution requires RESCUEX_CDSE_CLIENT_ID and RESCUEX_CDSE_CLIENT_SECRET")
    existing_paths = [
        Path("data/raw/satellite/sentinel-1"),
        Path("data/qa/phase10d_diagnostics"),
        output_dir,
    ]
    existing_files = {
        path.resolve()
        for root in existing_paths
        if root.exists()
        for path in root.rglob("*")
        if path.is_file() and not str(path).endswith(".part")
    }
    existing = sum(path.stat().st_size for path in existing_files)
    client = ProcessAPIClient(CopernicusAuthenticator.from_env())
    for role, scene_id in scene_ids.items():
        start, end = WINDOWS[role]
        manifest["scenes"][role]["stac_uniqueness"] = verify_stac_candidate(
            aoi.geometry, scene_id, start, end
        )
        destination = output_dir / f"{role}_sigma0_lee_vv_vh_datamask.tif"
        if destination.exists():
            raise RuntimeError(f"candidate output already exists; refusing to overwrite: {destination}")
        record = _acquire_one(client, role, scene_id, aoi.geometry, grid, destination, existing)
        existing += record["file_size"]
        manifest["scenes"][role].update(record)
    manifest["status"] = "CANDIDATE_DATA_VALIDATED"
    manifest["live_acquisition_performed"] = True
    manifest["network_request_performed"] = True
    manifest["validation"] = {"performed": True, "status": "PASS"}
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--execute", action="store_true",
                        help="Perform authenticated STAC and Process API requests.")
    parser.add_argument("--manifest", type=Path, default=OUTPUT_MANIFEST)
    args = parser.parse_args()
    manifest = run(args.aoi, args.output_dir, args.execute)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
