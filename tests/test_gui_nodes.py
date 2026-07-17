"""Tests for predefined job-node library."""

import json
import tempfile
import unittest
from pathlib import Path

from flow_generator.gui.nodes import (
    builtin_node_jobs,
    extract_flow_name,
    extract_job_from_flow,
    generate_builtin_nodes,
    list_node_names,
    list_nodes_by_flow,
    load_node,
    load_node_flow,
    node_dir,
)


class TestJobNodes(unittest.TestCase):
    def test_builtin_catalog_covers_apr_and_pv(self):
        stems = {stem for stem, _flow, _job in builtin_node_jobs()}
        for required in (
            "blank_job",
            "01_floorplan",
            "04_postcts_opt",
            "06_postroute_opt",
            "SPI",
            "laker_In",
            "laker_Out",
            "sub_laker",
            "Calibre_dmf",
            "gds2oas",
            "DRC",
            "LVS",
        ):
            self.assertIn(required, stems)

    def test_builtin_flow_categories(self):
        by_flow = {}
        for stem, flow, _job in builtin_node_jobs():
            by_flow.setdefault(flow, []).append(stem)
        self.assertIn("blank_job", by_flow["custom_flow"])
        self.assertIn("01_floorplan", by_flow["APR"])
        self.assertIn("SPI", by_flow["PV"])

    def test_repo_node_dir_populated(self):
        names = list_node_names()
        self.assertGreaterEqual(len(names), 20)
        self.assertIn("SPI", names)
        job = load_node("SPI")
        self.assertEqual(job["name"], "SPI")
        self.assertTrue(job["command"])
        self.assertEqual(extract_flow_name(load_node_flow("SPI")), "PV")
        self.assertEqual(extract_flow_name(load_node_flow("01_floorplan")), "APR")
        self.assertEqual(extract_flow_name(load_node_flow("blank_job")), "custom_flow")

    def test_list_nodes_by_flow_order(self):
        grouped = list_nodes_by_flow()
        names = [flow for flow, _jobs in grouped]
        self.assertEqual(names[:3], ["PV", "APR", "custom_flow"])
        pv_jobs = dict(grouped)["PV"]
        self.assertTrue(any(stem == "SPI" for stem, _display in pv_jobs))

    def test_round_trip_write_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_builtin_nodes(root)
            names = list_node_names(root)
            self.assertIn("01_floorplan", names)
            job = load_node("01_floorplan", root)
            self.assertEqual(job["name"], "01_floorplan")
            self.assertTrue(job["outputs"])

            path = root / "SPI.json"
            with path.open(encoding="utf-8") as fp:
                data = json.load(fp)
            self.assertEqual(data["flow_name"], "PV")
            extracted = extract_job_from_flow(data)
            self.assertEqual(extracted["name"], "SPI")

            grouped = list_nodes_by_flow(root)
            self.assertEqual([f for f, _ in grouped][:3], ["PV", "APR", "custom_flow"])

    def test_node_dir_default(self):
        self.assertTrue(str(node_dir()).endswith("node") or node_dir().name == "node")


if __name__ == "__main__":
    unittest.main()
