"""PV SPI, RCXT, and LVS jobs."""

from __future__ import annotations

from flow_generator.core.models import Stage, Task, make_job, make_stage, make_task
from flow_generator.flows.pv.config import PVConfig


def spi_input_spi_path(config: PVConfig) -> str:
    return config.files.spi_input_spi.format(top=config.top)


def spi_input_netlist_path(config: PVConfig) -> str:
    return f"{config.paths.data_dir}/{config.files.spi_input_netlist}"


def spi_output_path(config: PVConfig) -> str:
    filename = config.files.spi_output.format(top=config.top)
    return f"{config.paths.spi_dir}/{filename}"


def dm_gds_path(config: PVConfig) -> str:
    return f"{config.paths.gds_dir}/DM.gds"


def rcxt_output_path(config: PVConfig) -> str:
    return config.files.rcxt_output


def spi_task(config: PVConfig) -> Task:
    paths = config.paths
    return make_task(
        "SPI",
        [
            make_job(
                "SPI",
                f"{paths.flow_dir}/{config.scripts.spi}",
                [
                    spi_input_spi_path(config),
                    spi_input_netlist_path(config),
                ],
                [spi_output_path(config)],
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
    return make_task(
        "RCXT",
        [
            make_job(
                "RCXT",
                f"{paths.flow_dir}/{config.scripts.rcxt}",
                [dm_gds_path(config)],
                [rcxt_output_path(config)],
                config.queue,
                config.cpu,
            )
        ],
    )


def lvs_oas_input(config: PVConfig) -> str:
    return f"{config.paths.gds_dir}/{config.final_top}.oas"


def lvs_cdl_input(config: PVConfig) -> str:
    filename = config.files.spi_output.format(top=config.top)
    return f"{config.paths.spi_dir}/{filename}"


def lvs_task(config: PVConfig) -> Task:
    paths = config.paths
    files = config.files
    return make_task(
        "LVS",
        [
            make_job(
                "LVS",
                f"{paths.flow_dir}/{config.scripts.lvs}",
                [
                    files.lvs_hcell,
                    files.lvs_calibre,
                    files.lvs_layout_spi,
                    lvs_oas_input(config),
                    lvs_cdl_input(config),
                ],
                [files.lvs_report],
                config.queue,
                config.cpu,
            )
        ],
    )
