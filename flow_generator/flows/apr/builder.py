"""APR (place-and-route) flow builder."""

from __future__ import annotations

from typing import List, Optional, Tuple

from flow_generator.core.builder import FlowBuilder
from flow_generator.core.context import BuildContext
from flow_generator.core.models import Flow, Job, Stage, make_flow, make_job, make_stage, make_task
from flow_generator.core.registry import register
from winflow_config import get_config
from winflow_config.models import JobIOConfig


def format_apr_suffix(prefix: str) -> str:
    """Return _{prefix} when prefix is non-empty, else empty string."""
    prefix = prefix.strip()
    return f"_{prefix}" if prefix else ""


def apr_job_name(stage_base: str, prefix: str) -> str:
    return f"{stage_base}{format_apr_suffix(prefix)}"


def apr_stage_bases(is_current: bool = False) -> List[str]:
    apr_cfg = get_config().apr
    names = list(apr_cfg.stages_before_current)
    if is_current:
        names.append(apr_cfg.current_stage)
    names.extend(apr_cfg.stages_after_current)
    return names


def apr_job_names(prefix: str = "", is_current: bool = False) -> List[str]:
    suffix = format_apr_suffix(prefix)
    return [f"{base}{suffix}" for base in apr_stage_bases(is_current)]


def _resolve_stage_io(stage_base: str) -> Tuple[Tuple[str, ...], Tuple[str, ...], str]:
    apr_cfg = get_config().apr
    override = apr_cfg.jobs.get(stage_base, JobIOConfig())
    merged = apr_cfg.default_job.merge_over(override)
    return merged.resolved(apr_cfg.default_job)


def _expand_apr_paths(
    templates: Tuple[str, ...],
    *,
    job_name: str,
    prev_output: Optional[str],
) -> List[str]:
    paths: List[str] = []
    for template in templates:
        if template == "{prev_output}":
            if prev_output:
                paths.append(prev_output)
            continue
        paths.append(template.format(job_name=job_name, prev_output=prev_output or ""))
    return paths


def apr_job_output(job_name: str, stage_base: Optional[str] = None) -> str:
    """Return the primary output path for an APR job (first outputs entry)."""
    if stage_base is None:
        # Infer base by stripping a trailing _prefix if present — prefer explicit base.
        apr_cfg = get_config().apr
        for base in (
            list(apr_cfg.stages_before_current)
            + [apr_cfg.current_stage]
            + list(apr_cfg.stages_after_current)
        ):
            if job_name == base or job_name.startswith(base + "_"):
                stage_base = base
                break
        stage_base = stage_base or job_name
    _inputs, outputs, _command = _resolve_stage_io(stage_base)
    expanded = _expand_apr_paths(outputs, job_name=job_name, prev_output=None)
    return expanded[0] if expanded else ""


def build_apr_jobs(
    prefix: str = "",
    is_current: bool = False,
    queue: Optional[str] = None,
    cpu: Optional[str] = None,
    machine: str = "",
) -> List[Job]:
    apr_cfg = get_config().apr
    queue = queue if queue is not None else apr_cfg.default_queue
    cpu = cpu if cpu is not None else apr_cfg.default_cpu
    jobs: List[Job] = []
    prev_output: Optional[str] = None

    for stage_base in apr_stage_bases(is_current):
        name = apr_job_name(stage_base, prefix)
        input_tmpls, output_tmpls, command_tmpl = _resolve_stage_io(stage_base)
        inputs = _expand_apr_paths(input_tmpls, job_name=name, prev_output=prev_output)
        outputs = _expand_apr_paths(output_tmpls, job_name=name, prev_output=prev_output)
        command = command_tmpl.format(job_name=name, prev_output=prev_output or "")
        job = make_job(
            name=name,
            command=command,
            inputs=inputs,
            outputs=outputs,
            queue=queue,
            cpu=cpu,
            machine=machine,
        )
        jobs.append(job)
        prev_output = outputs[0] if outputs else prev_output

    return jobs


def build_apr_stage(
    prefix: str = "",
    is_current: bool = False,
    queue: Optional[str] = None,
    cpu: Optional[str] = None,
    machine: str = "",
) -> Stage:
    apr_cfg = get_config().apr
    jobs = build_apr_jobs(prefix, is_current, queue, cpu, machine)
    return make_stage(apr_cfg.stage_name, [make_task(apr_cfg.task_name, jobs)])


@register("apr")
class APRFlowBuilder(FlowBuilder):
    """Build the APR place-and-route flow."""

    @classmethod
    def validate_context(cls, context: BuildContext) -> List[str]:
        return []

    @classmethod
    def build(cls, context: BuildContext) -> Flow:
        settings = context.settings
        apr_cfg = get_config().apr
        gen_cfg = get_config().generator
        prefix = settings.get("APR_PREFIX", "")
        is_current = settings.get("APR_IS_CURRENT", "0") == "1"
        queue = settings.get("MACHINE_QUEUE", apr_cfg.default_queue)
        cpu = settings.get("MACHINE_CPU", apr_cfg.default_cpu)
        machine = settings.get("MACHINE_HOST", "")

        stage = build_apr_stage(prefix, is_current, queue, cpu, machine)
        return make_flow(apr_cfg.flow_name, [stage], poll_interval=gen_cfg.poll_interval)
