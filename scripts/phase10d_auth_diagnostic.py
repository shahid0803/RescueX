"""Run a token-only CDSE diagnostic without printing credentials or the token."""

from __future__ import annotations

import json

from floodlens.satellite.auth import CopernicusAuthenticator


def main() -> int:
    report = CopernicusAuthenticator.from_env().diagnose_token_request()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "TOKEN_RECEIVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
