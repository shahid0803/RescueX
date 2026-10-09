from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class Point(BaseModel):
    id: str
    x: float
    y: float


class Road(BaseModel):
    id: str
    start: str
    end: str
    length_m: float = Field(gt=0)
    geometry: list[Point] = Field(min_length=2)


class Feature(BaseModel):
    id: str
    geometry: dict[str, Any]
    properties: dict[str, Any] = Field(default_factory=dict)


class RunRequest(BaseModel):
    aoi: dict[str, Any]
    event_date: date
    flood_zones: list[dict[str, Any]] = Field(min_length=1)
    buildings: list[Feature] = Field(default_factory=list)
    roads: list[Road] = Field(default_factory=list)
    bridges: list[Feature] = Field(default_factory=list)
    settlements: list[Point] = Field(default_factory=list)
    destinations: list[Point] = Field(default_factory=list)
    source_manifest: dict[str, Any] = Field(default_factory=dict)
    road_block_threshold: float = Field(default=0.5, gt=0, le=1)
    building_overlap_threshold: float = Field(default=0.1, ge=0, le=1)


class RunResponse(BaseModel):
    run_id: str
    created_at: datetime
    event_date: date
    results: dict[str, Any]
    provenance: dict[str, Any]
    report: str
