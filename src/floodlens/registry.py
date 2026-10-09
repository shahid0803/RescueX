from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SourceRegistry:
    def __init__(self, path: Path):
        self.path = path
        self._sources = {item["id"]: item for item in json.loads(path.read_text(encoding="utf-8"))["sources"]}

    def get(self, source_id: str) -> dict[str, Any]:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise ValueError(f"source is not registered: {source_id}") from exc

    def assert_allowed(self, source_id: str, boundary: str) -> None:
        source = self.get(source_id)
        if boundary not in source["allowed_in"]:
            raise ValueError(f"{source_id} is not allowed in the {boundary} boundary")

    def validate_metadata(self, source_id: str, metadata: dict[str, Any], boundary: str) -> None:
        self.assert_allowed(source_id, boundary)
        missing = [key for key in self.get(source_id)["required_metadata"] if not metadata.get(key)]
        if missing:
            raise ValueError(f"{source_id} metadata missing required fields: {', '.join(missing)}")
