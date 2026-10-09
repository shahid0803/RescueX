from __future__ import annotations

import json
import random
import time
from pathlib import Path

import numpy as np

from .loss import bce_dice_loss
from .metrics import segmentation_metrics
from .model import FloodUNet, _require_torch, torch


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    _require_torch()
    torch.manual_seed(seed)


def train_tiny(
    images: np.ndarray,
    masks: np.ndarray,
    checkpoint_path: Path,
    *,
    epochs: int = 1,
    learning_rate: float = 1e-3,
    seed: int = 42,
    device: str = "cpu",
) -> dict:
    _require_torch()
    seed_everything(seed)
    model = FloodUNet(images.shape[1])
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    inputs = torch.from_numpy(images).float().to(device)
    targets = torch.from_numpy(masks[:, None]).float().to(device)
    logs = []
    started = time.perf_counter()
    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad()
        logits = model(inputs)
        loss = bce_dice_loss(logits, targets)
        loss.backward()
        optimizer.step()
        with torch.no_grad():
            probabilities = torch.sigmoid(model(inputs)).cpu().numpy()
        logs.append({"epoch": epoch, "train_loss": float(loss.item()), **segmentation_metrics(probabilities, masks)})
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model_state": model.state_dict(), "input_channels": images.shape[1], "seed": seed}, checkpoint_path)
    manifest = {
        "experiment_id": checkpoint_path.stem,
        "dataset": "development-fixture",
        "model": "FloodUNet",
        "epochs": epochs,
        "learning_rate": learning_rate,
        "seed": seed,
        "device": device,
        "logs": logs,
        "duration_seconds": time.perf_counter() - started,
    }
    checkpoint_path.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
