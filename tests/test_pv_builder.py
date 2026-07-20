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
            ["streamIn_sub", "streamIn_APR", "streamOut_APR", "Merge", "streamOut_TOP", "DRC"],
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
                "DRC",
            ],
        )

    def test_build_uses_top_module_post_for_final_top(self):
        context = BuildContext(
            settings=base_settings(TOP_MODULE_POST="sm8466_top_post"),
            blocks=[],
        )
        flow = PVFlowBuilder.build(context)
        stream_out_top = next(s for s in flow["stages"] if s["name"] == "streamOut_TOP")
        gds2oas_job = stream_out_top["tasks"][0]["jobs"][2]
        self.assertIn("sm8466_top_post.oas", gds2oas_job["outputs"][0])

    def test_build_verify_stage_when_drcbe_enabled(self):
        context = BuildContext(
            settings=base_settings(FLAG_DRCBE="1"),
            blocks=[],
        )
        flow = PVFlowBuilder.build(context)
        self.assertEqual(flow["stages"][-1]["name"], "Verify")
        self.assertEqual(
            [task["name"] for task in flow["stages"][-1]["tasks"]],
            ["DRC_BE"],
        )

    def test_spi_runs_parallel_on_first_stream_in_stage(self):
        context = BuildContext(
            settings=base_settings(),
            blocks=[{"name": "blk1", "workdir": "/w/blk1"}],
        )
        flow = PVFlowBuilder.build(context)
        stream_in_sub = flow["stages"][0]
        task_names = [task["name"] for task in stream_in_sub["tasks"]]
        self.assertIn("SPI", task_names)
        self.assertIn("blk1", task_names)

    def test_spi_on_stream_in_apr_when_no_blocks(self):
        context = BuildContext(settings=base_settings(), blocks=[])
        flow = PVFlowBuilder.build(context)
        stream_in_apr = flow["stages"][0]
        task_names = [task["name"] for task in stream_in_apr["tasks"]]
        self.assertEqual(task_names, ["sm8466_top_streamIn_APR", "SPI"])

    def test_rcxt_runs_parallel_with_laker_toplib_when_flag_set(self):
        context = BuildContext(
            settings=base_settings(FLAG_DMF="1", FLAG_RCXT="1"),
            blocks=[],
        )
        flow = PVFlowBuilder.build(context)
        stream_out_top = next(s for s in flow["stages"] if s["name"] == "streamOut_TOP")
        task_names = [task["name"] for task in stream_out_top["tasks"]]
        self.assertIn("sm8466_top_streamOut_TOP", task_names)
        self.assertIn("RCXT", task_names)
        rcxt_job = next(t for t in stream_out_top["tasks"] if t["name"] == "RCXT")["jobs"][0]
        self.assertEqual(rcxt_job["inputs"], ["../GDS/DM.gds"])

    def test_rcxt_omitted_when_flag_off(self):
        context = BuildContext(settings=base_settings(FLAG_DMF="1"), blocks=[])
        flow = PVFlowBuilder.build(context)
        stream_out_top = next(s for s in flow["stages"] if s["name"] == "streamOut_TOP")
        self.assertEqual(len(stream_out_top["tasks"]), 1)

    def test_lvs_parallel_with_drc_after_gds2oas(self):
        context = BuildContext(
            settings=base_settings(FLAG_DRCBE="1", FLAG_LVS="1"),
            blocks=[],
        )
        flow = PVFlowBuilder.build(context)
        post_stage = flow["stages"][-1]
        self.assertEqual(post_stage["name"], "Verify")
        task_names = [task["name"] for task in post_stage["tasks"]]
        self.assertEqual(task_names, ["DRC_BE", "LVS"])
        lvs_job = next(t for t in post_stage["tasks"] if t["name"] == "LVS")["jobs"][0]
        self.assertEqual(lvs_job["command"], "../flow/run_lvs.sh")
        self.assertEqual(
            lvs_job["inputs"],
            [
                "hcell",
                "lvs.calibre",
                "layout.spi",
                "../GDS/sm8466_top.oas",
                "../spi/sm8466_top.cdl",
            ],
        )
        self.assertEqual(lvs_job["outputs"], ["lvs.rep"])

    def test_drc_lvs_link_top_out_when_oasii_off(self):
        context = BuildContext(
            settings=base_settings(USE_OASII="0", FLAG_DRCBE="1", FLAG_LVS="1"),
            blocks=[],
        )
        flow = PVFlowBuilder.build(context)
        stream_out = next(s for s in flow["stages"] if s["name"] == "streamOut_TOP")
        job_names = [j["name"] for t in stream_out["tasks"] for j in t["jobs"]]
        self.assertNotIn("gds2oas", job_names)
        post_stage = flow["stages"][-1]
        drc = next(t for t in post_stage["tasks"] if t["name"] == "DRC_BE")["jobs"][0]
        lvs = next(t for t in post_stage["tasks"] if t["name"] == "LVS")["jobs"][0]
        self.assertEqual(drc["inputs"], ["../GDS/sm8466_top.gds.gz"])
        self.assertIn("../GDS/sm8466_top.gds.gz", lvs["inputs"])
        self.assertNotIn(".oas", "".join(lvs["inputs"]))

    def test_lvs_omitted_when_flag_off(self):
        context = BuildContext(settings=base_settings(FLAG_DRCBE="1"), blocks=[])
        flow = PVFlowBuilder.build(context)
        post_stage = flow["stages"][-1]
        self.assertEqual([task["name"] for task in post_stage["tasks"]], ["DRC_BE"])


if __name__ == "__main__":
    unittest.main()
