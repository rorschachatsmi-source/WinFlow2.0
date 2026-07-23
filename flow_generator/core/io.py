"""Flow document I/O."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from flow_generator.core.models import Flow
from flow_graph import ensure_job_relations


def write_flow(
    flow: Flow,
    path: Union[str, Path],
    *,
    annotate: bool = True,
) -> None:
    """Write flow JSON. Seed parents/children when missing (runnable flows)."""
    if annotate:
        ensure_job_relations(flow["stages"])  # type: ignore[arg-type]
    output = Path(path)
    with output.open("w", encoding="utf-8") as fp:
        json.dump(flow, fp, indent=2)
