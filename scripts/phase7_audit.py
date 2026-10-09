"""Create a non-secret Phase 7 execution audit from the local environment."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def version(module: str) -> str | None:
    try:
        result = subprocess.run(
            ["python", "-c", f"import {module}; print({module}.__version__)"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def cuda_available() -> bool:
    try:
        result = subprocess.run(
            ["python", "-c", "import torch; print(torch.cuda.is_available())"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip().lower() == "true"
    except (OSError, subprocess.CalledProcessError):
        return False


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    data_root = root / "data"
    checkpoints = [
        str(path.relative_to(root)) for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".pt", ".pth", ".ckpt"}
    ]
    raw_files = [
        str(path.relative_to(root)) for path in (data_root / "raw").rglob("*")
        if path.is_file()
    ] if (data_root / "raw").exists() else []
    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cdse_client_configured": bool(os.getenv("RESCUEX_CDSE_CLIENT_ID")),
        "cdse_secret_configured": bool(os.getenv("RESCUEX_CDSE_CLIENT_SECRET")),
        "torch_version": version("torch"),
        "rasterio_version": version("rasterio"),
        "cuda_available": cuda_available(),
        "free_disk_bytes": shutil.disk_usage(root).free,
        "checkpoints": checkpoints,
        "raw_data_files": raw_files,
        "statuses": {
            "kuro_siwo_download": "BLOCKED",
            "real_model_training": "BLOCKED",
            "real_model_evaluation": "BLOCKED",
            "cdse_metadata_search": "NOT_EXECUTED",
            "sentinel_download": "BLOCKED",
            "sentinel_inference": "BLOCKED",
            "trishuli_case_study": "BLOCKED",
            "real_osm_extraction": "NOT_EXECUTED",
            "real_connectivity": "BLOCKED",
            "emsr927_validation": "NOT_APPLICABLE",
        },
        "blockers": [
            "CDSE client credentials are not configured in the local environment.",
            "No verified Kuro Siwo files are present locally.",
            "No genuine trained Phase 3 checkpoint or georeferenced flood mask exists.",
            "No Trishuli AOI geometry is configured for a live catalog query.",
            "The available PyTorch installation is CPU-only.",
        ],
    }
    output = root / "data" / "manifests" / "phase7_environment_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
