"""PV flow path configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from winflow_config.models import PVPathsConfig


@dataclass(frozen=True)
class PVPaths:
    laker_dir: str
    gds_dir: str
    flow_dir: str
    data_dir: str
    spi_dir: str

    @classmethod
    def defaults(cls) -> "PVPaths":
        return cls.from_settings({})

    @classmethod
    def from_settings(
        cls,
        settings: dict,
        defaults: Optional["PVPathsConfig"] = None,
    ) -> "PVPaths":
        from winflow_config import get_config

        base = defaults or get_config().pv.paths
        return cls(
            laker_dir=settings.get("LAKER_DIR", base.laker_dir),
            gds_dir=settings.get("GDS_DIR", base.gds_dir),
            flow_dir=settings.get("FLOW_DIR", base.flow_dir),
            data_dir=settings.get("DATA_DIR", base.data_dir),
            spi_dir=settings.get("SPI_DIR", base.spi_dir),
        )
