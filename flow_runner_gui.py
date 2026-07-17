#!/data1/util/Python-3.9.2/bin/python3
"""
flow_runner_gui.py

GUI wrapper for flow runner with DAG visualization, unified logging,
and per-job log tailing from log/*.
"""

import json
import os
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, scrolledtext, ttk
from pathlib import Path
import threading
from datetime import datetime
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple

from flow_graph import build_flow_graph_edges, compute_layers
from flow_generator.core.io import write_flow
from flow_runner_core import create_flow_runner
from winflow_config import get_config

# Segoe UI / Consolas are Windows fonts; missing glyphs on Linux X11 often trigger
# RENDER RenderAddGlyphs BadLength errors. Use common Linux fonts as fallback.
UI_FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
MONO_FONT = "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono"
APP_BRAND = "WinFlow"

# ── Visual theme ──────────────────────────────────────────────────────────────

COLORS = {
    "bg": "#f0f2f5",
    "panel": "#ffffff",
    "border": "#d0d7de",
    "text": "#24292f",
    "muted": "#656d76",
    "accent": "#0969da",
    "pending": "#8b949e",
    "pend": "#79c0ff",
    "running": "#0969da",
    "done": "#1a7f37",
    "failed": "#cf222e",
    "killing": "#8250df",
    "active_ring": "#fd8c73",
    "edge": "#afb8c1",
    "stage_label": "#57606a",
}

STATUS_COLORS = {
    "pending": COLORS["pending"],
    "waiting": COLORS["pending"],
    "PEND": COLORS["pend"],
    "RUN": COLORS["running"],
    "running": COLORS["running"],
    "DONE": COLORS["done"],
    "done": COLORS["done"],
    "EXIT": COLORS["failed"],
    "failed": COLORS["failed"],
    "KILLING": COLORS["killing"],
    "killing": COLORS["killing"],
    "UNKNOWN": COLORS["muted"],
}

LIGHT_NODE_STATUSES = {"PEND", "pend"}


def _truncate_to_width(text: str, font: tkfont.Font, max_width: int) -> str:
    if font.measure(text) <= max_width:
        return text
    ell = "…"
    trimmed = text
    while trimmed and font.measure(trimmed + ell) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + ell) if trimmed else ell


def _split_job_label(label: str) -> List[str]:
    """Prefer breaking long job names at underscores."""
    if "_" not in label or len(label) <= 16:
        return [label]
    parts = [part for part in label.split("_") if part]
    if len(parts) <= 1:
        return [label]
    if len(parts) == 2:
        return parts
    mid = len(parts) // 2
    return ["_".join(parts[:mid]), "_".join(parts[mid:])]


def _fit_job_label_with_fonts(
    label: str,
    max_width: int,
    fonts: List[Tuple[int, tkfont.Font]],
    max_lines: int = 2,
) -> Tuple[str, int]:
    """Return display text (with \\n) and font size for a node label."""
    for size, font in fonts:
        if font.measure(label) <= max_width:
            return label, size

        candidate_lines: List[str] = []
        for segment in _split_job_label(label):
            if font.measure(segment) <= max_width:
                candidate_lines.append(segment)
            else:
                candidate_lines.append(_truncate_to_width(segment, font, max_width))

        if 1 < len(candidate_lines) <= max_lines:
            return "\n".join(candidate_lines[:max_lines]), size
        if len(candidate_lines) == 1:
            return candidate_lines[0], size

    last_size, last_font = fonts[-1]
    return _truncate_to_width(label, last_font, max_width), last_size


class CanvasTooltip:
    """Small hover tooltip for canvas items."""

    def __init__(self, canvas: tk.Canvas):
        self.canvas = canvas
        self._tip: Optional[tk.Toplevel] = None
        self._label: Optional[tk.Label] = None

    def show(self, x_root: int, y_root: int, text: str):
        self.hide()
        self._tip = tk.Toplevel(self.canvas)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x_root + 12}+{y_root + 12}")
        self._label = tk.Label(
            self._tip,
            text=text,
            justify=tk.LEFT,
            background="#ffffe1",
            foreground=COLORS["text"],
            relief=tk.SOLID,
            borderwidth=1,
            font=(UI_FONT, 9),
            padx=8,
            pady=5,
        )
        self._label.pack()

    def hide(self):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None
            self._label = None


FAILED_STATUSES = {"EXIT", "failed", "KILLING", "killing"}
DONE_STATUSES = {"DONE", "done"}
RERUN_BLOCKING_STATUSES = {"RUN", "running", "KILLING", "killing"}
_APP_CFG = get_config()
KILL_CHECK_INTERVAL_MS = _APP_CFG.runner.kill_poll_ms
MAX_KILL_ATTEMPTS = _APP_CFG.runner.kill_max_retries
JOB_NOT_FOUND_HINTS = (
    "not found",
    "no matching",
    "does not exist",
    "unknown job",
    "already finished",
)


# ── Flow graph builder ────────────────────────────────────────────────────────

class FlowGraphModel:
    """Build job-level DAG from flow config."""

    def __init__(self, config: Dict):
        self.config = config
        self.nodes: List[Dict] = []
        self.edges: List[Tuple[str, str]] = []
        self.layers: Dict[str, int] = {}
        self._build()

    def _build(self):
        node_map: Dict[str, Dict] = {}

        for stage in self.config.get("stages", []):
            stage_name = stage["name"]
            for task in stage.get("tasks", []):
                task_name = task["name"]
                for job in task.get("jobs", []):
                    job_key = f"{stage_name}/{task_name}/{job['name']}"
                    node = {
                        "key": job_key,
                        "label": job["name"],
                        "stage": stage_name,
                        "task": task_name,
                        "inputs": job.get("inputs", []),
                        "outputs": job.get("outputs", []),
                        "status": "pending",
                        "lsf_name": "",
                        "job_id": "",
                        "start_time": None,
                        "end_time": None,
                    }
                    self.nodes.append(node)
                    node_map[job_key] = node

        labeled_edges = build_flow_graph_edges(self.config.get("stages", []))
        self.edges = [(src, dst) for src, dst, _label in labeled_edges]
        self.layers = compute_layers(list(node_map.keys()), labeled_edges)

    def get_node(self, key: str) -> Optional[Dict]:
        for n in self.nodes:
            if n["key"] == key:
                return n
        return None

    def layer_groups(self) -> List[List[Dict]]:
        by_layer: Dict[int, List[Dict]] = defaultdict(list)
        for n in self.nodes:
            by_layer[self.layers[n["key"]]].append(n)
        return [by_layer[i] for i in sorted(by_layer)]


def format_timestamp(value: Optional[datetime]) -> str:
    if not value:
        return "---"
    return value.strftime("%Y-%m-%d %H:%M:%S")


def format_runtime(start: Optional[datetime], end: Optional[datetime] = None) -> str:
    if not start:
        return "---"
    finish = end or datetime.now()
    seconds = max(0, int((finish - start).total_seconds()))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


JOB_STATE_KEYS = ("status", "lsf_name", "job_id", "start_time", "end_time")


# ── LSF helpers ───────────────────────────────────────────────────────────────

def _run_lsf_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except OSError as exc:
        return 1, "", str(exc)


def is_job_not_found_message(msg: str) -> bool:
    lowered = msg.lower()
    return any(hint in lowered for hint in JOB_NOT_FOUND_HINTS)


def lsf_job_alive(job_id: str = "", lsf_name: str = "") -> bool:
    """Return True if the LSF job is still in the queue."""
    if job_id:
        code, out, _err = _run_lsf_cmd(["bjobs", "-noheader", str(job_id)])
        if code == 0 and out:
            return True
    if lsf_name:
        code, out, _err = _run_lsf_cmd(["bjobs", "-noheader", "-J", lsf_name])
        if code == 0 and out:
            return True
    return False


def lsf_kill_job(job_id: str = "", lsf_name: str = "") -> Tuple[bool, str]:
    """Send bkill for a job by id or name."""
    if job_id:
        code, out, err = _run_lsf_cmd(["bkill", str(job_id)])
        msg = out or err
        if code == 0:
            return True, msg
        if is_job_not_found_message(msg):
            return False, msg
    if lsf_name:
        code, out, err = _run_lsf_cmd(["bkill", "-J", lsf_name])
        msg = out or err
        if code == 0:
            return True, msg
        return False, msg
    return False, "No job id or name available"


class JobRegistry:
    """Track every LSF submission so stop still works after re-run."""

    def __init__(self):
        self.entries: List[Dict] = []

    def register(self, job_key: str, lsf_name: str, job_id: str):
        self.entries.append({
            "job_key": job_key,
            "lsf_name": lsf_name,
            "job_id": job_id,
            "registered_at": datetime.now(),
        })

    def alive_entries(self) -> List[Dict]:
        alive = []
        seen = set()
        for entry in reversed(self.entries):
            uid = entry["job_id"] or entry["lsf_name"]
            if uid in seen:
                continue
            seen.add(uid)
            if lsf_job_alive(entry["job_id"], entry["lsf_name"]):
                alive.append(entry)
        return list(reversed(alive))

    def alive_for_key(self, job_key: str) -> List[Dict]:
        return [e for e in self.alive_entries() if e["job_key"] == job_key]


class JobKillMonitor:
    """Poll every 15s, re-send bkill until jobs are gone."""

    def __init__(self, gui: "FlowRunnerGUI"):
        self.gui = gui
        self.targets: Dict[str, Dict] = {}
        self._timer_id: Optional[str] = None

    def add(self, job_key: str, job_id: str, lsf_name: str):
        target_id = job_id or lsf_name
        if not target_id:
            return

        label = lsf_name or job_id
        if not lsf_job_alive(job_id, lsf_name):
            self._mark_killed(job_key, label, reason="Job not in LSF queue")
            return

        self.targets[target_id] = {
            "job_key": job_key,
            "job_id": job_id,
            "lsf_name": lsf_name,
            "attempts": 0,
        }
        self._set_node_status(job_key, "KILLING")
        self._ensure_timer()

    def add_entries(self, entries: List[Dict]):
        for entry in entries:
            self.add(entry["job_key"], entry["job_id"], entry["lsf_name"])

    def _set_node_status(self, job_key: str, status: str):
        if not self.gui.graph_model:
            return
        node = self.gui.graph_model.get_node(job_key)
        if node:
            node["status"] = status
        self.gui.graph_canvas.redraw()

    def _mark_killed(self, job_key: str, label: str, reason: str):
        node = self.gui.graph_model.get_node(job_key) if self.gui.graph_model else None
        if node and node.get("status") == "KILLING":
            node["status"] = "EXIT"
            if not node.get("end_time"):
                node["end_time"] = datetime.now()
        self.gui._log_callback(f"{reason}: {label}", "INFO")
        self.gui.graph_canvas.redraw()

    def _finish_target(self, target_id: str, info: Dict, reason: str):
        label = info["lsf_name"] or info["job_id"]
        self._mark_killed(info["job_key"], label, reason=reason)
        del self.targets[target_id]

    def _ensure_timer(self):
        if self._timer_id is None and self.targets:
            self._timer_id = self.gui.root.after(KILL_CHECK_INTERVAL_MS, self._tick)

    def _stop_timer(self):
        if self._timer_id is not None:
            self.gui.root.after_cancel(self._timer_id)
            self._timer_id = None

    def _tick(self):
        self._timer_id = None
        if not self.targets:
            return

        self.gui._update_status("Killing", COLORS["killing"])

        for target_id, info in list(self.targets.items()):
            job_key = info["job_key"]
            job_id = info["job_id"]
            lsf_name = info["lsf_name"]
            label = lsf_name or job_id

            if not lsf_job_alive(job_id, lsf_name):
                self._finish_target(target_id, info, "Confirmed killed")
                continue

            ok, msg = lsf_kill_job(job_id, lsf_name)
            if ok:
                info["attempts"] = 0
                self.gui._log_callback(f"Re-sent bkill for {label}: {msg}", "WARNING")
                self._set_node_status(job_key, "KILLING")
                continue

            if is_job_not_found_message(msg) or not lsf_job_alive(job_id, lsf_name):
                self._finish_target(target_id, info, "Job already gone")
                continue

            info["attempts"] = info.get("attempts", 0) + 1
            self.gui._log_callback(
                f"bkill retry failed for {label} ({info['attempts']}/{MAX_KILL_ATTEMPTS}): {msg}",
                "ERROR",
            )

            if info["attempts"] >= MAX_KILL_ATTEMPTS:
                self._finish_target(
                    target_id,
                    info,
                    f"Stopped retrying kill after {MAX_KILL_ATTEMPTS} attempts",
                )

        self.gui.graph_canvas.redraw()
        if (
            self.gui._detail_dialog
            and self.gui._detail_dialog.win.winfo_exists()
        ):
            self.gui._detail_dialog._refresh()

        if self.targets:
            self._ensure_timer()
        else:
            self._stop_timer()
            self.gui._update_action_buttons()
            if not self.gui.is_running:
                self.gui._update_status("Ready", COLORS["done"])


# ── Canvas DAG panel ──────────────────────────────────────────────────────────

class FlowGraphCanvas(tk.Canvas):
    """Left-to-right DAG renderer for jobs."""

    NODE_W, NODE_H, GAP_X, GAP_Y, PAD = 130, 58, 80, 28, 40
    LABEL_PAD = 12

    def __init__(self, parent, on_node_click=None, **kwargs):
        super().__init__(
            parent, bg=COLORS["panel"], highlightthickness=1,
            highlightbackground=COLORS["border"], **kwargs
        )
        self.model: Optional[FlowGraphModel] = None
        self.on_node_click = on_node_click
        self.positions: Dict[str, Tuple[int, int]] = {}
        self.active_key: Optional[str] = None
        self._pulse_on = False
        self._pulse_id: Optional[str] = None
        self._tooltip = CanvasTooltip(self)
        self._label_fonts = (
            (9, tkfont.Font(family=UI_FONT, size=9, weight="bold")),
            (8, tkfont.Font(family=UI_FONT, size=8, weight="bold")),
        )
        self.bind("<Configure>", lambda e: self.redraw())

    def set_model(self, model: FlowGraphModel):
        self.model = model
        self.active_key = None
        self.redraw()

    def load_config(self, config: Dict):
        self.set_model(FlowGraphModel(config))

    def update_job(self, job_key: str, status: str, lsf_name: str = "", job_id: str = ""):
        if not self.model:
            return
        node = self.model.get_node(job_key)
        if not node:
            return
        node["status"] = status
        if lsf_name:
            node["lsf_name"] = lsf_name
        if job_id:
            node["job_id"] = job_id
        if status in ("PEND", "RUN", "running", "pending", "job_start"):
            if self.active_key != job_key:
                if self._pulse_id:
                    self.after_cancel(self._pulse_id)
                    self._pulse_id = None
                self.active_key = job_key
        elif status in ("DONE", "done", "EXIT", "failed", "KILLING", "killing"):
            if self.active_key == job_key and status not in ("KILLING", "killing"):
                self.active_key = None
        self.redraw()

    def reset(self):
        if self.model:
            for n in self.model.nodes:
                n.update(
                    status="pending",
                    lsf_name="",
                    job_id="",
                    start_time=None,
                    end_time=None,
                )
        self.active_key = None
        self.redraw()

    def _bind_node_click(self, job_key: str):
        if not self.on_node_click:
            return
        self.tag_bind(
            job_key,
            "<Button-1>",
            lambda _event, key=job_key: self.on_node_click(key),
        )

    def _bind_node_interactions(self, job_key: str, node: Dict):
        tip_text = f"{node['label']}\n{node['stage']} / {node['task']}"

        def on_enter(event):
            self.config(cursor="hand2")
            self._tooltip.show(event.x_root, event.y_root, tip_text)

        def on_leave(_event):
            self.config(cursor="")
            self._tooltip.hide()

        self.tag_bind(job_key, "<Enter>", on_enter)
        self.tag_bind(job_key, "<Leave>", on_leave)

    def redraw(self):
        self.delete("all")
        if not self.model or not self.model.nodes:
            self._draw_placeholder("Load a flow config and press Run")
            return

        self._layout()
        self._draw_edges()
        self._draw_nodes()
        self._draw_stage_labels()

        if self.active_key and not self._pulse_id:
            self._start_pulse()
        elif not self.active_key and self._pulse_id:
            self.after_cancel(self._pulse_id)
            self._pulse_id = None

    def _start_pulse(self):
        self._pulse_on = not self._pulse_on
        self._draw_pulse_only()
        self._pulse_id = self.after(600, self._pulse_tick)

    def _pulse_tick(self):
        self._pulse_id = None
        if self.active_key:
            self._start_pulse()

    def _draw_pulse_only(self):
        if not self.active_key or not self.model:
            return
        self.delete("pulse")
        key = self.active_key
        if key not in self.positions:
            return
        x, y = self.positions[key]
        x0 = x - self.NODE_W // 2 - 3
        y0 = y - self.NODE_H // 2 - 3
        x1 = x + self.NODE_W // 2 + 3
        y1 = y + self.NODE_H // 2 + 3
        self.create_rectangle(
            x0, y0, x1, y1,
            fill=COLORS["active_ring"] if self._pulse_on else COLORS["panel"],
            outline="", tags="pulse"
        )
        self.tag_raise(key)

    def _draw_placeholder(self, text: str):
        w = self.winfo_width() or 400
        h = self.winfo_height() or 200
        self.create_text(
            w // 2, h // 2, text=text,
            fill=COLORS["muted"], font=(UI_FONT, 11)
        )

    def _layout(self):
        assert self.model
        groups = self.model.layer_groups()
        self.positions.clear()
        max_h = 0
        for col, group in enumerate(groups):
            x = self.PAD + col * (self.NODE_W + self.GAP_X) + self.NODE_W // 2
            total_h = len(group) * self.NODE_H + (len(group) - 1) * self.GAP_Y
            start_y = self.PAD + 30
            for i, node in enumerate(group):
                y = start_y + i * (self.NODE_H + self.GAP_Y) + self.NODE_H // 2
                self.positions[node["key"]] = (x, y)
                max_h = max(max_h, y + self.NODE_H // 2)
        needed_w = self.PAD * 2 + len(groups) * (self.NODE_W + self.GAP_X)
        needed_h = max_h + self.PAD + 20
        self.config(scrollregion=(0, 0, max(needed_w, self.winfo_width()), needed_h))

    def _draw_edges(self):
        assert self.model
        for src, dst in self.model.edges:
            if src not in self.positions or dst not in self.positions:
                continue
            x1, y1 = self.positions[src]
            x2, y2 = self.positions[dst]
            sx = x1 + self.NODE_W // 2
            tx = x2 - self.NODE_W // 2
            self.create_line(sx, y1, tx, y2, fill=COLORS["edge"], width=2, arrow=tk.LAST, smooth=True)

    def _draw_nodes(self):
        assert self.model
        for node in self.model.nodes:
            key = node["key"]
            if key not in self.positions:
                continue
            x, y = self.positions[key]
            x0, y0 = x - self.NODE_W // 2, y - self.NODE_H // 2
            x1, y1 = x + self.NODE_W // 2, y + self.NODE_H // 2
            color = STATUS_COLORS.get(node["status"], COLORS["pending"])
            is_active = key == self.active_key
            if node["status"] in LIGHT_NODE_STATUSES:
                title_fill, status_fill = COLORS["text"], COLORS["muted"]
            else:
                title_fill, status_fill = "white", "#e6edf3"

            if is_active:
                self.create_rectangle(
                    x0 - 3, y0 - 3, x1 + 3, y1 + 3,
                    fill=COLORS["active_ring"] if self._pulse_on else COLORS["panel"],
                    outline="", tags="pulse"
                )

            self.create_rectangle(x0, y0, x1, y1, fill=color, outline=COLORS["border"], width=1, tags=key)

            display_label, label_size = _fit_job_label_with_fonts(
                node["label"],
                self.NODE_W - self.LABEL_PAD,
                list(self._label_fonts),
            )
            line_count = display_label.count("\n") + 1
            title_y = y - (12 if line_count > 1 else 8)
            self.create_text(
                x, title_y, text=display_label, fill=title_fill,
                font=(UI_FONT, label_size, "bold"),
                justify=tk.CENTER, anchor=tk.CENTER, tags=key,
            )
            status_txt = node["status"] if node["status"] != "pending" else "waiting"
            self.create_text(
                x, y + 14, text=status_txt.upper(), fill=status_fill,
                font=(UI_FONT, 7), tags=key
            )
            self._bind_node_click(key)
            self._bind_node_interactions(key, node)

    def _draw_stage_labels(self):
        assert self.model
        stage_cols: Dict[str, int] = {}
        for node in self.model.nodes:
            layer = self.model.layers[node["key"]]
            if node["stage"] not in stage_cols:
                stage_cols[node["stage"]] = layer

        drawn: Set[str] = set()
        for stage, col in sorted(stage_cols.items(), key=lambda x: x[1]):
            if stage in drawn:
                continue
            drawn.add(stage)
            x = self.PAD + col * (self.NODE_W + self.GAP_X) + self.NODE_W // 2
            self.create_text(
                x, 14, text=stage, fill=COLORS["stage_label"],
                font=(UI_FONT, 8, "italic")
            )

# ── Job log tailer ────────────────────────────────────────────────────────────

class JobLogTailer:
    """Tail log/{job}.log and log/{job}.err in background."""

    def __init__(self, callback):
        self.callback = callback
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._paths: List[Path] = []
        self._offsets: Dict[str, int] = {}

    def start(self, lsf_name: str):
        self.stop()
        self._stop.clear()
        self._paths = [
            Path(f"{get_config().runner.job_log_dir}/{lsf_name}.log"),
            Path(f"{get_config().runner.job_log_dir}/{lsf_name}.err"),
        ]
        self._offsets = {str(p): 0 for p in self._paths}
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=get_config().runner.thread_join_timeout_sec)
        self._thread = None

    def _run(self):
        while not self._stop.is_set():
            for path in self._paths:
                if not path.exists():
                    continue
                key = str(path)
                try:
                    with open(path, "r", errors="replace") as fp:
                        fp.seek(self._offsets.get(key, 0))
                        chunk = fp.read()
                        self._offsets[key] = fp.tell()
                    if chunk:
                        kind = "stderr" if path.suffix == ".err" else "stdout"
                        self.callback(kind, path.name, chunk)
                except OSError:
                    pass
            self._stop.wait(get_config().runner.log_tail_interval_sec)


# ── Job detail dialog ─────────────────────────────────────────────────────────

class JobDetailDialog:
    """Popup window with job metadata and actions."""

    def __init__(self, parent: tk.Misc, gui: "FlowRunnerGUI", job_key: str):
        self.gui = gui
        self.job_key = job_key
        self._timer_id: Optional[str] = None

        node = gui.graph_model.get_node(job_key) if gui.graph_model else None
        title = node["label"] if node else job_key

        self.win = tk.Toplevel(parent)
        self.win.title(f"Job: {title}")
        self.win.geometry("500x460")
        self.win.configure(bg=COLORS["panel"])
        self.win.transient(parent)

        body = tk.Frame(self.win, bg=COLORS["panel"], padx=16, pady=12)
        body.pack(fill=tk.BOTH, expand=True)

        self._add_section(body, "Job Input", "inputs")
        self._add_section(body, "Job Output", "outputs")

        timing = tk.LabelFrame(
            body, text=" Timing ", font=(UI_FONT, 9, "bold"),
            bg=COLORS["panel"], fg=COLORS["text"], padx=10, pady=8
        )
        timing.pack(fill=tk.X, pady=(10, 0))

        self.start_var = tk.StringVar(value="---")
        self.end_var = tk.StringVar(value="---")
        self.runtime_var = tk.StringVar(value="---")
        self.status_var = tk.StringVar(value="---")
        self.lsf_var = tk.StringVar(value="---")

        for row, (label, var) in enumerate([
            ("Status", self.status_var),
            ("LSF Job", self.lsf_var),
            ("Start Time", self.start_var),
            ("End Time", self.end_var),
            ("Run Time", self.runtime_var),
        ]):
            tk.Label(
                timing, text=f"{label}:", bg=COLORS["panel"],
                font=(UI_FONT, 9), anchor=tk.W, width=12
            ).grid(row=row, column=0, sticky=tk.W, pady=2)
            tk.Label(
                timing, textvariable=var, bg=COLORS["panel"],
                font=(MONO_FONT, 9), anchor=tk.W
            ).grid(row=row, column=1, sticky=tk.W, pady=2)

        actions = tk.Frame(body, bg=COLORS["panel"])
        actions.pack(fill=tk.X, pady=(16, 0))

        self.stop_btn = tk.Button(
            actions, text="Stop Job", command=self._stop_job,
            bg=COLORS["failed"], fg="white", font=(UI_FONT, 9, "bold"),
            relief=tk.FLAT, padx=12, pady=6
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            actions, text="Validate Job", command=self._validate_job,
            bg=COLORS["accent"], fg="white", font=(UI_FONT, 9, "bold"),
            relief=tk.FLAT, padx=12, pady=6
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            actions, text="Close", command=self._close,
            font=(UI_FONT, 9), relief=tk.FLAT, padx=12, pady=6
        ).pack(side=tk.RIGHT)

        self.win.protocol("WM_DELETE_WINDOW", self._close)
        self._refresh()
        self._schedule_refresh()

    def _add_section(self, parent, title: str, field: str):
        frame = tk.LabelFrame(
            parent, text=f" {title} ", font=(UI_FONT, 9, "bold"),
            bg=COLORS["panel"], fg=COLORS["text"], padx=8, pady=6
        )
        frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        text = scrolledtext.ScrolledText(
            frame, height=4, wrap=tk.WORD, font=(MONO_FONT, 9),
            bg="#f6f8fa", relief=tk.FLAT, state=tk.DISABLED
        )
        text.pack(fill=tk.BOTH, expand=True)
        setattr(self, f"{field}_text", text)

    def _get_node(self) -> Optional[Dict]:
        if not self.gui.graph_model:
            return None
        return self.gui.graph_model.get_node(self.job_key)

    def _set_list_text(self, widget: scrolledtext.ScrolledText, items: List[str]):
        widget.config(state=tk.NORMAL)
        widget.delete(1.0, tk.END)
        widget.insert(tk.END, "\n".join(items) if items else "(none)")
        widget.config(state=tk.DISABLED)

    def _refresh(self):
        node = self._get_node()
        if not node:
            return

        self._set_list_text(self.inputs_text, node.get("inputs", []))
        self._set_list_text(self.outputs_text, node.get("outputs", []))

        status = node.get("status", "pending")
        if status == "pending":
            display_status = "WAITING"
        else:
            display_status = status.upper()
        self.status_var.set(display_status)
        self.lsf_var.set(node.get("lsf_name") or "---")
        self.start_var.set(format_timestamp(node.get("start_time")))
        self.end_var.set(format_timestamp(node.get("end_time")))
        self.runtime_var.set(format_runtime(node.get("start_time"), node.get("end_time")))

        lsf_name = node.get("lsf_name", "")
        has_target = bool(self.gui.job_registry.alive_for_key(self.job_key) or lsf_name)
        self.stop_btn.config(state=tk.NORMAL if has_target else tk.DISABLED)

    def _schedule_refresh(self):
        if not self.win.winfo_exists():
            return
        self._refresh()
        self._timer_id = self.win.after(1000, self._schedule_refresh)

    def _close(self):
        if self._timer_id:
            self.win.after_cancel(self._timer_id)
        self.win.destroy()
        if self.gui._detail_dialog is self:
            self.gui._detail_dialog = None

    def _stop_job(self):
        node = self._get_node()
        if not node:
            return

        targets = self.gui.job_registry.alive_for_key(self.job_key)
        if not targets and node.get("job_id"):
            targets = [{
                "job_key": self.job_key,
                "job_id": node.get("job_id", ""),
                "lsf_name": node.get("lsf_name", ""),
            }]

        if not targets:
            messagebox.showwarning(
                "Stop Job",
                "No running LSF job found for this node.",
                parent=self.win,
            )
            return

        for entry in targets:
            ok, msg = lsf_kill_job(entry["job_id"], entry["lsf_name"])
            self.gui._log_callback(
                f"bkill {entry['lsf_name'] or entry['job_id']}: {msg}",
                "WARNING" if ok else "ERROR",
            )
            self.gui.kill_monitor.add(
                entry["job_key"], entry["job_id"], entry["lsf_name"]
            )

        self._refresh()
        messagebox.showinfo(
            "Stop Job",
            f"Kill requested for {len(targets)} job(s). Status: KILLING",
            parent=self.win,
        )

    def _validate_job(self):
        node = self._get_node()
        if not node:
            return

        outputs = node.get("outputs", [])
        missing = [path for path in outputs if not os.path.exists(path)]

        if missing:
            node["status"] = "EXIT"
            messagebox.showerror(
                "Validate Job",
                "Validation failed. Missing outputs:\n" + "\n".join(missing),
                parent=self.win,
            )
        else:
            node["status"] = "DONE"
            if node.get("start_time") and not node.get("end_time"):
                node["end_time"] = datetime.now()
            messagebox.showinfo(
                "Validate Job",
                "All output files exist. Status set to DONE.",
                parent=self.win,
            )

        self.gui.graph_canvas.redraw()
        self._refresh()


# ── Main GUI ──────────────────────────────────────────────────────────────────

class FlowRunnerGUI:
    """GUI for Flow Runner with DAG view and unified logging."""

    def __init__(self, root: tk.Misc, sync_source=None):
        self.root = root
        self.window = root.winfo_toplevel()
        self.sync_source = sync_source
        self._owns_window = isinstance(root, tk.Tk)

        if self._owns_window:
            self.root.title("WinFlow Runner")
            gui_cfg = get_config().gui
            self.root.geometry(gui_cfg.runner_window_size)
            self.root.minsize(960, 640)
            self.root.configure(bg=COLORS["bg"])
        else:
            try:
                self.root.configure(bg=COLORS["bg"])
            except tk.TclError:
                pass

        self.runner = None
        self.flow_log_messages: List[Tuple[str, str, str]] = []
        self.job_log_messages: List[Tuple[str, str, str]] = []
        self.is_running = False
        self.flow_config: Optional[Dict] = None
        self.graph_model: Optional[FlowGraphModel] = None
        self.job_tailer = JobLogTailer(self._on_job_log_chunk)
        self.current_lsf_name = ""
        self.completed_jobs = 0
        self.total_jobs = 0
        self._detail_dialog: Optional[JobDetailDialog] = None
        self.job_registry = JobRegistry()
        self.kill_monitor = JobKillMonitor(self)
        self.sync_btn: Optional[tk.Button] = None
        self._suppress_auto_load = False

        self._setup_styles()
        self._setup_ui()
        self._bind_config_events()
        self.root.after(0, self._auto_load_graph)

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=COLORS["bg"])
        style.configure("TNotebook.Tab", padding=[12, 4], font=(UI_FONT, 9))
        style.configure("Header.TLabel", font=(UI_FONT, 11, "bold"), background=COLORS["bg"])
        style.configure("Status.TLabel", font=(UI_FONT, 9), background=COLORS["panel"])

    def _bind_config_events(self):
        self.config_path_var.trace_add("write", self._on_config_path_changed)

    def _on_config_path_changed(self, *_args):
        if self._suppress_auto_load:
            return
        self.root.after(get_config().runner.auto_load_delay_ms, self._auto_load_graph)

    def _init_paned_split(self):
        """Set initial 45/55 split between job flow and log panels."""
        try:
            height = self.main_paned.winfo_height()
            if height > 1:
                self.main_paned.sashpos(0, int(height * 0.45))
        except tk.TclError:
            pass

    def _setup_ui(self):
        # ── Top bar ──
        top = tk.Frame(self.root, bg=COLORS["panel"], relief=tk.FLAT, bd=0)
        top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(10, 0))

        inner_top = tk.Frame(top, bg=COLORS["panel"])
        inner_top.pack(fill=tk.X, padx=12, pady=10)

        tk.Label(
            inner_top, text=APP_BRAND, font=(UI_FONT, 14, "bold"),
            bg=COLORS["panel"], fg=COLORS["accent"]
        ).pack(side=tk.LEFT)

        tk.Label(inner_top, text="  Config:", bg=COLORS["panel"], fg=COLORS["muted"],
                 font=(UI_FONT, 9)).pack(side=tk.LEFT, padx=(20, 4))
        self.config_path_var = tk.StringVar(value=get_config().runner.default_flow_file)
        tk.Entry(
            inner_top, textvariable=self.config_path_var, width=42,
            font=(UI_FONT, 9), relief=tk.FLAT, bg="#f6f8fa",
            highlightthickness=1, highlightbackground=COLORS["border"]
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            inner_top, text="Browse", command=self._browse_config,
            font=(UI_FONT, 9), relief=tk.FLAT, bg="#f6f8fa", padx=8
        ).pack(side=tk.LEFT, padx=4)

        sep = tk.Frame(self.root, height=1, bg=COLORS["border"])
        sep.pack(fill=tk.X, padx=10)

        # ── Body ──
        body = tk.Frame(self.root, bg=COLORS["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left control rail
        rail = tk.Frame(body, bg=COLORS["panel"], width=148,
                        highlightthickness=1, highlightbackground=COLORS["border"])
        rail.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        rail.pack_propagate(False)

        tk.Label(rail, text="Control", font=(UI_FONT, 10, "bold"),
                 bg=COLORS["panel"], fg=COLORS["text"]).pack(pady=(14, 8))

        self.run_btn = tk.Button(
            rail, text="▶  Run Flow", command=self._run_flow,
            bg=COLORS["done"], fg="white", width=14, height=2,
            font=(UI_FONT, 9, "bold"), relief=tk.FLAT, cursor="hand2"
        )
        self.run_btn.pack(pady=6, padx=10)

        self.rerun_btn = tk.Button(
            rail, text="↻  Rerun", command=self._rerun_from_failure,
            bg="#bf8700", fg="white", width=14, height=2,
            state=tk.DISABLED, font=(UI_FONT, 9, "bold"), relief=tk.FLAT
        )
        self.rerun_btn.pack(pady=6, padx=10)

        self.stop_btn = tk.Button(
            rail, text="⏹  Stop", command=self._stop_flow,
            bg=COLORS["failed"], fg="white", width=14, height=2,
            state=tk.DISABLED, font=(UI_FONT, 9, "bold"), relief=tk.FLAT
        )
        self.stop_btn.pack(pady=6, padx=10)

        tk.Button(
            rail, text="🗑  Clear Logs", command=self._clear_logs,
            bg=COLORS["accent"], fg="white", width=14, height=2,
            font=(UI_FONT, 9, "bold"), relief=tk.FLAT
        ).pack(pady=6, padx=10)

        status_box = tk.LabelFrame(
            rail, text=" Status ", font=(UI_FONT, 8),
            bg=COLORS["panel"], fg=COLORS["muted"], padx=8, pady=6
        )
        status_box.pack(pady=16, padx=8, fill=tk.X)
        self.status_label = tk.Label(
            status_box, text="Ready", fg=COLORS["done"],
            font=(UI_FONT, 9, "bold"), bg=COLORS["panel"], wraplength=120
        )
        self.status_label.pack()

        filter_box = tk.LabelFrame(
            rail, text=" Log Filter ", font=(UI_FONT, 8),
            bg=COLORS["panel"], fg=COLORS["muted"], padx=8, pady=4
        )
        filter_box.pack(pady=4, padx=8, fill=tk.X)
        self.show_debug = tk.BooleanVar(value=False)
        self.show_info = tk.BooleanVar(value=True)
        self.show_warning = tk.BooleanVar(value=True)
        self.show_error = tk.BooleanVar(value=True)
        for var, label in [
            (self.show_debug, "Debug"), (self.show_info, "Info"),
            (self.show_warning, "Warning"), (self.show_error, "Error"),
        ]:
            tk.Checkbutton(
                filter_box, text=label, variable=var, bg=COLORS["panel"],
                font=(UI_FONT, 8), command=self._update_log_display
            ).pack(anchor=tk.W)

        # Right main area — vertical split (drag sash to resize graph vs logs)
        main_area = tk.Frame(body, bg=COLORS["bg"])
        main_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.main_paned = ttk.PanedWindow(main_area, orient=tk.VERTICAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)

        # Graph panel
        graph_frame = tk.LabelFrame(
            self.main_paned, text=" Job Flow (left → right) ", font=(UI_FONT, 9, "bold"),
            bg=COLORS["panel"], fg=COLORS["text"], padx=4, pady=4
        )
        self.main_paned.add(graph_frame, weight=1)

        graph_scroll_y = tk.Scrollbar(graph_frame, orient=tk.VERTICAL)
        graph_scroll_x = tk.Scrollbar(graph_frame, orient=tk.HORIZONTAL)
        self.graph_canvas = FlowGraphCanvas(
            graph_frame,
            on_node_click=self._open_job_detail,
            yscrollcommand=graph_scroll_y.set,
            xscrollcommand=graph_scroll_x.set,
        )
        graph_scroll_y.config(command=self.graph_canvas.yview)
        graph_scroll_x.config(command=self.graph_canvas.xview)
        graph_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        graph_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.graph_canvas.pack(fill=tk.BOTH, expand=True)

        # Log notebook
        log_frame = tk.Frame(self.main_paned, bg=COLORS["bg"])
        self.main_paned.add(log_frame, weight=1)

        self.log_notebook = ttk.Notebook(log_frame)
        self.log_notebook.pack(fill=tk.BOTH, expand=True)

        self.root.after_idle(self._init_paned_split)

        # Tab 1: Runner log (logs/*)
        runner_tab = tk.Frame(self.log_notebook, bg=COLORS["panel"])
        self.log_notebook.add(runner_tab, text="  Runner Log (logs/*)  ")

        self.flow_log_text = scrolledtext.ScrolledText(
            runner_tab, wrap=tk.WORD, font=(MONO_FONT, 9),
            bg="#f6f8fa", relief=tk.FLAT, state=tk.DISABLED
        )
        self.flow_log_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Tab 2: Job log (log/*)
        job_tab = tk.Frame(self.log_notebook, bg=COLORS["panel"])
        self.log_notebook.add(job_tab, text="  Job Log (log/*)  ")

        job_toolbar = tk.Frame(job_tab, bg=COLORS["panel"])
        job_toolbar.pack(fill=tk.X, padx=4, pady=(4, 0))
        tk.Label(job_toolbar, text="Job:", bg=COLORS["panel"],
                 font=(UI_FONT, 9)).pack(side=tk.LEFT)
        self.job_selector_var = tk.StringVar(value="(auto-follow active job)")
        self.job_selector = ttk.Combobox(
            job_toolbar, textvariable=self.job_selector_var,
            state="readonly", width=50, font=(UI_FONT, 9)
        )
        self.job_selector.pack(side=tk.LEFT, padx=6)
        self.job_selector.bind("<<ComboboxSelected>>", self._on_job_selected)

        tk.Button(
            job_toolbar, text="Open log file", command=self._open_job_log_file,
            font=(UI_FONT, 8), relief=tk.FLAT
        ).pack(side=tk.LEFT, padx=4)

        self.job_log_text = scrolledtext.ScrolledText(
            job_tab, wrap=tk.WORD, font=(MONO_FONT, 9),
            bg="#1e1e1e", fg="#d4d4d4", relief=tk.FLAT, state=tk.DISABLED,
            insertbackground="#d4d4d4"
        )
        self.job_log_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        for widget in (self.flow_log_text, self.job_log_text):
            for level, color in [
                ("DEBUG", "#8b949e"), ("INFO", "#0969da"),
                ("WARNING", "#bf8700"), ("ERROR", "#cf222e"),
                ("STDOUT", "#3fb950"), ("STDERR", "#f85149"),
            ]:
                widget.tag_configure(level, foreground=color)

        # Bottom bar
        bottom = tk.Frame(self.root, bg=COLORS["panel"],
                          highlightthickness=1, highlightbackground=COLORS["border"])
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 10))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            bottom, variable=self.progress_var, maximum=100, mode="determinate"
        )
        self.progress_bar.pack(fill=tk.X, padx=12, pady=(10, 4))

        bottom_row = tk.Frame(bottom, bg=COLORS["panel"])
        bottom_row.pack(fill=tk.X, padx=12, pady=(0, 8))

        self.stats_label = tk.Label(
            bottom_row, text="Ready to run", font=(UI_FONT, 9),
            bg=COLORS["panel"], fg=COLORS["muted"], anchor=tk.W
        )
        self.stats_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.sync_btn = tk.Button(
            bottom_row,
            text="↻ Sync from Generator",
            command=self._sync_from_generator,
            font=(UI_FONT, 9, "bold"),
            relief=tk.FLAT,
            bg=COLORS["accent"],
            fg="white",
            padx=12,
            pady=4,
            state=tk.DISABLED,
        )
        if self.sync_source is not None:
            self.sync_btn.pack(side=tk.RIGHT)
            self._update_sync_button()
        else:
            self.sync_btn = None

    # ── Config / graph ────────────────────────────────────────────────────────

    def _browse_config(self):
        file_path = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if file_path:
            self.config_path_var.set(file_path)

    def _load_config(self) -> Optional[Dict]:
        config_path = self.config_path_var.get()
        if not Path(config_path).exists():
            return None
        try:
            with open(config_path, "r") as fp:
                config = json.load(fp)
        except json.JSONDecodeError as e:
            return None
        return config

    def _snapshot_job_states(self) -> Dict[str, Dict]:
        if not self.graph_model:
            return {}
        return {
            node["key"]: {key: node.get(key) for key in JOB_STATE_KEYS}
            for node in self.graph_model.nodes
        }

    def _restore_job_states(self, snapshot: Dict[str, Dict]):
        if not self.graph_model:
            return
        for node in self.graph_model.nodes:
            saved = snapshot.get(node["key"])
            if saved:
                node.update(saved)
        self.graph_canvas.redraw()

    def _auto_load_graph(self):
        snapshot = self._snapshot_job_states()
        config = self._load_config()
        if not config:
            return
        self.flow_config = config
        self.graph_model = FlowGraphModel(config)
        self.graph_canvas.set_model(self.graph_model)
        self._restore_job_states(snapshot)
        self.total_jobs = len(self.graph_model.nodes)
        if not self.is_running:
            self.completed_jobs = sum(
                1 for node in self.graph_model.nodes
                if node.get("status") in ("DONE", "done", "EXIT", "failed")
            )
            if self.total_jobs:
                self.progress_var.set(100 * self.completed_jobs / self.total_jobs)
        self._refresh_job_selector()
        self._update_stats()
        self._update_action_buttons()

    def _has_rerun_blocking_status(self) -> bool:
        if not self.graph_model:
            return False
        return any(
            node.get("status") in RERUN_BLOCKING_STATUSES
            for node in self.graph_model.nodes
        )

    def _update_action_buttons(self):
        if self.rerun_btn:
            can_rerun = (
                bool(self.graph_model and self.graph_model.nodes)
                and not self.is_running
                and not self._has_rerun_blocking_status()
                and not self.kill_monitor.targets
            )
            self.rerun_btn.config(state=tk.NORMAL if can_rerun else tk.DISABLED)

        alive = self.job_registry.alive_entries()
        has_kill_targets = bool(self.kill_monitor.targets)
        if self.stop_btn and not self.is_running:
            self.stop_btn.config(
                state=tk.NORMAL if (alive or has_kill_targets) else tk.DISABLED
            )
        self._update_sync_button()

    def _can_sync(self) -> bool:
        if self.sync_source is None:
            return False
        if self.is_running:
            return False
        if self._has_rerun_blocking_status():
            return False
        if self.kill_monitor.targets:
            return False
        if self.job_registry.alive_entries():
            return False
        return True

    def _update_sync_button(self):
        if not self.sync_btn:
            return
        self.sync_btn.config(state=tk.NORMAL if self._can_sync() else tk.DISABLED)

    def _sync_from_generator(self):
        parent = self.window
        if not self._can_sync():
            messagebox.showinfo(
                "Sync",
                "Cannot sync while a job is running, queued as RUN, or being killed.",
                parent=parent,
            )
            return
        if self.sync_source is None:
            return

        try:
            flow = self.sync_source.get_flow_dict()
        except ValueError as exc:
            messagebox.showerror("Sync failed", str(exc), parent=parent)
            return
        except Exception as exc:
            messagebox.showerror(
                "Sync failed",
                f"Unable to read generator flow:\n{exc}",
                parent=parent,
            )
            return

        out = self.sync_source.get_output_path()
        try:
            write_flow(flow, out)
        except OSError as exc:
            messagebox.showerror(
                "Sync failed",
                f"Unable to write flow file:\n{exc}",
                parent=parent,
            )
            return

        # Point runner at the written file without the auto-load path that
        # preserves prior job statuses.
        self._suppress_auto_load = True
        try:
            self.config_path_var.set(str(out))
        finally:
            self._suppress_auto_load = False

        self.flow_config = flow
        self.graph_model = FlowGraphModel(flow)
        self.graph_canvas.set_model(self.graph_model)
        self.graph_canvas.reset()
        self.completed_jobs = 0
        self.total_jobs = len(self.graph_model.nodes)
        self.progress_var.set(0)
        self._refresh_job_selector()
        self._update_stats()
        self._update_action_buttons()
        self._update_status("Synced", COLORS["accent"])
        self._log_callback(
            f"Synced flow from Generator → {out} "
            f"({self.total_jobs} job(s); all statuses reset to pending)",
            "INFO",
        )

    def _request_kill_entries(self, entries: List[Dict]):
        if not entries:
            messagebox.showinfo("Stop", "No running LSF jobs found.")
            return

        for entry in entries:
            ok, msg = lsf_kill_job(entry["job_id"], entry["lsf_name"])
            self._log_callback(
                f"bkill {entry['lsf_name'] or entry['job_id']}: {msg}",
                "WARNING" if ok else "ERROR",
            )

        self.kill_monitor.add_entries(entries)
        self._update_status("Killing", COLORS["killing"])
        self._update_action_buttons()

    def _open_job_detail(self, job_key: str):
        if self._detail_dialog and self._detail_dialog.win.winfo_exists():
            self._detail_dialog._close()
        self._detail_dialog = JobDetailDialog(self.window, self, job_key)

    def _refresh_job_selector(self):
        if not self.graph_model:
            return
        names = []
        for n in self.graph_model.nodes:
            label = n["label"]
            lsf = n.get("lsf_name", "")
            names.append(f"{label}  ({lsf})" if lsf else label)
        self.job_selector["values"] = names

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log_callback(self, message: str, level: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.flow_log_messages.append((level, message, ts))
        self.root.after(0, self._update_log_display)

    def _on_job_log_chunk(self, kind: str, filename: str, chunk: str):
        level = "STDERR" if kind == "stderr" else "STDOUT"
        ts = datetime.now().strftime("%H:%M:%S")
        for line in chunk.splitlines(keepends=True):
            if line.strip():
                self.job_log_messages.append((level, f"[{filename}] {line.rstrip()}", ts))
        self.root.after(0, self._update_log_display)

    def _should_show(self, level: str) -> bool:
        if level in ("STDOUT", "STDERR"):
            return True
        if level == "DEBUG":
            return self.show_debug.get()
        if level == "INFO":
            return self.show_info.get()
        if level == "WARNING":
            return self.show_warning.get()
        if level == "ERROR":
            return self.show_error.get()
        return True

    def _fill_log_widget(self, widget, messages: List[Tuple[str, str, str]]):
        widget.config(state=tk.NORMAL)
        widget.delete(1.0, tk.END)
        for level, message, timestamp in messages:
            if not self._should_show(level):
                continue
            widget.insert(tk.END, f"[{timestamp}] [{level}] {message}\n", level)
        widget.config(state=tk.DISABLED)
        widget.see(tk.END)

    def _update_log_display(self):
        self._fill_log_widget(self.flow_log_text, self.flow_log_messages)
        self._fill_log_widget(self.job_log_text, self.job_log_messages)

    def _clear_logs(self):
        self.job_tailer.stop()
        self.flow_log_messages = []
        self.job_log_messages = []
        deleted = 0
        runner_cfg = get_config().runner
        for directory in (Path(runner_cfg.job_log_dir), Path(runner_cfg.session_log_dir)):
            if not directory.exists():
                continue
            for path in directory.iterdir():
                if path.is_file():
                    try:
                        path.unlink()
                        deleted += 1
                    except OSError:
                        pass
        for w in (self.flow_log_text, self.job_log_text):
            w.config(state=tk.NORMAL)
            w.delete(1.0, tk.END)
            w.config(state=tk.DISABLED)
        self.current_lsf_name = ""
        self._update_status("Ready", COLORS["done"])
        self.stats_label.config(text=f"Logs cleared, deleted {deleted} files")

    def _on_job_selected(self, _event=None):
        if not self.graph_model:
            return
        idx = self.job_selector.current()
        if idx < 0:
            return
        node = self.graph_model.nodes[idx]
        lsf_name = node.get("lsf_name", "")
        if lsf_name:
            self._load_job_log_snapshot(lsf_name)

    def _load_job_log_snapshot(self, lsf_name: str):
        """Load full content of job log files into job log panel."""
        self.job_log_messages = []
        for suffix in (".log", ".err"):
            path = Path(f"log/{lsf_name}{suffix}")
            if path.exists():
                level = "STDERR" if suffix == ".err" else "STDOUT"
                try:
                    text = path.read_text(errors="replace")
                    for line in text.splitlines():
                        if line.strip():
                            ts = datetime.now().strftime("%H:%M:%S")
                            self.job_log_messages.append(
                                (level, f"[{path.name}] {line}", ts)
                            )
                except OSError:
                    pass
        self._update_log_display()

    def _open_job_log_file(self):
        if not self.graph_model:
            return
        idx = self.job_selector.current()
        if idx < 0:
            messagebox.showinfo("Info", "Select a job first.")
            return
        lsf_name = self.graph_model.nodes[idx].get("lsf_name", "")
        if not lsf_name:
            messagebox.showinfo("Info", "Job has not been submitted yet.")
            return
        log_path = Path(f"{get_config().runner.job_log_dir}/{lsf_name}.log")
        if log_path.exists():
            try:
                subprocess.Popen([get_config().runner.log_viewer, str(log_path)])
            except OSError as exc:
                messagebox.showerror("Error", f"Failed to launch {get_config().runner.log_viewer}:\n{exc}")
        else:
            messagebox.showinfo("Info", f"Log not found: {log_path}")

    # ── Job events ────────────────────────────────────────────────────────────

    def _job_callback(self, event: str, data: Dict):
        self.root.after(0, lambda: self._handle_job_event(event, data))

    def _handle_job_event(self, event: str, data: Dict):
        job_key = data.get("job_key", "")
        status = data.get("status", "")
        lsf_name = data.get("lsf_name", "")
        job_id = data.get("job_id", "")
        now = datetime.now()

        node = self.graph_model.get_node(job_key) if self.graph_model else None
        if node:
            if event in ("job_start", "job_submitted") and not node.get("start_time"):
                node["start_time"] = now
            if event == "job_status" and status == "RUN" and not node.get("start_time"):
                node["start_time"] = now
            if event in ("job_done", "job_failed") and not node.get("end_time"):
                node["end_time"] = now

        if event == "job_submitted":
            self.job_registry.register(job_key, lsf_name, job_id)
            self.job_tailer.start(lsf_name)
            self.current_lsf_name = lsf_name
            self.job_log_messages = []
            self.log_notebook.select(1)
            node = self.graph_model.get_node(job_key) if self.graph_model else None
            if node:
                node["lsf_name"] = lsf_name
                node["job_id"] = job_id
            self._refresh_job_selector()
            if self.graph_model:
                idx = next(
                    (i for i, n in enumerate(self.graph_model.nodes) if n["key"] == job_key), -1
                )
                if idx >= 0:
                    self.job_selector.current(idx)

        if event in ("job_start", "job_submitted", "job_status", "job_done", "job_failed"):
            self.graph_canvas.update_job(job_key, status, lsf_name, job_id)

        if event == "job_done":
            self.completed_jobs += 1
            self._update_stats()
            if self.total_jobs:
                self.progress_var.set(100 * self.completed_jobs / self.total_jobs)

        if event == "job_failed":
            self.completed_jobs += 1
            self._update_stats()
            self._update_status("Failed", COLORS["failed"])

        if (
            self._detail_dialog
            and self._detail_dialog.job_key == job_key
            and self._detail_dialog.win.winfo_exists()
        ):
            self._detail_dialog._refresh()

        self._update_action_buttons()

    def _update_stats(self):
        self.stats_label.config(
            text=f"Jobs: {self.completed_jobs}/{self.total_jobs} completed"
        )

    # ── Run flow ──────────────────────────────────────────────────────────────

    def _start_flow(self, config: Dict, job_filter=None, reset_incomplete: bool = False):
        """Shared launcher for full run and rerun."""
        if not reset_incomplete:
            self.graph_model = FlowGraphModel(config)
            self.graph_canvas.set_model(self.graph_model)
            self.graph_canvas.reset()
            self.completed_jobs = 0
            self.progress_var.set(0)
        else:
            for node in self.graph_model.nodes:
                if node.get("status") in DONE_STATUSES:
                    continue
                node.update(
                    status="pending",
                    lsf_name="",
                    job_id="",
                    start_time=None,
                    end_time=None,
                )
            self.completed_jobs = sum(
                1 for node in self.graph_model.nodes
                if node.get("status") in DONE_STATUSES
            )
            if self.total_jobs:
                self.progress_var.set(100 * self.completed_jobs / self.total_jobs)
            self.graph_canvas.redraw()

        self.total_jobs = len(self.graph_model.nodes)
        self._refresh_job_selector()
        self._update_stats()

        self.is_running = True
        self.run_btn.config(state=tk.DISABLED)
        self.rerun_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self._update_action_buttons()
        self._update_status("Running…", COLORS["running"])

        thread = threading.Thread(
            target=self._run_flow_thread,
            args=(config, job_filter),
            daemon=True,
        )
        thread.start()

    def _run_flow(self):
        config = self._load_config()
        if not config:
            messagebox.showerror("Error", f"Unable to load config: {self.config_path_var.get()}")
            return

        alive = self.job_registry.alive_entries()
        if alive:
            self._log_callback(
                f"Warning: {len(alive)} previous LSF job(s) still running. Use Stop to kill them.",
                "WARNING",
            )

        self.flow_config = config
        self._start_flow(config)

    def _rerun_from_failure(self):
        config = self._load_config()
        if not config:
            messagebox.showerror("Error", f"Unable to load config: {self.config_path_var.get()}")
            return

        if not self.graph_model or not self.graph_model.nodes:
            messagebox.showinfo("Rerun", "No jobs loaded.")
            return

        if self.is_running or self._has_rerun_blocking_status() or self.kill_monitor.targets:
            messagebox.showinfo(
                "Rerun",
                "Cannot rerun while a job is RUN or KILLING.",
            )
            return

        skip_keys = {
            node["key"]
            for node in self.graph_model.nodes
            if node.get("status") in DONE_STATUSES
        }
        rerun_count = len(self.graph_model.nodes) - len(skip_keys)
        if rerun_count == 0:
            messagebox.showinfo("Rerun", "All jobs are DONE. Nothing to rerun.")
            return

        def job_filter(job_key: str) -> bool:
            return job_key not in skip_keys

        self.flow_config = config
        self._log_callback(
            f"Rerun: {rerun_count} failed/waiting job(s), "
            f"skipping {len(skip_keys)} DONE job(s)",
            "INFO",
        )
        self._start_flow(config, job_filter=job_filter, reset_incomplete=True)

    def _run_flow_thread(self, config, job_filter=None):
        try:
            session_log_dir = get_config().runner.session_log_dir
            log_file = f"{session_log_dir}/flow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            self.runner = create_flow_runner(
                log_file=log_file,
                log_callback=self._log_callback,
                job_callback=self._job_callback,
            )
            self._log_callback(f"Flow log → {log_file}", "INFO")
            self._log_callback("Starting flow execution", "INFO")
            self.runner.run_flow(config, job_filter=job_filter)
            self.root.after(0, lambda: self._update_status("Completed ✓", COLORS["done"]))
            self.root.after(0, lambda: messagebox.showinfo("Success", "Flow completed successfully!"))
        except Exception as e:
            self._log_callback(f"Error: {str(e)}", "ERROR")
            self.root.after(0, lambda: self._update_status("Failed", COLORS["failed"]))
            self.root.after(0, lambda: messagebox.showerror("Error", f"Flow execution failed:\n{e}"))
        finally:
            self.is_running = False
            self.job_tailer.stop()
            self.root.after(0, lambda: self.run_btn.config(state=tk.NORMAL))
            self.root.after(0, self._update_action_buttons)

    def _stop_flow(self):
        alive = self.job_registry.alive_entries()
        if not alive:
            messagebox.showinfo("Stop", "No running LSF jobs found.")
            return

        if not messagebox.askyesno(
            "Stop All Jobs",
            f"Kill {len(alive)} running LSF job(s)?\n"
            "Status will show KILLING until confirmed dead (every 15s).",
        ):
            return

        self._request_kill_entries(alive)

    def _update_status(self, status: str, color: str = COLORS["accent"]):
        self.status_label.config(text=status, fg=color)

    def run(self):
        self.window.mainloop()


def main():
    root = tk.Tk()
    gui = FlowRunnerGUI(root)
    gui.run()


if __name__ == "__main__":
    main()
