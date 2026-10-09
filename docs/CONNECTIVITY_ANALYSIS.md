# Phase 5 connectivity analysis

The connectivity service compares an intact pre-event road graph with a
derived graph in which Phase 4 **potentially blocked** segments are disabled.
It does not claim that a road or bridge is destroyed. A settlement is newly
cut off only when it had a baseline route to the selected destination and no
route remains under the modeled blockage assumptions.

`ConnectivityConfig` requires `osm_snapshot_date < event_date`; current or
post-event OSM must not silently become the baseline. The current reference
implementation preserves road IDs and lengths, uses explicit endpoint access
tolerances, records unmatched blockage IDs, and reports paths and distances.
Road restrictions, vehicle routing, live OSM retrieval, and geometry-based
intersection splitting remain future work.

The service returns machine-readable JSON and a map-ready settlement
GeoJSON helper. The API endpoints are:

- `POST /api/connectivity/analyze`
- `GET /api/connectivity/runs/{run_id}`
- `GET /api/connectivity/summary/{run_id}`

Use `rescuex connectivity analyze --input <json>` for local execution. Real
OSM/Phase 4 inputs are not present in this repository; tests use controlled
synthetic fixtures and are not hackathon or Trishuli results.
