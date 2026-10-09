from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .errors import InvalidAOIError


Sensor = Literal["sentinel-1", "sentinel-2"]


class AOI(BaseModel):
    geometry: dict[str, Any]
    crs: str = "EPSG:4326"
    bbox: tuple[float, float, float, float] | None = None
    area_km2: float | None = Field(default=None, ge=0)
    validation_status: Literal["valid"] = "valid"

    @model_validator(mode="after")
    def validate_geometry(self) -> "AOI":
        try:
            from shapely.geometry import shape
            from shapely.validation import explain_validity

            geom = shape(self.geometry)
            if geom.is_empty or not geom.is_valid:
                raise InvalidAOIError(explain_validity(geom))
            if not geom.bounds or any(
                coordinate < -180 or coordinate > 180
                for coordinate in (geom.bounds[0], geom.bounds[2])
            ):
                raise InvalidAOIError("longitude must be between -180 and 180")
            if any(coordinate < -90 or coordinate > 90 for coordinate in (geom.bounds[1], geom.bounds[3])):
                raise InvalidAOIError("latitude must be between -90 and 90")
            if self.bbox is None:
                object.__setattr__(self, "bbox", tuple(float(v) for v in geom.bounds))
            if self.area_km2 is None:
                object.__setattr__(self, "area_km2", 0.0)
        except ImportError:
            raise InvalidAOIError("Shapely is required for AOI validation")
        except (TypeError, ValueError, KeyError) as exc:
            raise InvalidAOIError("AOI must be valid GeoJSON geometry") from exc
        return self


class SatelliteScene(BaseModel):
    scene_id: str
    product_id: str
    satellite: str
    constellation: str = "Sentinel"
    sensor: Sensor
    mission: str
    product_type: str | None = None
    acquisition_datetime: datetime
    processing_level: str | None = None
    orbit_number: int | None = None
    relative_orbit: int | None = None
    orbit_direction: str | None = None
    footprint: dict[str, Any]
    bbox: tuple[float, float, float, float] | None = None
    crs: str | None = None
    resolution: float | None = None
    cloud_cover: float | None = Field(default=None, ge=0, le=100)
    polarization: list[str] = Field(default_factory=list)
    available_bands: list[str] = Field(default_factory=list)
    download_url_or_reference: str | None = None
    provider: str
    source_catalog: str
    file_size_if_available: int | None = Field(default=None, ge=0)
    checksum_if_available: str | None = None
    local_path: str | None = None
    download_status: Literal["not_downloaded", "downloading", "downloaded", "failed"] = "not_downloaded"
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("acquisition_datetime")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("acquisition_datetime must be timezone-aware")
        return value.astimezone(timezone.utc)


class SatelliteSearchRequest(BaseModel):
    aoi: AOI
    event_date: date
    sensor: Sensor
    search_window_before_days: int = Field(default=30, ge=1, le=365)
    search_window_after_days: int = Field(default=30, ge=1, le=365)
    max_cloud_percentage: float | None = Field(default=None, ge=0, le=100)
    limit: int = Field(default=50, ge=1, le=200)


class PairValidation(BaseModel):
    valid: bool
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    compatibility: dict[str, bool]


class SatelliteSearchResult(BaseModel):
    request: SatelliteSearchRequest
    candidates_before: list[SatelliteScene] = Field(default_factory=list)
    candidates_after: list[SatelliteScene] = Field(default_factory=list)
    selected_before: SatelliteScene | None = None
    selected_after: SatelliteScene | None = None
    validation: PairValidation | None = None
    selection_reasons: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(
        default_factory=lambda: {"query_timestamp": datetime.now(timezone.utc).isoformat()}
    )
