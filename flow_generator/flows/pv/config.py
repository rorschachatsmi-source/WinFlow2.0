"""PV flow settings derived from BuildContext."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, TYPE_CHECKING

from flow_generator.core.context import BuildContext
from flow_generator.flows.pv.paths import PVPaths
from winflow_config import get_config

if TYPE_CHECKING:
    from winflow_config.models import PVFilesConfig, PVScriptsConfig


@dataclass(frozen=True)
class PVConfig:
    top: str
    final_top: str
    queue: str
    cpu: str
    dmexcl_ptn: bool
    paths: PVPaths
    scripts: "PVScriptsConfig"
    files: "PVFilesConfig"

    @classmethod
    def from_context(cls, context: BuildContext) -> "PVConfig":
        settings = context.settings
        pv_cfg = get_config().pv
        top = settings["TOP_MODULE"]
        top_post = settings.get("TOP_MODULE_POST", "").strip()
        return cls(
            top=top,
            final_top=top_post if top_post else top,
            queue=settings["MACHINE_QUEUE"],
            cpu=settings["MACHINE_CPU"],
            dmexcl_ptn=settings.get("FLAG_DMEXCL_PTN", "0") == "1",
            paths=PVPaths.from_settings(settings),
            scripts=pv_cfg.scripts,
            files=pv_cfg.files,
        )


def flag_enabled(settings: Dict[str, str], key: str) -> bool:
    return settings.get(key, "0") == "1"
