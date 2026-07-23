"""Tests for PV SPI, RCXT, and LVS stage builders."""

import unittest

from flow_generator.flows.pv.config import PVConfig
from flow_generator.flows.pv.paths import PVPaths
from flow_generator.flows.pv.stages.spi_rcxt_lvs import (
    lvs_task,
    rcxt_task,
    spi_task,
)
from flow_generator.flows.pv.stages.stream_out import stream_out_top_stage
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


class TestPVSpiRcxtLvs(unittest.TestCase):
    def test_spi_task_command_inputs_outputs(self):
        task = spi_task(sample_config())
        job = task["jobs"][0]
        self.assertEqual(job["name"], "SPI")
        self.assertEqual(job["command"], "../flow/run_spi.sh")
        self.assertEqual(
            job["inputs"],
            ["../DATA/ref.spi", "../DATA/netlist.pg.v.gz"],
        )
        self.assertEqual(job["outputs"], ["../spi/sm8466_top.cdl"])

    def test_rcxt_task_command_inputs_outputs(self):
        task = rcxt_task(sample_config())
        job = task["jobs"][0]
        self.assertEqual(job["name"], "RCXT")
        self.assertEqual(job["command"], "../flow/run_rcxt.sh")
        self.assertEqual(job["inputs"], ["../GDS/DM.gds"])
        self.assertEqual(job["outputs"], ["flag_starrc_done"])

    def test_stream_out_top_includes_rcxt_when_flag_set(self):
        stage = stream_out_top_stage(
            sample_config(),
            ["../LakerBZ/create_text_from_APRgds.tcl"],
            {"FLAG_RCXT": "1"},
        )
        task_names = [task["name"] for task in stage["tasks"]]
        self.assertEqual(len(task_names), 2)
        self.assertIn("RCXT", task_names)

    def test_stream_out_top_omits_rcxt_when_flag_off(self):
        stage = stream_out_top_stage(
            sample_config(),
            ["../LakerBZ/create_text_from_APRgds.tcl"],
            {},
        )
        self.assertEqual(len(stage["tasks"]), 1)

    def test_stream_out_top_includes_gds2oas_by_default(self):
        stage = stream_out_top_stage(
            sample_config(),
            ["../LakerBZ/create_text_from_APRgds.tcl"],
            {},
        )
        names = [job["name"] for job in stage["tasks"][0]["jobs"]]
        self.assertIn("gds2oas", names)

    def test_stream_out_top_omits_gds2oas_when_use_oasii_off(self):
        stage = stream_out_top_stage(
            sample_config(),
            ["../LakerBZ/create_text_from_APRgds.tcl"],
            {"USE_OASII": "0"},
        )
        names = [job["name"] for job in stage["tasks"][0]["jobs"]]
        self.assertNotIn("gds2oas", names)
        self.assertEqual(names[-1], "sm8466_top_Out")

    def test_lvs_task_command_inputs_outputs(self):
        task = lvs_task(sample_config())
        job = task["jobs"][0]
        self.assertEqual(task["name"], "LVS")
        self.assertEqual(job["command"], "../flow/run_lvs.sh")
        self.assertEqual(
            job["inputs"],
            [
                "../DATA/hcell",
                "../GDS/sm8466_top.oas",
                "../spi/sm8466_top.cdl",
            ],
        )
        self.assertEqual(job["outputs"], ["lvs.rep"])

    def test_lvs_task_uses_top_out_gds_when_oasii_off(self):
        task = lvs_task(sample_config(), {"USE_OASII": "0"})
        job = task["jobs"][0]
        self.assertEqual(
            job["inputs"],
            [
                "../DATA/hcell",
                "../GDS/sm8466_top.gds.gz",
                "../spi/sm8466_top.cdl",
            ],
        )


if __name__ == "__main__":
    unittest.main()
