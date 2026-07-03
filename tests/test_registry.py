"""Tests for flow builder registry."""

import unittest

from flow_generator.core.builder import FlowBuilder
from flow_generator.core.context import BuildContext
from flow_generator.core.models import Flow, make_flow
from flow_generator.core.registry import get_builder, list_flows, register
from flow_generator.flows import apr, pv  # noqa: F401


class TestRegistry(unittest.TestCase):
    def test_pv_is_registered(self):
        self.assertIn("pv", list_flows())
        self.assertEqual(get_builder("pv").flow_type, "pv")
        self.assertEqual(get_builder("PV").flow_type, "pv")

    def test_apr_is_registered(self):
        self.assertIn("apr", list_flows())
        self.assertEqual(get_builder("apr").flow_type, "apr")

    def test_unknown_flow_raises_key_error(self):
        with self.assertRaises(KeyError):
            get_builder("does_not_exist")

    def test_register_decorator(self):
        @register("test_flow")
        class TestFlowBuilder(FlowBuilder):
            @classmethod
            def validate_context(cls, context: BuildContext):
                return []

            @classmethod
            def build(cls, context: BuildContext) -> Flow:
                return make_flow("test", [])

        self.assertIn("test_flow", list_flows())
        self.assertIs(get_builder("test_flow"), TestFlowBuilder)


if __name__ == "__main__":
    unittest.main()
