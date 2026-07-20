#!/usr/bin/env python3
"""
winflow_gui.py

Unified WinFlow window: Runner and Generator as notebook tabs, with Sync
from Generator into Runner.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import flow_generator_gui as gen_gui
import flow_runner_gui as run_gui
from winflow_config import get_config


class WinFlowApp(tk.Tk):
    """Single window hosting Runner and Generator tabs."""

    def __init__(self):
        super().__init__()
        # Pin fonts before any widgets — prevents Linux X11 emoji-font crashes.
        run_gui.configure_safe_tk_fonts(self)
        gen_gui.configure_safe_tk_fonts(self)

        gui_cfg = get_config().gui
        self.title("WinFlow")
        self.geometry(gui_cfg.runner_window_size)
        self.minsize(960, 640)
        self.configure(bg=run_gui.COLORS["bg"])

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=run_gui.COLORS["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            padding=[18, 8],
            font=(run_gui.UI_FONT, 10),
        )
        style.map(
            "TNotebook.Tab",
            background=[
                ("selected", run_gui.COLORS["panel"]),
                ("!selected", run_gui.COLORS["bg"]),
            ],
            foreground=[
                ("selected", run_gui.COLORS["text"]),
                ("!selected", run_gui.COLORS["muted"]),
            ],
        )

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        runner_tab = tk.Frame(notebook, bg=run_gui.COLORS["bg"])
        generator_tab = tk.Frame(notebook, bg=gen_gui.COLORS["bg"])
        notebook.add(runner_tab, text="  Runner  ")
        notebook.add(generator_tab, text="  Generator  ")

        self.generator = gen_gui.FlowGeneratorPanel(generator_tab)
        self.generator.pack(fill=tk.BOTH, expand=True)

        self.runner = run_gui.FlowRunnerGUI(runner_tab, sync_source=self.generator)


def main():
    app = WinFlowApp()
    app.mainloop()


if __name__ == "__main__":
    main()
