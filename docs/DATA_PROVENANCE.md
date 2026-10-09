# Raster data provenance

RescueX maintains this chain:

```text
data/raw/satellite/  ->  data/interim/satellite/  ->  data/processed/satellite/
       downloaded             extracted/aligned             AOI-ready GeoTIFF
```

The Phase 1 download manifest identifies the source scene, provider,
acquisition time, local raw file, file size, and SHA-256. Phase 2 processing
manifests add input/output paths and checksums, source/output CRS, bounds,
resolution, bands, nodata policy, resampling, configuration, processing
steps, pipeline version, and software information. A derived product is not
valid without its source scene and manifest linkage.

Raw products are immutable. Temporary `.part` outputs are atomically renamed
only after successful writing. Failed processing must not be represented by a
complete output. Raw products and manifests are excluded from git.
