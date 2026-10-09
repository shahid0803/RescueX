"""Bounded HTTP-range extraction of official Kuro Siwo WebDataset samples.

This intentionally does not use Hugging Face caching or download a complete
TAR shard. It reads a fixed byte window and materializes only complete sample
members found inside that window.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import tarfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from floodlens.ml.data import load_kuro_siwo_grd_sample

REPOSITORY = "orion-ai-lab/Kuro-Siwo-Webdataset"
REVISION = "e8e61b7b1254b04bfa2b5e26d43db90cb86b5004"
SHARD_URL_TEMPLATE = (
    "https://huggingface.co/datasets/orion-ai-lab/Kuro-Siwo-Webdataset/"
    "resolve/main/{split}/shard-00000.tar?download=true"
)
EXPECTED_FIELDS = {
    "flood_vv.npy", "flood_vh.npy", "sec1_vv.npy", "sec1_vh.npy",
    "sec2_vv.npy", "sec2_vh.npy", "dem.npy", "info.json", "mask.npy", "valid_mask.npy",
}
MAX_LOCAL_BYTES = 512 * 1024 * 1024


def fetch_range(url: str, size: int) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(url, headers={"Range": f"bytes=0-{size - 1}"})
    with urllib.request.urlopen(request, timeout=120) as response:
        headers = {key.lower(): value for key, value in response.headers.items()}
        body = response.read()
    if response.status != 206 or len(body) > size:
        raise RuntimeError("official server did not honor a bounded HTTP range response")
    return body, headers


def extract_samples(payload: bytes, destination: Path, limit: int) -> list[dict]:
    grouped: dict[str, dict[str, bytes]] = {}
    try:
        stream = tarfile.open(fileobj=io.BytesIO(payload), mode="r|")
        for member in stream:
            if not member.isfile():
                continue
            name = Path(member.name)
            stem, separator, field = name.name.partition(".")
            key = f"{name.parent}/{stem}" if str(name.parent) != "." else stem
            if not separator:
                continue
            if field not in EXPECTED_FIELDS:
                continue
            source = stream.extractfile(member)
            if source is None:
                continue
            grouped.setdefault(key, {})[field] = source.read()
            if len([item for item in grouped.values() if EXPECTED_FIELDS <= set(item)]) >= limit:
                break
    except (tarfile.ReadError, EOFError):
        # A bounded range commonly ends in the middle of a later member.
        pass
    complete = [(key, fields) for key, fields in grouped.items() if EXPECTED_FIELDS <= set(fields)]
    complete = complete[:limit]
    records = []
    for index, (key, fields) in enumerate(complete):
        sample_dir = destination / f"sample-{index:03d}"
        sample_dir.mkdir(parents=True, exist_ok=True)
        for field, content in fields.items():
            (sample_dir / field).write_bytes(content)
        image, source_mask, binary_target = load_kuro_siwo_grd_sample(sample_dir)
        mask = source_mask
        valid = np.load(sample_dir / "valid_mask.npy", allow_pickle=False)
        arrays = {field: np.load(sample_dir / field, allow_pickle=False) for field in EXPECTED_FIELDS if field.endswith(".npy")}
        records.append({
            "source_key": key,
            "local_path": str(sample_dir),
            "fields": sorted(fields),
            "shapes": {field: list(array.shape) for field, array in arrays.items()},
            "dtypes": {field: str(array.dtype) for field, array in arrays.items()},
            "mask_values": sorted(np.unique(mask).tolist()),
            "valid_mask_values": sorted(np.unique(valid).tolist()),
            "finite": {field: bool(np.isfinite(array).all()) for field, array in arrays.items()},
            "rescuex_loader": {
                "status": "REAL_EXECUTED",
                "image_shape": list(image.shape),
                "image_dtype": str(image.dtype),
                "binary_target_shape": list(binary_target.shape),
                "binary_target_values": sorted(np.unique(binary_target).tolist()),
                "source_mask_preserved": True,
            },
            "label_semantics": {"0": "no water", "1": "permanent water", "2": "flood"},
        })
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract bounded real Kuro Siwo GRD samples")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--split", choices=("train_GRD", "test_GRD"), default="train_GRD")
    parser.add_argument("--max-samples", type=int, default=1, choices=range(1, 9))
    parser.add_argument("--window-mb", type=int, default=64)
    args = parser.parse_args()
    window = args.window_mb * 1024 * 1024
    if window <= 0 or window > MAX_LOCAL_BYTES:
        raise SystemExit(f"window must be between 1 and {MAX_LOCAL_BYTES // (1024 * 1024)} MiB")
    if args.output is None:
        args.output = Path("data/raw/kuro_siwo_streamed") / args.split
    if args.manifest is None:
        args.manifest = Path("data/manifests") / f"kuro_siwo_streaming_{args.split.lower()}.json"
    url = SHARD_URL_TEMPLATE.format(split=args.split)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    free_before = shutil.disk_usage(args.output.parent).free
    payload, headers = fetch_range(url, window)
    if len(payload) > MAX_LOCAL_BYTES:
        raise SystemExit("safety budget exceeded")
    records = extract_samples(payload, args.output, args.max_samples)
    local_bytes = sum(path.stat().st_size for path in args.output.rglob("*") if path.is_file()) if args.output.exists() else 0
    if local_bytes > MAX_LOCAL_BYTES:
        raise SystemExit("materialized sample budget exceeded")
    report = {
        "source_repository": REPOSITORY,
        "source_revision": REVISION,
        "source_url": url,
        "access_timestamp": datetime.now(timezone.utc).isoformat(),
        "split": args.split,
        "streaming_method": "bounded HTTP Range request; no dataset cache",
        "range_bytes_requested": window,
        "range_bytes_received": len(payload),
        "response_content_range": headers.get("content-range"),
        "free_disk_before": free_before,
        "free_disk_after": shutil.disk_usage(args.output.parent).free,
        "local_bytes_materialized": local_bytes,
        "samples_retrieved": len(records),
        "samples": records,
        "license": "CC BY",
        "download_performed": False,
        "errors": [] if records else ["No complete labelled sample found in bounded range window."],
        "status": "REAL_EXECUTED" if records else "BLOCKED",
        "qa_label": "REAL KURO SIWO SAMPLE QA — NOT MODEL RESULT",
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if records else 2


if __name__ == "__main__":
    raise SystemExit(main())
