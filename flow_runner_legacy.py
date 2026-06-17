#!/usr/bin/env python3
"""
flow_runner_legacy.py

Backward compatible wrapper using the refactored core module.
Original flow_runner.py functionality is preserved here.
"""

import json
import sys
from flow_runner_core import create_flow_runner


def main():
    """Main entry point - maintains compatibility with original flow_runner.py"""
    config_file = sys.argv[1] if len(sys.argv) > 1 else "flow.json"
    
    try:
        with open(config_file, "r") as fp:
            config = json.load(fp)
        
        # Create runner with logging to file
        runner = create_flow_runner(log_file="logs/flow_runner.log")
        runner.run_flow(config)
        
    except FileNotFoundError:
        print(f"Error: Configuration file not found: {config_file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {config_file}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
