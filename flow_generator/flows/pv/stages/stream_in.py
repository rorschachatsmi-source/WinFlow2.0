"""PV stream-in and stream-out APR stages."""

from __future__ import annotations

from typing import Dict, List, Optional

from flow_generator.core.models import Stage, make_job, make_stage, make_task
from flow_generator.flows.pv.config import PVConfig


def block_blitz_outputs(blocks: List[Dict[str, str]], config: PVConfig) -> List[str]:
    return [
        config.io(config.files.sub_block_blitz, block=block["name"], workdir=block["workdir"])
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
    files = config.files
    tasks = []
    for block in blocks:
        name = block["name"]
        workdir = block["workdir"]
        jobs = [
            make_job(
                name=f"{name}_laker",
                command=f"{paths.flow_dir}/{scripts.sub_bzgdsin_apr} {name} {workdir}",
                inputs=[config.io(files.sub_block_gds, block=name, workdir=workdir)],
                outputs=[config.io(files.sub_block_blitz, block=name, workdir=workdir)],
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
    files = config.files
    tasks = []

    for block in blocks:
        name = block["name"]
        workdir = block["workdir"]
        jobs = [
            make_job(
                name=f"{name}_calibre",
                command=f"{paths.flow_dir}/{scripts.sub_calibre_dm} {name} {workdir}",
                inputs=[config.io(files.sub_dmexcl_calibre, block=name, workdir=workdir)],
                outputs=[config.io(files.sub_dummy_gds, block=name, workdir=workdir)],
                queue=config.queue,
                cpu=config.cpu,
            ),
            make_job(
                name=f"{name}_laker",
                command=f"{paths.flow_dir}/{scripts.sub_bzgdsin_apr} {name} dummy",
                inputs=[config.io(files.sub_dummy_gds, block=name, workdir=workdir)],
                outputs=[config.io(files.sub_block_blitz, block=name, workdir=workdir)],
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
    files = config.files
    top = config.top
    if input_from_stream_out:
        inputs = [config.io(files.full_gds)]
    else:
        inputs = [config.io(files.apr_gds)]
        if extra_inputs:
            inputs.extend(extra_inputs)
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
                        outputs=[config.io(files.apr_blitz)],
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
    files = config.files
    top = config.top
    inputs = [config.io(files.apr_gds)] + block_blitz_outputs(blocks, config)
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
                        outputs=[config.io(files.apr_blitz)],
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
    files = config.files
    top = config.top
    return make_stage(
        "streamOut_APR",
        [
            make_task(
                f"{top}_streamOut_APR",
                [
                    make_job(
                        name="laker_Out",
                        command=f"{paths.flow_dir}/{scripts.bzgdsout_apr}",
                        inputs=[config.io(files.apr_blitz)],
                        outputs=[config.io(files.full_gds)],
                        queue=config.queue,
                        cpu=config.cpu,
                    )
                ],
            )
        ],
    )
