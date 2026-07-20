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
    files = config.files
    merge_tasks: List[Task] = []
    laker_outputs: List[str] = []

    for flag_cfg in get_config().pv.merge_flags:
        if not flag_enabled(settings, flag_cfg.setting_key):
            continue

        script = flag_cfg.script
        tag = flag_cfg.tag
        tag_gds_tmpl = files.merge_tag_gds_gz if tag == "DMEXCL" else files.merge_tag_gds
        outputs = [config.io(tag_gds_tmpl, tag=tag)]
        blitz = config.io(files.merge_blitz, tag=tag)
        laker_outputs.append(blitz)
        merge_tasks.append(
            make_task(
                tag,
                [
                    make_job(
                        f"Calibre_{script}",
                        f"{paths.flow_dir}/{script}.sh",
                        [config.io(files.full_gds)],
                        outputs,
                        config.queue,
                        config.cpu,
                    ),
                    make_job(
                        f"laker_{script}",
                        f"{paths.flow_dir}/bzgdsin_{script}.sh",
                        outputs,
                        [blitz],
                        config.queue,
                        config.cpu,
                    ),
                ],
            )
        )

    create_text = config.io(files.create_text_tcl)
    merge_tasks.append(
        make_task(
            "laker_text",
            [
                make_job(
                    "laker_text",
                    f"{paths.flow_dir}/{config.scripts.laker_text}",
                    [
                        config.io(files.apr_blitz),
                        config.io(files.full_gds),
                    ],
                    [create_text],
                    config.queue,
                    config.cpu,
                )
            ],
        )
    )
    laker_outputs.append(create_text)
    laker_outputs.append(config.io(files.laker_top_lib_tcl))

    return make_stage("Merge", merge_tasks), laker_outputs
