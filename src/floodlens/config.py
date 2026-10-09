from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    log_level: str = "INFO"
    data_dir: Path = Path(".rescuex-data")
    cache_dir: Path = Path(".rescuex-cache")
    max_aoi_km2: float = 250.0
    scene_pair_days_before: int = 30
    scene_pair_days_after: int = 14

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            environment=os.getenv("RESCUEX_ENV", cls.environment),
            log_level=os.getenv("RESCUEX_LOG_LEVEL", cls.log_level),
            data_dir=Path(os.getenv("RESCUEX_DATA_DIR", str(cls.data_dir))),
            cache_dir=Path(os.getenv("RESCUEX_CACHE_DIR", str(cls.cache_dir))),
            max_aoi_km2=float(os.getenv("RESCUEX_MAX_AOI_KM2", str(cls.max_aoi_km2))),
            scene_pair_days_before=int(os.getenv("RESCUEX_SCENE_PAIR_DAYS_BEFORE", str(cls.scene_pair_days_before))),
            scene_pair_days_after=int(os.getenv("RESCUEX_SCENE_PAIR_DAYS_AFTER", str(cls.scene_pair_days_after))),
        )
