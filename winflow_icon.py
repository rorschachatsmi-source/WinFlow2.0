"""Apply the WinFlow window / desktop icon (Linux-friendly PNG)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    import tkinter as tk

_ASSETS = Path(__file__).resolve().parent / "assets"

# Prefer mid-size PNG for window chrome; fall back through common sizes.
_ICON_CANDIDATES = (
    "winflow.png",
    "winflow_128.png",
    "winflow_64.png",
    "winflow_48.png",
    "winflow_32.png",
    "winflow.gif",
)


def icon_path() -> Optional[Path]:
    """Preferred icon file for window chrome and .desktop entries."""
    for name in _ICON_CANDIDATES:
        path = _ASSETS / name
        if path.is_file():
            return path
    return None


def icon_paths_for_photo() -> List[Path]:
    """All available PNG/GIF sizes (largest first) for multi-resolution iconphoto."""
    names = (
        "winflow_256.png",
        "winflow_128.png",
        "winflow_64.png",
        "winflow_48.png",
        "winflow_32.png",
        "winflow.png",
        "winflow.gif",
    )
    found: List[Path] = []
    seen_sizes = set()
    for name in names:
        path = _ASSETS / name
        if not path.is_file():
            continue
        size = path.stat().st_size
        # Skip byte-identical copies (e.g. winflow.png == winflow_128.png).
        if size in seen_sizes:
            continue
        seen_sizes.add(size)
        found.append(path)
    return found


def apply_window_icon(root: "tk.Misc") -> Optional["tk.PhotoImage"]:
    """
    Set the window icon via ``iconphoto`` (works on Linux/X11 with PNG).

    Keeps references on ``root._winflow_icons`` so Tk does not garbage-collect
    the images. Returns the primary PhotoImage, or None if unavailable.
    """
    import tkinter as tk

    paths = icon_paths_for_photo()
    if not paths:
        return None
    try:
        images = [tk.PhotoImage(file=str(p)) for p in paths]
        # True = also apply to future transient/toplevel dialogs when possible.
        # Passing multiple sizes lets the WM pick a suitable resolution.
        root.winfo_toplevel().iconphoto(True, *images)
        root._winflow_icons = images  # type: ignore[attr-defined]
        return images[0]
    except tk.TclError:
        return None
