"""Parser for block_stream.list files."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Union


def parse_block_stream(path: Union[str, Path] = "block_stream.list") -> List[Dict[str, str]]:
    blocks: List[Dict[str, str]] = []
    list_path = Path(path)

    if not list_path.exists():
        return blocks

    with list_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            blocks.append({"name": parts[0], "workdir": parts[1]})

    return blocks
