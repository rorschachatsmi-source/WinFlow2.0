"""Job dependency graph for the flow editor canvas."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from flow_graph import (
    EDGE_PARENT,
    EDGE_TASK_ORDER,
    build_relation_edges,
    compute_layers,
    ensure_job_relations,
)
from flow_generator.gui.document import FlowDocument, JobKey, _job_key


@dataclass
class JobGraph:
    edges: List[Tuple[JobKey, JobKey, str]] = field(default_factory=list)
    parents: Dict[JobKey, List[JobKey]] = field(default_factory=lambda: defaultdict(list))
    children: Dict[JobKey, List[JobKey]] = field(default_factory=lambda: defaultdict(list))
    layers: Dict[JobKey, int] = field(default_factory=dict)

    def edge_set(self) -> Set[Tuple[JobKey, JobKey]]:
        return {(src, dst) for src, dst, _label in self.edges}

    def file_edges(self) -> List[Tuple[JobKey, JobKey, str]]:
        return [
            (s, d, label)
            for s, d, label in self.edges
            if label not in (EDGE_TASK_ORDER, EDGE_PARENT)
        ]

    def task_order_edges(self) -> List[Tuple[JobKey, JobKey]]:
        # Kept for compatibility; editor graph no longer invents task-order edges.
        return [(s, d) for s, d, label in self.edges if label == EDGE_TASK_ORDER]


def build_job_graph(document: FlowDocument) -> JobGraph:
    """Build canvas graph from job parents/children (seeded if missing)."""
    ensure_job_relations(document.stages)
    graph = JobGraph()
    graph.edges = build_relation_edges(document.stages, key_fn=_job_key)

    for src, dst, _label in graph.edges:
        graph.parents[dst].append(src)
        graph.children[src].append(dst)

    keys = [
        _job_key(stage["name"], task["name"], job["name"])
        for stage in document.stages
        for task in stage["tasks"]
        for job in task["jobs"]
    ]
    graph.layers = compute_layers(keys, graph.edges)
    return graph


def layout_by_graph(document: FlowDocument, graph: JobGraph, col_gap: int = 240, row_gap: int = 100) -> None:
    """Place jobs by parent/child layer (left = roots, right = deeper dependents)."""
    by_layer: Dict[int, List[JobKey]] = defaultdict(list)
    for key, layer in graph.layers.items():
        by_layer[layer].append(key)

    for layer_idx in sorted(by_layer):
        keys = by_layer[layer_idx]
        keys.sort(key=lambda k: document.positions.get(k, (0, 9999))[1])
        x = 100 + layer_idx * col_gap
        for row, key in enumerate(keys):
            document.positions[key] = (x, 80 + row * row_gap)
