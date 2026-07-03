#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Hub-enterprise shim over scripts/cec_sch_compose.py (the shared hierarchical
# schematic-composition engine, PROMOTED out of this file 2026-07-03 as the T4
# charter start -- see docs/schematic-quality-charter.md). Everything board-
# agnostic (build_leaf, build_thin_parent, the generic build_root/
# build_placeholder, the pwr_base #PWR/#FLG-block convention, the sheet-pin
# on-edge-AND-on-grid calibration, the addressing rules) lives THERE now,
# with all of its empirically-derived gotcha comments kept next to the code
# they protect. This file keeps only what is genuinely hub-specific: the
# root sheet's title block + sheet-map legend text and the placeholder
# sheets' SCHEMATIC-PLAN.md references.
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTDIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOTDIR, "scripts"))
import cec_sch  # noqa: E402,F401  (re-export convenience for gen_hub_enterprise)
import cec_sch_compose as _compose  # noqa: E402

# re-exports: the promoted engine, unchanged behavior
PAPER = _compose.PAPER
build_leaf = _compose.build_leaf
build_thin_parent = _compose.build_thin_parent


def build_root(hier_exports, project, root_uuid, sheet01_sym_uuid,
               placeholder_uuids, placeholder_titles, out_path, paper="A3"):
    """Hub-specific wrapper: the ENT hub root's title block + sheet-map legend
    around the generic cec_sch_compose.build_root.

    UNCHANGED by the 01a-01g leaf restructure: the root only ever sees ONE
    box named "01-power-input" exposing these 15 pins, regardless of whether
    that file is (as before) a flat capture sheet or (now) a thin parent that
    fans the same 15 signals out to seven leaf files of its own."""
    title_block_str = (
        '\t(title_block\n'
        '\t\t(title "CEC Hub -- Enterprise (ENT)")\n'
        '\t\t(date "2026-07-02")\n'
        '\t\t(rev "DRAFT")\n'
        '\t\t(company "CEC")\n'
        '\t\t(comment 1 "Hierarchical capture per hubs/hub-enterprise/SCHEMATIC-PLAN.md")\n'
        '\t\t(comment 2 "One schematic serves all ENT SKUs via the population/DNP matrix (REQ-105)")\n'
        '\t\t(comment 3 "DRAFT until every sheet passes the verification protocol -- see SCHEMATIC-PLAN.md sec 2")\n'
        '\t)'
    )
    legend_str = (
        '\t(text "Sheet map: 00=root 01=power-input(CAPTURED -- thin parent + 7 leaf sheets '
        '01a..01g, per functional block) 02=compute-core '
        '03=compute-rails 04=storage 05=module-ports 06=t1-dataplane 07=uplink '
        '08=secio-aux 09=watchdog(placeholders, capture pending) -- 10=voting-pair '
        '(MCX only, captured LAST per plan, not yet stubbed).\\n'
        'Population/DNP: per-SKU via BOM fields (fab DNP matrix), never schematic variants."\n'
        '\t\t(at 20 185 0)\n'
        '\t\t(effects (font (size 1.27 1.27)) (justify left top))\n'
        f'\t\t(uuid "{cec_sch.u()}")\n\t)'
    )
    return _compose.build_root(
        hier_exports, project, root_uuid, sheet01_sym_uuid,
        placeholder_uuids, placeholder_titles, out_path,
        title_block_str, legend_str,
        main_sheetname="01-power-input", main_sheetfile="01-power-input.kicad_sch",
        paper=paper)


def build_placeholder(num, sheet_sym_uuid, name, desc, project, page, out_path, paper="A4"):
    """Hub-specific wrapper: SCHEMATIC-PLAN.md capture-pending references."""
    return _compose.build_placeholder(
        num, sheet_sym_uuid, name, desc, project, page, out_path, paper=paper,
        comment1="CAPTURE PENDING -- see hubs/hub-enterprise/SCHEMATIC-PLAN.md sheet map",
        body_tail="See SCHEMATIC-PLAN.md sec 1 for BOM src + population.")
