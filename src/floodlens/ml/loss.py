from __future__ import annotations

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None


def bce_dice_loss(logits, target, dice_weight: float = 0.5):
    if torch is None:
        raise RuntimeError("PyTorch is required for training")
    target = target.float()
    bce = torch.nn.functional.binary_cross_entropy_with_logits(logits, target)
    probabilities = torch.sigmoid(logits)
    intersection = (probabilities * target).sum()
    dice = 1 - (2 * intersection + 1) / (probabilities.sum() + target.sum() + 1)
    return (1 - dice_weight) * bce + dice_weight * dice
