#!/usr/bin/env python3
"""Authoritative current-BETA project manifest.

Only entries declared here are current products. Discovery code must not walk
``beta/`` recursively because archived projects and generated candidates can
otherwise be mistaken for released design inputs.
"""
from __future__ import annotations

import os


PROJECTS = (
    {
        "board": "12vhpwr-standard",
        "directory": "12vhpwr-standard",
        "project": "12vhpwr-standard-module",
        "schematic": "12vhpwr-standard-module.kicad_sch",
        "pcb": "12vhpwr-standard-module.kicad_pcb",
        "wave": True,
    },
    {
        "board": "argb-standard",
        "directory": "argb-standard",
        "project": "argb-standard-module",
        "schematic": "argb-standard-module.kicad_sch",
        "pcb": None,
        "wave": False,
    },
    {
        "board": "atx-24pin-rev3",
        "directory": "atx-24pin-rev3",
        "project": "24pin-module",
        "schematic": "24pin-module.kicad_sch",
        "pcb": "24pin-module.kicad_pcb",
        "wave": True,
    },
    {
        "board": "eps-8pin-rev3",
        "directory": "eps-8pin-rev3",
        "project": "eps-8pin-rev3",
        "schematic": "eps-8pin-rev3.kicad_sch",
        "pcb": "eps-8pin-rev3.kicad_pcb",
        "wave": True,
    },
    {
        "board": "hub-standard-rev2",
        "directory": "hub-standard-rev2",
        "project": "hub-standard-rev2",
        "schematic": "hub-standard-rev2.kicad_sch",
        # The candidate directory is the current beta placement authority.
        # Leaving this empty forced every canonical-pipeline invocation to
        # accept an arbitrary --input-board path, which allowed old probes to
        # masquerade as the current Hub board.
        "pcb": "candidate/hub-standard-rev2-candidate.kicad_pcb",
        "wave": True,
    },
    {
        "board": "pcie-8pin-2port",
        "directory": "pcie-8pin-2port",
        "project": "pcie8pin-2port-module",
        "schematic": "pcie8pin-2port-module.kicad_sch",
        # The root board predates the current hierarchical source.  The
        # schematic-derived candidate is the live placement authority; keeping
        # the old board here made canonical runs report C41-C45/D3/D4/F1 as
        # missing even after a successful current-source wave published them.
        "pcb": "candidate/pcie-8pin-2port-candidate.kicad_pcb",
        "wave": True,
    },
    {
        "board": "pcie-8pin-3port",
        "directory": "pcie-8pin-3port",
        "project": "pcie8pin-3port-module",
        "schematic": "pcie8pin-3port-module.kicad_sch",
        # The root PCB is an older 58-footprint flat-board artifact.  The
        # candidate carries the current hierarchical placement (and exposes
        # any remaining missing refs to intake instead of hiding them behind
        # the much older root board).
        "pcb": "candidate/pcie-8pin-3port-candidate.kicad_pcb",
        "wave": True,
    },
    {
        "board": "output-daughterboards/atx24-out-db",
        "directory": "output-daughterboards/atx24-out-db",
        "project": "atx24-out-db-board",
        "schematic": "atx24-out-db-board.kicad_sch",
        "pcb": "atx24-out-db-board.kicad_pcb",
        "wave": False,
    },
    {
        "board": "output-daughterboards/eps-out-db",
        "directory": "output-daughterboards/eps-out-db",
        "project": "eps-out-db-board",
        "schematic": "eps-out-db-board.kicad_sch",
        "pcb": "eps-out-db-board.kicad_pcb",
        "wave": False,
    },
    {
        "board": "output-daughterboards/pcie-out-db",
        "directory": "output-daughterboards/pcie-out-db",
        "project": "pcie-out-db-board",
        "schematic": "pcie-out-db-board.kicad_sch",
        "pcb": "pcie-out-db-board.kicad_pcb",
        "wave": False,
    },
)

CURRENT_BETA_BOARDS = tuple(p["board"] for p in PROJECTS)
WAVE_BOARDS = tuple(p["board"] for p in PROJECTS if p["wave"])
# Boards covered by the Standard main-board electrical review.  Keep this as
# executable manifest data so a prose review cannot silently omit a current
# product (the Hub omission that prompted this gate).
STANDARD_MAIN_BOARDS = (
    "atx-24pin-rev3",
    "eps-8pin-rev3",
    "pcie-8pin-2port",
    "pcie-8pin-3port",
    "12vhpwr-standard",
    "hub-standard-rev2",
)
BY_BOARD = {p["board"]: p for p in PROJECTS}


def project_paths(beta_root: str, boards=None):
    """Yield ``(board, directory, schematic)`` for declared current projects."""
    selected = set(CURRENT_BETA_BOARDS if boards is None else boards)
    unknown = selected - set(CURRENT_BETA_BOARDS)
    if unknown:
        raise ValueError(f"unknown current BETA board(s): {', '.join(sorted(unknown))}")
    for project in PROJECTS:
        if project["board"] not in selected:
            continue
        directory = os.path.join(beta_root, project["directory"])
        schematic = os.path.join(directory, project["schematic"])
        if not os.path.isfile(schematic):
            raise FileNotFoundError(
                f"current BETA manifest entry is missing: {schematic}"
            )
        yield project["board"], directory, schematic


def validate(root: str) -> list[str]:
    """Return manifest integrity errors without scanning historical folders."""
    errors = []
    beta_root = os.path.join(root, "beta")
    if len(BY_BOARD) != len(PROJECTS):
        errors.append("duplicate board key in current BETA manifest")
    if "eps-8pin" in BY_BOARD:
        errors.append("obsolete EPS product key is present; only eps-8pin-rev3 is current")
    if len(set(STANDARD_MAIN_BOARDS)) != len(STANDARD_MAIN_BOARDS):
        errors.append("duplicate board key in Standard main-board review scope")
    for board in STANDARD_MAIN_BOARDS:
        if board not in BY_BOARD:
            errors.append(f"Standard main-board review references unknown board: {board}")
    for project in PROJECTS:
        directory = os.path.join(beta_root, project["directory"])
        paths = {
            "project": os.path.join(directory, project["project"] + ".kicad_pro"),
            "schematic": os.path.join(directory, project["schematic"]),
        }
        if project["pcb"]:
            paths["pcb"] = os.path.join(directory, project["pcb"])
        for kind, path in paths.items():
            if not os.path.isfile(path):
                errors.append(f"missing {kind}: {os.path.relpath(path, root)}")
    return errors
