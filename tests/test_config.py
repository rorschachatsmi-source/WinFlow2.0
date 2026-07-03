"""Tests for centralized WinFlow configuration."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from winflow_config import get_config, load_config, reset_config
from winflow_config.loader import merge_dataclass
from winflow_config.models import AppConfig, RunnerConfig


class TestWinflowConfig(unittest.TestCase):
    def setUp(self):
        reset_config()

    def tearDown(self):
        reset_config()

    def test_defaults_match_config_json(self):
        config_path = Path(__file__).resolve().parent.parent / "config.json"
        loaded = load_config(config_path)
        self.assertEqual(loaded.runner.default_queue, "tpdsd1")
        self.assertEqual(loaded.runner.poll_interval, 20)
        self.assertEqual(loaded.generator.default_cpu, 4)
        self.assertEqual(loaded.pv.paths.data_dir, "../DATA")

    def test_merge_dataclass_overrides_nested_values(self):
        base = AppConfig()
        updated = merge_dataclass(base, {"runner": {"default_queue": "custom_q"}})
        self.assertEqual(updated.runner.default_queue, "custom_q")
        self.assertEqual(updated.runner.poll_interval, base.runner.poll_interval)

    def test_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps({"runner": {"default_queue": "from_file"}}),
                encoding="utf-8",
            )
            os.environ["WINFLOW_CONFIG"] = str(config_path)
            os.environ["WINFLOW_RUNNER_DEFAULT_QUEUE"] = "from_env"
            try:
                reset_config()
                config = get_config(reload=True)
                self.assertEqual(config.runner.default_queue, "from_env")
            finally:
                os.environ.pop("WINFLOW_CONFIG", None)
                os.environ.pop("WINFLOW_RUNNER_DEFAULT_QUEUE", None)
                reset_config()

    def test_get_config_is_cached(self):
        first = get_config()
        second = get_config()
        self.assertIs(first, second)
        third = get_config(reload=True)
        self.assertIsNot(first, third)


if __name__ == "__main__":
    unittest.main()
