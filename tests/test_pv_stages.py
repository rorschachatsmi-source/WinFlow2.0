"""Tests for PV stage builders."""

import unittest

from flow_generator.flows.pv.config import PVConfig
from flow_generator.flows.pv.paths import PVPaths
from flow_generator.flows.pv.stages.merge import build_merge_stage
from flow_generator.flows.pv.stages.stream_in import (
    pre_stream_in_apr_stage,
    stream_in_apr_stage,
    stream_in_sub_stage,
    stream_out_apr_stage,
)
from flow_generator.flows.pv.stages.verify import build_post_gds2oas_stage
from winflow_config import get_config


def sample_config(**overrides):
    pv_cfg = get_config().pv
    values = {
        "top": "sm8466_top",
        "final_top": "sm8466_top",
        "queue": "tpdsd1",
        "cpu": "4",
        "dmexcl_ptn": False,
        "paths": PVPaths.defaults(),
        "scripts": pv_cfg.scripts,
        "jobs": pv_cfg.jobs,
    }
    values.update(overrides)
    return PVConfig(**values)


class TestPVStages(unittest.TestCase):
    def test_stream_in_sub_skipped_when_no_blocks(self):
        self.assertIsNone(stream_in_sub_stage([], sample_config()))

    def test_stream_in_sub_creates_task_per_block(self):
        blocks = [{"name": "blk1", "workdir": "/w/blk1"}]
        stage = stream_in_sub_stage(blocks, sample_config())
        self.assertEqual(stage["name"], "streamIn_sub")
        self.assertEqual(len(stage["tasks"]), 1)
        self.assertEqual(stage["tasks"][0]["name"], "blk1")

    def test_stream_in_apr_job_command(self):
        stage = stream_in_apr_stage(sample_config())
        job = stage["tasks"][0]["jobs"][0]
        self.assertEqual(job["name"], "laker_In")
        self.assertEqual(job["command"], "../flow/bzgdsin_apr.sh")

    def test_stream_in_apr_includes_sub_block_outputs(self):
        blocks = [{"name": "blk1", "workdir": "/w/blk1"}]
        stage = stream_in_apr_stage(sample_config(), ["../LakerBZ/blk1.blitz++"])
        job = stage["tasks"][0]["jobs"][0]
        self.assertEqual(
            job["inputs"],
            ["../DATA/apr.gds.gz", "../LakerBZ/blk1.blitz++"],
        )

    def test_pre_stream_in_apr_combines_apr_and_dummy_outputs(self):
        blocks = [{"name": "blk1", "workdir": "/w/blk1"}]
        stage = pre_stream_in_apr_stage(blocks, sample_config())
        self.assertEqual(stage["name"], "pre_streamIn_APR")
        job = stage["tasks"][0]["jobs"][0]
        self.assertEqual(job["name"], "laker_pre_In")
        self.assertIn("../DATA/apr.gds.gz", job["inputs"])
        self.assertIn("../LakerBZ/blk1.blitz++", job["inputs"])
        self.assertEqual(job["outputs"], ["../LakerBZ/sm8466_top_APR.blitz++"])

    def test_stream_out_apr_outputs_full_gds(self):
        stage = stream_out_apr_stage(sample_config())
        job = stage["tasks"][0]["jobs"][0]
        self.assertIn("../GDS/sm8466_top_FULL.gds.gz", job["outputs"])

    def test_merge_stage_respects_flags(self):
        settings = {"FLAG_DMF": "1", "FLAG_DOD": "0", "FLAG_DEX": "0"}
        stage, laker_outputs = build_merge_stage(settings, sample_config())
        task_names = [task["name"] for task in stage["tasks"]]
        self.assertIn("DM", task_names)
        self.assertNotIn("DODPO", task_names)
        self.assertIn("laker_text", task_names)
        self.assertIn("../LakerBZ/create_text_from_APRgds.tcl", laker_outputs)

    def test_post_gds2oas_defaults_to_drc_stage(self):
        stage = build_post_gds2oas_stage({}, sample_config())
        self.assertIsNotNone(stage)
        self.assertEqual(stage["name"], "DRC")
        self.assertEqual([task["name"] for task in stage["tasks"]], ["DRC"])

    def test_post_gds2oas_verify_stage_when_be_or_fe_enabled(self):
        stage = build_post_gds2oas_stage({"FLAG_DRCBE": "1"}, sample_config())
        self.assertEqual(stage["name"], "Verify")
        self.assertEqual([task["name"] for task in stage["tasks"]], ["DRC_BE"])

    def test_post_gds2oas_parallel_drc_be_fe_and_lvs(self):
        settings = {
            "FLAG_DRCBE": "1",
            "FLAG_DRCFE": "1",
            "FLAG_LVS": "1",
        }
        stage = build_post_gds2oas_stage(settings, sample_config())
        self.assertEqual(stage["name"], "Verify")
        self.assertEqual(
            [task["name"] for task in stage["tasks"]],
            ["DRC_BE", "DRC_FE", "LVS"],
        )

    def test_post_gds2oas_drc_stage_with_flag_drc(self):
        settings = {"FLAG_DRC": "1", "FLAG_DRCBE": "1"}
        stage = build_post_gds2oas_stage(settings, sample_config())
        self.assertEqual(stage["name"], "DRC")
        self.assertEqual(
            [task["name"] for task in stage["tasks"]],
            ["DRC", "DRC_BE"],
        )

    def test_post_gds2oas_drc_lvs_use_top_out_gds_when_oasii_off(self):
        settings = {"USE_OASII": "0", "FLAG_LVS": "1"}
        stage = build_post_gds2oas_stage(settings, sample_config())
        self.assertEqual(stage["name"], "DRC")
        drc = next(t for t in stage["tasks"] if t["name"] == "DRC")["jobs"][0]
        lvs = next(t for t in stage["tasks"] if t["name"] == "LVS")["jobs"][0]
        self.assertEqual(drc["inputs"], ["../GDS/sm8466_top.gds.gz"])
        self.assertIn("../GDS/sm8466_top.gds.gz", lvs["inputs"])
        self.assertNotIn("../GDS/sm8466_top.oas", lvs["inputs"])


if __name__ == "__main__":
    unittest.main()
