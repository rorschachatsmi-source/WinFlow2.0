"""Tests for parallel task execution and job failure callbacks."""

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


class TestParallelTasks(unittest.TestCase):
    def _runner(self, callback=None):
        logger = FlowLogger()
        return FlowRunner(logger, FlowValidator(logger), LSFJobManager(logger), job_callback=callback)

    def test_two_root_tasks_submit_together(self):
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
                            "jobs": [
                                {
                                    "name": "j1",
                                    "command": "echo 1",
                                    "inputs": [],
                                    "outputs": [],
                                    "queue": "q",
                                    "cpu": 1,
                                }
                            ],
                        },
                        {
                            "name": "t2",
                            "jobs": [
                                {
                                    "name": "j2",
                                    "command": "echo 2",
                                    "inputs": [],
                                    "outputs": [],
                                    "queue": "q",
                                    "cpu": 1,
                                }
                            ],
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
                            "jobs": [
                                {
                                    "name": "j1",
                                    "command": "echo 1",
                                    "inputs": [],
                                    "outputs": [],
                                    "queue": "q",
                                    "cpu": 1,
                                }
                            ],
                        },
                        {
                            "name": "bad",
                            "jobs": [
                                {
                                    "name": "j2",
                                    "command": "echo 2",
                                    "inputs": ["__winflow_missing_input__.dat"],
                                    "outputs": [],
                                    "queue": "q",
                                    "cpu": 1,
                                }
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


if __name__ == "__main__":
    unittest.main()
