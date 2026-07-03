"""APR (place-and-route) flow builder."""

from __future__ import annotations

from typing import List, Optional

from flow_generator.core.builder import FlowBuilder
from flow_generator.core.context import BuildContext
from flow_generator.core.models import Flow, Job, Stage, make_flow, make_job, make_stage, make_task
from flow_generator.core.registry import register
from winflow_config import get_config


def format_apr_suffix(prefix: str) -> str:
    """Return _{prefix} when prefix is non-empty, else empty string."""
    prefix = prefix.strip()
    return f"_{prefix}" if prefix else ""


def apr_job_name(stage_base: str, prefix: str) -> str:
    return f"{stage_base}{format_apr_suffix(prefix)}"


def apr_job_output(job_name: str) -> str:
    template = get_config().apr.output_template
    return template.format(job_name=job_name)


def apr_job_names(prefix: str = "", is_current: bool = False) -> List[str]:
    apr_cfg = get_config().apr
    suffix = format_apr_suffix(prefix)
    names = [f"{base}{suffix}" for base in apr_cfg.stages_before_current]
    if is_current:
        names.append(f"{apr_cfg.current_stage}{suffix}")
    names.extend(f"{base}{suffix}" for base in apr_cfg.stages_after_current)
    return names


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

    for name in apr_job_names(prefix, is_current):
        inputs = [prev_output] if prev_output else []
        output = apr_job_output(name)
        job = make_job(
            name=name,
            command=apr_cfg.run_stage_template.format(job_name=name),
            inputs=inputs,
            outputs=[output],
            queue=queue,
            cpu=cpu,
            machine=machine,
        )
        jobs.append(job)
        prev_output = output

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
