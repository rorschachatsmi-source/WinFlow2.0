"""Predefined job-node library under flow_generator/node/*.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

from flow_generator.core.io import write_flow
from flow_generator.core.models import Job, make_flow, make_job, make_stage, make_task
from winflow_config import get_config

# Default library location: flow_generator/node/
NODE_DIR = Path(__file__).resolve().parent.parent / "node"

# Placeholders used in generated PV node templates
PLACEHOLDER_TOP = "TOP_MODULE"
PLACEHOLDER_BLOCK = "BLOCK"
PLACEHOLDER_WORKDIR = "workdir"


def node_dir() -> Path:
    return NODE_DIR


def _wrap_job_as_flow(job: Job, flow_name: str = "custom_flow", poll_interval: int = 20) -> dict:
    return make_flow(
        flow_name,
        [make_stage("stage_1", [make_task("task_1", [job])])],
        poll_interval=poll_interval,
    )


def extract_job_from_flow(data: dict) -> Job:
    """Return the first job found in a node/flow JSON document."""
    for stage in data.get("stages", []):
        for task in stage.get("tasks", []):
            jobs = task.get("jobs", [])
            if jobs:
                return jobs[0]  # type: ignore[return-value]
    raise ValueError("No job found in node JSON")


def extract_flow_name(data: dict) -> str:
    name = str(data.get("flow_name", "") or "").strip()
    return name or get_config().generator.blank_flow_name


def list_node_files(directory: Optional[Path] = None) -> List[Path]:
    root = directory or node_dir()
    if not root.is_dir():
        return []
    return sorted(root.glob("*.json"), key=lambda p: p.stem.lower())


def list_node_names(directory: Optional[Path] = None) -> List[str]:
    return [path.stem for path in list_node_files(directory)]


def list_nodes_by_flow(directory: Optional[Path] = None) -> List[Tuple[str, List[Tuple[str, str]]]]:
    """
    Group node templates by flow_name from each JSON.

    Returns [(flow_name, [(stem, job_display_name), ...]), ...]
    Prefer PV, APR, then custom_flow, then other names alphabetically.
    """
    root = directory or node_dir()
    grouped: dict = {}
    for path in list_node_files(root):
        try:
            with path.open(encoding="utf-8") as fp:
                data = json.load(fp)
            flow = extract_flow_name(data)
            job = extract_job_from_flow(data)
            display = str(job.get("name") or path.stem)
        except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError):
            flow = get_config().generator.blank_flow_name
            display = path.stem
        grouped.setdefault(flow, []).append((path.stem, display))

    for jobs in grouped.values():
        jobs.sort(key=lambda item: item[1].lower())

    preferred = ["PV", "APR", get_config().generator.blank_flow_name]
    ordered: List[Tuple[str, List[Tuple[str, str]]]] = []
    for name in preferred:
        if name in grouped:
            ordered.append((name, grouped.pop(name)))
    for name in sorted(grouped.keys(), key=str.lower):
        ordered.append((name, grouped[name]))
    return ordered


def load_node(name: str, directory: Optional[Path] = None) -> Job:
    """Load a predefined job by stem name (without .json)."""
    root = directory or node_dir()
    path = root / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Node template not found: {path}")
    with path.open(encoding="utf-8") as fp:
        data = json.load(fp)
    return extract_job_from_flow(data)


def load_node_flow(name: str, directory: Optional[Path] = None) -> dict:
    root = directory or node_dir()
    path = root / f"{name}.json"
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


def write_node(
    job: Job,
    directory: Optional[Path] = None,
    filename: Optional[str] = None,
    flow_name: Optional[str] = None,
) -> Path:
    root = directory or node_dir()
    root.mkdir(parents=True, exist_ok=True)
    stem = filename or job["name"]
    path = root / f"{stem}.json"
    gen_cfg = get_config().generator
    flow = _wrap_job_as_flow(
        job,
        flow_name=flow_name or gen_cfg.blank_flow_name,
        poll_interval=gen_cfg.poll_interval,
    )
    write_flow(flow, path)
    return path


def _pv_paths():
    return get_config().pv.paths


def _pv_scripts():
    return get_config().pv.scripts


def _pv_files():
    return get_config().pv.files


def builtin_node_jobs() -> List[Tuple[str, str, Job]]:
    """
    Canonical job nodes derived from Blank / APR / PV template rules.

    Returns list of (filename_stem, flow_name, job).
    """
    gen = get_config().generator
    apr = get_config().apr
    pv_flow = get_config().pv.flow_name
    apr_flow = apr.flow_name
    blank_flow = gen.blank_flow_name
    paths = _pv_paths()
    scripts = _pv_scripts()
    files = _pv_files()
    queue = gen.default_queue
    cpu = gen.default_cpu
    top = PLACEHOLDER_TOP
    block = PLACEHOLDER_BLOCK
    workdir = PLACEHOLDER_WORKDIR

    nodes: List[Tuple[str, str, Job]] = []

    def add(stem: str, flow: str, job: Job) -> None:
        nodes.append((stem, flow, job))

    add(
        "blank_job",
        blank_flow,
        make_job("job_1", "", [], [], queue, gen.new_job_cpu),
    )

    apr_bases = list(apr.stages_before_current) + [apr.current_stage] + list(apr.stages_after_current)
    for base in apr_bases:
        output = apr.output_template.format(job_name=base)
        add(
            base,
            apr_flow,
            make_job(
                base,
                apr.run_stage_template.format(job_name=base),
                [],
                [output],
                apr.default_queue,
                int(apr.default_cpu) if str(apr.default_cpu).isdigit() else cpu,
            ),
        )

    add(
        "sub_calibre",
        pv_flow,
        make_job(
            f"{block}_calibre",
            f"{paths.flow_dir}/{scripts.sub_calibre_dm} {block} {workdir}",
            [f"{paths.laker_dir}/{files.sub_dmexcl_calibre}"],
            [f"{paths.laker_dir}/{block}_dummy.gds.gz"],
            queue,
            cpu,
        ),
    )
    add(
        "sub_laker",
        pv_flow,
        make_job(
            f"{block}_laker",
            f"{paths.flow_dir}/{scripts.sub_bzgdsin_apr} {block} {workdir}",
            [f"{workdir}/GDS/{block}.gds.gz"],
            [f"{paths.laker_dir}/{block}.blitz++"],
            queue,
            cpu,
        ),
    )
    add(
        "laker_In",
        pv_flow,
        make_job(
            "laker_In",
            f"{paths.flow_dir}/{scripts.bzgdsin_apr}",
            [f"{paths.data_dir}/{files.apr_gds}"],
            [f"{paths.laker_dir}/{top}_APR.blitz++"],
            queue,
            cpu,
        ),
    )
    add(
        "laker_pre_In",
        pv_flow,
        make_job(
            "laker_pre_In",
            f"{paths.flow_dir}/{scripts.pre_bzgdsin_apr}",
            [f"{paths.data_dir}/{files.apr_gds}"],
            [f"{paths.laker_dir}/{top}_APR.blitz++"],
            queue,
            cpu,
        ),
    )
    add(
        "laker_Out",
        pv_flow,
        make_job(
            "laker_Out",
            f"{paths.flow_dir}/{scripts.bzgdsout_apr}",
            [f"{paths.laker_dir}/{top}_APR.blitz++"],
            [f"{paths.gds_dir}/{top}_FULL.gds.gz"],
            queue,
            cpu,
        ),
    )
    add(
        "SPI",
        pv_flow,
        make_job(
            "SPI",
            f"{paths.flow_dir}/{scripts.spi}",
            [
                files.spi_input_spi.format(top=top),
                f"{paths.data_dir}/{files.spi_input_netlist}",
            ],
            [f"{paths.spi_dir}/{files.spi_output.format(top=top)}"],
            queue,
            cpu,
        ),
    )
    add(
        "RCXT",
        pv_flow,
        make_job(
            "RCXT",
            f"{paths.flow_dir}/{scripts.rcxt}",
            [f"{paths.gds_dir}/DM.gds"],
            [files.rcxt_output],
            queue,
            cpu,
        ),
    )
    add(
        "LVS",
        pv_flow,
        make_job(
            "LVS",
            f"{paths.flow_dir}/{scripts.lvs}",
            [
                files.lvs_hcell,
                files.lvs_calibre,
                files.lvs_layout_spi,
                f"{paths.gds_dir}/{top}.oas",
                f"{paths.spi_dir}/{files.spi_output.format(top=top)}",
            ],
            [files.lvs_report],
            queue,
            cpu,
        ),
    )

    for flag_cfg in get_config().pv.merge_flags:
        script = flag_cfg.script
        tag = flag_cfg.tag
        if tag == "DMEXCL":
            gds_outs = [f"{paths.gds_dir}/{tag}.gds.gz"]
        else:
            gds_outs = [f"{paths.gds_dir}/{tag}.gds"]
        add(
            f"Calibre_{script}",
            pv_flow,
            make_job(
                f"Calibre_{script}",
                f"{paths.flow_dir}/{script}.sh",
                [f"{paths.gds_dir}/{top}_FULL.gds.gz"],
                gds_outs,
                queue,
                cpu,
            ),
        )
        add(
            f"laker_{script}",
            pv_flow,
            make_job(
                f"laker_{script}",
                f"{paths.flow_dir}/bzgdsin_{script}.sh",
                gds_outs,
                [f"{paths.laker_dir}/{top}_{tag}.blitz++"],
                queue,
                cpu,
            ),
        )

    add(
        "laker_text",
        pv_flow,
        make_job(
            "laker_text",
            f"{paths.flow_dir}/{scripts.laker_text}",
            [
                f"{paths.laker_dir}/{top}_APR.blitz++",
                f"{paths.gds_dir}/{top}_FULL.gds.gz",
            ],
            [f"{paths.laker_dir}/{files.create_text_tcl}"],
            queue,
            cpu,
        ),
    )
    add(
        "laker_topLib",
        pv_flow,
        make_job(
            "laker_topLib",
            f"{paths.flow_dir}/{scripts.laker_topLib}",
            [
                f"{paths.laker_dir}/{top}_DM.blitz++",
                f"{paths.laker_dir}/{files.create_text_tcl}",
                f"{paths.data_dir}/{files.laker_top_lib_tcl}",
            ],
            [f"{paths.laker_dir}/{top}_LIB.blitz++"],
            queue,
            cpu,
        ),
    )
    add(
        "top_Out",
        pv_flow,
        make_job(
            f"{top}_Out",
            f"{paths.flow_dir}/{scripts.bzgdsout_top}",
            [
                f"{paths.laker_dir}/{top}_LIB.blitz++",
                f"{paths.gds_dir}/{top}_FULL.gds.gz",
            ],
            [f"{paths.gds_dir}/{top}.gds.gz"],
            queue,
            cpu,
        ),
    )
    add(
        "gds2oas",
        pv_flow,
        make_job(
            "gds2oas",
            f"{paths.flow_dir}/{scripts.gds2oas}",
            [f"{paths.gds_dir}/{top}.gds.gz"],
            [f"{paths.gds_dir}/{top}.oas"],
            queue,
            cpu,
        ),
    )

    for drc_name in ("DRC", "DRC_BE", "DRC_FE"):
        add(
            drc_name,
            pv_flow,
            make_job(
                drc_name,
                f"{paths.flow_dir}/{scripts.run_drc} {drc_name}",
                [f"{paths.gds_dir}/{top}.oas"],
                [files.drc_report],
                queue,
                cpu,
            ),
        )

    return nodes


def generate_builtin_nodes(directory: Optional[Path] = None) -> List[Path]:
    """Write all builtin template job nodes as flow-shaped JSON files."""
    root = directory or node_dir()
    written: List[Path] = []
    for stem, flow_name, job in builtin_node_jobs():
        written.append(write_node(job, directory=root, filename=stem, flow_name=flow_name))
    return written


def node_summary(job: Job) -> str:
    lines = [
        f"name:    {job.get('name', '')}",
        f"queue:   {job.get('queue', '')}",
        f"cpu:     {job.get('cpu', 1)}",
        f"command: {job.get('command', '') or '(empty)'}",
        "inputs:",
    ]
    inputs = job.get("inputs") or []
    if inputs:
        lines.extend(f"  - {p}" for p in inputs)
    else:
        lines.append("  (none)")
    lines.append("outputs:")
    outputs = job.get("outputs") or []
    if outputs:
        lines.extend(f"  - {p}" for p in outputs)
    else:
        lines.append("  (none)")
    return "\n".join(lines)


if __name__ == "__main__":
    paths = generate_builtin_nodes()
    print(f"Wrote {len(paths)} node templates to {node_dir()}")
    for path in paths:
        print(f"  {path.name}")
