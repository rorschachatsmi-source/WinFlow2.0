"""PV verify stage."""

from __future__ import annotations

from typing import Dict, List, Optional

from flow_generator.core.models import Stage, Task, make_job, make_stage, make_task
from flow_generator.flows.pv.config import PVConfig, flag_enabled


def verify_stage(
    settings: Dict[str, str],
    config: PVConfig,
) -> Optional[Stage]:
    paths = config.paths
    scripts = config.scripts
    files = config.files
    final_top = config.final_top
    verify_tasks: List[Task] = []

    if flag_enabled(settings, "FLAG_DRCBE"):
        verify_tasks.append(
            make_task(
                "DRC_BE",
                [
                    make_job(
                        "DRC_BE",
                        f"{paths.flow_dir}/{scripts.run_drc} DRC_BE",
                        [f"{paths.gds_dir}/{final_top}.oas"],
                        [files.drc_report],
                        config.queue,
                        config.cpu,
                    )
                ],
            )
        )

    if flag_enabled(settings, "FLAG_DRCFE"):
        verify_tasks.append(
            make_task(
                "DRC_FE",
                [
                    make_job(
                        "DRC_FE",
                        f"{paths.flow_dir}/{scripts.run_drc} DRC_FE",
                        [f"{paths.gds_dir}/{final_top}.oas"],
                        [files.drc_report],
                        config.queue,
                        config.cpu,
                    )
                ],
            )
        )

    if not verify_tasks:
        return None

    return make_stage("Verify", verify_tasks)
