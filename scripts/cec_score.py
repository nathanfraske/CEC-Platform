#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_score -- SCORER + GATES tier for the CEC automated routing pipeline.
# ============================================================================
# Evaluates a KiCad PCB candidate and returns a Metrics snapshot containing:
#   * Hard gates on safety-critical nets — Kelvin sense pairs (_HI/_LO) and
#     differential signal pairs (_P/_N) MUST both be routed and fully connected
#     or the candidate is rejected outright via gates_pass=False.
#   * A soft objective (lower = better) for ranking gate-passing candidates:
#     weighted penalty on structural DRC, unconnected ratlines, total length,
#     via count, and copper balance.
#
# DRC filter matches cec_route.verify() exactly — cosmetic types are excluded
# from the structural count so only real copper/clearance errors count.
#
# Usage:
#   from cec_score import score, gate, objective, Rules, Metrics, DEFAULT_WEIGHTS
#   m = score("path/to/board.kicad_pcb")
#   passed, reasons = gate(m)
#   cost = objective(m)
# ============================================================================
import os, sys, json, re, math, subprocess, tempfile
from collections import defaultdict
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import pcbnew                       # only the DRC paths need it; the scoring math is pure-python
except ImportError:                     # host without KiCad (R-05 toolchain degradation)
    pcbnew = None
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_toolchain as _tc   # dependency-free toolchain presence helpers (R-05)

# ---------------------------------------------------------------------------
#  DRC filter — MUST match cec_route.verify() exactly
# ---------------------------------------------------------------------------
COSMETIC_DRC_TYPES = (
    "silk_overlap",
    "silk_over_copper",
    "silk_edge_clearance",
    "lib_footprint_mismatch",
    "lib_footprint_issues",
)

# DRC types that make a routed sense / diff pair leg ELECTRICALLY INVALID even though it is
# connected (>=1 track, 0 ratlines). A /SENSEC*_LO leg fully routed but shorted to GND/+3V3 reads
# "routed" yet is a broken Kelvin sense -- _check_pairs used to false-green it. The kelvin/diffpair
# gate now ALSO fails a leg whose net appears in any of these foreign-net-contact violations.
SENSE_FAULT_DRC_TYPES = (
    "shorting_items",
    "clearance",
    "solder_mask_bridge",
    "tracks_crossing",
)

# ---------------------------------------------------------------------------
#  Net-name conventions
# ---------------------------------------------------------------------------
# Kelvin pairs:  /SENSEC1_HI / /SENSEC1_LO  (suffix _HI / _LO, same stem)
# Diff pairs:    /USB_D_P    / /USB_D_N      (suffix _P  / _N,  same stem)
# 12V / HC nets: net name contains '12V' OR matches a /SENSEC*_HI force-net
#                (the _HI tap shares the 12V force net on these boards, so it
#                 is also a high-current net by convention).

_RE_KELVIN_HI = re.compile(r"^(.+)_HI$")
_RE_DIFF_P    = re.compile(r"^(.+)_P$")


def _derive_pairs(net_names):
    """Return (kelvin_pairs, diff_pairs) from a list of net name strings."""
    names = set(net_names)
    kelvin, diff = [], []
    for n in sorted(names):
        m = _RE_KELVIN_HI.match(n)
        if m:
            lo = m.group(1) + "_LO"
            # PHANTOM-PAIR guard (escalated review 2026-07-08): only pair when the
            # fabricated LO name EXISTS -- the 24-pin's 5V pair is (/SENSE5V_HI,
            # +5V_MAIN), so a fabricated /SENSE5V_LO made the kelvin gate structurally
            # unpassable. The shunt-straddle derivation carries the real rail-sided
            # pairs; the name rule must never invent nets.
            if lo in names:
                kelvin.append((n, lo))
    for n in sorted(names):
        m = _RE_DIFF_P.match(n)
        if m:
            neg = m.group(1) + "_N"
            if neg in names:
                diff.append((n, neg))
    return kelvin, diff


def _derive_nets_12v(net_names):
    """Nets whose names contain '12V' or match /SENSEC*_HI (high-current force nets)."""
    out = []
    for n in net_names:
        if "12V" in n or re.match(r"^/SENSEC\d+_HI$", n):
            out.append(n)
    return out


# ---------------------------------------------------------------------------
#  Rules
# ---------------------------------------------------------------------------
@dataclass
class Rules:
    """What the scorer needs to know about a board to gate/score it.

    All fields are optional — when empty, the scorer derives them from net
    names by convention (_HI/_LO for Kelvin, _P/_N for diff pairs, '12V' or
    /SENSEC*_HI for high-current nets).  Construct via Rules.from_board() for
    the auto-derived defaults.
    """
    kelvin_pairs: list = field(default_factory=list)
    # [("/SENSEC1_HI", "/SENSEC1_LO"), ...]
    diff_pairs: list = field(default_factory=list)
    # [("/USB_D_P", "/USB_D_N"), ...]
    nets_12v: list = field(default_factory=list)
    # high-current nets (for cu12v metric)
    require_drc_zero: bool = True
    # whether gates require structural DRC == 0
    require_unconnected_zero: bool = True
    # whether gates require every routed net to have zero remaining ratlines

    @classmethod
    def from_board(cls, board_path: str) -> "Rules":
        """Derive Rules from the board's actual net list PLUS shunt-straddle Kelvin pairs
        (2026-07-08): the two nets of any 2-pad RS* shunt form a pair regardless of naming --
        real boards carry a POWER net on one shunt side (24-pin RS2 -> +5V_MAIN, RS4 -> +5VSB;
        12VHPWR lane 6's HI renamed /FAN_12V), and the name-only derivation silently DROPPED
        those rails from the kelvin HARD GATE. Orientation: name hint, else the side a known
        sense IC's IN+ pad taps, else lexical."""
        b = pcbnew.LoadBoard(board_path)
        net_names = [n.GetNetname()
                     for n in b.GetNetInfo().NetsByNetcode().values()
                     if n.GetNetname()]
        kelvin, diff = _derive_pairs(net_names)
        seen = {frozenset(p) for p in kelvin}
        inp_pin = {"INA238": "10", "INA228": "10", "INA226": "10", "INA181": "3"}
        ina_inp = {}                                   # net -> True (a known IN+ pad taps it)
        shunts = []
        for fp in b.GetFootprints():
            ref = fp.GetReference() or ""
            val = (fp.GetValue() or "").upper()
            want = next((v for k, v in inp_pin.items() if k in val), None)
            for p in fp.Pads():
                if want is not None and p.GetPadName() == want and p.GetNetname():
                    ina_inp[p.GetNetname()] = True
            if ref.startswith("RS") and fp.GetPadCount() == 2:
                nets = sorted({p.GetNetname() for p in fp.Pads() if p.GetNetname()})
                if len(nets) == 2:
                    shunts.append(tuple(nets))
        for na, nb in shunts:
            key = frozenset((na, nb))
            if key in seen:
                continue
            seen.add(key)
            if na.endswith("_HI") or nb.endswith("_LO"):
                hi, lo = na, nb
            elif nb.endswith("_HI") or na.endswith("_LO"):
                hi, lo = nb, na
            elif ina_inp.get(na):
                hi, lo = na, nb
            elif ina_inp.get(nb):
                hi, lo = nb, na
            else:
                hi, lo = na, nb
            kelvin.append((hi, lo))
        nets_12v = _derive_nets_12v(net_names)
        return cls(kelvin_pairs=kelvin, diff_pairs=diff, nets_12v=nets_12v)


# ---------------------------------------------------------------------------
#  Metrics
# ---------------------------------------------------------------------------
@dataclass
class Metrics:
    drc: int             # structural DRC violation count (lower better; 0 ideal)
    unconnected: int     # unrouted ratline count
    length: float        # total routed track length, mm
    vias: int            # via count
    tracks: int          # track segment count
    kelvin_ok: bool      # HARD GATE: all Kelvin pairs routed
    diffpair_ok: bool    # HARD GATE: all diff pairs routed
    cu12v: float         # routed copper length on the 12V/high-current nets, mm
    balance: float       # F.Cu vs B.Cu copper balance [0,1] (1 = perfectly balanced)
    gates_pass: bool     # pair gates AND configured DRC/unconnected completion gates
    detail: dict         # per-net breakdown, gate reasons, raw counts — decision log
    # Structural-violation breakdown from the SAME DRC run (R-02: callers must not re-run
    # DRC to get these -- cec_dispatch._drc_types used to be a second full DRC per board).
    drc_types: dict = field(default_factory=dict)   # violation type -> count (cosmetic filtered)
    drc_loci: list = field(default_factory=list)    # [{type, where}] for the first violations
    # mm of TRACK on detected plane layers (any net -- planes carry zones, never tracks;
    # corpus gnd-plane-continuity / the FR-04 owner-override finding). Priced in objective().
    plane_signal_mm: float = 0.0


# ---------------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------------
def _run_drc(board_path: str, tmp: str) -> dict:
    """Run kicad-cli DRC and return raw JSON dict."""
    cli = _tc.require_kicad_cli("scoring DRC")    # FAIL FAST with the install hint (R-05)
    subprocess.run(
        [cli, "pcb", "drc", "--exit-code-violations",
         "--format", "json", "-o", tmp, board_path],
        capture_output=True,
    )
    # KiCad's JSON is UTF-8 and may contain non-ASCII net/reference text.  Do not
    # inherit Python's process locale here: headless workers and fresh WSL images
    # commonly run with an ASCII C locale, which made otherwise valid DRC output
    # impossible to score.
    with open(tmp, encoding="utf-8") as fh:
        return json.load(fh)


def _types_loci(struct: list) -> tuple[dict, list]:
    """Structural violations -> (type->count, [{type, where}]) -- the judge-facing
    breakdown. ONE definition (R-02): score() populates Metrics.drc_types/drc_loci from
    the same DRC run, and drc_types() below serves standalone callers (cec_constraints)."""
    import collections
    types = dict(collections.Counter(v["type"] for v in struct))
    loci = []
    for v in struct[:80]:
        desc = " ".join(it.get("description", "") for it in v.get("items", []))
        # keep enough of the description that BOTH 'of <REF>' tokens and BOTH bracketed nets
        # survive (the finishing classifier reads them) -- 80 chars truncated the 2nd token.
        loci.append({"type": v["type"], "where": re.sub(r"\s+", " ", desc)[:160]})
    return types, loci


def drc_types(board_path: str) -> tuple[dict, list]:
    """Standalone (types, loci) for callers holding only a board path (one DRC run).
    Callers that already score() the board must read Metrics.drc_types/drc_loci instead
    -- that is the whole point of R-02 (no second DRC per scored board)."""
    fd, tmp = tempfile.mkstemp(prefix="cec_score_drc_", suffix=".json")
    os.close(fd)
    try:
        d = _run_drc(board_path, tmp)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    struct = [v for v in d.get("violations", []) if v.get("type") not in COSMETIC_DRC_TYPES]
    try:
        board = pcbnew.LoadBoard(board_path)
        struct = qualify_structural_violations(struct, board)
    except Exception:                                      # noqa: BLE001 -- parity filter is best-effort here
        pass
    return _types_loci(struct)


# matches 'Pad 1 [GND] of SW2 on F.Cu' AND 'PTH pad 1 [GND] of H3' (kicad-cli varies the form)
_RE_PAD_ITEM = re.compile(r"^(?:\w+ )??[Pp]ad (\S+) \[[^\]]*\] of (\S+)")


def _drop_impossible_pad_artifacts(struct: list, board) -> list:
    """Drop the DOCUMENTED headless kicad-cli false positives: a shorting_items /
    solder_mask_bridge violation whose items are EXACTLY the pads of one footprint that do
    not even touch (seen on the rotated TS-1088 buttons: 'SW2 pad1<->pad2 short', pads
    4.36mm apart; recorded in CLAUDE.md as geometrically-impossible-absent-in-GUI). The
    filter is GEOMETRY-VERIFIED against the live board -- pads are re-tested with the same
    Collide() the DRC engine uses and the violation is kept whenever they truly touch, so a
    REAL overlapping-pad short can never be filtered. A real short THROUGH copper lists the
    track/via in items (>2 items or a non-pad item) and is never touched here."""
    fcu = board.GetLayerID("F.Cu")
    pads = {}
    footprints = {}
    for fp in board.GetFootprints():
        footprints[fp.GetReference()] = fp
        for p in fp.Pads():
            pads[(fp.GetReference(), str(p.GetPadName()))] = p
    mounts = {fp.GetReference() for fp in board.GetFootprints()
              if "mountinghole" in str(fp.GetFPID().GetLibItemName()).lower()}
    out = []
    for v in struct:
        if v.get("type") in ("shorting_items", "solder_mask_bridge"):
            items = v.get("items", [])
            parsed = [_RE_PAD_ITEM.match(it.get("description", "")) for it in items]
            # CROSS-FACE artifact (2026-07-08, dual-sided boards): two SMD pads whose copper
            # layer sets are DISJOINT (one F.Cu, one B.Cu) cannot short -- verified by layer
            # sets, not position. kicad-cli reports these on coincident-xy opposite-face pads.
            if len(items) == 2 and all(parsed):
                pa = pads.get((parsed[0].group(2), parsed[0].group(1)))
                pb = pads.get((parsed[1].group(2), parsed[1].group(1)))
                if pa is not None and pb is not None:
                    try:
                        la = set(pa.GetLayerSet().CuStack())
                        lb = set(pb.GetLayerSet().CuStack())
                        if la and lb and not (la & lb):
                            continue                   # opposite faces: impossible short
                    except Exception:                  # noqa: BLE001
                        pass
            if len(items) == 2 and all(parsed) and parsed[0].group(2) == parsed[1].group(2):
                pa = pads.get((parsed[0].group(2), parsed[0].group(1)))
                pb = pads.get((parsed[1].group(2), parsed[1].group(1)))
                if pa is not None and pb is not None:
                    try:
                        lay = fcu if fcu >= 0 else pa.GetLayer()
                        if not pa.GetEffectiveShape(lay).Collide(pb.GetEffectiveShape(lay), 0):
                            continue                       # impossible short -> the known artifact
                    except Exception:                      # noqa: BLE001 -- never widen the filter on error
                        pass
        elif v.get("type") == "hole_clearance":
            # KiCad CLI 10 can ignore an otherwise valid sibling .kicad_dru
            # copper-to-hole exception. Duplicate the XKB drawing-qualified
            # connector exception in the headless scoring path, bounded by all of:
            # exact footprint, exact four SMD lands, the connector's own NPTH,
            # and the declared 0.15 mm floor. Foreign holes, routed copper,
            # other lands, other connectors, and tighter geometry still fail.
            items = v.get("items", [])
            descs = [it.get("description", "") for it in items]
            pad_ms = [_RE_PAD_ITEM.match(x) for x in descs]
            pad_hits = [m for m in pad_ms if m]
            npth_refs = [re.match(r"^NPTH pad of (\S+)$", x) for x in descs]
            npth_hits = [m for m in npth_refs if m]
            actual = re.search(r"\bactual\s+([0-9.]+)\s*mm", v.get("description", ""))
            if (len(items) == 2 and len(pad_hits) == 1 and len(npth_hits) == 1
                    and pad_hits[0].group(2) == npth_hits[0].group(1)
                    and pad_hits[0].group(1) in {"A4", "A9", "B1", "B12"}
                    and actual and float(actual.group(1)) >= 0.15):
                fp = footprints.get(pad_hits[0].group(2))
                if fp is not None:
                    libname = str(fp.GetFPID().GetLibItemName())
                    if libname == "USB_C_Receptacle_XKB_U262-16XN-4BVC11":
                        continue
        elif v.get("type") == "copper_edge_clearance":
            # MOUNT-pad annulus near Edge.Cuts: the documented deliberate finishing state
            # (place_mechanical e=3.5 note -- an M3 screw pad may hug the edge; the GUI
            # clears it). Waived ONLY for a mounting-hole footprint's pad vs an edge
            # segment; every other copper-vs-edge hit stays structural.
            items = v.get("items", [])
            if len(items) == 2:
                descs = [it.get("description", "") for it in items]
                pad_ms = [_RE_PAD_ITEM.match(x) for x in descs]
                has_edge = any("Edge.Cuts" in x or "edge" in x.lower() for x in descs)
                pad_refs = [m.group(2) for m in pad_ms if m]
                if has_edge and pad_refs and all(r in mounts for r in pad_refs):
                    continue
                # Reverse-mount LED vendor land vs its OWN optical aperture.
                # KiCad CLI can miss the sibling .kicad_dru on renamed route
                # artifacts, so duplicate the scoped rule here instead of
                # either hiding all board-edge errors or falsely rejecting the
                # manufacturer's intended land.  The waiver is deliberately
                # narrow: pad only, same footprint's Edge.Cuts graphic, the
                # exact SK6812MINI-E reverse-mount family, and a measured gap
                # at/above the declared 0.25 mm qualified minimum. Tracks,
                # vias, foreign apertures, and tighter lands remain failures.
                edge_refs = []
                for desc in descs:
                    match = re.search(r"\bof (DL\d+)\b.*\bEdge\.Cuts\b", desc)
                    if match:
                        edge_refs.append(match.group(1))
                actual = re.search(r"\bactual\s+([0-9.]+)\s*mm", v.get("description", ""))
                if (len(pad_refs) == 1 and len(edge_refs) == 1
                        and pad_refs[0] == edge_refs[0] and actual
                        and float(actual.group(1)) >= 0.25):
                    fp = footprints.get(pad_refs[0])
                    if fp is not None:
                        libname = str(fp.GetFPID().GetLibItemName()).lower()
                        if "sk6812mini-e" in libname and "reversemount" in libname:
                            continue
        out.append(v)
    return out


def _drop_profile_qualified_pofv_geometry(struct: list, board) -> list:
    """Remove generic via-size DRC rows proven legal by the board fab profile.

    KiCad's global minimum via diameter/annular settings cannot express a
    process-qualified POFV exception.  The pipeline's fabrication contract can:
    it checks the actual diameter/drill pair, exact full-land containment in a
    same-net SMD pad, and the declared board profile.  Suppress only those two
    generic geometry messages for a via that passes that centralized proof.
    Clearance, shorts, dangling copper, overhanging lands, and ordinary
    undersized vias remain structural failures.
    """
    import cec_fab_profile as fab

    # KiCad 9/10 may report a profile-qualified small POFV drill through the
    # aggregate ``drill_out_of_range`` code instead of ``via_diameter``.
    # Apply the exact same containment/process proof; this is not a blanket
    # drill waiver and ordinary/off-pad undersized barrels still fail.
    qualified_types = {
        "via_diameter", "annular_width", "drill_out_of_range"}
    vias = []
    for item in board.GetTracks():
        if item.GetClass() != "PCB_VIA":
            continue
        pos = item.GetPosition()
        vias.append((pos.x, pos.y, item))

    def _qualified(row):
        if row.get("type") not in qualified_types:
            return False
        via_items = [item for item in row.get("items", ())
                     if (item.get("description") or "").startswith("Via [")]
        if len(via_items) != 1:
            return False
        pos = via_items[0].get("pos") or {}
        try:
            x = int(round(float(pos["x"]) * 1e6))
            y = int(round(float(pos["y"]) * 1e6))
        except (KeyError, TypeError, ValueError):
            return False
        matches = [via for vx, vy, via in vias
                   if abs(vx - x) <= 1_000 and abs(vy - y) <= 1_000]
        if len(matches) != 1:
            return False
        via = matches[0]
        blocking, allowed = fab.via_at_pad_conflicts(
            board, via.GetPosition(), via.GetWidth(via.TopLayer()),
            via.GetDrillValue(), via.GetNetCode())
        return blocking is None and bool(allowed)

    return [row for row in struct if not _qualified(row)]


def _drop_qualified_endpoint_neckdown_geometry(struct: list, board) -> list:
    """Suppress only bounded, locked fine-pitch launch width findings.

    A board-wide Power-class minimum describes the current-carrying body of a
    route, but a smaller IC land can require a short manufacturable escape
    before that body begins.  KiCad custom rules cannot identify the
    generator-owned endpoint prefix, so prove it from exact board geometry:
    the complete narrow component must be locked, at/above the board process
    floor, unbranched, within the same bounded escape budget used by the
    router, start in a same-net fine-pitch SMD pad, and terminate at a
    same-net track meeting the declared width.  Anything remote, unlocked,
    branched, long, below process minimum, or lacking a full-width throat
    remains a structural DRC failure.
    """
    tracks = [item for item in board.GetTracks()
              if item.GetClass() == "PCB_TRACK"]
    by_uuid = {item.m_Uuid.AsString(): item for item in tracks}
    try:
        board_min = int(board.GetDesignSettings().m_TrackMinWidth)
    except Exception:                                   # noqa: BLE001
        board_min = pcbnew.FromMM(0.20)

    def point_key(point):
        return int(point.x), int(point.y)

    endpoint_index = defaultdict(list)
    for item in tracks:
        endpoint_index[(item.GetNetCode(), item.GetLayer(),
                        point_key(item.GetStart()))].append(item)
        endpoint_index[(item.GetNetCode(), item.GetLayer(),
                        point_key(item.GetEnd()))].append(item)

    pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()]

    def qualified(row):
        if row.get("type") != "track_width":
            return False
        items = row.get("items") or ()
        if len(items) != 1:
            return False
        seed = by_uuid.get(str(items[0].get("uuid") or ""))
        if seed is None or not seed.IsLocked():
            return False
        match = re.search(
            r"\bmin width\s+([0-9.]+)\s*mm", row.get("description", ""))
        if not match:
            return False
        required = pcbnew.FromMM(float(match.group(1)))
        if (seed.GetWidth() >= required or seed.GetWidth() < board_min):
            return False

        net_code, layer = seed.GetNetCode(), seed.GetLayer()
        component = {seed.m_Uuid.AsString(): seed}
        queue = [seed]
        while queue:
            current = queue.pop()
            for point in (current.GetStart(), current.GetEnd()):
                for neighbor in endpoint_index.get(
                        (net_code, layer, point_key(point)), ()):
                    uid = neighbor.m_Uuid.AsString()
                    if uid in component:
                        continue
                    if (neighbor.IsLocked()
                            and board_min <= neighbor.GetWidth() < required):
                        component[uid] = neighbor
                        queue.append(neighbor)
        # A bounded endpoint profile has at most two bends and no branches.
        if len(component) > 4:
            return False
        degree = defaultdict(int)
        for item in component.values():
            degree[point_key(item.GetStart())] += 1
            degree[point_key(item.GetEnd())] += 1
        if any(value > 2 for value in degree.values()):
            return False
        length_mm = sum(math.hypot(
            item.GetEnd().x - item.GetStart().x,
            item.GetEnd().y - item.GetStart().y) / 1e6
            for item in component.values())
        required_mm = required / 1e6
        budget_mm = max(0.6, min(1.5, 1.5 * required_mm))
        if length_mm > budget_mm + 0.001:
            return False

        component_ids = set(component)
        component_points = {
            point_key(point)
            for item in component.values()
            for point in (item.GetStart(), item.GetEnd())}
        has_throat = False
        for key in component_points:
            for neighbor in endpoint_index.get((net_code, layer, key), ()):
                if (neighbor.m_Uuid.AsString() not in component_ids
                        and neighbor.GetWidth() >= required):
                    has_throat = True
                    break
            if has_throat:
                break
        if not has_throat:
            return False

        has_fine_pad = False
        for pad in pads:
            if pad.GetNetCode() != net_code:
                continue
            try:
                if int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD):
                    continue
                if layer not in set(pad.GetLayerSet().CuStack()):
                    continue
            except Exception:                           # noqa: BLE001
                continue
            if min(pad.GetSize().x, pad.GetSize().y) >= required:
                continue
            shape = pad.GetEffectiveShape(layer)
            if any(shape.Collide(pcbnew.VECTOR2I(x, y), 0)
                   for x, y in component_points):
                has_fine_pad = True
                break
        return has_fine_pad

    return [row for row in struct if not qualified(row)]


def qualify_structural_violations(struct: list, board) -> list:
    """Apply the central, geometry-proven DRC qualification contract.

    Every consumer that turns KiCad rows into a project or fabrication gate
    must use this function.  Keeping the sequence in one public entry point
    prevents an independent audit from counting a process-qualified POFV or
    manufacturer land that the route scorer has already proved, while each
    underlying predicate remains fail-closed and geometry bounded.
    """
    rows = _drop_impossible_pad_artifacts(list(struct), board)
    rows = _drop_profile_qualified_pofv_geometry(rows, board)
    return _drop_qualified_endpoint_neckdown_geometry(rows, board)


def _parse_net_from_desc(desc: str) -> str | None:
    """Extract net name from a DRC item description like 'Track [/FOO] on F.Cu'."""
    m = re.search(r"\[([^\]]+)\]", desc)
    if not m:
        return None
    v = m.group(1)
    # skip type labels like 'PTH', 'SMD' that can appear in pad descs
    if v in ("PTH", "SMD", "NPTH", "no net", "<no net>"):
        return None
    return v


def _unconnected_nets(unconnected_items: list) -> set:
    """Return set of net names that appear in any unconnected ratline."""
    nets = set()
    for uc in unconnected_items:
        for item in uc.get("items", []):
            n = _parse_net_from_desc(item.get("description", ""))
            if n:
                nets.add(n)
    return nets


def _unconnected_signature(unconnected_items: list):
    """Stable endpoint-level signature for residual-route plateau tracing."""
    rows = []
    for violation in unconnected_items:
        endpoints = []
        nets = set()
        for item in violation.get("items", []):
            description = str(item.get("description", ""))
            net = _parse_net_from_desc(description)
            if net:
                nets.add(net)
            pos = item.get("pos") or {}
            endpoints.append({
                "description": description,
                "x": round(float(pos.get("x", 0.0)), 4),
                "y": round(float(pos.get("y", 0.0)), 4),
            })
        endpoints.sort(key=lambda row: (
            row["description"], row["x"], row["y"]))
        distance = None
        if len(endpoints) == 2:
            distance = round(math.hypot(
                endpoints[1]["x"] - endpoints[0]["x"],
                endpoints[1]["y"] - endpoints[0]["y"]), 4)
        rows.append({"nets": sorted(nets), "endpoints": endpoints,
                     "distance_mm": distance})
    rows.sort(key=lambda row: (
        row["nets"], [(item["description"], item["x"], item["y"])
                      for item in row["endpoints"]]))
    return rows


def _pair_fault_nets(struct: list, watch_nets: set) -> tuple[set, dict]:
    """Nets in *watch_nets* (Kelvin/diff pair legs) that appear in any SENSE_FAULT_DRC_TYPES
    violation -- a short/clearance/mask-bridge/crossing against a FOREIGN item. Returns
    (fault_nets, fault_types: net -> set(violation_type)). This is the term that makes
    kelvin_ok / diffpair_ok see a routed-but-shorted leg: a /SENSEC*_LO routed into the GND
    pour reads 0 ratlines but DOES carry a shorting_items locus, so it now FAILs the gate."""
    fault, types = set(), {}
    for v in struct:
        if v.get("type") not in SENSE_FAULT_DRC_TYPES:
            continue
        item_nets = set()
        for it in v.get("items", []):
            n = _parse_net_from_desc(it.get("description", ""))
            if n:
                item_nets.add(n)
        for n in (item_nets & watch_nets):
            fault.add(n)
            types.setdefault(n, set()).add(v["type"])
    return fault, types


def _measure_board(b) -> dict:
    """Measure tracks/vias/lengths per net and by layer from a loaded board."""
    F_CU = pcbnew.F_Cu  # layer id 0
    B_CU = pcbnew.B_Cu  # layer id 2 (In1.Cu=1, In2.Cu=3 on 4-layer)

    net_tracks = {}   # net_name -> track segment count
    net_len    = {}   # net_name -> total mm
    net_len_f  = {}   # net_name -> F.Cu mm
    net_len_b  = {}   # net_name -> B.Cu mm
    total_f    = 0.0
    total_b    = 0.0
    via_count  = 0

    # PLANE-LAYER tracks (the FR-04 owner-override finding, 2026-06-11): a copper layer
    # carrying a near-board-sized zone is a PLANE; tracks do not belong on it AT ALL
    # (they carve return-path slots -- corpus rule gnd-plane-continuity). Detect planes
    # the same way cec_fr.plane_layers does (kept inline: no cec_fr import coupling).
    bb = b.GetBoardEdgesBoundingBox()
    barea = max(1, bb.GetWidth()) * max(1, bb.GetHeight())
    plane_lids = set()
    for z in b.Zones():
        if z.GetIsRuleArea():
            continue
        zb = z.GetBoundingBox()
        if (zb.GetWidth() * zb.GetHeight()) / barea >= 0.5:
            for lid in z.GetLayerSet().CuStack():
                plane_lids.add(lid)
    net_plane_mm = {}  # net_name -> mm of track on plane layers (ANY net: all is illegal)

    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_TRACE_T:
            name = t.GetNetname()
            l    = t.GetLength() / 1e6  # nm -> mm
            ly   = t.GetLayer()
            net_tracks[name] = net_tracks.get(name, 0) + 1
            net_len[name]    = net_len.get(name, 0.0) + l
            if ly == F_CU:
                net_len_f[name] = net_len_f.get(name, 0.0) + l
                total_f += l
            elif ly == B_CU:
                net_len_b[name] = net_len_b.get(name, 0.0) + l
                total_b += l
            if ly in plane_lids:
                net_plane_mm[name] = net_plane_mm.get(name, 0.0) + l
        elif t.Type() == pcbnew.PCB_VIA_T:
            via_count += 1

    total_len   = sum(net_len.values())
    track_count = sum(net_tracks.values())

    # balance: min(F,B)/max(F,B); 1.0 when both zero (no copper at all)
    mx = max(total_f, total_b)
    balance = (min(total_f, total_b) / mx) if mx > 0.0 else 1.0

    return dict(
        net_tracks=net_tracks,
        net_len=net_len,
        total_len=total_len,
        total_f=total_f,
        total_b=total_b,
        track_count=track_count,
        via_count=via_count,
        balance=balance,
        net_plane_mm=net_plane_mm,
        plane_signal_mm=round(sum(net_plane_mm.values()), 4),
    )


def _check_pairs(
    pairs: list,
    label: str,
    net_tracks: dict,
    unconn_nets: set,
    board_nets: set,
    fault_nets: set | None = None,
    fault_types: dict | None = None,
) -> tuple[bool, list, list]:
    """Check that every pair in `pairs` is routed (≥1 track, 0 unconnected) AND electrically
    CLEAN (no short/clearance/mask/crossing DRC against a foreign net -- *fault_nets*). A pair
    leg that is fully routed but shorted to GND/+3V3 is NOT a valid Kelvin/diff leg; the routed
    +0-ratline test alone false-greened it (the documented kelvin_ok hole).

    Returns (all_ok, failing_pairs_detail, per_pair_dicts).
    """
    fault_nets = fault_nets or set()
    fault_types = fault_types or {}
    all_ok = True
    reasons = []
    per_pair = []

    for a, b in pairs:
        pair_ok = True
        pair_reasons = []

        for net in (a, b):
            if net not in board_nets:
                pair_ok = False
                pair_reasons.append(
                    f"{label} pair {a}/{b}: net {net!r} not present on board"
                )
                continue
            if net_tracks.get(net, 0) == 0:
                pair_ok = False
                pair_reasons.append(
                    f"{label} pair {a}/{b}: {net!r} has 0 routed track segments"
                )
            if net in unconn_nets:
                # count how many unconnected items reference this net — informational
                pair_ok = False
                pair_reasons.append(
                    f"{label} pair {a}/{b}: {net!r} has unconnected ratlines"
                )
            if net in fault_nets:
                # HARDENED: a routed leg shorted/too-close to a foreign net is electrically
                # invalid even with 0 ratlines -- the gate must reject it (not advisory).
                tys = ",".join(sorted(fault_types.get(net, {"short/clearance"})))
                pair_ok = False
                pair_reasons.append(
                    f"{label} pair {a}/{b}: {net!r} has a foreign-net DRC fault [{tys}] "
                    f"-- routed but electrically shorted/too-close, not a valid sense leg"
                )

        per_pair.append({"pair": (a, b), "ok": pair_ok, "reasons": pair_reasons})
        if not pair_ok:
            all_ok = False
            reasons.extend(pair_reasons)

    return all_ok, reasons, per_pair


# ---------------------------------------------------------------------------
#  Kelvin four-wire TOPOLOGY gate (the current-carrying-sense hole)
# ---------------------------------------------------------------------------
# _check_pairs above proves each sense leg is ROUTED (>=1 track, 0 ratlines) and electrically
# clean (no foreign-net short). It is BLIND to the WIRING TOPOLOGY: on a cable interposer the
# cable connector pad (J_IN/J_OUT), the shunt terminal pad (RS*) and the sense IC input pad
# (INA*) are ALL the same net (/SENSEC*_HI|_LO), so the router can satisfy the INA-input
# connectivity by tying it to the NEAREST net point -- the connector -- and 0 ratlines still
# reads kelvin_ok=True. That is NOT a 4-wire Kelvin tap: the sense then includes the
# connector->shunt force trace + contact resistance, and the sense wire carries current.
#
# The §6.8 four-wire rule is GEOMETRIC: the INA input must tap the shunt element TERMINAL only,
# so the sense stub carries no current. The deterministic test for that on the copper graph is a
# CUT-VERTEX test: build the conductor graph for the net from TRACKS + VIAS (zones EXCLUDED --
# the high-current force pour is the legitimate connector->shunt copper that terminates AT the
# shunt pad), DELETE the shunt pad node, and assert the INA input pad can no longer reach ANY
# cable-connector pad. If it can, a sense-carrying copper path bypasses the shunt element
# (parallel sense-through-connector), so the tap is not 4-wire -> FAIL.
#
#   * legitimate tap (sense stub on the shunt inner edge, force = pour/wide copper terminating
#     at the shunt pad): with the shunt pad removed the INA input dead-ends -> PASS.
#   * the documented bug (FR routes the sense pad to the connector, or the INA taps the force
#     trace upstream of the shunt): the INA reaches the connector WITHOUT the shunt -> FAIL.
#
# Self-gating: a net is checked only when it carries the per-cable triple (>=1 J connector pad,
# >=1 RS shunt pad, >=1 INA input pad). Shared-bus per-pin (12VHPWR J3/J4) / per-rail (24-pin)
# and the Hub have no such triple on a sense net -> N/A (no fault, no false-fail).
# registry kelvin-sense-no-connector-tap params (kept in sync with cec_constraints REGISTRY so
# score()'s folded gate and the standalone checker agree by construction).
_KELVIN_TOPO_SNAP_NM = 60000    # 0.06 mm  terminal-coincidence tolerance (snap_tol_mm)
_KELVIN_TOPO_REACH_NM = 150000  # 0.15 mm  pad HitTest accuracy beyond the pad edge (pad_reach_extra_mm)


def _topo_is_ina(fp) -> bool:
    s = (fp.GetReference() + " " + (fp.GetValue() or "") + " " + fp.GetFPIDAsString()).upper()
    return "INA2" in s or "INA181" in s


def _topo_is_vbus_pad(fp, padname: str) -> bool:
    """The INA226/228/238 (VSSOP-10 power-monitor) Vbus pin is footprint pad 8 -- a high-Z VOLTAGE
    tap, not a current-sense input, so it may be FR-routed to the bus/connector and is NOT a Kelvin
    fault (registry kelvin-sense-no-connector-tap). INA181/240 current-shunt amps have no Vbus pin,
    so nothing is excluded for them."""
    s = ((fp.GetValue() or "") + " " + fp.GetFPIDAsString()).upper()
    return padname == "8" and ("INA226" in s or "INA228" in s or "INA238" in s)


def ina_highz_pad_names(fp) -> frozenset:
    """Footprint pad NAMES that are HIGH-IMPEDANCE INA sense terminals carrying ~0
    current: for the INA226/228/238 VSSOP-10 power monitors the Vin+/Vin-/Vbus pins
    (pads 10/9/8); for the INA181 the inputs are 3/4, while the INA240
    SOIC/TSSOP inputs are 1/8.
    Empty for non-INA parts.

    Shared with the electro-thermal solver (cec_thermal2d) so it never injects cable
    current through Kelvin sense-tap copper, and kept consistent with this module's
    Kelvin topology gate (uses the same `_topo_is_ina` footprint detection). The Vbus
    pad (8) is INCLUDED here because, unlike the topology gate -- which excludes it as
    a benign voltage tap that may legitimately reach the bus -- the SOLVER cares only
    that it is high-Z (carries ~0 current), so it must not source/sink cable current."""
    if not _topo_is_ina(fp):
        return frozenset()
    s = ((fp.GetValue() or "") + " " + fp.GetFPIDAsString()).upper()
    if "INA240" in s:
        # INA240 SOIC/TSSOP pinout: IN- = 1, IN+ = 8.  Treating it like the
        # INA181 (3/4) made the field solver inject cable current into the
        # filtered Kelvin branches on every per-pin monitor lane.
        return frozenset({"1", "8"})
    if "INA181" in s:
        return frozenset({"3", "4"})
    return frozenset({"8", "9", "10"})


def _topo_role(fp) -> str:
    if _topo_is_ina(fp):
        return "ina"
    r = fp.GetReference().upper()
    if r.startswith("RS"):
        return "shunt"
    if r.startswith("J"):
        return "conn"
    return "other"


class _UF:
    """Tiny union-find over hashable node ids."""
    __slots__ = ("p",)

    def __init__(self):
        self.p = {}

    def add(self, x):
        if x not in self.p:
            self.p[x] = x

    def find(self, x):
        self.add(x)
        r = x
        while self.p[r] != r:
            r = self.p[r]
        while self.p[x] != r:
            self.p[x], x = r, self.p[x]
        return r

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def kelvin_topology_faults(board, kelvin_pairs, *,
                           snap_tol_nm: int = _KELVIN_TOPO_SNAP_NM,
                           pad_reach_nm: int = _KELVIN_TOPO_REACH_NM):
    """CUT-VERTEX 4-wire topology check (see the block comment above).

    Parameters
    ----------
    board        a LOADED pcbnew board object.
    kelvin_pairs [("/SENSEC1_HI","/SENSEC1_LO"), ...] -- the sense pairs to evaluate.
    snap_tol_nm  terminal-coincidence tolerance (registry snap_tol_mm).
    pad_reach_nm pad HitTest accuracy beyond the pad edge (registry pad_reach_extra_mm).

    Returns (fault_nets:set, reasons:list[str], detail:list[dict], nets_checked:int).
    A net contributes to nets_checked only when its per-cable connector/shunt/INA triple is
    present (otherwise it is N/A and silently skipped). A fault means some INA CURRENT-SENSE
    input pad (Vin+/Vin- -- the INA226/228/238 Vbus pad is excluded) on the net reaches a
    cable-connector pad on the net with the shunt pad removed.
    """
    nets = set()
    for hi, lo in kelvin_pairs:
        nets.add(hi)
        nets.add(lo)
    if not nets:
        return set(), [], [], 0

    # pads on each sense net, tagged by role (one pass over footprints). The INA226/228/238 Vbus
    # pad (a high-Z voltage tap) is reclassified to "vbus" so it is neither cut nor flagged.
    padrec = {n: [] for n in nets}                       # net -> [(node_id, role, pad)]
    for fp in board.GetFootprints():
        role = _topo_role(fp)
        ref = fp.GetReference()
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn in nets:
                pad_role = role
                if role == "ina" and _topo_is_vbus_pad(fp, p.GetPadName()):
                    pad_role = "vbus"
                padrec[nn].append(((ref, p.GetPadName()), pad_role, p))

    # tracks / vias bucketed by sense net (one pass over tracks)
    trk = {n: [] for n in nets}
    via = {n: [] for n in nets}
    for t in board.GetTracks():
        nn = t.GetNetname()
        if nn not in nets:
            continue
        if t.Type() == pcbnew.PCB_TRACE_T:
            trk[nn].append(t)
        elif t.Type() == pcbnew.PCB_VIA_T:
            via[nn].append(t)

    fault_nets, reasons, detail, checked = set(), [], [], 0

    for net in sorted(nets):
        recs = padrec[net]
        ina = [r for r in recs if r[1] == "ina"]
        shunt = [r for r in recs if r[1] == "shunt"]
        conn = [r for r in recs if r[1] == "conn"]
        if not ina or not shunt or not conn:
            continue                                     # N/A: not a per-cable connector/shunt/INA triple
        checked += 1

        uf = _UF()
        terms = []                                       # (x_nm, y_nm, frozenset(layers), node_id)
        for t in trk[net]:
            s, e = t.GetStart(), t.GetEnd()
            ly = t.GetLayer()
            na = ("t", s.x, s.y, ly)
            nb = ("t", e.x, e.y, ly)
            uf.add(na); uf.add(nb); uf.union(na, nb)
            terms.append((s.x, s.y, frozenset((ly,)), na))
            terms.append((e.x, e.y, frozenset((ly,)), nb))
        for v in via[net]:
            vp = v.GetPosition()
            ls = frozenset(v.GetLayerSet().CuStack())
            nv = ("v", vp.x, vp.y)
            uf.add(nv)
            terms.append((vp.x, vp.y, ls, nv))
        # coincidence: same point within snap tol AND sharing a copper layer (a via bridges layers)
        for i in range(len(terms)):
            xi, yi, li, ni = terms[i]
            for j in range(i + 1, len(terms)):
                xj, yj, lj, nj = terms[j]
                if abs(xi - xj) <= snap_tol_nm and abs(yi - yj) <= snap_tol_nm and (li & lj):
                    uf.union(ni, nj)
        # pad <-> terminal: skip the SHUNT pad(s) on this net -- that is the cut vertex
        for nid, role, p in recs:
            if role == "shunt":
                continue
            for (x, y, ls, tn) in terms:
                hit = False
                for ly in ls:
                    if p.IsOnLayer(ly) and p.HitTest(pcbnew.VECTOR2I(int(x), int(y)), int(pad_reach_nm)):
                        hit = True
                        break
                if hit:
                    uf.add(nid); uf.union(nid, tn)

        # any INA input pad in the same component as any cable connector pad => bypass fault
        net_fault = False
        for nid_a, _r, _pa in ina:
            if nid_a not in uf.p:
                continue                                 # INA input has no copper here (ratline -> _check_pairs)
            ra = uf.find(nid_a)
            for nid_c, _rc, _pc in conn:
                if nid_c in uf.p and uf.find(nid_c) == ra:
                    fault_nets.add(net)
                    net_fault = True
                    detail.append({"net": net, "ina": "%s.%s" % nid_a, "conn": "%s.%s" % nid_c})
                    reasons.append(
                        "kelvin pair %s: sense input %s.%s reaches connector %s.%s with the shunt "
                        "removed -- current-carrying sense (not a 4-wire tap)" %
                        (net, nid_a[0], nid_a[1], nid_c[0], nid_c[1]))
                    break
            if net_fault:
                break                                    # one fault per net is enough to gate it

    return fault_nets, reasons, detail, checked


def kelvin_topology_summary(board_path, rules=None):
    """Public path-based summary (mirrors cec_constraints.foreign_on_pour_summary). Loads the
    board, derives Kelvin pairs (rules or by net name), runs the cut-vertex topology check and
    reports {applicable, n_faults, faults, by_net, nets_checked}. applicable is False (vacuous)
    when no per-cable connector/shunt/INA sense triple exists on the board."""
    b = pcbnew.LoadBoard(board_path)
    if rules is not None and rules.kelvin_pairs:
        pairs = rules.kelvin_pairs
    else:
        names = [n.GetNetname() for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()]
        pairs, _ = _derive_pairs(names)
    fault_nets, reasons, detail, checked = kelvin_topology_faults(b, pairs)
    by_net = {}
    for d in detail:
        by_net.setdefault(d["net"], []).append("%s<-%s" % (d["ina"], d["conn"]))
    return {"applicable": checked > 0, "n_faults": len(detail), "faults": detail[:60],
            "by_net": by_net, "nets_checked": checked, "fault_nets": sorted(fault_nets),
            "reasons": reasons[:60]}


# ---------------------------------------------------------------------------
#  score()
# ---------------------------------------------------------------------------
def score(
    board_path: str,
    rules: "Rules | None" = None,
    *,
    drc_json: str | None = None,
) -> Metrics:
    """Load the board, measure copper, run DRC, evaluate hard gates, return Metrics.

    Parameters
    ----------
    board_path  Path to the .kicad_pcb file to evaluate.
    rules       Gate/scoring rules.  None → Rules.from_board(board_path).
    drc_json    Path to a pre-existing DRC JSON output.  When given, skip the
                kicad-cli DRC run (avoids a redundant run when the orchestrator
                already has it).
    """
    if rules is None:
        rules = Rules.from_board(board_path)

    # ---- load board ----
    b = pcbnew.LoadBoard(board_path)
    board_net_names: set = {
        n.GetNetname()
        for n in b.GetNetInfo().NetsByNetcode().values()
        if n.GetNetname()
    }

    # ---- fill Rules with derived values where not provided ----
    kelvin_pairs = rules.kelvin_pairs
    diff_pairs   = rules.diff_pairs
    nets_12v     = rules.nets_12v

    if not kelvin_pairs and not diff_pairs and not nets_12v:
        # fully auto-derive
        kp, dp = _derive_pairs(board_net_names)
        nv      = _derive_nets_12v(board_net_names)
        kelvin_pairs = kp
        diff_pairs   = dp
        nets_12v     = nv
    else:
        # fill in any missing field individually
        if not kelvin_pairs:
            kelvin_pairs, _ = _derive_pairs(board_net_names)
        if not diff_pairs:
            _, diff_pairs    = _derive_pairs(board_net_names)
        if not nets_12v:
            nets_12v         = _derive_nets_12v(board_net_names)

    # ---- measure copper ----
    m = _measure_board(b)

    # ---- cu12v ----
    cu12v = sum(m["net_len"].get(n, 0.0) for n in nets_12v)

    # ---- DRC ----
    if drc_json:
        with open(drc_json) as fh:
            drc_data = json.load(fh)
    else:
        # mkstemp: unique per CALL, not per process -- getpid-keyed names collide under
        # in-process concurrency (threads / repeated calls racing the same path), R-02.
        fd, tmp = tempfile.mkstemp(prefix="cec_score_drc_", suffix=".json")
        os.close(fd)
        try:
            drc_data = _run_drc(board_path, tmp)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    all_violations = drc_data.get("violations", [])
    struct = [v for v in all_violations if v["type"] not in COSMETIC_DRC_TYPES]
    struct = qualify_structural_violations(struct, b)
    unconn = drc_data.get("unconnected_items", [])
    unconn_nets = _unconnected_nets(unconn)
    unconn_signature = _unconnected_signature(unconn)
    import hashlib
    unconn_signature_sha256 = hashlib.sha256(json.dumps(
        unconn_signature, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()

    drc_count   = len(struct)
    unconn_count = len(unconn)

    # ---- structural-violation breakdown (R-02: from the same run; no second DRC) ----
    drc_types, drc_loci = _types_loci(struct)

    # ---- foreign-net DRC faults on the safety pairs (HARDENED gate term) ----
    # A routed-but-shorted sense / diff leg carries a short/clearance/mask/crossing locus while
    # reading 0 ratlines; fold those into the kelvin/diffpair gates so a /SENSEC*_LO->GND short
    # can no longer pass kelvin_ok. Computed from the SAME structural DRC run (R-02).
    watch_nets = ({n for pr in kelvin_pairs for n in pr}
                  | {n for pr in diff_pairs for n in pr})
    fault_nets, fault_types_map = _pair_fault_nets(struct, watch_nets)

    # ---- evaluate hard gates ----
    kelvin_ok, kelvin_reasons, kelvin_detail = _check_pairs(
        kelvin_pairs, "kelvin", m["net_tracks"], unconn_nets, board_net_names,
        fault_nets, fault_types_map
    )
    diffpair_ok, diff_reasons, diff_detail = _check_pairs(
        diff_pairs, "diffpair", m["net_tracks"], unconn_nets, board_net_names,
        fault_nets, fault_types_map
    )

    # ---- connected-but-geometrically-broken protected routes ----
    # DRC and ratlines cannot see an acute doubled-back trace: the Hub USB
    # pseudo-stub was connected, clearance-clean, and therefore false-green in
    # _check_pairs().  Audit exact track junction topology on the already-open
    # board.  A hit on a protected pair is a hard pair-gate fault; ordinary-net
    # hits remain ranked evidence through objective().
    try:
        import cec_route_quality
        route_quality = cec_route_quality.analyze_board(
            b, critical_nets=watch_nets)
    except Exception as _e:                                  # noqa: BLE001
        # The scorer remains available for old/non-routing artifacts, but a
        # protected pair may never pass when its topology could not be audited.
        route_quality = {
            "ok": not bool(watch_nets),
            "issue_count": 0,
            "blocking_count": (1 if watch_nets else 0),
            "advisory_count": 0,
            "critical_nets": sorted(watch_nets),
            "issues": [],
            "error": "%s: %s" % (type(_e).__name__, _e),
        }
    topology_fault_nets = {
        row.get("net") for row in route_quality.get("issues", ())
        if row.get("severity") == "blocking" and row.get("net")}
    topology_fault_nets |= {
        row.get("net") for row in route_quality.get("non_octilinear", ())
        if row.get("severity") == "blocking" and row.get("net")}
    if route_quality.get("error") and watch_nets:
        topology_reason = (
            "protected-route topology audit errored (fail-closed): %s"
            % route_quality["error"])
        kelvin_ok = False if kelvin_pairs else kelvin_ok
        diffpair_ok = False if diff_pairs else diffpair_ok
        if kelvin_pairs:
            kelvin_reasons = list(kelvin_reasons) + [topology_reason]
        if diff_pairs:
            diff_reasons = list(diff_reasons) + [topology_reason]
    else:
        for label, pairs, current_ok, reasons in (
                ("kelvin", kelvin_pairs, kelvin_ok, kelvin_reasons),
                ("diffpair", diff_pairs, diffpair_ok, diff_reasons)):
            affected = sorted({net for pair in pairs for net in pair}
                              & topology_fault_nets)
            if not affected:
                continue
            messages = [
                "%s topology gate: %s" % (label, row["message"])
                for row in (list(route_quality.get("issues", ()))
                            + list(route_quality.get("non_octilinear", ())))
                if row.get("net") in affected
                and row.get("severity") == "blocking"]
            if label == "kelvin":
                kelvin_ok = False
                kelvin_reasons = list(kelvin_reasons) + messages
            else:
                diffpair_ok = False
                diff_reasons = list(diff_reasons) + messages

    # ---- Kelvin four-wire TOPOLOGY (cut-vertex) gate, FOLDED INTO kelvin_ok ----
    # _check_pairs is blind to a current-carrying sense (INA input tied to the connector on the
    # shared sense net, 0 ratlines). The cut-vertex trace fails kelvin_ok when any INA input
    # reaches a cable-connector pad with the shunt pad removed. N/A boards (no per-cable triple)
    # contribute nothing. This makes kelvin_ok the COMPLETE 4-wire gate, so gates_pass (below) and
    # every reader (cec_router.independent_drc via gate(), the loop ranking, cec_constraints) inherit it.
    # FAIL-CLOSED on error: a hard safety gate must never pass on an exception (the opposite of the
    # foreign_on_pour fail-open summary). An unexpected board that breaks the trace fails kelvin_ok.
    try:
        topo_fault_nets, topo_reasons, topo_detail, topo_checked = kelvin_topology_faults(b, kelvin_pairs)
    except Exception as _e:                                   # noqa: BLE001
        topo_fault_nets, topo_checked = {"<error>"}, -1
        topo_detail = [{"error": "%s: %s" % (type(_e).__name__, _e)}]
        topo_reasons = ["kelvin topology gate errored (fail-closed, gate FAILS): %s: %s"
                        % (type(_e).__name__, _e)]
    if topo_fault_nets:
        kelvin_ok = False
        kelvin_reasons = list(kelvin_reasons) + topo_reasons

    drc_gate_ok = (drc_count == 0) if rules.require_drc_zero else True
    unconnected_gate_ok = ((unconn_count == 0)
                           if rules.require_unconnected_zero else True)

    gates_pass = (kelvin_ok and diffpair_ok and drc_gate_ok
                  and unconnected_gate_ok)

    # ---- detail dict ----
    detail: dict = {
        "board_path":      board_path,
        "board_nets":      sorted(board_net_names),
        "net_tracks":      m["net_tracks"],
        "net_len_mm":      {k: round(v, 4) for k, v in m["net_len"].items()},
        "total_f_mm":      round(m["total_f"], 4),
        "total_b_mm":      round(m["total_b"], 4),
        "kelvin_pairs":    kelvin_pairs,
        "kelvin_detail":   kelvin_detail,
        "kelvin_reasons":  kelvin_reasons,
        "diff_pairs":      diff_pairs,
        "diff_detail":     diff_detail,
        "diff_reasons":    diff_reasons,
        "unconn_nets":     sorted(unconn_nets),
        "unconn_signature": unconn_signature,
        "unconn_signature_sha256": unconn_signature_sha256,
        # Preserve the exact authority used for this score.  Downstream
        # provenance must not rerun DRC and then try to explain a potentially
        # different board state.  These JSON rows let every final blocker keep
        # its KiCad UUIDs and loci from the same signoff observation.
        "structural_violations": struct,
        "unconnected_items": unconn,
        "sense_fault_nets": {n: sorted(fault_types_map.get(n, [])) for n in sorted(fault_nets)},
        "route_quality": route_quality,
        "route_topology_fault_nets": sorted(topology_fault_nets),
        "kelvin_topology_faults":  topo_detail,
        "kelvin_topology_checked": topo_checked,
        "drc_struct_count": drc_count,
        "drc_gate_ok":     drc_gate_ok,
        "require_drc_zero": rules.require_drc_zero,
        "unconnected_gate_ok": unconnected_gate_ok,
        "require_unconnected_zero": rules.require_unconnected_zero,
        "nets_12v":        nets_12v,
        "cu12v_mm":        round(cu12v, 4),
        "net_plane_mm":    {k: round(v, 3) for k, v in m.get("net_plane_mm", {}).items()},
    }

    return Metrics(
        drc          = drc_count,
        unconnected  = unconn_count,
        length       = round(m["total_len"], 4),
        vias         = m["via_count"],
        tracks       = m["track_count"],
        kelvin_ok    = kelvin_ok,
        diffpair_ok  = diffpair_ok,
        cu12v        = round(cu12v, 4),
        balance      = round(m["balance"], 6),
        gates_pass   = gates_pass,
        detail       = detail,
        drc_types    = drc_types,
        drc_loci     = drc_loci,
        plane_signal_mm = m.get("plane_signal_mm", 0.0),
    )


# ---------------------------------------------------------------------------
#  gate()
# ---------------------------------------------------------------------------
def gate(m: "Metrics", rules: "Rules | None" = None) -> tuple[bool, list[str]]:
    """Return (passed, reasons).

    ``passed`` == ``m.gates_pass``.  ``reasons`` lists one string per
    failing hard gate; empty when all gates pass.

    The ``rules`` argument is accepted for API symmetry but the gate
    evaluation is taken directly from the pre-computed ``m`` fields —
    calling ``score()`` already baked the gate state into Metrics.
    """
    reasons: list[str] = []

    if not m.kelvin_ok:
        reasons.extend(m.detail.get("kelvin_reasons", [
            "kelvin gate: no detail available (re-run score())"
        ]))

    if not m.diffpair_ok:
        reasons.extend(m.detail.get("diff_reasons", [
            "diffpair gate: no detail available (re-run score())"
        ]))

    d = m.detail
    if not d.get("drc_gate_ok", True):
        reasons.append(
            f"structural DRC = {m.drc} (require 0 because require_drc_zero=True)"
        )

    if not d.get("unconnected_gate_ok", True):
        reasons.append(
            f"unconnected ratlines = {m.unconnected} "
            "(require 0 because require_unconnected_zero=True)"
        )

    # Router-side deterministic gates (via-on-pad, physical high-speed pair,
    # and future candidate-only folds) may tighten ``m.gates_pass`` after the
    # core score is built. Preserve their named reasons so the repair tier does
    # not receive an unexplained false verdict.
    reasons.extend(str(reason) for reason in
                   d.get("external_gate_reasons", ()) if reason)

    return m.gates_pass, reasons


# ---------------------------------------------------------------------------
#  objective()
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS: dict = {
    "drc":         1000.0,   # +cost per structural DRC violation
    "unconnected":  100.0,   # +cost per unrouted ratline
    "length":         0.01,  # +cost per mm of total routed copper (penalise meandering)
    "vias":           0.5,   # +cost per via
    "balance":       -5.0,   # NEGATIVE weight: (1-balance) * |W| → bonus for balanced F/B copper
    # +cost per mm of track on a plane layer: 50/mm makes 20mm of plane carving cost a
    # full DRC violation -- a candidate can never win by hiding copper in the GND plane
    # (the FR-04 scorer blind spot, owner-overridden 2026-06-11; normally 0 mm under the
    # cec_fr layer policy, so this prices REGRESSIONS, not routine routing).
    "plane_mm":      50.0,
    # Electrically legal copper can still contain an acute doubled-back vertex.
    # Price each non-critical occurrence above two ordinary ratlines; protected
    # Kelvin/differential nets fail their hard gate separately in score().
    "route_quality": 250.0,
}


def objective(m: "Metrics", weights: dict | None = None) -> float:
    """Soft cost (LOWER IS BETTER) for ranking gate-passing candidates.

    Formula (all terms add cost; balance term rewards symmetry):
        cost  = drc*W.drc
              + unconnected*W.unconnected
              + length*W.length
              + vias*W.vias
              + (1 - balance) * |W.balance|

    Sign conventions
    ----------------
    * W.drc, W.unconnected, W.length, W.vias  — positive: more = worse.
    * W.balance                                — negative in DEFAULT_WEIGHTS:
      (1 - balance) is 0 when perfectly balanced, 1 when fully one-sided.
      Multiplying by |W.balance| keeps the contribution non-negative so a
      worse-balanced board still incurs a higher cost.  The raw weight is
      stored negative to make the sign intent explicit (negative = "reward
      for balance").
    """
    w = DEFAULT_WEIGHTS.copy()
    if weights:
        w.update(weights)

    cost = (
        m.drc         * w["drc"]
        + m.unconnected * w["unconnected"]
        + m.length      * w["length"]
        + m.vias        * w["vias"]
        + getattr(m, "plane_signal_mm", 0.0) * w.get("plane_mm", 0.0)
        + int((m.detail.get("route_quality") or {}).get(
            "advisory_count", 0)) * w.get("route_quality", 0.0)
        + (1.0 - m.balance) * abs(w["balance"])
    )
    return cost


# Pour-aware, gate-gated ranking weights (retrospective lesson 7). gate_fail_base dominates so any
# gate-FAILING board ranks strictly worse than any gate-passing one; island/copper price pour
# integrity as a first-class term.
DEFAULT_V2_WEIGHTS = {"gate_fail_base": 1_000_000.0, "island": 5_000.0, "copper": 100.0}


def objective_v2(*, gates_pass, drc, islands_excess, sense_copper, base=0.0, weights=None):
    """Pour-aware, gate-gated ranking cost (LOWER IS BETTER) -- retrospective lesson 7.

    The last run rode its DRC proxy into a physically worse board: it shaved DRC by routing signal
    through the sense corridors, fragmenting the pours, while gates never passed. Fix:

      * NO DRC CREDIT WHILE gates_pass IS FALSE. A gate-failing board's cost is a fixed base plus the
        pour-integrity term ONLY -- shaving DRC cannot lower it, so the loop cannot buy proxy
        improvement with sense-copper destruction.
      * POUR INTEGRITY IS FIRST-CLASS: + island-excess cost (fragmentation) and - copper reward
        (sense-corridor copper area). The round-1 board (intact pours, worst DRC) then wins the
        scorer the way it won the eye.

    For a gate-PASSING board the supplied `base` (the normal soft cost, which credits DRC=0,
    length, vias, balance) is used and only the fragmentation PENALTY refines it; gate_fail_base
    keeps every gate-failing board above every gate-passing one regardless of pour state.

    Copper-reward loophole (PR #35 review item 1): the - copper*area reward is a PROXY, and on a
    gate-passing board it could dominate `base` and let raw copper area buy rank between two passing
    candidates -- the exact proxy pressure this change exists to kill. So the copper reward is
    GATE-FAILING-ONLY: it exists solely to make the intact round-1 board win among failing
    candidates. Passing boards carry the fragmentation penalty (island excess) but NO copper bonus,
    so copper area can never reorder two passing boards.
    """
    w = dict(DEFAULT_V2_WEIGHTS)
    if weights:
        w.update(weights)
    island_pen = w["island"] * max(0.0, islands_excess)
    if gates_pass:
        return base + island_pen                     # no copper reward -> copper can't buy rank
    copper_reward = w["copper"] * max(0.0, sense_copper)
    return w["gate_fail_base"] + island_pen - copper_reward   # drc NOT credited while failing


_SENSE_POUR_RE = re.compile(r"/?SENSEC\d+_(HI|LO)$", re.I)


def sense_pour_components(board_path):
    """F+B-mirror-AWARE pour fragmentation (SB-08 item-2 escalation, 2026-06-12). The original gate
    counts F.Cu islands (OutlineCount); that PREDATES the synthesize_power_copper F+B mirror, where a
    sense pour is legitimately SEVERAL F.Cu islands STITCHED into ONE conductor by the via field + the
    THT connector/shunt pads -- so F.Cu OutlineCount over-reports fragmentation (measured: the synth
    eps golden reads SENSEC2_LO at 3 F.Cu islands but ONE connected component). This counts CONNECTED
    COMPONENTS of each sense net's pour copper across F.Cu + B.Cu, with same-net vias and THT pads as
    inter-layer bridges -> 1 == intact. A genuinely clipped single-layer pour with no mirror/stitch
    (the validation-run R4 shape: 3 F.Cu islands, no B.Cu, no bridges) still reads 3 -> FAIL. Returns
    {net: components}. Needs pcbnew (in-container). Use to populate pour_facts[net]['components']."""
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    isl = {}                                              # net -> [(filled_polyset, outline_idx), ...]
    for z in b.Zones():
        nn = z.GetNetname()
        if not _SENSE_POUR_RE.search(str(nn)):
            continue
        for L in (pcbnew.F_Cu, pcbnew.B_Cu):
            if z.IsOnLayer(L):
                ps = z.GetFilledPolysList(L)
                for i in range(ps.OutlineCount()):
                    isl.setdefault(nn, []).append((ps, i))
    bridges = {}                                          # net -> [VECTOR2I positions] (vias + THT pads)
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() in isl:
            bridges.setdefault(t.GetNetname(), []).append(t.GetPosition())
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() in isl and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                bridges.setdefault(p.GetNetname(), []).append(p.GetPosition())
    out = {}
    for nn, nodes in isl.items():
        parent = list(range(len(nodes)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for pt in bridges.get(nn, []):
            v = pcbnew.VECTOR2I(pt.x, pt.y)
            touched = [i for i, (ps, oi) in enumerate(nodes) if ps.Contains(v, oi)]
            for k in range(1, len(touched)):
                parent[find(touched[0])] = find(touched[k])
        out[nn] = len({find(i) for i in range(len(nodes))}) if nodes else 0
    return out


def pour_integrity_ok(pour_facts, *, min_copper_mm2=None):
    """BLOCKING pour-integrity gate (PR #35 review item 2; F+B-aware SB-08 item 2, 2026-06-12). Every
    sense-pour net (/SENSEC*_HI|LO) must be ONE connected conductor. The kelvin_ok gate checks PAD
    CONNECTIVITY only and is BLIND to pour fragmentation -- it returned True on the round-4 board that
    had SENSEC2_HI at 3 islands and -21% sense copper. This gate uses the F+B-mirror-AWARE component
    count (`components`, from sense_pour_components: F.Cu islands stitched through the via field + THT
    pads count as one) when present, falling back to the raw F.Cu `islands` otherwise. A synth board's
    3-F.Cu-islands-but-1-component sense pour PASSES; R4's 3-islands-no-stitch FAILS. Optional
    `min_copper_mm2` per-sense-net copper floor. Returns (ok, reasons). Vacuously True with no sense pours."""
    reasons = []
    for net, v in (pour_facts or {}).items():
        if not isinstance(v, dict) or not _SENSE_POUR_RE.search(str(net)):
            continue
        # prefer the F+B-aware component count; fall back to the raw F.Cu island count
        comp = v.get("components")
        n = (comp if comp is not None else v.get("islands", 1)) or 1
        if n != 1:
            unit = "components" if comp is not None else "islands"
            reasons.append(f"{net}: fragmented ({n} {unit}, expected 1)")
        if min_copper_mm2 is not None and (v.get("area_mm2", 0) or 0) < min_copper_mm2:
            reasons.append(f"{net}: copper {v.get('area_mm2')}mm2 < floor {min_copper_mm2}")
    return (not reasons), reasons


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    BOARDS = [
        ("/tmp/fr-test/b_routed.kicad_pcb", "routed"),
        ("/tmp/fr-test/b.kicad_pcb",         "unrouted"),
        (os.path.join(ROOT, "beta", "eps-8pin-rev3", "eps-8pin-rev3.kicad_pcb"),
         "floorplan"),
    ]

    # Use pre-existing DRC for the routed board to save time; run fresh for others
    drc_cache = {
        "/tmp/fr-test/b_routed.kicad_pcb": "/tmp/b_routed_drc.json"
        if os.path.exists("/tmp/b_routed_drc.json") else None,
    }

    header = (
        f"{'board':<12} {'drc':>4} {'unc':>4} {'trk':>5} {'via':>4} "
        f"{'len_mm':>8} {'kv':>5} {'dp':>5} {'cu12v':>8} {'bal':>6} "
        f"{'gates':>6} {'obj':>10}"
    )
    print(header)
    print("-" * len(header))

    results = {}
    for path, label in BOARDS:
        if not os.path.exists(path):
            print(f"{label:<12}  (file not found: {path})")
            continue
        drc_hint = drc_cache.get(path)
        m = score(path, drc_json=drc_hint)
        obj = objective(m)
        results[label] = (m, obj)
        print(
            f"{label:<12} {m.drc:>4} {m.unconnected:>4} {m.tracks:>5} {m.vias:>4} "
            f"{m.length:>8.1f} {str(m.kelvin_ok):>5} {str(m.diffpair_ok):>5} "
            f"{m.cu12v:>8.1f} {m.balance:>6.3f} {str(m.gates_pass):>6} {obj:>10.1f}"
        )

    # Gate reasons for the unrouted board
    if "unrouted" in results:
        print()
        print("gate() reasons for unrouted board:")
        m_unr, _ = results["unrouted"]
        passed, reasons = gate(m_unr)
        print(f"  gates_pass = {passed}")
        for r in reasons:
            print(f"  - {r}")
