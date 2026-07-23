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
    merge_tasks: List[Task] = []
    laker_outputs: List[str] = []

    for flag_cfg in get_config().pv.merge_flags:
        if not flag_enabled(settings, flag_cfg.setting_key):
            continue

        script = flag_cfg.script
        tag = flag_cfg.tag
        calibre_key = "Calibre_merge_gz" if tag == "DMEXCL" else "Calibre_merge"
        cal_in, cal_out = config.job_io(calibre_key, tag=tag)
        # laker_merge inputs follow calibre outputs (wire by path, not template).
        _, lak_out = config.job_io("laker_merge", tag=tag)
        blitz = lak_out[0]
        laker_outputs.append(blitz)
        merge_tasks.append(
            make_task(
                tag,
                [
                    make_job(
                        f"Calibre_{script}",
                        f"{paths.flow_dir}/{script}.sh",
                        cal_in,
                        cal_out,
                        config.queue,
                        config.cpu,
                    ),
                    make_job(
                        f"laker_{script}",
                        f"{paths.flow_dir}/bzgdsin_{script}.sh",
                        cal_out,
                        [blitz],
                        config.queue,
                        config.cpu,
                    ),
                ],
            )
        )

    text_in, text_out = config.job_io("laker_text")
    merge_tasks.append(
        make_task(
            "laker_text",
            [
                make_job(
                    "laker_text",
                    f"{paths.flow_dir}/{config.scripts.laker_text}",
                    text_in,
                    text_out,
                    config.queue,
                    config.cpu,
                )
            ],
        )
    )
    laker_outputs.extend(text_out)
    extras_in, _ = config.job_io("merge_topLib_extras")
    laker_outputs.extend(extras_in)

    return make_stage("Merge", merge_tasks), laker_outputs
