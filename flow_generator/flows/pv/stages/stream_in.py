"""PV stream-in and stream-out APR stages."""

from __future__ import annotations

from typing import Dict, List, Optional

from flow_generator.core.models import Stage, make_job, make_stage, make_task
from flow_generator.flows.pv.config import PVConfig


def block_blitz_outputs(blocks: List[Dict[str, str]], config: PVConfig) -> List[str]:
    paths = config.paths
    return [f"{paths.laker_dir}/{block['name']}.blitz++" for block in blocks]


def _apr_gds_input(config: PVConfig) -> str:
    paths = config.paths
    return f"{paths.data_dir}/{config.files.apr_gds}"


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
        jobs = [
            make_job(
                name=f"{block['name']}_laker",
                command=f"{paths.flow_dir}/{scripts.sub_bzgdsin_apr} {block['name']} {block['workdir']}",
                inputs=[f"{block['workdir']}/GDS/{block['name']}.gds.gz"],
                outputs=[f"{paths.laker_dir}/{block['name']}.blitz++"],
                queue=config.queue,
                cpu=config.cpu,
            )
        ]
        tasks.append(make_task(block["name"], jobs))

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
        jobs = [
            make_job(
                name=f"{block['name']}_calibre",
                command=f"{paths.flow_dir}/{scripts.sub_calibre_dm} {block['name']} {block['workdir']}",
                inputs=[f"{paths.laker_dir}/{files.sub_dmexcl_calibre}"],
                outputs=[f"{paths.laker_dir}/{block['name']}_dummy.gds.gz"],
                queue=config.queue,
                cpu=config.cpu,
            ),
            make_job(
                name=f"{block['name']}_laker",
                command=f"{paths.flow_dir}/{scripts.sub_bzgdsin_apr} {block['name']} dummy",
                inputs=[f"{paths.laker_dir}/{block['name']}_dummy.gds.gz"],
                outputs=[f"{paths.laker_dir}/{block['name']}.blitz++"],
                queue=config.queue,
                cpu=config.cpu,
            ),
        ]
        tasks.append(make_task(f"{block['name']}_dummy", jobs))

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
    if input_from_stream_out:
        inputs = [f"{paths.gds_dir}/{top}_FULL.gds.gz"]
    else:
        inputs = [_apr_gds_input(config)]
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
                        outputs=[f"{paths.laker_dir}/{top}_APR.blitz++"],
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
    inputs = [_apr_gds_input(config)] + block_blitz_outputs(blocks, config)
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
                        outputs=[f"{paths.laker_dir}/{top}_APR.blitz++"],
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
    return make_stage(
        "streamOut_APR",
        [
            make_task(
                f"{top}_streamOut_APR",
                [
                    make_job(
                        name="laker_Out",
                        command=f"{paths.flow_dir}/{scripts.bzgdsout_apr}",
                        inputs=[f"{paths.laker_dir}/{top}_APR.blitz++"],
                        outputs=[f"{paths.gds_dir}/{top}_FULL.gds.gz"],
                        queue=config.queue,
                        cpu=config.cpu,
                    )
                ],
            )
        ],
    )
