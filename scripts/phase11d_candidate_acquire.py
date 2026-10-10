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

import rasterio

from floodlens.satellite.auth import CopernicusAuthenticator
from floodlens.satellite.models import AOI
from floodlens.satellite.errors import (
    CatalogUnavailableError,
    ProcessAPIAuthError,
    ProcessAPIRequestError,
)
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
CANDIDATE_DIAGNOSTICS = Path("data/qa/phase11d_diagnostics")
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
    validation: dict[str, Any] | None = None
    try:
        validation = validate_candidate_raster(temporary, aoi, scene_id, grid)
        if not validation["valid"]:
            error = RuntimeError(f"candidate failed strict validation: {validation['errors']}")
            error.diagnostics = {
                "stage": "candidate_raster_validation",
                "network_request_performed": True,
                "validation": validation,
            }
            raise error
        temporary.replace(destination)
    except Exception as exc:
        _preserve_rejected_candidate(
            role, content, validation, getattr(client, "last_response_content_type", None),
            existing_bytes, exc,
        )
        temporary.unlink(missing_ok=True)
        raise
    return {
        "status": "VALIDATED",
        "path": str(destination),
        "file_size": destination.stat().st_size,
        "sha256": _sha256(destination),
        "request": payload,
        "validation": validation,
        "network_request": True,
    }


def _candidate_grid() -> AcquisitionGrid:
    return AcquisitionGrid(
        "EPSG:32645", 10.0, 830, 496,
        (313843.864892112, 3084291.802767885,
         322143.864892112, 3089251.802767885),
    )


def recover_candidate(
    aoi_path: Path,
    manifest_path: Path,
    quarantine_path: Path,
    destination: Path,
    role: str,
) -> dict[str, Any]:
    """Recover only missing TIFF descriptions from preserved response bytes."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scene = manifest.get("scenes", {}).get(role, {})
    scene_ids = _scene_ids()
    if role not in scene_ids or scene.get("scene_id") != scene_ids[role]:
        raise RuntimeError(f"candidate {role.upper()} provenance does not match acquisition manifest")
    diagnostic_path = quarantine_path.with_suffix(".json")
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    if diagnostic.get("sha256") != _sha256(quarantine_path):
        raise RuntimeError("candidate quarantine checksum does not match its diagnostic")
    if diagnostic.get("role") != role:
        raise RuntimeError(f"candidate quarantine role does not match {role}")
    validation_evidence = diagnostic.get("validation", {})
    if validation_evidence.get("scene_id") != scene_ids[role]:
        raise RuntimeError(f"candidate quarantine scene does not match {role}")
    if validation_evidence.get("band_descriptions") != [None, None, None]:
        raise RuntimeError("recovery requires all original band descriptions to be absent")
    document = json.loads(aoi_path.read_text(encoding="utf-8"))
    aoi = AOI(geometry=extract_geometry(document))
    grid = _candidate_grid()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    shutil.copyfile(quarantine_path, temporary)
    try:
        with rasterio.open(temporary, "r+") as dataset:
            if dataset.count != 3:
                raise RuntimeError("recovery requires exactly three bands")
            dataset.set_band_description(1, "VV")
            dataset.set_band_description(2, "VH")
            dataset.set_band_description(3, "dataMask")
        recovered_validation = validate_candidate_raster(
            temporary, aoi.geometry, scene_ids[role], grid
        )
        if not recovered_validation["valid"]:
            raise RuntimeError(
                f"recovered candidate failed strict validation: {recovered_validation['errors']}"
            )
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    recovered_hash = _sha256(destination)
    scene.update({
        "status": "LOCALLY_RECOVERED_VALIDATED",
        "path": str(destination),
        "output": str(destination),
        "file_size": destination.stat().st_size,
        "sha256": recovered_hash,
        "original_response_sha256": diagnostic["sha256"],
        "validation": recovered_validation,
        "provenance": "local metadata-only recovery from preserved candidate response",
        "network_request": False,
        "local_recovery": True,
    })
    manifest["live_acquisition_performed"] = False
    manifest["network_request_performed"] = True
    recovery_record = {
        "performed": True,
        "network_request": False,
        "role": role,
        "original_response_path": str(quarantine_path),
        "original_response_sha256": diagnostic["sha256"],
        "recovered_path": str(destination),
        "recovered_sha256": recovered_hash,
        "production_artifact_modified": False,
    }
    history = manifest.setdefault("local_recovery_history", [])
    previous_recovery = manifest.get("local_recovery")
    if previous_recovery and previous_recovery not in history:
        history.append(previous_recovery)
    history.append(recovery_record)
    manifest["local_recovery"] = recovery_record
    before_valid = manifest.get("scenes", {}).get("before", {}).get("validation", {}).get("valid") is True
    after_valid = manifest.get("scenes", {}).get("after", {}).get("validation", {}).get("valid") is True
    if role == "before":
        before_valid = True
    if role == "after":
        after_valid = True
    pair_complete = before_valid and after_valid
    manifest["status"] = "CANDIDATE_PAIR_LOCALLY_RECOVERED_VALIDATED" if pair_complete else (
        "BEFORE_LOCALLY_RECOVERED_VALIDATED" if before_valid else "AFTER_LOCALLY_RECOVERED_VALIDATED"
    )
    manifest["validation"] = {
        "performed": True,
        "status": "PAIR_PASS" if pair_complete else f"{role.upper()}_ONLY_PASS",
        "before_status": "PASS" if before_valid else "NOT_VALIDATED",
        "after_status": "PASS" if after_valid else "NOT_ACQUIRED",
        "pair_complete": pair_complete,
    }
    manifest.setdefault("warnings", []).append(
        f"{role.upper()} candidate recovered locally from preserved response; no reacquisition occurred."
    )
    temporary_manifest = manifest_path.with_suffix(manifest_path.suffix + ".part")
    temporary_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary_manifest.replace(manifest_path)
    return manifest


def recover_before_candidate(
    aoi_path: Path,
    manifest_path: Path,
    quarantine_path: Path,
    destination: Path,
) -> dict[str, Any]:
    return recover_candidate(aoi_path, manifest_path, quarantine_path, destination, "before")


def _preserve_rejected_candidate(
    role: str,
    content: bytes,
    validation: dict[str, Any] | None,
    content_type: str | None,
    existing_bytes: int,
    error: Exception,
) -> None:
    """Quarantine a rejected TIFF separately from candidate production outputs."""
    signature = content[:4]
    is_tiff = signature in (b"II*\x00", b"MM\x00*")
    remaining = MAX_STORAGE_BYTES - existing_bytes
    report = {
        "artifact_type": "rejected_candidate_raster_diagnostic",
        "production_output": False,
        "role": role,
        "response_content_type": content_type,
        "file_size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "tiff_signature_valid": is_tiff,
        "within_remaining_budget": len(content) <= remaining,
        "validation": validation,
        "failure": str(error)[:2000],
        "credentials_saved": False,
    }
    if not is_tiff or len(content) > remaining:
        report["preserved"] = False
    else:
        CANDIDATE_DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
        path = CANDIDATE_DIAGNOSTICS / f"{role}_rejected.tif"
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_bytes(content)
        temporary.replace(path)
        report.update({
            "preserved": True,
            "path": str(path),
            "report_path": str(path.with_suffix(".json")),
        })
    report_path = CANDIDATE_DIAGNOSTICS / f"{role}_rejected.json"
    CANDIDATE_DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def run(
    aoi_path: Path,
    output_dir: Path,
    execute: bool,
    manifest_path: Path = OUTPUT_MANIFEST,
) -> dict[str, Any]:
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
    if manifest_path.is_file():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous.get("scenes", {}).get("before", {}).get("scene_id") == scene_ids["before"]:
            if previous.get("attempt_history"):
                manifest["attempt_history"] = previous["attempt_history"]
            if previous.get("local_recovery"):
                manifest["local_recovery"] = previous["local_recovery"]
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
        destination = output_dir / f"{role}_sigma0_lee_vv_vh_datamask.tif"
        if role == "before" and destination.exists():
            validation = validate_candidate_raster(
                destination, aoi.geometry, scene_id, grid
            )
            if not validation["valid"]:
                raise RuntimeError(
                    f"existing candidate BEFORE failed strict validation: {validation['errors']}"
                )
            record = {
                "status": "LOCALLY_RECOVERED_VALIDATED",
                "path": str(destination),
                "file_size": destination.stat().st_size,
                "sha256": _sha256(destination),
                "validation": validation,
                "network_request": False,
                "local_reuse": True,
            }
            manifest["scenes"][role].update(record)
            existing += record["file_size"]
            continue
        start, end = WINDOWS[role]
        manifest["scenes"][role]["stac_uniqueness"] = verify_stac_candidate(
            aoi.geometry, scene_id, start, end
        )
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
    parser.add_argument("--recover-before", action="store_true",
                        help="Recover the BEFORE candidate from its quarantined TIFF locally.")
    parser.add_argument("--recover-after", action="store_true",
                        help="Recover the AFTER candidate from its quarantined TIFF locally.")
    parser.add_argument("--quarantine", type=Path,
                        default=CANDIDATE_DIAGNOSTICS / "before_rejected.tif")
    args = parser.parse_args()
    try:
        if args.recover_before:
            manifest = recover_candidate(
                args.aoi, args.manifest, args.quarantine,
                args.output_dir / "before_sigma0_lee_vv_vh_datamask.tif",
                "before",
            )
            print(json.dumps(manifest, indent=2))
            return 0
        if args.recover_after:
            manifest = recover_candidate(
                args.aoi, args.manifest, args.quarantine,
                args.output_dir / "after_sigma0_lee_vv_vh_datamask.tif",
                "after",
            )
            print(json.dumps(manifest, indent=2))
            return 0
        manifest = run(args.aoi, args.output_dir, args.execute, args.manifest)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))
        return 0
    except (ProcessAPIAuthError, ProcessAPIRequestError, CatalogUnavailableError, RuntimeError) as exc:
        manifest = _record_failure(args.manifest, args.aoi, args.output_dir, exc)
        print(json.dumps(manifest, indent=2))
        return 2 if isinstance(exc, CatalogUnavailableError) else 1


def _record_failure(
    manifest_path: Path,
    aoi_path: Path,
    output_dir: Path,
    exc: Exception,
) -> dict[str, Any]:
    """Persist bounded, credential-free candidate attempt evidence."""
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        scene_ids = _scene_ids()
        document = json.loads(aoi_path.read_text(encoding="utf-8"))
        aoi = AOI(geometry=extract_geometry(document))
        grid = AcquisitionGrid(
            "EPSG:32645", 10.0, 830, 496,
            (313843.864892112, 3084291.802767885,
             322143.864892112, 3089251.802767885),
        )
        manifest = build_manifest(aoi_path, output_dir, grid, scene_ids)
    manifest.setdefault("attempt_history", []).append({
        "kind": "candidate_acquisition_failure",
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "diagnostics": getattr(exc, "diagnostics", {}),
    })
    manifest["status"] = "CANDIDATE_ACQUISITION_FAILED"
    manifest["live_acquisition_performed"] = False
    diagnostics = getattr(exc, "diagnostics", {})
    manifest["network_request_performed"] = bool(
        diagnostics.get("network_request_performed")
        or diagnostics.get("stage") == "http_submission_or_response"
    )
    manifest["validation"] = {"performed": False, "status": "NOT_EXECUTED"}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_suffix(manifest_path.suffix + ".part")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    return manifest


if __name__ == "__main__":
    raise SystemExit(main())
