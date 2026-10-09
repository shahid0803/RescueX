from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine

from .model import FloodUNet, _require_torch, torch
from .patches import generate_patches


def infer_array(
    image: np.ndarray, checkpoint_path: Path, threshold: float = 0.5, patch_size: int = 256, stride: int = 128
) -> tuple[np.ndarray, np.ndarray]:
    _require_torch()
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model = FloodUNet(checkpoint["input_channels"])
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    height, width = image.shape[1:]
    probabilities = np.zeros((height, width), dtype="float32")
    counts = np.zeros((height, width), dtype="float32")
    with torch.no_grad():
        for patch in generate_patches(image, patch_size=patch_size, stride=stride):
            output = torch.sigmoid(model(torch.from_numpy(patch.image[None]).float()))[0, 0].numpy()
            row_end, col_end = min(patch.row + patch_size, height), min(patch.col + patch_size, width)
            probabilities[patch.row:row_end, patch.col:col_end] += output[:row_end - patch.row, :col_end - patch.col]
            counts[patch.row:row_end, patch.col:col_end] += 1
    probabilities = np.divide(probabilities, counts, out=np.zeros_like(probabilities), where=counts > 0)
    return probabilities, (probabilities >= threshold).astype("uint8")


def infer_geotiff(input_path: Path, checkpoint_path: Path, output_probability: Path, output_mask: Path, threshold: float = 0.5):
    with rasterio.open(input_path) as source:
        image = source.read().astype("float32")
        probabilities, mask = infer_array(image, checkpoint_path, threshold)
        profile = source.profile.copy()
        profile.update(count=1, dtype="float32", nodata=0)
        with rasterio.open(output_probability, "w", **profile) as destination:
            destination.write(probabilities, 1)
        profile.update(dtype="uint8")
        with rasterio.open(output_mask, "w", **profile) as destination:
            destination.write(mask, 1)
    return {"threshold": threshold, "probability_path": str(output_probability), "mask_path": str(output_mask)}
