"""Build context passed to flow builders."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from winflow_config import get_config


def _generator_defaults():
    cfg = get_config().generator
    return cfg.default_setting_file, cfg.default_blocks_file, cfg.default_output_file


@dataclass
class BuildContext:
    """Inputs available when generating a flow document."""

    settings: Dict[str, str]
    blocks: List[Dict[str, str]]
    setting_path: Path = field(default_factory=lambda: Path(_generator_defaults()[0]))
    blocks_path: Path = field(default_factory=lambda: Path(_generator_defaults()[1]))
    output_path: Path = field(default_factory=lambda: Path(_generator_defaults()[2]))
