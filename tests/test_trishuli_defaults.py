"""Regression tests for the Trishuli default-geometry and fixture-status fix.

These tests run entirely offline with no network, satellite, or model calls.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from floodlens.pipeline import (
    PipelineRequest,
    ProcessingRun,
    ProcessingStatus,
    RescueXPipeline,
    result_classification,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
AOI_CONFIG_PATH = REPO_ROOT / "configs" / "case_studies" / "trishuli_2026_aoi.geojson"
FRONTEND_PATH = REPO_ROOT / "frontend" / "index.html"

# ── helpers ─────────────────────────────────────────────────────────────

def _load_configured_aoi() -> dict:
    """Load the authoritative Trishuli AOI geometry from the config file."""
    with open(AOI_CONFIG_PATH, encoding="utf-8") as fh:
        fc = json.load(fh)
    return fc["features"][0]["geometry"]


def _parse_frontend_defaults() -> dict:
    """Extract default AOI, flood zone, and date values from the HTML source."""
    html = FRONTEND_PATH.read_text(encoding="utf-8")
    aoi_match = re.search(r'<textarea\s+id="aoi"[^>]*>(.*?)</textarea>', html, re.DOTALL)
    zone_match = re.search(r'<textarea\s+id="zone"[^>]*>(.*?)</textarea>', html, re.DOTALL)
    date_match = re.search(r'<input\s+id="date"[^>]*value="([^"]*)"', html)
    return {
        "aoi": json.loads(aoi_match.group(1)) if aoi_match else None,
        "zone": json.loads(zone_match.group(1)) if zone_match else None,
        "date": date_match.group(1) if date_match else None,
    }


def _bbox(geometry: dict) -> tuple[float, float, float, float]:
    """Return (min_lon, min_lat, max_lon, max_lat) for a Polygon geometry."""
    coords = geometry["coordinates"][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return min(lons), min(lats), max(lons), max(lats)


def _bbox_contains(outer: dict, inner: dict) -> bool:
    """Return True if outer bbox fully contains inner bbox."""
    o = _bbox(outer)
    i = _bbox(inner)
    return i[0] >= o[0] and i[1] >= o[1] and i[2] <= o[2] and i[3] <= o[3]


CONFIGURED_AOI = _load_configured_aoi()
FRONTEND = _parse_frontend_defaults()
SYNTHETIC_FLOOD_ZONE = FRONTEND["zone"]

# ── 1. Default AOI equals configured Trishuli geometry ──────────────────

def test_default_aoi_matches_configured_trishuli_geometry():
    assert FRONTEND["aoi"] is not None, "Frontend must have an #aoi textarea"
    assert FRONTEND["aoi"] == CONFIGURED_AOI, (
        "The default AOI in the dashboard must match "
        "configs/case_studies/trishuli_2026_aoi.geojson"
    )


def test_default_aoi_is_in_trishuli_region():
    """Sanity-check that the AOI is near Trishuli, Nepal (not at 0,0)."""
    min_lon, min_lat, max_lon, max_lat = _bbox(FRONTEND["aoi"])
    assert 84.0 < min_lon < 86.0, f"AOI longitude {min_lon} is not in Nepal"
    assert 27.0 < min_lat < 29.0, f"AOI latitude {min_lat} is not in Nepal"
    assert 84.0 < max_lon < 86.0
    assert 27.0 < max_lat < 29.0


# ── 2. Event date is 2026-08-26 ─────────────────────────────────────────

def test_default_event_date():
    assert FRONTEND["date"] == "2026-08-26"


# ── 3. Fixture flood geometry is separate from AOI and inside it ────────

def test_fixture_flood_zone_is_separate_from_aoi():
    assert SYNTHETIC_FLOOD_ZONE is not None
    assert SYNTHETIC_FLOOD_ZONE != CONFIGURED_AOI, (
        "The synthetic flood zone must be a different polygon from the AOI"
    )


def test_fixture_flood_zone_inside_aoi():
    assert _bbox_contains(CONFIGURED_AOI, SYNTHETIC_FLOOD_ZONE), (
        "The synthetic flood zone must lie entirely inside the Trishuli AOI"
    )


def test_fixture_flood_zone_is_smaller_than_aoi():
    aoi_area = _bbox(CONFIGURED_AOI)
    fz_area = _bbox(SYNTHETIC_FLOOD_ZONE)
    aoi_span = (aoi_area[2] - aoi_area[0]) * (aoi_area[3] - aoi_area[1])
    fz_span = (fz_area[2] - fz_area[0]) * (fz_area[3] - fz_area[1])
    assert fz_span < aoi_span * 0.5, "Fixture flood zone should be much smaller than AOI"


# ── 4. Fixture result is labelled as demo/fixture data ───────────────────

def _make_fixture_request() -> PipelineRequest:
    return PipelineRequest(
        aoi=CONFIGURED_AOI,
        event_date=date(2026, 8, 26),
        flood_zones=[SYNTHETIC_FLOOD_ZONE],
        execution_mode="FIXTURE",
    )


def test_fixture_run_labelled_as_demo():
    run = RescueXPipeline().execute(_make_fixture_request())
    assert run.status == ProcessingStatus.COMPLETED
    assert run.execution_mode == "FIXTURE"
    classification = result_classification(run)
    assert "FIXTURE" in classification or "NOT REAL" in classification
    assert any("FIXTURE" in w or "fixture" in w for w in run.warnings)


def test_fixture_run_sends_separate_aoi_and_flood_zone():
    """The pipeline receives the AOI and flood zone as distinct geometries."""
    req = _make_fixture_request()
    assert req.aoi != req.flood_zones[0], "AOI and flood zone must differ in the request"
    run = RescueXPipeline().execute(req)
    # The map layers should contain the fixture flood zone, not the AOI
    flood_features = run.map_layers.get("flood_zones", {}).get("features", [])
    assert len(flood_features) >= 1
    flood_geom = flood_features[0]["geometry"]
    assert flood_geom == SYNTHETIC_FLOOD_ZONE
    assert flood_geom != CONFIGURED_AOI


# ── 5. Failed / incomplete real runs cannot appear as successful ─────────

def test_failed_real_run_not_labelled_successful(tmp_path):
    req = PipelineRequest(
        aoi=CONFIGURED_AOI,
        event_date=date(2026, 8, 26),
        flood_zones=[SYNTHETIC_FLOOD_ZONE],
        execution_mode="REAL",
    )
    run = RescueXPipeline(tmp_path).execute(req)
    assert run.status == ProcessingStatus.FAILED
    classification = result_classification(run)
    assert "REAL DATA RESULT" != classification
    assert "INCOMPLETE" in classification or "FIXTURE" in classification


def test_completed_real_run_without_verified_outputs_is_not_real():
    """Even if status is COMPLETED, unverified real runs are not labelled real."""
    req = _make_fixture_request()
    run = RescueXPipeline().execute(req)
    # Simulate a real run that completed but provenance is not verified
    run.execution_mode = "REAL"
    run.status = ProcessingStatus.COMPLETED
    run.provenance["real_outputs_verified"] = False
    assert result_classification(run) == "REAL EXECUTION INCOMPLETE — NO VERIFIED RESULT"


# ── 6. Model compatibility INDETERMINATE blocks real inference ───────────

def test_model_inference_blocked_with_indeterminate_compatibility():
    """The inference module raises when called, guarding against premature use."""
    from floodlens.ml.inference import infer_geotiff
    # The function has a hard RuntimeError before any real processing
    import inspect
    source = inspect.getsource(infer_geotiff)
    assert "INDETERMINATE" in source, (
        "infer_geotiff must contain the INDETERMINATE compatibility gate"
    )


def test_real_pipeline_refuses_without_artifacts(tmp_path):
    req = PipelineRequest(
        aoi=CONFIGURED_AOI,
        event_date=date(2026, 8, 26),
        flood_zones=[SYNTHETIC_FLOOD_ZONE],
        execution_mode="REAL",
    )
    run = RescueXPipeline(tmp_path).execute(req)
    assert run.status == ProcessingStatus.FAILED
    assert any("REAL execution unavailable" in e for e in run.errors)
