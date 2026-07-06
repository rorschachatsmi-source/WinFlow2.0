"""Configuration dataclasses for WinFlow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


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
class PVFilesConfig:
    apr_gds: str = "apr.gds.gz"
    laker_top_lib_tcl: str = "laker_topLib.tcl"
    sub_dmexcl_calibre: str = "sub_dmexcl.calibre"
    create_text_tcl: str = "create_text_from_APRgds.tcl"
    drc_report: str = "DRC.rep"
    spi_input_spi: str = "{top}.spi"
    spi_input_netlist: str = "netlist.pg.v.gz"
    spi_output: str = "{top}.cdl"
    rcxt_output: str = "flag_starrc_done"
    lvs_hcell: str = "hcell"
    lvs_calibre: str = "lvs.calibre"
    lvs_layout_spi: str = "layout.spi"
    lvs_report: str = "lvs.rep"


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
    files: PVFilesConfig = field(default_factory=PVFilesConfig)
    merge_flags: Tuple[PVMergeFlagConfig, ...] = (
        PVMergeFlagConfig("FLAG_DMF", "dmf", "DM"),
        PVMergeFlagConfig("FLAG_DOD", "dod", "DODPO"),
        PVMergeFlagConfig("FLAG_DEX", "dex", "DMEXCL"),
    )


@dataclass(frozen=True)
class APRConfig:
    flow_name: str = "APR"
    stage_name: str = "APR"
    task_name: str = "apr"
    run_stage_template: str = "./run_stage {job_name}"
    output_template: str = "{job_name}/DB/{job_name}.enc.dat"
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
