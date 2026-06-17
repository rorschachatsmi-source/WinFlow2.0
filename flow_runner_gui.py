#!/data1/util/Python-3.9.2/bin/python3
"""
flow_runner_gui.py

GUI wrapper for flow runner with real-time logging and job monitoring.
"""

import json
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pathlib import Path
import threading
from datetime import datetime

from flow_runner_core import create_flow_runner, FlowLogger


class FlowRunnerGUI:
    """GUI for Flow Runner with logging display"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Flow Runner - GUI")
        self.root.geometry("1000x700")
        self.runner = None
        self.log_messages = []
        self.is_running = False

        self._setup_ui()

    def _setup_ui(self):
        """Setup GUI components"""
        # Top frame: Configuration
        config_frame = tk.Frame(self.root, relief=tk.SUNKEN, borderwidth=2)
        config_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        tk.Label(config_frame, text="Flow Config:").pack(side=tk.LEFT, padx=5)
        self.config_path_var = tk.StringVar(value="flow.json")
        config_entry = tk.Entry(config_frame, textvariable=self.config_path_var, width=40)
        config_entry.pack(side=tk.LEFT, padx=5)

        browse_btn = tk.Button(config_frame, text="Browse", command=self._browse_config)
        browse_btn.pack(side=tk.LEFT, padx=5)

        # Separator
        sep1 = tk.Frame(self.root, height=2, bd=1, relief=tk.SUNKEN)
        sep1.pack(fill=tk.X, padx=5, pady=5)

        # Main content frame
        content_frame = tk.Frame(self.root)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel: Control
        left_frame = tk.Frame(content_frame, relief=tk.RAISED, borderwidth=2, width=150)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        left_frame.pack_propagate(False)

        tk.Label(left_frame, text="Control", font=("Arial", 10, "bold")).pack(pady=10)

        self.run_btn = tk.Button(
            left_frame, text="▶ Run Flow", command=self._run_flow,
            bg="#4CAF50", fg="white", width=15, height=2, font=("Arial", 9, "bold")
        )
        self.run_btn.pack(pady=10, padx=5)

        self.stop_btn = tk.Button(
            left_frame, text="⏹ Stop", command=self._stop_flow,
            bg="#f44336", fg="white", width=15, height=2, state=tk.DISABLED,
            font=("Arial", 9, "bold")
        )
        self.stop_btn.pack(pady=10, padx=5)

        clear_btn = tk.Button(
            left_frame, text="🗑 Clear Logs", command=self._clear_logs,
            bg="#2196F3", fg="white", width=15, height=2,
            font=("Arial", 9, "bold")
        )
        clear_btn.pack(pady=10, padx=5)

        # Status frame
        status_frame = tk.LabelFrame(left_frame, text="Status", padx=5, pady=5)
        status_frame.pack(pady=20, padx=5, fill=tk.X)

        self.status_label = tk.Label(
            status_frame, text="Ready", fg="green", font=("Arial", 9, "bold"), wraplength=130
        )
        self.status_label.pack()

        # Filter frame
        filter_frame = tk.LabelFrame(left_frame, text="Log Filter", padx=5, pady=5)
        filter_frame.pack(pady=10, padx=5, fill=tk.X)

        self.show_debug = tk.BooleanVar(value=False)
        tk.Checkbutton(filter_frame, text="Debug", variable=self.show_debug,
                       command=self._update_log_display).pack(anchor=tk.W)

        self.show_info = tk.BooleanVar(value=True)
        tk.Checkbutton(filter_frame, text="Info", variable=self.show_info,
                       command=self._update_log_display).pack(anchor=tk.W)

        self.show_warning = tk.BooleanVar(value=True)
        tk.Checkbutton(filter_frame, text="Warning", variable=self.show_warning,
                       command=self._update_log_display).pack(anchor=tk.W)

        self.show_error = tk.BooleanVar(value=True)
        tk.Checkbutton(filter_frame, text="Error", variable=self.show_error,
                       command=self._update_log_display).pack(anchor=tk.W)

        # Right panel: Log display
        right_frame = tk.LabelFrame(content_frame, text="Execution Log", padx=5, pady=5)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)

        self.log_text = scrolledtext.ScrolledText(
            right_frame, height=30, width=80, wrap=tk.WORD,
            font=("Courier", 9), bg="#f5f5f5"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Configure tags for different log levels
        self.log_text.tag_configure("DEBUG", foreground="#808080")
        self.log_text.tag_configure("INFO", foreground="#2196F3")
        self.log_text.tag_configure("WARNING", foreground="#ff9800")
        self.log_text.tag_configure("ERROR", foreground="#f44336")

        # Bottom frame: Progress and Stats
        bottom_frame = tk.Frame(self.root, relief=tk.SUNKEN, borderwidth=2)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = tk.Scale(
            bottom_frame, from_=0, to=100, orient=tk.HORIZONTAL,
            variable=self.progress_var, state=tk.DISABLED
        )
        self.progress_bar.pack(fill=tk.X, padx=5, pady=5)

        self.stats_label = tk.Label(bottom_frame, text="Ready to run", font=("Arial", 9))
        self.stats_label.pack(anchor=tk.W, padx=5, pady=5)

    def _browse_config(self):
        """Open file dialog to select config file"""
        file_path = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if file_path:
            self.config_path_var.set(file_path)

    def _log_callback(self, message: str, level: str):
        """Callback for log messages from runner"""
        self.log_messages.append((level, message, datetime.now().strftime("%H:%M:%S")))
        self.root.after(0, self._update_log_display)

    def _update_log_display(self):
        """Update log display with filtered messages"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)

        for level, message, timestamp in self.log_messages:
            # Apply filter
            if level == "DEBUG" and not self.show_debug.get():
                continue
            if level == "INFO" and not self.show_info.get():
                continue
            if level == "WARNING" and not self.show_warning.get():
                continue
            if level == "ERROR" and not self.show_error.get():
                continue

            # Format and display
            log_line = f"[{timestamp}] [{level}] {message}\n"
            self.log_text.insert(tk.END, log_line, level)

        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def _clear_logs(self):
        """Clear all logs"""
        self.log_messages = []
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self._update_status("Ready")

    def _run_flow(self):
        """Run flow in separate thread"""
        config_path = self.config_path_var.get()

        if not Path(config_path).exists():
            messagebox.showerror("Error", f"Config file not found: {config_path}")
            return

        # Load config
        try:
            with open(config_path, "r") as fp:
                config = json.load(fp)
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Invalid JSON: {e}")
            return

        self.is_running = True
        self.run_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self._update_status("Running...")

        # Run in separate thread
        thread = threading.Thread(
            target=self._run_flow_thread,
            args=(config,),
            daemon=True
        )
        thread.start()

    def _run_flow_thread(self, config):
        """Thread worker for flow execution"""
        try:
            log_file = f"logs/flow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            self.runner = create_flow_runner(log_file=log_file, log_callback=self._log_callback)
            self._log_callback("Starting flow execution", "INFO")
            self.runner.run_flow(config)
            self._update_status("Completed ✓", "#4CAF50")
            messagebox.showinfo("Success", "Flow completed successfully!")
        except Exception as e:
            self._log_callback(f"Error: {str(e)}", "ERROR")
            self._update_status(f"Failed: {str(e)[:50]}", "#f44336")
            messagebox.showerror("Error", f"Flow execution failed:\n{str(e)}")
        finally:
            self.is_running = False
            self.run_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)

    def _stop_flow(self):
        """Stop flow execution (placeholder)"""
        messagebox.showwarning("Info", "Flow stop not implemented yet.\nJob will continue running on LSF cluster.")

    def _update_status(self, status: str, color: str = "blue"):
        """Update status label"""
        self.status_label.config(text=status, fg=color)

    def run(self):
        """Start GUI"""
        self.root.mainloop()


def main():
    root = tk.Tk()
    gui = FlowRunnerGUI(root)
    gui.run()


if __name__ == "__main__":
    main()
