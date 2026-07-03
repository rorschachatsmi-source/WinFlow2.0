"""Tests for LSF job submission options."""

import unittest
from unittest.mock import MagicMock, patch

from flow_runner_core import LSFJobManager


class TestLSFSubmit(unittest.TestCase):
    @patch("flow_runner_core.subprocess.run")
    def test_submit_without_machine(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Job <42> is submitted", stderr="")
        manager = LSFJobManager(MagicMock())
        job_id = manager.submit_job("test_job", "echo hi", queue="tpdsd1", cpu=2)
        self.assertEqual(job_id, "42")
        cmd = mock_run.call_args[0][0]
        self.assertIn("-q", cmd)
        self.assertIn("tpdsd1", cmd)
        self.assertNotIn("-m", cmd)

    @patch("flow_runner_core.subprocess.run")
    def test_submit_with_machine(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Job <99> is submitted", stderr="")
        manager = LSFJobManager(MagicMock())
        manager.submit_job(
            "test_job",
            "echo hi",
            queue="tpdsd1",
            cpu=4,
            machine="machine1 machine2",
        )
        cmd = mock_run.call_args[0][0]
        m_index = cmd.index("-m")
        self.assertEqual(cmd[m_index + 1], "machine1 machine2")
        self.assertEqual(cmd[-1], "echo hi")


if __name__ == "__main__":
    unittest.main()
