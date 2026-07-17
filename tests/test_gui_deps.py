"""Tests for manual job dependency editing."""

import unittest

from flow_graph import EDGE_TASK_ORDER
from flow_generator.core.models import make_job, make_stage, make_task
from flow_generator.flows.apr.builder import build_apr_stage
from flow_generator.gui.deps import (
    break_task_order,
    cleanup_unused_dummy_outputs,
    dummy_output_for,
    get_file_parent_keys,
    get_parent_keys,
    is_dummy_dep_path,
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

        err, child, _notes = link_jobs(doc, parent, child)
        self.assertIsNone(err)
        self.assertIn(parent, get_file_parent_keys(doc, child))
        parent_out = doc.get_job(parent)[2]["outputs"][0]
        self.assertIn(parent_out, doc.get_job(child)[2]["inputs"])

        child, _notes = unlink_jobs(doc, parent, child)
        self.assertNotIn(parent, get_file_parent_keys(doc, child))
        # Unlink splits the task, so task-order parent should be gone too.
        self.assertNotIn(parent, get_parent_keys(doc, child))

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
        err, _key, _notes = link_jobs(doc, c, a)
        self.assertIsNotNone(err)

    def test_link_creates_dummy_outputs_when_missing(self):
        doc = FlowDocument(
            stages=[
                make_stage(
                    "s1",
                    [
                        make_task(
                            "t1",
                            [
                                make_job("a", "ca", [], [], "q", 1),
                                make_job("b", "cb", [], [], "q", 1),
                            ],
                        )
                    ],
                )
            ],
        )
        a = _job_key("s1", "t1", "a")
        b = _job_key("s1", "t1", "b")
        err, b, _notes = link_jobs(doc, a, b)
        self.assertIsNone(err)

        dummy = dummy_output_for(a)
        self.assertTrue(is_dummy_dep_path(dummy))
        self.assertEqual(doc.get_job(a)[2]["outputs"], [dummy])
        self.assertIn(dummy, doc.get_job(b)[2]["inputs"])
        self.assertIn(a, get_file_parent_keys(doc, b))

    def test_unlink_removes_unused_dummy_outputs(self):
        doc = FlowDocument(
            stages=[
                make_stage(
                    "s1",
                    [
                        make_task(
                            "t1",
                            [
                                make_job("a", "ca", [], [], "q", 1),
                                make_job("b", "cb", [], [], "q", 1),
                            ],
                        )
                    ],
                )
            ],
        )
        a = _job_key("s1", "t1", "a")
        b = _job_key("s1", "t1", "b")
        err, b, _notes = link_jobs(doc, a, b)
        self.assertIsNone(err)
        dummy = dummy_output_for(a)
        self.assertIn(dummy, doc.get_job(a)[2]["outputs"])

        b, _notes = unlink_jobs(doc, a, b)
        self.assertNotIn(dummy, doc.get_job(b)[2]["inputs"])
        self.assertNotIn(dummy, doc.get_job(a)[2]["outputs"])
        self.assertEqual(cleanup_unused_dummy_outputs(doc), [])

    def test_dummy_kept_when_shared_by_another_child(self):
        doc = FlowDocument(
            stages=[
                make_stage(
                    "s1",
                    [
                        make_task("t1", [make_job("a", "ca", [], [], "q", 1)]),
                        make_task("t2", [make_job("b", "cb", [], [], "q", 1)]),
                        make_task("t3", [make_job("c", "cc", [], [], "q", 1)]),
                    ],
                )
            ],
        )
        a = _job_key("s1", "t1", "a")
        b = _job_key("s1", "t2", "b")
        c = _job_key("s1", "t3", "c")
        err, b, _notes = link_jobs(doc, a, b)
        self.assertIsNone(err)
        a = _job_key("s1", "t2", "a")  # parent followed b
        err, c, _notes = link_jobs(doc, a, c)
        self.assertIsNone(err)
        a = _job_key("s1", "t3", "a")  # parent followed c
        dummy = dummy_output_for(a)
        # Dummy path rewrite keeps b's input aligned with the relocated parent.
        self.assertIn(dummy, doc.get_job(b)[2]["inputs"])
        self.assertIn(dummy, doc.get_job(c)[2]["inputs"])

        c, _notes = unlink_jobs(doc, a, c)
        self.assertIn(dummy, doc.get_job(a)[2]["outputs"])
        self.assertIn(dummy, doc.get_job(b)[2]["inputs"])

    def test_unlink_breaks_task_order_without_file_dep(self):
        doc = FlowDocument(
            stages=[
                make_stage(
                    "s1",
                    [
                        make_task(
                            "t1",
                            [
                                make_job("a", "ca", [], ["x.txt"], "q", 1),
                                make_job("b", "cb", [], ["y.txt"], "q", 1),
                                make_job("c", "cc", [], ["z.txt"], "q", 1),
                            ],
                        )
                    ],
                )
            ],
        )
        a = _job_key("s1", "t1", "a")
        b = _job_key("s1", "t1", "b")
        graph = build_job_graph(doc)
        self.assertIn((a, b, EDGE_TASK_ORDER), graph.edges)

        new_b, notes = unlink_jobs(doc, a, b)
        self.assertTrue(any("split" in n for n in notes))
        self.assertIsNotNone(doc.get_job(new_b))
        graph = build_job_graph(doc)
        self.assertNotIn(a, graph.parents.get(new_b, []))
        # c stays with b after the split point
        new_c = _job_key("s1", new_b.split("\0")[1], "c")
        self.assertIsNotNone(doc.get_job(new_c))

    def test_link_merges_into_child_task(self):
        """Parent moves into the child's task (follow child)."""
        doc = FlowDocument(
            stages=[
                make_stage(
                    "s1",
                    [
                        make_task("t1", [make_job("a", "ca", [], [], "q", 1)]),
                        make_task("t2", [make_job("b", "cb", [], [], "q", 1)]),
                    ],
                )
            ],
        )
        a = _job_key("s1", "t1", "a")
        b = _job_key("s1", "t2", "b")
        err, new_b, notes = link_jobs(doc, a, b)
        self.assertIsNone(err)
        self.assertTrue(any("moved" in n for n in notes))
        # Child stays in t2; parent follows into t2.
        _stage, task, _job = doc.get_job(new_b)
        self.assertEqual(task, "t2")
        new_a = _job_key("s1", "t2", "a")
        self.assertIsNotNone(doc.get_job(new_a))
        located_a = doc.find_job_index(new_a)
        located_b = doc.find_job_index(new_b)
        self.assertLess(located_a[2], located_b[2])
        graph = build_job_graph(doc)
        self.assertIn(new_a, graph.parents.get(new_b, []))

    def test_link_merges_into_child_stage(self):
        """Cross-stage link moves parent into the child's stage."""
        doc = FlowDocument(
            stages=[
                make_stage("s1", [make_task("t1", [make_job("a", "ca", [], [], "q", 1)])]),
                make_stage("s2", [make_task("t1", [make_job("b", "cb", [], [], "q", 1)])]),
            ],
        )
        a = _job_key("s1", "t1", "a")
        b = _job_key("s2", "t1", "b")
        err, new_b, notes = link_jobs(doc, a, b)
        self.assertIsNone(err)
        self.assertTrue(any("follow child" in n for n in notes))
        new_a = _job_key("s2", "t1", "a")
        self.assertIsNotNone(doc.get_job(new_a))
        self.assertIsNone(doc.get_job(a))  # old key gone
        stage_a, task_a, _ = doc.get_job(new_a)
        stage_b, task_b, _ = doc.get_job(new_b)
        self.assertEqual(stage_a, "s2")
        self.assertEqual(stage_b, "s2")
        self.assertEqual(task_a, task_b)
        self.assertIn(new_a, get_file_parent_keys(doc, new_b))

    def test_link_later_job_as_parent_of_earlier_root(self):
        """A root job (no parents) can receive a later same-task job as parent.

        Task-order edges alone must not block the link; place_parent_before_child
        reorders so the new parent runs first.
        """
        doc = FlowDocument(
            stages=[
                make_stage(
                    "s1",
                    [
                        make_task(
                            "t1",
                            [
                                make_job("a", "ca", [], [], "q", 1),
                                make_job("b", "cb", [], [], "q", 1),
                            ],
                        )
                    ],
                )
            ],
        )
        a = _job_key("s1", "t1", "a")
        b = _job_key("s1", "t1", "b")
        self.assertEqual(get_parent_keys(doc, a), [])
        # Task order has a→b, so a naive walk of all edges would false-positive.
        self.assertFalse(would_create_cycle(doc, b, a))

        err, new_a, notes = link_jobs(doc, b, a)
        self.assertIsNone(err, err)
        self.assertIn(b, get_file_parent_keys(doc, new_a))
        # Child should now sit after parent in the task.
        located_b = doc.find_job_index(b)
        located_a = doc.find_job_index(new_a)
        self.assertIsNotNone(located_b)
        self.assertIsNotNone(located_a)
        self.assertEqual(located_b[1]["name"], located_a[1]["name"])
        self.assertLess(located_b[2], located_a[2])

    def test_graph_reflects_manual_link(self):
        doc = self._apr_doc()
        names = [job["name"] for _s, _t, job in doc.iter_jobs()]
        parent = _job_key("APR", "apr", names[0])
        child = _job_key("APR", "apr", names[2])
        err, child, _notes = link_jobs(doc, parent, child)
        self.assertIsNone(err)
        graph = build_job_graph(doc)
        self.assertIn(parent, graph.parents.get(child, []))


if __name__ == "__main__":
    unittest.main()
