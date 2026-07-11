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


def _clip_seg(x1, y1, x2, y2, win):
    """Liang-Barsky segment clip to the (x0, x1, y0, y1) window; None if fully out."""
    wx0, wx1, wy0, wy1 = win
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - wx0), (dx, wx1 - x1), (-dy, y1 - wy0), (dy, wy1 - y1)):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            t0 = max(t0, r)
        else:
            if r < t0:
                return None
            t1 = min(t1, r)
    return ((x1 + t0 * dx, y1 + t0 * dy), (x1 + t1 * dx, y1 + t1 * dy))


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
        "standins": [{net_role, kind: track|zone|via, layer(s), geometry}],
                                                     # boundary-net FORCE copper in the
                                                     # cell window (lane tracks / pours);
                                                     # obstacles + emit context, never moved
        "port_tracks": [{net_role, layer, start_rel_mm, end_rel_mm, width_mm}],
                                                     # the cell's own THIN copper on port
                                                     # nets (hand Kelvin taps, supply links)
        "internal_pads": {net_role: {"net": literal, "pads": [{ref, pad, rel_mm}]}},
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
    internal_pads = {}                     # net_role -> {"net": literal, "pads": [...]} for INTERNAL nets
    for ref in refs:
        for p in bi.fp(ref).Pads():
            n = p.GetNetname()
            if not n or (n not in boundary_nets and n not in internal_nets):
                continue
            pos = p.GetPosition()
            lx, ly = _to_local(_mm(pos.x), _mm(pos.y), ax, ay, a_rot)
            role = net_role(n)
            bucket = ports if n in boundary_nets else internal_pads
            bucket.setdefault(role, {"net": n, "pads": []})["pads"].append(
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

    # ---- boundary-net copper STAND-INS (owner ask 2026-07-10: "if it incorporates
    # a pour, it should add standins for the pour so it can route it properly").
    # The FORCE copper serving the cell's port nets -- pours (zones) on eps/pcie
    # cells, the 2.5mm lane TRACKS on the 12vhpwr cells -- inside the cell window
    # (parts bbox + margin), anchor-local. GND is skipped (plane-served on every
    # CEC board; a clipped GND-plane AABB would just be the whole window). Zones
    # are captured as the AABB of (zone bbox INTERSECT window) per copper layer --
    # a documented v1 simplification, exact for the rectangular lane/pour shapes
    # these boards actually carry.
    STANDIN_TRACK_MIN_W = 0.5                       # mm; >= this = force copper, not signal
    margin = 2.0
    wxs, wys = [], []
    for ref in refs:
        bb = bi.fp(ref).GetBoundingBox()
        wxs += [_mm(bb.GetLeft()), _mm(bb.GetRight())]
        wys += [_mm(bb.GetTop()), _mm(bb.GetBottom())]
    win = (min(wxs) - margin, max(wxs) + margin, min(wys) - margin, max(wys) + margin)

    def _loc(gx, gy):
        return _to_local(gx, gy, ax, ay, a_rot)

    def _loc_box(x0, x1, y0, y1):
        pts = [_loc(x0, y0), _loc(x1, y0), _loc(x1, y1), _loc(x0, y1)]
        return [round(min(p[0] for p in pts), 6), round(max(p[0] for p in pts), 6),
                round(min(p[1] for p in pts), 6), round(max(p[1] for p in pts), 6)]

    standins = []
    port_tracks = []                              # the cell's own thin copper on port nets
    for t in board.GetTracks():
        n = t.GetNetname()
        if n not in boundary_nets or n == "GND":
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            gx, gy = _mm(p.x), _mm(p.y)
            if not (win[0] <= gx <= win[1] and win[2] <= gy <= win[3]):
                continue
            lx, ly = _loc(gx, gy)
            standins.append({"net_role": net_role(n), "kind": "via",
                             "at_rel_mm": [round(lx, 6), round(ly, 6)],
                             "dia_mm": round(_mm(t.GetWidth(t.TopLayer())), 6),
                             "drill_mm": round(_mm(t.GetDrillValue()), 6),
                             "layers": [board.GetLayerName(t.TopLayer()),
                                        board.GetLayerName(t.BottomLayer())]})
            continue
        w = _mm(t.GetWidth())
        s, e = t.GetStart(), t.GetEnd()
        sx, sy, ex, ey = _mm(s.x), _mm(s.y), _mm(e.x), _mm(e.y)
        # keep if the segment's bbox touches the window (clip left to the model)
        if max(sx, ex) < win[0] or min(sx, ex) > win[1] or \
           max(sy, ey) < win[2] or min(sy, ey) > win[3]:
            continue
        slx, sly = _loc(sx, sy)
        elx, ely = _loc(ex, ey)
        rec = {"net_role": net_role(n), "kind": "track",
               "layer": board.GetLayerName(t.GetLayer()),
               "start_rel_mm": [round(slx, 6), round(sly, 6)],
               "end_rel_mm": [round(elx, 6), round(ely, 6)],
               "width_mm": round(w, 6)}
        if w >= STANDIN_TRACK_MIN_W:
            standins.append(rec)                  # force copper: fixed context
        else:
            # the cell's own SIGNAL copper on a boundary net -- the hand Kelvin
            # taps / supply links live here (a boundary net's thin tracks were
            # previously captured NOWHERE, so the hand baseline under-reported
            # its tap copper as 0 -- measured 2026-07-10). CLIPPED to the window
            # (Liang-Barsky): a board trunk passing through must not inflate the
            # cell's own extents/copper.
            cl = _clip_seg(sx, sy, ex, ey, win)
            if cl is None:
                continue
            (csx, csy), (cex, cey) = cl
            slx, sly = _loc(csx, csy)
            elx, ely = _loc(cex, cey)
            rec.pop("kind")
            rec["start_rel_mm"] = [round(slx, 6), round(sly, 6)]
            rec["end_rel_mm"] = [round(elx, 6), round(ely, 6)]
            port_tracks.append(rec)
    for z in board.Zones():
        n = z.GetNetname()
        if n not in boundary_nets or n == "GND":
            continue
        bb = z.GetBoundingBox()
        zx0, zx1 = _mm(bb.GetLeft()), _mm(bb.GetRight())
        zy0, zy1 = _mm(bb.GetTop()), _mm(bb.GetBottom())
        ix0, ix1 = max(zx0, win[0]), min(zx1, win[1])
        iy0, iy1 = max(zy0, win[2]), min(zy1, win[3])
        if ix0 >= ix1 or iy0 >= iy1:
            continue
        for lid in z.GetLayerSet().Seq():
            lname = board.GetLayerName(lid)
            if not (lname.endswith(".Cu") or lname.startswith(("In", "GND"))):
                continue
            standins.append({"net_role": net_role(n), "kind": "zone", "layer": lname,
                             "box_rel_mm": _loc_box(ix0, ix1, iy0, iy1)})

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
        "standins": standins,
        "port_tracks": port_tracks,
        # INTERNAL-net pad footprints (anchor-local, same frame as internal_tracks). A cell whose
        # source was never routed carries internal_tracks==[] but STILL records the internal pad
        # geometry here, so synthesize_ideal_internal() can compile the owner's "super-tight ideal"
        # internal route at stamp time (docs/pass-form-plan.md §4 P4 OWNER ADDITION, 2026-07-08).
        "internal_pads": internal_pads,
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


def stamp(template, board=None, *, at_mm, rot=0.0, ref_map, net_map=None,
          lay_tracks=False, lay=False, apply=False, clearance_mm=None):
    """Affine-place `template` at a new anchor (at_mm, rot), remapping refs
    via `ref_map` (template ref -> destination ref) and net roles via
    `net_map` (role -> destination literal net name; any role NOT given falls
    back to the template's own extraction-time literal, which reproduces the
    ORIGINAL instance's net name -- correct only when re-stamping onto the
    same instance's own position, wrong across instances. Cross-instance
    callers should build net_map with net_map_for_index() or their own map).

    Returns (placement, copper):
      placement: {dest_ref: (x_mm, y_mm, rot_deg, flipped)}
      copper: {} unless lay_tracks/lay, in which case
        {"tracks": [...], "vias": [...]} with roles resolved to net names and
        coordinates affine-transformed into the destination frame. With lay=True
        it ALSO carries copper["laid"] -- the actuation report (below).

    lay_tracks=True         -> compute + RETURN the transformed copper as DATA ONLY
                               (no board mutation); the historical A3 behaviour.
    lay=True (P4, S3)       -> ACTUATE: write the transformed INTERNAL copper onto
                               `board` (a loaded pcbnew board) as real LOCKED tracks
                               + vias (SetLocked(True) on every laid segment), net
                               codes resolved through net_map -> the destination
                               board's own nets. GUARD-CHECKED FIRST (the exact-
                               geometry guard discipline, GetEffectiveShape().Collide
                               at clearance): if ANY segment would collide FOREIGN
                               copper (a net not in the cell's own laid set), the
                               WHOLE CELL's copper is REFUSED with a named reason and
                               NOTHING is laid -- a shorting stub is never laid. Ports
                               lay nothing (only internal copper is the cell's own).
                               The placement still stamps when apply=True (a refused
                               cell keeps its placement; only its internal copper is
                               withheld -- the snag re-surfaces to the seat/route pass).
                               `clearance_mm` overrides the board's min clearance.

    apply=True writes the PLACEMENT onto `board` (footprints looked up via ref_map's
    destination refs). Default (apply=False) never moves a footprint; combine
    apply=True + lay=True for a full rigid stamp (place the cell + lay its internal
    copper LOCKED). apply/lay never touch a footprint's F/B side (CLAUDE.md
    "Rotate, don't flip") -- flip is a layer-change decision, not a coordinate edit.
    Both are no-ops on a pure measurement call (board=None, apply=lay=False)."""
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
    if lay_tracks or lay:
        def resolve_net(role):
            return net_map[role] if role in net_map else template["net_roles"].get(role, role)

        tracks = []
        for tr in template.get("internal_tracks", []):
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
        for v in template.get("vias", []):
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

    if lay:
        if board is None:
            raise ValueError("lay=True requires a loaded pcbnew board")
        copper["laid"] = _lay_locked_copper(board, copper, clearance_mm=clearance_mm)

    return placement, copper


# =====================================================================================
#  ACTUATION (P4, docs/pass-form-plan.md stage S3): lay a stamped cell's INTERNAL copper
#  as real LOCKED tracks/vias, guard-checked against foreign copper (whole-cell refusal).
# =====================================================================================
def _foreign_clear(board, shape, layer_id, foreign_codes, clr_nm):
    """True iff `shape` (a SHAPE_SEGMENT/SHAPE_CIRCLE) has NO copper whose net code is in
    `foreign_codes` within clr_nm on layer_id. The exact GetEffectiveShape().Collide()
    geometry DRC uses (reused from cec_fr._tap_foreign_clear discipline), so a PASS here is
    DRC-clean for copper clearance -- the guard that lets a cell REFUSE rather than short."""
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() not in foreign_codes:
                continue
            if layer_id not in p.GetLayerSet().CuStack():
                continue
            try:
                if p.GetEffectiveShape(layer_id).Collide(shape, clr_nm):
                    return False
            except Exception:                       # noqa: BLE001 -- a weird shape never breaks the guard
                continue
    for t in board.GetTracks():
        if t.GetNetCode() not in foreign_codes:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            if layer_id not in t.GetLayerSet().CuStack():
                continue
        elif t.GetLayer() != layer_id:
            continue
        try:
            if t.GetEffectiveShape(layer_id).Collide(shape, clr_nm):
                return False
        except Exception:                           # noqa: BLE001
            continue
    return True


def _lay_locked_copper(board, copper, *, clearance_mm=None):
    """Lay `copper` ({"tracks":[...], "vias":[...]}) onto `board` as LOCKED segments, GUARDED
    as a WHOLE CELL: resolve every net, build the pcbnew objects in memory, test EACH against
    FOREIGN-net copper (any net not in the cell's own laid set) at the board clearance -- and
    if ANY collides, REFUSE the whole cell (add nothing, name the reason). Returns a report:
      {"laid_tracks": n, "laid_vias": n, "refused": bool, "reason": str|None,
       "nets": [laid net names]}.
    Same-net copper never counts as foreign (a cell's own filter chain is legitimately dense),
    exactly mirroring cec_fr's tap guard: adjacency within the cell is allowed, foreign shorts
    are refused."""
    tracks = copper.get("tracks", []) or []
    vias = copper.get("vias", []) or []
    report = {"laid_tracks": 0, "laid_vias": 0, "refused": False, "reason": None, "nets": []}
    if not tracks and not vias:
        return report

    if clearance_mm is not None:
        clr_nm = _nm(clearance_mm)
    else:
        try:                                        # board default-netclass clearance (KiCad-10 API varies)
            clr_nm = max(board.GetDesignSettings().GetDefault().GetClearance(), _nm(0.1))
        except Exception:                           # noqa: BLE001
            clr_nm = _nm(0.2)

    # resolve nets; a net missing on the destination board = a HARD refuse (named).
    def netcode(name):
        nc = board.GetNetcodeFromNetname(name)
        return nc

    cell_codes = set()
    resolved_tracks, resolved_vias = [], []
    for tr in tracks:
        nc = netcode(tr["net"])
        if nc < 0 or (nc == 0 and tr["net"] not in ("", "GND")):
            report.update(refused=True,
                          reason=f"net {tr['net']!r} not on destination board -- cell copper refused")
            return report
        cell_codes.add(nc)
        resolved_tracks.append((tr, nc))
    for v in vias:
        nc = netcode(v["net"])
        if nc < 0:
            report.update(refused=True,
                          reason=f"net {v['net']!r} not on destination board -- cell copper refused")
            return report
        cell_codes.add(nc)
        resolved_vias.append((v, nc))

    all_codes = {n.GetNetCode() for n in board.GetNetInfo().NetsByNetcode().values()}
    foreign_codes = all_codes - cell_codes

    # BUILD in memory (not yet added) + GUARD every segment against foreign copper.
    built = []
    for tr, nc in resolved_tracks:
        ly = board.GetLayerID(tr["layer"])
        if ly < 0:
            report.update(refused=True, reason=f"layer {tr['layer']!r} not on board -- cell copper refused")
            return report
        (sx, sy), (ex, ey) = tr["start_mm"], tr["end_mm"]
        S = pcbnew.VECTOR2I(_nm(sx), _nm(sy))
        E = pcbnew.VECTOR2I(_nm(ex), _nm(ey))
        w = _nm(tr["width_mm"])
        seg = pcbnew.SHAPE_SEGMENT(S, E, w)
        if not _foreign_clear(board, seg, ly, foreign_codes, clr_nm):
            report.update(refused=True,
                          reason=f"track on net {tr['net']!r} ({tr['layer']}) collides FOREIGN "
                                 f"copper at clearance -- whole cell refused")
            return report
        built.append(("track", tr, nc, ly, S, E, w))
    for v, nc in resolved_vias:
        top = board.GetLayerID(v["layers"][0]); bot = board.GetLayerID(v["layers"][-1])
        at = pcbnew.VECTOR2I(_nm(v["at_mm"][0]), _nm(v["at_mm"][1]))
        dia = _nm(v["dia_mm"])
        circ = pcbnew.SHAPE_CIRCLE(at, dia // 2)
        if not (_foreign_clear(board, circ, top, foreign_codes, clr_nm)
                and _foreign_clear(board, circ, bot, foreign_codes, clr_nm)):
            report.update(refused=True,
                          reason=f"via on net {v['net']!r} collides FOREIGN copper -- whole cell refused")
            return report
        built.append(("via", v, nc, top, bot, at, dia))

    # ALL clear -> ACTUATE: add LOCKED copper.
    for item in built:
        if item[0] == "track":
            _, tr, nc, ly, S, E, w = item
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(S); t.SetEnd(E); t.SetWidth(w); t.SetLayer(ly)
            t.SetNetCode(nc); t.SetLocked(True)
            board.Add(t)
            report["laid_tracks"] += 1
        else:
            _, v, nc, top, bot, at, dia = item
            vv = pcbnew.PCB_VIA(board)
            vv.SetPosition(at); vv.SetWidth(dia); vv.SetDrill(_nm(v["drill_mm"]))
            vv.SetLayerPair(top, bot); vv.SetNetCode(nc); vv.SetLocked(True)
            board.Add(vv)
            report["laid_vias"] += 1
    report["nets"] = sorted({tr["net"] for tr in tracks} | {v["net"] for v in vias})
    return report


def synthesize_ideal_internal(template, *, width=0.2, layer="F.Cu", escape_mm=1.2):
    """Compile-time SUPER-TIGHT IDEAL internal routing (owner addition 2026-07-08,
    docs/pass-form-plan.md §4 P4): for each INTERNAL net that carries >=2 recorded pads
    (template['internal_pads']) but NO extracted copper yet, lay a tight orthogonal route in
    the template's local frame. Each pad ESCAPES outward from its owner part's centre (so the
    run leaves the pad ROW instead of plowing down its own part's other pads -- the naive
    pad-to-pad straight line clips the adjacent foreign pads), then the escape points connect
    with an orthogonal (L) chain. Returns a NEW template (shallow copy) with those ideal tracks
    APPENDED to internal_tracks. A net that already carries extracted copper is left untouched
    (real extraction always wins over synthesis).

    This is how a cell whose SOURCE board was never routed (e.g. the eps sense cell -- the
    committed board is placement-only) still arrives at stamp() pre-routed for its LOCAL nets:
    the internal route is a short legal connection, laid + LOCKED at stamp (guard-checked
    against foreign copper on the destination -- a route that still collides is REFUSED, per
    spec). Non-local nets (ports) stay for the board passes, per the owner directive ('super
    tight ideal routing ... for ones that are staying local')."""
    have = {tr["net_role"] for tr in template.get("internal_tracks", [])}
    pcenter = {ref: tuple(spec["offset_mm"]) for ref, spec in template["parts"].items()}
    add = []
    for role, spec in (template.get("internal_pads") or {}).items():
        if role in have:
            continue
        pads = spec.get("pads", [])
        if len(pads) < 2:
            continue                          # a lone pad (e.g. an unconnected/Alert pad) is not routable
        # per-pad OUTWARD escape (from owner-part centre), snapped to the dominant axis.
        nodes = []                            # (pad_pt, escape_pt)
        for p in pads:
            px, py = p["rel_mm"]
            cx, cy = pcenter.get(p["ref"], (px, py))
            dx, dy = px - cx, py - cy
            if abs(dx) >= abs(dy):
                esc = (px + math.copysign(escape_mm, dx or 1.0), py)
            else:
                esc = (px, py + math.copysign(escape_mm, dy or 1.0))
            nodes.append(((px, py), esc))
        # nearest-neighbour order on the escape points (deterministic, 'super tight').
        order = [0]
        rem = list(range(1, len(nodes)))
        while rem:
            lx, ly = nodes[order[-1]][1]
            nxt = min(rem, key=lambda i: (nodes[i][1][0] - lx) ** 2 + (nodes[i][1][1] - ly) ** 2)
            order.append(nxt); rem.remove(nxt)
        pts = []
        for k, idx in enumerate(order):
            pad_pt, esc_pt = nodes[idx]
            if k == 0:
                pts += [pad_pt, esc_pt]
            else:
                prev = pts[-1]
                pts += [(esc_pt[0], prev[1]), esc_pt, pad_pt]   # orthogonal L: horizontal then vertical
        for a, b in zip(pts, pts[1:]):
            if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9:
                continue                       # skip a degenerate zero-length segment
            add.append({
                "net_role": role,
                "layer": layer,
                "start_rel_mm": [round(a[0], 6), round(a[1], 6)],
                "end_rel_mm": [round(b[0], 6), round(b[1], 6)],
                "width_mm": width,
            })
    if not add:
        return template
    out = dict(template)
    out["internal_tracks"] = list(template.get("internal_tracks", [])) + add
    return out


def locked_nets(board):
    """The set of net NAMES that carry at least one LOCKED track or via on `board`. Generally
    useful (P4/S3): the derived protect-list for route_oracle_grade (so a stamped cell's LOCKED
    internal copper is fix->protect'd through Freerouting and SURVIVES the route), and the skip
    set for the double-lay guard below. `board` may be a path or an already-loaded pcbnew board."""
    b = pcbnew.LoadBoard(board) if isinstance(board, str) else board
    out = set()
    for t in b.GetTracks():
        if t.IsLocked():
            n = t.GetNetname()
            if n:
                out.add(n)
    return out


class guard_kelvin_double_lay:
    """Context manager -- the P4 DOUBLE-LAY GUARD (docs/pass-form-plan.md §4, S3), implemented
    WITHOUT editing cec_fr.py (S2/A5 own that file; its skip_locked_taps is not merged). Wraps
    cec_fr.synthesize_kelvin_taps for the duration so it SKIPS any Kelvin pair whose *_HI/_LO
    net already carries LOCKED copper (a stamped cell's pre-routed sense chain) -- the tap
    synthesizer must not lay a second, redundant tap on a net the blueprint already owns.

    BYTE-SAFE: when `locked_net_names` is empty (every non-blueprint board -- FR output isn't
    locked, the golden floorplan carries 0 tracks) NO wrap is installed and the tap path is
    byte-identical. Only a board that actually laid LOCKED Kelvin copper triggers a skip."""

    def __init__(self, cec_fr_module, locked_net_names):
        self.mod = cec_fr_module
        self.skip = set(locked_net_names or ())
        self._orig = None

    def __enter__(self):
        if not self.skip:
            return self                          # inert -> byte-identical
        orig = self.mod.synthesize_kelvin_taps
        self._orig = orig
        skip = self.skip

        def wrapped(board, *, kelvin_pairs=None, **kw):
            if kelvin_pairs is None:
                kelvin_pairs = self.mod._board_kelvin_pairs(board)
            kept = [pr for pr in kelvin_pairs if not (set(pr) & skip)]
            return orig(board, kelvin_pairs=kept, **kw)

        self.mod.synthesize_kelvin_taps = wrapped
        return self

    def __exit__(self, *exc):
        if self._orig is not None:
            self.mod.synthesize_kelvin_taps = self._orig
        return False
