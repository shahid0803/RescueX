import json
from pathlib import Path

import pytest

from scripts.phase10b_case_study_check import check_case_study


CONFIG = Path("configs/case_studies/trishuli_2026.json")


def test_trishuli_event_date_is_authoritative_and_aoi_is_missing(monkeypatch):
    monkeypatch.delenv("RESCUEX_CDSE_CLIENT_ID", raising=False)
    monkeypatch.delenv("RESCUEX_CDSE_CLIENT_SECRET", raising=False)
    report = check_case_study(CONFIG)
    assert report["event_date"]["value"] == "2026-08-26"
    assert report["event_date"]["status"] == "READY"
    assert report["aoi"]["status"] == "MISSING_USER_INPUT"
    assert report["cdse_credentials"]["status"] == "BLOCKED"
    assert report["sentinel_discovery"]["status"] == "BLOCKED"
    assert report["sentinel_discovery"]["network_search_performed"] is False


def test_template_contains_no_geometry():
    template = json.loads(
        Path("configs/case_studies/trishuli_2026.template.geojson").read_text()
    )
    assert template["features"] == []
    assert "REPLACE" in template["properties"]["status"]


def write_aoi(tmp_path, document):
    path = tmp_path / "aoi.geojson"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_one_feature_polygon_feature_collection_is_accepted(tmp_path):
    path = write_aoi(
        tmp_path,
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[85, 27], [85, 28], [86, 28], [86, 27], [85, 27]]],
                    },
                }
            ],
        },
    )
    report = check_case_study(CONFIG, path)
    assert report["aoi"]["status"] == "READY"


@pytest.mark.parametrize(
    "document",
    [
        {"type": "FeatureCollection", "features": []},
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": None},
                {"type": "Feature", "geometry": None},
            ],
        },
        {"type": "FeatureCollection", "features": [{"type": "Feature"}]},
        {"type": "Point", "coordinates": [85, 27]},
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}},
    ],
)
def test_invalid_or_ambiguous_aoi_is_rejected(tmp_path, document):
    report = check_case_study(CONFIG, write_aoi(tmp_path, document))
    assert report["aoi"]["status"] == "INVALID"
    assert report["aoi"]["error"]
