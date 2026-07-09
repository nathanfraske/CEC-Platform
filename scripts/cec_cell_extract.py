#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_cell_extract -- the HAND-CELL EXTRACTOR (A3 of
#  docs/actuation-space-2026-07-08.md; feeds P4 of docs/pass-form-plan.md)
# ============================================================================
# Lift a placed+routed functional cell off a shipped hand board into a
# reusable, parameterized BLUEPRINT TEMPLATE: relative placement (offset from
# an anchor part) + the cell's INTERNAL routing (copper whose net never
# touches a part outside the cell). Net names are stored as ROLES, not
# literals, so a template stamps onto any instance's nets -- the PCB-side
# analogue of scripts/cec_sch_archetypes.py (which does the same job for
# schematic blocks).
#
# WHAT COUNTS AS "INTERNAL": a net is internal to a cell iff EVERY pad on that
# net, board-wide, belongs to a ref in the cell. This is a real, useful
# distinction on the 12vhpwr lane cell measured below: the shunt's FORCE
# nets (/SENSEP{n}_HI, /SENSEP{n}_LO) also land on the board's J3/J4
# connectors, so they are BOUNDARY nets (ports) even though the shunt itself
# is in the cell; only the Kelvin/filter nets (/IN{n}_P, /IN{n}_N) that never
# leave RFHn/RFLn/CFn/INAn are internal. That is not a bug in the classifier
# -- it is exactly the shape a Kelvin sense chain should have: the sense
# chain is self-contained, the force path is external plumbing.
#
# pcbnew is container-only in this repo:
#   sg docker -c "docker compose -f docker/compose.yaml exec -T routing \
#       python3 scripts/cec_cell_extract.py ..."
#
# KiCad-10 footgun (see CLAUDE.md + cec_fr.py): PCB_VIA.GetWidth() with NO
# layer argument asserts (via width is per-layer now) -- always pass a layer,
# e.g. t.GetWidth(t.TopLayer()).
import math
import re

import pcbnew

MM = 1_000_000  # nm per mm


def _mm(nm):
    return nm / MM


def _nm(v):
    return int(round(v * MM))


def _rot(lx, ly, a_deg):
    """Rotate a LOCAL (lx,ly) by a_deg, KiCad's footprint convention (y-down
    screen space) -- the same convention as cec_pcb._rot, duplicated here so
    this module has no import-time dependency on the gen-module-pcb chain."""
    a = math.radians(a_deg)
    return (lx * math.cos(a) + ly * math.sin(a), -lx * math.sin(a) + ly * math.cos(a))


def _to_local(gx, gy, ax, ay, a_rot):
    """Global point -> the anchor's local frame (inverse-rotate, then it's
    already translated since we subtract the anchor first)."""
    return _rot(gx - ax, gy - ay, -a_rot)


def _to_global(lx, ly, ax, ay, a_rot):
    dx, dy = _rot(lx, ly, a_rot)
    return (ax + dx, ay + dy)


def _norm_deg(a):
    a = a % 360.0
    return a + 360.0 if a < 0 else a


# A net-name's instance index is captured as everywhere-digits -> '{n}'. Every
# net family actually on the boards this module has been run against
# (/SENSEP{n}_HI, /IN{n}_P, /ISENSEP{n}, ...) carries exactly ONE digit run,
# so a blanket digit-run substitution is safe there; a net with more than one
# digit run (not seen on these boards) would collapse them all to the same
# '{n}' -- this is a DOCUMENTED LIMITATION, not a silent assumption: check
# template["net_roles"] before trusting a role on an unfamiliar family.
_DIGIT_RUN = re.compile(r"\d+")


def net_role(name):
    """'/SENSEP4_HI' -> '/SENSEP{n}_HI'; 'GND' -> 'GND' (no digits = a fixed,
    non-parameterized port, e.g. GND/+3V3/rail nets shared board-wide)."""
    return _DIGIT_RUN.sub("{n}", name)


class BoardIndex:
    """Cheap read-only index over a pcbnew LoadBoard(): ref -> footprint and
    net-name -> {every ref with a pad on that net, board-wide}. Built once
    (LoadBoard is the expensive part) and reusable across many extract() /
    measurement calls against the same board."""

    def __init__(self, board_path):
        self.path = board_path
        self.board = pcbnew.LoadBoard(board_path)
        self.fps = {fp.GetReference(): fp for fp in self.board.GetFootprints()}
        mem = {}
        for fp in self.board.GetFootprints():
            ref = fp.GetReference()
            for p in fp.Pads():
                n = p.GetNetname()
                if n:
                    mem.setdefault(n, set()).add(ref)
        self.net_members = mem

    def fp(self, ref):
        if ref not in self.fps:
            raise KeyError(f"ref {ref!r} not found on board {self.path}")
        return self.fps[ref]

    def pos_mm(self, ref):
        p = self.fp(ref).GetPosition()
        return (_mm(p.x), _mm(p.y))

    def rot_deg(self, ref):
        return self.fp(ref).GetOrientationDegrees()

    def flipped(self, ref):
        return self.fp(ref).IsFlipped()


def extract(board_path, refs, *, anchor_ref, index=None):
    """Lift `refs` off `board_path` into a JSON-able template dict, anchored
    to `anchor_ref`'s own position/rotation/flip state. READ-ONLY: this
    function only calls pcbnew.LoadBoard() (via BoardIndex) and never Save()s
    -- the board file on disk is untouched, byte-for-byte, by any call here.

    `index`: an already-built BoardIndex for board_path, to avoid a re-parse
    when extracting many cells off the same board (see measure_lanes below).

    Returns:
      {
        "anchor": {ref, footprint, value, flipped},
        "parts": {ref: {offset_mm, rot_delta, flipped, footprint, value}},
        "internal_tracks": [{net_role, layer, start_rel_mm, end_rel_mm, width_mm}],
        "vias": [{net_role, at_rel_mm, drill_mm, dia_mm, layers}],
        "ports": {net_role: {"net": literal, "pads": [{ref, pad, rel_mm}]}},
        "net_roles": {net_role: literal_net_name},   # every net the cell touches
        "meta": {source_board, anchor_ref, anchor_pos_mm, anchor_rot_deg, refs},
      }

    `offset_mm` / `*_rel_mm` are all expressed in the ANCHOR's own local frame
    (rotated out by -anchor_rot), so stamp() can re-place the whole cell at a
    differently-ROTATED destination anchor by the same transform used for the
    anchor position, not just a translation.
    """
    if anchor_ref not in refs:
        raise ValueError(f"anchor_ref {anchor_ref!r} must be one of refs {refs!r}")
    bi = index or BoardIndex(board_path)
    board = bi.board
    refset = set(refs)

    ax, ay = bi.pos_mm(anchor_ref)
    a_rot = bi.rot_deg(anchor_ref)
    a_flip = bi.flipped(anchor_ref)

    parts = {}
    for ref in refs:
        fp = bi.fp(ref)
        x, y = bi.pos_mm(ref)
        lx, ly = _to_local(x, y, ax, ay, a_rot)
        parts[ref] = {
            "offset_mm": [round(lx, 6), round(ly, 6)],
            "rot_delta": round(_norm_deg(bi.rot_deg(ref) - a_rot), 6),
            "flipped": bool(fp.IsFlipped() != a_flip),
            "footprint": fp.GetFPIDAsString(),
            "value": fp.GetValue(),
        }

    # ---- classify every net the cell touches: internal (subset of refset)
    # vs. boundary (a port -- some pad on the net lives outside the cell).
    cell_nets = set()
    for ref in refs:
        for p in bi.fp(ref).Pads():
            n = p.GetNetname()
            if n:
                cell_nets.add(n)

    internal_nets, boundary_nets = set(), set()
    for n in cell_nets:
        members = bi.net_members.get(n, set())
        (internal_nets if members <= refset else boundary_nets).add(n)

    net_roles = {net_role(n): n for n in cell_nets}

    ports = {}
    for ref in refs:
        for p in bi.fp(ref).Pads():
            n = p.GetNetname()
            if n not in boundary_nets:
                continue
            pos = p.GetPosition()
            lx, ly = _to_local(_mm(pos.x), _mm(pos.y), ax, ay, a_rot)
            role = net_role(n)
            ports.setdefault(role, {"net": n, "pads": []})["pads"].append(
                {"ref": ref, "pad": p.GetNumber(), "rel_mm": [round(lx, 6), round(ly, 6)]}
            )

    # ---- internal copper: any track/arc/via whose net is internal to the cell.
    internal_tracks = []
    vias = []
    for t in board.GetTracks():
        n = t.GetNetname()
        if n not in internal_nets:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            lx, ly = _to_local(_mm(p.x), _mm(p.y), ax, ay, a_rot)
            vias.append(
                {
                    "net_role": net_role(n),
                    "at_rel_mm": [round(lx, 6), round(ly, 6)],
                    "drill_mm": round(_mm(t.GetDrillValue()), 6),
                    # KiCad-10 footgun: PCB_VIA.GetWidth() with no layer asserts.
                    "dia_mm": round(_mm(t.GetWidth(t.TopLayer())), 6),
                    "layers": [board.GetLayerName(t.TopLayer()), board.GetLayerName(t.BottomLayer())],
                }
            )
        else:  # PCB_TRACE_T or PCB_ARC_T -- arcs captured by endpoints only (documented limit, no mid/radius)
            s, e = t.GetStart(), t.GetEnd()
            slx, sly = _to_local(_mm(s.x), _mm(s.y), ax, ay, a_rot)
            elx, ely = _to_local(_mm(e.x), _mm(e.y), ax, ay, a_rot)
            internal_tracks.append(
                {
                    "net_role": net_role(n),
                    "layer": board.GetLayerName(t.GetLayer()),
                    "start_rel_mm": [round(slx, 6), round(sly, 6)],
                    "end_rel_mm": [round(elx, 6), round(ely, 6)],
                    "width_mm": round(_mm(t.GetWidth()), 6),
                }
            )

    return {
        "anchor": {
            "ref": anchor_ref,
            "footprint": bi.fp(anchor_ref).GetFPIDAsString(),
            "value": bi.fp(anchor_ref).GetValue(),
            "flipped": a_flip,
        },
        "parts": parts,
        "internal_tracks": internal_tracks,
        "vias": vias,
        "ports": ports,
        "net_roles": net_roles,
        "meta": {
            "source_board": board_path,
            "anchor_ref": anchor_ref,
            "anchor_pos_mm": [round(ax, 6), round(ay, 6)],
            "anchor_rot_deg": round(a_rot, 6),
            "refs": list(refs),
        },
    }


def net_map_for_index(template, index):
    """Convenience net_map builder for the common case: a role with EXACTLY
    ONE '{n}' placeholder gets it filled with `index`; a role with ZERO or
    2+ placeholders keeps its recorded literal instead.

    Zero placeholders is the obvious fixed case (GND). TWO OR MORE is a real
    trap net_role()'s blanket digit-run substitution can produce and this
    guards against: '+3V3' has TWO digit runs ('3' and '3'), so net_role()
    returns '+{n}V{n}' -- naively filling BOTH placeholders with a lane index
    produces '+5V5' for lane 5, which does not exist on any board (a fixed
    rail is not lane-indexed at all; its digits are just its own name). This
    was caught for real by this module's own round-trip teeth
    (build/teeth_cell_extract.py) before being fixed here -- exactly the
    failure mode net_role()'s docstring warns a multi-digit-run net name
    would hit. A role is trusted as genuinely lane-indexed only when it
    carries a single '{n}'; everything else is passed through unindexed."""
    out = {}
    for role, literal in template["net_roles"].items():
        out[role] = role.format(n=index) if role.count("{n}") == 1 else literal
    return out


def stamp(template, board=None, *, at_mm, rot=0.0, ref_map, net_map=None, lay_tracks=False, apply=False):
    """Affine-place `template` at a new anchor (at_mm, rot), remapping refs
    via `ref_map` (template ref -> destination ref) and net roles via
    `net_map` (role -> destination literal net name; any role NOT given falls
    back to the template's own extraction-time literal, which reproduces the
    ORIGINAL instance's net name -- correct only when re-stamping onto the
    same instance's own position, wrong across instances. Cross-instance
    callers should build net_map with net_map_for_index() or their own map).

    Returns (placement, copper):
      placement: {dest_ref: (x_mm, y_mm, rot_deg, flipped)}
      copper: {} unless lay_tracks=True, in which case
        {"tracks": [...], "vias": [...]} with roles resolved to net names and
        coordinates affine-transformed into the destination frame -- v1
        RETURNS DATA ONLY (no board mutation, no routing-engine call); a
        later routing pass lays it.

    Placement stamping is solid (this is the primitive P4 needs today);
    copper stamping is deliberately left as returned data, per the A3 spec,
    until a routing pass consumes it.

    apply=True additionally WRITES the placement onto `board` (a loaded
    pcbnew board; footprints looked up via ref_map's destination refs) --
    opt-in actuation. Default (apply=False) never mutates `board` and never
    calls Save(); this keeps stamp() safe to call for a pure measurement
    (e.g. the round-trip teeth below) without touching any file on disk.
    Does not touch a footprint's F/B (Flipped) side -- flipping a footprint
    is a layer-change operation elsewhere in this repo's convention
    (CLAUDE.md "Rotate, don't flip"), not a coordinate edit stamp() should
    make unasked."""
    ax, ay = at_mm
    net_map = net_map or {}
    placement = {}
    for tref, spec in template["parts"].items():
        dref = ref_map.get(tref, tref)
        lx, ly = spec["offset_mm"]
        gx, gy = _to_global(lx, ly, ax, ay, rot)
        g_rot = _norm_deg(rot + spec["rot_delta"])
        placement[dref] = (round(gx, 6), round(gy, 6), round(g_rot, 6), bool(spec["flipped"]))

    copper = {}
    if lay_tracks:
        def resolve_net(role):
            return net_map[role] if role in net_map else template["net_roles"].get(role, role)

        tracks = []
        for tr in template["internal_tracks"]:
            slx, sly = tr["start_rel_mm"]
            elx, ely = tr["end_rel_mm"]
            sgx, sgy = _to_global(slx, sly, ax, ay, rot)
            egx, egy = _to_global(elx, ely, ax, ay, rot)
            tracks.append(
                {
                    "net": resolve_net(tr["net_role"]),
                    "layer": tr["layer"],
                    "start_mm": [round(sgx, 6), round(sgy, 6)],
                    "end_mm": [round(egx, 6), round(egy, 6)],
                    "width_mm": tr["width_mm"],
                }
            )
        v_out = []
        for v in template["vias"]:
            lx, ly = v["at_rel_mm"]
            gx, gy = _to_global(lx, ly, ax, ay, rot)
            v_out.append(
                {
                    "net": resolve_net(v["net_role"]),
                    "at_mm": [round(gx, 6), round(gy, 6)],
                    "drill_mm": v["drill_mm"],
                    "dia_mm": v["dia_mm"],
                    "layers": v["layers"],
                }
            )
        copper = {"tracks": tracks, "vias": v_out}

    if apply:
        if board is None:
            raise ValueError("apply=True requires a loaded pcbnew board")
        for dref, (x, y, r, _fl) in placement.items():
            fp = board.FindFootprintByReference(dref)
            if fp is None:
                raise KeyError(f"apply: dest ref {dref!r} not found on board")
            fp.SetPosition(pcbnew.VECTOR2I(_nm(x), _nm(y)))
            fp.SetOrientationDegrees(r)

    return placement, copper
