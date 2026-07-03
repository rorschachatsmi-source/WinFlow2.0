"""Flow document models and factory helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from winflow_config import get_config


class Job(TypedDict):
    name: str
    command: str
    queue: str
    cpu: int
    inputs: List[str]
    outputs: List[str]


class Task(TypedDict):
    name: str
    jobs: List[Job]


class Stage(TypedDict):
    name: str
    tasks: List[Task]


class Flow(TypedDict):
    flow_name: str
    poll_interval: int
    stages: List[Stage]


def make_job(
    name: str,
    command: str,
    inputs: List[str],
    outputs: List[str],
    queue: str,
    cpu: Any,
    machine: str = "",
) -> Job:
    job: Job = {
        "name": name,
        "command": command,
        "queue": queue,
        "cpu": int(cpu),
        "inputs": inputs,
        "outputs": outputs,
    }
    if str(machine).strip():
        job["machine"] = str(machine).strip()  # type: ignore[typeddict-unknown-key]
    return job


def make_task(name: str, jobs: List[Job]) -> Task:
    return {
        "name": name,
        "jobs": jobs,
    }


def make_stage(name: str, tasks: List[Task]) -> Stage:
    return {
        "name": name,
        "tasks": tasks,
    }


def make_flow(
    flow_name: str,
    stages: List[Stage],
    poll_interval: Optional[int] = None,
) -> Flow:
    if poll_interval is None:
        poll_interval = get_config().generator.poll_interval
    return {
        "flow_name": flow_name,
        "poll_interval": poll_interval,
        "stages": stages,
    }
