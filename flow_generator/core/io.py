"""Flow document I/O."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from flow_generator.core.models import Flow


def write_flow(flow: Flow, path: Union[str, Path]) -> None:
    output = Path(path)
    with output.open("w", encoding="utf-8") as fp:
        json.dump(flow, fp, indent=2)
