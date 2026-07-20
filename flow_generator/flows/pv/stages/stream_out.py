"""PV stream-out TOP stage."""

from __future__ import annotations

from typing import Dict, List

from flow_generator.core.models import Stage, make_job, make_stage, make_task
from flow_generator.flows.pv.config import PVConfig, flag_enabled
from flow_generator.flows.pv.stages.spi_rcxt_lvs import rcxt_task


def stream_out_top_stage(
    config: PVConfig,
    laker_outputs: List[str],
    settings: Dict[str, str],
) -> Stage:
    paths = config.paths
    scripts = config.scripts
    files = config.files
    top = config.top

    main_task = make_task(
        f"{top}_streamOut_TOP",
        [
            make_job(
                "laker_topLib",
                f"{paths.flow_dir}/{scripts.laker_topLib}",
                laker_outputs,
                [config.io(files.lib_blitz)],
                config.queue,
                config.cpu,
            ),
            make_job(
                f"{top}_Out",
                f"{paths.flow_dir}/{scripts.bzgdsout_top}",
                [
                    config.io(files.lib_blitz),
                    config.io(files.full_gds),
                ],
                [config.io(files.final_gds)],
                config.queue,
                config.cpu,
            ),
            make_job(
                "gds2oas",
                f"{paths.flow_dir}/{scripts.gds2oas}",
                [config.io(files.final_gds)],
                [config.io(files.final_oas)],
                config.queue,
                config.cpu,
            ),
        ],
    )

    tasks = [main_task]
    if flag_enabled(settings, "FLAG_RCXT"):
        tasks.append(rcxt_task(config))

    return make_stage("streamOut_TOP", tasks)
