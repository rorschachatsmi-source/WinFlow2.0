"""PV SPI, RCXT, and LVS jobs."""

from __future__ import annotations

from flow_generator.core.models import Stage, Task, make_job, make_stage, make_task
from flow_generator.flows.pv.config import PVConfig


def spi_task(config: PVConfig) -> Task:
    paths = config.paths
    files = config.files
    return make_task(
        "SPI",
        [
            make_job(
                "SPI",
                f"{paths.flow_dir}/{config.scripts.spi}",
                config.io_list(files.spi_inputs),
                config.io_list(files.spi_outputs),
                config.queue,
                config.cpu,
            )
        ],
    )


def add_spi_task(stage: Stage, config: PVConfig) -> Stage:
    """Append SPI as a parallel task on the first stream-in stage."""
    stage["tasks"].append(spi_task(config))
    return stage


def rcxt_task(config: PVConfig) -> Task:
    paths = config.paths
    files = config.files
    return make_task(
        "RCXT",
        [
            make_job(
                "RCXT",
                f"{paths.flow_dir}/{config.scripts.rcxt}",
                config.io_list(files.rcxt_inputs),
                config.io_list(files.rcxt_outputs),
                config.queue,
                config.cpu,
            )
        ],
    )


def lvs_task(config: PVConfig) -> Task:
    paths = config.paths
    files = config.files
    return make_task(
        "LVS",
        [
            make_job(
                "LVS",
                f"{paths.flow_dir}/{config.scripts.lvs}",
                config.io_list(files.lvs_inputs),
                config.io_list(files.lvs_outputs),
                config.queue,
                config.cpu,
            )
        ],
    )
