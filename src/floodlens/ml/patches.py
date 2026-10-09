from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Patch:
    image: np.ndarray
    mask: np.ndarray | None
    row: int
    col: int
    valid_fraction: float


def generate_patches(
    image: np.ndarray,
    mask: np.ndarray | None = None,
    patch_size: int = 256,
    stride: int = 128,
    minimum_valid_fraction: float = 0.0,
) -> list[Patch]:
    if image.ndim != 3:
        raise ValueError("image must have shape (channels, height, width)")
    channels, height, width = image.shape
    if mask is not None and mask.shape != (height, width):
        raise ValueError("image and mask dimensions do not match")
    patches = []
    rows = list(range(0, max(1, height - patch_size + 1), stride))
    cols = list(range(0, max(1, width - patch_size + 1), stride))
    if height > patch_size and rows[-1] != height - patch_size:
        rows.append(height - patch_size)
    if width > patch_size and cols[-1] != width - patch_size:
        cols.append(width - patch_size)
    for row in rows:
        for col in cols:
            row_end, col_end = min(row + patch_size, height), min(col + patch_size, width)
            sample = image[:, row:row_end, col:col_end]
            valid = np.isfinite(sample).all(axis=0)
            if valid.mean() < minimum_valid_fraction:
                continue
            padded = np.zeros((channels, patch_size, patch_size), dtype=image.dtype)
            padded[:, :sample.shape[1], :sample.shape[2]] = np.nan_to_num(sample)
            target = None
            if mask is not None:
                target = np.zeros((patch_size, patch_size), dtype=mask.dtype)
                target[:sample.shape[1], :sample.shape[2]] = mask[row:row_end, col:col_end]
            patches.append(Patch(padded, target, row, col, float(valid.mean())))
    return patches
