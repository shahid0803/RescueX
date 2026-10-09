# RescueX

RescueX — Satellite-Powered Flood Damage and Connectivity Intelligence — is
the foundation for an educational, geospatially explicit system for
**“Mapping Flood Damage from Space”**. It is not an SOS application. The
system will transform satellite observations and pre-event map data into
flood extent, infrastructure impact, road connectivity, and situation-report
evidence.

This repository now contains **Phase 0: project foundation**,
**Phase 1: satellite data acquisition and scene management**. Phase 1
implements metadata discovery and safe download primitives; it does not
implement flood segmentation, damage analysis, connectivity, or a complete
dashboard. The
contracts, source registry, configuration boundaries, governance rules,
documentation, and CI are established before the model, acquisition
adapters, and complete dashboard are implemented.

The repository deliberately keeps data provenance visible. Copernicus EMS
maps and post-event OSM edits are validation-only inputs and are never used by
the production analysis.

## Phase-0 deliverables

- Logical architecture and requirements traceability.
- Versioned core contracts for AOIs, scenes, OSM snapshots, masks, and runs.
- A machine-readable source registry with production/validation boundaries.
- Environment-backed settings with safe defaults and no credentials in git.
- Dataset/download procedures and explicit forbidden-data guardrails.
- Reproducible Python packaging, tests, and GitHub Actions CI.

The small existing analysis code is a contract exercise and reference
implementation only. It is intentionally not a complete satellite pipeline,
trained model, or production frontend.

## Prerequisites

- Python 3.11 or newer
- GDAL-compatible wheels are not required for the test suite.
- For production GeoJSON/GeoPackage processing, install the optional
  `geospatial` extra (GeoPandas, Shapely, Rasterio, and OSMnx).

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Install geospatial support when needed:

```powershell
python -m pip install -e ".[geospatial]"
```

## Run the reference API

```powershell
python -m floodlens.api
```

Open <http://127.0.0.1:8000>. The API documentation is at
<http://127.0.0.1:8000/docs>.

`POST /api/v1/runs` accepts a provisional AOI/event contract and pre-event
geometries. A full example is in `examples/minimal-run.json`. This endpoint
is a smoke-test reference, not the final processing pipeline.

## Repository map

| Path | Purpose |
| --- | --- |
| `docs/architecture.md` | system boundaries and phase plan |
| `docs/data-sources.md` | source registry and acquisition policy |
| `docs/datasets.md` | permitted training data and download procedure |
| `docs/requirements-traceability.md` | hackathon requirement mapping |
| `docs/SATELLITE_DATA_ACCESS.md` | official CDSE access decision |
| `docs/SATELLITE_SCENE_SELECTION.md` | deterministic before/after selection |
| `docs/DATA_DOWNLOAD_GUIDE.md` | credentials, CLI, cache, and manifest |
| `src/floodlens/contracts.py` | phase-0 data contracts |
| `src/floodlens/registry.py` | allowlist/validation-only registry |
| `src/floodlens/config.py` | environment configuration |
| `src/floodlens/satellite/` | Phase-1 acquisition services |
| `src/floodlens/raster.py` | Phase-2 georeferenced raster operations |
| `src/floodlens/satellite/preprocessing.py` | explicit sensor preprocessing configuration |
| `src/floodlens/ml/` | dataset policy, scene splits, patches, U-Net, metrics, training, inference |
| `configs/data-sources.json` | machine-readable source registry |
| `tests/` | contract and reference-analysis tests |

## Data and training boundary

Allowed production inputs are Sentinel-1, Sentinel-2, Copernicus DEM, and
pre-event OpenStreetMap. A future segmentation implementation must use an
allowed training dataset, such as Kuro Siwo or Sen1Floods11, with scene-level
splits and citations recorded in the run manifest. Published damage maps
(including EMSR927) are validation references only.

The case study comparison with Copernicus EMSR927 belongs in validation and
error analysis, not in inference or training. Do not use post-event OSM
edits. See [DATA_GOVERNANCE.md](DATA_GOVERNANCE.md).

## Tests

```powershell
python -m pytest
```

The tests cover overlap thresholds, blocked-road handling, and alternate
route connectivity. No test uses a published damage map as input.

## Phase-0 limitations

No AI model training, large data download, infrastructure damage analysis,
road connectivity, complete frontend, raster preprocessing, or hydrodynamic
simulation is included in these phases. These are explicit next-phase work
items.

## Phase 2 — satellite preprocessing

Phase 2 adds raster inspection, GeoTIFF metadata validation, AOI clipping,
CRS-aware reprojection, common-grid alignment, nodata/QC reports, diagnostic
previews, and explicit Sentinel-1/Sentinel-2 preprocessing contracts. It does
not claim flood detection, calibration, terrain correction, or cloud masking
unless the corresponding real product/backend operation is executed.

## AI flood segmentation

**Implemented:** a CPU-safe, lightweight binary U-Net baseline, scene/region
split utility, patch generation, BCE+Dice loss, IoU/Dice/precision/recall,
checkpoint/experiment manifest writing, and georeferenced probability/mask
inference. A tiny synthetic end-to-end test proves the software path.

**Experimental/not executed:** Kuro Siwo retrieval, dataset inspection on
real samples, baseline training, final metrics, and real Sentinel/Trishuli
inference. Run `rescuex dataset inspect --dataset kuro-siwo` to create
metadata without downloading data. Install the optional ML extra before
training: `python -m pip install -e ".[ml]"`.

**Phase 4 foundation:** fixture-tested damage overlap and road-connectivity
analysis are available, but real OSM ingestion, real flood-mask execution,
final dashboard work, and EMSR927 comparison remain pending.

## Phase 5 connectivity foundation

The repository now includes a structured before/after road-network
connectivity service with Phase 4 blockage adaptation, route paths and
distances, nearest town/hospital analysis, cut-off and degraded-access
states, diagnostics, GeoJSON output, CLI, API, and provenance. It is tested
with synthetic graphs only; no real OSM snapshot, Phase 4 road-impact result,
or Trishuli connectivity result is present.

## Phase 6 end-to-end foundation

`RescueXPipeline` and the dashboard at `/` provide a single processing-run
workflow with lifecycle status, progress history, structured layer output, a
Leaflet map, and a limitations-aware situation report. Fixture mode is
explicitly labelled **DEVELOPMENT FIXTURE — NOT REAL SATELLITE RESULT**.
Real mode fails rather than fabricating results because no verified Phase 3
checkpoint or georeferenced mask is present. See
[docs/PHASE6_ORCHESTRATION.md](docs/PHASE6_ORCHESTRATION.md).

## Phase 7 real-data execution status

The Phase 7 audit is recorded in
[docs/PHASE7_EXECUTION_STATUS.md](docs/PHASE7_EXECUTION_STATUS.md).
This environment has no CDSE credentials, Kuro Siwo files, real checkpoint,
or georeferenced inference mask, so real training, Sentinel inference,
Trishuli processing, infrastructure analysis, connectivity, and EMSR927
comparison were not claimed or fabricated.

## Phase 8 readiness gate

Phase 8 stops at the real-data readiness gate when CDSE credentials, approved
training files, a verified checkpoint, or a configured case-study AOI are
missing. Run `python scripts/phase8_readiness.py` for the current non-secret
status. See [docs/PHASE8_EXECUTION_STATUS.md](docs/PHASE8_EXECUTION_STATUS.md).
Phase 8A decouples CDSE, Kuro Siwo, OHSOME, ML, Sentinel inference, Trishuli,
and EMSR927 validation readiness; see
[docs/PHASE8A_IMPLEMENTATION_REPORT.md](docs/PHASE8A_IMPLEMENTATION_REPORT.md).

## Phase 9A Kuro Siwo acquisition

The official Kuro Siwo distribution was audited without downloading raw
data. Its smallest inspected GRD GeoTIFF shard is approximately 20.25 GB and
the official source does not expose a verified sample-level download path.
Acquisition is therefore explicitly **BLOCKED_SAFE_SUBSET_UNAVAILABLE**;
see [docs/PHASE9A_IMPLEMENTATION_REPORT.md](docs/PHASE9A_IMPLEMENTATION_REPORT.md).

## Phase 9B WebDataset sample validation

The official labelled GRD WebDataset was safely range-probed and one complete
real sample was materialized (~1.81 MiB) without downloading a full shard.
All required fields and source labels were validated, and the RescueX loader
consumed the sample. This is **REAL KURO SIWO SAMPLE QA — NOT MODEL RESULT**;
no training was performed. See
[docs/PHASE9B_IMPLEMENTATION_REPORT.md](docs/PHASE9B_IMPLEMENTATION_REPORT.md).

## Phase 9C controlled real-data training

The bounded experiment trained the existing two-channel lightweight U-Net on
7 real Kuro Siwo training samples and evaluated it on 5 held-out official
test-split samples. Three CPU epochs produced an ignored, hashed checkpoint
and measured metrics. This is Kuro Siwo training-data development only, not a
Sentinel or Trishuli result. See
[docs/PHASE9C_IMPLEMENTATION_REPORT.md](docs/PHASE9C_IMPLEMENTATION_REPORT.md).

## Phase 10A CDSE Trishuli pair discovery

Phase 10A stops safely at the metadata gate because no authoritative
Trishuli AOI/event date exists in this checkout and CDSE credentials are not
configured. No Sentinel scene ID, coverage claim, pair, or download was
fabricated. See
[docs/PHASE10A_IMPLEMENTATION_REPORT.md](docs/PHASE10A_IMPLEMENTATION_REPORT.md)
and `python scripts/phase10a_discovery.py`.

## Phase 10B Trishuli case-study configuration

The Track B challenge specifies the Trishuli event date as **2026-08-26**.
The challenge does not supply an authoritative machine-readable AOI, so the
case-study config records `aoi_status: MISSING_USER_INPUT` and requires a
team-supplied GeoJSON path. The template intentionally contains no geometry.
Run `python scripts/phase10b_case_study_check.py`; it performs no network
search and preserves the CDSE credential gate. See
[docs/PHASE10B_IMPLEMENTATION_REPORT.md](docs/PHASE10B_IMPLEMENTATION_REPORT.md).

## Phase 10C Sentinel-1 pair verification

The exact public CDSE metadata pair for the Trishuli case study was verified:
2026-08-16 before and 2026-08-28 after, both Sentinel-1D IW ascending
relative orbit 85 with explicit VV/VH COG assets. Both metadata footprints
cover the configured AOI. Authentication remains blocked and no imagery was
downloaded. This is a verified candidate pair, not a flood result. See
[docs/PHASE10C_IMPLEMENTATION_REPORT.md](docs/PHASE10C_IMPLEMENTATION_REPORT.md).

## Phase 10D bounded Sentinel-1 acquisition

The bounded Process API acquisition implementation is in place for the exact
Phase 10C pair, using the unchanged Trishuli AOI, a common 20 m
`EPSG:32645` grid, and VV/VH FLOAT32 outputs. The live execution is currently
blocked by missing `RESCUEX_CDSE_CLIENT_ID` and
`RESCUEX_CDSE_CLIENT_SECRET`; no Sentinel request or raster was made. See
[docs/PHASE10D_IMPLEMENTATION_REPORT.md](docs/PHASE10D_IMPLEMENTATION_REPORT.md).

## Phase 4 execution status

The Phase 4 software path is implemented as a fixture-tested integration
foundation. Local artifact inspection confirms that no genuine Phase 3
checkpoint or georeferenced flood mask is available, so no real satellite
analysis is claimed. Fixture outputs are explicitly labelled
**DEVELOPMENT FIXTURE — NOT REAL SATELLITE RESULT**. See
[docs/PHASE4_EXECUTION_STATUS.md](docs/PHASE4_EXECUTION_STATUS.md).

## Required attribution

Contains modified Copernicus Sentinel data 2026.

Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus
Defence and Space GmbH 2014–2018 provided under COPERNICUS by the European
Union and ESA; all rights reserved.

© OpenStreetMap contributors.
