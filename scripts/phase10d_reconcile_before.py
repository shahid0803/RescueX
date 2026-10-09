"""Restore previously successful BEFORE provenance without network access."""

from __future__ import annotations

import argparse
from pathlib import Path

from phase10d_acquire import (
    DEFAULT_AOI,
    DEFAULT_OUTPUT,
    MANIFEST,
    reconcile_before_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT / "before_vv_vh.tif",
    )
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    try:
        manifest = reconcile_before_artifact(
            args.manifest, args.aoi, args.output, args.expected_sha256
        )
    except Exception as exc:
        print(f"RECONCILIATION_FAILED: {type(exc).__name__}: {exc}")
        return 1
    print("RECONCILIATION_VALIDATED")
    print(f"manifest={args.manifest}")
    print(f"scene_id={manifest['scenes']['before']['scene_id']}")
    print(f"sha256={manifest['scenes']['before']['sha256']}")
    print(f"file_size={manifest['scenes']['before']['file_size']}")
    print("network_request=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
