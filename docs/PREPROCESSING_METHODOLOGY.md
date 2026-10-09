# RescueX Phase 2 preprocessing methodology

## Scope

Phase 2 produces validated, georeferenced analysis-ready raster products. It
does not detect floods, train a model, infer damage, or perform connectivity
analysis. A resampled common grid is **geometric alignment**, not image
co-registration.

## Raster and CRS policy

Rasterio is the baseline reader/writer. Every input is checked for CRS,
transform, finite bounds, positive resolution, dimensions, band count, and
readability. GeoTIFF remains authoritative; PNG previews are diagnostic only.
AOIs are clipped with geographic masking, preserving nodata and transform.
Reprojection records source and output CRS. An `auto` analysis CRS should be
selected in a later service from the AOI's suitable projected CRS; no Nepal
zone is hard-coded.

Before/after alignment rejects non-overlap and reprojects both inputs to a
common CRS/resolution/grid. Continuous values use bilinear resampling;
categorical masks use nearest-neighbor. This does not claim sub-pixel
co-registration.

## Sentinel-1

The baseline exposes Sentinel-1 GRD asset resolution and records a
`source_calibrated` backscatter representation. It does not claim to have
performed calibration, thermal-noise removal, speckle filtering, terrain
correction, or orthorectification. Those operations require a validated
processing backend and DEM-backed configuration; the configuration contains
explicit flags, defaulting to disabled. A raw DN is never labelled calibrated
backscatter.

The official CDSE Sentinel-1 GRD processing documentation
([S1 GRD](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html)
and [processing examples](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Process/Examples/S1GRD.html))
describes
calibration, thermal-noise removal, optional speckle filtering, and
Range-Doppler/radiometric terrain correction. RescueX records these as future
backend decisions rather than inventing a local algorithm.

## Sentinel-2

Sentinel-2 L2A asset resolution supports spectral bands and SCL. The
[official Level-2A documentation](https://documentation.dataspace.copernicus.eu/Data/SentinelMissions/Sentinel2.html)
defines the known
SCL cloud/cloud-shadow/invalid classes are 3, 8, 9, 10, 1, 7, and 11;
masking is configurable and preserves a mask rather than deleting a scene.
L2A DN reflectance scaling is explicit (`DN / 10000`) and is not applied to
unknown representations. Bands at different native resolutions are not
stacked implicitly.

## Nodata, QC, and provenance

Nodata remains distinct from valid zero and invalid numeric values. QC
calculates valid/nodata fractions from the actual array. Every processing
manifest links source and output paths, checksums, CRS, transform-derived
bounds/resolution, configuration, steps, software version, and pipeline
version.

## Limitations

No real CDSE product processing was executed in this phase because
credentials/product access were unavailable. Synthetic GeoTIFFs are
development fixtures only. The baseline does not yet implement ESA SNAP or a
remote CDSE processing backend.
