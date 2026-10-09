# Phase 11B — Sentinel-1 / Kuro Siwo SAR Representation Compatibility Audit

## Decision

**REAL_EXECUTED:** The audit re-read the existing local Kuro Siwo samples,
recomputed the training normalization, verified the real Sentinel-1 files and
checkpoint hashes, and wrote
`data/manifests/sentinel_kuro_siwo_compatibility.json`.

**Final compatibility status: `INDETERMINATE`.** The checkpoint must not be
used for Sentinel inference yet. The channel names/order and floating-point
arrays are not sufficient evidence of physical representation equivalence.

**Recommended next action: D — More source evidence or a controlled
compatibility experiment.** The pinned Kuro Siwo source revision cannot
currently be resolved by the official repository API, and the available
official GRD graph differs materially from RescueX's Process API contract.
Arbitrary scaling, dB conversion, clipping, or inference would therefore be
premature.

## Sources and revision status

The recorded dataset source is
`orion-ai-lab/Kuro-Siwo-Webdataset` at revision
`e8e61b7b1254b04bfa2b5e26d43db90cb86b5004`. The pinned
`configs/grd_preprocessing.xml` URL was checked but the revision was not
resolvable; it was not silently replaced.

For bounded source evidence, the official repository's available
`main/configs/grd_preprocessing.xml` was inspected. Its retrieved blob SHA is
`09f180da6e803d4a5c389903e42ed059215e01e3`. Relevant official sources are
recorded in the JSON manifest:

- Repository: <https://github.com/Orion-AI-Lab/KuroSiwo>
- Dataset: <https://huggingface.co/datasets/orion-ai-lab/Kuro-Siwo-Webdataset>
- GRD graph: <https://github.com/Orion-AI-Lab/KuroSiwo/blob/main/configs/grd_preprocessing.xml>
- Paper: <https://arxiv.org/abs/2311.12056>
- CDSE S1GRD documentation:
  <https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html>

## Kuro Siwo evidence

The existing local Phase 9C samples were used; no dataset was downloaded.
The seven selected training samples are source keys `000000` through
`000006`; the loader reads `flood_vv.npy` then `flood_vh.npy`, concatenates
two FLOAT32 channels, and retains `valid_mask == 1` for training loss and
statistics. The source mask conversion is class 2 → flood 1 and classes 0/1
→ background 0.

The actual training implementation was imported and run only through its
sample-loading and normalization functions. Recomputed values match the
checkpoint manifest:

| Channel | Raw min–max | Raw mean | Raw stddev | Normalized mean | Normalized stddev |
|---|---:|---:|---:|---:|---:|
| `flood_vv` | 0.001876–1.589664 | 0.0947169513 | 0.0705694184 | approximately 0 | 1 |
| `flood_vh` | 0.000844–12.238182 | 0.0209812708 | 0.0459058620 | approximately 0 | 1 |

The full shapes, dtypes, percentiles, finite/zero/negative counts, and
per-channel normalized statistics are in the JSON artifact. This verifies the
normalization implementation, but does not establish the physical units of
the source arrays. The checkpoint is the real `FloodUNet` checkpoint and was
not changed; its SHA-256 remains
`dc1da66fb3a837bf93f406330ace78245e385248c5b7b9443de47810481fa52d`.

The available official GRD graph establishes: precise-orbit application,
thermal-noise removal, GRD border-noise removal, Sigma0 calibration with
`outputImageScaleInDb=false`, Lee Sigma speckle filtering, and SRTM terrain
correction with 10 m pixel spacing. Its graph also sets
`applyRadiometricNormalization=false`. Because the recorded revision is
unavailable, these findings are explicitly fallback-source evidence, not a
claim about the pinned revision.

## Sentinel-1 evidence

The production hashes and sizes were independently verified:

| Role | Size | SHA-256 |
|---|---:|---|
| BEFORE | 661,872 bytes | `28e6dd9fef265db3ec4d203e5f7b80d2de06993455a4844f91625559275740fa` |
| AFTER | 662,458 bytes | `c4df94426a9be90e5dcf20b7d14d09165880fd36ae85c0ef34dc9bf1c2663a2b` |

The existing acquisition contract requests VV/VH FLOAT32 values with
`GAMMA0_ELLIPSOID`, orthorectification enabled, speckle filtering disabled,
and radiometric terrain correction disabled. CDSE documentation establishes
that Sentinel-1 polarization values in this mode are linear power in the
selected backscatter coefficient—not DN and not dB. Orthorectification does
not make the data radiometrically terrain corrected; that requires the
terrain gamma-zero processing path, which was not requested.

The TIFFs remain EPSG:32645, 415×248, 20 m, VV then VH, with undeclared
nodata. No `dataMask` was requested, so a Kuro-style `valid_mask == 1`
cannot be reconstructed from documented evidence. Zero was not invented as
nodata.

## Compatibility conclusion

The representations differ in documented processing choices: the available
Kuro graph uses Sigma0 calibration, Lee Sigma filtering, and terrain
correction, whereas RescueX uses Gamma0 ellipsoid, no speckle filtering, and
no radiometric terrain correction. Even if future source inspection shows
that the Kuro arrays are linear backscatter, the coefficient, filtering,
terrain treatment, resolution/resampling, and validity semantics must still
be aligned before applying the checkpoint.

Statistical similarity is supporting evidence only and cannot establish
physical equivalence. No arbitrary multiplier, logarithm, clipping, or
standardization was applied to Sentinel data.

## Execution classification

- **REAL_EXECUTED:** local deterministic sample audit, normalization
  recomputation, production-raster hash/metadata verification, checkpoint
  hash verification, manifest generation.
- **BLOCKED:** definitive pinned `grd_preprocessing.xml` verification because
  revision `e8e61b7b1254b04bfa2b5e26d43db90cb86b5004` was not resolvable.
- **NOT_EXECUTED:** CDSE acquisition, inference, training, fine-tuning, flood
  mask, flood-area estimate, OSM, EMSR927, and connectivity.

Commands executed:

```powershell
python scripts/phase11b_compatibility_audit.py
```

No production TIFF, checkpoint, or reconciled Phase 10D manifest was
modified. No credentials or tokens were written to the manifest. The audit
performed no network acquisition.
