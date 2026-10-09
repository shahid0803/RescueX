# Phase 11A — Real Sentinel-1 Pair QA and Model-Input Compatibility Audit

## Status

**REAL_EXECUTED:** Both reconciled Trishuli production rasters were read and
independently verified without modification. The QA manifest is
`data/manifests/trishuli_sentinel1_pair_qa.json`; the compact visual artifact
is `data/qa/sentinel1_trishuli_pair_qa.png`.

**Input compatibility:** `INDETERMINATE`. The two-channel shape/order and
spatial grid match the `FloodUNet` interface, but the project does not prove
that the Process API `GAMMA0_ELLIPSOID` values have the same units/scale as
the Kuro Siwo `flood_vv`/`flood_vh` training arrays. No Sentinel valid-mask
contract exists because both TIFFs have undeclared nodata. No inference was
run.

## Production artifact verification

| Role | Scene | Size | SHA-256 | Grid |
|---|---|---:|---|---|
| BEFORE | `S1D_IW_GRDH_1SDV_20260816T122141_20260816T122206_004151_007980_B091_COG` | 661,872 | `28e6dd9fef265db3ec4d203e5f7b80d2de06993455a4844f91625559275740fa` | EPSG:32645, 415×248, 20 m |
| AFTER | `S1D_IW_GRDH_1SDV_20260828T122141_20260828T122206_004326_007FA4_C73B_COG` | 662,458 | `c4df94426a9be90e5dcf20b7d14d09165880fd36ae85c0ef34dc9bf1c2663a2b` | EPSG:32645, 415×248, 20 m |

Both transforms are
`(20, 0, 313843.864892112, 0, -20, 3089251.802767885, 0, 0, 1)`.
Both have two FLOAT32 bands labelled VV then VH, full AOI coverage, readable
finite data, and matching grids. Nodata is undeclared; zero was not treated as
nodata.

## Pixel QA

The complete per-band statistics, percentiles, and ten-bin histograms are in
the JSON QA manifest. Key values:

| Role/band | Finite | Non-finite | Zero | Min | Max | Mean | Stddev |
|---|---:|---:|---:|---:|---:|---:|---:|
| BEFORE VV | 102,920 | 0 | 0 | 0.001310 | 20.141703 | 0.276140 | 0.370678 |
| BEFORE VH | 102,920 | 0 | 8 | 0.000000 | 2.829065 | 0.054034 | 0.060620 |
| AFTER VV | 102,920 | 0 | 0 | 0.002283 | 50.699501 | 0.293646 | 0.553486 |
| AFTER VH | 102,920 | 0 | 7 | 0.000000 | 3.417268 | 0.057511 | 0.065188 |

The pair has 102,920 pixels finite in both scenes and zero pixels where either
scene is non-finite. Mean AFTER−BEFORE change is `0.017507` for VV and
`0.003478` for VH; mean absolute change is `0.130387` and `0.025027`,
respectively. These are descriptive differences only, not flood
classification.

## Kuro Siwo model-input audit

The checkpoint is `FloodUNet`, base channels 4, with two inputs in
`flood_vv`, `flood_vh` order and one flood logit output per pixel. The recorded
normalization is mean `[0.09471695, 0.02098127]` and standard deviation
`[0.07056942, 0.04590586]`. Training used official Kuro Siwo revision
`e8e61b7b1254b04bfa2b5e26d43db90cb86b5004`, with 7 training and 5 held-out
evaluation samples. Labels mapped source class 2 to flood 1, classes 0/1 to
background 0, retaining only `valid_mask == 1`.

Kuro Siwo sampled ranges/means were VV `0.001876–1.589664`, mean `0.094717`,
and VH `0.000844–12.238182`, mean `0.020981`. Sentinel dimensions and channel
names align, but representation equivalence, valid-mask handling, and a
documented Sentinel normalization pipeline are not established. Therefore
compatibility is **INDETERMINATE**, not a license to infer.

## Not executed and limitations

**NOT_EXECUTED:** model inference, flood mask generation, flood-area
estimation, OSM/EMSR927, connectivity analysis, dashboard analysis, and any
CDSE request. The checkpoint is a small controlled experiment and is not a
validated Trishuli model.

The QA command was:

```powershell
python scripts/phase11a_pair_qa.py
```

Local artifacts remain Git-ignored. No production TIFF or reconciled
acquisition manifest was modified.
