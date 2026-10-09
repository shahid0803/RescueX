# Phase 4 execution status

## A. Implemented

- Provenance-aware Phase 3 artifact inspection.
- Infrastructure overlap analysis for buildings, roads, and bridges.
- Pre-event road graph connectivity and cut-off settlement analysis.
- Fixture-only integration execution with an explicit non-satellite label.

## B. Executed on real data

None. No genuine trained Phase 3 checkpoint or georeferenced flood mask is
available in this repository. The Kuro Siwo manifest is metadata only and is
disabled; no raw dataset was downloaded.

## C. Executed on synthetic fixtures

The automated tests execute overlap and connectivity logic using controlled
geometries. These outputs are software/integration evidence only and must not
be reported as satellite flood extent, model performance, affected assets, or
Trishuli results.

## D. Not yet executed

- Kuro Siwo download, training, and evaluation.
- Sentinel-1/Sentinel-2 inference.
- Trishuli inference.
- Real OSM snapshot ingestion and real infrastructure impact analysis.
- Real road-network cut-off analysis.

## E. Planned

After approved data and a documented inference manifest are available, connect
the georeferenced model mask to the Phase 4 overlap pipeline, record checksums,
CRS, transform, source scene IDs, thresholds, and run timestamps, then report
real and fixture results separately.
