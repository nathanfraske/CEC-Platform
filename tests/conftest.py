"""Keep native synthetic test cases from leaking KiCad's borrowed Default."""
from contextlib import contextmanager
from pathlib import Path
import importlib.util
import sys

# A fresh checkout must not need a machine-specific PYTHONPATH or source
# hidden inside ignored build output. The historical operators remain an
# explicitly separate test dependency, never the model control-plane API.
_ROOT=Path(__file__).resolve().parents[1]
for _directory in ('src','scripts','ops','tests','experiments/legacy_2026'):
    _entry=str(_ROOT/_directory)
    if _entry not in sys.path:sys.path.append(_entry)

import pytest


@contextmanager
def preserve_borrowed_default_scalars():
    # Hold every SWIG owner through restoration.  An unattached BOARD can
    # borrow a process-shared class; none of these are project rule changes.
    from cec_native_items import create_empty_board
    owner=create_empty_board()
    settings=owner.GetDesignSettings()
    net_settings=settings.m_NetSettings
    default=net_settings.GetDefaultNetclass()
    before=(default.GetTrackWidth(),default.GetClearance(),
        default.GetViaDiameter(),default.GetViaDrill())
    try:
        yield
    finally:
        default.SetTrackWidth(before[0]);default.SetClearance(before[1])
        default.SetViaDiameter(before[2]);default.SetViaDrill(before[3])


@pytest.fixture(autouse=True)
def isolate_native_default_scalars():
    """Restore the actual prior state after the WHOLE case, even on failure."""
    # Optional pure CadQuery lanes intentionally have no KiCad ABI loaded.
    # There is no borrowed native Default to restore in such an interpreter.
    # Native tests still import pcbnew themselves and cannot pass without it.
    if importlib.util.find_spec('pcbnew')is None:
        yield
        return
    with preserve_borrowed_default_scalars():
        yield
