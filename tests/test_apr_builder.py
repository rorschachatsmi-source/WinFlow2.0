"""Tests for APR flow builder."""

import unittest

from flow_generator.flows.apr.builder import (
    apr_job_names,
    apr_job_output,
    build_apr_stage,
    format_apr_suffix,
)
from flow_generator.gui.document import TemplateOptions, apr_template


class TestAPRBuilder(unittest.TestCase):
    def test_format_apr_suffix(self):
        self.assertEqual(format_apr_suffix(""), "")
        self.assertEqual(format_apr_suffix("top"), "_top")

    def test_job_names_without_prefix_or_current(self):
        self.assertEqual(
            apr_job_names(),
            [
                "01_floorplan",
                "02_prects_opt",
                "03_cts_concurrent",
                "05_route.tcl",
                "06_postroute_opt",
            ],
        )

    def test_job_names_with_prefix_and_current(self):
        self.assertEqual(
            apr_job_names(prefix="chip", is_current=True),
            [
                "01_floorplan_chip",
                "02_prects_opt_chip",
                "03_cts_concurrent_chip",
                "04_postcts_opt_chip",
                "05_route.tcl_chip",
                "06_postroute_opt_chip",
            ],
        )

    def test_job_output_path(self):
        self.assertEqual(
            apr_job_output("01_floorplan_top"),
            "01_floorplan_top/DB/01_floorplan_top.enc.dat",
        )

    def test_build_stage_chains_inputs(self):
        stage = build_apr_stage(prefix="top", is_current=False, queue="q1", cpu="8")
        jobs = stage["tasks"][0]["jobs"]
        self.assertEqual(len(jobs), 5)
        self.assertEqual(jobs[0]["name"], "01_floorplan_top")
        self.assertEqual(jobs[0]["inputs"], [])
        self.assertEqual(jobs[0]["command"], "./run_stage 01_floorplan_top")
        self.assertEqual(
            jobs[0]["outputs"],
            ["01_floorplan_top/DB/01_floorplan_top.enc.dat"],
        )
        self.assertEqual(jobs[1]["inputs"], jobs[0]["outputs"])
        self.assertEqual(jobs[2]["inputs"], jobs[1]["outputs"])
        self.assertEqual(jobs[3]["inputs"], jobs[2]["outputs"])
        self.assertEqual(jobs[4]["inputs"], jobs[3]["outputs"])

    def test_includes_postcts_when_current(self):
        stage = build_apr_stage(is_current=True)
        names = [job["name"] for job in stage["tasks"][0]["jobs"]]
        self.assertIn("04_postcts_opt", names)

    def test_apr_template_from_gui_options(self):
        doc = apr_template(TemplateOptions(apr_prefix="blk", apr_is_current=True, queue="tpdsd1", cpu=4))
        self.assertEqual(doc.flow_name, "APR")
        self.assertEqual(doc.stages[0]["name"], "APR")
        self.assertEqual(doc.stages[0]["tasks"][0]["name"], "apr")
        names = [job["name"] for _s, _t, job in doc.iter_jobs()]
        self.assertEqual(names[0], "01_floorplan_blk")


if __name__ == "__main__":
    unittest.main()
