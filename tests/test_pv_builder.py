"""Tests for PV flow builder."""

import unittest

from flow_generator.core.context import BuildContext
from flow_generator.flows.pv.builder import PVFlowBuilder


def base_settings(**extra):
    settings = {
        "TOP_MODULE": "sm8466_top",
        "MACHINE_QUEUE": "tpdsd1",
        "MACHINE_CPU": "4",
    }
    settings.update(extra)
    return settings


class TestPVFlowBuilder(unittest.TestCase):
    def test_validate_requires_core_settings(self):
        context = BuildContext(settings={}, blocks=[])
        errors = PVFlowBuilder.validate_context(context)
        self.assertTrue(any("TOP_MODULE" in err for err in errors))
        self.assertTrue(any("MACHINE_QUEUE" in err for err in errors))
        self.assertTrue(any("MACHINE_CPU" in err for err in errors))

    def test_validate_dmexcl_ptn_requires_blocks(self):
        context = BuildContext(
            settings=base_settings(FLAG_DMEXCL_PTN="1"),
            blocks=[],
        )
        errors = PVFlowBuilder.validate_context(context)
        self.assertIn("FLAG_DMEXCL_PTN=1 requires non-empty block_stream.list", errors)

    def test_build_default_stage_order(self):
        context = BuildContext(
            settings=base_settings(),
            blocks=[{"name": "blk1", "workdir": "/w/blk1"}],
        )
        flow = PVFlowBuilder.build(context)
        stage_names = [stage["name"] for stage in flow["stages"]]
        self.assertEqual(
            stage_names,
            ["streamIn_sub", "streamIn_APR", "streamOut_APR", "Merge", "streamOut_TOP"],
        )
        self.assertEqual(flow["flow_name"], "PV")
        self.assertEqual(flow["poll_interval"], 20)

    def test_build_stream_in_apr_waits_on_sub_outputs(self):
        context = BuildContext(
            settings=base_settings(),
            blocks=[{"name": "blk1", "workdir": "/w/blk1"}],
        )
        flow = PVFlowBuilder.build(context)
        stream_in_apr = next(s for s in flow["stages"] if s["name"] == "streamIn_APR")
        laker_in = stream_in_apr["tasks"][0]["jobs"][0]
        self.assertIn("../DATA/apr.gds.gz", laker_in["inputs"])
        self.assertIn("../LakerBZ/blk1.blitz++", laker_in["inputs"])

    def test_build_dmexcl_ptn_laker_job_chain(self):
        context = BuildContext(
            settings=base_settings(FLAG_DMEXCL_PTN="1"),
            blocks=[{"name": "blk1", "workdir": "/w/blk1"}],
        )
        flow = PVFlowBuilder.build(context)
        pre_in = next(
            s for s in flow["stages"] if s["name"] == "pre_streamIn_APR"
        )["tasks"][0]["jobs"][0]
        laker_out = next(
            s for s in flow["stages"] if s["name"] == "streamOut_APR"
        )["tasks"][0]["jobs"][0]
        laker_in = next(
            s for s in flow["stages"] if s["name"] == "streamIn_APR"
        )["tasks"][0]["jobs"][0]

        self.assertEqual(pre_in["name"], "laker_pre_In")
        self.assertEqual(laker_out["name"], "laker_Out")
        self.assertEqual(laker_in["name"], "laker_In")

        pre_out = pre_in["outputs"][0]
        self.assertIn(pre_out, laker_out["inputs"])
        out_gds = laker_out["outputs"][0]
        self.assertIn(out_gds, laker_in["inputs"])

    def test_build_dmexcl_ptn_stage_order(self):
        context = BuildContext(
            settings=base_settings(FLAG_DMEXCL_PTN="1"),
            blocks=[{"name": "blk1", "workdir": "/w/blk1"}],
        )
        flow = PVFlowBuilder.build(context)
        stage_names = [stage["name"] for stage in flow["stages"]]
        self.assertEqual(
            stage_names,
            [
                "streamIn_sub_dummy",
                "pre_streamIn_APR",
                "streamOut_APR",
                "streamIn_APR",
                "Merge",
                "streamOut_TOP",
            ],
        )

    def test_build_uses_top_module_post_for_final_top(self):
        context = BuildContext(
            settings=base_settings(TOP_MODULE_POST="sm8466_top_post"),
            blocks=[],
        )
        flow = PVFlowBuilder.build(context)
        stream_out_top = flow["stages"][-1]
        gds2oas_job = stream_out_top["tasks"][0]["jobs"][2]
        self.assertIn("sm8466_top_post.oas", gds2oas_job["outputs"][0])

    def test_build_appends_verify_when_enabled(self):
        context = BuildContext(
            settings=base_settings(FLAG_DRCBE="1"),
            blocks=[],
        )
        flow = PVFlowBuilder.build(context)
        self.assertEqual(flow["stages"][-1]["name"], "Verify")


if __name__ == "__main__":
    unittest.main()
