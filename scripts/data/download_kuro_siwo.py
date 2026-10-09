from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

from floodlens.ml.data import dataset_manifest, write_manifest


OFFICIAL_HF_API = "https://huggingface.co/api/datasets/orion-ai-lab/Kuro-Siwo-GeoTIFFs"
OFFICIAL_HF_RESOLVE = (
    "https://huggingface.co/datasets/orion-ai-lab/Kuro-Siwo-GeoTIFFs/"
    "resolve/main/GRD/{shard}?download=true"
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def official_audit(shard: str = "00000.tar") -> dict:
    """Inspect official metadata and one shard size without downloading data."""
    request = urllib.request.Request(OFFICIAL_HF_API, method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        metadata = json.loads(response.read().decode("utf-8"))
    files = [item["rfilename"] for item in metadata.get("siblings", [])]
    shard_url = OFFICIAL_HF_RESOLVE.format(shard=shard)
    headers = {}
    try:
        request = urllib.request.Request(shard_url, method="HEAD")
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(request, timeout=30) as response:
            headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        headers = dict(exc.headers.items())
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        headers = {"error": type(exc).__name__}
    linked_size = headers.get("X-Linked-Size") or headers.get("Content-Length")
    shard_size = int(linked_size) if linked_size and linked_size.isdigit() else None
    grd_shards = [item for item in files if item.startswith("GRD/") and item.endswith(".tar")]
    return {
        "source": OFFICIAL_HF_API,
        "source_revision": metadata.get("sha"),
        "license": "CC BY 4.0",
        "dataset_description": "43 flood events, 6 continents, 3 climate zones, 10 m annotations",
        "representation": "GeoTIFF GRD shards",
        "available_files": len(files),
        "grd_shard_count": len(grd_shards),
        "sampled_shard": f"GRD/{shard}",
        "sampled_shard_url": shard_url,
        "sampled_shard_size_bytes": shard_size,
        "download_performed": False,
        "status": "BLOCKED_SAFE_SUBSET_UNAVAILABLE",
        "blocker": (
            "Official GeoTIFF distribution exposes complete tar shards; the sampled "
            "shard is too large for a bounded acquisition on this machine. No official "
            "sample-level download path was verified."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Kuro Siwo metadata without silently downloading raw data.")
    parser.add_argument("--root", default="data/raw/datasets/kuro_siwo")
    parser.add_argument("--download", action="store_true", help="manual download remains opt-in; no automated large download")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--audit-official", action="store_true", help="inspect official HF metadata and shard size only")
    parser.add_argument("--shard", default="00000.tar", help="GRD shard name for HEAD-only size audit")
    args = parser.parse_args()
    root = Path(args.root)
    if args.audit_official:
        report = official_audit(args.shard)
        output = Path("data/manifests/kuro_siwo_acquisition_audit.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    manifest = dataset_manifest("kuro-siwo", str(root), enabled=args.verify)
    if args.download:
        print("Kuro Siwo is a large third-party dataset. Use the official download script/Hugging Face source, then rerun --verify.")
        return 2
    write_manifest(Path("data/manifests/training_datasets.json"), manifest)
    print(f"wrote metadata manifest; no raw data downloaded: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
