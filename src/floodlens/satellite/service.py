from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Protocol

from .models import SatelliteScene, SatelliteSearchRequest, SatelliteSearchResult
from .selection import select_pair


class SceneProvider(Protocol):
    def search(self, request: SatelliteSearchRequest) -> list[SatelliteScene]:
        ...


class SatelliteService:
    def __init__(self, provider: SceneProvider):
        self.provider = provider

    def search(self, request: SatelliteSearchRequest) -> SatelliteSearchResult:
        return select_pair(request, self.provider.search(request))


def search_window(request: SatelliteSearchRequest) -> tuple[datetime, datetime]:
    start = datetime.combine(
        request.event_date - timedelta(days=request.search_window_before_days),
        time.min,
        tzinfo=timezone.utc,
    )
    end = datetime.combine(
        request.event_date + timedelta(days=request.search_window_after_days),
        time.max,
        tzinfo=timezone.utc,
    )
    return start, end
