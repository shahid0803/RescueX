# RescueX architecture

## System boundary

```text
Web dashboard
      |
Backend/API ---- structured run contracts ---- provenance manifest
      |
  +---+-------------------+
  |                       |
Data acquisition       ML service
  |                       |
Sentinel-1/2          flood segmentation
  |                       |
  +----------+------------+
             |
      geospatial engine
       OSM / Copernicus DEM
             |
   processing and alignment
       +-----+------+
       |            |
 damage analysis  network analysis
       |            |
       +-----+------+
             |
   structured results -> map layers + situation report
```

## Layer responsibilities

- **Contracts:** validate dates, identifiers, CRS, geometry references, and
  provenance before work crosses a boundary.
- **Acquisition:** search, pair, download, cache, checksum, and record scenes.
  Providers are adapters; the processing layer does not call provider APIs.
- **ML:** train/evaluate/infer segmentation with geographic or scene-level
  splits. It emits a georeferenced mask and measured metrics.
- **Geospatial engine:** aligns rasters, overlays pre-event OSM, and preserves
  CRS/transform/bounds.
- **Analysis:** distinguishes spatially affected, potentially blocked, and
  confirmed damage; graph analysis removes affected edges and checks alternate
  routes.
- **Presentation:** renders computed layers and report text, never invents
  measurements.

## Phase plan

1. Foundation (this phase): contracts, registry, configuration, governance,
   docs, tests, CI.
2. Acquisition and preprocessing: provider adapters, cache, scene pairing,
   raster alignment and QA.
3. Segmentation: permitted dataset preparation, geographic splits, training,
   evaluation, and georeferenced inference.
4. Damage and connectivity: OSM snapshot ingestion, transparent overlap
   analysis, road graph and cut-off settlements.
5. Dashboard/report: map layers, processing status, export, demo flow, and
   EMSR927 validation comparison.
