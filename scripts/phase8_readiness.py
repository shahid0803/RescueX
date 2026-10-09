"""Report independent Phase 8 readiness domains without exposing secrets."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOKEN_ENDPOINT = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"
    "protocol/openid-connect/token"
)
STAC_ENDPOINT = "https://stac.dataspace.copernicus.eu/v1/search"
OHSOME_ENDPOINT = "https://api.ohsome.org/v1"
KURO_SIWO_REPOSITORY = "https://github.com/Orion-AI-Lab/KuroSiwo"
VALID_STATUSES = {"READY", "BLOCKED", "NOT_CHECKED", "PARTIAL", "FAILED"}


def package_version(name: str) -> str | None:
    try:
        result = subprocess.run(
            ["python", "-c", f"import {name}; print({name}.__version__)"],
            capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def endpoint_reachable(url: str) -> tuple[bool, str]:
    """Perform a bounded, unauthenticated reachability probe only."""
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=10) as response:
            return True, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        # A 401/403 still proves the service is reachable; it is not auth success.
        if exc.code in {401, 403, 405}:
            return True, f"HTTP {exc.code} (reachable; authentication or method required)"
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, type(exc).__name__


def artifact_state(root: Path) -> dict[str, Any]:
    raw_root = root / "data" / "raw"
    kuro_root = raw_root / "datasets" / "kuro_siwo"
    kuro_files = [
        str(path.relative_to(root)) for path in kuro_root.rglob("*") if path.is_file()
    ] if kuro_root.exists() else []
    checkpoints = [
        str(path.relative_to(root)) for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".pt", ".pth", ".ckpt"}
    ]
    return {
        "kuro_files": kuro_files,
        "checkpoints": checkpoints,
        "real_checkpoint_available": False,
        "real_mask_available": False,
    }


def domain(
    status: str,
    dependencies: list[str],
    evidence: list[str],
    blockers: list[str] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid readiness status: {status}")
    return {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "dependencies": dependencies,
        "evidence": evidence,
        "blockers": blockers or [],
        "notes": notes or [],
    }


def build_report(root: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    artifacts = artifact_state(root)
    client_ready = bool(os.getenv("RESCUEX_CDSE_CLIENT_ID"))
    secret_ready = bool(os.getenv("RESCUEX_CDSE_CLIENT_SECRET"))
    stac_ok, stac_evidence = endpoint_reachable(STAC_ENDPOINT)
    ohsome_ok, ohsome_evidence = endpoint_reachable(OHSOME_ENDPOINT)
    kuro_available = bool(artifacts["kuro_files"])
    torch_available = package_version("torch") is not None
    cdse_status = "PARTIAL" if stac_ok and not (client_ready and secret_ready) else (
        "READY" if stac_ok and client_ready and secret_ready else "BLOCKED"
    )
    kuro_status = "READY" if kuro_available else "BLOCKED"
    ml_status = "READY" if kuro_available and torch_available else "BLOCKED"
    sentinel_status = "READY" if cdse_status == "READY" and artifacts["real_checkpoint_available"] else "BLOCKED"
    ohsome_status = "PARTIAL" if ohsome_ok else "BLOCKED"
    report = {
        "generated_at": now,
        "phase": "8A",
        "cdse": domain(
            cdse_status,
            ["local CDSE client ID", "local CDSE client secret", "CDSE STAC"],
            [f"STAC endpoint: {stac_evidence}", f"token endpoint: {TOKEN_ENDPOINT}", "credential values were not read or printed"],
            [] if cdse_status == "READY" else (
                ["CDSE credentials are not configured; token smoke test not run."]
                if not (client_ready and secret_ready) else ["CDSE STAC or authentication readiness is incomplete."]
            ),
            ["CDSE readiness gates Sentinel acquisition only."],
        ),
        "kuro_siwo": domain(
            kuro_status,
            ["official Kuro Siwo source", "local storage", "download/inspection tooling"],
            [f"official repository: {KURO_SIWO_REPOSITORY}", f"local file count: {len(artifacts['kuro_files'])}", "dataset license/citation recorded in data/manifests/training_datasets.yaml"],
            [] if kuro_available else ["No verified Kuro Siwo files are present locally; download and inspection remain pending."],
            ["Kuro Siwo retrieval does not require CDSE credentials."],
        ),
        "ohsome": domain(
            ohsome_status,
            ["ohsome historical API", "configured AOI", "pre-event snapshot date"],
            [f"endpoint: {OHSOME_ENDPOINT}", f"reachability: {ohsome_evidence}"],
            [] if ohsome_ok else ["ohsome endpoint reachability was not verified."],
            ["No historical AOI extraction was executed; current OSM is not substituted."],
        ),
        "ml_training": domain(
            ml_status,
            ["Kuro Siwo data", "PyTorch", "storage/memory", "training configuration"],
            [f"PyTorch: {package_version('torch') or 'unavailable'}", f"Kuro Siwo local files: {len(artifacts['kuro_files'])}"],
            [] if ml_status == "READY" else ["Real training cannot start until verified Kuro Siwo data is locally available."],
            ["This domain is independent of CDSE credentials."],
        ),
        "sentinel_inference": domain(
            sentinel_status,
            ["CDSE readiness", "real Sentinel product", "Phase 2 preprocessing", "verified trained checkpoint"],
            [f"CDSE status: {cdse_status}", f"checkpoint files: {len(artifacts['checkpoints'])}", "real mask available: false"],
            ["Requires CDSE access and a verified real checkpoint; no real inference is claimed."],
        ),
        "trishuli": domain(
            "BLOCKED",
            ["CDSE", "Kuro Siwo/model", "Sentinel product", "ohsome", "impact", "connectivity"],
            [f"CDSE: {cdse_status}", f"Kuro Siwo: {kuro_status}", f"ML training: {ml_status}", f"ohsome: {ohsome_status}", f"Sentinel inference: {sentinel_status}"],
            ["No configured Trishuli AOI, real product, checkpoint, or flood mask is available."],
        ),
        "emsr927_validation": domain(
            "NOT_CHECKED",
            ["independent RescueX result", "official EMSR927 reference"],
            ["EMSR927 remains validation-only and was not retrieved."],
            [],
            ["Not a prerequisite for training, acquisition, inference, impact, or connectivity."],
        ),
        "environment": {
            "python": platform.python_version(),
            "torch": package_version("torch"),
            "rasterio": package_version("rasterio"),
            "free_disk_bytes": shutil.disk_usage(root).free,
        },
        "local_artifacts": artifacts,
    }
    statuses = [report[name]["status"] for name in (
        "cdse", "kuro_siwo", "ohsome", "ml_training", "sentinel_inference", "trishuli", "emsr927_validation"
    )]
    report["overall_status"] = "READY" if all(status == "READY" for status in statuses) else (
        "PARTIAL_READINESS" if any(status in {"READY", "PARTIAL"} for status in statuses) else "BLOCKED"
    )
    report["dependency_notes"] = {
        "cdse_missing_does_not_block": ["kuro_siwo", "ml_training", "ohsome"],
        "sentinel_inference_requires": ["cdse", "ml_training"],
        "trishuli_requires": ["sentinel_inference", "ohsome"],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Report independent RescueX Phase 8A readiness")
    parser.add_argument(
        "--domain",
        choices=("all", "cdse", "kuro-siwo", "ohsome", "ml-training", "sentinel-inference", "trishuli", "emsr927"),
        default="all",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = build_report(root)
    output = root / "data" / "manifests" / "phase8_readiness.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    selected = {
        "kuro-siwo": "kuro_siwo", "ml-training": "ml_training",
        "sentinel-inference": "sentinel_inference", "emsr927": "emsr927_validation",
    }.get(args.domain, args.domain)
    print(json.dumps(report if args.domain == "all" else {selected: report[selected]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
