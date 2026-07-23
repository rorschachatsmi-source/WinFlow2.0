"""Tests for lazy Job Log file helpers."""

import unittest
from pathlib import Path
import tempfile

from job_log_io import is_job_log_noise, read_file_tail_lines, read_lines_before


class TestJobLogIo(unittest.TestCase):
    def test_term_noise_filter(self):
        self.assertTrue(is_job_log_noise("TERM environment variable not set"))
        self.assertTrue(is_job_log_noise("TERM environment variable not set."))
        self.assertTrue(is_job_log_noise("  term environment variable not set  "))
        self.assertFalse(is_job_log_noise("ERROR: something failed"))

    def test_read_file_tail_and_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "job.log"
            lines = [f"line-{i}" for i in range(250)]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            got, start, truncated = read_file_tail_lines(path, 100)
            self.assertTrue(truncated)
            self.assertEqual(len(got), 100)
            self.assertEqual(got[0], "line-150")
            self.assertEqual(got[-1], "line-249")

            older, new_start = read_lines_before(path, start, 50)
            self.assertEqual(len(older), 50)
            self.assertEqual(older[0], "line-100")
            self.assertEqual(older[-1], "line-149")
            self.assertGreater(new_start, 0)

            older2, start2 = read_lines_before(path, new_start, 200)
            self.assertEqual(older2[0], "line-0")
            self.assertEqual(older2[-1], "line-99")
            self.assertEqual(start2, 0)

    def test_tail_small_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "small.log"
            path.write_text("a\nb\nc\n", encoding="utf-8")
            got, start, truncated = read_file_tail_lines(path, 100)
            self.assertFalse(truncated)
            self.assertEqual(start, 0)
            self.assertEqual(got, ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
