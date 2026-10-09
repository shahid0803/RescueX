# Satellite data download guide

## Account and local configuration

Register an account and OAuth client in the Copernicus Data Space Ecosystem.
Copy credentials only into a local secret manager or ignored `.env` file.
Start from `.env.example`; never commit `.env`.

```powershell
python -m pip install -e ".[dev]"
$env:RESCUEX_CDSE_CLIENT_ID = "local-client-id"
$env:RESCUEX_CDSE_CLIENT_SECRET = "<local client secret>"
```

The API and CLI never print these values. A local download root is configured
with `RESCUEX_DATA_DIR`; raw, interim, processed, and manifest directories
remain separate.

## Search

Prepare a small GeoJSON geometry file, then run:

```powershell
rescuex satellite search --aoi aoi.json --date 2026-08-26 --sensor sentinel-1
rescuex satellite search --aoi aoi.json --date 2026-08-26 --sensor sentinel-2 --max-cloud-percentage 30
```

The command performs live metadata discovery and prints candidates and the
validated pair. It does not download all candidates.

## Download and provenance

The download service receives a selected `SatelliteScene`, requests one
OAuth2 token when needed, streams to a `.part` file, retries with bounded
exponential backoff, rejects zero-byte files, atomically renames on success,
computes SHA-256, and writes a JSONL manifest. Existing non-empty files are
cache hits and are not downloaded again.

Do not place SAFE archives, JP2s, GeoTIFFs, or credentials in git. The
repository stores code and metadata only.
