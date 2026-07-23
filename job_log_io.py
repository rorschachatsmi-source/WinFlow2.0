"""Helpers for reading large job log files efficiently."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

# Harmless stderr noise from batch/LSF jobs (no tty).
_JOB_LOG_NOISE_PATTERNS = [
    re.compile(r"^TERM environment variable not set\.?\s*$", re.IGNORECASE),
]


def is_job_log_noise(line: str) -> bool:
    text = line.strip()
    if not text:
        return True
    return any(p.match(text) for p in _JOB_LOG_NOISE_PATTERNS)


def _drop_prefix_lines(buf: bytes, drop: int) -> Tuple[bytes, int]:
    """Drop ``drop`` newline-terminated lines from the start of ``buf``."""
    idx = 0
    for _ in range(drop):
        nl = buf.find(b"\n", idx)
        if nl == -1:
            return b"", len(buf)
        idx = nl + 1
    return buf[idx:], idx


def read_file_tail_lines(path: Path, max_lines: int) -> Tuple[List[str], int, bool]:
    """
    Read the last ``max_lines`` of a text file.

    Returns (lines, start_byte_offset, truncated).
    ``start_byte_offset`` is where the returned lines begin; ``truncated`` is True
    when earlier content exists before that offset.
    """
    if max_lines <= 0:
        return [], 0, False
    try:
        size = path.stat().st_size
    except OSError:
        return [], 0, False
    if size == 0:
        return [], 0, False

    block = 8192
    with path.open("rb") as fp:
        pos = size
        buf = b""
        while pos > 0 and buf.count(b"\n") <= max_lines:
            step = min(block, pos)
            pos -= step
            fp.seek(pos)
            buf = fp.read(step) + buf

        # Drop possibly-partial first line when we did not start at byte 0.
        if pos > 0:
            nl = buf.find(b"\n")
            if nl != -1:
                pos += nl + 1
                buf = buf[nl + 1 :]

        text = buf.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            drop = len(lines) - max_lines
            buf, skipped = _drop_prefix_lines(buf, drop)
            pos += skipped
            lines = lines[-max_lines:]

        truncated = pos > 0
        return lines, pos, truncated


def read_lines_before(path: Path, before: int, max_lines: int) -> Tuple[List[str], int]:
    """Read up to ``max_lines`` ending at byte offset ``before``."""
    if before <= 0 or max_lines <= 0:
        return [], 0
    block = 8192
    with path.open("rb") as fp:
        pos = before
        buf = b""
        while pos > 0 and buf.count(b"\n") <= max_lines:
            step = min(block, pos)
            pos -= step
            fp.seek(pos)
            chunk = fp.read(step)
            buf = chunk + buf

        # Ensure buf only covers [pos, before).
        excess = len(buf) - (before - pos)
        if excess > 0:
            buf = buf[: len(buf) - excess]

        if pos > 0:
            nl = buf.find(b"\n")
            if nl != -1:
                pos += nl + 1
                buf = buf[nl + 1 :]

        text = buf.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            drop = len(lines) - max_lines
            buf, skipped = _drop_prefix_lines(buf, drop)
            pos += skipped
            lines = lines[-max_lines:]
        return lines, pos
