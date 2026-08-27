"""Regression teeth for structural six-layer migration."""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_migrate_6layer as migrate  # noqa: E402


def test_profile_properties_are_inserted_at_board_root_not_first_footprint():
    text = """(kicad_pcb
\t(footprint "X"
\t\t(property "Reference" "R1")
\t(embedded_fonts no)
\t)
\t(embedded_fonts no)
)
"""
    migrated = migrate._set_properties(
        text, "jlcpcb_6l_pofv_high_current")
    root_marker = migrated.rfind("\n\t(embedded_fonts no)")
    footprint_close = migrated.find("\n\t)\n")
    for key in ("CEC_FAB_PROFILE", "CEC_VENDOR_STACKUP",
                "CEC_STACKUP_ROLES", "CEC_VIA_PROTECTION"):
        position = migrated.index('(property "%s"' % key)
        assert footprint_close < position < root_marker


def test_current_eps_migration_validates_without_writing_source():
    path = os.path.join(
        ROOT, "beta", "eps-8pin-rev3", "eps-8pin-rev3.kicad_pcb")
    before = os.stat(path).st_mtime_ns
    result = migrate.migrate_board(path, write=False)
    assert result["profile"] == "jlcpcb_6l_pofv_high_current"
    assert not result["written"]
    assert os.stat(path).st_mtime_ns == before
