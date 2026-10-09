# Phase 10C — Verify Sentinel-1 Trishuli Candidate Pair

## REAL_EXECUTED

- The exact public CDSE STAC items were retrieved and verified:
  - Before:
    `S1D_IW_GRDH_1SDV_20260816T122141_20260816T122206_004151_007980_B091_COG`
  - After:
    `S1D_IW_GRDH_1SDV_20260828T122141_20260828T122206_004326_007FA4_C73B_COG`
- Both items are in `sentinel-1-grd`, platform Sentinel-1D, product
  `IW_GRDH_1S`, processing level `L1`, instrument mode `IW`, ascending
  direction, and relative orbit `85`.
- Both items expose explicit `VV` and `VH` measurement assets. The assets are
  Cloud Optimized GeoTIFFs with `data` roles and polarization-specific asset
  metadata.
- The real AOI
  `configs/case_studies/trishuli_2026_aoi.geojson` passed the existing AOI
  validator. Shapely footprint tests found both item footprints cover the AOI.
- Acquisition times were verified as:
  - Before: `2026-08-16T12:21:41.058298Z`
  - After: `2026-08-28T12:21:41.762029Z`
- Relative to UTC midnight on the event date `2026-08-26`, the exact offsets
  are `9 days, 11:38:18.941702` before and `2 days, 12:21:41.762029` after.
- The generated pair manifest is
  `data/manifests/trishuli_sentinel1_pair_manifest.json`.

## IMPLEMENTED_ONLY

- `scripts/phase10c_pair_verify.py` performs exact-item retrieval, asset-level
  VV/VH checks, same-track compatibility checks, AOI footprint coverage
  checks, temporal offset calculation, disk-size estimation, and manifest
  writing.
- The verifier does not request any asset URL. It records the official HTTPS
  asset references for a later authenticated phase only.
- Recommended next acquisition investigation: an authenticated Sentinel Hub
  Process API bounded AOI request if the required COG output and service
  permissions are confirmed; otherwise use authenticated direct VV/VH COG
  asset access with strict byte and disk checks. No bounded method was
  implemented or executed in this phase.

## BLOCKED

- CDSE authentication is blocked: neither
  `RESCUEX_CDSE_CLIENT_ID` nor `RESCUEX_CDSE_CLIENT_SECRET` is present.
- The estimated VV/VH measurement total for both scenes is
  `2,463,632,479` bytes (`2.2944 GiB`), before any derived outputs or working
  space. Blind full-product download is therefore not recommended.
- Metadata footprint coverage is not a raster-level guarantee; the manifest
  calls the status `VERIFIED_FOOTPRINT_COVERS_AOI`, not pixel-level coverage.

## FAILED

None. The exact pair passed the configured metadata compatibility checks.

## NOT_EXECUTED

- No Sentinel asset or product was downloaded.
- No SAFE archive, TIFF, raster stack, or model input was created.
- No raster preprocessing, flood inference, change detection, flood-area
  calculation, infrastructure analysis, OSM/ohsome extraction,
  connectivity, EMSR927 access, training, or GitHub push occurred.

## Manifest and provenance

The manifest records the exact IDs, complete scene metadata needed for this
phase, item geometries and bboxes, asset URLs/types/roles/sizes/checksums,
VV/VH verification, AOI coverage checks, temporal offsets, compatibility
booleans, authentication status, estimated size, recommended next method,
timestamp, and warnings. No EMSR927 or published damage source influenced the
pair.

## Tests and exact command

```powershell
python scripts/phase10c_pair_verify.py --aoi configs/case_studies/trishuli_2026_aoi.geojson
python -m pytest tests/test_phase10c.py
python -m pytest
python -m compileall -q src tests scripts
git diff --check
```

The exact-pair tests cover VV/VH assets, orbit compatibility, AOI coverage,
and mismatch failure behavior. This phase establishes a verified candidate
pair only; it is not a flood result or damage map.
