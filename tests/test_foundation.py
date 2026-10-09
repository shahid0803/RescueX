from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from floodlens.config import Settings
from floodlens.contracts import EventContext, Provenance, ScenePair
from floodlens.registry import SourceRegistry


REGISTRY = SourceRegistry(Path("configs/data-sources.json"))


def provenance(source_id: str, artifact_id: str) -> Provenance:
    return Provenance(
        source_id=source_id,
        artifact_id=artifact_id,
        retrieved_at=datetime.now(timezone.utc),
        sha256="a" * 64,
    )


def test_registry_rejects_validation_map_in_production():
    with pytest.raises(ValueError, match="not allowed"):
        REGISTRY.assert_allowed("copernicus-emsr927", "production")


def test_registry_requires_source_metadata():
    with pytest.raises(ValueError, match="missing required"):
        REGISTRY.validate_metadata("osm-pre-event", {"sha256": "a"}, "production")


def test_event_requires_pre_event_osm_snapshot():
    with pytest.raises(ValueError, match="predate"):
        EventContext(aoi={}, event_date=date(2026, 8, 15), osm_snapshot_date=date(2026, 8, 15))


def test_scene_pair_cannot_reuse_artifact():
    with pytest.raises(ValueError, match="distinct"):
        ScenePair(
            before=provenance("sentinel-1", "same"),
            after=provenance("sentinel-1", "same"),
            sensor="sentinel-1",
        )


def test_settings_are_safe_and_reproducible(monkeypatch):
    monkeypatch.setenv("RESCUEX_MAX_AOI_KM2", "10")
    settings = Settings.from_env()
    assert settings.max_aoi_km2 == 10
