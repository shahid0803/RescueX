"""Acquire the verified Trishuli Sentinel-1 pair as bounded Process API GeoTIFFs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from floodlens.satellite.auth import CopernicusAuthenticator
from floodlens.satellite.errors import (
    AuthenticationError,
    CatalogUnavailableError,
    DownloadError,
    IntegrityError,
    ProcessAPIAuthError,
    ProcessAPIRequestError,
)
from floodlens.satellite.models import AOI
from floodlens.satellite.process_api import (
    MAX_STORAGE_BYTES,
    PROCESS_URL,
    ProcessAPIClient,
    acquire_scene,
    build_grid,
    compare_raster_grids,
    verify_stac_candidate,
    validate_acquired_raster,
)

BEFORE_ID = "S1D_IW_GRDH_1SDV_20260816T122141_20260816T122206_004151_007980_B091_COG"
AFTER_ID = "S1D_IW_GRDH_1SDV_20260828T122141_20260828T122206_004326_007FA4_C73B_COG"
SCENE_WINDOWS = {
    "before": (
        datetime(2026, 8, 16, 12, 21, 41, tzinfo=timezone.utc),
        datetime(2026, 8, 16, 12, 22, 6, tzinfo=timezone.utc),
    ),
    "after": (
        datetime(2026, 8, 28, 12, 21, 41, tzinfo=timezone.utc),
        datetime(2026, 8, 28, 12, 22, 6, tzinfo=timezone.utc),
    ),
}
EVENT_DATE = "2026-08-26"
DEFAULT_AOI = Path("configs/case_studies/trishuli_2026_aoi.geojson")
DEFAULT_OUTPUT = Path("data/raw/satellite/sentinel-1/trishuli_2026")
MANIFEST = Path("data/manifests/trishuli_sentinel1_acquisition_manifest.json")
QA = Path("data/qa/sentinel1_trishuli_acquisition_qa.json")
BEFORE_SHA256 = "28e6dd9fef265db3ec4d203e5f7b80d2de06993455a4844f91625559275740fa"


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


def _auth_status() -> dict[str, Any]:
    return {
        "client_id_present": bool(os.getenv("RESCUEX_CDSE_CLIENT_ID")),
        "client_secret_present": bool(os.getenv("RESCUEX_CDSE_CLIENT_SECRET")),
        "status": (
            "READY"
            if os.getenv("RESCUEX_CDSE_CLIENT_ID") and os.getenv("RESCUEX_CDSE_CLIENT_SECRET")
            else "BLOCKED"
        ),
        "values_exposed": False,
    }


def _base_manifest(aoi_path: Path, grid: Any) -> dict[str, Any]:
    return {
        "phase": "10D",
        "status": "INCOMPLETE",
        "case_study": "Trishuli 2026",
        "event_date": EVENT_DATE,
        "aoi_path": str(aoi_path),
        "process_api_endpoint": PROCESS_URL,
        "request_crs": "EPSG:4326",
        "output_crs": grid.crs,
        "resolution_m": grid.resolution_m,
        "dimensions": {"width": grid.width, "height": grid.height},
        "transform": list(grid.transform),
        "expected_pixel_count": grid.width * grid.height,
        "bands": ["VV", "VH"],
        "processing": {
            "backCoeff": "GAMMA0_ELLIPSOID",
            "orthorectify": True,
            "speckle_filter": False,
            "radiometric_terrain_correction": False,
        },
        "authentication": _auth_status(),
        "scenes": {
            "before": {"scene_id": BEFORE_ID, "output": str(DEFAULT_OUTPUT / "before_vv_vh.tif")},
            "after": {"scene_id": AFTER_ID, "output": str(DEFAULT_OUTPUT / "after_vv_vh.tif")},
        },
        "warnings": [
            "Acquisition QA only; no flood inference or change analysis was performed.",
            "Process API scene selection uses documented narrow timeRange and S1GRD filters; item identity is verified by STAC before processing.",
        ],
        "failures": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_existing_before_artifact(
    path: Path,
    manifest: dict[str, Any],
    aoi_geometry: dict[str, Any],
    grid: Any,
) -> dict[str, Any]:
    """Require the recorded successful BEFORE artifact without reacquiring it."""
    before = manifest.get("scenes", {}).get("before", {})
    if before.get("scene_id") != BEFORE_ID:
        raise IntegrityError("existing BEFORE manifest does not record the verified scene")
    if "sha256" not in before:
        raise IntegrityError("MISSING_MANIFEST_EVIDENCE: existing BEFORE checksum is absent")
    if before.get("sha256") != BEFORE_SHA256:
        raise IntegrityError("existing BEFORE manifest checksum does not match the verified artifact")
    if not path.is_file():
        raise IntegrityError(f"existing BEFORE raster is missing: {path}")
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    if checksum != BEFORE_SHA256:
        raise IntegrityError("existing BEFORE raster checksum does not match the manifest")
    validation = validate_acquired_raster(path, aoi_geometry, BEFORE_ID, grid)
    if not validation["valid"]:
        raise IntegrityError(f"existing BEFORE raster failed validation: {validation['errors']}")
    return {
        "scene_id": BEFORE_ID,
        "path": str(path),
        "sha256": checksum,
        "validation": validation,
        "network_request": False,
        "revalidated": True,
    }


def reconcile_before_artifact(
    manifest_path: Path,
    aoi_path: Path,
    output_path: Path,
    expected_sha256: str,
) -> dict[str, Any]:
    """Restore successful BEFORE provenance locally without contacting CDSE."""
    document = json.loads(aoi_path.read_text(encoding="utf-8"))
    aoi = AOI(geometry=extract_geometry(document))
    grid = build_grid(aoi.geometry)
    if not output_path.is_file():
        raise IntegrityError(f"production BEFORE raster is missing: {output_path}")
    actual_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise IntegrityError("production BEFORE raster does not match the expected SHA-256")
    validation = validate_acquired_raster(output_path, aoi.geometry, BEFORE_ID, grid)
    if not validation["valid"]:
        raise IntegrityError(f"production BEFORE raster failed validation: {validation['errors']}")
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else _base_manifest(aoi_path, grid)
    )
    before = manifest.setdefault("scenes", {}).setdefault("before", {"scene_id": BEFORE_ID})
    historical = {
        key: manifest[key]
        for key in ("status", "failures", "exception_type", "request_diagnostics")
        if key in manifest
    }
    if historical:
        manifest.setdefault("attempt_history", []).append({
            "kind": "prior_attempt_evidence",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            **historical,
        })
    before.update({
        "status": "VALIDATED",
        "scene_id": BEFORE_ID,
        "output": str(output_path),
        "file_size": output_path.stat().st_size,
        "sha256": actual_sha256,
        "validation": validation,
        "provenance": "local reconciliation of previously successful BEFORE acquisition",
        "network_request": False,
        "revalidated": True,
    })
    manifest["status"] = "BEFORE_RECONCILED_VALIDATED"
    manifest["reconciliation"] = {
        "performed": True,
        "network_request": False,
        "expected_sha256": expected_sha256,
        "actual_sha256": actual_sha256,
        "file_size": output_path.stat().st_size,
    }
    manifest.setdefault("warnings", []).append(
        "BEFORE provenance restored locally; no CDSE request was performed."
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--crs", default="EPSG:32645")
    parser.add_argument("--resolution", type=float, default=20.0)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--before-only",
        action="store_true",
        help="Make one bounded BEFORE request only; never start the AFTER request.",
    )
    mode_group.add_argument(
        "--after-only",
        action="store_true",
        help="Validate the existing BEFORE artifact, then make one AFTER request only.",
    )
    parser.add_argument(
        "--preserve-invalid-diagnostic",
        action="store_true",
        help="Preserve a bounded rejected BEFORE TIFF under data/qa diagnostics.",
    )
    args = parser.parse_args()
    manifest_path = MANIFEST
    try:
        document = json.loads(args.aoi.read_text(encoding="utf-8"))
        geometry = extract_geometry(document)
        aoi = AOI(geometry=geometry)
        grid = build_grid(aoi.geometry, args.crs, args.resolution)
        existing_manifest = None
        if args.after_only:
            if not MANIFEST.is_file():
                raise IntegrityError("cannot run --after-only without the existing acquisition manifest")
            existing_manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        manifest = existing_manifest or _base_manifest(args.aoi, grid)
        manifest["aoi"] = {"geometry": aoi.geometry, "bbox": list(aoi.bbox), "crs": aoi.crs}
        manifest["scenes"]["before"]["output"] = str(args.output_dir / "before_vv_vh.tif")
        manifest["scenes"]["after"]["output"] = str(args.output_dir / "after_vv_vh.tif")

        stac_checks = {}
        records = {}
        before_output = args.output_dir / "before_vv_vh.tif"
        if args.after_only:
            manifest["scenes"]["before"].update(
                validate_existing_before_artifact(before_output, manifest, aoi.geometry, grid)
            )
            manifest.setdefault("warnings", []).append(
                "AFTER-only invocation did not make a BEFORE network request."
            )
            requested_scenes = (("after", AFTER_ID),)
        else:
            requested_scenes = (("before", BEFORE_ID),)
        if not args.before_only and not args.after_only:
            requested_scenes += (("after", AFTER_ID),)
        for role, scene_id in requested_scenes:
            output = args.output_dir / f"{role}_vv_vh.tif"
            if args.after_only and role == "after" and output.exists():
                raise IntegrityError(f"AFTER production raster already exists; refusing to overwrite: {output}")
            acquisition_start, acquisition_end = SCENE_WINDOWS[role]
            stac_checks[role] = verify_stac_candidate(
                aoi.geometry, scene_id, acquisition_start, acquisition_end
            )
            manifest["scenes"][role]["stac_uniqueness"] = stac_checks[role]
            authenticator = CopernicusAuthenticator.from_env()
            authenticator.get_token()
            client = ProcessAPIClient(authenticator)
            existing = sum(
                path.stat().st_size for path in args.output_dir.glob("*.tif") if path != output
            ) if args.output_dir.exists() else 0
            records[role] = acquire_scene(
                client,
                scene_id,
                aoi.geometry,
                grid,
                output,
                acquisition_start,
                acquisition_end,
                existing,
                (
                    Path(f"data/qa/phase10d_diagnostics/{role}_rejected.tif")
                    if args.preserve_invalid_diagnostic
                    else None
                ),
            )
            manifest["scenes"][role].update(records[role])
        if args.before_only:
            manifest["status"] = "BEFORE_ONLY_REAL_EXECUTED"
            manifest["storage_budget_bytes"] = MAX_STORAGE_BYTES
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(manifest, indent=2))
            return 0
        if args.after_only:
            manifest["status"] = "AFTER_ONLY_REAL_EXECUTED"
            manifest["storage_budget_bytes"] = MAX_STORAGE_BYTES
            manifest["combined_storage_bytes"] = sum(
                path.stat().st_size
                for path in args.output_dir.glob("*.tif")
                if path.is_file()
            )
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(manifest, indent=2))
            return 0
        manifest["grid_comparison"] = compare_raster_grids(
            args.output_dir / "before_vv_vh.tif", args.output_dir / "after_vv_vh.tif"
        )
        if not manifest["grid_comparison"]["aligned"]:
            raise IntegrityError("before and after rasters do not share a common grid")
        manifest["status"] = "REAL_EXECUTED"
        manifest["storage_budget_bytes"] = MAX_STORAGE_BYTES
        QA.parent.mkdir(parents=True, exist_ok=True)
        QA.write_text(json.dumps({
            "label": "REAL SENTINEL-1 ACQUISITION QA — NOT FLOOD RESULT",
            "scenes": {role: record["qc"] for role, record in records.items()},
        }, indent=2) + "\n", encoding="utf-8")
        manifest["qa_artifact"] = str(QA)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))
        return 0
    except ProcessAPIAuthError as exc:
        return _write_failure(
            manifest_path,
            locals().get("manifest"),
            "FAILED",
            "PROCESS_API_AUTH_FAILURE",
            exc,
        )
    except ProcessAPIRequestError as exc:
        return _write_failure(
            manifest_path,
            locals().get("manifest"),
            "FAILED",
            str(exc),
            exc,
        )
    except CatalogUnavailableError as exc:
        return _write_failure(
            manifest_path,
            locals().get("manifest"),
            "BLOCKED",
            "STAC_UNIQUENESS_FAILURE",
            exc,
        )
    except AuthenticationError as exc:
        status = "BLOCKED" if not (_auth_status()["client_id_present"] and _auth_status()["client_secret_present"]) else "FAILED"
        reason = "CDSE credentials are missing" if status == "BLOCKED" else "CDSE authentication failed"
        return _write_failure(manifest_path, locals().get("manifest"), status, reason, exc)
    except (DownloadError, IntegrityError, ValueError, OSError) as exc:
        return _write_failure(manifest_path, locals().get("manifest"), "PARTIALLY_COMPLETED", str(exc), exc)


def _write_failure(path: Path, manifest: dict[str, Any] | None, status: str, reason: str, exc: Exception) -> int:
    record = manifest or {
        "phase": "10D",
        "event_date": EVENT_DATE,
        "authentication": _auth_status(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if record.get("scenes", {}).get("before", {}).get("status") == "VALIDATED":
        record.setdefault("attempt_history", []).append({
            "kind": "failed_later_attempt",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "reason": reason,
            "exception_type": type(exc).__name__,
        })
    record["status"] = status
    record.setdefault("failures", []).append(reason)
    record["exception_type"] = type(exc).__name__
    if getattr(exc, "diagnostics", None):
        record["request_diagnostics"] = exc.diagnostics
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))
    return 2 if status == "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
