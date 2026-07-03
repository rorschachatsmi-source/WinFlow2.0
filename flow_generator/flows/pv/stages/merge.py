"""PV merge stage."""

from __future__ import annotations

from typing import Dict, List, Tuple

from flow_generator.core.models import Stage, Task, make_job, make_stage, make_task
from flow_generator.flows.pv.config import PVConfig, flag_enabled
from winflow_config import get_config


def build_merge_stage(
    settings: Dict[str, str],
    config: PVConfig,
) -> Tuple[Stage, List[str]]:
    paths = config.paths
    top = config.top
    merge_tasks: List[Task] = []
    laker_outputs: List[str] = []

    for flag_cfg in get_config().pv.merge_flags:
        if not flag_enabled(settings, flag_cfg.setting_key):
            continue

        script = flag_cfg.script
        tag = flag_cfg.tag
        if tag == "DMEXCL":
            outputs = [f"{paths.gds_dir}/{tag}.gds.gz"]
        else:
            outputs = [f"{paths.gds_dir}/{tag}.gds"]

        laker_outputs.append(f"{paths.laker_dir}/{top}_{tag}.blitz++")
        merge_tasks.append(
            make_task(
                tag,
                [
                    make_job(
                        f"Calibre_{script}",
                        f"{paths.flow_dir}/{script}.sh",
                        [f"{paths.gds_dir}/{top}_FULL.gds.gz"],
                        outputs,
                        config.queue,
                        config.cpu,
                    ),
                    make_job(
                        f"laker_{script}",
                        f"{paths.flow_dir}/bzgdsin_{script}.sh",
                        outputs,
                        [f"{paths.laker_dir}/{top}_{tag}.blitz++"],
                        config.queue,
                        config.cpu,
                    ),
                ],
            )
        )

    merge_tasks.append(
        make_task(
            "laker_text",
            [
                make_job(
                    "laker_text",
                    f"{paths.flow_dir}/{config.scripts.laker_text}",
                    [
                        f"{paths.laker_dir}/{top}_APR.blitz++",
                        f"{paths.gds_dir}/{top}_FULL.gds.gz",
                    ],
                    [f"{paths.laker_dir}/{config.files.create_text_tcl}"],
                    config.queue,
                    config.cpu,
                )
            ],
        )
    )
    laker_outputs.append(f"{paths.laker_dir}/{config.files.create_text_tcl}")
    laker_outputs.append(f"{paths.data_dir}/{config.files.laker_top_lib_tcl}")

    return make_stage("Merge", merge_tasks), laker_outputs
