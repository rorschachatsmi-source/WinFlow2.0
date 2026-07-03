#!/usr/bin/env python3
"""
Generate flow.json for WinFlow.

Backward-compatible wrapper around the flow_generator package.
Default flow type is PV (reads setting.sh and block_stream.list).

Examples:
  python flow_generator.py
  python flow_generator.py --flow pv -o flow.json
  python -m flow_generator --list
"""

from flow_generator.cli import main

if __name__ == "__main__":
    main()
