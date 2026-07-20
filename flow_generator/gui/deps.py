"""Manual parent/child dependency helpers for the flow editor."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from flow_generator.gui.document import FlowDocument, JobKey, _job_key
from flow_generator.gui.graph import build_job_graph

# Auto-created file markers used only to express job order in the DAG.
# Runner still requires these paths to exist at runtime if left in the flow.
DUMMY_DEP_PREFIX = ".winflow/deps/"
DUMMY_DEP_SUFFIX = ".done"


def is_dummy_dep_path(path: str) -> bool:
    return path.startswith(DUMMY_DEP_PREFIX) and path.endswith(DUMMY_DEP_SUFFIX)


def dummy_output_for(parent_key: JobKey) -> str:
    """Stable dummy output path for a parent job (stage/task/job)."""
    stage, task, name = parent_key.split("\0")
    safe = "/".join(_safe_path_part(p) for p in (stage, task, name))
    return f"{DUMMY_DEP_PREFIX}{safe}{DUMMY_DEP_SUFFIX}"


def _safe_path_part(part: str) -> str:
    cleaned = []
    for ch in part:
        if ch.isalnum() or ch in ("-", "_", "."):
            cleaned.append(ch)
        else:
            cleaned.append("_")
    return "".join(cleaned) or "_"


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
    """Return True if adding file-dep parent→child would form a cycle.

    Uses input/output file links only. Task-order edges are ignored because
    ``link_jobs`` rewrites order via ``place_parent_before_child`` (parent moves
    into the child's stage/task). File adjacency is built from job I/O directly
    (not from the visual graph), since ``build_flow_graph_edges`` keeps at most
    one edge per job pair and may store task-order instead of the file link.
    """
    if parent_key == child_key:
        return True

    producers = _output_producers(document)
    file_children: Dict[JobKey, List[JobKey]] = defaultdict(list)
    for stage_name, task_name, job in document.iter_jobs():
        key = _job_key(stage_name, task_name, job["name"])
        for inp in job.get("inputs", []):
            producer = producers.get(inp)
            if producer and producer != key:
                file_children[producer].append(key)

    stack = [child_key]
    seen: Set[JobKey] = set()
    while stack:
        key = stack.pop()
        if key == parent_key:
            return True
        if key in seen:
            continue
        seen.add(key)
        stack.extend(file_children.get(key, []))
    return False


def ensure_parent_output(document: FlowDocument, parent_key: JobKey) -> Tuple[Optional[str], Optional[str]]:
    """
    Ensure parent has at least one output for file-based linking.

    Returns (dummy_path_or_None, error_or_None).
    When a dummy is created, dummy_path is returned for status messages.
    """
    parent = document.get_job(parent_key)
    if not parent:
        return None, "Parent job not found"

    job = parent[2]
    outputs = list(job.get("outputs", []))
    if outputs:
        return None, None

    dummy = dummy_output_for(parent_key)
    job["outputs"] = [dummy]
    return dummy, None


def _used_input_paths(document: FlowDocument) -> Set[str]:
    used: Set[str] = set()
    for _stage, _task, job in document.iter_jobs():
        used.update(job.get("inputs", []))
    return used


def cleanup_unused_dummy_outputs(document: FlowDocument) -> List[str]:
    """Remove dummy outputs that no job still lists as an input."""
    used = _used_input_paths(document)
    removed: List[str] = []
    for _stage, _task, job in document.iter_jobs():
        outputs = list(job.get("outputs", []))
        kept = []
        for path in outputs:
            if is_dummy_dep_path(path) and path not in used:
                removed.append(path)
                continue
            kept.append(path)
        job["outputs"] = kept
    return removed


def _rewrite_dummy_paths_for_key(
    document: FlowDocument,
    old_key: JobKey,
    new_key: JobKey,
) -> None:
    """Keep auto dummy paths aligned when a job's stage/task key changes."""
    if old_key == new_key:
        return
    old_dummy = dummy_output_for(old_key)
    new_dummy = dummy_output_for(new_key)
    if old_dummy == new_dummy:
        return

    for _stage, _task, job in document.iter_jobs():
        outputs = job.get("outputs", [])
        inputs = job.get("inputs", [])
        job["outputs"] = [new_dummy if path == old_dummy else path for path in outputs]
        job["inputs"] = [new_dummy if path == old_dummy else path for path in inputs]


def place_parent_before_child(
    document: FlowDocument,
    parent_key: JobKey,
    child_key: JobKey,
) -> Tuple[JobKey, JobKey, List[str]]:
    """
    Move parent into the child's stage/task, immediately before child.

    Always merges both jobs into the child's stage so they share task order.
    Returns (new_parent_key, child_key, notes). Child key is unchanged.
    """
    notes: List[str] = []
    parent = document.get_job(parent_key)
    child = document.get_job(child_key)
    if not parent or not child:
        return parent_key, child_key, notes

    parent_stage, _parent_task_name, parent_job = parent
    child_stage, child_task_name, _child_job = child

    parent_loc = document.find_job_index(parent_key)
    child_loc = document.find_job_index(child_key)
    if not parent_loc or not child_loc:
        return parent_key, child_key, notes

    _p_stage, p_task, parent_idx = parent_loc
    _c_stage, c_task, child_idx = child_loc

    # Already in the child's task with parent before child — nothing to move.
    if c_task is p_task and parent_idx < child_idx:
        return parent_key, child_key, notes

    job = p_task["jobs"].pop(parent_idx)
    document._prune_empty()

    child_loc = document.find_job_index(child_key)
    if not child_loc:
        stage = document._ensure_stage(child_stage)
        task = document._ensure_task(stage, child_task_name)
        task["jobs"].insert(0, job)
        new_parent_key = _job_key(child_stage, child_task_name, job["name"])
        document._relocate_key(parent_key, new_parent_key)
        child_pos = document.positions.get(child_key)
        if child_pos is not None:
            document.positions[new_parent_key] = (child_pos[0] - 40.0, child_pos[1] - 48.0)
        _rewrite_dummy_paths_for_key(document, parent_key, new_parent_key)
        notes.append(f"moved {parent_job['name']} into stage {child_stage!r} (follow child)")
        return new_parent_key, child_key, notes

    stage, dest_task, child_idx = child_loc
    dest_task["jobs"].insert(child_idx, job)
    new_parent_key = _job_key(stage["name"], dest_task["name"], job["name"])
    document._relocate_key(parent_key, new_parent_key)
    # Keep parent visually with the child so canvas stage order stays coherent.
    child_pos = document.positions.get(child_key)
    if child_pos is not None:
        document.positions[new_parent_key] = (child_pos[0] - 40.0, child_pos[1] - 48.0)
    if new_parent_key != parent_key:
        _rewrite_dummy_paths_for_key(document, parent_key, new_parent_key)
        if parent_stage != stage["name"]:
            notes.append(
                f"moved {parent_job['name']} into stage {stage['name']!r} (follow child)"
            )
        else:
            notes.append(f"moved {parent_job['name']} into task {dest_task['name']!r}")
    else:
        notes.append(f"ordered {parent_job['name']} before child")
    return new_parent_key, child_key, notes


def place_child_after_parent(
    document: FlowDocument,
    parent_key: JobKey,
    child_key: JobKey,
) -> Tuple[JobKey, List[str]]:
    """Deprecated wrapper — linking now follows the child's stage."""
    _new_parent_key, new_child_key, notes = place_parent_before_child(
        document, parent_key, child_key
    )
    return new_child_key, notes


def break_task_order(
    document: FlowDocument,
    parent_key: JobKey,
    child_key: JobKey,
) -> Tuple[Dict[JobKey, JobKey], List[str]]:
    """
    If parent and child share a task and parent is before child, split the task
    so child (and following jobs) run in a new parallel task.

    Returns (renamed_keys, notes).
    """
    notes: List[str] = []
    renames: Dict[JobKey, JobKey] = {}
    parent = document.get_job(parent_key)
    child = document.get_job(child_key)
    if not parent or not child:
        return renames, notes

    parent_stage, parent_task, _ = parent
    child_stage, child_task, child_job = child
    if parent_stage != child_stage or parent_task != child_task:
        return renames, notes

    located = document.find_job_index(child_key)
    parent_loc = document.find_job_index(parent_key)
    if not located or not parent_loc:
        return renames, notes

    stage, task, child_idx = located
    _ps, _pt, parent_idx = parent_loc
    if parent_idx >= child_idx:
        return renames, notes

    # Split: keep jobs before child; move child..end into a new parallel task.
    moving = list(task["jobs"][child_idx:])
    if not moving:
        return renames, notes

    task["jobs"] = list(task["jobs"][:child_idx])
    new_task_name = document._unique_task_name(stage, f"task_{child_job['name']}")
    new_task = {"name": new_task_name, "jobs": moving}
    # Insert the new task right after the original task for readability.
    task_index = stage["tasks"].index(task)
    stage["tasks"].insert(task_index + 1, new_task)

    for job in moving:
        old_key = _job_key(parent_stage, parent_task, job["name"])
        new_key = _job_key(parent_stage, new_task_name, job["name"])
        document._relocate_key(old_key, new_key)
        _rewrite_dummy_paths_for_key(document, old_key, new_key)
        renames[old_key] = new_key

    document._prune_empty()
    notes.append(
        f"split task {parent_task!r} → {new_task_name!r} "
        f"(no longer sequential after parent)"
    )
    return renames, notes


def set_job_parents(
    document: FlowDocument,
    child_key: JobKey,
    parent_keys: List[JobKey],
) -> Optional[str]:
    """Set file-based parent jobs by syncing input paths from parent outputs.

    Parents with no outputs automatically get a dummy `.winflow/deps/...done`
    marker so link/unlink works without manually editing I/O first.
    """
    found = document.get_job(child_key)
    if not found:
        return "Job not found"

    parent_set = set(parent_keys)
    for parent_key in parent_keys:
        if would_create_cycle(document, parent_key, child_key):
            parent = document.get_job(parent_key)
            parent_name = parent[2]["name"] if parent else parent_key
            return f"Cannot link {parent_name!r}: would create a cycle"
        _dummy, err = ensure_parent_output(document, parent_key)
        if err:
            return err

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
    cleanup_unused_dummy_outputs(document)
    return None


def link_jobs(
    document: FlowDocument,
    parent_key: JobKey,
    child_key: JobKey,
) -> Tuple[Optional[str], JobKey, List[str]]:
    """
    Link parent → child with file dependency and task ordering.

    Parent is always moved into the child's stage/task (immediately before the
    child) so both share sequential runner order.

    Returns (error_or_None, new_child_key, notes).
    """
    notes: List[str] = []
    if parent_key == child_key:
        return "Cannot link a job to itself", child_key, notes
    if not document.get_job(parent_key) or not document.get_job(child_key):
        return "Job not found", child_key, notes
    if would_create_cycle(document, parent_key, child_key):
        parent = document.get_job(parent_key)
        parent_name = parent[2]["name"] if parent else parent_key
        return f"Cannot link {parent_name!r}: would create a cycle", child_key, notes

    new_parent_key, new_child_key, move_notes = place_parent_before_child(
        document, parent_key, child_key
    )
    notes.extend(move_notes)

    if not document.get_job(new_parent_key):
        return "Parent job not found after move", new_child_key, notes

    parents = [
        key
        for key in get_file_parent_keys(document, new_child_key)
        if key not in (parent_key, new_parent_key)
    ]
    parents.append(new_parent_key)
    err = set_job_parents(document, new_child_key, parents)
    if err:
        return err, new_child_key, notes

    parent = document.get_job(new_parent_key)
    if parent and any(is_dummy_dep_path(p) for p in parent[2].get("outputs", [])):
        if any(
            is_dummy_dep_path(p)
            for p in (document.get_job(new_child_key) or (None, None, {}))[2].get("inputs", [])
        ):
            notes.append("added dummy file dependency")

    return None, new_child_key, notes


def unlink_jobs(
    document: FlowDocument,
    parent_key: JobKey,
    child_key: JobKey,
) -> Tuple[JobKey, List[str]]:
    """
    Remove file dependency and break same-task sequential order if present.

    Returns (new_child_key, notes).
    """
    notes: List[str] = []
    if not document.get_job(parent_key) or not document.get_job(child_key):
        return child_key, notes

    parents = [key for key in get_file_parent_keys(document, child_key) if key != parent_key]
    had_file = parent_key in get_file_parent_keys(document, child_key)
    set_job_parents(document, child_key, parents)
    if had_file:
        notes.append("removed file dependency")

    renames, split_notes = break_task_order(document, parent_key, child_key)
    notes.extend(split_notes)
    new_child_key = renames.get(child_key, child_key)
    return new_child_key, notes
