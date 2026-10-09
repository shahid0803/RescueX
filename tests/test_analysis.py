import pytest
from pathlib import Path

from floodlens.analysis import infrastructure_impact
from floodlens.models import Feature, Point, Road
from floodlens.phase4 import DEVELOPMENT_FIXTURE_LABEL, classify_phase3_artifacts, run_development_fixture


def polygon(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]]]}


def test_overlap_thresholds_are_computed_from_geometry():
    result = infrastructure_impact(
        [polygon(0, 0, 1, 1)],
        [Feature(id="b1", geometry=polygon(0, 0, 0.5, 0.5))],
        [Road(id="r1", start="a", end="b", length_m=100, geometry=[Point(id="p1",x=-1,y=.5), Point(id="p2",x=2,y=.5)])],
        [],
        building_threshold=0.1,
        road_threshold=0.2,
    )
    assert result["affected_buildings"][0]["id"] == "b1"
    assert result["affected_roads"][0]["affected_length_m"] == pytest.approx(100 / 3)


def test_phase4_fixture_is_explicitly_not_real():
    result = run_development_fixture(
        [polygon(0, 0, 1, 1)],
        [Feature(id="b1", geometry=polygon(0, 0, 0.5, 0.5))],
        [Road(id="r1", start="village", end="town", length_m=100,
              geometry=[Point(id="p1", x=-1, y=.5), Point(id="p2", x=2, y=.5)])],
        [],
        [Point(id="village", x=0, y=0)],
        [Point(id="town", x=1, y=1)],
    )
    assert result["label"] == DEVELOPMENT_FIXTURE_LABEL
    assert result["real_satellite_result"] is False


def test_phase3_artifact_classification_reports_no_real_output(tmp_path: Path):
    report = classify_phase3_artifacts(tmp_path)
    assert report["real_checkpoint_exists"] is False
    assert report["real_georeferenced_mask_exists"] is False
