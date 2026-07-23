"""PV post-streamOut_TOP verification stage (DRC / LVS)."""

from __future__ import annotations

from typing import Dict, List, Optional

from flow_generator.core.models import Stage, Task, make_job, make_stage, make_task
from flow_generator.flows.pv.config import PVConfig, flag_enabled
from flow_generator.flows.pv.stages.spi_rcxt_lvs import lvs_task, _rewrite_layout_inputs


def _use_drc_stage_name(settings: Dict[str, str]) -> bool:
    return flag_enabled(settings, "FLAG_DRC") or (
        not flag_enabled(settings, "FLAG_DRCBE")
        and not flag_enabled(settings, "FLAG_DRCFE")
    )


def _drc_task(config: PVConfig, name: str, settings: Dict[str, str]) -> Task:
    inputs, outputs = config.job_io(name)
    inputs = _rewrite_layout_inputs(inputs, config, settings)
    return make_task(
        name,
        [
            make_job(
                name,
                f"{config.paths.flow_dir}/{config.scripts.run_drc} {name}",
                inputs,
                outputs,
                config.queue,
                config.cpu,
            )
        ],
    )


def build_post_gds2oas_stage(
    settings: Dict[str, str],
    config: PVConfig,
) -> Optional[Stage]:
    """Build DRC/Verify stage after streamOut_TOP (after gds2oas or *_Out)."""
    tasks: List[Task] = []
    use_drc_stage = _use_drc_stage_name(settings)

    if use_drc_stage:
        tasks.append(_drc_task(config, "DRC", settings))

    if flag_enabled(settings, "FLAG_DRCBE"):
        tasks.append(_drc_task(config, "DRC_BE", settings))

    if flag_enabled(settings, "FLAG_DRCFE"):
        tasks.append(_drc_task(config, "DRC_FE", settings))

    if flag_enabled(settings, "FLAG_LVS"):
        tasks.append(lvs_task(config, settings))

    if not tasks:
        return None

    stage_name = "DRC" if use_drc_stage else "Verify"
    return make_stage(stage_name, tasks)


# Backward-compatible alias used by older imports/tests.
def verify_stage(
    settings: Dict[str, str],
    config: PVConfig,
) -> Optional[Stage]:
    return build_post_gds2oas_stage(settings, config)
