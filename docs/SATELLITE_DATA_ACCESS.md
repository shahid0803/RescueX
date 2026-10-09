# Satellite data access

## Official interface decision (checked 2026-10-03)

RescueX uses the current **Copernicus Data Space Ecosystem STAC API** for
metadata discovery:

`https://stac.dataspace.copernicus.eu/v1/search`

The current official STAC documentation says the STAC catalog is
complementary to OData, implements STAC 1.1.0 discovery concepts, and
provides a POST `/search` endpoint. CDSE release notes explicitly state that
the legacy `https://catalogue.dataspace.copernicus.eu/stac` endpoint was
deprecated from 17 November 2025. RescueX therefore does not use that legacy
URL.

STAC is selected because it gives a standard GeoJSON response, AOI
intersection, temporal filtering, collection filtering, pagination/limits,
and normalized item assets. The provider is isolated in
`floodlens.satellite.stac.CDSEStacProvider`, so a future OData or SDA adapter
can be added without changing selection or downstream contracts.

## Authentication

Catalog metadata search is implemented as a public STAC request. Product
downloads use a dedicated `CopernicusAuthenticator` and OAuth2 client
credentials against the current CDSE token endpoint:

`https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token`

Credentials are read only from `RESCUEX_CDSE_CLIENT_ID` and
`RESCUEX_CDSE_CLIENT_SECRET`. Tokens are cached until shortly before expiry
and are never logged. The official authentication documentation warns against
requesting a new token for every request; the implementation follows that
guidance.

## Request flow

1. Validate GeoJSON AOI and event date.
2. Build a configurable UTC search interval.
3. Query the Sentinel-1 GRD or Sentinel-2 Level-2A STAC collection.
4. Normalize items into `SatelliteScene`.
5. Filter by AOI intersection and before/after relationship.
6. Rank and validate a pair.
7. Download only selected products through the authenticated downloader.
8. Cache the file and append a redacted provenance record to
   `data/manifests/downloads.jsonl`.

No credentials, raw products, or tokens are committed.

## Limitations

This phase does not perform raster subsetting, SAFE/JP2 interpretation,
reprojection, cloud masking, or ML inference. The STAC asset selected by a
catalog item must be reviewed before a production downloader is enabled for a
specific product type. Real CDSE authentication/download was not executed in
this environment because credentials were not configured.
