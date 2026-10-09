from pathlib import Path

import numpy as np
import pytest

from floodlens.ml.data import (
    SampleRecord,
    assert_training_dataset_is_allowed,
    dataset_manifest,
    inspect_samples,
    load_kuro_siwo_grd_sample,
)
from floodlens.ml.metrics import segmentation_metrics
from floodlens.ml.patches import generate_patches
from floodlens.ml.split import geographic_split


def test_forbidden_training_sources_are_rejected():
    with pytest.raises(ValueError, match="forbidden"):
        assert_training_dataset_is_allowed("EMSR927")
    assert_training_dataset_is_allowed("development-fixture")


def test_manifest_and_inspection_are_explicit(tmp_path: Path):
    manifest = dataset_manifest("kuro-siwo", str(tmp_path), enabled=False)
    assert manifest.license.startswith("CC BY")
    report = inspect_samples([SampleRecord("a", "missing", "missing-mask", "scene-a", "region-a")])
    assert report["missing_images"] == ["a"]
    assert report["label_semantics"]["1"] == "flood/water target"


def test_kuro_siwo_loader_preserves_source_mask_and_adapts_target(tmp_path: Path):
    sample = tmp_path / "sample"
    sample.mkdir()
    shape = (1, 2, 2)
    for name in ("flood_vv.npy", "flood_vh.npy"):
        np.save(sample / name, np.ones(shape, dtype="float32"))
    np.save(sample / "mask.npy", np.array([[[0, 1], [2, 2]]], dtype="float32"))
    np.save(sample / "valid_mask.npy", np.ones(shape, dtype="float32"))
    (sample / "info.json").write_text("{}", encoding="utf-8")
    image, source_mask, target = load_kuro_siwo_grd_sample(sample)
    assert image.shape == (2, 2, 2)
    assert sorted(np.unique(source_mask).tolist()) == [0, 1, 2]
    assert sorted(np.unique(target).tolist()) == [0, 1]


def test_scene_region_split_has_no_group_overlap():
    samples = [
        SampleRecord(str(i), "", "", f"scene-{i // 2}", f"region-{i // 2}")
        for i in range(8)
    ]
    split = geographic_split(samples, seed=7)
    groups = [{s.region for s in part} for part in (split.train, split.validation, split.test)]
    assert not groups[0] & groups[1]
    assert not groups[0] & groups[2]
    assert not groups[1] & groups[2]


def test_patch_generation_keeps_image_mask_alignment():
    image = np.ones((2, 5, 5), dtype="float32")
    mask = np.zeros((5, 5), dtype="uint8")
    patches = generate_patches(image, mask, patch_size=4, stride=3)
    assert patches
    assert all(p.image.shape == (2, 4, 4) and p.mask.shape == (4, 4) for p in patches)


def test_metrics_known_case():
    result = segmentation_metrics(np.array([[0.9, 0.9], [0.1, 0.1]]), np.array([[1, 0], [1, 0]]))
    assert result == {"iou": 1 / 3, "dice": 0.5, "precision": 0.5, "recall": 0.5}


torch = pytest.importorskip("torch")


def test_unet_forward_and_tiny_checkpoint(tmp_path: Path):
    from floodlens.ml.inference import infer_array
    from floodlens.ml.model import FloodUNet
    from floodlens.ml.training import train_tiny

    model = FloodUNet(in_channels=2, base_channels=4)
    output = model(torch.zeros((1, 2, 16, 16)))
    assert output.shape == (1, 1, 16, 16)
    checkpoint = tmp_path / "model.pt"
    images = np.random.default_rng(1).random((2, 2, 16, 16), dtype=np.float32)
    masks = np.zeros((2, 16, 16), dtype=np.float32)
    masks[:, 4:12, 4:12] = 1
    manifest = train_tiny(images, masks, checkpoint, epochs=1)
    assert checkpoint.exists()
    assert manifest["dataset"] == "development-fixture"
    probabilities, binary = infer_array(images[0], checkpoint, patch_size=16, stride=16)
    assert probabilities.shape == binary.shape == (16, 16)
    assert np.all((probabilities >= 0) & (probabilities <= 1))
