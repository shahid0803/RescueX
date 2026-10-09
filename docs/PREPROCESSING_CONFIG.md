# Preprocessing configuration

`floodlens.satellite.preprocessing.PreprocessingConfig` is the explicit
baseline configuration:

| Field | Default | Meaning |
| --- | --- | --- |
| `analysis_crs` | `auto` conceptually; baseline `EPSG` must be supplied by caller | projected CRS for metric/grid work |
| `target_resolution` | `null` | preserve source unless an explicit grid resolution is selected |
| `clip_to_aoi` | `true` | mask and crop using AOI geometry |
| `sentinel1_backscatter` | `source_calibrated` | metadata declaration only; no calibration claim |
| `sentinel1_terrain_correction` | `false` | requires a real supported backend and Copernicus DEM |
| `sentinel1_speckle_filter_enabled` | `false` | avoids unvalidated smoothing in the baseline |
| `sentinel2_bands` | B02, B03, B04, B08 | explicit spectral selection |
| `sentinel2_cloud_mask` | `true` | preserve SCL-derived mask |
| `sentinel2_scl_classes_to_mask` | 3, 8, 9, 10, 1, 7, 11 | cloud/shadow/invalid classes |
| `nodata_value` | -9999 | output nodata where a writer needs a value |
| `resampling` | `bilinear` | continuous data; categorical data overrides to nearest |

Outputs use deterministic sensor/scene/role names under
`data/processed/satellite/`. Raw products under `data/raw/` are never
overwritten. Processing manifests and QC sidecars are stored separately.
