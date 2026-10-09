# Phase 10A — CDSE Sentinel-1 Trishuli Discovery + Before/After Pair Validation

## REAL_EXECUTED

- The Phase 10A readiness/discovery runner was executed:
  `python scripts/phase10a_discovery.py`.
- The current CDSE STAC root and OAuth token endpoint were used as the
  configured official endpoints; no deprecated catalogue endpoint was used.
- The non-secret authentication audit found neither
  `RESCUEX_CDSE_CLIENT_ID` nor `RESCUEX_CDSE_CLIENT_SECRET`.
- The repository search covered the configured Trishuli case-study paths and
  found no authoritative AOI geometry or event date.
- The result was written to
  `data/manifests/trishuli_sentinel1_pair_manifest.json`.

## IMPLEMENTED_ONLY

- `scripts/phase10a_discovery.py` performs a metadata-only run when an
  authoritative AOI and event date are supplied.
- It uses the existing `CDSEStacProvider`, `SatelliteService`, deterministic
  selector, and pair validator rather than duplicating acquisition logic.
- The provider can attach a bearer token obtained through the existing
  environment-backed authenticator without logging credentials or tokens.
- The runner records candidate metadata, selected-candidate rationale, orbit
  compatibility, polarization, coverage validation, endpoint status, and
  download decision without downloading imagery.

## BLOCKED

- Real Trishuli scene discovery is blocked because the repository contains no
  authoritative Trishuli AOI geometry and no authoritative event date.
- Authenticated CDSE discovery is blocked because both CDSE environment
  credentials are absent.
- No scene ID, acquisition date, coverage status, or pair was fabricated.
- The generated manifest records zero candidates and no selected pair.

## FAILED

None. The runner stopped at the required missing-input gate rather than
issuing an invented case-study query.

## NOT_EXECUTED

- No OAuth token request.
- No authenticated or case-study STAC search.
- No Sentinel-1 product download.
- No raster preprocessing, flood segmentation, change detection, impact
  analysis, connectivity analysis, OSM/ohsome extraction, EMSR927 use, or
  report generation from Sentinel results.
- No training was performed.

## Authentication status

**BLOCKED.** Credential presence was checked only as booleans. Values were
never read into the report, printed, or committed. The configured token
endpoint is:
`https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token`.

## AOI and event-date source

**MISSING.** The runner searched:

- `configs/trishuli.json`
- `configs/trishuli.geojson`
- `configs/case-studies/trishuli.json`
- `configs/case-studies/trishuli.geojson`
- `examples/trishuli.json`
- `examples/trishuli.geojson`

No authoritative source was found. An approximate bounding box or guessed
date was intentionally not substituted.

## Candidates, pair, orbit, polarization, and coverage

**NOT_EXECUTED.** Candidate count is zero because the required AOI/date gate
failed. Therefore there are no selected before/after IDs, orbit details,
polarization details, or coverage claims.

## Download decision

**REAL_EXECUTED.** The decision was **do not download**. Phase 10A ended before
any imagery request and the manifest records `imagery_downloaded: false`.

## Manifest and provenance

The metadata-only output is
`data/manifests/trishuli_sentinel1_pair_manifest.json`. It records the phase
status, public endpoint checks, credential-presence booleans, searched
case-study paths, missing-input blockers, zero candidate IDs, and the
no-download decision. Generated manifests are ignored by Git.

## Tests

**IMPLEMENTED_ONLY.** Existing satellite tests cover AOI validation,
same-relative-orbit selection, missing-side behavior, authentication
missing-credential behavior, and provider boundaries. The Phase 10A runner
was compiled and its blocked-mode CLI execution completed as expected.
The full regression suite and final diff checks remain the required
validation commands for this change.

## Exact commands

```powershell
python scripts/phase10a_discovery.py
python -m pytest
python -m compileall -q src tests scripts
git diff --check
```

## Limitations

This phase establishes no flood result and no Sentinel pair. A future run
must provide the authoritative Trishuli AOI and event date, then rerun the
metadata-only command with `--aoi <path> --event-date YYYY-MM-DD`. Credentials
must be configured separately if authenticated CDSE access is required.
