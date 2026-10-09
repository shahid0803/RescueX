from datetime import date

import pytest

from floodlens.connectivity import (
    BlockedRoad,
    BlockedRoadSet,
    ConnectivityConfig,
    Phase4RoadImpactAdapter,
    analyze_connectivity,
)
from floodlens.models import Point, Road


def road(identifier: str, start: str, end: str, a: tuple[float, float], b: tuple[float, float]) -> Road:
    return Road(
        id=identifier, start=start, end=end, length_m=1,
        geometry=[Point(id=f"{identifier}-a", x=a[0], y=a[1]), Point(id=f"{identifier}-b", x=b[0], y=b[1])],
    )


def config() -> ConnectivityConfig:
    return ConnectivityConfig(event_date=date(2026, 8, 1), osm_snapshot_date=date(2026, 7, 27))


def test_blocked_edge_cuts_off_settlement_and_preserves_path_evidence():
    roads = [road("r1", "village", "town", (0, 0), (1, 0))]
    result = analyze_connectivity(
        roads, [Point(id="settlement", x=0, y=0)], [Point(id="town", x=1, y=0)], [],
        BlockedRoadSet(roads=[BlockedRoad(segment_id="r1")]), config(),
    )
    item = result.settlements[0]
    assert item.cut_off_from_town is True
    assert item.status == "CUT_OFF"
    assert item.path_before == ["r1"]
    assert item.path_after is None
    assert result.diagnostics["blocked_edges"] == ["r1"]


def test_alternate_route_remains_connected():
    roads = [
        road("a", "village", "junction", (0, 0), (1, 0)),
        road("b", "junction", "town", (1, 0), (2, 0)),
        road("c", "village", "town", (0, 0), (2, 0)),
    ]
    result = analyze_connectivity(
        roads, [Point(id="settlement", x=0, y=0)], [Point(id="town", x=2, y=0)], [],
        BlockedRoadSet(roads=[BlockedRoad(segment_id="a")]), config(),
    )
    assert result.settlements[0].cut_off_from_town is False
    assert result.settlements[0].town_connected_after is True


def test_no_baseline_route_is_not_new_cutoff_and_snapshot_is_required():
    roads = [road("r1", "other", "town", (0, 0), (1, 0))]
    result = analyze_connectivity(
        roads, [Point(id="settlement", x=1000, y=1000)], [Point(id="town", x=1, y=0)], [],
        BlockedRoadSet(), config(),
    )
    assert result.settlements[0].status == "UNMAPPED_SETTLEMENT"
    with pytest.raises(ValueError, match="earlier"):
        ConnectivityConfig(event_date=date(2026, 7, 27), osm_snapshot_date=date(2026, 7, 27)).validate_snapshot()


def test_phase4_adapter_records_unknown_block_match():
    result = analyze_connectivity(
        [road("r1", "village", "town", (0, 0), (1, 0))],
        [Point(id="settlement", x=0, y=0)], [Point(id="town", x=1, y=0)], [],
        Phase4RoadImpactAdapter.adapt({"potentially_blocked_roads": [{"segment_id": "missing"}]}), config(),
    )
    assert result.status == "WARNING"
    assert result.diagnostics["blocked_match_failures"] == ["missing"]
