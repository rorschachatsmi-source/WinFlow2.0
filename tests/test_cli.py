"""Tests for flow_generator CLI."""

import json
import tempfile
import unittest
from pathlib import Path
import io
from contextlib import redirect_stdout

from flow_generator.cli import run


SETTING = '\n'.join(
    [
        'set TOP_MODULE = "sm8466_top"',
        'set MACHINE_QUEUE = "tpdsd1"',
        'set MACHINE_CPU = "4"',
    ]
)


class TestCLI(unittest.TestCase):
    def test_list_flows(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run(["--list"])
        self.assertEqual(code, 0)
        output = buf.getvalue()
        self.assertIn("pv", output)
        self.assertIn("apr", output)

    def test_generate_pv_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting = Path(tmp) / "setting.sh"
            blocks = Path(tmp) / "block_stream.list"
            output = Path(tmp) / "flow.json"
            setting.write_text(SETTING, encoding="utf-8")
            blocks.write_text("blk1 /work/blk1\n", encoding="utf-8")

            code = run(
                [
                    "--flow",
                    "pv",
                    "--setting",
                    str(setting),
                    "--blocks",
                    str(blocks),
                    "-o",
                    str(output),
                ]
            )

            self.assertEqual(code, 0)
            self.assertTrue(output.exists())
            flow = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(flow["flow_name"], "PV")
            self.assertGreater(len(flow["stages"]), 0)

    def test_missing_setting_returns_error(self):
        code = run(["--flow", "pv", "--setting", "missing-setting.sh"])
        self.assertEqual(code, 1)

    def test_validation_error_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting = Path(tmp) / "setting.sh"
            setting.write_text('set TOP_MODULE = "only_top"\n', encoding="utf-8")
            code = run(["--flow", "pv", "--setting", str(setting)])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
