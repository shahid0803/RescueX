import json

from scripts.phase10c_pair_verify import verify_pair


def item(scene_id, when, relative=85):
    return {
        "id": scene_id,
        "collection": "sentinel-1-grd",
        "properties": {
            "datetime": when,
            "platform": "sentinel-1d",
            "instruments": ["sar"],
            "product:type": "IW_GRDH_1S",
            "processing:level": "L1",
            "sar:instrument_mode": "IW",
            "sat:orbit_state": "ascending",
            "sat:relative_orbit": relative,
            "sar:polarizations": ["VV", "VH"],
        },
        "bbox": [85, 27, 86, 28],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[85, 27], [85, 28], [86, 28], [86, 27], [85, 27]]],
        },
        "assets": {
            "vv": {"href": "https://example/vv.tif", "roles": ["data"], "type": "image/tiff; profile=cloud-optimized", "file:size": 10, "sar:polarizations": ["VV"]},
            "vh": {"href": "https://example/vh.tif", "roles": ["data"], "type": "image/tiff; profile=cloud-optimized", "file:size": 20, "sar:polarizations": ["VH"]},
        },
    }


def aoi():
    return {"type": "Polygon", "coordinates": [[[85, 27], [85, 28], [86, 28], [86, 27], [85, 27]]]}


def test_exact_pair_verification_checks_assets_orbit_and_coverage():
    result = verify_pair(
        aoi(),
        item("before", "2026-08-16T12:21:41Z"),
        item("after", "2026-08-28T12:21:41Z"),
    )
    assert result["status"] == "REAL_EXECUTED"
    assert result["compatibility"]["relative_orbit"] is True
    assert result["vv_vh_verification"] == {"before": True, "after": True}
    assert result["coverage_status"] == "VERIFIED_FOOTPRINT_COVERS_AOI"
    assert result["estimated_measurement_download_bytes"] == 60


def test_pair_verification_flags_track_mismatch():
    result = verify_pair(
        aoi(),
        item("before", "2026-08-16T12:21:41Z"),
        item("after", "2026-08-28T12:21:41Z", relative=86),
    )
    assert result["status"] == "FAILED"
    assert result["compatibility"]["relative_orbit"] is False
