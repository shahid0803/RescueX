# Phase 6 orchestration and dashboard

`RescueXPipeline` is the single run boundary for the application. It records
meaningful lifecycle transitions, progress, warnings, errors, provenance,
structured outputs, and map layers in a `ProcessingRun`.

The current `FIXTURE` mode reuses the existing geometry impact and network
analysis services with caller-supplied controlled geometries. It is always
labelled `DEVELOPMENT FIXTURE — NOT REAL SATELLITE RESULT`; the dashboard,
report, and API do not present it as a satellite finding.

`REAL` mode currently fails explicitly unless artifact inspection finds a
verified real Phase 3 checkpoint and georeferenced mask. This is intentional:
the repository has no real Phase 3, Phase 4, or Trishuli result yet.

## API

- `POST /api/pipeline/runs`
- `GET /api/pipeline/runs/{run_id}`
- `GET /api/pipeline/runs/{run_id}/report`
- `GET /api/pipeline/runs/{run_id}/layers`

The dashboard at `/` submits a run, displays status history and limitations,
renders fixture flood-zone GeoJSON on Leaflet, and displays the structured
report. It does not fabricate unavailable satellite/model layers.
