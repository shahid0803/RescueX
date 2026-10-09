"""Verify the exact public CDSE Sentinel-1 pair without downloading imagery."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import shape

from floodlens.satellite.models import AOI

BEFORE_ID = "S1D_IW_GRDH_1SDV_20260816T122141_20260816T122206_004151_007980_B091_COG"
AFTER_ID = "S1D_IW_GRDH_1SDV_20260828T122141_20260828T122206_004326_007FA4_C73B_COG"
STAC_ITEM_URL = "https://stac.dataspace.copernicus.eu/v1/collections/sentinel-1-grd/items/"
EVENT_DATE = datetime(2026, 8, 26, tzinfo=timezone.utc)
MANIFEST_PATH = Path("data/manifests/trishuli_sentinel1_pair_manifest.json")


def fetch_item(scene_id: str) -> dict:
    with urllib.request.urlopen(STAC_ITEM_URL + scene_id, timeout=60) as response:
        return json.load(response)


def _asset_summary(asset: dict) -> dict:
    alternate = asset.get("alternate", {}).get("https", {})
    return {
        "href": asset.get("href"),
        "https_href": alternate.get("href"),
        "roles": asset.get("roles", []),
        "media_type": asset.get("type"),
        "size_bytes": asset.get("file:size"),
        "checksum": asset.get("file:checksum"),
        "polarization": asset.get("sar:polarizations", []),
        "cloud_optimized": "cloud-optimized" in asset.get("type", ""),
    }


def verify_item(item: dict, aoi: AOI, role: str) -> dict:
    properties = item.get("properties", {})
    footprint = shape(item["geometry"])
    target = shape(aoi.geometry)
    assets = {
        name: _asset_summary(asset)
        for name, asset in item.get("assets", {}).items()
        if name.lower() in {"vv", "vh"}
    }
    required_assets = {
        polarization: assets.get(polarization.lower())
        for polarization in ("VV", "VH")
    }
    acquisition = datetime.fromisoformat(properties["datetime"].replace("Z", "+00:00"))
    offset = EVENT_DATE - acquisition if role == "before" else acquisition - EVENT_DATE
    return {
        "scene_id": item["id"],
        "collection": item.get("collection"),
        "role": role,
        "acquisition_datetime": acquisition.isoformat(),
        "event_offset": str(offset),
        "platform": properties.get("platform"),
        "instrument": properties.get("instruments"),
        "product_type": properties.get("product:type"),
        "processing_level": properties.get("processing:level"),
        "instrument_mode": properties.get("sar:instrument_mode"),
        "orbit_direction": properties.get("sat:orbit_state"),
        "relative_orbit": properties.get("sat:relative_orbit"),
        "polarization": properties.get("sar:polarizations", []),
        "bbox": item.get("bbox"),
        "geometry": item.get("geometry"),
        "aoi_intersects": footprint.intersects(target),
        "aoi_fully_covered_by_footprint": footprint.covers(target),
        "assets": required_assets,
        "vv_vh_available": all(required_assets.values()),
    }


def verify_pair(aoi_document: dict, before_item: dict, after_item: dict) -> dict:
    if aoi_document.get("type") == "FeatureCollection":
        features = aoi_document.get("features", [])
        if len(features) != 1:
            raise ValueError("AOI FeatureCollection must contain exactly one feature")
        aoi_geometry = features[0].get("geometry")
    elif aoi_document.get("type") == "Feature":
        aoi_geometry = aoi_document.get("geometry")
    else:
        aoi_geometry = aoi_document
    aoi = AOI(geometry=aoi_geometry)
    before = verify_item(before_item, aoi, "before")
    after = verify_item(after_item, aoi, "after")
    compatibility_fields = (
        "relative_orbit", "orbit_direction", "instrument_mode", "platform",
        "product_type", "processing_level", "polarization",
    )
    compatibility = {
        field: before[field] == after[field] for field in compatibility_fields
    }
    pair_valid = (
        compatibility["relative_orbit"]
        and compatibility["orbit_direction"]
        and compatibility["instrument_mode"]
        and before["vv_vh_available"]
        and after["vv_vh_available"]
        and before["aoi_fully_covered_by_footprint"]
        and after["aoi_fully_covered_by_footprint"]
    )
    measurement_bytes = sum(
        item["assets"][pol]["size_bytes"]
        for item in (before, after)
        for pol in ("VV", "VH")
    )
    return {
        "phase": "10C",
        "status": "REAL_EXECUTED" if pair_valid else "FAILED",
        "case_study": "Trishuli 2026",
        "event_date": "2026-08-26",
        "aoi": {
            "path": "configs/case_studies/trishuli_2026_aoi.geojson",
            "validation_status": "valid",
            "bbox": list(aoi.bbox),
            "geometry": aoi.geometry,
        },
        "before": before,
        "after": after,
        "compatibility": compatibility,
        "coverage_status": (
            "VERIFIED_FOOTPRINT_COVERS_AOI"
            if before["aoi_fully_covered_by_footprint"] and after["aoi_fully_covered_by_footprint"]
            else "PARTIAL_OR_UNVERIFIED_COVERAGE"
        ),
        "vv_vh_verification": {
            "before": before["vv_vh_available"],
            "after": after["vv_vh_available"],
        },
        "estimated_measurement_download_bytes": measurement_bytes,
        "estimated_measurement_download_gib": measurement_bytes / (1024 ** 3),
        "authentication": {
            "client_id_present": bool(os.getenv("RESCUEX_CDSE_CLIENT_ID")),
            "client_secret_present": bool(os.getenv("RESCUEX_CDSE_CLIENT_SECRET")),
            "status": "READY" if os.getenv("RESCUEX_CDSE_CLIENT_ID") and os.getenv("RESCUEX_CDSE_CLIENT_SECRET") else "BLOCKED",
            "values_exposed": False,
        },
        "download": {
            "status": "NOT_EXECUTED",
            "imagery_downloaded": False,
            "recommended_next_method": "Sentinel Hub Process API bounded AOI request, if authenticated access and requested COG output are supported; otherwise authenticated direct VV/VH COG asset access with strict byte/disk checks.",
        },
        "provenance": {
            "source_catalog": "https://stac.dataspace.copernicus.eu/v1/",
            "verification_timestamp": datetime.now(timezone.utc).isoformat(),
            "selection": "User-specified exact pair; no EMSR927 or published damage source used.",
        },
        "warnings": [
            "Metadata footprint coverage is not a raster-level coverage guarantee.",
            "This is a verified candidate pair, not a flood result or damage map.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", type=Path, default=Path("configs/case_studies/trishuli_2026_aoi.geojson"))
    args = parser.parse_args()
    document = json.loads(args.aoi.read_text(encoding="utf-8"))
    report = verify_pair(document, fetch_item(BEFORE_ID), fetch_item(AFTER_ID))
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "REAL_EXECUTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
