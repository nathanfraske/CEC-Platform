"""Stable compatibility facade for the capability modules."""

from .identity import (
    inspection,
    require,
    digest,
    code_identity,
    family,
    evidence_summary,
    check_passed,
    GATES,
    INSTRUCTIONS,
)
from .geometry import path, polygon, alignment
from .native import native_world, visible_delta
from .construction import _construct
from .workbench import Workbench
from .protocol import TOOL_PARAMETERS, REQUIRED, DESCRIPTIONS, dispatch, serve
from .cli import main

__all__ = [name for name in globals() if not name.startswith("__")]
