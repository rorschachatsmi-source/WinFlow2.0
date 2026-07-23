#!/usr/bin/env python3
"""
flow_generator_gui.py

Visual editor for WinFlow flow.json documents.

- Drag job nodes on a canvas to arrange and reorder within a task
- Load templates (Blank, PV) with optional setting.sh / block_stream.list
- Export a runnable flow.json in one click
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from flow_generator.core.io import write_flow
from flow_graph import EDGE_TASK_ORDER
from flow_generator.gui.deps import get_file_parent_keys, get_parent_keys, link_jobs, set_job_parents, unlink_jobs
from flow_generator.gui.document import (
    FlowDocument,
    TemplateOptions,
    _job_key,
    apply_template,
    auto_layout_all,
    document_to_flow,
    flow_to_document,
)
from flow_generator.gui.graph import JobGraph, build_job_graph
from flow_generator.gui.nodes import list_nodes_by_flow, load_node, node_dir, node_summary
from winflow_config import get_config
from winflow_icon import apply_window_icon

# Segoe UI / Cascadia Mono are Windows fonts; missing glyphs on Linux X11 often
# trigger RENDER RenderAddGlyphs BadLength errors. Use Linux-safe fallbacks.
# Avoid emoji / astral Unicode in labels — color-emoji font fallback crashes Tk.
UI_FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
MONO_FONT = "Cascadia Mono" if sys.platform == "win32" else "DejaVu Sans Mono"
# ── Visual theme (aligned with Runner flat style) ─────────────────────────────

COLORS = {
    "bg": "#f0f2f5",
    "header": "#ffffff",
    "header_text": "#24292f",
    "header_sub": "#656d76",
    "header_accent": "#0969da",
    "panel": "#ffffff",
    "panel_alt": "#f6f8fa",
    "panel_inset": "#f6f8fa",
    "border": "#d0d7de",
    "border_strong": "#afb8c1",
    "text": "#24292f",
    "muted": "#656d76",
    "accent": "#0969da",
    "accent_dark": "#0550ae",
    "accent_soft": "#ddf4ff",
    "btn": "#f6f8fa",
    "btn_hover": "#eaeef2",
    "btn_active": "#ddf4ff",
    "btn_active_fg": "#0550ae",
    "success": "#1a7f37",
    "warning": "#9a6700",
    "danger": "#cf222e",
    "node": "#ffffff",
    "node_border": "#d0d7de",
    "node_accent_bar": "#0969da",
    "node_sel": "#ddf4ff",
    "node_sel_border": "#0969da",
    "node_parent": "#dafbe1",
    "node_parent_border": "#1a7f37",
    "node_child": "#fff8c5",
    "node_child_border": "#bf8700",
    "node_link_src": "#fff1e5",
    "node_link_src_border": "#bc4c00",
    "shadow": "#1f232820",
    "edge": "#afb8c1",
    "edge_task_order": "#d0d7de",
    "edge_active": "#0969da",
    "edge_dim": "#e6eaef",
    "edge_label": "#656d76",
    "stage_band": "#f6f8fa",
    "stage_band_edge": "#e6eaef",
    "stage_label": "#656d76",
    "status_bg": "#ffffff",
    "tooltip_bg": "#ffffe1",
    "sep": "#d0d7de",
    "canvas_dot": "#d0d7de",
}

FONTS = {
    "title": (UI_FONT, 14, "bold"),
    "subtitle": (UI_FONT, 9),
    "section": (UI_FONT, 10, "bold"),
    "body": (UI_FONT, 9),
    "mono": (MONO_FONT, 9),
    "node": (UI_FONT, 9, "bold"),
    "hint": (UI_FONT, 8),
    "toolbar": (UI_FONT, 9),
    "bold": (UI_FONT, 9, "bold"),
}


def _rebuild_fonts() -> None:
    """Refresh FONTS tuples after UI_FONT / MONO_FONT may have changed."""
    global FONTS
    FONTS = {
        "title": (UI_FONT, 14, "bold"),
        "subtitle": (UI_FONT, 9),
        "section": (UI_FONT, 10, "bold"),
        "body": (UI_FONT, 9),
        "mono": (MONO_FONT, 9),
        "node": (UI_FONT, 9, "bold"),
        "hint": (UI_FONT, 8),
        "toolbar": (UI_FONT, 9),
        "bold": (UI_FONT, 9, "bold"),
    }


def configure_safe_tk_fonts(root: tk.Misc) -> None:
    """Pin Tk named fonts so fontconfig does not fall back to Noto Color Emoji."""
    global UI_FONT, MONO_FONT
    available = {name.lower(): name for name in tkfont.families(root)}

    def _pick(candidates):
        for name in candidates:
            hit = available.get(name.lower())
            if hit:
                return hit
        return candidates[0]

    if sys.platform == "win32":
        UI_FONT = _pick(("Segoe UI", "Arial", "Tahoma"))
        MONO_FONT = _pick(("Cascadia Mono", "Consolas", "Courier New"))
    else:
        UI_FONT = _pick(("DejaVu Sans", "Liberation Sans", "FreeSans", "Helvetica"))
        MONO_FONT = _pick(("DejaVu Sans Mono", "Liberation Mono", "FreeMono", "Courier"))

    for font_name, family, size in (
        ("TkDefaultFont", UI_FONT, 9),
        ("TkTextFont", UI_FONT, 9),
        ("TkMenuFont", UI_FONT, 9),
        ("TkHeadingFont", UI_FONT, 10),
        ("TkCaptionFont", UI_FONT, 9),
        ("TkSmallCaptionFont", UI_FONT, 8),
        ("TkTooltipFont", UI_FONT, 8),
        ("TkFixedFont", MONO_FONT, 9),
    ):
        try:
            tkfont.nametofont(font_name).configure(family=family, size=size)
        except tk.TclError:
            pass
    _rebuild_fonts()


def _setup_styles(root: tk.Misc) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("App.TFrame", background=COLORS["bg"])
    style.configure("Card.TFrame", background=COLORS["panel"])
    style.configure("Card.TLabelframe", background=COLORS["panel"])
    style.configure(
        "Card.TLabelframe.Label",
        background=COLORS["panel"],
        foreground=COLORS["text"],
        font=FONTS["section"],
    )
    style.configure(
        "Panel.TLabel",
        background=COLORS["panel"],
        foreground=COLORS["text"],
        font=FONTS["body"],
    )
    style.configure(
        "Muted.TLabel",
        background=COLORS["panel"],
        foreground=COLORS["muted"],
        font=FONTS["hint"],
    )
    style.configure(
        "Accent.TButton",
        font=(UI_FONT, 9, "bold"),
        padding=(14, 6),
    )
    style.configure(
        "Gen.TCombobox",
        fieldbackground=COLORS["panel_alt"],
        background=COLORS["panel_alt"],
        foreground=COLORS["text"],
        padding=4,
    )
    _install_checkmark_checkbuttons(style, root)
    return style


def _install_checkmark_checkbuttons(style: ttk.Style, master: tk.Misc) -> None:
    """No-op kept for winflow_gui compatibility (dialogs use tk.Checkbutton)."""
    del style, master


def _option_checkbutton(parent: tk.Misc, text: str, variable: tk.BooleanVar) -> tk.Checkbutton:
    """Visible checkbox that is not affected by clam ttk theme artwork."""
    return tk.Checkbutton(
        parent,
        text=text,
        variable=variable,
        bg=COLORS["panel"],
        fg=COLORS["text"],
        activebackground=COLORS["panel"],
        activeforeground=COLORS["text"],
        selectcolor=COLORS["panel_alt"],
        font=FONTS["body"],
        anchor="w",
        highlightthickness=0,
        bd=0,
    )


def _flat_button(
    parent: tk.Misc,
    text: str,
    command,
    *,
    primary: bool = False,
    danger: bool = False,
    padx: int = 12,
    pady: int = 5,
) -> tk.Button:
    """Runner-style flat button with simple hover feedback."""
    if primary:
        bg, fg, hover = COLORS["accent"], "#ffffff", COLORS["accent_dark"]
    elif danger:
        bg, fg, hover = "#fff1f0", COLORS["danger"], "#ffe0de"
    else:
        bg, fg, hover = COLORS["btn"], COLORS["text"], COLORS["btn_hover"]

    btn = tk.Button(
        parent,
        text=text,
        command=command,
        font=FONTS["toolbar"] if not primary else (UI_FONT, 9, "bold"),
        relief=tk.FLAT,
        bg=bg,
        fg=fg,
        activebackground=hover,
        activeforeground=fg if not primary else "#ffffff",
        bd=0,
        padx=padx,
        pady=pady,
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=COLORS["border"] if not primary else COLORS["accent"],
        highlightcolor=COLORS["accent"],
    )
    btn._flat_bg = bg  # type: ignore[attr-defined]
    btn._flat_fg = fg  # type: ignore[attr-defined]
    btn._flat_hover = hover  # type: ignore[attr-defined]

    def _enter(_e, b=btn, h=hover):
        if str(b["state"]) != "disabled":
            b.configure(bg=h)

    def _leave(_e, b=btn):
        if str(b["state"]) != "disabled":
            b.configure(bg=getattr(b, "_flat_bg", COLORS["btn"]))

    btn.bind("<Enter>", _enter)
    btn.bind("<Leave>", _leave)
    return btn


def _set_flat_toggle(btn: tk.Button, active: bool) -> None:
    if active:
        btn._flat_bg = COLORS["btn_active"]  # type: ignore[attr-defined]
        btn._flat_fg = COLORS["btn_active_fg"]  # type: ignore[attr-defined]
        btn._flat_hover = COLORS["accent_soft"]  # type: ignore[attr-defined]
        btn.configure(
            bg=COLORS["btn_active"],
            fg=COLORS["btn_active_fg"],
            highlightbackground=COLORS["accent"],
            font=(UI_FONT, 9, "bold"),
        )
    else:
        btn._flat_bg = COLORS["btn"]  # type: ignore[attr-defined]
        btn._flat_fg = COLORS["text"]  # type: ignore[attr-defined]
        btn._flat_hover = COLORS["btn_hover"]  # type: ignore[attr-defined]
        btn.configure(
            bg=COLORS["btn"],
            fg=COLORS["text"],
            highlightbackground=COLORS["border"],
            font=FONTS["toolbar"],
        )


def _card(parent: tk.Misc, title: str = "") -> Tuple[tk.Frame, tk.Frame]:
    """White bordered card; returns (outer, body)."""
    outer = tk.Frame(
        parent,
        bg=COLORS["panel"],
        highlightthickness=1,
        highlightbackground=COLORS["border"],
    )
    if title:
        tk.Label(
            outer,
            text=title,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=FONTS["section"],
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 0))
    body = tk.Frame(outer, bg=COLORS["panel"])
    body.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
    return outer, body


def _activate_modal(dialog: tk.Toplevel, attempt: int = 0) -> None:
    """Show a dialog and grab focus once the window is mapped."""
    dialog.update_idletasks()
    dialog.deiconify()
    dialog.lift()
    dialog.focus_force()
    try:
        dialog.wait_visibility()
        dialog.grab_set()
    except tk.TclError:
        if attempt < 20:
            dialog.after(50, lambda: _activate_modal(dialog, attempt + 1))


class CanvasTooltip:
    def __init__(self, canvas: tk.Canvas):
        self.canvas = canvas
        self._tip: Optional[tk.Toplevel] = None

    def show(self, x_root: int, y_root: int, text: str):
        self.hide()
        self._tip = tk.Toplevel(self.canvas)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x_root + 14}+{y_root + 14}")
        frame = tk.Frame(
            self._tip,
            bg=COLORS["tooltip_bg"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        frame.pack()
        tk.Label(
            frame,
            text=text,
            justify=tk.LEFT,
            background=COLORS["tooltip_bg"],
            foreground=COLORS["text"],
            font=FONTS["body"],
        ).pack()

    def hide(self):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


def _rounded_rect(canvas: tk.Canvas, x0, y0, x1, y1, r: int, **kwargs):
    if r > (x1 - x0) / 2:
        r = int((x1 - x0) / 2)
    if r > (y1 - y0) / 2:
        r = int((y1 - y0) / 2)
    points = [
        x0 + r, y0,
        x1 - r, y0,
        x1, y0,
        x1, y0 + r,
        x1, y1 - r,
        x1, y1,
        x1 - r, y1,
        x0 + r, y1,
        x0, y1,
        x0, y1 - r,
        x0, y0 + r,
        x0, y0,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class FlowEditorCanvas(tk.Canvas):
    """Canvas with draggable job-node rectangles."""

    NODE_W, NODE_H = 158, 76
    CORNER_R = 8

    def __init__(self, parent, on_select=None, on_edit=None, on_link=None, on_link_mode=None, **kwargs):
        super().__init__(
            parent,
            bg=COLORS["panel_alt"],
            highlightthickness=0,
            **kwargs,
        )
        self.on_select = on_select
        self.on_edit = on_edit
        self.on_link = on_link
        self.on_link_mode = on_link_mode
        self.document: Optional[FlowDocument] = None
        self.selected_key: Optional[str] = None
        self.link_mode: Optional[str] = None
        self._link_source: Optional[str] = None
        self._drag_key: Optional[str] = None
        self._drag_offset: Tuple[int, int] = (0, 0)
        self._graph: Optional[JobGraph] = None
        self._tooltip = CanvasTooltip(self)
        self._label_font = tkfont.Font(font=FONTS["node"])

        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Button-4>", self._on_mousewheel)
        self.bind("<Button-5>", self._on_mousewheel)
        self.bind("<Escape>", self._on_escape)

    def set_link_mode(self, mode: Optional[str]) -> None:
        self.link_mode = mode
        self._link_source = None
        self.config(cursor="crosshair" if mode else "")
        if self.on_link_mode:
            self.on_link_mode(mode)

    def _on_escape(self, _event):
        if self.link_mode:
            self.set_link_mode(None)
            self.redraw()

    def _event_xy(self, event) -> Tuple[float, float]:
        """Convert window event coords to canvas coords (accounts for scroll)."""
        return self.canvasx(event.x), self.canvasy(event.y)

    def _on_mousewheel(self, event):
        if event.num == 5 or getattr(event, "delta", 0) < 0:
            self.yview_scroll(1, "units")
        elif event.num == 4 or getattr(event, "delta", 0) > 0:
            self.yview_scroll(-1, "units")

    def set_document(self, document: FlowDocument, keep_selection: bool = False):
        self.document = document
        if not keep_selection:
            self.selected_key = None
        self.redraw()

    def select(self, key: Optional[str]):
        self.selected_key = key
        self.redraw()
        if self.on_select:
            self.on_select(key)

    def redraw(self):
        self.delete("all")
        if not self.document:
            self._draw_placeholder("Load a template or open flow.json to begin")
            return

        jobs = list(self.document.iter_jobs())
        if not jobs:
            self._draw_placeholder("No jobs yet - add a job or load a template")
            return

        self._graph = build_job_graph(self.document)
        parent_keys: Set[str] = set()
        child_keys: Set[str] = set()
        active_edges: Set[Tuple[str, str]] = set()
        if self.selected_key and self._graph:
            parent_keys = set(self._graph.parents.get(self.selected_key, []))
            child_keys = set(self._graph.children.get(self.selected_key, []))
            for src, dst, _label in self._graph.edges:
                if src == self.selected_key or dst == self.selected_key:
                    active_edges.add((src, dst))

        self._draw_stage_bands()
        self._draw_edges(active_edges)
        for stage_name, task_name, job in jobs:
            key = _job_key(stage_name, task_name, job["name"])
            x, y = self.document.positions.get(key, (80, 60))
            role = "link_source" if key == self._link_source else (
                "selected" if key == self.selected_key else (
                    "parent" if key in parent_keys else (
                        "child" if key in child_keys else "normal"
                    )
                )
            )
            parent_count = len(self._graph.parents.get(key, [])) if self._graph else 0
            child_count = len(self._graph.children.get(key, [])) if self._graph else 0
            self._draw_node(key, stage_name, task_name, job, x, y, role, parent_count, child_count)

        self._draw_layer_labels()
        self._update_scrollregion()

    def _draw_placeholder(self, text: str):
        w = self.winfo_width() or 400
        h = self.winfo_height() or 200
        cx, cy = w // 2, h // 2
        box_w, box_h = min(420, w - 48), 120
        x0, y0 = cx - box_w // 2, cy - box_h // 2
        _rounded_rect(
            self,
            x0, y0, x0 + box_w, y0 + box_h,
            12,
            fill=COLORS["panel"],
            outline=COLORS["border"],
            width=1,
        )
        self.create_text(
            cx,
            cy - 18,
            text=text,
            fill=COLORS["text"],
            font=(UI_FONT, 11),
        )
        self.create_text(
            cx,
            cy + 14,
            text="Load Template  |  Open flow.json  |  Add Job",
            fill=COLORS["muted"],
            font=FONTS["hint"],
        )

    def _update_scrollregion(self):
        if not self.document:
            return
        max_x = max_y = 0
        for pos in self.document.positions.values():
            max_x = max(max_x, pos[0] + self.NODE_W)
            max_y = max(max_y, pos[1] + self.NODE_H)
        self.config(
            scrollregion=(
                0,
                0,
                max(max_x + 100, self.winfo_width()),
                max(max_y + 100, self.winfo_height()),
            )
        )

    def _stage_x_ranges(self) -> Dict[str, Tuple[float, float]]:
        ranges: Dict[str, Tuple[float, float]] = {}
        if not self.document:
            return ranges
        for stage in self.document.stages:
            xs = []
            for task in stage["tasks"]:
                for job in task["jobs"]:
                    key = _job_key(stage["name"], task["name"], job["name"])
                    if key in self.document.positions:
                        xs.append(self.document.positions[key][0])
            if xs:
                pad = self.NODE_W // 2 + 24
                ranges[stage["name"]] = (min(xs) - pad, max(xs) + pad)
        return ranges

    def _draw_stage_bands(self):
        for stage_name, (x0, x1) in self._stage_x_ranges().items():
            self.create_rectangle(
                x0, 32, x1, 2000,
                fill=COLORS["stage_band"],
                outline="",
                tags="band",
            )
            self.create_line(
                x0, 32, x0, 2000,
                fill=COLORS["stage_band_edge"],
                width=1,
                tags="band",
            )
            self.create_line(
                x1, 32, x1, 2000,
                fill=COLORS["stage_band_edge"],
                width=1,
                tags="band",
            )
            # Stage title sits in the top label strip (above typical node tops)
            self.create_text(
                (x0 + x1) / 2,
                12,
                text=stage_name,
                fill=COLORS["stage_label"],
                font=(UI_FONT, 8, "bold"),
                tags="band",
            )
            self.tag_lower("band")

    def _draw_layer_labels(self):
        if not self.document or not self._graph:
            return
        layer_xs: Dict[int, List[float]] = defaultdict(list)
        for key, (x, _y) in self.document.positions.items():
            layer_xs[self._graph.layers.get(key, 0)].append(x)
        for layer, xs in sorted(layer_xs.items()):
            cx = sum(xs) / len(xs)
            label = "inputs" if layer == 0 else f"step {layer}"
            self.create_text(
                cx,
                26,
                text=label,
                fill=COLORS["muted"],
                font=(UI_FONT, 7, "italic"),
            )

    def _draw_edges(self, active_edges: Optional[Set[Tuple[str, str]]] = None):
        if not self.document or not self._graph:
            return
        active_edges = active_edges or set()
        has_selection = bool(self.selected_key)

        for src_key, dst_key, label in self._graph.edges:
            if src_key not in self.document.positions or dst_key not in self.document.positions:
                continue
            is_active = (src_key, dst_key) in active_edges
            is_task_order = label == EDGE_TASK_ORDER
            if has_selection and not is_active:
                color = COLORS["edge_dim"]
                width = 1
            elif is_active:
                color = COLORS["edge_active"]
                width = 3
            elif is_task_order:
                color = COLORS["edge_task_order"]
                width = 1
            else:
                color = COLORS["edge"]
                width = 2
            self._draw_edge(src_key, dst_key, label, color, width)

    def _draw_edge(self, src_key: str, dst_key: str, label: str, color: str, width: int):
        x1, y1 = self.document.positions[src_key]
        x2, y2 = self.document.positions[dst_key]
        sx = x1 + self.NODE_W // 2
        tx = x2 - self.NODE_W // 2
        mid = (sx + tx) / 2
        edge_tag = f"edge:{src_key}:{dst_key}"
        self.create_line(
            sx, y1, mid, y1, mid, y2, tx, y2,
            fill=color,
            width=width,
            arrow=tk.LAST,
            smooth=False,
            tags=edge_tag,
        )
        short = label if len(label) <= 22 else label[:20] + "..."
        self.create_text(
            mid,
            (y1 + y2) / 2 - 8,
            text=short,
            fill=COLORS["edge_label"] if color != COLORS["edge_dim"] else COLORS["muted"],
            font=FONTS["hint"],
            tags=edge_tag,
        )

    def _draw_node(
        self,
        key: str,
        stage: str,
        task: str,
        job: dict,
        x: float,
        y: float,
        role: str = "normal",
        parent_count: int = 0,
        child_count: int = 0,
    ):
        x0, y0 = x - self.NODE_W // 2, y - self.NODE_H // 2
        x1, y1 = x + self.NODE_W // 2, y + self.NODE_H // 2

        # Soft drop shadow (untagged so hit-testing stays on the node body)
        _rounded_rect(
            self,
            x0 + 2, y0 + 3, x1 + 2, y1 + 3,
            self.CORNER_R,
            fill="#d0d7de",
            outline="",
        )

        if role == "selected":
            fill, outline, width, bar = COLORS["node_sel"], COLORS["node_sel_border"], 2, COLORS["accent"]
        elif role == "link_source":
            fill, outline, width, bar = COLORS["node_link_src"], COLORS["node_link_src_border"], 2, COLORS["node_link_src_border"]
        elif role == "parent":
            fill, outline, width, bar = COLORS["node_parent"], COLORS["node_parent_border"], 2, COLORS["node_parent_border"]
        elif role == "child":
            fill, outline, width, bar = COLORS["node_child"], COLORS["node_child_border"], 2, COLORS["node_child_border"]
        else:
            fill, outline, width, bar = COLORS["node"], COLORS["node_border"], 1, COLORS["node_accent_bar"]
        _rounded_rect(self, x0, y0, x1, y1, self.CORNER_R, fill=fill, outline=outline, width=width, tags=key)
        # Left accent stripe
        self.create_rectangle(
            x0 + 1, y0 + 6, x0 + 5, y1 - 6,
            fill=bar,
            outline="",
            tags=key,
        )

        label = job["name"]
        max_label_w = self.NODE_W - 22
        if self._label_font.measure(label) > max_label_w:
            while label and self._label_font.measure(label + "...") > max_label_w:
                label = label[:-1]
            label = (label + "...") if label else "..."
        self.create_text(x + 2, y - 16, text=label, fill=COLORS["text"], font=self._label_font, tags=key)

        meta_parts = [task]
        if job.get("queue"):
            meta_parts.append(job["queue"])
        if job.get("machine"):
            meta_parts.append(f"-m {job['machine']}")
        self.create_text(
            x + 2, y + 2,
            text=" | ".join(meta_parts),
            fill=COLORS["muted"],
            font=FONTS["hint"],
            tags=key,
        )
        cpu = job.get("cpu", 1)
        rel = f"^{parent_count}  v{child_count}" if (parent_count or child_count) else "no deps"
        self.create_text(
            x + 2, y + 20,
            text=f"{cpu} CPU  |  {rel}",
            fill=COLORS["accent_dark"] if role != "normal" else COLORS["muted"],
            font=FONTS["hint"],
            tags=key,
        )
        self.tag_bind(key, "<Enter>", lambda e, j=job, s=stage, t=task: self._on_enter(e, j, s, t))
        self.tag_bind(key, "<Leave>", lambda _e: self._tooltip.hide())

    def _on_enter(self, event, job: dict, stage: str, task: str):
        self.config(cursor="hand2")
        lines = [
            job["name"],
            f"{stage} / {task}",
            "",
            f"queue:   {job.get('queue', '') or '(default)'}",
            f"machine: {job.get('machine', '') or '(any)'}",
            f"cpu:     {job.get('cpu', 1)}",
            "",
            job.get("command", "") or "(no command)",
        ]
        self._tooltip.show(event.x_root, event.y_root, "\n".join(lines))

    def _hit_test(self, x: float, y: float) -> Optional[str]:
        if not self.document:
            return None
        jobs = list(self.document.iter_jobs())
        for stage_name, task_name, job in reversed(jobs):
            key = _job_key(stage_name, task_name, job["name"])
            nx, ny = self.document.positions.get(key, (0, 0))
            if abs(x - nx) <= self.NODE_W // 2 and abs(y - ny) <= self.NODE_H // 2:
                return key
        return None

    def _on_press(self, event):
        cx, cy = self._event_xy(event)
        key = self._hit_test(cx, cy)

        if self.link_mode:
            if not key:
                return
            if self._link_source is None:
                self._link_source = key
                self.select(key)
                self.redraw()
                return
            if self._link_source != key and self.on_link:
                self.on_link(self.link_mode, self._link_source, key)
            self._link_source = None
            self.set_link_mode(None)
            return

        self.select(key)
        if key and self.document:
            nx, ny = self.document.positions[key]
            self._drag_key = key
            self._drag_offset = (cx - nx, cy - ny)

    def _on_drag(self, event):
        if not self._drag_key or not self.document:
            return
        cx, cy = self._event_xy(event)
        nx = cx - self._drag_offset[0]
        ny = cy - self._drag_offset[1]
        self.document.positions[self._drag_key] = (nx, ny)
        self.redraw()
        self.select(self._drag_key)

    def _on_release(self, _event):
        # Drag only updates canvas positions; job list order stays unchanged.
        self._drag_key = None
        self.redraw()

    def _on_double_click(self, event):
        cx, cy = self._event_xy(event)
        key = self._hit_test(cx, cy)
        if not key or not self.on_edit:
            return
        self._drag_key = None
        self.after(1, lambda k=key: self.on_edit(k))


class TemplateLoadDialog(tk.Toplevel):
    """Collect template options (queue, machine, cpu, and PV reference files)."""

    def __init__(self, parent, template_name: str):
        super().__init__(parent)
        self.template_name = template_name.lower()
        self.title(f"Load {template_name} template")
        self.resizable(False, False)
        self.transient(parent)
        self.result: Optional[TemplateOptions] = None

        self.setting_path = tk.StringVar()
        self.blocks_path = tk.StringVar()
        gen_cfg = get_config().generator
        self.queue = tk.StringVar(value=gen_cfg.default_queue)
        self.machine = tk.StringVar(value="")
        self.cpu = tk.StringVar(value=str(gen_cfg.default_cpu))
        self.apr_is_current = tk.BooleanVar(value=False)
        self.apr_prefix = tk.StringVar(value="")

        outer = ttk.Frame(self, padding=20, style="Card.TFrame")
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            outer,
            text=f"{template_name.title()} template",
            style="Panel.TLabel",
            font=FONTS["section"],
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text="Configure LSF resources applied to every job in the template. "
            "Leave machine blank to submit to any host.",
            style="Muted.TLabel",
            wraplength=440,
        ).pack(anchor="w", pady=(6, 14))

        res_frame = ttk.LabelFrame(outer, text=" Job resources ", style="Card.TLabelframe", padding=10)
        res_frame.pack(fill=tk.X, pady=(0, 10))
        for row, (label, var) in enumerate(
            (
                ("Queue", self.queue),
                ("Machine (bsub -m)", self.machine),
                ("CPU", self.cpu),
            )
        ):
            ttk.Label(res_frame, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(res_frame, textvariable=var, width=42).grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
        ttk.Label(
            res_frame,
            text="Machine: space-separated hosts, e.g. host1 host2",
            style="Muted.TLabel",
        ).grid(row=3, column=1, sticky="w", padx=(8, 0))
        res_frame.columnconfigure(1, weight=1)

        if self.template_name == "pv":
            pv_opts = ttk.LabelFrame(outer, text=" PV options ", style="Card.TLabelframe", padding=10)
            pv_opts.pack(fill=tk.X, pady=(0, 10))
            self.use_oasii = tk.BooleanVar(value=True)
            _option_checkbutton(
                pv_opts,
                "Use OASII (add gds2oas after streamOut_TOP; DRC/LVS wait on .oas)",
                self.use_oasii,
            ).pack(anchor="w", fill=tk.X)
            ttk.Label(
                pv_opts,
                text="Unchecked: skip gds2oas; DRC/LVS link behind {top}_Out GDS.",
                style="Muted.TLabel",
                wraplength=420,
            ).pack(anchor="w", pady=(4, 0))

            pv_frame = ttk.LabelFrame(outer, text=" PV reference files (optional) ", style="Card.TLabelframe", padding=10)
            pv_frame.pack(fill=tk.X, pady=(0, 4))
            ttk.Label(
                pv_frame,
                text="When provided, TOP_MODULE, flags, and paths are read from your project files.",
                style="Muted.TLabel",
                wraplength=400,
            ).pack(anchor="w", pady=(0, 8))
            self._file_row(pv_frame, "setting.sh", self.setting_path, [("Shell settings", "*.sh"), ("All", "*.*")])
            self._file_row(
                pv_frame,
                "block_stream.list",
                self.blocks_path,
                [("Block list", "*.list"), ("All", "*.*")],
            )

        if self.template_name == "apr":
            apr_frame = ttk.LabelFrame(outer, text=" APR options ", style="Card.TLabelframe", padding=10)
            apr_frame.pack(fill=tk.X, pady=(0, 4))
            _option_checkbutton(
                apr_frame,
                "isCurrent (include 04_postcts_opt)",
                self.apr_is_current,
            ).pack(anchor="w", fill=tk.X, pady=(0, 8))
            prefix_row = ttk.Frame(apr_frame, style="Card.TFrame")
            prefix_row.pack(fill=tk.X)
            ttk.Label(prefix_row, text="Prefix", style="Panel.TLabel").pack(side=tk.LEFT)
            ttk.Entry(prefix_row, textvariable=self.apr_prefix, width=36).pack(
                side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True
            )
            ttk.Label(
                apr_frame,
                text='Prepended as "_prefix" on each stage name (e.g. prefix "top" -> 01_floorplan_top)',
                style="Muted.TLabel",
                wraplength=400,
            ).pack(anchor="w", pady=(6, 0))

        btn_row = ttk.Frame(outer, style="Card.TFrame")
        btn_row.pack(fill=tk.X, pady=(16, 0))
        _flat_button(btn_row, "Cancel", self._cancel).pack(side=tk.RIGHT, padx=(8, 0))
        _flat_button(btn_row, "Load Template", self._ok, primary=True).pack(side=tk.RIGHT)

        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.update_idletasks()
        req_w = max(self.winfo_reqwidth(), 480)
        req_h = self.winfo_reqheight()
        self.geometry(f"{req_w}x{req_h}")
        _activate_modal(self)

    def _file_row(self, parent, label: str, var: tk.StringVar, filetypes):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=tk.X, pady=6)
        ttk.Label(row, text=label, style="Panel.TLabel").pack(anchor="w")
        inner = ttk.Frame(row, style="Card.TFrame")
        inner.pack(fill=tk.X, pady=(4, 0))
        ttk.Entry(inner, textvariable=var, width=48).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            inner,
            text="Browse...",
            command=lambda: self._browse(var, filetypes),
        ).pack(side=tk.LEFT, padx=(6, 0))

    def _browse(self, var: tk.StringVar, filetypes):
        path = filedialog.askopenfilename(parent=self, filetypes=filetypes)
        if path:
            var.set(path)

    def _ok(self):
        gen_cfg = get_config().generator
        try:
            cpu = int(self.cpu.get().strip() or str(gen_cfg.default_cpu))
        except ValueError:
            messagebox.showerror("Invalid CPU", "CPU must be an integer.", parent=self)
            return
        setting = Path(self.setting_path.get()) if self.setting_path.get().strip() else None
        blocks = Path(self.blocks_path.get()) if self.blocks_path.get().strip() else None
        use_oasii = True
        if self.template_name == "pv":
            use_oasii = bool(self.use_oasii.get())
        self.result = TemplateOptions(
            queue=self.queue.get().strip() or gen_cfg.default_queue,
            machine=self.machine.get().strip(),
            cpu=cpu,
            setting_path=setting,
            blocks_path=blocks,
            apr_is_current=self.apr_is_current.get(),
            apr_prefix=self.apr_prefix.get().strip(),
            use_oasii=use_oasii,
        )
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    @classmethod
    def ask(cls, parent, template_name: str) -> Optional[TemplateOptions]:
        dlg = cls(parent, template_name)
        parent.wait_window(dlg)
        return dlg.result


class AddJobDialog(tk.Toplevel):
    """Pick a predefined job node grouped by flow_name category."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add Job")
        self.resizable(True, True)
        self.minsize(640, 420)
        self.transient(parent)
        self.result: Optional[str] = None  # node stem

        outer = ttk.Frame(self, padding=20, style="Card.TFrame")
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="Add job from library", style="Panel.TLabel", font=FONTS["section"]).pack(anchor="w")
        ttk.Label(
            outer,
            text=f"Pick a predefined node grouped by flow | {node_dir()}",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 12))

        body = ttk.Frame(outer, style="Card.TFrame")
        body.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(body, style="Card.TFrame")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 12))
        right = ttk.Frame(body, style="Card.TFrame")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(left, show="tree", selectmode="browse", height=18)
        scroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.config(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.column("#0", width=220, stretch=True)

        self.preview = scrolledtext.ScrolledText(
            right,
            width=52,
            height=18,
            font=FONTS["mono"],
            relief="flat",
            state=tk.DISABLED,
        )
        self.preview.pack(fill=tk.BOTH, expand=True)

        # iid -> node stem (None for category headers)
        self._stem_by_iid: Dict[str, Optional[str]] = {}
        self._populate_tree()
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-Button-1>", self._on_double_click)

        btn_row = ttk.Frame(outer, style="Card.TFrame")
        btn_row.pack(fill=tk.X, pady=(12, 0))
        _flat_button(btn_row, "Cancel", self._cancel).pack(side=tk.RIGHT)
        _flat_button(btn_row, "Add", self._ok, primary=True).pack(side=tk.RIGHT, padx=(0, 8))

        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Return>", lambda _e: self._ok())
        _activate_modal(self)

    def _populate_tree(self):
        first_job_iid = None
        for flow_name, jobs in list_nodes_by_flow():
            cat_iid = f"flow:{flow_name}"
            self.tree.insert("", tk.END, iid=cat_iid, text=f"{flow_name}:", open=True)
            self._stem_by_iid[cat_iid] = None
            for stem, display in jobs:
                job_iid = f"node:{stem}"
                self.tree.insert(cat_iid, tk.END, iid=job_iid, text=f"  {display}")
                self._stem_by_iid[job_iid] = stem
                if first_job_iid is None:
                    first_job_iid = job_iid
        if first_job_iid:
            self.tree.selection_set(first_job_iid)
            self.tree.focus(first_job_iid)
            self.tree.see(first_job_iid)
        self._on_select()

    def _selected_stem(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel:
            return None
        return self._stem_by_iid.get(sel[0])

    def _on_select(self, _event=None):
        stem = self._selected_stem()
        self.preview.config(state=tk.NORMAL)
        self.preview.delete("1.0", tk.END)
        if stem is None:
            self.preview.insert("1.0", "Select a job under a flow category.")
            self.preview.config(state=tk.DISABLED)
            return
        try:
            text = node_summary(load_node(stem))
        except (OSError, json.JSONDecodeError, ValueError, KeyError, FileNotFoundError) as exc:
            text = f"Failed to load node:\n{exc}"
        self.preview.insert("1.0", text)
        self.preview.config(state=tk.DISABLED)

    def _on_double_click(self, _event=None):
        if self._selected_stem() is not None:
            self._ok()

    def _ok(self):
        stem = self._selected_stem()
        if stem is None:
            messagebox.showinfo("Add Job", "Select a job node (not a category).", parent=self)
            return
        self.result = stem
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    @classmethod
    def ask(cls, parent) -> Optional[str]:
        """Return node stem, or None if cancelled."""
        dlg = cls(parent)
        parent.wait_window(dlg)
        return dlg.result


class JobEditorDialog(tk.Toplevel):
    """Modal dialog to edit a single job."""

    def __init__(self, parent, document: FlowDocument, child_key: str, stage: str, task: str, job: dict, on_save):
        super().__init__(parent)
        self.title("Edit Job")
        self.resizable(False, False)
        self.transient(parent)
        self.on_save = on_save
        self._parent_keys: List[str] = []

        outer = ttk.Frame(self, padding=16, style="Card.TFrame")
        outer.grid(row=0, column=0, sticky="nsew")

        fields = [
            ("Job name", "name", job["name"]),
            ("Stage", "stage", stage),
            ("Task", "task", task),
            ("Command", "command", job.get("command", "")),
            ("Queue", "queue", job.get("queue", "")),
            ("Machine (bsub -m)", "machine", job.get("machine", "")),
            ("CPU", "cpu", str(job.get("cpu", 1))),
            ("Inputs (one per line)", "inputs", "\n".join(job.get("inputs", []))),
            ("Outputs (one per line)", "outputs", "\n".join(job.get("outputs", []))),
        ]

        self.vars: Dict[str, object] = {}
        grid_row = 0
        for label, key, value in fields:
            ttk.Label(outer, text=label, style="Panel.TLabel").grid(row=grid_row, column=0, sticky="nw", pady=5)
            if key in ("inputs", "outputs"):
                widget = scrolledtext.ScrolledText(outer, width=46, height=3, font=FONTS["mono"])
                widget.insert("1.0", value)
                widget.grid(row=grid_row, column=1, sticky="ew", pady=5)
                self.vars[key] = widget
                grid_row += 1
            elif key == "machine":
                var = tk.StringVar(value=value)
                self.vars[key] = var
                ttk.Entry(outer, textvariable=var, width=50).grid(row=grid_row, column=1, sticky="ew", pady=5)
                grid_row += 1
                ttk.Label(
                    outer,
                    text="Space-separated hosts, e.g. host1 host2",
                    style="Muted.TLabel",
                ).grid(row=grid_row, column=1, sticky="w")
                grid_row += 1
            else:
                var = tk.StringVar(value=value)
                self.vars[key] = var
                ttk.Entry(outer, textvariable=var, width=50).grid(row=grid_row, column=1, sticky="ew", pady=5)
                grid_row += 1

        ttk.Label(outer, text="File parents", style="Panel.TLabel").grid(
            row=grid_row, column=0, sticky="nw", pady=5
        )
        parent_box = ttk.Frame(outer, style="Card.TFrame")
        parent_box.grid(row=grid_row, column=1, sticky="ew", pady=5)
        self.parent_listbox = tk.Listbox(
            parent_box,
            height=6,
            selectmode=tk.EXTENDED,
            exportselection=False,
            font=FONTS["mono"],
        )
        parent_scroll = ttk.Scrollbar(parent_box, orient=tk.VERTICAL, command=self.parent_listbox.yview)
        self.parent_listbox.config(yscrollcommand=parent_scroll.set)
        self.parent_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        parent_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        current_parents = set(get_file_parent_keys(document, child_key))
        for stage_name, task_name, other in document.iter_jobs():
            other_key = _job_key(stage_name, task_name, other["name"])
            if other_key == child_key:
                continue
            index = self.parent_listbox.size()
            self.parent_listbox.insert(tk.END, f"{other['name']}  ({stage_name}/{task_name})")
            self._parent_keys.append(other_key)
            if other_key in current_parents:
                self.parent_listbox.selection_set(index)
        grid_row += 1
        ttk.Label(
            outer,
            text="File parents pass outputs into inputs. Link moves the parent "
            "into the child's stage/task (ordered before the child). Unlink "
            "removes the file dep and can split same-task sequence.",
            style="Muted.TLabel",
        ).grid(row=grid_row, column=1, sticky="w")
        grid_row += 1

        btn_row = ttk.Frame(outer, style="Card.TFrame")
        btn_row.grid(row=grid_row, column=0, columnspan=2, pady=(14, 0), sticky="e")
        _flat_button(btn_row, "Cancel", self.destroy).pack(side=tk.RIGHT, padx=(8, 0))
        _flat_button(btn_row, "Save", self._save, primary=True).pack(side=tk.RIGHT)

        self.bind("<Escape>", lambda _e: self.destroy())
        _activate_modal(self)

    def _get(self, key: str) -> str:
        val = self.vars[key]
        if isinstance(val, scrolledtext.ScrolledText):
            return val.get("1.0", "end-1c")
        return val.get().strip()  # type: ignore[union-attr]

    def _save(self):
        lines = lambda k: [ln.strip() for ln in self._get(k).splitlines() if ln.strip()]
        try:
            cpu = int(self._get("cpu") or "1")
        except ValueError:
            messagebox.showerror("Invalid CPU", "CPU must be an integer.", parent=self)
            return
        payload = {
            "name": self._get("name"),
            "stage": self._get("stage"),
            "task": self._get("task"),
            "command": self._get("command"),
            "queue": self._get("queue"),
            "machine": self._get("machine"),
            "cpu": cpu,
            "inputs": lines("inputs"),
            "outputs": lines("outputs"),
            "parent_keys": [self._parent_keys[i] for i in self.parent_listbox.curselection()],
        }
        if not payload["name"]:
            messagebox.showerror("Missing name", "Job name is required.", parent=self)
            return
        self.on_save(payload)
        self.destroy()


class FlowGeneratorPanel(tk.Frame):
    """Embeddable flow generator UI (usable inside a notebook or standalone window)."""

    PANE_RATIO_LEFT = 2
    PANE_RATIO_RIGHT = 5

    def __init__(self, master: tk.Misc, **kwargs):
        configure_safe_tk_fonts(master.winfo_toplevel())
        _setup_styles(master.winfo_toplevel())
        super().__init__(master, bg=COLORS["bg"], **kwargs)
        gen_cfg = get_config().generator

        self.document = blank_document()
        self.output_path = tk.StringVar(value=gen_cfg.default_output_file)
        self.template_var = tk.StringVar(value="blank")
        self.flow_name_var = tk.StringVar(value=self.document.flow_name)
        self.poll_var = tk.StringVar(value=str(self.document.poll_interval))
        self._pane_ready = False

        self._build_ui()
        self.canvas.set_document(self.document)
        self._sync_header_fields()
        self._refresh_meta()

    def _dialog_parent(self) -> tk.Misc:
        return self.winfo_toplevel()

    def get_flow_dict(self) -> dict:
        """Return the current in-memory document as a runnable flow dict."""
        self._apply_header_fields()
        return document_to_flow(self.document)

    def get_output_path(self) -> Path:
        return Path(self.output_path.get().strip() or "flow.json")

    def _build_ui(self):
        # ── Header (light, matches Runner) ──────────────────────────────────
        header = tk.Frame(self, bg=COLORS["panel"])
        header.pack(fill=tk.X, padx=10, pady=(10, 0))
        inner = tk.Frame(header, bg=COLORS["panel"])
        inner.pack(fill=tk.X, padx=12, pady=10)

        tk.Label(
            inner,
            text="WinFlow",
            bg=COLORS["panel"],
            fg=COLORS["accent"],
            font=FONTS["title"],
        ).pack(side=tk.LEFT)
        tk.Label(
            inner,
            text="Generator",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=FONTS["title"],
        ).pack(side=tk.LEFT, padx=(6, 0))
        tk.Label(
            inner,
            text="Design job DAGs | link dependencies | export flow.json",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=FONTS["subtitle"],
        ).pack(side=tk.LEFT, padx=(16, 0))

        tk.Frame(self, height=1, bg=COLORS["border"]).pack(fill=tk.X, padx=10)

        # ── Toolbar ─────────────────────────────────────────────────────────
        toolbar = tk.Frame(self, bg=COLORS["panel"])
        toolbar.pack(fill=tk.X, padx=10, pady=(0, 0))
        tools = tk.Frame(toolbar, bg=COLORS["panel"])
        tools.pack(fill=tk.X, padx=10, pady=8)

        tk.Label(
            tools, text="Template", bg=COLORS["panel"], fg=COLORS["muted"], font=FONTS["hint"]
        ).pack(side=tk.LEFT)
        ttk.Combobox(
            tools,
            textvariable=self.template_var,
            values=["blank", "pv", "apr"],
            state="readonly",
            width=8,
            style="Gen.TCombobox",
        ).pack(side=tk.LEFT, padx=(6, 8))

        _flat_button(tools, "Load", self._load_template).pack(side=tk.LEFT, padx=3)
        _flat_button(tools, "Open...", self._open_flow).pack(side=tk.LEFT, padx=3)

        tk.Frame(tools, width=1, bg=COLORS["sep"]).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)

        _flat_button(tools, "Add Job", self._add_job).pack(side=tk.LEFT, padx=3)
        _flat_button(tools, "Delete", self._delete_job, danger=True).pack(side=tk.LEFT, padx=3)
        self._link_btn = _flat_button(tools, "Link ->", lambda: self._set_link_mode("add"))
        self._link_btn.pack(side=tk.LEFT, padx=3)
        self._unlink_btn = _flat_button(tools, "Unlink", lambda: self._set_link_mode("remove"))
        self._unlink_btn.pack(side=tk.LEFT, padx=3)

        tk.Frame(tools, width=1, bg=COLORS["sep"]).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)
        _flat_button(tools, "Auto Layout", self._auto_layout).pack(side=tk.LEFT, padx=3)

        _flat_button(tools, "Export flow.json", self._export_flow, primary=True, padx=16).pack(
            side=tk.RIGHT, padx=3
        )

        tk.Frame(self, height=1, bg=COLORS["border"]).pack(fill=tk.X, padx=10)

        # ── Body ────────────────────────────────────────────────────────────
        body_wrap = tk.Frame(self, bg=COLORS["bg"])
        body_wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._body = ttk.Panedwindow(body_wrap, orient=tk.HORIZONTAL)
        self._body.pack(fill=tk.BOTH, expand=True)

        left = tk.Frame(self._body, bg=COLORS["bg"])
        right = tk.Frame(self._body, bg=COLORS["bg"])
        self._body.add(left, weight=self.PANE_RATIO_LEFT)
        self._body.add(right, weight=self.PANE_RATIO_RIGHT)
        self._body.bind("<Configure>", self._apply_pane_ratio)

        self._build_sidebar(left)

        canvas_card, canvas_body = _card(right, "Flow canvas")
        canvas_card.pack(fill=tk.BOTH, expand=True)

        hint_row = tk.Frame(canvas_body, bg=COLORS["panel"])
        hint_row.pack(fill=tk.X, pady=(0, 6))
        self._canvas_hint = tk.Label(
            hint_row,
            text="Drag to rearrange | Double-click to edit | Esc cancels link",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=FONTS["hint"],
            anchor="w",
        )
        self._canvas_hint.pack(side=tk.LEFT)

        canvas_frame = tk.Frame(canvas_body, bg=COLORS["panel"])
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        xscroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        yscroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        self.canvas = FlowEditorCanvas(
            canvas_frame,
            on_select=self._on_node_select,
            on_edit=self._edit_job,
            on_link=self._on_canvas_link,
            on_link_mode=self._on_link_mode_changed,
            xscrollcommand=xscroll.set,
            yscrollcommand=yscroll.set,
        )
        xscroll.config(command=self.canvas.xview)
        yscroll.config(command=self.canvas.yview)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        xscroll.grid(row=1, column=0, sticky="ew")
        yscroll.grid(row=0, column=1, sticky="ns")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        legend = tk.Frame(right, bg=COLORS["bg"])
        legend.pack(fill=tk.X, pady=(8, 0))
        for color, label in (
            (COLORS["node_sel_border"], "Selected"),
            (COLORS["node_parent_border"], "Parent"),
            (COLORS["node_child_border"], "Child"),
            (COLORS["node_link_src_border"], "Link source"),
        ):
            swatch = tk.Frame(legend, bg=color, width=10, height=10)
            swatch.pack(side=tk.LEFT, padx=(0, 4))
            swatch.pack_propagate(False)
            tk.Label(
                legend, text=label, bg=COLORS["bg"], fg=COLORS["muted"], font=FONTS["hint"]
            ).pack(side=tk.LEFT, padx=(0, 12))

        # ── Status bar ──────────────────────────────────────────────────────
        status_wrap = tk.Frame(self, bg=COLORS["panel"], highlightthickness=1, highlightbackground=COLORS["border"])
        status_wrap.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=(0, 10))
        status = tk.Frame(status_wrap, bg=COLORS["panel"])
        status.pack(fill=tk.X, padx=12, pady=7)
        self.status_var = tk.StringVar(value="Ready - load a template or open an existing flow.json")
        self.meta_var = tk.StringVar(value="0 jobs")
        tk.Label(
            status,
            textvariable=self.status_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=FONTS["hint"],
            anchor="w",
        ).pack(side=tk.LEFT)
        tk.Label(
            status,
            textvariable=self.meta_var,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=(UI_FONT, 8, "bold"),
            anchor="e",
        ).pack(side=tk.RIGHT)

    def _set_link_mode(self, mode: str):
        if self.canvas.link_mode == mode:
            self.canvas.set_link_mode(None)
            self._set_status("Ready")
            return
        self.canvas.set_link_mode(mode)
        if mode == "add":
            self._set_status(
                "Link mode: click parent, then child "
                "(parent moves into child's stage/task; Esc to cancel)"
            )
        else:
            self._set_status(
                "Unlink mode: click parent, then child "
                "(removes file dep and splits same-task sequence; Esc to cancel)"
            )

    def _on_link_mode_changed(self, mode: Optional[str]):
        self._update_link_buttons(mode)
        if mode is None and self.status_var.get().startswith(("Link mode", "Unlink mode")):
            self._set_status("Ready")

    def _update_link_buttons(self, mode: Optional[str]):
        if not hasattr(self, "_link_btn"):
            return
        _set_flat_toggle(self._link_btn, mode == "add")
        _set_flat_toggle(self._unlink_btn, mode == "remove")
        if hasattr(self, "_canvas_hint"):
            if mode == "add":
                self._canvas_hint.config(
                    text="Link: click parent -> child  |  Esc cancels",
                    fg=COLORS["accent_dark"],
                )
            elif mode == "remove":
                self._canvas_hint.config(
                    text="Unlink: click parent -> child  |  Esc cancels",
                    fg=COLORS["warning"],
                )
            else:
                self._canvas_hint.config(
                    text="Drag to rearrange | Double-click to edit | Esc cancels link",
                    fg=COLORS["muted"],
                )

    def _on_canvas_link(self, mode: str, src: str, dst: str):
        if mode == "add":
            parent = self.document.get_job(src)
            child = self.document.get_job(dst)
            parent_name = parent[2]["name"] if parent else src
            child_name = child[2]["name"] if child else dst
            err, new_child_key, notes = link_jobs(self.document, src, dst)
            if err:
                messagebox.showerror("Link failed", err, parent=self._dialog_parent())
                return
            detail = f" ({'; '.join(notes)})" if notes else ""
            self._set_status(f"Linked {parent_name} -> {child_name}{detail}")
            select_key = new_child_key
        else:
            parent = self.document.get_job(src)
            child = self.document.get_job(dst)
            parent_name = parent[2]["name"] if parent else src
            child_name = child[2]["name"] if child else dst
            new_child_key, notes = unlink_jobs(self.document, src, dst)
            detail = f" ({'; '.join(notes)})" if notes else ""
            if not notes:
                detail = " (no dependency to remove)"
            self._set_status(f"Unlinked {parent_name} -> {child_name}{detail}")
            select_key = new_child_key

        self._update_link_buttons(None)
        self.canvas.set_document(self.document, keep_selection=True)
        self.canvas.select(select_key)

    def _apply_pane_ratio(self, event):
        if self._pane_ready or event.width < 200:
            return
        total = self._body.winfo_width()
        if total > 0:
            self._body.sashpos(0, max(220, int(total * self.PANE_RATIO_LEFT / (self.PANE_RATIO_LEFT + self.PANE_RATIO_RIGHT))))
            self._pane_ready = True

    def _build_sidebar(self, parent: tk.Frame):
        settings_card, form = _card(parent, "Flow settings")
        settings_card.pack(fill=tk.X, pady=(0, 10))

        rows = [
            ("Flow name", self.flow_name_var),
            ("Poll interval (s)", self.poll_var),
        ]
        for i, (label, var) in enumerate(rows):
            tk.Label(
                form, text=label, bg=COLORS["panel"], fg=COLORS["muted"], font=FONTS["hint"]
            ).grid(row=i * 2, column=0, sticky="w")
            entry = tk.Entry(
                form,
                textvariable=var,
                font=FONTS["body"],
                relief=tk.FLAT,
                bg=COLORS["panel_alt"],
                highlightthickness=1,
                highlightbackground=COLORS["border"],
                highlightcolor=COLORS["accent"],
            )
            entry.grid(row=i * 2 + 1, column=0, sticky="ew", pady=(2, 8))

        tk.Label(
            form, text="Output path", bg=COLORS["panel"], fg=COLORS["muted"], font=FONTS["hint"]
        ).grid(row=4, column=0, sticky="w")
        out_row = tk.Frame(form, bg=COLORS["panel"])
        out_row.grid(row=5, column=0, sticky="ew", pady=(2, 0))
        tk.Entry(
            out_row,
            textvariable=self.output_path,
            font=FONTS["body"],
            relief=tk.FLAT,
            bg=COLORS["panel_alt"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        _flat_button(out_row, "...", self._browse_output, padx=8, pady=3).pack(side=tk.LEFT, padx=(4, 0))
        form.columnconfigure(0, weight=1)

        job_card, job_body = _card(parent, "Selected job")
        job_card.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            job_body,
            text="Click a node on the canvas to inspect details.",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=FONTS["hint"],
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 6))

        self.detail = scrolledtext.ScrolledText(
            job_body,
            height=16,
            font=FONTS["mono"],
            bg=COLORS["panel_inset"],
            fg=COLORS["text"],
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
            padx=8,
            pady=8,
            state=tk.DISABLED,
            wrap=tk.WORD,
        )
        self.detail.pack(fill=tk.BOTH, expand=True)
        _flat_button(job_body, "Edit job...", self._edit_selected).pack(fill=tk.X, pady=(10, 0))

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            parent=self._dialog_parent(),
            defaultextension=".json",
            filetypes=[("Flow JSON", "*.json"), ("All", "*.*")],
            initialfile=self.output_path.get() or "flow.json",
        )
        if path:
            self.output_path.set(path)

    def _sync_header_fields(self):
        self.flow_name_var.set(self.document.flow_name)
        self.poll_var.set(str(self.document.poll_interval))

    def _apply_header_fields(self):
        gen_cfg = get_config().generator
        self.document.flow_name = self.flow_name_var.get().strip() or gen_cfg.blank_flow_name
        try:
            self.document.poll_interval = int(
                self.poll_var.get().strip() or str(gen_cfg.poll_interval)
            )
        except ValueError:
            raise ValueError("Poll interval must be an integer")

    def _load_template(self):
        name = self.template_var.get()
        opts = TemplateLoadDialog.ask(self._dialog_parent(), name)
        if opts is None:
            return
        try:
            self.document = apply_template(name, opts)
        except (KeyError, ValueError) as exc:
            messagebox.showerror("Template error", str(exc), parent=self._dialog_parent())
            return
        self._sync_header_fields()
        self.canvas.set_document(self.document)
        self._set_status(f"Loaded {name} template")

    def _open_flow(self):
        path = filedialog.askopenfilename(
            parent=self._dialog_parent(),
            filetypes=[("Flow JSON", "*.json"), ("All", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fp:
                data = json.load(fp)
            self.document = flow_to_document(data)
            self.output_path.set(path)
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            messagebox.showerror("Open failed", str(exc), parent=self._dialog_parent())
            return
        self._sync_header_fields()
        self.canvas.set_document(self.document)
        self._set_status(f"Opened {path}")

    def _add_job(self):
        choice = AddJobDialog.ask(self._dialog_parent())
        if choice is None:
            return

        stage = "stage_1"
        task = "task_1"
        if self.document.stages:
            stage = self.document.stages[-1]["name"]
            if self.document.stages[-1]["tasks"]:
                task = self.document.stages[-1]["tasks"][-1]["name"]

        try:
            job = dict(load_node(choice))
        except (OSError, json.JSONDecodeError, ValueError, KeyError, FileNotFoundError) as exc:
            messagebox.showerror("Add job failed", str(exc), parent=self._dialog_parent())
            return
        job["name"] = self._unique_job_name(job.get("name") or choice)

        key = self.document.add_job(stage, task, job=job)
        self.canvas.set_document(self.document)
        self.canvas.select(key)
        self._set_status(f"Added job from {choice}")
        self._edit_job(key)

    def _unique_job_name(self, base: str) -> str:
        existing = {job["name"] for _s, _t, job in self.document.iter_jobs()}
        if base not in existing:
            return base
        index = 2
        while f"{base}_{index}" in existing:
            index += 1
        return f"{base}_{index}"

    def _delete_job(self):
        key = self.canvas.selected_key
        parent = self._dialog_parent()
        if not key:
            messagebox.showinfo("Delete job", "Select a job node first.", parent=parent)
            return
        if not messagebox.askyesno("Delete job", "Remove the selected job?", parent=parent):
            return
        self.document.remove_job(key)
        self.canvas.set_document(self.document)
        self._set_status("Job removed")

    def _auto_layout(self):
        auto_layout_all(self.document)
        self.canvas.set_document(self.document, keep_selection=True)
        self._set_status("Auto layout applied")

    def _export_flow(self):
        parent = self._dialog_parent()
        try:
            self._apply_header_fields()
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc), parent=parent)
            return

        missing = []
        for _stage, _task, job in self.document.iter_jobs():
            if not job.get("command", "").strip():
                missing.append(job["name"])
        if missing:
            warn = (
                f"{len(missing)} job(s) have no command:\n"
                + ", ".join(missing[:8])
                + ("..." if len(missing) > 8 else "")
                + "\n\nExport anyway?"
            )
            if not messagebox.askyesno("Incomplete jobs", warn, parent=parent):
                return

        out = self.get_output_path()
        try:
            flow = document_to_flow(self.document)
            write_flow(flow, out)
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc), parent=parent)
            return

        self._set_status(f"Exported {out.resolve()}")
        messagebox.showinfo("Export complete", f"Wrote runnable flow to:\n{out.resolve()}", parent=parent)

    def _on_node_select(self, key: Optional[str]):
        self.detail.config(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        if not key or not self.document:
            self.detail.insert("1.0", "No job selected.\n\nClick a node on the canvas\nto view its properties.")
            self.detail.config(state=tk.DISABLED)
            return
        found = self.document.get_job(key)
        if not found:
            self.detail.config(state=tk.DISABLED)
            return
        stage, task, job = found
        graph = build_job_graph(self.document)
        lines = [
            f"name:     {job['name']}",
            f"stage:    {stage}",
            f"task:     {task}",
            f"queue:    {job.get('queue', '') or '(default)'}",
            f"machine:  {job.get('machine', '') or '(any)'}",
            f"cpu:      {job.get('cpu', 1)}",
            "",
            f"command:",
            f"  {job.get('command', '') or '(none)'}",
        ]
        parents = graph.parents.get(key, [])
        children = graph.children.get(key, [])
        if parents:
            lines.append("")
            lines.append("parents:")
            for parent_key in parents:
                p_stage, p_task, p_name = parent_key.split("\0")
                lines.append(f"  ^ {p_name}  ({p_stage}/{p_task})")
        if children:
            lines.append("")
            lines.append("children:")
            for child_key in children:
                c_stage, c_task, c_name = child_key.split("\0")
                lines.append(f"  v {c_name}  ({c_stage}/{c_task})")
        lines.append("")
        lines.append("inputs:")
        inputs = job.get("inputs", [])
        if inputs:
            lines.extend(f"  | {p}" for p in inputs)
        else:
            lines.append("  (none)")
        lines.append("outputs:")
        outputs = job.get("outputs", [])
        if outputs:
            lines.extend(f"  | {p}" for p in outputs)
        else:
            lines.append("  (none)")
        self.detail.insert("1.0", "\n".join(lines))
        self.detail.config(state=tk.DISABLED)

    def _edit_selected(self):
        if self.canvas.selected_key:
            self._edit_job(self.canvas.selected_key)

    def _edit_job(self, key: str):
        found = self.document.get_job(key)
        if not found:
            return
        stage, task, job = found
        parent = self._dialog_parent()

        def on_save(payload: dict):
            new_stage = payload["stage"] or stage
            new_task = payload["task"] or task

            updated: dict = {
                "name": payload["name"],
                "command": payload["command"],
                "queue": payload["queue"],
                "cpu": payload["cpu"],
                "inputs": payload["inputs"],
                "outputs": payload["outputs"],
            }
            machine = str(payload.get("machine", "")).strip()
            if machine:
                updated["machine"] = machine

            new_key = self.document.update_job(key, new_stage, new_task, updated)  # type: ignore[arg-type]
            err = set_job_parents(self.document, new_key, payload.get("parent_keys", []))
            if err:
                messagebox.showerror("Parent assignment failed", err, parent=parent)
                return
            self.canvas.set_document(self.document)
            self.canvas.select(new_key)
            self._set_status(f"Updated job {payload['name']}")

        JobEditorDialog(parent, self.document, key, stage, task, dict(job), on_save)

    def _set_status(self, text: str):
        self.status_var.set(text)
        self._refresh_meta()

    def _refresh_meta(self):
        if not hasattr(self, "meta_var"):
            return
        jobs = list(self.document.iter_jobs()) if self.document else []
        n_jobs = len(jobs)
        n_stages = len(self.document.stages) if self.document else 0
        n_tasks = sum(len(s.get("tasks", [])) for s in (self.document.stages if self.document else []))
        self.meta_var.set(f"{n_stages} stages  |  {n_tasks} tasks  |  {n_jobs} jobs")


class FlowGeneratorApp(tk.Tk):
    """Standalone window wrapping FlowGeneratorPanel."""

    def __init__(self):
        super().__init__()
        configure_safe_tk_fonts(self)
        apply_window_icon(self)
        gui_cfg = get_config().gui
        self.title("WinFlow Generator")
        self.geometry(gui_cfg.generator_window_size)
        self.minsize(*map(int, gui_cfg.generator_window_min.split("x")))
        self.configure(bg=COLORS["bg"])
        self.panel = FlowGeneratorPanel(self)
        self.panel.pack(fill=tk.BOTH, expand=True)


def blank_document() -> FlowDocument:
    return apply_template("blank")


def main():
    app = FlowGeneratorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
