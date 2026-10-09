# Phase 9C — Real Kuro Siwo Training & Evaluation

## Objective

**REAL_EXECUTED.** Run one bounded, reproducible flood-segmentation
experiment on official Kuro Siwo labelled GRD samples. This phase does not
claim Sentinel, Trishuli, infrastructure, connectivity, or EMSR927 results.

## Environment

**REAL_EXECUTED.** Python 3.14.6, PyTorch 2.14.0+cpu, CPU device, and
approximately 7.7 GB RAM were used. Free disk was 104,778,186,752 bytes
before the final experiment and 104,777,723,904 bytes afterward. No CDSE
credentials or Sentinel data were accessed.

## Input Contract

**REAL_EXECUTED.** The existing Phase 3 `FloodUNet` was retained with its
smallest documented compatible contract: two channels,
`flood_vv` and `flood_vh`, at 224×224. DEM and the four earlier temporal
channels were not silently added. Training-only per-channel mean/std
normalization was computed from the selected training samples.

## Dataset Source

**REAL_EXECUTED.** Official source:
`orion-ai-lab/Kuro-Siwo-Webdataset`, revision
`e8e61b7b1254b04bfa2b5e26d43db90cb86b5004`. Samples were obtained from
`train_GRD/shard-00000.tar` and `test_GRD/shard-00000.tar` using bounded
512 MiB HTTP Range requests. No complete shard and no dataset cache were
downloaded. Total selected local sample bytes were 28,967,072.

## Samples Used

**REAL_EXECUTED.** Seven training samples were used: `000000` through
`000006` from the official training split. Five evaluation samples were used:
`000000`, `000002`, `000004`, `000005`, and `000007` from the official test
split. Samples containing source mask value `3`, which is outside the
documented `0/1/2` semantics, were conservatively excluded rather than
relabelled. The source metadata provided distinct grid IDs; training and
evaluation used the official train/test separation. A formal geographic
leakage proof was **NOT_ESTABLISHED** beyond that official split.

## Split Strategy

**REAL_EXECUTED.** Official `train_GRD` was used for training and official
`test_GRD` for held-out evaluation. No random pixel or patch split was used.
The experiment records `actid`, `aoiid`, and `grid_id` metadata for every
selected sample. Group overlap was not independently established from all
dataset metadata and is recorded as a limitation, not claimed as proven.

## Label Conversion

**REAL_EXECUTED.** Source class `2` became binary target `1`; source classes
`0` and `1` became target `0`; source masks remained separate. Pixels were
included only where `valid_mask == 1`. Source value `3` was treated as an
undocumented sample-level exclusion, never as flood.

## Model Configuration

**REAL_EXECUTED.** Existing lightweight `FloodUNet`, two input channels,
one output channel, and `base_channels=4` were used. No pretrained weights,
new architecture, or DEM input was introduced.

## Training Configuration

**REAL_EXECUTED.** BCE+Dice with equal weights, Adam, learning rate `0.001`,
batch size `2`, `3` epochs, seed `42`, threshold `0.5`, CPU device, and a
512 MiB materialized-data safety ceiling were explicit CLI values. Exact
normalization values and configuration are in the experiment manifest.

## Training Execution

**REAL_EXECUTED.** Exact command:

```text
python scripts/data/stream_kuro_siwo.py --split train_GRD --max-samples 8 --window-mb 512
python scripts/data/stream_kuro_siwo.py --split test_GRD --max-samples 8 --window-mb 512
python scripts/data/train_kuro_siwo.py --train-samples 8 --eval-samples 8 --epochs 3 --batch-size 2 --base-channels 4 --learning-rate 0.001 --seed 42 --device cpu
```

Seven samples were selected after the documented-label filter. Three epochs
completed. Training losses were `0.7339819073677063`,
`0.6841267794370651`, and `0.7077005505561829`.

## Evaluation Execution

**REAL_EXECUTED.** Held-out evaluation ran on five real test-split samples.
The measured masked evaluation loss was `0.7259478569030762`.

## Real Metrics

**REAL_EXECUTED.** Metrics are pixel-level aggregate over 250,880 valid
pixels at threshold `0.5`: IoU `0.2042889030612245`, Dice/F1
`0.339268928812572`, precision `0.2042889030612245`, and recall `1.0`.
There were 51,252 flood-positive pixels, 51,252 true positives, 199,628
false positives, and zero false negatives. No metrics beyond these were
computed.

## Baseline

**REAL_EXECUTED.** An all-background baseline on the same five evaluation
samples produced IoU `0.0`, Dice/F1 `0.0`, precision `0.0`, and recall `0.0`.
This reports measurements only and is not a broad project verdict.

## Checkpoint

**REAL_EXECUTED.** A real checkpoint was created at the ignored path
`data/models/kuro_siwo/flood_unet.pt`. It is 34,677 bytes with SHA-256
`dc1da66fb3a837bf93f406330ace78245e385248c5b7b9443de47810481fa52d`.
The traceable checkpoint manifest is
`data/manifests/kuro_siwo_checkpoint_manifest.json`.

## QA Artifact

**REAL_EXECUTED.** `data/qa/kuro_siwo_training_qa.npz` contains one real
evaluation input, its source mask, binary target, and model probability
prediction. It is labelled **REAL KURO SIWO TRAINING QA — NOT SENTINEL
CASE-STUDY RESULT**.

## Provenance

**REAL_EXECUTED.** The experiment manifest is
`data/manifests/kuro_siwo_training_experiment.json`. Streaming manifests,
sample IDs, source revision, split, disk checks, normalization, checkpoint
hash, training logs, and evaluation metrics are recorded there or in the
checkpoint manifest. Raw data, manifests, checkpoint, and QA artifact are
ignored by Git.

## Tests

**REAL_EXECUTED.** The real streaming commands, real training/evaluation
command, checkpoint creation, manifest generation, and QA generation
completed. The existing regression suite passed with 36 tests before this
experiment. Python compilation and `git diff --check` are required final
checks; no secret or large-archive files were added.

**FAILED then corrected.** The first training run completed computation but
failed while serializing a `Path` in the experiment manifest. The runner was
corrected to serialize paths explicitly and was rerun from the same
configuration; the final run above completed successfully.

## Limitations

**IMPLEMENTED_ONLY / NOT_EXECUTED.** This is a tiny CPU experiment using
seven training and five evaluation samples, not a full-dataset model. The
official split was used, but complete geographic leakage analysis was not
possible from the bounded subset. Source mask value `3` occurred in other
retrieved samples and those samples were excluded conservatively. Metrics
are not representative of full Kuro Siwo performance.

## What Was NOT Executed

**NOT_EXECUTED.** No complete Kuro Siwo shard acquisition, CDSE access,
Sentinel-1/Sentinel-2 acquisition or inference, Trishuli case study, OSM or
ohsome extraction, infrastructure impact, road connectivity, cut-off
settlement analysis, EMSR927 comparison, or dashboard result generation was
performed.

## Git Status

**REAL_EXECUTED.** Raw samples and generated manifests/checkpoint/QA are
ignored and were not tracked. No credentials, tokens, large archives, or
checkpoint files were staged. No GitHub push was performed.

The next phase is **not automatic**: any future phase must separately define
whether to improve Kuro Siwo training or to build a real Sentinel acquisition
and inference run; this checkpoint must not be presented as a Sentinel or
Trishuli result.
