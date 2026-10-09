from __future__ import annotations

from datetime import date


ATTRIBUTIONS = [
    "Contains modified Copernicus Sentinel data 2026.",
    "Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.",
    "© OpenStreetMap contributors.",
]


def situation_report(event_date: date, results: dict) -> str:
    impact = results["infrastructure"]
    network = results["network"]
    return "\n".join(
        [
            "# RescueX situation report",
            f"**Event date:** {event_date.isoformat()}",
            "",
            "## Executive summary",
            f"- Flood/change zones analysed: {results['flood_zone_count']}",
            f"- Spatially affected buildings: {len(impact['affected_buildings'])}",
            f"- Potentially blocked roads: {len(impact['affected_roads'])}",
            f"- Spatially affected bridges: {len(impact['affected_bridges'])}",
            f"- Settlements that lost all analysed routes: {network['cut_off_count']}",
            "",
            "## Method and limitations",
            "Counts are computed from submitted georeferenced geometries. "
            "Overlap indicates spatial impact or potential blockage, not structural collapse. "
            "Connectivity uses the supplied pre-event road graph and removes roads above "
            "the configured overlap threshold.",
            "",
            "## Attribution",
            *[f"- {item}" for item in ATTRIBUTIONS],
        ]
    )


def processing_report(run: dict) -> str:
    """Render a status/limitations report without inventing analytical results."""
    if run.get("execution_mode") == "FIXTURE":
        return "\n".join([
            "# RescueX development run report",
            f"**Event date:** {run['event_date']}",
            "",
            f"**Status:** {run['status']}",
            f"**Classification:** DEVELOPMENT FIXTURE — NOT REAL SATELLITE RESULT",
            "",
            "This run validates orchestration and geometry integration using "
            "controlled fixture inputs. It is not a satellite result, model "
            "performance result, or Trishuli finding.",
            "",
            "## Pipeline status",
            *[f"- {item['status']}: {item['step']}" for item in run.get("history", [])],
            "",
            "## Limitations",
            "- No verified real Phase 3 checkpoint or georeferenced mask is available.",
            "- Real satellite acquisition, inference, and OSM execution remain pending.",
            *[f"- {warning}" for warning in run.get("warnings", [])],
        ])
    return "\n".join([
        "# RescueX processing report",
        f"**Event date:** {run['event_date']}",
        f"**Status:** {run['status']}",
        "",
        "No real analytical result is reported until verified satellite and "
        "model artifacts are available.",
        *[f"- {error}" for error in run.get("errors", [])],
    ])
