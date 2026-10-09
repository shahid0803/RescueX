# Phase 10D — Authenticated Bounded Sentinel-1 Trishuli Acquisition

## REAL_EXECUTED

- The Phase 10D command was run against the unchanged AOI:
  `configs/case_studies/trishuli_2026_aoi.geojson`.
- Local input validation succeeded. The requested common grid was calculated as
  `EPSG:32645`, 20 m/pixel, 415 x 248 pixels for the real AOI.
- The command stopped at the existing CDSE authenticator before making a
  Process API request because the required environment credentials were not
  present in this execution environment.
- No access token, secret, Authorization header, or credential value was
  printed or written to a manifest.

## IMPLEMENTED_ONLY

- Added `src/floodlens/satellite/process_api.py` with:
  - CDSE Process API client using the existing OAuth authenticator.
  - exact Sentinel-1 scene binding through `dataFilter.ids`;
  - `sentinel-1-grd`, VV/VH-only FLOAT32 evalscript;
  - `GAMMA0_ELLIPSOID` and `orthorectify: true`;
  - speckle filtering and radiometric terrain correction disabled;
  - common projected grid construction;
  - atomic GeoTIFF writes and immediate Rasterio validation;
  - AOI intersection, finite-pixel, two-band/dtype, CRS, transform, and
    metadata checks;
  - before/after grid comparison;
  - 512 MiB aggregate storage budget enforcement;
  - SHA-256, free-disk, file-size, and compact QC recording.
- Added `scripts/phase10d_acquire.py`, which executes BEFORE then AFTER and
  preserves a valid BEFORE artifact if a later AFTER request fails.
- Added `tests/test_phase10d.py` covering exact scene binding, processing
  parameters, bounded two-band raster validation, and budget rejection.
- The intended output names are:
  - `data/raw/satellite/sentinel-1/trishuli_2026/before_vv_vh.tif`
  - `data/raw/satellite/sentinel-1/trishuli_2026/after_vv_vh.tif`
- The intended compact QA artifact is
  `data/qa/sentinel1_trishuli_acquisition_qa.json`, labelled
  `REAL SENTINEL-1 ACQUISITION QA — NOT FLOOD RESULT`.

## BLOCKED

- Authentication status: `BLOCKED`.
- `RESCUEX_CDSE_CLIENT_ID` and `RESCUEX_CDSE_CLIENT_SECRET` were absent.
- Because authentication failed before request creation, neither exact scene
  was sent to `https://sh.dataspace.copernicus.eu/process/v1`.
- The generated ignored manifest is
  `data/manifests/trishuli_sentinel1_acquisition_manifest.json` and records
  the blocker without credentials.

## FAILED

None. The implementation tests pass, and the live run stopped safely at the
credential gate rather than attempting an unauthenticated protected request.

## NOT_EXECUTED

- BEFORE raster acquisition: no.
- AFTER raster acquisition: no.
- No Sentinel-1 raster, COG, TIFF, SAFE archive, or QA image was created.
- No flood inference was performed.
- No flood mask was generated.
- No flood area was calculated.
- No change detection, training, OSM/ohsome, EMSR927, connectivity, dashboard
  result generation, or GitHub push was performed.

## Exact command result

```powershell
python scripts/phase10d_acquire.py --aoi configs/case_studies/trishuli_2026_aoi.geojson
```

Result: exit code `2`, manifest status `BLOCKED`, failure
`CDSE credentials are missing`. The command reported output CRS `EPSG:32645`,
20 m resolution, dimensions `415 x 248`, two requested bands (`VV`, `VH`),
and no network acquisition.

## Validation

```text
python -m pytest tests/test_phase10d.py  -> 3 passed
python -m pytest                         -> 49 passed
python -m compileall -q src tests scripts -> passed
git diff --check                         -> passed
```

No Sentinel raster or QA artifact is tracked by Git. The phase can be
re-executed after credentials are supplied; it must still remain limited to
bounded acquisition and acquisition QA.

## Correction/update — WinError 3 diagnosis

### LOCAL BUG FOUND

The reported `FileNotFoundError: [WinError 3]` was raised by
`shutil.disk_usage(destination.parent)` in `acquire_scene()`. The default
nested output directory did not exist yet, and Windows therefore could not
inspect its filesystem volume. The failure occurred before the Process API
HTTP request, before Rasterio, and before any raster write. No subprocess,
curl, GDAL executable, or alternate Sentinel product was involved.

### LOCAL BUG FIXED

`acquire_scene()` now creates `destination.parent` before calling
`shutil.disk_usage()`. The atomic `.part` write and existing 512 MiB guard are
unchanged. A regression test uses a missing nested output directory and
confirms that a valid two-band FLOAT32 raster can be written and validated.
The Process API request also sends the obtained token as a Bearer header
without logging or writing the token; a focused test verifies that header.

### REAL PROCESS API REQUEST ATTEMPTED

Yes, one retry was performed after the local path fix:

```powershell
python scripts/phase10d_acquire.py --aoi configs/case_studies/trishuli_2026_aoi.geojson
```

### REAL RASTER ACQUIRED

No. This execution environment reported both CDSE credential presence flags
as false, so the existing authenticator stopped the retry before constructing
the Process API request.

### REAL RASTER VALIDATED

No real raster was returned. The local fake-raster validation path remains
covered by the focused tests.

### BLOCKED

The retry is blocked by missing `RESCUEX_CDSE_CLIENT_ID` and
`RESCUEX_CDSE_CLIENT_SECRET` in this execution environment. Credential
values were not inspected or exposed.

### FAILED

The original local WinError 3 is fixed. No authenticated Process API failure
was observed because the retry did not reach the network.

### NOT_EXECUTED

No Sentinel request, raster acquisition, flood inference, preprocessing,
training, OSM/ohsome, EMSR927, connectivity, or GitHub push was executed.

## AUTHENTICATOR DIAGNOSIS

### Exact failure layer

The execution path is:

`phase10d_acquire.py` -> `CopernicusAuthenticator.get_token()` ->
`POST TOKEN_URL` -> `ProcessAPIClient.request_raster()` ->
`POST PROCESS_URL`.

`AuthenticationError("Copernicus authentication failed")` is raised only by
the broad exception wrapper in `CopernicusAuthenticator.get_token()`. That
wrapper covers the token HTTP request, JSON decoding, missing
`access_token`, and expiry parsing; it does not validate or send a token.
The Process API client is reached only after `get_token()` returns.

### Request comparison

The project uses the same token endpoint specified for the successful direct
test, `grant_type=client_credentials`, the environment variable names
`RESCUEX_CDSE_CLIENT_ID` and `RESCUEX_CDSE_CLIENT_SECRET`, and
`application/x-www-form-urlencoded` encoding. No scope or audience is added.
The parser reads `access_token`, `token_type`, and `expires_in` from the JSON
response. The cached-token path is valid only until 60 seconds before the
recorded expiry.

### Safe diagnostic result

Added `scripts/phase10d_auth_diagnostic.py`, which reports only credential
presence, HTTP status, response content type, safe OAuth error fields,
response-key presence, token type, and expiry. It never prints or stores a
credential, token, or Authorization header.

In this coding-agent runner the diagnostic returned:

```json
{
  "client_id_present": false,
  "client_secret_present": false,
  "reason": "credentials_missing",
  "status": "BLOCKED"
}
```

Therefore the user-reported successful direct OAuth response cannot be
reproduced from this runner: its interactive PowerShell environment is
different from the environment inherited by this process. No conclusion that
the token endpoint rejected the credentials is justified from this run.

### Root cause and classification

The original `AuthenticationError` message is under-specified because it
erases the HTTP/parsing layer. The diagnostic now exposes the safe failure
fields needed to distinguish those cases. Separately, Process API HTTP 401
and 403 responses are now classified as `PROCESS_API_AUTH_FAILURE`, rather
than as CDSE token-authentication failures. A focused test covers that
classification.

No authenticated Process API request was made in this diagnostic phase, so
there is no evidence of a Process API authorization failure and no real
Sentinel raster was acquired or validated.

## Correction/update — Process API failure diagnostics (2026-10-09)

### REAL_EXECUTED

- The prior user-run manifest recorded both credential-presence flags as
  `true`, the BEFORE scene as the first attempted scene, and only the generic
  failure `Process API acquisition failed for ...` with exception type
  `DownloadError`.
- That historical failure did not preserve an HTTP status, response headers,
  response body, or response stage because the original client discarded the
  underlying exception. Its exact server-side cause therefore cannot be
  reconstructed from the old manifest without inventing evidence.
- A new single BEFORE-only retry was attempted with:

  ```powershell
  python scripts/phase10d_acquire.py --aoi configs/case_studies/trishuli_2026_aoi.geojson --before-only
  ```

  ## Diagnostic update — preserve rejected BEFORE GeoTIFF (2026-10-10)

  ### DIAGNOSTIC PRESERVATION IMPLEMENTED

  The failed live BEFORE response was previously written to
  `before_vv_vh.tif.part`, validated, and unconditionally deleted when strict
  validation failed. That cleanup explains why no artifact remained.

  The new opt-in `--preserve-invalid-diagnostic` path keeps production output
  strict and separate. For a BEFORE response only, it atomically preserves the
  original response bytes at
  `data/qa/phase10d_diagnostics/before_rejected.tif` only when the response has
  a TIFF signature, an acceptable image content type, and fits within the
  remaining 512 MiB budget. A JSON/error response, oversized response, or
  non-TIFF response is never saved as a TIFF. The diagnostic directory is
  ignored by Git.

  The accompanying JSON report records response content type, byte size, TIFF
  signature, expected grid, actual validation metadata when readable, failed
  checks, and whether preservation occurred. It contains no credentials,
  tokens, authorization headers, or cookies. The production destination is
  never replaced by a rejected diagnostic artifact and incomplete `.part` files
  are cleaned.

  ### STATUS

  - Diagnostic preservation implemented: `IMPLEMENTED_ONLY`.
  - Diagnostic tests executed: focused and full suites passed.
  - Real request retried in this coding-agent environment: `NOT_EXECUTED`.
  - Response actually received here: `NOT_EXECUTED`.
  - Rejected TIFF preserved here: `NOT_EXECUTED`.
  - Real raster validated here: `NOT_EXECUTED`.

  Run one bounded BEFORE-only retry from the credentialed interactive PowerShell
  session:

  ```powershell
  python scripts/phase10d_acquire.py --aoi configs/case_studies/trishuli_2026_aoi.geojson --before-only --preserve-invalid-diagnostic
  ```

  ## Correction/update — safe AFTER-only acquisition mode (2026-10-10)

  ### IMPLEMENTED

  Added mutually exclusive `--after-only` execution. It first validates the
  existing production BEFORE artifact against the existing manifest, recorded
  verified scene ID, successful SHA-256
  `28e6dd9fef265db3ec4d203e5f7b80d2de06993455a4844f91625559275740fa`, exact
  grid, CRS, dimensions, resolution, VV/VH FLOAT32 bands, finite data, and AOI
  coverage. Missing or inconsistent evidence stops before any network request;
  BEFORE is never reacquired in this mode.

  The mode performs the corrected STAC uniqueness check and one exact AFTER
  request only. It refuses to overwrite an existing AFTER production raster,
  counts the existing BEFORE bytes against the 512 MiB budget, retains atomic
  writes and optional rejected-diagnostic preservation, and records BEFORE
  revalidation, network-request status, AFTER result, and combined storage in
  the acquisition manifest. Existing BEFORE bytes are not rewritten or
  re-enriched.

  ### STATUS

  - `--after-only` implemented: `IMPLEMENTED_ONLY`.
  - Conflicting `--before-only --after-only` flags: rejected before network access.
  - Existing BEFORE artifact: preserved; no live action performed here.
  - AFTER live request by Copilot: `NOT_EXECUTED`.
  - AFTER production raster acquired/validated: `NOT_EXECUTED`.

  Run exactly one credentialed interactive PowerShell attempt:

  ```powershell
  python scripts/phase10d_acquire.py --aoi configs/case_studies/trishuli_2026_aoi.geojson --after-only --preserve-invalid-diagnostic
  ```

  ## Correction/update — local BEFORE provenance reconciliation (2026-10-10)

  The failed AFTER-only preflight exposed an incomplete manifest: the production
  BEFORE TIFF exists and its independently recorded SHA-256 is
  `28e6dd9fef265db3ec4d203e5f7b80d2de06993455a4844f91625559275740fa` with
  size `661872` bytes, but the later failure manifest retained no successful
  BEFORE checksum or validation record. Missing evidence was incorrectly
  reported as a checksum disagreement.

  Added the network-free command
  `scripts/phase10d_reconcile_before.py`. It computes the file hash and size,
  requires the caller-supplied expected hash, runs the existing strict raster
  validation against the unchanged AOI/grid/scene contract, and only then
  restores a `VALIDATED` BEFORE scene record. It never modifies the TIFF,
  reacquires BEFORE, enriches data, contacts CDSE, or treats the rejected
  diagnostic TIFF as production output. Prior failures and rejected-raster
  diagnostics are retained under `attempt_history`.

  AFTER-only preflight now classifies an absent manifest checksum as
  `MISSING_MANIFEST_EVIDENCE`; a genuine hash mismatch remains a hard integrity
  failure. Later failed attempts retain validated BEFORE evidence and append
  attempt history rather than downgrading the scene record.

  Local reconciliation has **not** been run by Copilot. No network request,
  AFTER acquisition, or new raster validation occurred in this environment.
  After running the command below successfully, the repaired manifest will
  permit a later safe AFTER-only attempt:

  ```powershell
  python scripts/phase10d_reconcile_before.py --aoi configs/case_studies/trishuli_2026_aoi.geojson --expected-sha256 28e6dd9fef265db3ec4d203e5f7b80d2de06993455a4844f91625559275740fa
  ```

  ## Final reconciliation update — local production pair provenance (2026-10-10)

  Added `scripts/phase10d_reconcile_pair.py`, a local-only operation that does
  not read CDSE credentials or perform HTTP requests. It verifies both
  production TIFFs exist, match the user-provided SHA-256 values and sizes,
  pass strict CRS/dimension/resolution/transform/dtype/VV-VH/non-empty/AOI
  validation, retain the verified BEFORE and AFTER scene IDs, and have aligned
  grids. Only after all checks pass does it set the pair status to
  `PAIR_ACQUIRED_AND_VALIDATED`, restore both validated scene records, and clear
  the current stale top-level failures. Prior failures and request diagnostics
  are moved unchanged into `attempt_history`; diagnostic TIFFs remain separate
  and untouched. Production TIFFs are never modified.

  Copilot did not run pair reconciliation, acquire data, or make a network
  request. The user should run exactly:

  ```powershell
  python scripts/phase10d_reconcile_pair.py --aoi configs/case_studies/trishuli_2026_aoi.geojson --expected-before-sha256 28e6dd9fef265db3ec4d203e5f7b80d2de06993455a4844f91625559275740fa --expected-after-sha256 c4df94426a9be90e5dcf20b7d14d09165880fd36ae85c0ef34dc9bf1c2663a2b
  ```

  ## Correction/update — align Process API bounds and enrich band metadata (2026-10-10)

  ### REAL PROCESS API RESPONSE / REJECTED DIAGNOSTIC

  The user-provided BEFORE response was a real `image/tiff` with EPSG:32645,
  415 x 248 FLOAT32 pixels, two bands, full AOI coverage, and no declared
  nodata. Its observed resolution and transform did not match the intended
  20 m grid, and CDSE supplied null band descriptions. The original response
  and report at `data/qa/phase10d_diagnostics/before_rejected.tif` and
  `before_rejected.json` remain separate and unchanged.

  ### GRID CORRECTION IMPLEMENTED

  Process API payload construction now sends `AcquisitionGrid.bounds` directly
  instead of recomputing the smaller AOI-projected extent. This requests the
  complete fixed projected grid: EPSG:32645, 415 x 248, 20 m pixels, with the
  existing expected transform and bounds. The legal output schema remains
  width/height only; `resx`/`resy` are not added.

  ### BAND METADATA ENRICHMENT IMPLEMENTED

  The evalscript explicitly returns `[sample.VV, sample.VH]`. When the response
  has two bands, production processing adds only Rasterio band descriptions
  `VV` and `VH`, marked as RescueX-derived metadata. Pixel values, dtype,
  transform, CRS, dimensions, and nodata are not changed. Nodata remains a
  warning when undeclared. The original diagnostic bytes are never enriched or
  overwritten.

  Strict validation still rejects mismatched resolution/transform, dimensions,
  CRS, dtype, empty data, or AOI coverage; it does not resample or relabel
  values.

  ### STATUS AND NEXT COMMAND

  - Real Process API response received: `REAL_EXECUTED` by the user's prior run.
  - Response preserved as rejected diagnostic: `REAL_EXECUTED`.
  - Grid correction and metadata enrichment: `IMPLEMENTED_ONLY`.
  - Local focused/full tests and static checks: passed.
  - Live retry from this coding-agent environment: `NOT_EXECUTED`.
  - Production raster acquired and validated: `NOT_EXECUTED`.

  Run exactly one credentialed BEFORE-only attempt:

  ```powershell
  python scripts/phase10d_acquire.py --aoi configs/case_studies/trishuli_2026_aoi.geojson --before-only --preserve-invalid-diagnostic
  ```

  ## Correction/update — Process API output dimension contract (2026-10-10)

  ### LOCAL FIX IMPLEMENTED

  The credentialed BEFORE-only request reached the CDSE Process API and returned
  HTTP 400 `COMMON_BAD_PAYLOAD`: `Only width and height or resx and resy can be
  set at the same time.` The payload contained both dimension specifications.

  The Process API output object now uses the fixed `width` and `height` grid
  only. `resx` and `resy` were removed; the existing projected
  `EPSG:32645` bounds, 415 x 248 grid, 20 m `AcquisitionGrid`, VV/VH FLOAT32
  evalscript, processing parameters, and 512 MiB budget are unchanged.

  Returned GeoTIFF validation now rejects any mismatch in dimensions, CRS,
  20 m pixel size, VV/VH band descriptions, transform, readability,
  non-empty finite data, or AOI intersection. It does not resample or silently
  accept a different grid.

  ### TESTS PASSED

  The focused Phase 10D suite and full regression suite passed, along with
  compileall and `git diff --check`.

  ### LIVE REQUEST / REAL RASTER STATUS

  The reported live request was not repeated from this coding-agent
  environment. No new authenticated Process API request was made, no real
  raster was acquired, and no real raster was validated. No AFTER request or
  downstream analysis was executed.

  Run exactly this single BEFORE-only command from the credentialed interactive
  PowerShell session:

  ```powershell
  python scripts/phase10d_acquire.py --aoi configs/case_studies/trishuli_2026_aoi.geojson --before-only
  ```

  In this coding-agent runner the authenticator saw both credentials absent
  and stopped before the Process API. No HTTP response was captured, no
  Sentinel request reached CDSE, and no raster was acquired.

### IMPLEMENTED_ONLY

- `ProcessAPIClient` now records safe diagnostics for request failures:
  endpoint, stage, HTTP status when provided, response content type,
  whether a response body was received, error type, and bounded sanitized
  JSON error fields or body preview.
- Credentials, access tokens, Authorization headers, cookies, and secrets
  are excluded from diagnostics. The diagnostics are attached to the
  acquisition manifest as `request_diagnostics` when a Process API request
  actually returns an error.
- HTTP 401/403 remains classified as `PROCESS_API_AUTH_FAILURE`; other HTTP
  or transport failures are classified as Process API request failures rather
  than token-authentication failures.
- Added `--before-only` so a diagnostic retry cannot start the AFTER request.
- Added regression coverage for sanitized HTTP 400 diagnostics, endpoint and
  stage recording, authorization-header behavior, and the existing exact
  scene/budget/raster checks.

### Process API scene-selection evidence

- The current official Sentinel-1 GRD page documents `timeRange`,
  `acquisitionMode`, `polarization`, and `orbitDirection` filters, but does
  not list `ids` in its S1GRD filtering table:
  https://documentation.v1.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html
- An official Copernicus beginner-guide example uses `dataFilter.ids` for
  Sentinel-2:
  https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/UserGuides/BeginnersGuide.html
- The official S1GRD examples use `timeRange` and the documented S1GRD
  filters, not `ids`:
  https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Process/Examples/S1GRD.html
- Therefore this phase does not silently remove the exact-scene constraint or
  replace it with an unverified time range. No evidence currently proves that
  `ids` is accepted for this S1GRD Process API path, and a time-range
  fallback would require an explicit uniqueness check before it could be safe.

### BLOCKED

- The user-reported successful OAuth response and credentialed
  `DownloadError` run occurred in an interactive PowerShell environment that
  is not inherited by this coding-agent runner. The diagnostic run here
  reported `client_id_present=false` and `client_secret_present=false`.
- Consequently, no sanitized HTTP status or response body can be reported
  from this runner, and the exact server-side cause of the user-run
  `DownloadError` remains unobserved.

### FAILED

- No new authenticated Process API failure occurred in this diagnostic
  phase. The prior generic `DownloadError` remains historical evidence only;
  it is not reclassified as OAuth, schema rejection, scene-selection
  failure, response download failure, or TIFF validation failure without a
  captured response.

### NOT_EXECUTED

- No AFTER request was made.
- No full-product download, Sentinel raster acquisition, TIFF validation,
  preprocessing, flood inference, training, OSM/ohsome, EMSR927,
  connectivity, or GitHub push was performed.

## Correction/update — documented S1GRD filters and STAC uniqueness (2026-10-10)

### REAL_EXECUTED

- No new live authenticated request was made from the coding-agent
  environment, as required because its interactive PowerShell credentials are
  unavailable.
- Phase 10C’s selected scene metadata remains unchanged:
  - BEFORE `S1D_IW_GRDH_1SDV_20260816T122141_20260816T122206_004151_007980_B091_COG`,
    `2026-08-16T12:21:41Z`–`12:22:06Z`.
  - AFTER `S1D_IW_GRDH_1SDV_20260828T122141_20260828T122206_004326_007FA4_C73B_COG`,
    `2026-08-28T12:21:41Z`–`12:22:06Z`.
- The existing historical acquisition manifest remains unchanged as evidence
  of the previous generic `DownloadError`; it does not prove a server-side
  rejection reason.

### IMPLEMENTED_ONLY

- Removed `dataFilter.ids` from Process API payload construction.
- Each request now uses only the documented S1GRD filter fields:
  `timeRange`, `acquisitionMode: IW`, `orbitDirection: ASCENDING`, and
  `polarization: DV`.
- The time range is the exact 25-second acquisition window encoded by the
  selected product identifier; it is never widened.
- Before each Process API request, the public CDSE STAC search queries the
  unchanged AOI and that exact window. Processing is allowed only when one
  returned feature has the expected candidate ID, Sentinel-1D platform, IW
  mode, ascending direction, relative orbit 85, VV/VH polarization, and AOI
  intersection. Zero, missing, or ambiguous distinct acquisition results
  stop before processing.
- The Process API response is not currently sufficient to prove the exact
  STAC item was used. This implementation therefore reports STAC uniqueness
  provenance, not explicit item-ID binding.

### BLOCKED

- No live retry was performed. The user must run the first retry from the
  credentialed interactive PowerShell session.
- Official S1GRD documentation lists the filters used above and its examples
  use narrow `timeRange`; it does not list `ids` in the S1GRD filter table.
  The generic official guide’s `ids` example is for Sentinel-2 and is not
  treated as proof for S1GRD.

### FAILED

None in this correction. The prior generic `DownloadError` remains historical
and is not reinterpreted without the response diagnostics that were absent.

### NOT_EXECUTED

- No authenticated Process API request, real raster acquisition, or TIFF
  validation occurred in this coding-agent run.
- No AFTER request is authorized by the corrected first retry command.
- No flood inference, preprocessing, training, OSM/ohsome, EMSR927,
  connectivity, dashboard analysis, or GitHub push occurred.

### Tests and next command

Focused and full regression tests validate documented payload fields,
absence of `dataFilter.ids`, exact non-widened windows, STAC uniqueness and
ambiguity rejection, orbit/mode/polarization matching, budget enforcement,
and sanitized failure diagnostics.

After reviewing the manifest and report, run exactly this first retry from
the interactive PowerShell session containing the verified credentials:

```powershell
python scripts/phase10d_acquire.py --aoi configs/case_studies/trishuli_2026_aoi.geojson --before-only
```

This command performs one STAC uniqueness check and one bounded BEFORE
Process API request only. It must stop on ambiguity, invalid response, or
validation failure; it does not automatically request the AFTER scene.

## Correction/update — STAC uniqueness gate aligned with working catalogue query (2026-10-10)

### LOCAL CODE FIX

The gate previously sent an `intersects` GeoJSON filter with `limit: 20` and
required the returned `properties.datetime` to equal the product timestamp
without fractional seconds. The public catalogue returns a FeatureCollection
with a fractional-second timestamp (for example,
`2026-08-16T12:21:41.058298Z`), so the valid item was rejected and the
orchestration reported `STAC_UNIQUENESS_FAILURE`.

The gate now matches the proven working request shape: POST JSON with the AOI
`bbox`, the unchanged narrow interval, collection `sentinel-1-grd`, and
`limit: 100`. It parses the top-level FeatureCollection and accepts fractional
seconds when they resolve to the expected acquisition second. It still
requires the exact scene ID, Sentinel-1D platform, timestamp, IW mode,
ascending direction, relative orbit 85, VV/VH polarizations/assets, and AOI
intersection.

Catalogue outcomes are now distinct: transport/HTTP or malformed responses
raise `CatalogUnavailableError`; zero items raise `CatalogNoMatchError`;
multiple items raise `CatalogAmbiguousError`; and one item failing metadata
validation raises `CatalogValidationError`.

### PUBLIC STAC VERIFICATION

The credential-free command `python scripts/phase10d_stac_check.py` was run
successfully against the public catalogue:

- BEFORE: matching item count `1`; metadata verification
  `VERIFIED_UNIQUE`; expected scene ID accepted.
- AFTER: matching item count `1`; metadata verification
  `VERIFIED_UNIQUE`; expected scene ID accepted.

This verifies catalogue metadata only. It does not prove Process API scene
selection, raster acquisition, or raster validation.

### AUTHENTICATED PROCESS API REQUEST

Not executed from this coding-agent environment because interactive CDSE
credentials are unavailable here. No authenticated retry was performed.

### REAL RASTER ACQUIRED / RASTER VALIDATED

No new real raster was acquired or validated. No AFTER Process API request,
full-product download, inference, preprocessing, OSM/EMSR927, connectivity,
or GitHub push was performed.

### TESTS AND NEXT COMMAND

Focused Phase 10D tests, the public catalogue-only check, compilation, and
diff validation passed. The next user-side command is the bounded BEFORE-only
retry from the credentialed interactive PowerShell:

```powershell
python scripts/phase10d_acquire.py --aoi configs/case_studies/trishuli_2026_aoi.geojson --before-only
```
