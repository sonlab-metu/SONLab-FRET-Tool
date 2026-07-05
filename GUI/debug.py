"""Lightweight debug-print gating for the SONLab FRET Tool.

All diagnostic ``print`` calls in the GUI modules go through :func:`dprint`, which
only writes to stdout when debug output is enabled. This keeps the terminal quiet
for normal use while preserving the traces for troubleshooting.

Enable debug output either by setting the environment variable before launch::

    SONLAB_DEBUG=1 python -m GUI

or at runtime via :func:`set_debug` (e.g. from a menu action).
"""
from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}

# Initial state comes from the environment so it can be turned on before the UI
# is built (useful for start-up issues).
_DEBUG = os.environ.get("SONLAB_DEBUG", "").strip().lower() in _TRUTHY


def is_debug() -> bool:
    """Return True when debug output is currently enabled."""
    return _DEBUG


def set_debug(enabled: bool) -> None:
    """Enable or disable debug output at runtime."""
    global _DEBUG
    _DEBUG = bool(enabled)


def dprint(*args, **kwargs) -> None:
    """``print`` that only emits when debug output is enabled."""
    if _DEBUG:
        print(*args, **kwargs)
