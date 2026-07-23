"""Configuration dataclasses for WinFlow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class RunnerConfig:
    default_flow_file: str = "flow.json"
    session_log_dir: str = "logs"
    session_log_file: str = "logs/flow_runner.log"
    job_log_dir: str = "log"
    poll_interval: int = 20
    default_queue: str = "tpdsd1"
    default_cpu: int = 4
    logger_name: str = "FlowRunner"
    kill_poll_ms: int = 15000
    kill_max_retries: int = 4
    log_tail_interval_sec: float = 0.5
    job_log_view_lines: int = 100
    thread_join_timeout_sec: float = 1.0
    log_viewer: str = "gvim"
    auto_load_delay_ms: int = 150


@dataclass(frozen=True)
class LSFConfig:
    bsub: str = "bsub"
    bjobs: str = "bjobs"
    bkill: str = "bkill"
    bjobs_noheader: bool = True
    bjobs_output_field: str = "stat"
    job_name_timestamp_format: str = "%Y%m%d_%H%M%S"


@dataclass(frozen=True)
class GeneratorConfig:
    default_flow_type: str = "pv"
    default_setting_file: str = "setting.sh"
    default_blocks_file: str = "block_stream.list"
    default_output_file: str = "flow.json"
    poll_interval: int = 20
    default_queue: str = "tpdsd1"
    default_cpu: int = 4
    blank_flow_name: str = "custom_flow"
    new_job_cpu: int = 1


@dataclass(frozen=True)
class PVPathsConfig:
    laker_dir: str = "../LakerBZ"
    gds_dir: str = "../GDS"
    flow_dir: str = "../flow"
    data_dir: str = "../DATA"
    spi_dir: str = "../spi"


@dataclass(frozen=True)
class PVScriptsConfig:
    sub_bzgdsin_apr: str = "sub_bzgdsin_apr.sh"
    sub_calibre_dm: str = "sub_calibre_dm.sh"
    bzgdsin_apr: str = "bzgdsin_apr.sh"
    pre_bzgdsin_apr: str = "pre_bzgdsin_apr.sh"
    bzgdsout_apr: str = "bzgdsout_apr.sh"
    laker_topLib: str = "laker_topLib.sh"
    bzgdsout_top: str = "bzgdsout_top.sh"
    gds2oas: str = "gds2oas.sh"
    laker_text: str = "laker_text.sh"
    run_drc: str = "run_drc"
    spi: str = "run_spi.sh"
    rcxt: str = "run_rcxt.sh"
    lvs: str = "run_lvs.sh"


@dataclass(frozen=True)
class JobIOConfig:
    """Per-job I/O (and optional command) path templates.

    ``None`` means “unset” so APR can override only some fields against ``default_job``.
    """

    inputs: Optional[Tuple[str, ...]] = None
    outputs: Optional[Tuple[str, ...]] = None
    command: Optional[str] = None

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "JobIOConfig":
        return cls(
            inputs=tuple(data["inputs"]) if "inputs" in data else None,
            outputs=tuple(data["outputs"]) if "outputs" in data else None,
            command=data["command"] if "command" in data else None,
        )

    def resolved(
        self,
        default: Optional["JobIOConfig"] = None,
    ) -> Tuple[Tuple[str, ...], Tuple[str, ...], str]:
        """Return concrete (inputs, outputs, command), filling gaps from ``default``."""
        base = default or JobIOConfig(inputs=(), outputs=(), command="")
        inputs = self.inputs if self.inputs is not None else (base.inputs or ())
        outputs = self.outputs if self.outputs is not None else (base.outputs or ())
        command = self.command if self.command is not None else (base.command or "")
        return inputs, outputs, command

    def merge_over(self, other: "JobIOConfig") -> "JobIOConfig":
        """Overlay ``other`` fields that are set (not ``None``)."""
        return JobIOConfig(
            inputs=other.inputs if other.inputs is not None else self.inputs,
            outputs=other.outputs if other.outputs is not None else self.outputs,
            command=other.command if other.command is not None else self.command,
        )


def _default_pv_jobs() -> Dict[str, JobIOConfig]:
    return {
        "sub_laker": JobIOConfig(
            inputs=("{workdir}/GDS/{block}.gds.gz",),
            outputs=("{laker_dir}/{block}.blitz++",),
        ),
        "sub_calibre": JobIOConfig(
            inputs=("{laker_dir}/sub_dmexcl.calibre",),
            outputs=("{laker_dir}/{block}_dummy.gds.gz",),
        ),
        "sub_laker_dummy": JobIOConfig(
            inputs=("{laker_dir}/{block}_dummy.gds.gz",),
            outputs=("{laker_dir}/{block}.blitz++",),
        ),
        "laker_In": JobIOConfig(
            inputs=("{data_dir}/apr.gds.gz",),
            outputs=("{laker_dir}/{top}_APR.blitz++",),
        ),
        "laker_In_from_stream_out": JobIOConfig(
            inputs=("{gds_dir}/{top}_FULL.gds.gz",),
            outputs=("{laker_dir}/{top}_APR.blitz++",),
        ),
        "laker_pre_In": JobIOConfig(
            inputs=("{data_dir}/apr.gds.gz",),
            outputs=("{laker_dir}/{top}_APR.blitz++",),
        ),
        "laker_Out": JobIOConfig(
            inputs=("{laker_dir}/{top}_APR.blitz++",),
            outputs=("{gds_dir}/{top}_FULL.gds.gz",),
        ),
        "SPI": JobIOConfig(
            inputs=("{top}.spi", "{data_dir}/netlist.pg.v.gz"),
            outputs=("{spi_dir}/{top}.cdl",),
        ),
        "RCXT": JobIOConfig(
            inputs=("{gds_dir}/DM.gds",),
            outputs=("flag_starrc_done",),
        ),
        "LVS": JobIOConfig(
            inputs=(
                "hcell",
                "lvs.calibre",
                "layout.spi",
                "{gds_dir}/{final_top}.oas",
                "{spi_dir}/{top}.cdl",
            ),
            outputs=("lvs.rep",),
        ),
        "Calibre_merge": JobIOConfig(
            inputs=("{gds_dir}/{top}_FULL.gds.gz",),
            outputs=("{gds_dir}/{tag}.gds",),
        ),
        "Calibre_merge_gz": JobIOConfig(
            inputs=("{gds_dir}/{top}_FULL.gds.gz",),
            outputs=("{gds_dir}/{tag}.gds.gz",),
        ),
        "laker_merge": JobIOConfig(
            inputs=("{gds_dir}/{tag}.gds",),
            outputs=("{laker_dir}/{top}_{tag}.blitz++",),
        ),
        "laker_text": JobIOConfig(
            inputs=(
                "{laker_dir}/{top}_APR.blitz++",
                "{gds_dir}/{top}_FULL.gds.gz",
            ),
            outputs=("{laker_dir}/create_text_from_APRgds.tcl",),
        ),
        "laker_topLib": JobIOConfig(
            inputs=(
                "{laker_dir}/{top}_DM.blitz++",
                "{laker_dir}/create_text_from_APRgds.tcl",
                "{data_dir}/laker_topLib.tcl",
            ),
            outputs=("{laker_dir}/{final_top}_LIB.blitz++",),
        ),
        "top_Out": JobIOConfig(
            inputs=(
                "{laker_dir}/{final_top}_LIB.blitz++",
                "{gds_dir}/{top}_FULL.gds.gz",
            ),
            outputs=("{gds_dir}/{final_top}.gds.gz",),
        ),
        "gds2oas": JobIOConfig(
            inputs=("{gds_dir}/{final_top}.gds.gz",),
            outputs=("{gds_dir}/{final_top}.oas",),
        ),
        "DRC": JobIOConfig(
            inputs=("{gds_dir}/{final_top}.oas",),
            outputs=("DRC.rep",),
        ),
        "DRC_BE": JobIOConfig(
            inputs=("{gds_dir}/{final_top}.oas",),
            outputs=("DRC.rep",),
        ),
        "DRC_FE": JobIOConfig(
            inputs=("{gds_dir}/{final_top}.oas",),
            outputs=("DRC.rep",),
        ),
        # Static extras appended to merge → topLib input list
        "merge_topLib_extras": JobIOConfig(
            inputs=(
                "{laker_dir}/create_text_from_APRgds.tcl",
                "{data_dir}/laker_topLib.tcl",
            ),
            outputs=(),
        ),
    }


@dataclass(frozen=True)
class PVMergeFlagConfig:
    setting_key: str
    script: str
    tag: str


@dataclass(frozen=True)
class PVFlowConfig:
    flow_name: str = "PV"
    required_settings: Tuple[str, ...] = ("TOP_MODULE", "MACHINE_QUEUE", "MACHINE_CPU")
    paths: PVPathsConfig = field(default_factory=PVPathsConfig)
    scripts: PVScriptsConfig = field(default_factory=PVScriptsConfig)
    jobs: Dict[str, JobIOConfig] = field(default_factory=_default_pv_jobs)
    merge_flags: Tuple[PVMergeFlagConfig, ...] = (
        PVMergeFlagConfig("FLAG_DMF", "dmf", "DM"),
        PVMergeFlagConfig("FLAG_DOD", "dod", "DODPO"),
        PVMergeFlagConfig("FLAG_DEX", "dex", "DMEXCL"),
    )


def _default_apr_job() -> JobIOConfig:
    return JobIOConfig(
        inputs=("{prev_output}",),
        outputs=("{job_name}/DB/{job_name}.enc.dat",),
        command="./run_stage {job_name}",
    )


def _default_apr_jobs() -> Dict[str, JobIOConfig]:
    return {
        "01_floorplan": JobIOConfig(inputs=()),
    }


@dataclass(frozen=True)
class APRConfig:
    flow_name: str = "APR"
    stage_name: str = "APR"
    task_name: str = "apr"
    default_job: JobIOConfig = field(default_factory=_default_apr_job)
    jobs: Dict[str, JobIOConfig] = field(default_factory=_default_apr_jobs)
    stages_before_current: Tuple[str, ...] = (
        "01_floorplan",
        "02_prects_opt",
        "03_cts_concurrent",
    )
    current_stage: str = "04_postcts_opt"
    stages_after_current: Tuple[str, ...] = (
        "05_route.tcl",
        "06_postroute_opt",
    )
    default_queue: str = "tpdsd1"
    default_cpu: str = "4"


@dataclass(frozen=True)
class GUIConfig:
    generator_window_size: str = "1280x800"
    generator_window_min: str = "960x640"
    runner_window_size: str = "1280x820"
    sidebar_min_width: int = 220


@dataclass(frozen=True)
class AppConfig:
    runner: RunnerConfig = field(default_factory=RunnerConfig)
    lsf: LSFConfig = field(default_factory=LSFConfig)
    generator: GeneratorConfig = field(default_factory=GeneratorConfig)
    pv: PVFlowConfig = field(default_factory=PVFlowConfig)
    apr: APRConfig = field(default_factory=APRConfig)
    gui: GUIConfig = field(default_factory=GUIConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        from winflow_config.loader import merge_dataclass

        return merge_dataclass(cls(), data)
