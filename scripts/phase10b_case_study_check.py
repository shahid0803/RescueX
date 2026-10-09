"""Check Phase 10B Trishuli inputs without making any network request."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from floodlens.satellite.errors import InvalidAOIError
from floodlens.satellite.models import AOI

CONFIG_PATH = Path("configs/case_studies/trishuli_2026.json")
MANIFEST_PATH = Path("data/manifests/trishuli_case_study_manifest.json")
EVENT_DATE_SOURCE = (
    "Multimodal AI Hackathon 2026 — Track B; "
    "case study: August 2026 Trishuli flood"
)


def _extract_aoi_geometry(document: dict) -> dict:
    """Normalize supported GeoJSON wrappers without weakening AOI validation."""
    if not isinstance(document, dict):
        raise ValueError("AOI GeoJSON must be an object")
    geojson_type = document.get("type")
    if geojson_type == "FeatureCollection":
        features = document.get("features")
        if not isinstance(features, list) or len(features) != 1:
            raise ValueError("AOI FeatureCollection must contain exactly one feature")
        feature = features[0]
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("AOI FeatureCollection contains an invalid feature")
        geometry = feature.get("geometry")
        if geometry is None:
            raise ValueError("AOI feature must contain geometry")
    elif geojson_type == "Feature":
        geometry = document.get("geometry")
        if geometry is None:
            raise ValueError("AOI feature must contain geometry")
    else:
        geometry = document
    if not isinstance(geometry, dict):
        raise ValueError("AOI geometry must be an object")
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("AOI geometry type must be Polygon or MultiPolygon")
    return geometry


def check_case_study(config_path: Path, aoi_path: Path | None = None) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    selected_aoi = aoi_path or (
        Path(config["aoi_path"]) if config.get("aoi_path") else None
    )
    event_date = date.fromisoformat(config["event_date"])
    credentials = {
        "client_id_present": bool(os.getenv("RESCUEX_CDSE_CLIENT_ID")),
        "client_secret_present": bool(os.getenv("RESCUEX_CDSE_CLIENT_SECRET")),
    }
    aoi_status = "MISSING_USER_INPUT"
    aoi_error = None
    if selected_aoi is not None:
        try:
            geometry = _extract_aoi_geometry(
                json.loads(selected_aoi.read_text(encoding="utf-8"))
            )
            AOI(geometry=geometry)
            aoi_status = "READY"
        except (OSError, json.JSONDecodeError, TypeError, ValueError, InvalidAOIError) as exc:
            aoi_status = "INVALID"
            aoi_error = f"{type(exc).__name__}: {exc}"
    cdse_ready = credentials["client_id_present"] and credentials["client_secret_present"]
    discovery_status = "READY_TO_RUN" if aoi_status == "READY" and cdse_ready else "BLOCKED"
    return {
        "phase": "10B",
        "status": "READY" if discovery_status == "READY_TO_RUN" else "BLOCKED",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "case_study": "Trishuli 2026",
        "event_date": {
            "value": event_date.isoformat(),
            "status": "READY",
            "source": EVENT_DATE_SOURCE,
        },
        "aoi": {
            "status": aoi_status,
            "source": "USER_SUPPLIED",
            "path": str(selected_aoi) if selected_aoi else None,
            "error": aoi_error,
        },
        "cdse_credentials": {
            "status": "READY" if cdse_ready else "BLOCKED",
            **credentials,
            "values_exposed": False,
        },
        "sentinel_discovery": {
            "status": discovery_status,
            "network_search_performed": False,
            "depends_on": ["event_date", "aoi", "cdse_credentials"],
        },
        "sentinel_pair": {"status": "NOT_EXECUTED"},
        "restrictions": {
            "emsr927": "VALIDATION_ONLY; not accessed",
            "downloads": "NOT_EXECUTED",
            "inference": "NOT_EXECUTED",
            "osm": "NOT_EXECUTED",
            "connectivity": "NOT_EXECUTED",
        },
        "warnings": [
            "AOI must be supplied by the team/user; no production geometry is inferred.",
            "This check performs no Sentinel or validation-data network request.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--aoi", type=Path, help="user/team-supplied GeoJSON AOI")
    args = parser.parse_args()
    report = check_case_study(args.config, args.aoi)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"CASE STUDY: {report['case_study']}")
    print(f"Event date: {report['event_date']['value']}")
    print(f"SOURCE: {report['event_date']['source']}")
    print(f"AOI: {report['aoi']['status']} — user/team-supplied GeoJSON required")
    print(f"CDSE credentials: {report['cdse_credentials']['status']}")
    print(f"Sentinel discovery: {report['sentinel_discovery']['status']}")
    return 0 if report["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
