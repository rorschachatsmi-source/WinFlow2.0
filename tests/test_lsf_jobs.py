"""Tests for LSF alive / kill helpers."""

import unittest
from unittest.mock import patch

from lsf_jobs import (
    is_active_lsf_status,
    lsf_job_alive,
    lsf_kill_job,
)


class TestLsfJobAlive(unittest.TestCase):
    def test_active_statuses(self):
        for status in ("PEND", "RUN", "PSUSP", "USUSP", "SSUSP", "WAIT"):
            self.assertTrue(is_active_lsf_status(status), status)
        for status in ("DONE", "EXIT", "ZOMBI", ""):
            self.assertFalse(is_active_lsf_status(status), status)

    @patch("lsf_jobs.run_lsf_cmd")
    def test_alive_false_for_done_job_id(self, mock_run):
        # Classic LSF quirk: bjobs still returns finished jobs.
        mock_run.return_value = (0, "DONE", "")
        self.assertFalse(lsf_job_alive(job_id="12345"))
        cmd = mock_run.call_args[0][0]
        self.assertIn("-o", cmd)
        self.assertIn("12345", cmd)

    @patch("lsf_jobs.run_lsf_cmd")
    def test_alive_true_for_run(self, mock_run):
        mock_run.return_value = (0, "RUN", "")
        self.assertTrue(lsf_job_alive(job_id="99"))

    @patch("lsf_jobs.run_lsf_cmd")
    def test_alive_true_for_pend(self, mock_run):
        mock_run.return_value = (0, "PEND", "")
        self.assertTrue(lsf_job_alive(job_id="99"))

    @patch("lsf_jobs.run_lsf_cmd")
    def test_alive_false_when_bjobs_fails(self, mock_run):
        mock_run.return_value = (1, "", "Job <99> is not found")
        self.assertFalse(lsf_job_alive(job_id="99"))

    @patch("lsf_jobs.run_lsf_cmd")
    def test_kill_prefers_job_id_no_name_fallback(self, mock_run):
        mock_run.return_value = (1, "", "Job <99> is not found")
        ok, msg = lsf_kill_job(job_id="99", lsf_name="user_job_ts")
        self.assertFalse(ok)
        self.assertIn("not found", msg.lower())
        # Must not fall back to bkill -J when job_id was provided.
        self.assertEqual(mock_run.call_count, 1)
        cmd = mock_run.call_args[0][0]
        self.assertNotIn("-J", cmd)
        self.assertIn("99", cmd)

    @patch("lsf_jobs.run_lsf_cmd")
    def test_kill_by_name_when_no_id(self, mock_run):
        mock_run.return_value = (0, "Job <1> is being terminated", "")
        ok, _msg = lsf_kill_job(job_id="", lsf_name="user_job_ts")
        self.assertTrue(ok)
        cmd = mock_run.call_args[0][0]
        self.assertIn("-J", cmd)


if __name__ == "__main__":
    unittest.main()
