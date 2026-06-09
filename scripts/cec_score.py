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

import pcbnew
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
    )


def _check_pairs(
    pairs: list,
    label: str,
    net_tracks: dict,
    unconn_nets: set,
    board_nets: set,
) -> tuple[bool, list, list]:
    """Check that every pair in `pairs` is routed (≥1 track, 0 unconnected).

    Returns (all_ok, failing_pairs_detail, per_pair_dicts).
    """
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

    # ---- evaluate hard gates ----
    kelvin_ok, kelvin_reasons, kelvin_detail = _check_pairs(
        kelvin_pairs, "kelvin", m["net_tracks"], unconn_nets, board_net_names
    )
    diffpair_ok, diff_reasons, diff_detail = _check_pairs(
        diff_pairs, "diffpair", m["net_tracks"], unconn_nets, board_net_names
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
        "drc_struct_count": drc_count,
        "drc_gate_ok":     drc_gate_ok,
        "require_drc_zero": rules.require_drc_zero,
        "nets_12v":        nets_12v,
        "cu12v_mm":        round(cu12v, 4),
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
        + (1.0 - m.balance) * abs(w["balance"])
    )
    return cost


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
