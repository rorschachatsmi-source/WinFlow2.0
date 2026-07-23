"""PV flow settings derived from BuildContext."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple, TYPE_CHECKING

from flow_generator.core.context import BuildContext
from flow_generator.flows.pv.io import format_pv_io, format_pv_io_list
from flow_generator.flows.pv.paths import PVPaths
from winflow_config import get_config
from winflow_config.models import JobIOConfig

if TYPE_CHECKING:
    from winflow_config.models import PVScriptsConfig


@dataclass(frozen=True)
class PVConfig:
    top: str
    final_top: str
    queue: str
    cpu: str
    dmexcl_ptn: bool
    paths: PVPaths
    scripts: "PVScriptsConfig"
    jobs: Dict[str, JobIOConfig]

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
            jobs=pv_cfg.jobs,
        )

    def io(self, template: str, **extra: str) -> str:
        """Expand one path template."""
        return format_pv_io(
            template,
            paths=self.paths,
            top=self.top,
            final_top=self.final_top,
            **extra,
        )

    def io_list(self, templates: Sequence[str], **extra: str) -> List[str]:
        """Expand a list of path templates."""
        return format_pv_io_list(
            templates,
            paths=self.paths,
            top=self.top,
            final_top=self.final_top,
            **extra,
        )

    def job_io(self, name: str, **extra: str) -> Tuple[List[str], List[str]]:
        """Return expanded (inputs, outputs) for a named job in ``pv.jobs``."""
        spec = self.jobs.get(name)
        if spec is None:
            raise KeyError(f"Unknown PV job I/O config: {name!r}")
        inputs, outputs, _command = spec.resolved()
        return self.io_list(inputs, **extra), self.io_list(outputs, **extra)


def flag_enabled(settings: Dict[str, str], key: str) -> bool:
    return settings.get(key, "0") == "1"
