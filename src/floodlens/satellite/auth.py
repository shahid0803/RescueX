from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .errors import AuthenticationError, NoCredentialsError


TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"


@dataclass
class CopernicusAuthenticator:
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str = TOKEN_URL
    _token: str | None = None
    _expires_at: float = 0

    @classmethod
    def from_env(cls) -> "CopernicusAuthenticator":
        return cls(os.getenv("RESCUEX_CDSE_CLIENT_ID"), os.getenv("RESCUEX_CDSE_CLIENT_SECRET"))

    def get_token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        if not self.client_id or not self.client_secret:
            raise NoCredentialsError(
                "Set RESCUEX_CDSE_CLIENT_ID and RESCUEX_CDSE_CLIENT_SECRET to download from CDSE"
            )
        body = urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode()
        request = Request(self.token_url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            import json

            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
            self._token = payload["access_token"]
            self._expires_at = time.time() + int(payload.get("expires_in", 300))
            return self._token
        except Exception as exc:
            raise AuthenticationError("Copernicus authentication failed") from exc

    def diagnose_token_request(self) -> dict[str, Any]:
        """Make a token-only diagnostic request without returning or recording the token."""
        import json

        if not self.client_id or not self.client_secret:
            return {
                "status": "BLOCKED",
                "reason": "credentials_missing",
                "client_id_present": bool(self.client_id),
                "client_secret_present": bool(self.client_secret),
            }
        body = urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }).encode()
        request = Request(
            self.token_url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
                payload = json.loads(raw)
                return {
                    "status": "TOKEN_RECEIVED" if "access_token" in payload else "TOKEN_MISSING",
                    "http_status": getattr(response, "status", None),
                    "content_type": response.headers.get("Content-Type"),
                    "access_token_key_present": "access_token" in payload,
                    "token_type": payload.get("token_type"),
                    "expires_in": payload.get("expires_in"),
                    "response_keys": sorted(str(key) for key in payload if key != "access_token"),
                }
        except Exception as exc:
            status = getattr(exc, "code", None)
            content_type = None
            safe_fields: dict[str, Any] = {}
            if hasattr(exc, "headers") and exc.headers:
                content_type = exc.headers.get("Content-Type")
            if hasattr(exc, "read"):
                try:
                    parsed = json.loads(exc.read())
                    if isinstance(parsed, dict):
                        safe_fields = {
                            key: parsed[key]
                            for key in ("error", "error_description", "message")
                            if key in parsed
                        }
                except (OSError, ValueError, TypeError):
                    pass
            return {
                "status": "TOKEN_REQUEST_FAILED",
                "http_status": status,
                "content_type": content_type,
                "error_type": type(exc).__name__,
                "safe_error_fields": safe_fields,
            }
