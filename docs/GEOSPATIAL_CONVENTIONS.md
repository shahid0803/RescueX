# Geospatial conventions

- GeoJSON coordinates are `[longitude, latitude]` in `EPSG:4326`.
- Raster CRS, affine transform, bounds, and resolution are preserved and
  recorded on every operation.
- Degree coordinates are not used for metric distance/area calculations.
- AOI clipping is geographic masking, not array slicing.
- Continuous rasters use bilinear resampling by default; categorical layers
  use nearest-neighbor.
- A common raster grid is geometric alignment only; it is not proof of
  image-to-image co-registration.
- Nodata, cloud masks, and invalid numeric values remain distinguishable.
