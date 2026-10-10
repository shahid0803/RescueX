# RescueX

RescueX — Satellite-Powered Flood Damage and Connectivity Intelligence — is
the foundation for an educational, geospatially explicit system for
**"Mapping Flood Damage from Space"**. It is not an SOS application. The
system will transform satellite observations and pre-event map data into
flood extent, infrastructure impact, road connectivity, and situation-report
evidence.

## Current project status

> [!IMPORTANT]
> **Model/preprocessing compatibility remains INDETERMINATE.** No validated
> Trishuli flood mask, flooded-area result, or accuracy metric has been
> generated. Real inference is blocked until a documented compatibility
> experiment or recovered preprocessing provenance is completed.

**What works today:**

- Sentinel-1 metadata discovery and bounded Process API acquisition pipeline
  (credential-gated; no imagery committed).
- The Trishuli 2026 case study is configured with an authoritative AOI
  (`configs/case_studies/trishuli_2026_aoi.geojson`), challenge event date
  `2026-08-26`, and a verified before/after Sentinel-1D IW pair (2026-08-16
  and 2026-08-28, relative orbit 85, VV/VH COG assets).
- Strict raster validation, VV/VH-only inference adapter, and
  model-compatibility gate that prevents unverified real execution.
- Geospatial impact/connectivity analysis (fixture-tested with synthetic
  geometry only).
- Fixture-labelled dashboard at `/` with Leaflet map, Trishuli AOI overlay,
  and a separate synthetic flood-zone polygon for demo layout. Fixture runs
  are explicitly labelled **DEVELOPMENT FIXTURE — NOT REAL SATELLITE RESULT**.
- Offline tests via `python -m pytest`, compile-check via
  `python -m compileall -q src tests scripts`, and whitespace check via
  `git diff --check`.
- Kuro Siwo sample QA (one real sample validated) and bounded training
  experiment (7 training / 5 test samples, CPU, ignored checkpoint).
- Candidate 10 m Sigma0/LEE pair recovered and validated locally from
  preserved responses. Original response TIFFs remain unchanged.

**What has not been done:**

- No validated Trishuli flood mask or flooded-area result.
- No production inference — the `infer_geotiff` function contains a hard
  RuntimeError because Sentinel/Kuro Siwo preprocessing compatibility is
  INDETERMINATE.
- No live deployment, production URL, or browser-tested dashboard.
- No EMSR927 comparison or accuracy metric.
- No raw imagery, checkpoint, manifest, or diagnostic is committed.

## Architecture overview

```
frontend/index.html     Leaflet dashboard — fixture-mode demo UI
src/floodlens/
  api.py                FastAPI application (serves dashboard + REST API)
  pipeline.py           RescueXPipeline orchestrator (fixture/real paths)
  models.py             Pydantic data contracts (RunRequest, Feature, Road, Point)
  analysis.py           Geometry-based impact analysis (overlap, affected roads)
  phase4.py             Phase 4 integration: real-vs-fixture classification
  report.py             Situation report generation with attributions
  config.py             Environment configuration with safe defaults
  contracts.py          Phase 0 data contracts (EventContext, ScenePair, etc.)
  registry.py           Source allowlist/validation-only registry
  geo.py                Geospatial utilities
  raster.py             GeoTIFF inspection, QC, clipping, reprojection
  connectivity.py       Road-network connectivity analysis
  network.py            Graph-based route analysis
  satellite/            CDSE STAC discovery, download, preprocessing config
  ml/                   U-Net model, dataset policy, inference (blocked), training
configs/
  case_studies/         Trishuli AOI GeoJSON + case-study JSON
  ml/                   Baseline model config
  data-sources.json     Machine-readable source registry
tests/                  Offline regression tests (pytest)
scripts/                Phase discovery/audit scripts (no network by default)
docs/                   Architecture, requirements, phase reports
```

## Prerequisites

- Python 3.11 or newer
- GDAL-compatible wheels are not required for the test suite.
- For production GeoJSON/GeoPackage processing, install the optional
  `geospatial` extra (GeoPandas, Shapely, Rasterio, and OSMnx).

## Setup

```powershell
git clone https://github.com/shahid0803/RescueX.git
cd RescueX
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Install geospatial support when needed:

```powershell
python -m pip install -e ".[geospatial]"
```

## Running the application

```powershell
python -m floodlens.api
```

Open <http://127.0.0.1:8000>. The API documentation is at
<http://127.0.0.1:8000/docs>.

The dashboard defaults to the configured Trishuli AOI and event date
`2026-08-26`. Fixture mode submits a synthetic flood-zone polygon (separate
from the study-area AOI) and labels all results as demo data.

## Running tests

```powershell
# Full regression suite
python -m pytest

# Compile check
python -m compileall -q src tests scripts

# Whitespace / merge-conflict check
git diff --check
```

The tests cover AOI/geometry defaults, fixture labelling, real-run guards,
overlap thresholds, blocked-road handling, path safety, and connectivity.
No test uses a published damage map as input or makes network requests.

## Repository map

| Path | Purpose |
| --- | --- |
| `frontend/index.html` | Leaflet dashboard with Trishuli AOI and fixture controls |
| `src/floodlens/api.py` | FastAPI application serving dashboard + REST API |
| `src/floodlens/pipeline.py` | End-to-end pipeline orchestrator |
| `src/floodlens/ml/inference.py` | Inference module (blocked by compatibility gate) |
| `configs/case_studies/trishuli_2026_aoi.geojson` | Authoritative Trishuli study-area AOI |
| `docs/architecture.md` | System boundaries and phase plan |
| `docs/data-sources.md` | Source registry and acquisition policy |
| `docs/requirements-traceability.md` | Hackathon requirement mapping |
| `tests/` | Offline regression tests |

## Data and training boundary

Allowed production inputs are Sentinel-1, Sentinel-2, Copernicus DEM, and
pre-event OpenStreetMap. A future segmentation implementation must use an
allowed training dataset, such as Kuro Siwo or Sen1Floods11, with scene-level
splits and citations recorded in the run manifest. Published damage maps
(including EMSR927) are validation references only.

The case study comparison with Copernicus EMSR927 belongs in validation and
error analysis, not in inference or training. Do not use post-event OSM
edits. See [DATA_GOVERNANCE.md](DATA_GOVERNANCE.md).

## Historical phase reports

> [!NOTE]
> The sections below are **historical snapshots** from earlier development
> phases. Some statements (e.g. "no configured AOI", "only Phases 0–1 exist")
> are superseded by later work. Refer to the "Current project status" section
> above for the authoritative state.

### Phase 0 — project foundation

Logical architecture, requirements traceability, versioned core contracts,
machine-readable source registry, environment-backed settings, dataset/download
procedures, forbidden-data guardrails, reproducible packaging, tests, and CI.

### Phase 1 — satellite data acquisition

Metadata discovery and safe download primitives for CDSE STAC. Does not
implement flood segmentation, damage analysis, connectivity, or a complete
dashboard.

### Phase 2 — satellite preprocessing

Raster inspection, GeoTIFF metadata validation, AOI clipping, CRS-aware
reprojection, common-grid alignment, nodata/QC reports, diagnostic previews,
and explicit Sentinel-1/Sentinel-2 preprocessing contracts.

### Phase 3 — AI flood segmentation

CPU-safe lightweight binary U-Net baseline, scene/region split utility, patch
generation, BCE+Dice loss, IoU/Dice/precision/recall, checkpoint/experiment
manifest writing, and georeferenced probability/mask inference. A tiny
synthetic end-to-end test proves the software path; no production inference
has been executed.

### Phase 4 — infrastructure impact

Fixture-tested damage overlap and road-connectivity analysis. No real OSM
ingestion, real flood-mask execution, or EMSR927 comparison.

### Phase 5 — connectivity

Structured before/after road-network connectivity with route paths, distances,
nearest town/hospital analysis, cut-off states, diagnostics, and GeoJSON
output. Tested with synthetic graphs only.

### Phase 6 — end-to-end pipeline

`RescueXPipeline` and dashboard with lifecycle status, progress history,
structured layer output, Leaflet map, and situation report. Fixture mode is
explicitly labelled. Real mode fails rather than fabricating results.

### Phases 7–8 — real-data readiness

Audit and readiness gate. No CDSE credentials, Kuro Siwo files, real
checkpoint, or georeferenced mask available in this environment.

### Phases 9A–9C — Kuro Siwo acquisition and training

9A: Official Kuro Siwo distribution audited; acquisition BLOCKED (safe subset
unavailable). 9B: One real labelled GRD WebDataset sample validated. 9C:
Bounded training on 7 real samples, 5 held-out test samples, 3 CPU epochs —
ignored checkpoint with measured metrics. Not a Sentinel or Trishuli result.

### Phases 10A–10D — Trishuli Sentinel-1 pair

10A: Metadata discovery gate. 10B: Case-study configuration with AOI and event
date. 10C: Exact public CDSE metadata pair verified (2026-08-16 before,
2026-08-28 after). 10D: Bounded Process API acquisition implementation
(credential-gated, no request made).

### Phase 11E — candidate validation closeout

Candidate Sigma0/LEE pair recovered and validated locally. Process API LEE is
not claimed equivalent to SNAP Lee Sigma or the pinned Kuro Siwo
preprocessing. Model compatibility remains **INDETERMINATE**.

## Required attribution

Contains modified Copernicus Sentinel data 2026.

Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus
Defence and Space GmbH 2014–2018 provided under COPERNICUS by the European
Union and ESA; all rights reserved.

© OpenStreetMap contributors.
