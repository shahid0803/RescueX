"""Provider boundary for reproducible satellite scene acquisition."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class Scene:
    product_id: str
    sensor: str
    acquired: date
    orbit: str | None
    source: str
    cache_path: str | None = None


class SceneProvider(Protocol):
    def search(self, aoi: dict, start: date, end: date, sensor: str) -> list[Scene]:
        ...


class ManifestSceneProvider:
    """Reads already acquired scenes from a caller-owned manifest.

    Network access is intentionally not hidden in the core pipeline. A cloud
    provider adapter can implement SceneProvider and enforce credentials,
    retries, checksums, and same-orbit pairing.
    """

    def __init__(self, scenes: list[Scene]):
        self.scenes = scenes

    def search(self, aoi: dict, start: date, end: date, sensor: str) -> list[Scene]:
        return [
            scene
            for scene in self.scenes
            if scene.sensor == sensor and start <= scene.acquired <= end
        ]
