"""Tests for parallel DAG execution and job failure callbacks."""

import threading
import time
import unittest
from unittest.mock import patch

from flow_runner_core import (
    FlowLogger,
    FlowRunner,
    FlowValidator,
    JobStatus,
    LSFJobManager,
)


def _job(name, *, inputs=None, outputs=None, parents=None, children=None):
    return {
        "name": name,
        "command": f"echo {name}",
        "inputs": list(inputs or []),
        "outputs": list(outputs or []),
        "parents": list(parents or []),
        "children": list(children or []),
        "queue": "q",
        "cpu": 1,
    }


class TestParallelTasks(unittest.TestCase):
    def _runner(self, callback=None):
        logger = FlowLogger()
        return FlowRunner(logger, FlowValidator(logger), LSFJobManager(logger), job_callback=callback)

    def test_two_root_jobs_submit_together(self):
        starts = []
        lock = threading.Lock()

        def fake_submit(self, job_name, command, queue=None, cpu=None, machine=""):
            with lock:
                starts.append(time.time())
            time.sleep(0.05)
            return str(len(starts))

        def fake_wait(self, job_id, job_outputs, poll_interval=None, validator=None, on_status=None):
            if on_status:
                on_status(JobStatus.RUNNING)
            time.sleep(0.05)
            if on_status:
                on_status(JobStatus.DONE)

        config = {
            "flow_name": "t",
            "poll_interval": 1,
            "stages": [
                {
                    "name": "root",
                    "tasks": [
                        {
                            "name": "t1",
                            "jobs": [_job("j1")],
                        },
                        {
                            "name": "t2",
                            "jobs": [_job("j2")],
                        },
                    ],
                }
            ],
        }

        with patch.object(LSFJobManager, "submit_job", fake_submit), patch.object(
            LSFJobManager, "wait_job", fake_wait
        ):
            self._runner().run_flow(config)

        self.assertEqual(len(starts), 2)
        self.assertLess(abs(starts[0] - starts[1]), 0.1)

    def test_child_waits_for_parent_across_stages(self):
        order = []
        lock = threading.Lock()
        parent_done = threading.Event()

        def fake_submit(self, job_name, command, queue=None, cpu=None, machine=""):
            with lock:
                order.append(("submit", job_name))
            return job_name

        def fake_wait(self, job_id, job_outputs, poll_interval=None, validator=None, on_status=None):
            with lock:
                order.append(("wait_start", job_id))
            if "_j1_" in job_id:
                time.sleep(0.08)
                parent_done.set()
            else:
                ok = parent_done.wait(timeout=1.0)
                if not ok:
                    raise RuntimeError("child started before parent finished")
            if on_status:
                on_status(JobStatus.DONE)
            with lock:
                order.append(("wait_done", job_id))

        # Different stages; dependency only via parents/children.
        config = {
            "flow_name": "t",
            "poll_interval": 1,
            "stages": [
                {
                    "name": "s1",
                    "tasks": [
                        {
                            "name": "t1",
                            "jobs": [
                                _job(
                                    "j1",
                                    children=["s2/t2/j2"],
                                )
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
                                _job(
                                    "j2",
                                    parents=["s1/t1/j1"],
                                )
                            ],
                        }
                    ],
                },
            ],
        }

        with patch.object(LSFJobManager, "submit_job", fake_submit), patch.object(
            LSFJobManager, "wait_job", fake_wait
        ):
            self._runner().run_flow(config)

        submit_names = [n for kind, n in order if kind == "submit"]
        self.assertEqual(len(submit_names), 2)
        # Parent must finish wait before child is submitted.
        wait_done_j1 = next(i for i, (k, n) in enumerate(order) if k == "wait_done" and "_j1_" in n)
        submit_j2 = next(i for i, (k, n) in enumerate(order) if k == "submit" and "_j2_" in n)
        self.assertLess(wait_done_j1, submit_j2)

    def test_diamond_d_waits_for_b_and_c(self):
        starts = {}
        ends = {}
        lock = threading.Lock()
        id_to_logical = {}

        def fake_submit(self, job_name, command, queue=None, cpu=None, machine=""):
            for logical in ("A", "B", "C", "D"):
                if f"_{logical}_" in job_name:
                    id_to_logical[job_name] = logical
                    break
            return job_name

        def fake_wait(self, job_id, job_outputs, poll_interval=None, validator=None, on_status=None):
            logical = id_to_logical[job_id]
            with lock:
                starts[logical] = time.time()
            time.sleep(0.05)
            with lock:
                ends[logical] = time.time()
            if on_status:
                on_status(JobStatus.DONE)

        a, b, c, d = "s/t/A", "s/t/B", "s/t/C", "s/t/D"
        config = {
            "flow_name": "t",
            "poll_interval": 1,
            "stages": [
                {
                    "name": "s",
                    "tasks": [
                        {
                            "name": "t",
                            "jobs": [
                                _job("A", children=[b, c]),
                                _job("B", parents=[a], children=[d]),
                                _job("C", parents=[a], children=[d]),
                                _job("D", parents=[b, c]),
                            ],
                        }
                    ],
                }
            ],
        }

        with patch.object(LSFJobManager, "submit_job", fake_submit), patch.object(
            LSFJobManager, "wait_job", fake_wait
        ):
            self._runner().run_flow(config)

        self.assertLess(ends["A"], starts["B"])
        self.assertLess(ends["A"], starts["C"])
        self.assertLess(ends["B"], starts["D"])
        self.assertLess(ends["C"], starts["D"])
        # B and C can overlap.
        self.assertLess(abs(starts["B"] - starts["C"]), 0.1)

    def test_job_filter_skip_parent_unlocks_child(self):
        ran = []

        def fake_submit(self, job_name, command, queue=None, cpu=None, machine=""):
            ran.append(job_name)
            return "1"

        def fake_wait(self, job_id, job_outputs, poll_interval=None, validator=None, on_status=None):
            if on_status:
                on_status(JobStatus.DONE)

        config = {
            "flow_name": "t",
            "poll_interval": 1,
            "stages": [
                {
                    "name": "s",
                    "tasks": [
                        {
                            "name": "t",
                            "jobs": [
                                _job("parent", children=["s/t/child"]),
                                _job("child", parents=["s/t/parent"]),
                            ],
                        }
                    ],
                }
            ],
        }

        def job_filter(key):
            return key != "s/t/parent"  # skip parent

        with patch.object(LSFJobManager, "submit_job", fake_submit), patch.object(
            LSFJobManager, "wait_job", fake_wait
        ):
            self._runner().run_flow(config, job_filter=job_filter)

        self.assertEqual(len(ran), 1)
        self.assertTrue(any("child" in n for n in ran))
        self.assertFalse(any("parent" in n and "child" not in n for n in ran))

    def test_legacy_flow_without_parents_children_annotates_and_runs(self):
        ran = []

        def fake_submit(self, job_name, command, queue=None, cpu=None, machine=""):
            ran.append(job_name)
            return str(len(ran))

        def fake_wait(self, job_id, job_outputs, poll_interval=None, validator=None, on_status=None):
            if on_status:
                on_status(JobStatus.DONE)

        # No parents/children fields — runner should annotate from task order.
        config = {
            "flow_name": "t",
            "poll_interval": 1,
            "stages": [
                {
                    "name": "s",
                    "tasks": [
                        {
                            "name": "t",
                            "jobs": [
                                {
                                    "name": "j1",
                                    "command": "echo 1",
                                    "inputs": [],
                                    "outputs": [],
                                    "queue": "q",
                                    "cpu": 1,
                                },
                                {
                                    "name": "j2",
                                    "command": "echo 2",
                                    "inputs": [],
                                    "outputs": [],
                                    "queue": "q",
                                    "cpu": 1,
                                },
                            ],
                        }
                    ],
                }
            ],
        }

        with patch.object(LSFJobManager, "submit_job", fake_submit), patch.object(
            LSFJobManager, "wait_job", fake_wait
        ):
            self._runner().run_flow(config)

        self.assertEqual(len(ran), 2)
        j1 = config["stages"][0]["tasks"][0]["jobs"][0]
        j2 = config["stages"][0]["tasks"][0]["jobs"][1]
        self.assertEqual(j1["children"], ["s/t/j2"])
        self.assertEqual(j2["parents"], ["s/t/j1"])

    def test_missing_input_emits_job_failed(self):
        events = []

        def cb(event, data):
            events.append((event, data.get("job_key"), data.get("status")))

        def fake_submit(self, job_name, command, queue=None, cpu=None, machine=""):
            return "1"

        def fake_wait(self, job_id, job_outputs, poll_interval=None, validator=None, on_status=None):
            if on_status:
                on_status(JobStatus.DONE)

        config = {
            "flow_name": "t",
            "poll_interval": 1,
            "stages": [
                {
                    "name": "root",
                    "tasks": [
                        {
                            "name": "ok",
                            "jobs": [_job("j1")],
                        },
                        {
                            "name": "bad",
                            "jobs": [
                                _job("j2", inputs=["__winflow_missing_input__.dat"]),
                            ],
                        },
                    ],
                }
            ],
        }

        with patch.object(LSFJobManager, "submit_job", fake_submit), patch.object(
            LSFJobManager, "wait_job", fake_wait
        ):
            with self.assertRaises(RuntimeError):
                self._runner(cb).run_flow(config)

        self.assertIn(
            ("job_failed", "root/bad/j2", JobStatus.EXIT.value),
            events,
        )


class TestJobRelationsValidation(unittest.TestCase):
    def test_cycle_rejected(self):
        logger = FlowLogger()
        validator = FlowValidator(logger)
        config = {
            "flow_name": "t",
            "stages": [
                {
                    "name": "s",
                    "tasks": [
                        {
                            "name": "t",
                            "jobs": [
                                _job("a", parents=["s/t/b"], children=["s/t/b"]),
                                _job("b", parents=["s/t/a"], children=["s/t/a"]),
                            ],
                        }
                    ],
                }
            ],
        }
        self.assertFalse(validator.validate_config(config))

    def test_unknown_parent_rejected(self):
        logger = FlowLogger()
        validator = FlowValidator(logger)
        config = {
            "flow_name": "t",
            "stages": [
                {
                    "name": "s",
                    "tasks": [
                        {
                            "name": "t",
                            "jobs": [
                                _job("a", parents=["s/t/missing"]),
                            ],
                        }
                    ],
                }
            ],
        }
        self.assertFalse(validator.validate_config(config))

    def test_inconsistent_mutual_link_rejected(self):
        logger = FlowLogger()
        validator = FlowValidator(logger)
        config = {
            "flow_name": "t",
            "stages": [
                {
                    "name": "s",
                    "tasks": [
                        {
                            "name": "t",
                            "jobs": [
                                _job("a", children=["s/t/b"]),
                                _job("b", parents=[]),  # missing back-link
                            ],
                        }
                    ],
                }
            ],
        }
        self.assertFalse(validator.validate_config(config))


if __name__ == "__main__":
    unittest.main()
