# Phase 11D — Controlled Sentinel-1 Candidate Reprocessing Experiment

## Outcome

**CANDIDATE_PROFILE_IMPLEMENTED:** A separate, explicit candidate path is
implemented in `scripts/phase11d_candidate_acquire.py`. Its dry-run manifest
is `data/manifests/trishuli_candidate_preprocessing_manifest.json`.

**CANDIDATE_DATA_ACQUIRED:** `NOT_EXECUTED`.

**CANDIDATE_DATA_VALIDATED:** `NOT_EXECUTED`.

**TRAINING_INPUT_COMPARISON_COMPLETED:** `NOT_EXECUTED`. No inference, model
training, flood mask, or compatibility claim was made. Overall model
compatibility remains `INDETERMINATE`.

## Pinned evidence

The candidate reads both scene IDs from the reconciled Phase 10D manifest:

- BEFORE:
  `S1D_IW_GRDH_1SDV_20260816T122141_20260816T122206_004151_007980_B091_COG`
- AFTER:
  `S1D_IW_GRDH_1SDV_20260828T122141_20260828T122206_004326_007FA4_C73B_COG`

The alternate AFTER identifier in the phase request was not used. Candidate
requests retain the verified narrow acquisition intervals and require the
existing strict STAC uniqueness gate before authenticated processing.

The fixed candidate grid is EPSG:32645, bounds
`[313843.864892112, 3084291.802767885, 322143.864892112, 3089251.802767885]`,
830 × 496 pixels at 10 m. Outputs are isolated under
`data/raw/satellite/sentinel-1/trishuli_2026/candidate_sigma0_10m/` and never
share production paths.

## Candidate processing contract

The candidate payload requests VV/VH, `SIGMA0_ELLIPSOID`, orthorectification,
and a Process API `LEE` speckle filter with a 3 × 3 window. The evalscript
requests linear FLOAT32 VV, VH, and `dataMask` bands in that order.

The official Kuro Siwo evidence records a SNAP **Lee Sigma** filter with its
own window parameters. Process API `LEE` is recorded as a different filter;
the implementation does not claim that it reproduces SNAP Lee Sigma.
Likewise, Process API `dataMask` is not claimed equivalent to Kuro Siwo's
`valid_mask` or land/sea labels. The Hugging Face revision
`e8e61b7b1254b04bfa2b5e26d43db90cb86b5004` remains a dataset-repository
revision, and the GitHub config blob
`09f180da6e803d4a5c389903e42ed059215e01e3` is not proven to have generated
those samples.

The candidate records the official CDSE S1GRD and Process API example
documentation URLs in its manifest. No local SNAP executable was found
(`SNAP_EXECUTABLE=NOT_FOUND`), and no SNAP installation or SAFE download was
attempted.

## Safety and execution

The command is dry-run by default and writes only the candidate manifest.
Authenticated STAC/Process API requests require explicit `--execute` and
`RESCUEX_CDSE_CLIENT_ID` / `RESCUEX_CDSE_CLIENT_SECRET`. Candidate writes use
`.part` files, strict three-band validation, finite-value checks, dataMask
0/1 checks, AOI coverage, hashes, byte sizes, and the existing 512 MiB budget.
Credentials and authorization headers are never written to manifests.

This coding-agent run made no CDSE request, downloaded no data, did not inspect
or modify SNAP binaries, and did not modify production rasters, the model
checkpoint, or the Phase 10D acquisition manifest. The production hashes
remain:

- BEFORE: `28e6dd9fef265db3ec4d203e5f7b80d2de06993455a4844f91625559275740fa`
- AFTER: `c4df94426a9be90e5dcf20b7d14d09165880fd36ae85c0ef34dc9bf1c2663a2b`

## Validation performed

- Focused candidate and Phase 10D tests: **23 passed**.
- Full regression suite: **69 passed**.
- `python -m compileall -q src tests scripts`: passed.
- `git diff --check`: passed.
- Production rasters and checkpoint hash checks: passed.
- Raw data and checkpoint Git tracking check: no tracked files.
- Candidate dry-run manifest: `CANDIDATE_PROFILE_IMPLEMENTED`.
- Live acquisition: `NOT_EXECUTED`.
- Inference/training/downstream analysis: `NOT_EXECUTED`.

## User-controlled execution

After reviewing the dry-run manifest, the exact authenticated PowerShell
command is:

```powershell
python scripts/phase11d_candidate_acquire.py --execute
```

This command uses the existing `RESCUEX_CDSE_CLIENT_ID` and
`RESCUEX_CDSE_CLIENT_SECRET` environment variables, performs the exact
manifest-pinned STAC checks, and writes only to the isolated candidate
directory. It must not be used as evidence that the FloodUNet checkpoint is
authorized for inference.
