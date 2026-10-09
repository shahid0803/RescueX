# AI dataset policy

## Primary dataset

RescueX selects **Kuro Siwo** as the intended baseline dataset after
inspecting the official repository on 2026-10-03:
<https://github.com/Orion-AI-Lab/KuroSiwo>.

The repository documents v2 updates, GRD and SLC products, GeoTIFFs and
WebDatasets, annotation polygons, and a download script. The dataset README
states CC BY; the repository `LICENSE` is MIT for code. RescueX does not
redistribute the raw dataset. The cited work is Bountos et al., NeurIPS 2024,
“Kuro Siwo: 33 billion m² under the water.”

No Kuro Siwo data was downloaded or used for metrics in this phase. The
manifest and loader are ready for a user-provided local path.

## Optional dataset

Sen1Floods11 is an optional adapter only:
<https://github.com/cloudtostreet/Sen1Floods11>. Its README describes v1.1,
Sentinel-1/Sentinel-2 GeoTIFF layers, labels (`-1` no data, `0` non-water,
`1` water), and approximately 14 GB for the full bucket. It is disabled and
not downloaded. Citation: Bonafilia et al., CVPR Workshops 2020.

## Forbidden sources

EMSR927, UNOSAT, published damage maps, and post-event map edits are not
training data and are rejected by `assert_training_dataset_is_allowed`.
