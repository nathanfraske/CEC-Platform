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
import os, sys, json, re, subprocess, tempfile
from dataclasses import dataclass, field

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
            kelvin.append((n, lo))
    for n in sorted(names):
        m = _RE_DIFF_P.match(n)
        if m:
            neg = m.group(1) + "_N"
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

    @classmethod
    def from_board(cls, board_path: str) -> "Rules":
        """Derive Rules from the board's actual net list."""
        b = pcbnew.LoadBoard(board_path)
        net_names = [n.GetNetname()
                     for n in b.GetNetInfo().NetsByNetcode().values()
                     if n.GetNetname()]
        kelvin, diff = _derive_pairs(net_names)
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
    gates_pass: bool     # kelvin_ok AND diffpair_ok AND (drc==0 if require_drc_zero)
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
    with open(tmp) as fh:
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
    return _types_loci(struct)


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
    unconn = drc_data.get("unconnected_items", [])
    unconn_nets = _unconnected_nets(unconn)

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

    drc_gate_ok = (drc_count == 0) if rules.require_drc_zero else True

    gates_pass = kelvin_ok and diffpair_ok and drc_gate_ok

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
        "sense_fault_nets": {n: sorted(fault_types_map.get(n, [])) for n in sorted(fault_nets)},
        "drc_struct_count": drc_count,
        "drc_gate_ok":     drc_gate_ok,
        "require_drc_zero": rules.require_drc_zero,
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
        ("/home/user/CEC-Platform/modules/eps-8pin/eps8pin-module.kicad_pcb",
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
