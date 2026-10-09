from __future__ import annotations

import numpy as np


def _counts(prediction, target, threshold=0.5):
    pred = np.asarray(prediction) >= threshold
    truth = np.asarray(target).astype(bool)
    return (
        int(np.logical_and(pred, truth).sum()),
        int(np.logical_and(pred, ~truth).sum()),
        int(np.logical_and(~pred, truth).sum()),
    )


def segmentation_metrics(prediction, target, threshold=0.5) -> dict[str, float]:
    true_positive, false_positive, false_negative = _counts(prediction, target, threshold)
    union = true_positive + false_positive + false_negative
    return {
        "iou": true_positive / union if union else 1.0,
        "dice": 2 * true_positive / (2 * true_positive + false_positive + false_negative)
        if true_positive or false_positive or false_negative else 1.0,
        "precision": true_positive / (true_positive + false_positive)
        if true_positive + false_positive else 0.0,
        "recall": true_positive / (true_positive + false_negative)
        if true_positive + false_negative else 0.0,
    }
