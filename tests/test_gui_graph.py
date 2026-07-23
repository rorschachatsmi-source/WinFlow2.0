"""Tests for flow editor job dependency graph."""

import unittest

from flow_generator.core.models import make_flow, make_job, make_stage, make_task
from flow_generator.gui.document import FlowDocument, _job_key, flow_to_document
from flow_generator.gui.graph import build_job_graph


class TestJobGraph(unittest.TestCase):
    def test_builds_edges_from_parents_children(self):
        flow = make_flow(
            "demo",
            [
                make_stage(
                    "s1",
                    [
                        make_task(
                            "t1",
                            [
                                make_job("j1", "cmd1", [], ["a.txt"], "q", 1),
                                make_job("j2", "cmd2", ["a.txt"], ["b.txt"], "q", 1),
                            ],
                        )
                    ],
                ),
                make_stage(
                    "s2",
                    [
                        make_task(
                            "t2",
                            [
                                make_job("j3", "cmd3", ["b.txt"], [], "q", 1),
                            ],
                        )
                    ],
                ),
            ],
        )
        doc = flow_to_document(flow)
        graph = build_job_graph(doc)
        j1 = _job_key("s1", "t1", "j1")
        j2 = _job_key("s1", "t1", "j2")
        j3 = _job_key("s2", "t2", "j3")
        self.assertIn(j1, graph.parents.get(j2, []))
        self.assertIn(j2, graph.parents.get(j3, []))
        # Layout layers follow parent depth.
        self.assertEqual(graph.layers[j1], 0)
        self.assertEqual(graph.layers[j2], 1)
        self.assertEqual(graph.layers[j3], 2)

    def test_task_order_seeded_into_parents_children(self):
        flow = make_flow(
            "demo",
            [
                make_stage(
                    "s1",
                    [
                        make_task(
                            "t1",
                            [
                                make_job("j1", "cmd1", [], ["a.txt"], "q", 1),
                                make_job("j2", "cmd2", [], ["b.txt"], "q", 1),
                            ],
                        )
                    ],
                )
            ],
        )
        doc = flow_to_document(flow)
        graph = build_job_graph(doc)
        j1 = _job_key("s1", "t1", "j1")
        j2 = _job_key("s1", "t1", "j2")
        self.assertIn(j1, graph.parents.get(j2, []))
        # Edge label may be EDGE_PARENT when no shared file path on the relation.
        self.assertTrue(any(src == j1 and dst == j2 for src, dst, _ in graph.edges))

    def test_position_changes_preserve_job_order_and_edges(self):
        from flow_generator.flows.apr.builder import build_apr_stage

        stage = build_apr_stage(prefix="top", is_current=True)
        doc = FlowDocument(flow_name="APR", stages=[stage])
        original_names = [job["name"] for job in stage["tasks"][0]["jobs"]]
        graph_before = build_job_graph(doc)

        keys = [_job_key("APR", "apr", name) for name in original_names]
        for index, key in enumerate(keys):
            doc.positions[key] = (500 - index * 80, index * 120)

        names_after = [job["name"] for job in doc.stages[0]["tasks"][0]["jobs"]]
        graph_after = build_job_graph(doc)

        self.assertEqual(names_after, original_names)
        self.assertEqual(graph_before.edges, graph_after.edges)


class TestUpdateJob(unittest.TestCase):
    def test_update_preserves_task_order(self):
        doc = FlowDocument(
            stages=[
                make_stage(
                    "s1",
                    [
                        make_task(
                            "t1",
                            [
                                make_job("j1", "c1", [], [], "q", 1),
                                make_job("j2", "c2", [], [], "q", 1),
                                make_job("j3", "c3", [], [], "q", 1),
                            ],
                        )
                    ],
                )
            ]
        )
        key = _job_key("s1", "t1", "j2")
        doc.positions[key] = (100, 200)
        updated = make_job("j2_edited", "c2-new", [], [], "q", 2)
        new_key = doc.update_job(key, "s1", "t1", updated)
        names = [job["name"] for job in doc.stages[0]["tasks"][0]["jobs"]]
        self.assertEqual(names, ["j1", "j2_edited", "j3"])
        self.assertEqual(doc.positions[new_key], (100, 200))


if __name__ == "__main__":
    unittest.main()
