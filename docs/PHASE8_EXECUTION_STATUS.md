# Phase 8 real-data execution status

The original Phase 8 gate was run locally on 2026-10-03 with a global
`NO_GO`. That output is historical. Phase 8A replaces the global decision
with independent domain statuses in `data/manifests/phase8_readiness.json`;
the manifests directory is ignored by Git.

## Gate result

The historical result was **NO_GO — AUTHENTICATION_BLOCKED.** Neither
`RESCUEX_CDSE_CLIENT_ID` nor `RESCUEX_CDSE_CLIENT_SECRET` is present in the
local environment. No token request, product download, Kuro Siwo download,
real training, real evaluation, Sentinel inference, Trishuli case study,
historical OSM extraction, infrastructure result, connectivity result, or
EMSR927 comparison was claimed.

The official CDSE authentication endpoint documented for the current
Sentinel Hub OAuth2 flow is:

`https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token`

The existing metadata interface remains:

`https://stac.dataspace.copernicus.eu/v1/search`

## Local setup required to proceed

Configure credentials in the local process environment or an ignored `.env`
file; never paste them into chat, commit them, or place them in manifests:

```powershell
$env:RESCUEX_CDSE_CLIENT_ID = "<local client id>"
$env:RESCUEX_CDSE_CLIENT_SECRET = "<local client secret>"
python scripts/phase8_readiness.py
```

After the gate reports readiness, the next controlled steps are a token
smoke test, a metadata-only AOI query, and a small approved Kuro Siwo
inspection. No large download should begin before size and compatibility are
recorded.

## Current execution categories

| Work item | Status |
| --- | --- |
| Environment audit | REAL_EXECUTED |
| CDSE credential readiness | BLOCKED |
| CDSE authentication smoke test | BLOCKED |
| Kuro Siwo retrieval/inspection | BLOCKED |
| Real model training/evaluation | BLOCKED |
| Real Sentinel product processing | BLOCKED |
| Trishuli inference | BLOCKED |
| Historical OSM retrieval | NOT_EXECUTED |
| Real infrastructure/connectivity analysis | BLOCKED |
| EMSR927 validation | NOT_APPLICABLE |

No synthetic checkpoint, flood mask, metric, area, asset count, road result,
or validation score is substituted for any blocked result. See
[PHASE8A_IMPLEMENTATION_REPORT.md](PHASE8A_IMPLEMENTATION_REPORT.md) for the
decoupled readiness model.
