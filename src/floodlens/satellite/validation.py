from __future__ import annotations

from datetime import date, datetime, timezone

from .models import AOI, PairValidation, SatelliteScene


def _overlap(a: dict, b: dict) -> bool:
    from shapely.geometry import shape

    return shape(a).intersects(shape(b))


def validate_sentinel1_pair(
    before: SatelliteScene, after: SatelliteScene, aoi: AOI, event_date: date
) -> PairValidation:
    compatibility = {
        "mission": before.mission == after.mission,
        "processing_level": before.processing_level == after.processing_level,
        "relative_orbit": before.relative_orbit is not None
        and before.relative_orbit == after.relative_orbit,
        "orbit_direction": before.orbit_direction is not None
        and before.orbit_direction == after.orbit_direction,
        "spatial_overlap": _overlap(before.footprint, after.footprint)
        and _overlap(before.footprint, aoi.geometry)
        and _overlap(after.footprint, aoi.geometry),
        "temporal_relationship": before.acquisition_datetime < datetime.combine(
            event_date, datetime.min.time(), tzinfo=timezone.utc
        )
        and after.acquisition_datetime > datetime.combine(
            event_date, datetime.min.time(), tzinfo=timezone.utc
        ),
    }
    reasons = [name for name, valid in compatibility.items() if not valid]
    warnings = []
    if compatibility["relative_orbit"] is False:
        warnings.append("different or unknown relative orbit; pixel comparison may be unreliable")
    if compatibility["orbit_direction"] is False:
        warnings.append("different or unknown orbit direction")
    valid = all(
        compatibility[key]
        for key in ("mission", "processing_level", "spatial_overlap", "temporal_relationship")
    )
    return PairValidation(valid=valid, reasons=reasons, warnings=warnings, compatibility=compatibility)
