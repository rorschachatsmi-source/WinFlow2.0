"""
Shared flow graph construction and execution semantics.

Used by flow_runner_gui (DAG view) and flow_generator_gui (canvas).

Execution model (flow_runner_core.FlowRunner)
------------------------------------------
- **Stages** run sequentially, in JSON list order.
- **Tasks** within a stage run in parallel (one thread per task).
- **Jobs** within a task run sequentially, in JSON list order.
- **Inputs/outputs** do NOT schedule jobs. Before each job starts, the runner
  only checks that every input path already exists on disk. Cross-task file
  dependencies are not waited on automatically.

Graph edges (visual / documentation only for scheduling)
--------------------------------------------------------
1. **Task order** — consecutive jobs in the same task (enforced by runner).
2. **File link** — child's input matches parent's output path (runner validates
   file exists at job start; does not wait for producer job).
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Callable, Dict, List, Optional, Set, Tuple

EDGE_TASK_ORDER = "(task order)"

JobKey = str
JobEdge = Tuple[JobKey, JobKey, str]


def default_job_key(stage_name: str, task_name: str, job_name: str) -> str:
    return f"{stage_name}/{task_name}/{job_name}"


def build_flow_graph_edges(
    stages: List[dict],
    key_fn: Callable[[str, str, str], JobKey] = default_job_key,
) -> List[JobEdge]:
    """
    Build job edges the same way as flow_runner_gui.FlowGraphModel.

    Returns list of (parent_key, child_key, label).
    """
    edges: List[JobEdge] = []
    edge_pairs: Set[Tuple[JobKey, JobKey]] = set()
    output_producers: Dict[str, JobKey] = {}
    prev_in_task: Dict[Tuple[str, str], JobKey] = {}

    for stage in stages:
        stage_name = stage["name"]
        for task in stage.get("tasks", []):
            task_name = task["name"]
            task_id = (stage_name, task_name)

            for job in task.get("jobs", []):
                job_name = job["name"]
                key = key_fn(stage_name, task_name, job_name)

                prev_key = prev_in_task.get(task_id)
                if prev_key:
                    _add_edge(edges, edge_pairs, prev_key, key, EDGE_TASK_ORDER)
                prev_in_task[task_id] = key

                for inp in job.get("inputs", []):
                    producer = output_producers.get(inp)
                    if producer and producer != key:
                        _add_edge(edges, edge_pairs, producer, key, inp)

                for out in job.get("outputs", []):
                    output_producers[out] = key

    return edges


def _add_edge(
    edges: List[JobEdge],
    seen: Set[Tuple[JobKey, JobKey]],
    src: JobKey,
    dst: JobKey,
    label: str,
) -> None:
    # One edge per (src, dst) pair — task-order wins over file link when both apply.
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
    return [src for src, dst, label in edges if dst == child_key and label != EDGE_TASK_ORDER]


def task_order_parent_key(edges: List[JobEdge], child_key: JobKey) -> Optional[JobKey]:
    for src, dst, label in edges:
        if dst == child_key and label == EDGE_TASK_ORDER:
            return src
    return None
