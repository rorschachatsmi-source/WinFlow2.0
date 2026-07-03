"""Manual parent/child dependency helpers for the flow editor."""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from flow_generator.gui.document import FlowDocument, JobKey, _job_key
from flow_generator.gui.graph import build_job_graph


def _output_producers(document: FlowDocument) -> Dict[str, JobKey]:
    mapping: Dict[str, JobKey] = {}
    for stage_name, task_name, job in document.iter_jobs():
        key = _job_key(stage_name, task_name, job["name"])
        for out_path in job.get("outputs", []):
            mapping[out_path] = key
    return mapping


def get_parent_keys(document: FlowDocument, child_key: JobKey) -> List[JobKey]:
    graph = build_job_graph(document)
    return list(graph.parents.get(child_key, []))


def get_file_parent_keys(document: FlowDocument, child_key: JobKey) -> List[JobKey]:
    found = document.get_job(child_key)
    if not found:
        return []
    producers = _output_producers(document)
    parents: List[JobKey] = []
    seen: Set[JobKey] = set()
    for inp in found[2].get("inputs", []):
        producer = producers.get(inp)
        if producer and producer != child_key and producer not in seen:
            parents.append(producer)
            seen.add(producer)
    return parents


def would_create_cycle(document: FlowDocument, parent_key: JobKey, child_key: JobKey) -> bool:
    if parent_key == child_key:
        return True
    graph = build_job_graph(document)
    stack = [child_key]
    seen: Set[JobKey] = set()
    while stack:
        key = stack.pop()
        if key == parent_key:
            return True
        if key in seen:
            continue
        seen.add(key)
        stack.extend(graph.children.get(key, []))
    return False


def set_job_parents(
    document: FlowDocument,
    child_key: JobKey,
    parent_keys: List[JobKey],
) -> Optional[str]:
    """Set file-based parent jobs by syncing input paths from parent outputs."""
    found = document.get_job(child_key)
    if not found:
        return "Job not found"

    parent_set = set(parent_keys)
    for parent_key in parent_keys:
        if would_create_cycle(document, parent_key, child_key):
            parent = document.get_job(parent_key)
            parent_name = parent[2]["name"] if parent else parent_key
            return f"Cannot link {parent_name!r}: would create a cycle"
        parent = document.get_job(parent_key)
        if parent and not parent[2].get("outputs"):
            return f"Parent job {parent[2]['name']!r} has no outputs — add an output path first"

    _stage, _task, job = found
    producers = _output_producers(document)

    kept_inputs = []
    for inp in job.get("inputs", []):
        producer = producers.get(inp)
        if producer is None or producer in parent_set:
            kept_inputs.append(inp)

    for parent_key in parent_keys:
        parent = document.get_job(parent_key)
        if not parent:
            continue
        for out_path in parent[2].get("outputs", []):
            if out_path not in kept_inputs:
                kept_inputs.append(out_path)

    job["inputs"] = kept_inputs
    return None


def link_jobs(document: FlowDocument, parent_key: JobKey, child_key: JobKey) -> Optional[str]:
    parents = get_file_parent_keys(document, child_key)
    if parent_key in parents:
        return None
    parents.append(parent_key)
    return set_job_parents(document, child_key, parents)


def unlink_jobs(document: FlowDocument, parent_key: JobKey, child_key: JobKey) -> None:
    parents = [key for key in get_file_parent_keys(document, child_key) if key != parent_key]
    set_job_parents(document, child_key, parents)
