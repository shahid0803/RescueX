from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, Field, model_validator


class Provenance(BaseModel):
    source_id: str
    artifact_id: str
    retrieved_at: datetime
    sha256: str = Field(min_length=64, max_length=64)
    metadata: dict[str, str] = Field(default_factory=dict)


class EventContext(BaseModel):
    aoi: dict
    event_date: date
    osm_snapshot_date: date | None = None

    @model_validator(mode="after")
    def pre_event_osm(self) -> "EventContext":
        if self.osm_snapshot_date and self.osm_snapshot_date >= self.event_date:
            raise ValueError("OSM snapshot must predate the event date")
        return self


class ScenePair(BaseModel):
    before: Provenance
    after: Provenance
    sensor: str
    same_orbit: bool | None = None

    @model_validator(mode="after")
    def pair_is_distinct(self) -> "ScenePair":
        if self.before.artifact_id == self.after.artifact_id:
            raise ValueError("before and after scenes must be distinct artifacts")
        return self


class SegmentationArtifact(BaseModel):
    provenance: Provenance
    crs: str
    transform: list[float] = Field(min_length=6, max_length=6)
    bounds: list[float] = Field(min_length=4, max_length=4)
    mask_uri: str
    model_version: str


class AnalysisRun(BaseModel):
    run_id: str
    context: EventContext
    scenes: list[ScenePair] = Field(default_factory=list)
    flood_mask: SegmentationArtifact | None = None
    created_at: datetime
