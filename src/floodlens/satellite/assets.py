from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import IntegrityError
from .models import SatelliteScene


@dataclass(frozen=True)
class ResolvedAssets:
    measurement: dict[str, str]
    metadata: dict[str, str]
    quality: dict[str, str]


class SatelliteAssetResolver:
    def resolve(self, scene: SatelliteScene, assets: dict[str, dict[str, Any]]) -> ResolvedAssets:
        raise NotImplementedError


class Sentinel1AssetResolver(SatelliteAssetResolver):
    def resolve(self, scene: SatelliteScene, assets: dict[str, dict[str, Any]]) -> ResolvedAssets:
        measurement = {
            name: item["href"] for name, item in assets.items()
            if item.get("href") and (
                item.get("roles") and "data" in item["roles"] or
                "measurement" in name.lower() or name.lower() in {"vv", "vh", "hh", "hv"}
            )
        }
        if not measurement:
            raise IntegrityError("Sentinel-1 item has no measurement asset")
        return ResolvedAssets(measurement, {}, {})


class Sentinel2AssetResolver(SatelliteAssetResolver):
    required_bands = {"B02", "B03", "B04", "B08"}

    def resolve(self, scene: SatelliteScene, assets: dict[str, dict[str, Any]]) -> ResolvedAssets:
        measurement = {}
        quality = {}
        for name, item in assets.items():
            key = name.upper().replace("_", "")
            if key in self.required_bands or key.startswith(tuple(self.required_bands)):
                if item.get("href"):
                    measurement[name] = item["href"]
            if "SCL" in key and item.get("href"):
                quality["SCL"] = item["href"]
        if not self.required_bands.intersection({name.upper() for name in measurement}):
            raise IntegrityError("Sentinel-2 item has no required spectral measurement assets")
        return ResolvedAssets(measurement, {}, quality)
