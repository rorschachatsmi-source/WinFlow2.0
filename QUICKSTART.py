#!/usr/bin/env python3
"""
QUICK START GUIDE - Flow Runner Enhanced Edition

Three ways to run your flows:
"""

import subprocess
import sys

def option1_original():
    """Option 1: Keep using the original (no changes required)"""
    print("Option 1: Original flow runner")
    print("Command: python flow_runner.py")
    print("Result: Works exactly as before\n")

def option2_cli():
    """Option 2: Use refactored core with CLI"""
    print("Option 2: Refactored core (recommended for automation)")
    print("Command: python flow_runner_legacy.py flow.json")
    print("Advantages:")
    print("  - Structured logging (both file and console)")
    print("  - Better error messages")
    print("  - Type-safe code")
    print("  - Easier to integrate with other scripts\n")

def option3_gui():
    """Option 3: Use GUI for interactive monitoring"""
    print("Option 3: Professional GUI (recommended for interactive use)")
    print("Command: python flow_runner_gui.py")
    print("Features:")
    print("  - Real-time job monitoring")
    print("  - Log filtering by level")
    print("  - Visual status display")
    print("  - Easy config file selection")
    print("  - Perfect for debugging\n")

def print_menu():
    """Print menu"""
    print("=" * 60)
    print("FLOW RUNNER - Enhanced Edition Quick Start")
    print("=" * 60)
    print()
    
    option1_original()
    option2_cli()
    option3_gui()
    
    print("=" * 60)
    print("QUICK SETUP")
    print("=" * 60)
    print("\n1. Prepare your flow configuration in flow.json")
    print("2. Ensure LSF cluster is accessible (bsub, bjobs commands)")
    print("3. Choose your preferred method above")
    print("4. Run the command")
    print()
    print("Files created:")
    print("  ✓ flow_runner_core.py     - Refactored core module")
    print("  ✓ flow_runner_gui.py      - GUI application")
    print("  ✓ flow_runner_legacy.py   - CLI wrapper for backward compatibility")
    print("  ✓ flow_runner_README.md   - Detailed documentation")
    print()
    print("=" * 60)

def launch_gui():
    """Launch GUI directly"""
    try:
        print("Launching Flow Runner GUI...")
        subprocess.run([sys.executable, "flow_runner_gui.py"])
    except Exception as e:
        print(f"Error launching GUI: {e}")
        print("Try running: python flow_runner_gui.py")

if __name__ == "__main__":
    print_menu()
    
    # Ask user what to do
    print("\nWhat would you like to do?")
    print("1. Launch GUI")
    print("2. Show detailed documentation")
    print("3. Run with current config (CLI)")
    print("0. Exit")
    
    choice = input("\nEnter choice (0-3): ").strip()
    
    if choice == "1":
        launch_gui()
    elif choice == "2":
        try:
            with open("flow_runner_README.md") as f:
                print("\n" + f.read())
        except FileNotFoundError:
            print("Documentation file not found")
    elif choice == "3":
        subprocess.run([sys.executable, "flow_runner_legacy.py", "flow.json"])
    else:
        print("Exiting...")
