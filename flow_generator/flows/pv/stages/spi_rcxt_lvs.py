"""PV SPI, RCXT, and LVS jobs."""

from __future__ import annotations

from flow_generator.core.models import Stage, Task, make_job, make_stage, make_task
from flow_generator.flows.pv.config import PVConfig


def spi_task(config: PVConfig) -> Task:
    inputs, outputs = config.job_io("SPI")
    return make_task(
        "SPI",
        [
            make_job(
                "SPI",
                f"{config.paths.flow_dir}/{config.scripts.spi}",
                inputs,
                outputs,
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
    inputs, outputs = config.job_io("RCXT")
    return make_task(
        "RCXT",
        [
            make_job(
                "RCXT",
                f"{config.paths.flow_dir}/{config.scripts.rcxt}",
                inputs,
                outputs,
                config.queue,
                config.cpu,
            )
        ],
    )


def lvs_task(config: PVConfig) -> Task:
    inputs, outputs = config.job_io("LVS")
    return make_task(
        "LVS",
        [
            make_job(
                "LVS",
                f"{config.paths.flow_dir}/{config.scripts.lvs}",
                inputs,
                outputs,
                config.queue,
                config.cpu,
            )
        ],
    )
