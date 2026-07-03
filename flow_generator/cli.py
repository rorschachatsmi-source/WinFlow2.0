"""Command-line interface for flow generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from flow_generator.core.context import BuildContext
from flow_generator.core.io import write_flow
from flow_generator.core.registry import get_builder, list_flows
from flow_generator.flows import apr, pv  # noqa: F401 — register built-in flows
from flow_generator.parsers import parse_block_stream, parse_setting_sh
from winflow_config import get_config


def build_parser() -> argparse.ArgumentParser:
    gen_cfg = get_config().generator
    parser = argparse.ArgumentParser(
        description="Generate WinFlow flow.json from flow-specific inputs.",
    )
    parser.add_argument(
        "--flow",
        default=gen_cfg.default_flow_type,
        help=f"Flow type to generate (default: {gen_cfg.default_flow_type})",
    )
    parser.add_argument(
        "--setting",
        default=gen_cfg.default_setting_file,
        help=f"Path to setting.sh (default: {gen_cfg.default_setting_file})",
    )
    parser.add_argument(
        "--blocks",
        default=gen_cfg.default_blocks_file,
        help=f"Path to block_stream.list (default: {gen_cfg.default_blocks_file})",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=gen_cfg.default_output_file,
        help=f"Output flow.json path (default: {gen_cfg.default_output_file})",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List registered flow types and exit",
    )
    return parser


def run(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        for name in list_flows():
            print(name)
        return 0

    try:
        builder_cls = get_builder(args.flow)
    except KeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    setting_path = Path(args.setting)
    blocks_path = Path(args.blocks)
    output_path = Path(args.output)

    if not setting_path.exists():
        print(f"ERROR: setting file not found: {setting_path}", file=sys.stderr)
        return 1

    context = BuildContext(
        settings=parse_setting_sh(setting_path),
        blocks=parse_block_stream(blocks_path),
        setting_path=setting_path,
        blocks_path=blocks_path,
        output_path=output_path,
    )

    errors = builder_cls.validate_context(context)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    flow = builder_cls.build(context)
    write_flow(flow, output_path)
    print(f"Generated {output_path}")
    return 0


def main() -> None:
    raise SystemExit(run())
