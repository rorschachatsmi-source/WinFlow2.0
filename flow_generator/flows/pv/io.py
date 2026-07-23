"""Resolve PV job I/O path templates from config.json."""

from __future__ import annotations

from typing import List, Mapping, Optional, Sequence

from flow_generator.flows.pv.paths import PVPaths


def format_pv_io(
    template: str,
    *,
    paths: PVPaths,
    top: str,
    final_top: Optional[str] = None,
    **extra: str,
) -> str:
    """Expand a full I/O path template.

    Supported placeholders:
    ``{top}``, ``{final_top}``, ``{block}``, ``{workdir}``, ``{tag}``,
    ``{laker_dir}``, ``{gds_dir}``, ``{data_dir}``, ``{spi_dir}``, ``{flow_dir}``.
    """
    values: Mapping[str, str] = {
        "top": top,
        "final_top": final_top if final_top is not None else top,
        "laker_dir": paths.laker_dir,
        "gds_dir": paths.gds_dir,
        "data_dir": paths.data_dir,
        "spi_dir": paths.spi_dir,
        "flow_dir": paths.flow_dir,
        **extra,
    }
    return template.format(**values)


def format_pv_io_list(
    templates: Sequence[str],
    *,
    paths: PVPaths,
    top: str,
    final_top: Optional[str] = None,
    **extra: str,
) -> List[str]:
    return [
        format_pv_io(template, paths=paths, top=top, final_top=final_top, **extra)
        for template in templates
    ]
