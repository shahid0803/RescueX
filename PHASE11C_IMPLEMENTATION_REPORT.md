# Phase 11C — Kuro Siwo Dataset Provenance Reconciliation

## Decision

**REAL_EXECUTED:** The existing seven local training samples were audited
without downloading additional data. Their metadata, array hashes, loader
contract, and deterministic training normalization were recorded in
`data/manifests/sentinel_kuro_siwo_compatibility.json`.

**Compatibility: `INDETERMINATE`.** The audit resolves the identity of the
dataset revision and the available GitHub GRD history, but it cannot prove
which GitHub preprocessing commit generated the saved WebDataset arrays.
Therefore no positive compatibility decision is scientifically justified.

**Recommended next action: D — Continue source recovery or design a
controlled compatibility experiment.** Do not implement an adapter,
reacquisition, or retraining from this audit alone.

## Separate source identities

| Identity | Exact evidence | Meaning |
|---|---|---|
| Hugging Face dataset | `orion-ai-lab/Kuro-Siwo-Webdataset`, revision `e8e61b7b1254b04bfa2b5e26d43db90cb86b5004` | Dataset-repository revision; its commit message is `Update README.md` |
| GitHub source repository | `Orion-AI-Lab/KuroSiwo` | Independent preprocessing/training code repository |
| GRD graph | `configs/grd_preprocessing.xml`, blob SHA `09f180da6e803d4a5c389903e42ed059215e01e3` | Exact graph content retrieved from the path history |
| First path-specific GitHub commit | `a6755656108dc03ecc6fe4919147ff4feec6d3d0` | `Add GRD preprocessing pipeline`, 2024-07-13; introduces the GRD graph |
| Later relevant GitHub history | `7660d6e6…` (`Update code for KuroSiwo v2`), `1663f3a1…` (`update mean/std`) | Relevant history, but not proof of WebDataset generation |
| RescueX pipeline | `src/floodlens/ml/data.py` and `scripts/data/train_kuro_siwo.py` | Local loader and deterministic normalization applied after arrays were saved |

The Hugging Face revision is not used as a GitHub commit identifier. A
matching filename, date, or numerical range was not treated as proof of
provenance.

## Local sample metadata

The seven selected training samples are `sample-000` through `sample-006`
(source keys `000000`–`000006`). Each `info.json` contains:
`actid`, `aoiid`, `datasets`, `flood_date`, `geom`, `grid_id`, `gvalid`,
`mastercov`, `pcovered`, `pflood`, `pwater`, `revision`, `slavecov`,
`sources`, and `version`.

The metadata records the source product identifiers, source dates and roles:
`MS1_IVV`/`MS1_IVH` master imagery, `SL1_IVV`/`SL1_IVH` and
`SL2_IVV`/`SL2_IVH` slave imagery, plus DEM/MLU/MNA datasets. It does **not**
record a SNAP graph revision, GitHub commit, config blob, calibration
coefficient, speckle-filter parameters, terrain-correction version, or
WebDataset generation commit. Consequently, it cannot bind the arrays to
`a6755656…`, `7660d6e6…`, `1663f3a1…`, or any other GitHub commit.

The manifest records SHA-256 values for each selected sample's
`flood_vv.npy`, `flood_vh.npy`, `valid_mask.npy`, and `mask.npy`; the local
files were not modified.

## Training transformation verification

The existing implementation was imported and executed only through sample
loading and normalization. It:

1. loads `flood_vv.npy` then `flood_vh.npy`;
2. concatenates them as two FLOAT32 channels of shape `2×224×224`;
3. creates the binary target from source mask class 2, retaining
   `valid_mask == 1`;
4. computes per-channel mean/std over valid training pixels;
5. applies `(image - mean) / std` for model inputs.

The recomputed values match the checkpoint manifest:

| Channel | Mean | Stddev |
|---|---:|---:|
| `flood_vv` | `0.09471695125102997` | `0.07056941837072372` |
| `flood_vh` | `0.02098127081990242` | `0.045905862003564835` |

No additional scaling, clipping, logarithm, or resampling is applied by
RescueX. This confirms the local training transformation, not the physical
units or upstream preprocessing of the saved arrays.

## Processing-contract comparison

The available GitHub GRD graph documents precise-orbit application,
thermal-noise removal, GRD border-noise removal, Sigma0 calibration without
dB scaling, Lee Sigma filtering, and terrain correction. It is current
GitHub evidence and its graph blob is exact, but its linkage to the
Hugging Face dataset revision is **UNPROVEN**.

RescueX's verified Process API request documents VV/VH FLOAT32,
`GAMMA0_ELLIPSOID`, orthorectification enabled, speckle filtering disabled,
radiometric terrain correction disabled, and a 20 m output grid. These
contracts cannot be declared equivalent based only on both being Sentinel-1
GRD-derived floating-point arrays.

## Final compatibility and execution safety

The status remains **`INDETERMINATE`** because the applicable upstream GRD
processing revision and valid-pixel semantics are unresolved. No arbitrary
conversion or positive inference authorization was introduced.

**NOT_EXECUTED:** dataset download, CDSE request, inference, training or
fine-tuning, flood mask/area estimation, OSM, EMSR927, connectivity, and
GitHub push.

The Phase 10D acquisition manifest and historical attempt records were read
only. Production TIFFs remain:

- BEFORE SHA-256:
  `28e6dd9fef265db3ec4d203e5f7b80d2de06993455a4844f91625559275740fa`
- AFTER SHA-256:
  `c4df94426a9be90e5dcf20b7d14d09165880fd36ae85c0ef34dc9bf1c2663a2b`

The checkpoint remains SHA-256
`dc1da66fb3a837bf93f406330ace78245e385248c5b7b9443de47810481fa52d`.
No credentials or tokens were written.
