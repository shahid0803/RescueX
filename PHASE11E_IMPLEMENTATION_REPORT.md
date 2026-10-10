# Phase 11E — Candidate Acquisition and Model-Input Validation

## Final status

Both candidate responses were recovered locally from preserved evidence and
passed strict validation after metadata-only enrichment. This does not
establish model compatibility.

**Candidate acquisition history:** the initial execution was blocked by missing
credentials, and a later candidate request produced preserved response bytes.
No further network request was made during offline recovery:

```powershell
python scripts/phase11d_candidate_acquire.py --execute
```

It stopped at the existing credential preflight with the non-sensitive error:

```text
RuntimeError: candidate execution requires RESCUEX_CDSE_CLIENT_ID and RESCUEX_CDSE_CLIENT_SECRET
```

No additional STAC, OAuth, or Process API request was made during recovery.
The preserved response TIFFs were not altered; only metadata-enriched copies
were promoted to the ignored candidate output paths.

## Preflight

- Branch: `shahid0803-build-floodlens`
- Production manifest: present and `PAIR_ACQUIRED_AND_VALIDATED`
- BEFORE production SHA-256: `28e6dd9fef265db3ec4d203e5f7b80d2de06993455a4844f91625559275740fa`
- AFTER production SHA-256: `c4df94426a9be90e5dcf20b7d14d09165880fd36ae85c0ef34dc9bf1c2663a2b`
- Candidate BEFORE response quarantine: present and hash-verified
- Candidate BEFORE output: locally recovered and strictly validated
- Candidate AFTER response quarantine: present and hash-verified
- Candidate AFTER output: locally recovered and strictly validated
- Production rasters and the Phase 10D manifest were not modified.

The exact scene IDs and windows were read from the reconciled manifest:

- BEFORE `S1D_IW_GRDH_1SDV_20260816T122141_20260816T122206_004151_007980_B091_COG`,
  `2026-08-16T12:21:41Z/2026-08-16T12:22:06Z`
- AFTER `S1D_IW_GRDH_1SDV_20260828T122141_20260828T122206_004326_007FA4_C73B_COG`,
  `2026-08-28T12:21:41Z/2026-08-28T12:22:06Z`

## Phase 11E.2/11E.4 local recovery

The candidate evalscript declares three FLOAT32 outputs and returns exactly:

```javascript
[sample.VV, sample.VH, sample.dataMask]
```

This proves the expected order `[VV, VH, dataMask]` for the preserved response
when paired with the exact candidate request payload. The quarantined response
had three FLOAT32 bands, null descriptions, the expected EPSG:32645 830×496
10 m grid, finite values, full AOI coverage, and dataMask values `[1.0]`.
Its only recorded validation error was the missing descriptions.

The recovery copied each quarantine TIFF to a separate staging file, set only
the three proven band descriptions on each copy, ran the strict candidate
validator, and atomically promoted them to:

`data/raw/satellite/sentinel-1/trishuli_2026/candidate_sigma0_10m/before_sigma0_lee_vv_vh_datamask.tif`

- Original response SHA-256:
  `c2bd705a9925659f325c6a884fee795abdac145ef40cecb69f807f0341a76a75`
- Recovered file SHA-256:
  `57493681ac295b9ac297f5d3b42b43703478553e4f7d0fdd64f38a12038c857a`
- Strict validation: **PASS**; undeclared nodata remains a warning
- Network request during recovery: **false**
- Original response network evidence: **true** (preserved from the failed
  candidate request)
- AFTER original response SHA-256:
  `929ad24559896e7d86546a10a1ea9cbd8b831748330743454f1b1d0a948e6911`
- AFTER recovered file SHA-256:
  `7498fba4fc56d7eff922a4f3e3029de201873f308a6d5065d01b5145d72a143e`
- AFTER strict validation: **PASS**; undeclared nodata remains a warning
- Candidate pair complete: **true** for raster validation

The quarantined TIFF and JSON report remain unchanged. The candidate manifest
now records local-recovery provenance, both hashes, `network_request_performed`
as true for the preserved response history, and pair validation status.

## Phase 11E.3 offline resume safety

The resume path now validates an existing BEFORE candidate before any STAC or
Process API call. A valid recovered BEFORE is marked
`LOCALLY_RECOVERED_VALIDATED`, reused without a network request, and its
attempt history and local-recovery provenance are carried forward. The loop
The prior execution performed work only for the exact manifest-pinned AFTER
scene and its fixed window:

`S1D_IW_GRDH_1SDV_20260828T122141_20260828T122206_004326_007FA4_C73B_COG`

`2026-08-28T12:21:41Z/2026-08-28T12:22:06Z`

An offline mocked test confirmed that neither STAC validation nor Process API
acquisition is invoked for BEFORE, while both are invoked for AFTER. No further
acquisition is needed for these preserved responses.

```powershell
python scripts/phase11d_candidate_acquire.py --execute
```

## Validation boundary

- candidate BEFORE raster validation: **PASS**
- candidate AFTER raster validation: **PASS**
- candidate pair grid/hash/statistics comparison: **NOT EXECUTED**
- training-input comparison: **NOT EXECUTED**
- model compatibility: **INDETERMINATE**

The existing Phase 11D profile remains only an implemented approximation:
Sigma0 ellipsoid, orthorectification, Process API `LEE` 3×3 filtering,
10 m EPSG:32645 output, VV/VH/dataMask FLOAT32. Process API `LEE` is not
claimed equivalent to SNAP Lee Sigma. The remaining documented differences
also include terrain/DEM processing, masks, projection/grid semantics, and
the unresolved link between the published GitHub graph and the pinned
Hugging Face training-data revision.

No inference, flood mask, flood-area calculation, retraining, resampling, or
normalization alteration was performed.

## Phase 11D HTTP 400 local audit

The earlier candidate traceback did not persist a candidate attempt manifest:
`scripts/phase11d_candidate_acquire.py` allowed `ProcessAPIRequestError` to
escape from `main()`. The shared Process API client already retained the
HTTP status and bounded response diagnostics on the exception, but that
exception object was lost when the process exited. The candidate runner now
persists those sanitized diagnostics under `attempt_history` using an atomic
manifest update. It does not persist request headers or credentials.

The actual earlier candidate response body is **not recoverable locally**:
there is no candidate HTTP-failure attempt record or saved response body in
the existing local manifests. No network request was made during this audit,
so the concrete server error message remains unknown.

Offline payload comparison against the successful Phase 10D builder found:

| Field | Successful Phase 10D | Phase 11D candidate |
|---|---|---|
| Collection | `sentinel-1-grd` | same |
| Scene selection | IW, ascending, DV, exact narrow time window | same manifest-pinned scene/window |
| Backscatter | `GAMMA0_ELLIPSOID` | `SIGMA0_ELLIPSOID` |
| Orthorectification | enabled | enabled |
| Speckle processing | no `speckleFilter` field | `speckleFilter: {type: LEE, windowSizeX: 3, windowSizeY: 3}` |
| Evalscript inputs | VV, VH | VV, VH, `dataMask` |
| Evalscript outputs | 2 FLOAT32 bands | 3 FLOAT32 bands |
| Output grid | 415×248, 20 m, EPSG:32645 | 830×496, 10 m, same EPSG and fixed bounds |
| Response format | `image/tiff` under `default` | same |

The candidate-only request fields most likely to require provider validation
are therefore the `processing.speckleFilter` object and the three-band
evalscript; this is an offline code comparison, not a claim about the
unobserved server error. The candidate parameters were not changed.

## Candidate validation-failure quarantine

Candidate response bytes that are valid TIFFs but fail strict validation are
preserved separately under the Git-ignored
`data/qa/phase11d_diagnostics/` quarantine, with a JSON report containing
bounded validation evidence, size/hash/content type, failure text, and an
explicit `production_output: false` marker. The `.part` production candidate
file is still deleted and rejected bytes are never promoted. Non-TIFF or
budget-exceeding responses are not preserved. No request headers, tokens,
credentials, or environment values are saved.

## Checks executed

- Focused Phase 11D tests: **8 passed**
- Focused Phase 11D/resume tests: **9 passed**
- Full regression: **83 passed**
- `python -m compileall -q src tests scripts`: **passed**
- `git diff --check`: **passed**
- Production artifact hash verification: **passed**
- Raw data/checkpoint tracking audit: production rasters and checkpoint remain
  untracked and ignored
- Offline HTTP 400 diagnostic persistence test: **passed**
- No credentials, tokens, or authorization headers were printed or written

## Recommended next action

Review both locally recovered candidate rasters and their provenance before
any future inference decision. No acquisition command is required for this
offline closeout.

After successful acquisition, validate the two candidate rasters and update
this report with their hashes, metadata, statistics, and the resulting
compatibility evidence. Do not treat that evidence as authorization for
FloodUNet inference without resolving the documented preprocessing gaps.
