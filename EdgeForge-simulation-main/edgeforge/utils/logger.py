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

import sys
from typing import Optional

from loguru import logger as _loguru_logger

_CONFIGURED: bool = False


def _configure_defaults() -> None:
    """Configure Loguru once with a readable, beginner-friendly format."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    # Remove the default handler so we can install our own with consistent formatting.
    _loguru_logger.remove()

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
        # Loguru's `bind` tags the log record with extra context; we surface
        # the name through a helper logger-like wrapper.  For simplicity we
        # just use the base logger and rely on its ``name`` capture from the
        # stack trace; for explicit naming we patch `name` via opt() below.
        return _loguru_logger.bind(module=name)
    return _loguru_logger
