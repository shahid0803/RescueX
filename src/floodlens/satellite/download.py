from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from .auth import CopernicusAuthenticator
from .errors import AuthenticationError, DownloadError, IntegrityError
from .models import SatelliteScene


class DownloadService:
    def __init__(self, root: Path, authenticator: CopernicusAuthenticator, retries: int = 3):
        self.root = root
        self.authenticator = authenticator
        self.retries = retries
        self.manifest = root / "manifests" / "downloads.jsonl"
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest.parent.mkdir(parents=True, exist_ok=True)

    def _destination(self, scene: SatelliteScene) -> Path:
        sensor = scene.sensor.replace("-", "")
        return self.root / "raw" / "satellite" / sensor / f"{scene.product_id}.download"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def download(self, scene: SatelliteScene) -> SatelliteScene:
        destination = self._destination(scene)
        if destination.exists() and destination.stat().st_size > 0:
            if scene.checksum_if_available and self._sha256(destination) != scene.checksum_if_available:
                destination.unlink()
            else:
                return self._record(scene, destination, "cache_hit")
        if not scene.download_url_or_reference:
            raise DownloadError(f"scene {scene.scene_id} has no download reference")
        temporary = destination.with_suffix(destination.suffix + ".part")
        for attempt in range(self.retries):
            try:
                token = self.authenticator.get_token()
                request = Request(scene.download_url_or_reference, headers={"Authorization": f"Bearer {token}"})
                with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                if temporary.stat().st_size == 0:
                    raise IntegrityError("downloaded file is zero bytes")
                if scene.checksum_if_available and self._sha256(temporary) != scene.checksum_if_available:
                    raise IntegrityError("download checksum does not match source checksum")
                temporary.replace(destination)
                return self._record(scene, destination, "downloaded")
            except AuthenticationError:
                raise
            except Exception as exc:
                if temporary.exists():
                    temporary.unlink()
                if attempt == self.retries - 1:
                    raise DownloadError(f"download failed for {scene.scene_id}") from exc
                time.sleep(2**attempt)
        raise DownloadError(f"download failed for {scene.scene_id}")

    def _record(self, scene: SatelliteScene, path: Path, status: str) -> SatelliteScene:
        record = {
            "scene_id": scene.scene_id,
            "product_id": scene.product_id,
            "sensor": scene.sensor,
            "acquisition_datetime": scene.acquisition_datetime.isoformat(),
            "local_path": str(path),
            "source": scene.provider,
            "download_datetime": datetime.now(timezone.utc).isoformat(),
            "file_size": path.stat().st_size,
            "checksum": self._sha256(path),
            "status": status,
        }
        with self.manifest.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        return scene.model_copy(update={"local_path": str(path), "download_status": "downloaded"})
