"""
Shared flow graph construction and execution semantics.

Used by flow_runner_gui (DAG view) and flow_generator_gui (canvas).

Execution model (flow_runner_core.FlowRunner)
------------------------------------------
- Jobs schedule solely from each job's ``parents`` / ``children`` attributes
  (job keys ``stage/task/job``). A job becomes ready when all parents are DONE
  (or skipped via job_filter); ready jobs may run in parallel.
- Stage/task nesting remains for identity, logging, and editor tags only.
- **Inputs/outputs** do NOT schedule jobs. Before each job starts, the runner
  checks that every input path already exists on disk.

Editor / layout
---------------
- Canvas edges and auto-layout layers come from ``parents`` / ``children``.
- ``annotate_job_relations`` seeds those fields from task-order + file I/O when
  missing (migration / first generate). Link/unlink then edit the attributes.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Callable, Dict, List, Optional, Set, Tuple

EDGE_TASK_ORDER = "(task order)"
EDGE_PARENT = "(parent)"

JobKey = str
JobEdge = Tuple[JobKey, JobKey, str]


def default_job_key(stage_name: str, task_name: str, job_name: str) -> JobKey:
    return f"{stage_name}/{task_name}/{job_name}"


def gui_job_key(stage_name: str, task_name: str, job_name: str) -> JobKey:
    return f"{stage_name}\0{task_name}\0{job_name}"


def slash_to_key(
    slash_key: str,
    key_fn: Callable[[str, str, str], JobKey] = default_job_key,
) -> JobKey:
    """Convert stored slash key ``stage/task/job`` to a display key."""
    parts = slash_key.split("/", 2)
    if len(parts) != 3:
        return slash_key
    return key_fn(parts[0], parts[1], parts[2])


def key_to_slash(key: JobKey) -> str:
    """Convert a display key (slash or NUL-separated) to stored slash form."""
    if "\0" in key:
        return key.replace("\0", "/")
    return key


def rewrite_relation_key_refs(stages: List[dict], old_slash: str, new_slash: str) -> None:
    """Rewrite parents/children entries after a job identity (stage/task) changes."""
    if old_slash == new_slash:
        return
    for _key, job in iter_jobs(stages):
        if "parents" in job:
            job["parents"] = [new_slash if p == old_slash else p for p in (job.get("parents") or [])]
        if "children" in job:
            job["children"] = [new_slash if c == old_slash else c for c in (job.get("children") or [])]


def build_flow_graph_edges(
    stages: List[dict],
    key_fn: Callable[[str, str, str], JobKey] = default_job_key,
) -> List[JobEdge]:
    """
    Derive edges from task-order + file I/O (migration / annotation source).

    Returns list of (parent_key, child_key, label).
    """
    edges: List[JobEdge] = []
    edge_pairs: Set[Tuple[JobKey, JobKey]] = set()
    output_producers: Dict[str, JobKey] = {}
    prev_in_task: Dict[Tuple[str, str], JobKey] = {}
    jobs: List[Tuple[JobKey, dict]] = []

    for stage in stages:
        stage_name = stage["name"]
        for task in stage.get("tasks", []):
            task_name = task["name"]
            task_id = (stage_name, task_name)

            for job in task.get("jobs", []):
                job_name = job["name"]
                key = key_fn(stage_name, task_name, job_name)
                jobs.append((key, job))

                prev_key = prev_in_task.get(task_id)
                if prev_key:
                    _add_edge(edges, edge_pairs, prev_key, key, EDGE_TASK_ORDER)
                prev_in_task[task_id] = key

                for out in job.get("outputs", []):
                    output_producers[out] = key

    for key, job in jobs:
        for inp in job.get("inputs", []):
            producer = output_producers.get(inp)
            if producer and producer != key:
                _add_edge(edges, edge_pairs, producer, key, inp)

    return edges


def build_relation_edges(
    stages: List[dict],
    key_fn: Callable[[str, str, str], JobKey] = default_job_key,
) -> List[JobEdge]:
    """
    Build edges solely from each job's parents/children attributes.

    Stored relation keys are always ``stage/task/job`` (slash). ``key_fn`` only
    affects keys in the returned edge tuples (e.g. GUI NUL separator).
    """
    edges: List[JobEdge] = []
    edge_pairs: Set[Tuple[JobKey, JobKey]] = set()
    jobs = iter_jobs(stages, default_job_key)
    job_by_slash = {key: job for key, job in jobs}

    for slash, job in jobs:
        dst = slash_to_key(slash, key_fn)
        parent_outs = set()
        for parent_slash in job.get("parents") or []:
            if parent_slash not in job_by_slash:
                continue
            src = slash_to_key(parent_slash, key_fn)
            label = EDGE_PARENT
            parent_job = job_by_slash[parent_slash]
            parent_outs = set(parent_job.get("outputs") or [])
            for inp in job.get("inputs") or []:
                if inp in parent_outs:
                    label = inp
                    break
            _add_edge(edges, edge_pairs, src, dst, label)
    return edges


def _add_edge(
    edges: List[JobEdge],
    seen: Set[Tuple[JobKey, JobKey]],
    src: JobKey,
    dst: JobKey,
    label: str,
) -> None:
    pair = (src, dst)
    if pair in seen:
        return
    seen.add(pair)
    edges.append((src, dst, label))


def edges_to_adjacency(edges: List[JobEdge]) -> Tuple[Dict[JobKey, List[JobKey]], Dict[JobKey, List[JobKey]]]:
    parents: Dict[JobKey, List[JobKey]] = defaultdict(list)
    children: Dict[JobKey, List[JobKey]] = defaultdict(list)
    for src, dst, _label in edges:
        parents[dst].append(src)
        children[src].append(dst)
    return parents, children


def compute_layers(keys: List[JobKey], edges: List[JobEdge]) -> Dict[JobKey, int]:
    in_degree = {key: 0 for key in keys}
    adj: Dict[JobKey, List[JobKey]] = defaultdict(list)

    for src, dst, _label in edges:
        if src not in in_degree or dst not in in_degree:
            continue
        adj[src].append(dst)
        in_degree[dst] += 1

    queue = deque(key for key, degree in in_degree.items() if degree == 0)
    layer_of: Dict[JobKey, int] = {}
    layers: Dict[JobKey, int] = {}

    while queue:
        key = queue.popleft()
        layer = layer_of.get(key, 0)
        layers[key] = layer
        for nxt in adj[key]:
            layer_of[nxt] = max(layer_of.get(nxt, 0), layer + 1)
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    for key in keys:
        layers.setdefault(key, 0)
    return layers


def file_parent_keys(edges: List[JobEdge], child_key: JobKey) -> List[JobKey]:
    return [
        src
        for src, dst, label in edges
        if dst == child_key and label not in (EDGE_TASK_ORDER, EDGE_PARENT)
    ]


def task_order_parent_key(edges: List[JobEdge], child_key: JobKey) -> Optional[JobKey]:
    for src, dst, label in edges:
        if dst == child_key and label == EDGE_TASK_ORDER:
            return src
    return None


def iter_jobs(
    stages: List[dict],
    key_fn: Callable[[str, str, str], JobKey] = default_job_key,
) -> List[Tuple[JobKey, dict]]:
    """Flatten stages into (job_key, job_dict) pairs in document order."""
    jobs: List[Tuple[JobKey, dict]] = []
    for stage in stages:
        stage_name = stage["name"]
        for task in stage.get("tasks", []):
            task_name = task["name"]
            for job in task.get("jobs", []):
                jobs.append((key_fn(stage_name, task_name, job["name"]), job))
    return jobs


def jobs_need_relation_annotation(stages: List[dict]) -> bool:
    """True if any job is missing parents or children fields."""
    for _key, job in iter_jobs(stages):
        if "parents" not in job or "children" not in job:
            return True
    return False


def ensure_job_relations(stages: List[dict]) -> List[dict]:
    """Annotate parents/children from task-order + file I/O when missing."""
    if jobs_need_relation_annotation(stages):
        annotate_job_relations(stages)
    return stages


def strip_job_relations(stages: List[dict]) -> List[dict]:
    """Remove parents/children from jobs (e.g. node-library templates)."""
    for _key, job in iter_jobs(stages):
        job.pop("parents", None)
        job.pop("children", None)
    return stages


def annotate_job_relations(
    stages: List[dict],
    key_fn: Callable[[str, str, str], JobKey] = default_job_key,
) -> List[dict]:
    """
    Derive parents/children from task-order + file I/O and write slash keys
    onto every job. Always persists ``stage/task/job`` keys for the runner.
    """
    # Ignore key_fn for storage — runner identity is always slash-separated.
    _ = key_fn
    jobs = iter_jobs(stages, default_job_key)
    parents_map, children_map = edges_to_adjacency(
        build_flow_graph_edges(stages, default_job_key)
    )
    for key, job in jobs:
        job["parents"] = list(dict.fromkeys(parents_map.get(key, [])))
        job["children"] = list(dict.fromkeys(children_map.get(key, [])))
    return stages


def validate_job_relations(
    stages: List[dict],
    key_fn: Callable[[str, str, str], JobKey] = default_job_key,
) -> Optional[str]:
    """
    Validate parents/children consistency.

    Returns an error message, or None if valid.
    """
    _ = key_fn
    jobs = iter_jobs(stages, default_job_key)
    key_set: Set[JobKey] = {key for key, _ in jobs}

    if len(key_set) != len(jobs):
        return "Duplicate job keys found in flow"

    parents_of: Dict[JobKey, List[JobKey]] = {}
    children_of: Dict[JobKey, List[JobKey]] = {}

    for key, job in jobs:
        parents = list(job.get("parents") or [])
        children = list(job.get("children") or [])
        parents_of[key] = parents
        children_of[key] = children

        for p in parents:
            if p not in key_set:
                return f"Unknown parent key {p!r} referenced by {key!r}"
        for c in children:
            if c not in key_set:
                return f"Unknown child key {c!r} referenced by {key!r}"

    for key, children in children_of.items():
        for child in children:
            if key not in parents_of.get(child, []):
                return (
                    f"Inconsistent relation: {key!r} lists child {child!r}, "
                    f"but {child!r} does not list {key!r} as parent"
                )
    for key, parents in parents_of.items():
        for parent in parents:
            if key not in children_of.get(parent, []):
                return (
                    f"Inconsistent relation: {key!r} lists parent {parent!r}, "
                    f"but {parent!r} does not list {key!r} as child"
                )

    in_degree = {key: len(parents_of[key]) for key in key_set}
    queue = deque(key for key, deg in in_degree.items() if deg == 0)
    seen = 0
    while queue:
        key = queue.popleft()
        seen += 1
        for child in children_of[key]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if seen != len(key_set):
        return "Cycle detected in parents/children graph"

    return None
