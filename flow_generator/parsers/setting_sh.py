"""Parser for csh-style setting.sh files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Union


def parse_setting_sh(path: Union[str, Path] = "setting.sh") -> Dict[str, str]:
    cfg: Dict[str, str] = {}
    pattern = re.compile(r'^\s*set\s+(\S+)\s*=\s*"(.*)"\s*$')

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = pattern.match(line)
            if match:
                key, value = match.groups()
                cfg[key] = value

    return cfg
