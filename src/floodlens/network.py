from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable

from .models import Point, Road


def _components(roads: Iterable[Road], blocked: set[str]) -> dict[str, int]:
    graph: dict[str, set[str]] = defaultdict(set)
    for road in roads:
        if road.id not in blocked:
            graph[road.start].add(road.end)
            graph[road.end].add(road.start)
    component: dict[str, int] = {}
    number = 0
    for node in graph:
        if node in component:
            continue
        queue = deque([node])
        component[node] = number
        while queue:
            current = queue.popleft()
            for neighbor in graph[current]:
                if neighbor not in component:
                    component[neighbor] = number
                    queue.append(neighbor)
        number += 1
    return component


def connectivity_analysis(
    roads: list[Road],
    settlements: list[Point],
    destinations: list[Point],
    blocked: set[str],
) -> dict[str, object]:
    if not destinations:
        return {"settlements": [], "cut_off_count": 0, "assumption": "no destinations supplied"}
    baseline = _components(roads, set())
    after = _components(roads, blocked)
    destination_components = {baseline.get(point.id) for point in destinations}
    destination_components.discard(None)
    after_destination_components = {after.get(point.id) for point in destinations}
    after_destination_components.discard(None)
    results = []
    for settlement in settlements:
        before_connected = baseline.get(settlement.id) in destination_components
        after_connected = after.get(settlement.id) in after_destination_components
        results.append(
            {
                "settlement_id": settlement.id,
                "baseline_connected": before_connected,
                "post_event_connected": after_connected,
                "cut_off": bool(before_connected and not after_connected),
                "blocked_road_ids": sorted(blocked) if before_connected and not after_connected else [],
            }
        )
    return {
        "settlements": results,
        "cut_off_count": sum(1 for item in results if item["cut_off"]),
        "blocked_road_ids": sorted(blocked),
        "method": "connected components on pre-event graph with affected edges removed",
    }
