# RescueX FloodUNet model card

**Status:** implemented baseline and synthetic smoke path; no real training
result yet.

**Purpose:** pixel-level flood/water segmentation for later geospatial
analysis. **Input:** prepared georeferenced satellite raster, initially
Sentinel-1 channels. **Output:** probability raster and thresholded binary
flood mask.

**Architecture:** lightweight U-Net. **Training data:** intended Kuro Siwo
CC BY dataset; not downloaded in this phase. **Target:** 0 background,
1 flood/water, with ignore/nodata preserved by the dataset adapter.

**Intended use:** research prototype and explainable flood extent baseline.
**Not intended:** structural damage confirmation, debris classification,
hydrodynamic simulation, or emergency certainty. Known risks include
geographic domain shift, terrain/radar effects, cloud/mask quality, and
dataset-label differences. Trishuli must remain an unseen qualitative
generalization case unless permitted independent labels exist.
