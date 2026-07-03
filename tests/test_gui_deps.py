"""Tests for manual job dependency editing."""

import unittest

from flow_generator.core.models import make_job, make_stage, make_task
from flow_generator.flows.apr.builder import build_apr_stage
from flow_generator.gui.deps import (
    get_file_parent_keys,
    get_parent_keys,
    link_jobs,
    set_job_parents,
    unlink_jobs,
    would_create_cycle,
)
from flow_generator.gui.document import FlowDocument, _job_key
from flow_generator.gui.graph import build_job_graph


class TestJobDeps(unittest.TestCase):
    def _apr_doc(self) -> FlowDocument:
        return FlowDocument(flow_name="APR", stages=[build_apr_stage(prefix="top")])

    def test_link_and_unlink_jobs(self):
        doc = self._apr_doc()
        jobs = [job["name"] for _s, _t, job in doc.iter_jobs()]
        parent = _job_key("APR", "apr", jobs[0])
        child = _job_key("APR", "apr", jobs[1])

        self.assertIsNone(link_jobs(doc, parent, child))
        self.assertIn(parent, get_file_parent_keys(doc, child))
        parent_out = doc.get_job(parent)[2]["outputs"][0]
        self.assertIn(parent_out, doc.get_job(child)[2]["inputs"])

        unlink_jobs(doc, parent, child)
        self.assertNotIn(parent, get_file_parent_keys(doc, child))
        # Consecutive jobs in the same task still have a task-order parent.
        self.assertIn(parent, get_parent_keys(doc, child))

    def test_set_job_parents_multiple(self):
        doc = self._apr_doc()
        names = [job["name"] for _s, _t, job in doc.iter_jobs()]
        j0, j1, j2 = [_job_key("APR", "apr", n) for n in names[:3]]
        self.assertIsNone(set_job_parents(doc, j2, [j0, j1]))
        parents = get_file_parent_keys(doc, j2)
        self.assertEqual(set(parents), {j0, j1})

    def test_rejects_cycle(self):
        doc = FlowDocument(
            stages=[
                make_stage(
                    "s1",
                    [
                        make_task(
                            "t1",
                            [
                                make_job("a", "ca", [], ["x.txt"], "q", 1),
                                make_job("b", "cb", ["x.txt"], ["y.txt"], "q", 1),
                                make_job("c", "cc", ["y.txt"], [], "q", 1),
                            ],
                        )
                    ],
                )
            ]
        )
        a = _job_key("s1", "t1", "a")
        c = _job_key("s1", "t1", "c")
        self.assertTrue(would_create_cycle(doc, c, a))
        self.assertIsNotNone(link_jobs(doc, c, a))

    def test_parent_requires_outputs(self):
        doc = FlowDocument(
            stages=[
                make_stage(
                    "s1",
                    [make_task("t1", [make_job("a", "ca", [], [], "q", 1), make_job("b", "cb", [], ["o.txt"], "q", 1)])],
                )
            ],
        )
        a = _job_key("s1", "t1", "a")
        b = _job_key("s1", "t1", "b")
        err = link_jobs(doc, a, b)
        self.assertIn("no outputs", err or "")

    def test_graph_reflects_manual_link(self):
        doc = self._apr_doc()
        names = [job["name"] for _s, _t, job in doc.iter_jobs()]
        parent = _job_key("APR", "apr", names[0])
        child = _job_key("APR", "apr", names[2])
        link_jobs(doc, parent, child)
        graph = build_job_graph(doc)
        self.assertIn(parent, graph.parents.get(child, []))


if __name__ == "__main__":
    unittest.main()
