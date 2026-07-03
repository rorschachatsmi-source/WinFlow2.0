"""Tests for flow_generator GUI document helpers."""

import json
import tempfile
import unittest
from pathlib import Path

from flow_generator.core.models import make_flow, make_job, make_stage, make_task
from flow_generator.gui.document import (
    TemplateOptions,
    apply_template,
    blank_template,
    document_to_flow,
    flow_to_document,
    pv_template,
)


class TestFlowDocument(unittest.TestCase):
    def test_blank_template_has_one_job(self):
        doc = blank_template()
        jobs = list(doc.iter_jobs())
        self.assertEqual(len(jobs), 1)
        self.assertEqual(doc.flow_name, "custom_flow")

    def test_round_trip_flow(self):
        flow = make_flow(
            "demo",
            [
                make_stage(
                    "s1",
                    [
                        make_task(
                            "t1",
                            [
                                make_job("j1", "echo hi", ["a.txt"], ["b.txt"], "q1", 2),
                            ],
                        )
                    ],
                )
            ],
            poll_interval=15,
        )
        doc = flow_to_document(flow)
        self.assertEqual(doc.flow_name, "demo")
        self.assertEqual(doc.poll_interval, 15)
        self.assertIn(len(doc.positions), (1,))

        rebuilt = document_to_flow(doc)
        self.assertEqual(rebuilt, flow)

    def test_blank_template_default_resources(self):
        doc = blank_template()
        job = next(doc.iter_jobs())[2]
        self.assertEqual(job["queue"], "tpdsd1")
        self.assertEqual(job["cpu"], 4)
        self.assertNotIn("machine", job)

    def test_pv_template_without_references(self):
        doc = pv_template()
        stage_names = [stage["name"] for stage in doc.stages]
        self.assertIn("Merge", stage_names)
        self.assertIn("streamOut_TOP", stage_names)
        for _s, _t, job in doc.iter_jobs():
            self.assertEqual(job.get("queue"), "tpdsd1")
            self.assertEqual(job.get("cpu"), 4)

    def test_pv_template_applies_custom_resources(self):
        opts = TemplateOptions(queue="myqueue", machine="host1 host2", cpu=8)
        doc = pv_template(opts)
        for _s, _t, job in doc.iter_jobs():
            self.assertEqual(job.get("queue"), "myqueue")
            self.assertEqual(job.get("cpu"), 8)
            self.assertEqual(job.get("machine"), "host1 host2")

    def test_pv_template_with_setting_file(self):
        content = '\n'.join(
            [
                'set TOP_MODULE = "chip_top"',
                'set MACHINE_QUEUE = "old_queue"',
                'set MACHINE_CPU = "2"',
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            setting = Path(tmp) / "setting.sh"
            setting.write_text(content, encoding="utf-8")
            doc = pv_template(TemplateOptions(setting_path=setting, queue="tpdsd1", cpu=4))
        queues = {job.get("queue") for _s, _t, job in doc.iter_jobs()}
        self.assertEqual(queues, {"tpdsd1"})

    def test_apply_template_unknown_raises(self):
        with self.assertRaises(KeyError):
            apply_template("unknown")

    def test_document_export_is_valid_json(self):
        doc = apply_template("blank")
        flow = document_to_flow(doc)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "flow.json"
            out.write_text(json.dumps(flow, indent=2), encoding="utf-8")
            loaded = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(loaded["flow_name"], flow["flow_name"])
        self.assertIn("stages", loaded)


if __name__ == "__main__":
    unittest.main()
