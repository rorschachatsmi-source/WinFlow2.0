"""Tests for input parsers."""

import tempfile
import unittest
from pathlib import Path

from flow_generator.parsers.block_stream import parse_block_stream
from flow_generator.parsers.setting_sh import parse_setting_sh


class TestParseSettingSh(unittest.TestCase):
    def test_parses_set_lines_and_ignores_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "setting.sh"
            path.write_text(
                '\n'.join(
                    [
                        '# comment',
                        'set TOP_MODULE = "sm8466_top"',
                        'set FLAG_DMF = "1"',
                        '',
                    ]
                ),
                encoding="utf-8",
            )
            cfg = parse_setting_sh(path)
            self.assertEqual(cfg["TOP_MODULE"], "sm8466_top")
            self.assertEqual(cfg["FLAG_DMF"], "1")

    def test_empty_file_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "setting.sh"
            path.write_text("", encoding="utf-8")
            self.assertEqual(parse_setting_sh(path), {})


class TestParseBlockStream(unittest.TestCase):
    def test_parses_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "block_stream.list"
            path.write_text(
                '\n'.join(
                    [
                        "# header",
                        "block_a /work/a",
                        "block_b /work/b",
                    ]
                ),
                encoding="utf-8",
            )
            blocks = parse_block_stream(path)
            self.assertEqual(
                blocks,
                [
                    {"name": "block_a", "workdir": "/work/a"},
                    {"name": "block_b", "workdir": "/work/b"},
                ],
            )

    def test_missing_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.list"
            self.assertEqual(parse_block_stream(path), [])


if __name__ == "__main__":
    unittest.main()
