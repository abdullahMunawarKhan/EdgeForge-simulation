"""
Simple Loguru-powered logging utility for EdgeForge.

Usage example
-------------
    from edgeforge.utils.logger import get_logger

    logger = get_logger(__name__)
    logger.info("EdgeForge started")
    logger.warning("Low confidence detection")
    logger.error("CARLA connection failed")
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import List, Optional

from loguru import logger as _loguru_logger

_CONFIGURED: bool = False
_FILE_SINK_IDS: List[int] = []


def _configure_defaults() -> None:
    """Configure Loguru once with a readable, beginner-friendly format."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    # Remove the default handler so we can install our own with consistent formatting.
    _loguru_logger.remove()

    # Ensure stdout supports UTF-8 on Windows consoles to avoid charmap UnicodeEncodeErrors
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    _loguru_logger.add(
        sys.stdout,
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        level="INFO",
    )

    _CONFIGURED = True


def get_logger(name: Optional[str] = None) -> _loguru_logger.__class__:
    """Return a configured Loguru logger instance.

    Parameters
    ----------
    name :
        Optional name used to identify the caller in log lines.
        Typically pass ``__name__`` so log lines show which module emitted them.

    Returns
    -------
    A configured Loguru logger instance.
    """
    _configure_defaults()
    if name:
        return _loguru_logger.bind(module=name)
    return _loguru_logger


# ----------------------------------------------------------------------
# NEW: file sinks (a "sink" is just a destination for log lines)
# ----------------------------------------------------------------------
def _jsonl_sink(path: str):
    """Return a sink that appends one JSON object per line (JSONL)."""

    def _write(message) -> None:
        record = message.record
        entry = {
            "ts": record["time"].timestamp(),
            "level": record["level"].name,
            "module": record["extra"].get("module", record["name"]),
            "message": record["message"],
        }
        data = record["extra"].get("data")
        if data:
            entry["data"] = data
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    return _write


def setup_file_sinks(log_dir: str, rotation: str = "1 MB", retention: int = 3) -> None:
    """Add a rotating text log and a JSONL log inside ``log_dir``.

    Safe to call twice: the second call does nothing.
    rotation  = start a new file when the current one reaches this size.
    retention = how many old files to keep.
    """
    _configure_defaults()  # must come first, see note above the code
    if _FILE_SINK_IDS:
        return
    os.makedirs(log_dir, exist_ok=True)
    _FILE_SINK_IDS.append(
        _loguru_logger.add(
            os.path.join(log_dir, "edgeforge.log"),
            rotation=rotation,
            retention=retention,
            level="DEBUG",
            encoding="utf-8",
        )
    )
    _FILE_SINK_IDS.append(
        _loguru_logger.add(_jsonl_sink(os.path.join(log_dir, "edgeforge.jsonl")), level="DEBUG")
    )


def remove_file_sinks() -> None:
    """Remove the file sinks again (mainly useful in tests)."""
    while _FILE_SINK_IDS:
        _loguru_logger.remove(_FILE_SINK_IDS.pop())


# ----------------------------------------------------------------------
# NEW: helpers that turn event / risk objects into plain dictionaries.
# They read fields BY NAME and never import data/models.py.
# ----------------------------------------------------------------------
def _plain(value):
    """Convert Enums, dataclasses, pydantic models and numpy values to JSON-friendly types."""
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):          # pydantic model
        return _plain(value.model_dump())
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "tolist"):              # numpy
        return value.tolist()
    return value


def event_to_log_dict(event) -> dict:
    """ScenarioEvent -> plain dict. Missing fields get safe defaults."""
    if event is None:
        return {"kind": "scenario_event", "error": "no event"}
    return {
        "kind": "scenario_event",
        "type": _plain(getattr(event, "type", "unknown")),
        "severity": _plain(getattr(event, "severity", "unknown")),
        "timestamp": getattr(event, "timestamp", None),
        "message": getattr(event, "message", ""),
    }


def risk_to_log_dict(risk, tick: Optional[int] = None) -> dict:
    """RiskAssessment -> plain dict. Missing fields get safe defaults."""
    if risk is None:
        return {"kind": "risk_assessment", "tick": tick, "error": "no risk"}
    return {
        "kind": "risk_assessment",
        "tick": tick,
        "score": getattr(risk, "score", None),
        "level": _plain(getattr(risk, "level", "unknown")),
        "reason": getattr(risk, "reason", ""),
        "top_objects": _plain(getattr(risk, "top_objects", [])),
    }