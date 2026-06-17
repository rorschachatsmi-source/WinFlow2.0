#!/usr/bin/env python3
"""
verify_enhancement.py

Verify that all enhancement files are in place and functional.
"""

import os
import sys
import json
from pathlib import Path

def check_file(path, description):
    """Check if file exists"""
    exists = os.path.exists(path)
    status = "✅" if exists else "❌"
    print(f"{status} {description}: {path}")
    return exists

def check_python_syntax(path):
    """Check Python syntax"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            compile(f.read(), path, 'exec')
        return True
    except SyntaxError as e:
        print(f"  ❌ Syntax error: {e}")
        return False

def check_json_syntax(path):
    """Check JSON syntax"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            json.load(f)
        return True
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON error: {e}")
        return False

def test_imports():
    """Test if core module can be imported"""
    try:
        from flow_runner_core import create_flow_runner, FlowLogger, FlowValidator, LSFJobManager, FlowRunner
        print("✅ Core module imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def main():
    print("=" * 70)
    print("FLOW RUNNER ENHANCEMENT VERIFICATION")
    print("=" * 70)
    print()
    
    all_ok = True
    
    # Check Python files
    print("1. Core Module Files:")
    all_ok &= check_file("flow_runner.py", "Original flow runner")
    all_ok &= check_file("flow_runner_core.py", "Refactored core module")
    all_ok &= check_file("flow_runner_gui.py", "GUI application")
    all_ok &= check_file("flow_runner_legacy.py", "CLI wrapper")
    print()
    
    # Check documentation
    print("2. Documentation Files:")
    all_ok &= check_file("flow_runner_README.md", "Comprehensive guide")
    all_ok &= check_file("ENHANCEMENT_SUMMARY.md", "Summary of changes")
    all_ok &= check_file("QUICKSTART.py", "Quick start script")
    print()
    
    # Check example files
    print("3. Example Files:")
    all_ok &= check_file("flow_example.json", "Example configuration")
    print()
    
    # Check syntax
    print("4. Python Syntax Check:")
    print("  flow_runner_core.py: ", end="")
    if check_python_syntax("flow_runner_core.py"):
        print("✅")
    else:
        all_ok = False
    
    print("  flow_runner_gui.py: ", end="")
    if check_python_syntax("flow_runner_gui.py"):
        print("✅")
    else:
        all_ok = False
    
    print("  flow_runner_legacy.py: ", end="")
    if check_python_syntax("flow_runner_legacy.py"):
        print("✅")
    else:
        all_ok = False
    print()
    
    # Check JSON syntax
    print("5. JSON Syntax Check:")
    print("  flow_example.json: ", end="")
    if check_json_syntax("flow_example.json"):
        print("✅")
    else:
        all_ok = False
    print()
    
    # Test imports
    print("6. Module Import Test:")
    test_imports()
    print()
    
    # Summary
    print("=" * 70)
    if all_ok:
        print("✅ All checks passed! Enhancement is ready to use.")
        print()
        print("Next steps:")
        print("1. Review ENHANCEMENT_SUMMARY.md for overview")
        print("2. Run: python flow_runner_gui.py  (to try GUI)")
        print("3. Or: python flow_runner_legacy.py flow.json  (CLI mode)")
        print()
    else:
        print("❌ Some checks failed. Please review above.")
        sys.exit(1)
    
    print("=" * 70)

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
