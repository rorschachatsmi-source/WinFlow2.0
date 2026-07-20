"""PV stream-in and stream-out APR stages."""

from __future__ import annotations

from typing import Dict, List, Optional

from flow_generator.core.models import Stage, make_job, make_stage, make_task
from flow_generator.flows.pv.config import PVConfig


def block_blitz_outputs(blocks: List[Dict[str, str]], config: PVConfig) -> List[str]:
    tmpl = config.jobs["sub_laker"].resolved()[1][0]
    return [
        config.io(tmpl, block=block["name"], workdir=block["workdir"])
        for block in blocks
    ]


def stream_in_sub_stage(
    blocks: List[Dict[str, str]],
    config: PVConfig,
) -> Optional[Stage]:
    if not blocks:
        return None

    paths = config.paths
    scripts = config.scripts
    tasks = []
    for block in blocks:
        name = block["name"]
        workdir = block["workdir"]
        inputs, outputs = config.job_io("sub_laker", block=name, workdir=workdir)
        jobs = [
            make_job(
                name=f"{name}_laker",
                command=f"{paths.flow_dir}/{scripts.sub_bzgdsin_apr} {name} {workdir}",
                inputs=inputs,
                outputs=outputs,
                queue=config.queue,
                cpu=config.cpu,
            )
        ]
        tasks.append(make_task(name, jobs))

    return make_stage("streamIn_sub", tasks)


def stream_in_sub_dummy_stage(
    blocks: List[Dict[str, str]],
    config: PVConfig,
) -> Stage:
    paths = config.paths
    scripts = config.scripts
    tasks = []

    for block in blocks:
        name = block["name"]
        workdir = block["workdir"]
        cal_in, cal_out = config.job_io("sub_calibre", block=name, workdir=workdir)
        lak_in, lak_out = config.job_io("sub_laker_dummy", block=name, workdir=workdir)
        jobs = [
            make_job(
                name=f"{name}_calibre",
                command=f"{paths.flow_dir}/{scripts.sub_calibre_dm} {name} {workdir}",
                inputs=cal_in,
                outputs=cal_out,
                queue=config.queue,
                cpu=config.cpu,
            ),
            make_job(
                name=f"{name}_laker",
                command=f"{paths.flow_dir}/{scripts.sub_bzgdsin_apr} {name} dummy",
                inputs=lak_in,
                outputs=lak_out,
                queue=config.queue,
                cpu=config.cpu,
            ),
        ]
        tasks.append(make_task(f"{name}_dummy", jobs))

    return make_stage("streamIn_sub_dummy", tasks)


def stream_in_apr_stage(
    config: PVConfig,
    extra_inputs: Optional[List[str]] = None,
    *,
    input_from_stream_out: bool = False,
) -> Stage:
    paths = config.paths
    scripts = config.scripts
    top = config.top
    job_key = "laker_In_from_stream_out" if input_from_stream_out else "laker_In"
    inputs, outputs = config.job_io(job_key)
    if not input_from_stream_out and extra_inputs:
        inputs = list(inputs) + list(extra_inputs)
    return make_stage(
        "streamIn_APR",
        [
            make_task(
                f"{top}_streamIn_APR",
                [
                    make_job(
                        name="laker_In",
                        command=f"{paths.flow_dir}/{scripts.bzgdsin_apr}",
                        inputs=inputs,
                        outputs=outputs,
                        queue=config.queue,
                        cpu=config.cpu,
                    )
                ],
            )
        ],
    )


def pre_stream_in_apr_stage(
    blocks: List[Dict[str, str]],
    config: PVConfig,
) -> Stage:
    paths = config.paths
    scripts = config.scripts
    top = config.top
    inputs, outputs = config.job_io("laker_pre_In")
    inputs = list(inputs) + block_blitz_outputs(blocks, config)
    return make_stage(
        "pre_streamIn_APR",
        [
            make_task(
                f"{top}_pre_streamIn_APR",
                [
                    make_job(
                        name="laker_pre_In",
                        command=f"{paths.flow_dir}/{scripts.pre_bzgdsin_apr}",
                        inputs=inputs,
                        outputs=outputs,
                        queue=config.queue,
                        cpu=config.cpu,
                    )
                ],
            )
        ],
    )


def stream_out_apr_stage(config: PVConfig) -> Stage:
    paths = config.paths
    scripts = config.scripts
    top = config.top
    inputs, outputs = config.job_io("laker_Out")
    return make_stage(
        "streamOut_APR",
        [
            make_task(
                f"{top}_streamOut_APR",
                [
                    make_job(
                        name="laker_Out",
                        command=f"{paths.flow_dir}/{scripts.bzgdsout_apr}",
                        inputs=inputs,
                        outputs=outputs,
                        queue=config.queue,
                        cpu=config.cpu,
                    )
                ],
            )
        ],
    )
