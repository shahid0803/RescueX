# RescueX data governance and provenance

This document is normative for all later phases. The machine-readable
allowlist is `configs/data-sources.json`; code should reject sources not
listed there rather than relying on developer memory.

## Production boundary

The production path may consume only:

1. Sentinel-1 radar imagery.
2. Sentinel-2 optical imagery.
3. Copernicus DEM.
4. An OpenStreetMap snapshot dated before the event.
5. Challenge-permitted training data.

Every scene and OSM snapshot must carry source, acquisition/snapshot date,
product identifier, AOI, processing level, CRS, and a local cache checksum in
the run manifest. A pair is rejected when its dates, orbit track, CRS, or AOI
cannot be validated. Sentinel-1 before/after pairs should use the same orbit
track where possible; scenes from different tracks must not be compared as
if they were pixel-aligned.

Production input validation must also enforce `snapshot_date < event_date`
for OSM and must keep validation references in a separate namespace from
production inputs.

## Validation boundary

Copernicus EMSR927 and other published damage maps may be used only after the
FloodLens result is produced, for comparison and error analysis. They must
never be passed into training, preprocessing, feature extraction, inference,
prompting, retrieval, or hidden-reference code paths. Post-event OSM edits
are likewise prohibited from production analysis.

## Model and evaluation

The planned segmentation model is an explainable U-Net-style model behind the
`FloodSegmenter` interface. Splits must be geographic/scene-level rather than
random neighboring tiles. Trishuli is an external generalization evaluation
area, not a training tile. Report only metrics calculated by the evaluation
run (IoU, Dice/F1, precision, and recall).

## Attribution

Use the exact attribution strings in `README.md` in the dashboard and
exported situation report. Cite the license and source for every training
dataset actually used; do not claim a dataset was used when it was not.

## Engineering guardrails

- No credentials, access tokens, downloaded imagery, or large datasets belong
  in git.
- All downloads must be resumable, checksum-verified, cached, and recorded in
  a manifest before use.
- A validation artifact must not be accepted by a production input contract.
- Numbers in reports must be derived from structured results, never generated
  by an LLM or hard-coded fixture.
