"""Load and merge WinFlow configuration from defaults, JSON, and environment."""

from __future__ import annotations

import json
import os
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import Any, Dict, Optional, TypeVar, get_args, get_origin, get_type_hints

from winflow_config.models import AppConfig

T = TypeVar("T")
_CONFIG: Optional[AppConfig] = None
_CONFIG_ENV = "WINFLOW_CONFIG"

_ENV_MAP = {
    "WINFLOW_RUNNER_DEFAULT_QUEUE": ("runner", "default_queue"),
    "WINFLOW_RUNNER_POLL_INTERVAL": ("runner", "poll_interval", int),
    "WINFLOW_RUNNER_DEFAULT_CPU": ("runner", "default_cpu", int),
    "WINFLOW_RUNNER_JOB_LOG_DIR": ("runner", "job_log_dir"),
    "WINFLOW_RUNNER_SESSION_LOG_DIR": ("runner", "session_log_dir"),
    "WINFLOW_GENERATOR_DEFAULT_QUEUE": ("generator", "default_queue"),
    "WINFLOW_GENERATOR_POLL_INTERVAL": ("generator", "poll_interval", int),
    "WINFLOW_GENERATOR_DEFAULT_CPU": ("generator", "default_cpu", int),
    "WINFLOW_PV_LAKER_DIR": ("pv", "paths", "laker_dir"),
    "WINFLOW_PV_GDS_DIR": ("pv", "paths", "gds_dir"),
    "WINFLOW_PV_FLOW_DIR": ("pv", "paths", "flow_dir"),
    "WINFLOW_PV_DATA_DIR": ("pv", "paths", "data_dir"),
    "WINFLOW_APR_DEFAULT_QUEUE": ("apr", "default_queue"),
    "WINFLOW_APR_DEFAULT_CPU": ("apr", "default_cpu"),
}


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_config_path() -> Path:
    env_path = os.environ.get(_CONFIG_ENV, "").strip()
    if env_path:
        return Path(env_path)
    return _project_root() / "config.json"


def _coerce(value: Any, target_type: type) -> Any:
    if target_type is bool and isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return target_type(value)


def _merge_value(current: Any, update: Any, field_type: Any = None) -> Any:
    if update is None:
        return current
    if is_dataclass(current):
        if not isinstance(update, dict):
            return current
        return merge_dataclass(current, update)
    origin = get_origin(field_type) if field_type is not None else get_origin(type(current))
    if origin is tuple and isinstance(update, list):
        inner_types = get_args(field_type) if field_type is not None else get_args(type(current))
        if inner_types and is_dataclass(inner_types[0]):
            item_type = inner_types[0]
            return tuple(
                item_type(**item) if isinstance(item, dict) else item
                for item in update
            )
        return tuple(update)
    return update


def merge_dataclass(instance: T, updates: Dict[str, Any]) -> T:
    type_hints = get_type_hints(type(instance))
    kwargs: Dict[str, Any] = {}
    for field_info in fields(instance):
        current = getattr(instance, field_info.name)
        if field_info.name not in updates:
            kwargs[field_info.name] = current
            continue
        kwargs[field_info.name] = _merge_value(
            current,
            updates[field_info.name],
            type_hints.get(field_info.name, field_info.type),
        )
    return replace(instance, **kwargs)


def _set_nested(config: AppConfig, path: tuple, value: Any) -> AppConfig:
    if len(path) == 2:
        section_name, field_name = path
        section = getattr(config, section_name)
        return replace(config, **{section_name: replace(section, **{field_name: value})})
    if len(path) == 3:
        section_name, nested_name, field_name = path
        section = getattr(config, section_name)
        nested = getattr(section, nested_name)
        updated_nested = replace(nested, **{field_name: value})
        return replace(config, **{section_name: replace(section, **{nested_name: updated_nested})})
    raise ValueError(f"Unsupported config path: {path}")


def _apply_env_overrides(config: AppConfig) -> AppConfig:
    current = config
    for env_name, mapping in _ENV_MAP.items():
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            continue
        if len(mapping) == 3:
            path, field_name, value_type = mapping[0], mapping[1], mapping[2]
            value = _coerce(raw, value_type)
            current = _set_nested(current, (path, field_name), value)
        else:
            section_name, field_name = mapping
            current = _set_nested(current, (section_name, field_name), raw)
    return current


def load_config(path: Optional[Path] = None) -> AppConfig:
    config = AppConfig()
    config_path = path or default_config_path()
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        if not isinstance(data, dict):
            raise ValueError(f"Config root must be an object: {config_path}")
        config = AppConfig.from_dict(data)
    return _apply_env_overrides(config)


def get_config(reload: bool = False, path: Optional[Path] = None) -> AppConfig:
    global _CONFIG
    if reload or _CONFIG is None:
        _CONFIG = load_config(path)
    return _CONFIG


def reset_config() -> None:
    global _CONFIG
    _CONFIG = None
