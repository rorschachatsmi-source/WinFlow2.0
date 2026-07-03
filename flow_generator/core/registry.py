"""Flow builder registry."""

from __future__ import annotations

from typing import Dict, List, Type

from flow_generator.core.builder import FlowBuilder

_REGISTRY: Dict[str, Type[FlowBuilder]] = {}


def register(name: str):
    """Register a flow builder under a lowercase flow type name."""

    key = name.lower()

    def decorator(cls: Type[FlowBuilder]) -> Type[FlowBuilder]:
        if not issubclass(cls, FlowBuilder):
            raise TypeError(f"{cls.__name__} must subclass FlowBuilder")
        if key in _REGISTRY and _REGISTRY[key] is not cls:
            raise ValueError(f"Flow type {key!r} is already registered")
        cls.flow_type = key
        _REGISTRY[key] = cls
        return cls

    return decorator


def get_builder(name: str) -> Type[FlowBuilder]:
    key = name.lower()
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(f"Unknown flow type {name!r}. Available: {available}") from exc


def list_flows() -> List[str]:
    return sorted(_REGISTRY)
