# RescueX data-source registry

The canonical registry is [`configs/data-sources.json`](../configs/data-sources.json).
Each entry declares whether it may enter the production pipeline or is
validation-only.

## Allowed production sources

| Source | Role | Required record |
| --- | --- | --- |
| Sentinel-1 | cloud-tolerant radar before/after observation | product ID, acquisition time, orbit, processing level, CRS, checksum |
| Sentinel-2 | optical observation when cloud conditions permit | product ID, acquisition time, cloud metadata, processing level, CRS, checksum |
| Copernicus DEM | elevation context/supporting analysis | tile ID, version, CRS, checksum |
| OpenStreetMap pre-event snapshot | buildings, roads, bridges, settlements, destinations | snapshot date, event date, extract source, checksum |

## Validation-only sources

Copernicus EMSR927 and other published damage maps can be used only for
post-run comparison and error analysis. They must never satisfy a production
input contract. This distinction is enforced in `registry.py`.

## Acquisition rules

Search must be AOI- and date-bounded. Before/after Sentinel-1 scenes should
share an orbit track. Downloads must use a temporary file, verify a checksum,
atomically move into the cache, and persist the metadata manifest. A failed or
partial download is not a usable scene.
