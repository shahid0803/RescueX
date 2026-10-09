# Phase 10B — Trishuli Case-Study Configuration + CDSE Credential Gate

## REAL_EXECUTED

- The event date was recorded as **2026-08-26** from the Multimodal AI
  Hackathon 2026 Track B case-study specification: “August 2026 Trishuli
  flood.”
- A machine-readable case-study configuration was added at
  `configs/case_studies/trishuli_2026.json`.
- The Phase 10B input check was executed:
  `python scripts/phase10b_case_study_check.py`.
- The generated manifest is
  `data/manifests/trishuli_case_study_manifest.json`.
- The check confirmed the event date is ready, AOI is missing user input,
  CDSE credentials are blocked, Sentinel discovery is blocked, and no
  network search was performed.

## IMPLEMENTED_ONLY

- `scripts/phase10b_case_study_check.py` accepts `--aoi <path>`, reuses the
  existing `AOI` validator, checks credential presence without exposing
  values, and records explicit dependency statuses.
- `configs/case_studies/trishuli_2026.template.geojson` is an empty,
  clearly-labelled template and contains no fabricated geometry.
- The manifest distinguishes event-date readiness from AOI and CDSE blockers.

## BLOCKED

- AOI is `MISSING_USER_INPUT`; the challenge material does not provide an
  authoritative polygon. No bounding box, river corridor, EMSR927 footprint,
  or published damage geometry was inferred.
- CDSE authentication is blocked because
  `RESCUEX_CDSE_CLIENT_ID` and `RESCUEX_CDSE_CLIENT_SECRET` are absent.
- Sentinel discovery and pair validation remain blocked behind both inputs.

## FAILED

None.

## NOT_EXECUTED

- No Sentinel scene search, OAuth token request, imagery download, flood
  inference, preprocessing, OSM/ohsome extraction, connectivity, or EMSR927
  access.
- No training or GitHub push.

## Exact commands

```powershell
python scripts/phase10b_case_study_check.py
python -m pytest
python -m compileall -q src tests scripts
git diff --check
```

## Required next inputs

1. A team/user-supplied GeoJSON AOI path passed with `--aoi`.
2. CDSE client ID and secret in the established environment variables.

Only after both are available may the metadata-only Phase 10A discovery
runner be considered; this phase does not perform that search.
