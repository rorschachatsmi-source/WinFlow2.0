"""Tests for shared flow graph + runner alignment."""

import unittest

from flow_graph import EDGE_TASK_ORDER, build_flow_graph_edges, default_job_key


class TestFlowGraph(unittest.TestCase):
    def test_task_order_and_file_edges(self):
        stages = [
            {
                "name": "s1",
                "tasks": [
                    {
                        "name": "t1",
                        "jobs": [
                            {"name": "j1", "inputs": [], "outputs": ["a.txt"]},
                            {"name": "j2", "inputs": ["a.txt"], "outputs": ["b.txt"]},
                        ],
                    }
                ],
            },
            {
                "name": "s2",
                "tasks": [
                    {
                        "name": "t2",
                        "jobs": [
                            {"name": "j3", "inputs": ["b.txt"], "outputs": []},
                        ],
                    }
                ],
            },
        ]
        edges = build_flow_graph_edges(stages)
        j1 = default_job_key("s1", "t1", "j1")
        j2 = default_job_key("s1", "t1", "j2")
        j3 = default_job_key("s2", "t2", "j3")
        self.assertIn((j1, j2, EDGE_TASK_ORDER), edges)
        self.assertIn((j2, j3, "b.txt"), edges)

    def test_runner_and_generator_keys_differ_only_by_separator(self):
        stages = [
            {
                "name": "APR",
                "tasks": [
                    {
                        "name": "apr",
                        "jobs": [
                            {"name": "j1", "inputs": [], "outputs": ["x"]},
                            {"name": "j2", "inputs": ["x"], "outputs": []},
                        ],
                    }
                ],
            }
        ]
        runner_edges = build_flow_graph_edges(stages, key_fn=default_job_key)
        doc_key = lambda s, t, n: f"{s}\0{t}\0{n}"
        gen_edges = build_flow_graph_edges(stages, key_fn=doc_key)
        self.assertEqual(len(runner_edges), len(gen_edges))
        for (_rs, _rd, label), (gs, gd, gl) in zip(runner_edges, gen_edges):
            self.assertEqual(label, gl)
            self.assertEqual(gs.replace("\0", "/"), _rs)
            self.assertEqual(gd.replace("\0", "/"), _rd)


if __name__ == "__main__":
    unittest.main()
