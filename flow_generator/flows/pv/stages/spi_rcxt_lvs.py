"""PV SPI, RCXT, and LVS jobs."""

from __future__ import annotations

from typing import Dict, List

from flow_generator.core.models import Stage, Task, make_job, make_task
from flow_generator.flows.pv.config import PVConfig


def _use_oasii(settings: Dict[str, str]) -> bool:
    return settings.get("USE_OASII", "1") == "1"


def _layout_input_for_verify(config: PVConfig, settings: Dict[str, str]) -> str:
    """Layout file DRC/LVS wait on: OAS from gds2oas, or GDS from top_Out."""
    if _use_oasii(settings):
        _ins, outs = config.job_io("gds2oas")
        return outs[0]
    _ins, outs = config.job_io("top_Out")
    return outs[0]


def _rewrite_layout_inputs(
    inputs: List[str],
    config: PVConfig,
    settings: Dict[str, str],
) -> List[str]:
    if _use_oasii(settings):
        return list(inputs)
    # Swap OAS layout paths for top_Out GDS so edges hang off *_Out.
    layout = _layout_input_for_verify(config, settings)
    return [layout if path.endswith(".oas") else path for path in inputs]


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


def lvs_task(config: PVConfig, settings: Dict[str, str] | None = None) -> Task:
    settings = settings or {}
    inputs, outputs = config.job_io("LVS")
    inputs = _rewrite_layout_inputs(inputs, config, settings)
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
