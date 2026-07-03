"""Abstract base class for flow builders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, List

from flow_generator.core.context import BuildContext
from flow_generator.core.models import Flow


class FlowBuilder(ABC):
    """Base class for registered flow generators."""

    flow_type: ClassVar[str] = ""

    @classmethod
    @abstractmethod
    def validate_context(cls, context: BuildContext) -> List[str]:
        """Return validation error messages. Empty list means valid."""

    @classmethod
    @abstractmethod
    def build(cls, context: BuildContext) -> Flow:
        """Build a complete flow document from the given context."""
