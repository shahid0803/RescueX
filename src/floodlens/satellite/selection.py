from __future__ import annotations

from datetime import date, datetime, time, timezone

from .models import AOI, SatelliteScene, SatelliteSearchRequest, SatelliteSearchResult
from .validation import validate_sentinel1_pair


def _coverage(scene: SatelliteScene, aoi: AOI) -> float:
    from shapely.geometry import shape

    footprint = shape(scene.footprint)
    target = shape(aoi.geometry)
    if not footprint.intersects(target):
        return 0.0
    return min(1.0, footprint.intersection(target).area / target.area) if target.area else 1.0


def _rank(scene: SatelliteScene, request: SatelliteSearchRequest, role: str) -> tuple:
    event = datetime.combine(request.event_date, time.min, tzinfo=timezone.utc)
    delta = abs((scene.acquisition_datetime - event).total_seconds())
    cloud = scene.cloud_cover if scene.cloud_cover is not None else 0.0
    return (-_coverage(scene, request.aoi), delta, cloud, scene.scene_id)


def select_pair(
    request: SatelliteSearchRequest, candidates: list[SatelliteScene]
) -> SatelliteSearchResult:
    event = datetime.combine(request.event_date, time.min, tzinfo=timezone.utc)
    before = sorted(
        [s for s in candidates if s.acquisition_datetime < event and _coverage(s, request.aoi) > 0],
        key=lambda s: _rank(s, request, "before"),
    )
    after = sorted(
        [s for s in candidates if s.acquisition_datetime > event and _coverage(s, request.aoi) > 0],
        key=lambda s: _rank(s, request, "after"),
    )
    selected_before = selected_after = None
    validation = None
    reasons: list[str] = []
    if before and after:
        pairs = sorted(
            ((b, a) for b in before[: request.limit] for a in after[: request.limit]),
            key=lambda pair: (
                not (pair[0].relative_orbit is not None and pair[0].relative_orbit == pair[1].relative_orbit),
                not (pair[0].orbit_direction and pair[0].orbit_direction == pair[1].orbit_direction),
                _rank(pair[0], request, "before"),
                _rank(pair[1], request, "after"),
            ),
        )
        selected_before, selected_after = pairs[0]
        validation = validate_sentinel1_pair(
            selected_before, selected_after, request.aoi, request.event_date
        ) if request.sensor == "sentinel-1" else None
        reasons = [
            f"selected {selected_before.scene_id} as nearest compatible pre-event candidate",
            f"selected {selected_after.scene_id} as nearest compatible post-event candidate",
        ]
        if selected_before.relative_orbit == selected_after.relative_orbit:
            reasons.append("same relative orbit preferred")
    return SatelliteSearchResult(
        request=request,
        candidates_before=before[: request.limit],
        candidates_after=after[: request.limit],
        selected_before=selected_before,
        selected_after=selected_after,
        validation=validation,
        selection_reasons=reasons,
    )
