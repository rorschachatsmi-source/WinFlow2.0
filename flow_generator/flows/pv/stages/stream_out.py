"""PV stream-out TOP stage."""

from __future__ import annotations

from typing import List

from flow_generator.core.models import Stage, make_job, make_stage, make_task
from flow_generator.flows.pv.config import PVConfig


def stream_out_top_stage(
    config: PVConfig,
    laker_outputs: List[str],
) -> Stage:
    paths = config.paths
    scripts = config.scripts
    top = config.top
    final_top = config.final_top

    return make_stage(
        "streamOut_TOP",
        [
            make_task(
                f"{top}_streamOut_TOP",
                [
                    make_job(
                        "laker_topLib",
                        f"{paths.flow_dir}/{scripts.laker_topLib}",
                        laker_outputs,
                        [f"{paths.laker_dir}/{final_top}_LIB.blitz++"],
                        config.queue,
                        config.cpu,
                    ),
                    make_job(
                        f"{top}_Out",
                        f"{paths.flow_dir}/{scripts.bzgdsout_top}",
                        [
                            f"{paths.laker_dir}/{final_top}_LIB.blitz++",
                            f"{paths.gds_dir}/{top}_FULL.gds.gz",
                        ],
                        [f"{paths.gds_dir}/{final_top}.gds.gz"],
                        config.queue,
                        config.cpu,
                    ),
                    make_job(
                        "gds2oas",
                        f"{paths.flow_dir}/{scripts.gds2oas}",
                        [f"{paths.gds_dir}/{final_top}.gds.gz"],
                        [f"{paths.gds_dir}/{final_top}.oas"],
                        config.queue,
                        config.cpu,
                    ),
                ],
            )
        ],
    )
