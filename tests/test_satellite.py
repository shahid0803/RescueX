from datetime import datetime, timezone
from pathlib import Path

import pytest

from floodlens.satellite.auth import CopernicusAuthenticator
from floodlens.satellite.download import DownloadService
from floodlens.satellite.errors import NoCredentialsError
from floodlens.satellite.models import AOI, SatelliteScene, SatelliteSearchRequest
from floodlens.satellite.selection import select_pair
from floodlens.satellite.service import SatelliteService


def polygon(x0=0, y0=0, x1=2, y1=2):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def scene(scene_id, when, orbit=12, sensor="sentinel-1", cloud=None, footprint=None):
    return SatelliteScene(
        scene_id=scene_id,
        product_id=scene_id,
        satellite="Sentinel-1A",
        sensor=sensor,
        mission="S1",
        acquisition_datetime=datetime.fromisoformat(when).replace(tzinfo=timezone.utc),
        processing_level="L1",
        relative_orbit=orbit,
        orbit_direction="ASCENDING",
        footprint=footprint or polygon(),
        cloud_cover=cloud,
        provider="fixture",
        source_catalog="fixture",
    )


def request(sensor="sentinel-1"):
    return SatelliteSearchRequest(
        aoi=AOI(geometry=polygon()),
        event_date="2026-08-15",
        sensor=sensor,
        search_window_before_days=30,
        search_window_after_days=30,
    )


def test_aoi_rejects_invalid_coordinates():
    with pytest.raises(Exception):
        AOI(geometry=polygon(0, 0, 200, 2))


def test_selection_prefers_same_relative_orbit():
    result = select_pair(
        request(),
        [
            scene("before-other", "2026-08-10T00:00:00", orbit=3),
            scene("before-same", "2026-08-09T00:00:00", orbit=12),
            scene("after", "2026-08-20T00:00:00", orbit=12),
        ],
    )
    assert result.selected_before.scene_id == "before-same"
    assert result.validation is not None
    assert result.validation.valid is True
    assert result.validation.compatibility["relative_orbit"] is True


def test_selection_does_not_fabricate_when_one_side_is_missing():
    result = select_pair(request(), [scene("before", "2026-08-10T00:00:00")])
    assert result.selected_before is None
    assert result.selected_after is None


def test_sentinel2_cloud_is_retained_and_ranked():
    result = select_pair(
        request("sentinel-2"),
        [
            scene("cloudy", "2026-08-10T00:00:00", sensor="sentinel-2", cloud=80),
            scene("clear", "2026-08-11T00:00:00", sensor="sentinel-2", cloud=5),
            scene("after", "2026-08-20T00:00:00", sensor="sentinel-2", cloud=10),
        ],
    )
    assert result.selected_before.scene_id == "clear"
    assert result.selected_after.scene_id == "after"


def test_auth_does_not_accept_missing_credentials():
    with pytest.raises(NoCredentialsError):
        CopernicusAuthenticator().get_token()


def test_download_reuses_existing_file(tmp_path: Path):
    service = DownloadService(tmp_path, CopernicusAuthenticator())
    item = scene("cached", "2026-08-10T00:00:00")
    destination = service._destination(item)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"fixture")
    downloaded = service.download(item)
    assert downloaded.download_status == "downloaded"
    assert len(service.manifest.read_text(encoding="utf-8").splitlines()) == 1


def test_download_removes_corrupt_cached_file_when_checksum_is_known(tmp_path: Path):
    service = DownloadService(tmp_path, CopernicusAuthenticator())
    item = scene("corrupt", "2026-08-10T00:00:00").model_copy(
        update={"checksum_if_available": "b" * 64}
    )
    destination = service._destination(item)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"corrupt")
    with pytest.raises(Exception):
        service.download(item)
    assert not destination.exists()


class FixtureProvider:
    def search(self, request):
        return [scene("before", "2026-08-10T00:00:00"), scene("after", "2026-08-20T00:00:00")]


def test_service_uses_provider_boundary():
    result = SatelliteService(FixtureProvider()).search(request())
    assert result.selected_before.scene_id == "before"
