#!/usr/bin/env python3
"""
winflow_gui.py

Unified WinFlow window: Runner and Generator as notebook tabs, with Sync
from Generator into Runner.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from flow_generator_gui import FlowGeneratorPanel
from flow_runner_gui import FlowRunnerGUI, COLORS, UI_FONT
from winflow_config import get_config


class WinFlowApp(tk.Tk):
    """Single window hosting Runner and Generator tabs."""

    def __init__(self):
        super().__init__()
        gui_cfg = get_config().gui
        self.title("WinFlow")
        self.geometry(gui_cfg.runner_window_size)
        self.minsize(960, 640)
        self.configure(bg=COLORS["bg"])

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=COLORS["bg"])
        style.configure("TNotebook.Tab", padding=[16, 6], font=(UI_FONT, 10))

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        runner_tab = tk.Frame(notebook, bg=COLORS["bg"])
        generator_tab = tk.Frame(notebook, bg=COLORS["bg"])
        notebook.add(runner_tab, text="  Runner  ")
        notebook.add(generator_tab, text="  Generator  ")

        self.generator = FlowGeneratorPanel(generator_tab)
        self.generator.pack(fill=tk.BOTH, expand=True)

        self.runner = FlowRunnerGUI(runner_tab, sync_source=self.generator)


def main():
    app = WinFlowApp()
    app.mainloop()


if __name__ == "__main__":
    main()
