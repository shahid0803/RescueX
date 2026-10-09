"""Perform a safe, metadata-only CDSE Trishuli pair readiness/discovery run."""

from __future__ import annotations

import argparse
import json
import os
import platform
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from floodlens.satellite.auth import CopernicusAuthenticator
from floodlens.satellite.models import AOI, SatelliteSearchRequest
from floodlens.satellite.service import SatelliteService, search_window
from floodlens.satellite.stac import CDSEStacProvider

STAC_ROOT = "https://stac.dataspace.copernicus.eu/v1/"
TOKEN_ENDPOINT = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
REPORT_PATH = Path("data/manifests/trishuli_sentinel1_pair_manifest.json")


def endpoint_status(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return {"reachable": True, "status": response.status}
    except urllib.error.HTTPError as exc:
        return {"reachable": True, "status": exc.code}
    except (OSError, urllib.error.URLError) as exc:
        return {"reachable": False, "error_type": type(exc).__name__}


def authoritative_case_study_sources(root: Path) -> dict:
    candidates = [
        "configs/trishuli.json",
        "configs/trishuli.geojson",
        "configs/case-studies/trishuli.json",
        "configs/case-studies/trishuli.geojson",
        "examples/trishuli.json",
        "examples/trishuli.geojson",
    ]
    return {
        "searched_paths": candidates,
        "found_paths": [path for path in candidates if (root / path).is_file()],
        "status": "FOUND" if any((root / path).is_file() for path in candidates) else "MISSING",
    }


def scene_dict(scene) -> dict:
    return scene.model_dump(mode="json")


def run(root: Path, aoi_path: Path | None, event_date: str | None) -> dict:
    client_id_present = bool(os.getenv("RESCUEX_CDSE_CLIENT_ID"))
    secret_present = bool(os.getenv("RESCUEX_CDSE_CLIENT_SECRET"))
    source_audit = authoritative_case_study_sources(root)
    authentication = {
        "client_id_present": client_id_present,
        "client_secret_present": secret_present,
        "credentials_complete": client_id_present and secret_present,
        "token_endpoint": TOKEN_ENDPOINT,
        "token_request": "NOT_EXECUTED",
    }
    report = {
        "phase": "10A",
        "status": "BLOCKED",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": platform.python_version()},
        "source_catalog": STAC_ROOT,
        "public_endpoint_checks": {
            "stac_root": endpoint_status(STAC_ROOT),
            "token_endpoint": endpoint_status(TOKEN_ENDPOINT),
        },
        "authentication": authentication,
        "case_study_source_audit": source_audit,
        "aoi": {"status": "NOT_AVAILABLE", "path": str(aoi_path) if aoi_path else None},
        "event_date": {
            "status": "READY" if event_date else "NOT_AVAILABLE",
            "value": event_date,
            "source": "CLI input" if event_date else "MISSING",
        },
        "candidates_considered": [],
        "selected_candidate_pair": None,
        "download": {
            "status": "NOT_EXECUTED",
            "imagery_downloaded": False,
            "reason": "Metadata-only phase stopped before query because authoritative AOI/date were not supplied.",
        },
        "warnings": [
            "No authoritative Trishuli AOI geometry or event date exists in the repository.",
            "No scene ID, availability, coverage, or pair was fabricated.",
        ],
        "provenance": {
            "aoi_source": "MISSING",
            "event_date_source": "MISSING",
            "pairing": "NOT_EXECUTED",
        },
    }
    if aoi_path is None or event_date is None:
        return report

    geometry = json.loads(aoi_path.read_text(encoding="utf-8"))
    request = SatelliteSearchRequest(
        aoi=AOI(geometry=geometry),
        event_date=event_date,
        sensor="sentinel-1",
        search_window_before_days=30,
        search_window_after_days=30,
        limit=100,
    )
    authenticator = CopernicusAuthenticator.from_env()
    if authentication["credentials_complete"]:
        authenticator.get_token()
        authentication["token_request"] = "SUCCEEDED"
    else:
        authentication["token_request"] = "BLOCKED_MISSING_CREDENTIALS"
    start, end = search_window(request)
    result = SatelliteService(
        CDSEStacProvider(authenticator=authenticator if authentication["credentials_complete"] else None)
    ).search(request)
    report.update({
        "status": "REAL_EXECUTED",
        "aoi": {"status": "VERIFIED_INPUT", "path": str(aoi_path), "geometry": geometry},
        "event_date": {"status": "VERIFIED_INPUT", "value": event_date},
        "search_window": {"start": start.isoformat(), "end": end.isoformat()},
        "candidates_before": [scene_dict(scene) for scene in result.candidates_before],
        "candidates_after": [scene_dict(scene) for scene in result.candidates_after],
        "candidates_considered": [scene.scene_id for scene in result.candidates_before + result.candidates_after],
        "selected_candidate_pair": {
            "before": scene_dict(result.selected_before) if result.selected_before else None,
            "after": scene_dict(result.selected_after) if result.selected_after else None,
            "validation": result.validation.model_dump(mode="json") if result.validation else None,
            "selection_reasons": result.selection_reasons,
        },
        "download": {
            "status": "NOT_EXECUTED",
            "imagery_downloaded": False,
            "reason": "Phase 10A ends at metadata-only pair validation.",
        },
        "provenance": {
            "aoi_source": str(aoi_path),
            "event_date_source": "CLI input",
            "pairing": "existing deterministic RescueX selector",
        },
    })
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", type=Path, help="authoritative Trishuli GeoJSON geometry")
    parser.add_argument("--event-date", help="authoritative event date, YYYY-MM-DD")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    report = run(args.root, args.aoi, args.event_date)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "REAL_EXECUTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
