from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from .errors import CatalogUnavailableError
from .auth import CopernicusAuthenticator
from .models import SatelliteScene, SatelliteSearchRequest
from .service import search_window


class CDSEStacProvider:
    endpoint = "https://stac.dataspace.copernicus.eu/v1/search"
    source_catalog = "CDSE STAC v1"

    def __init__(
        self,
        endpoint: str | None = None,
        timeout: int = 30,
        authenticator: CopernicusAuthenticator | None = None,
    ):
        self.endpoint = endpoint or self.endpoint
        self.timeout = timeout
        self.authenticator = authenticator

    def search(self, request: SatelliteSearchRequest) -> list[SatelliteScene]:
        collection = "sentinel-1-grd" if request.sensor == "sentinel-1" else "sentinel-2-l2a"
        start, end = search_window(request)
        payload = {
            "collections": [collection],
            "intersects": request.aoi.geometry,
            "datetime": f"{start.isoformat().replace('+00:00', 'Z')}/{end.isoformat().replace('+00:00', 'Z')}",
            "limit": request.limit,
        }
        headers = {"Content-Type": "application/json", "Accept": "application/geo+json"}
        if self.authenticator is not None:
            headers["Authorization"] = f"Bearer {self.authenticator.get_token()}"
        http_request = Request(
            self.endpoint,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self.timeout) as response:
                feature_collection = json.loads(response.read())
        except Exception as exc:
            raise CatalogUnavailableError("CDSE STAC search failed") from exc
        scenes = [self._scene(feature, request.sensor) for feature in feature_collection.get("features", [])]
        if request.max_cloud_percentage is not None:
            scenes = [
                scene
                for scene in scenes
                if scene.cloud_cover is None or scene.cloud_cover <= request.max_cloud_percentage
            ]
        return scenes

    def _scene(self, feature: dict, sensor: str) -> SatelliteScene:
        properties = feature.get("properties", {})
        scene_id = str(feature.get("id", ""))
        if not scene_id or "datetime" not in properties:
            raise CatalogUnavailableError("STAC item is missing stable id or datetime")
        return SatelliteScene(
            scene_id=scene_id,
            product_id=scene_id,
            satellite=properties.get("platform", "unknown"),
            sensor=sensor,
            mission=properties.get("constellation", "Sentinel"),
            product_type=properties.get("sar:product_type"),
            acquisition_datetime=datetime.fromisoformat(properties["datetime"].replace("Z", "+00:00")),
            processing_level=properties.get("processing:level"),
            relative_orbit=properties.get("sat:relative_orbit"),
            orbit_direction=properties.get("sat:orbit_state"),
            footprint=feature["geometry"],
            bbox=tuple(feature["bbox"]) if feature.get("bbox") else None,
            cloud_cover=properties.get("eo:cloud_cover"),
            polarization=properties.get("sar:polarizations", []),
            available_bands=list(feature.get("assets", {}).keys()),
            download_url_or_reference=next(
                (asset.get("href") for asset in feature.get("assets", {}).values() if asset.get("href")), None
            ),
            provider="copernicus-data-space",
            source_catalog=self.source_catalog,
            provenance={"stac_item": scene_id, "query_timestamp": datetime.now(timezone.utc).isoformat()},
        )
