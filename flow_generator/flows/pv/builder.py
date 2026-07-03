"""PV (physical verification) flow builder."""

from __future__ import annotations

from typing import List

from flow_generator.core.builder import FlowBuilder
from flow_generator.core.context import BuildContext
from flow_generator.core.models import Flow, Stage, make_flow
from flow_generator.core.registry import register
from flow_generator.flows.pv.config import PVConfig
from winflow_config import get_config
from flow_generator.flows.pv.stages import (
    block_blitz_outputs,
    build_merge_stage,
    pre_stream_in_apr_stage,
    stream_in_apr_stage,
    stream_in_sub_dummy_stage,
    stream_in_sub_stage,
    stream_out_apr_stage,
    stream_out_top_stage,
    verify_stage,
)


@register("pv")
class PVFlowBuilder(FlowBuilder):
    """Build the PV flow from setting.sh and block_stream.list."""

    @classmethod
    def validate_context(cls, context: BuildContext) -> List[str]:
        errors: List[str] = []
        settings = context.settings

        for key in get_config().pv.required_settings:
            if key not in settings or not str(settings[key]).strip():
                errors.append(f"Missing required setting: {key}")

        if settings.get("FLAG_DMEXCL_PTN", "0") == "1" and not context.blocks:
            errors.append("FLAG_DMEXCL_PTN=1 requires non-empty block_stream.list")

        return errors

    @classmethod
    def build(cls, context: BuildContext) -> Flow:
        config = PVConfig.from_context(context)
        stages: List[Stage] = []

        if config.dmexcl_ptn:
            stages.append(stream_in_sub_dummy_stage(context.blocks, config))
            stages.append(pre_stream_in_apr_stage(context.blocks, config))
            stages.append(stream_out_apr_stage(config))
            stages.append(stream_in_apr_stage(config, input_from_stream_out=True))
        else:
            stream_in_sub = stream_in_sub_stage(context.blocks, config)
            if stream_in_sub is not None:
                stages.append(stream_in_sub)
            sub_outputs = block_blitz_outputs(context.blocks, config) if context.blocks else None
            stages.append(stream_in_apr_stage(config, sub_outputs))
            stages.append(stream_out_apr_stage(config))

        merge_stage, laker_outputs = build_merge_stage(context.settings, config)
        stages.append(merge_stage)
        stages.append(stream_out_top_stage(config, laker_outputs))

        verify = verify_stage(context.settings, config)
        if verify is not None:
            stages.append(verify)

        pv_cfg = get_config().pv
        gen_cfg = get_config().generator
        return make_flow(pv_cfg.flow_name, stages, poll_interval=gen_cfg.poll_interval)
