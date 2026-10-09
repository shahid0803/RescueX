"""Run the bounded real Kuro Siwo training/evaluation experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from floodlens.ml.data import load_kuro_siwo_grd_sample
from floodlens.ml.loss import bce_dice_loss
from floodlens.ml.model import FloodUNet, _require_torch, torch

SOURCE_REVISION = "e8e61b7b1254b04bfa2b5e26d43db90cb86b5004"
SOURCE_REPOSITORY = "orion-ai-lab/Kuro-Siwo-Webdataset"
MAX_MATERIALIZED_BYTES = 512 * 1024 * 1024


def seed_everything(seed: int) -> None:
    import random

    random.seed(seed)
    np.random.seed(seed)
    _require_torch()
    torch.manual_seed(seed)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sample_paths(root: Path, limit: int) -> list[Path]:
    selected = []
    for path in sorted(root.glob("sample-*")):
        values = set(np.unique(np.load(path / "mask.npy", allow_pickle=False)).tolist())
        if values <= {0.0, 1.0, 2.0}:
            selected.append(path)
        if len(selected) == limit:
            break
    if not selected:
        raise RuntimeError(f"no samples with documented source labels found under {root}")
    return selected


def load_samples(paths: list[Path]) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    images, targets, valid_masks, records = [], [], [], []
    for path in paths:
        image, source_mask, target = load_kuro_siwo_grd_sample(path)
        valid_mask = np.load(path / "valid_mask.npy", allow_pickle=False).squeeze(0)
        image = image.astype("float32", copy=False)
        target = target.squeeze(0).astype("float32", copy=False)
        if not np.isfinite(image).all():
            raise ValueError(f"non-finite model input in {path}")
        if not np.isfinite(target).all() or not np.isfinite(valid_mask).all():
            raise ValueError(f"non-finite target or valid mask in {path}")
        info = json.loads((path / "info.json").read_text(encoding="utf-8"))
        records.append({
            "sample_id": path.name,
            "source_key": f"{int(path.name.removeprefix('sample-')):06d}",
            "group_id": f"actid={info.get('actid')};aoiid={info.get('aoiid')};grid_id={info.get('grid_id')}",
            "source_mask_values": sorted(np.unique(source_mask).tolist()),
            "valid_pixels": int((valid_mask == 1).sum()),
            "flood_positive_pixels": int(((target == 1) & (valid_mask == 1)).sum()),
        })
        images.append(image)
        targets.append(target)
        valid_masks.append(valid_mask)
    return np.stack(images), np.stack(targets), np.stack(valid_masks), records


def normalization(images: np.ndarray, valid_masks: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mask = valid_masks.astype(bool)
    means, stds = [], []
    for channel in range(images.shape[1]):
        values = images[:, channel][mask]
        means.append(float(values.mean()))
        stds.append(float(max(values.std(), 1e-6)))
    return np.asarray(means, dtype="float32"), np.asarray(stds, dtype="float32")


def masked_loss(logits, targets, valid_masks):
    mask = valid_masks[:, None].float()
    masked_logits = logits * mask
    masked_targets = targets[:, None] * mask
    bce = torch.nn.functional.binary_cross_entropy_with_logits(
        masked_logits, masked_targets, reduction="none"
    )
    bce = (bce * mask).sum() / mask.sum().clamp_min(1)
    probabilities = torch.sigmoid(logits)
    intersection = (probabilities * masked_targets).sum()
    dice = 1 - (2 * intersection + 1) / (
        (probabilities * mask).sum() + masked_targets.sum() + 1
    )
    return 0.5 * bce + 0.5 * dice


def aggregate_metrics(probabilities, targets, valid_masks, threshold: float) -> dict:
    valid = valid_masks.astype(bool)
    prediction = probabilities >= threshold
    truth = targets.astype(bool)
    tp = int((prediction & truth & valid).sum())
    fp = int((prediction & ~truth & valid).sum())
    fn = int((~prediction & truth & valid).sum())
    metrics = {}
    union = tp + fp + fn
    metrics.update({
        "iou": tp / union if union else 1.0,
        "dice": 2 * tp / (2 * tp + fp + fn) if tp or fp or fn else 1.0,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "valid_pixels": int(valid.sum()),
        "flood_positive_pixels": int((truth & valid).sum()),
        "true_positive_pixels": tp,
        "false_positive_pixels": fp,
        "false_negative_pixels": fn,
        "aggregation": "pixel-level aggregate",
        "threshold": threshold,
    })
    return metrics


def evaluate(model, images, targets, valid_masks, means, stds, device, threshold):
    normalized = (images - means[None, :, None, None]) / stds[None, :, None, None]
    inputs = torch.from_numpy(normalized).float().to(device)
    target_tensor = torch.from_numpy(targets).float().to(device)
    valid_tensor = torch.from_numpy(valid_masks).float().to(device)
    model.eval()
    with torch.no_grad():
        logits = model(inputs)
        loss = float(masked_loss(logits, target_tensor, valid_tensor).item())
        probabilities = torch.sigmoid(logits)[:, 0].cpu().numpy()
    return loss, probabilities, aggregate_metrics(probabilities, targets, valid_masks, threshold)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-root", type=Path, default=Path("data/raw/kuro_siwo_streamed/train_GRD"))
    parser.add_argument("--eval-root", type=Path, default=Path("data/raw/kuro_siwo_streamed/test_GRD"))
    parser.add_argument("--train-samples", type=int, default=8)
    parser.add_argument("--eval-samples", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--base-channels", type=int, default=4)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--device", default="cpu", choices=("cpu",))
    parser.add_argument("--checkpoint", type=Path, default=Path("data/models/kuro_siwo/flood_unet.pt"))
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1:
        raise SystemExit("epochs and batch-size must be positive")
    _require_torch()
    seed_everything(args.seed)
    torch.set_num_threads(min(2, os.cpu_count() or 1))
    started = time.perf_counter()
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    free_before = shutil.disk_usage(args.checkpoint.parent).free

    train_paths = sample_paths(args.train_root, args.train_samples)
    eval_paths = sample_paths(args.eval_root, args.eval_samples)
    train_images, train_targets, train_valid, train_records = load_samples(train_paths)
    eval_images, eval_targets, eval_valid, eval_records = load_samples(eval_paths)
    materialized = sum(
        p.stat().st_size
        for root in (args.train_root, args.eval_root)
        for p in root.rglob("*")
        if p.is_file()
    )
    if materialized > MAX_MATERIALIZED_BYTES:
        raise RuntimeError("materialized-data safety budget exceeded")
    means, stds = normalization(train_images, train_valid)
    normalized_train = (train_images - means[None, :, None, None]) / stds[None, :, None, None]
    model = FloodUNet(2, base_channels=args.base_channels).to(args.device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    inputs = torch.from_numpy(normalized_train).float().to(args.device)
    targets = torch.from_numpy(train_targets).float().to(args.device)
    valid_masks = torch.from_numpy(train_valid).float().to(args.device)
    logs = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        order = np.random.default_rng(args.seed + epoch).permutation(len(inputs))
        losses = []
        for start in range(0, len(order), args.batch_size):
            batch = order[start:start + args.batch_size]
            optimizer.zero_grad()
            loss = masked_loss(model(inputs[batch]), targets[batch], valid_masks[batch])
            loss.backward()
            optimizer.step()
            losses.append(float(loss.item()))
        logs.append({"epoch": epoch, "train_loss": float(np.mean(losses))})

    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_state": model.state_dict(),
        "input_channels": 2,
        "base_channels": args.base_channels,
        "seed": args.seed,
        "normalization_mean": means.tolist(),
        "normalization_std": stds.tolist(),
    }, args.checkpoint)
    eval_loss, probabilities, eval_metrics = evaluate(
        model, eval_images, eval_targets, eval_valid, means, stds, args.device, args.threshold
    )
    baseline = aggregate_metrics(
        np.zeros_like(eval_targets), eval_targets, eval_valid, args.threshold
    )
    qa_path = Path("data/qa/kuro_siwo_training_qa.npz")
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        qa_path,
        image=eval_images[0],
        source_mask=np.load(eval_paths[0] / "mask.npy", allow_pickle=False),
        binary_target=eval_targets[0],
        prediction=probabilities[0],
    )
    checkpoint_manifest = {
        "status": "REAL_EXECUTED",
        "file_path": str(args.checkpoint),
        "file_size_bytes": args.checkpoint.stat().st_size,
        "sha256": sha256(args.checkpoint),
        "model": {"architecture": "FloodUNet", "base_channels": args.base_channels, "input_channels": 2},
        "preprocessing": {"channels": ["flood_vv", "flood_vh"], "normalization_mean": means.tolist(), "normalization_std": stds.tolist()},
        "label_conversion": "source class 2 -> 1; source classes 0 and 1 -> 0; valid_mask==1 retained",
        "dataset": {"repository": SOURCE_REPOSITORY, "revision": SOURCE_REVISION},
        "training": {"sample_ids": [r["source_key"] for r in train_records], "seed": args.seed, "optimizer": "Adam", "learning_rate": args.learning_rate, "batch_size": args.batch_size, "epochs": args.epochs, "logs": logs},
        "evaluation": {"sample_ids": [r["source_key"] for r in eval_records], "loss": eval_loss, "metrics": eval_metrics},
    }
    manifest_path = Path("data/manifests/kuro_siwo_checkpoint_manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(checkpoint_manifest, indent=2) + "\n", encoding="utf-8")
    configuration = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in vars(args).items()
    }
    configuration["max_materialized_bytes"] = MAX_MATERIALIZED_BYTES
    experiment = {
        "status": "REAL_EXECUTED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": platform.python_version(), "torch": torch.__version__, "device": args.device, "free_disk_before": free_before, "free_disk_after": shutil.disk_usage(args.checkpoint.parent).free},
        "dataset_access": "REAL_EXECUTED via bounded HTTP Range; no complete shard downloaded",
        "dataset_materialized_locally": "REAL_EXECUTED",
        "materialized_bytes": materialized,
        "source": {"repository": SOURCE_REPOSITORY, "revision": SOURCE_REVISION, "official_split": "train_GRD for training; test_GRD for held-out evaluation"},
        "samples": {"training_count": len(train_records), "evaluation_count": len(eval_records), "training": train_records, "evaluation": eval_records, "excluded_samples": "Samples containing undocumented source mask value 3 were excluded conservatively.", "group_overlap_check": "NOT_ESTABLISHED from metadata; official train/test split used"},
        "configuration": configuration,
        "label_conversion": "source class 2 -> target 1; source classes 0 and 1 -> target 0; invalid pixels excluded where valid_mask != 1",
        "model": "FloodUNet",
        "training_execution": {"status": "REAL_EXECUTED", "epochs_completed": args.epochs, "logs": logs, "duration_seconds": time.perf_counter() - started},
        "evaluation_execution": {"status": "REAL_EXECUTED", "loss": eval_loss, "metrics": eval_metrics},
        "baseline": {"status": "REAL_EXECUTED", "type": "all-background", "metrics": baseline},
        "checkpoint": {"status": "REAL_EXECUTED", "manifest": str(manifest_path)},
        "qa_artifact": {"status": "REAL_EXECUTED", "path": str(qa_path), "label": "REAL KURO SIWO TRAINING QA — NOT SENTINEL CASE-STUDY RESULT"},
    }
    experiment_path = Path("data/manifests/kuro_siwo_training_experiment.json")
    experiment_path.parent.mkdir(parents=True, exist_ok=True)
    experiment_path.write_text(json.dumps(experiment, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(experiment, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
