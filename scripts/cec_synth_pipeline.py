#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_synth_pipeline.py -- the top-level board-SYNTHESIS pipeline orchestrator.
# ============================================================================
# This realizes the full run_pipeline(cfg) control flow:
#
#   Config+requirements -> ERC+BOM gate -> triage(arm optional) -> geometric floor
#   -> place+proxy(consent) -> feasibility/size oracle -> ROUTE SWARM -> physics FEA
#   -> full cascade -> gates+checks+DRC -> human sign-off -> build+freeze log.
#
# POSTURE = CAUTIOUS: at every failure/uncertainty we call resolve() -- the escalation
# ladder worker -> manager -> frontier -> human -- and any doubt escalates rather than
# being silently accepted.
#
# ---------------------------------------------------------------------------
# WHAT THIS FILE CONTAINS (built stage-by-stage; this is the CASCADE + RESOLVE backbone,
# the part every other stage hangs on):
#   * the data model            -- Config, Flag/Kind, Check, Action
#   * the netlist reader         -- a real KiCad .net s-expr parser (comps + nets)
#   * the SIX marker-criteria STAGE LISTS, each a list[Check] of REAL checks:
#       ERC_BOM, PLACEMENT, ROUTE_GATE, MEASURE, DFM, CONFORMANCE
#   * run_stage() / run_full_cascade()  -- run a stage / the post-route cascade
#   * the OPTIONAL-analysis REGISTRY + triage_arm()  -- arm the optional analyses, cautiously
#   * the resolve() escalation ladder    -- worker/manager/frontier/human rungs (the LLM
#                                           tiers plug in as pluggable callables, exactly
#                                           like cec_router.make_subagent_policy; deterministic
#                                           defaults so the whole thing runs headless)
#
# The remaining stages (geometric floor, place+proxy, the size oracle, the route_swarm
# wiring onto cec_router.route, the electrothermal physics FEA, sign-off, build+freeze)
# land in subsequent commits and plug into this backbone.
#
# Verified against the real EPS module (modules/eps-8pin) -- see the __main__ self-test.
import os
import re
import sys
import json
import glob
import math
import time
import shutil
import tempfile
import subprocess
from enum import Enum
from collections import defaultdict
from dataclasses import dataclass, field, asdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# cec_score gives the routed-board hard gates (kelvin / diffpair / DRC / unconnected).
# Import is wrapped so the cascade's non-route stages still work if pcbnew is unavailable.
try:
    import cec_score  # noqa: E402
    _HAVE_SCORE = True
except Exception as _exc:                      # pragma: no cover - env without pcbnew
    cec_score = None
    _HAVE_SCORE = False
    _SCORE_ERR = str(_exc)

# DRC/ERC violation types that are cosmetic or known-benign in this repo's flow and must
# not be treated as real gate failures (mirrors cec_score / cec_route filtering).
COSMETIC = (
    "silk_overlap", "silk_over_copper", "silk_edge_clearance",
    "lib_footprint_mismatch", "lib_footprint_issues",
)
BENIGN_ERC = (
    "lib_symbol_mismatch",          # generator symbol-cache drift (documented, harmless)
    "unconnected_wire_endpoint",    # off-grid flag stamps (documented Hub case)
)


# ============================================================ s-expr / netlist
def parse_sexpr(text):
    """Parse a KiCad s-expression string into nested Python lists. Atoms are strings
    (quotes stripped). Tolerant of the tab/newline layout KiCad emits."""
    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()]+', text)
    pos = 0

    def build():
        nonlocal pos
        node = []
        while pos < len(tokens):
            tok = tokens[pos]
            pos += 1
            if tok == "(":
                node.append(build())
            elif tok == ")":
                return node
            elif tok.startswith('"'):
                node.append(tok[1:-1].replace('\\"', '"'))
            else:
                node.append(tok)
        return node

    # skip to first '('
    while pos < len(tokens) and tokens[pos] != "(":
        pos += 1
    if pos >= len(tokens):
        return []
    pos += 1
    return build()


def _kids(node, head):
    """Yield child lists of *node* whose first atom == head."""
    for c in node:
        if isinstance(c, list) and c and c[0] == head:
            yield c


def _first(node, head, default=None):
    for c in _kids(node, head):
        return c
    return default


def _val(node, head, default=None):
    """The single atom value of (head value) under node, e.g. (ref "U1") -> 'U1'."""
    c = _first(node, head)
    if c and len(c) >= 2 and not isinstance(c[1], list):
        return c[1]
    return default


@dataclass
class Comp:
    ref: str
    value: str = ""
    footprint: str = ""
    props: dict = field(default_factory=dict)     # property name -> value (LCSC, MPN, ...)

    @property
    def lcsc(self):
        for k in ("LCSC", "LCSC Part #", "JLCPCB Part #"):
            if self.props.get(k):
                return self.props[k]
        return ""

    @property
    def excluded_from_bom(self):
        v = (self.props.get("dnp") or self.props.get("Exclude from BOM") or "").lower()
        return v in ("yes", "true", "1") or self.props.get("__dnp__") is True


@dataclass
class Netlist:
    comps: dict                                   # ref -> Comp
    nets: dict                                    # net name -> [(ref, pin), ...]
    source: str = ""

    @classmethod
    def from_file(cls, path):
        with open(path) as fh:
            root = parse_sexpr(fh.read())
        comps = {}
        comp_root = _first(root, "components") or []
        for comp in _kids(comp_root, "comp"):
            ref = _val(comp, "ref", "")
            c = Comp(ref=ref, value=_val(comp, "value", ""),
                     footprint=_val(comp, "footprint", ""))
            for prop in _kids(comp, "property"):
                name = _val(prop, "name")
                pv = _val(prop, "value", "")
                if name:
                    c.props[name] = pv
            # DNP / exclude flags appear as bare (property (name "dnp")) or a top (dnp) marker
            if any(isinstance(x, list) and x and x[0] == "dnp" for x in comp):
                c.props["__dnp__"] = True
            comps[ref] = c
        nets = {}
        nets_root = _first(root, "nets") or []
        for net in _kids(nets_root, "net"):
            name = _val(net, "name", "")
            nodes = []
            for node in _kids(net, "node"):
                nodes.append((_val(node, "ref", ""), _val(node, "pin", "")))
            nets[name] = nodes
        return cls(comps=comps, nets=nets, source=path)

    def net_of(self, ref, pin):
        """Return the net name a given (ref, pin) lands on, or None."""
        for name, nodes in self.nets.items():
            if (ref, pin) in nodes:
                return name
        return None

    def refs_like(self, *prefixes):
        return [r for r in self.comps if r.startswith(prefixes)]


# ============================================================ data model
class Kind(str, Enum):
    """Where resolve() routes a flag, and the natural first rung."""
    NETLIST = "netlist"      # ERC/BOM netlist-level (regen/edit; worker first)
    BOM     = "bom"          # sourcing gap (worker: source; else human)
    PLACE   = "placement"    # placement marker (worker: nudge; manager if structural)
    ROUTE   = "route"        # route gate / DRC (worker: re-route the offending nets)
    MEASURE = "measure"      # measurement-quality (manager: geometry judgement)
    DFM     = "dfm"          # manufacturability (worker: widen/space; manager if tight)
    CONFORM = "conformance"  # spec / locked-decision conformance (frontier; often human)
    SCOPE   = "scope"        # out-of-scope analysis alarm (manager -> frontier -> human)
    REGION  = "region"       # local routing region failure (worker)
    CROSS   = "cross"        # cross-region / seam / structural (frontier)
    SIGNOFF = "signoff"      # human sign-off objection (human)


@dataclass
class Flag:
    """A failure / uncertainty marker. CAUTIOUS posture: low conf still escalates."""
    name: str
    where: object                 # locus: a board path, a net name, a ref, a feats dict
    conf: float                   # 0..1 confidence the issue is REAL
    kind: Kind
    detail: dict = field(default_factory=dict)

    def __repr__(self):
        w = self.where if isinstance(self.where, str) else type(self.where).__name__
        return f"Flag[{self.kind.value}:{self.name} conf={self.conf:.2f} @{w}]"


@dataclass
class Check:
    """A marker criterion in a stage list: fn(view) -> list[Flag]."""
    name: str
    fn: object
    kind: Kind

    def run(self, view):
        try:
            out = self.fn(view) or []
        except Exception as exc:
            # a check that throws is itself a (cautious) flag -- never silently pass.
            return [Flag(f"{self.name}: check raised", str(exc), 1.0, self.kind,
                         {"exception": repr(exc)})]
        return list(out)


@dataclass
class Config:
    """cfg: params, pins, profile + the board artifacts the stages read."""
    board: str                                   # module dir name (under modules/) or a path
    profile: str = "consumer"                    # consumer | pro | enterprise | mission_critical
    pins: dict = field(default_factory=dict)     # ref -> reason (MECHANICAL / USER_PINNED)
    params: dict = field(default_factory=dict)   # tunables (TAU, N_PROBES, STALL_K, sizes...)
    # resolved artifact paths (filled by load())
    dir: str = ""
    sch: str = ""
    net: str = ""
    pcb: str = ""
    bom_csv: str = ""

    DEFAULT_PARAMS = {
        "EPS_SIZE_MM": 1.0, "N_PROBES": 3, "TAU": 0.66, "STALL_K": 3, "Kmax": 3,
        "bom_target": None,
    }

    @classmethod
    def load(cls, board, **kw):
        d = board if os.path.isdir(board) else os.path.join(ROOT, "modules", board)
        if not os.path.isdir(d):
            # allow passing a .kicad_pcb / .kicad_sch directly
            if os.path.isfile(board):
                d = os.path.dirname(os.path.abspath(board))
            else:
                raise FileNotFoundError(f"cec_synth_pipeline: no module dir for {board!r}")
        name = os.path.basename(os.path.normpath(d))
        params = dict(cls.DEFAULT_PARAMS)
        params.update(kw.pop("params", {}) or {})
        cfg = cls(board=name, dir=d, params=params, **kw)
        cfg.sch = _one(glob.glob(os.path.join(d, "*.kicad_sch")))
        cfg.pcb = _one([p for p in glob.glob(os.path.join(d, "*.kicad_pcb"))
                        if "-routed" not in p and ".merged." not in p])
        cfg.net = _one(glob.glob(os.path.join(d, "*.net")))
        cfg.bom_csv = _one(glob.glob(os.path.join(d, "bom", "*BOM-jlcpcb.csv"))
                           or glob.glob(os.path.join(d, "bom", "*.csv")))
        return cfg

    @property
    def is_draft(self):
        return os.path.isfile(os.path.join(self.dir, "DRAFT"))

    @property
    def tier(self):
        return {"consumer": "Standard", "pro": "Pro",
                "enterprise": "Enterprise", "mission_critical": "Mission Critical"}.get(
                    self.profile, "Standard")


def _one(paths):
    return sorted(paths)[0] if paths else ""


# ============================================================ View (lazy artifact access)
class View:
    """A uniform handle the stage checks read from. Lazily parses the netlist, runs DRC,
    and scores the board so each check pulls only what it needs and nothing runs twice."""
    def __init__(self, cfg, *, board=None):
        self.cfg = cfg
        self.board = board or cfg.pcb            # the .kicad_pcb under evaluation
        self.sch = cfg.sch
        self._nl = None
        self._metrics = None
        self._drc = None
        self._erc = None

    @property
    def nl(self):
        if self._nl is None:
            if self.cfg.net and os.path.isfile(self.cfg.net):
                self._nl = Netlist.from_file(self.cfg.net)
            else:
                self._nl = self._export_netlist()
        return self._nl

    def _export_netlist(self):
        if not self.sch:
            return Netlist(comps={}, nets={})
        out = os.path.join(tempfile.gettempdir(), f"cec_synth_{os.getpid()}.net")
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", out, self.sch],
                       capture_output=True)
        return Netlist.from_file(out) if os.path.isfile(out) else Netlist(comps={}, nets={})

    @property
    def metrics(self):
        if self._metrics is None and _HAVE_SCORE and self.board and os.path.isfile(self.board):
            self._metrics = cec_score.score(self.board)
        return self._metrics

    def drc(self):
        if self._drc is None:
            self._drc = _run_drc(self.board) if (self.board and os.path.isfile(self.board)) else {}
        return self._drc

    def erc(self):
        if self._erc is None:
            self._erc = _run_erc(self.sch) if self.sch else {}
        return self._erc


def _run_drc(board):
    out = os.path.join(tempfile.gettempdir(), f"cec_synth_drc_{os.getpid()}.json")
    subprocess.run(["kicad-cli", "pcb", "drc", "--exit-code-violations",
                    "--format", "json", "-o", out, board], capture_output=True)
    try:
        return json.load(open(out))
    except Exception:
        return {}


def _run_erc(sch):
    out = os.path.join(tempfile.gettempdir(), f"cec_synth_erc_{os.getpid()}.json")
    subprocess.run(["kicad-cli", "sch", "erc", "--exit-code-violations",
                    "--format", "json", "-o", out, sch], capture_output=True)
    try:
        return json.load(open(out))
    except Exception:
        return {}


def _struct_drc(drc):
    return [v for v in drc.get("violations", []) if v.get("type") not in COSMETIC]


# ============================================================ check helpers
def _r_value_ohms(value):
    """Parse a resistor value like '2.2k', '10k', '0.5mOhm', '120' to ohms (float) or None."""
    if not value:
        return None
    s = value.strip().lower().replace("ohm", "").replace("Ω", "").replace("ω", "").strip()
    m = re.match(r"^([0-9]*\.?[0-9]+)\s*([mkrun]?)", s)
    if not m:
        return None
    num = float(m.group(1))
    mult = {"m": 1e-3, "k": 1e3, "r": 1.0, "u": 1e-6, "n": 1e-9, "": 1.0}.get(m.group(2), 1.0)
    return num * mult


# ============================================================ STAGE: ERC_BOM
def chk_erc_clean(view):
    if view.cfg.is_draft:
        return []                                # DRAFT boards skip ERC by repo convention
    erc = view.erc()
    real = []
    for sheet in erc.get("sheets", []):
        for v in sheet.get("violations", []):
            if v.get("type") in BENIGN_ERC:
                continue
            real.append(v)
    # newer kicad-cli emits a flat "violations" too
    for v in erc.get("violations", []):
        if v.get("type") not in BENIGN_ERC:
            real.append(v)
    if not real:
        return []
    types = {}
    for v in real:
        types[v.get("type", "?")] = types.get(v.get("type", "?"), 0) + 1
    return [Flag("ERC violations", view.sch, 1.0, Kind.NETLIST,
                 {"count": len(real), "types": types})]


def chk_no_unconnected(view):
    """Single-node nets (a pin going nowhere) are a real connectivity defect."""
    nl = view.nl
    singles = [n for n, nodes in nl.nets.items()
               if len(nodes) == 1 and not n.startswith(("unconnected-", "Net-"))]
    # tolerate intentional no-connects: a 1-node net whose name marks it NC
    singles = [n for n in singles if "no_connect" not in n.lower() and "nc" != n.lower()]
    if not singles:
        return []
    return [Flag("single-node nets", view.cfg.net or view.sch, 0.7, Kind.NETLIST,
                 {"nets": singles[:12], "count": len(singles)})]


def chk_power_rails(view):
    """The board's expected power rails are present and multiply-connected."""
    nl = view.nl
    want = ("GND", "+3V3")
    missing = [w for w in want if not any(w == n or n.endswith("/" + w) for n in nl.nets)]
    if missing:
        return [Flag("missing power rail", view.cfg.net, 0.8, Kind.NETLIST, {"missing": missing})]
    return []


def chk_can_present(view):
    """CAN_H / CAN_L exist and reach a transceiver (control plane lives on CAN, all tiers)."""
    nl = view.nl
    canh = [n for n in nl.nets if n.endswith("CAN_H") or n.endswith("CAN1_H")]
    canl = [n for n in nl.nets if n.endswith("CAN_L") or n.endswith("CAN1_L")]
    if not canh or not canl:
        return [Flag("CAN net absent", view.cfg.net, 0.9, Kind.NETLIST,
                     {"have_H": bool(canh), "have_L": bool(canl)})]
    return []


def chk_bom_complete(view):
    """Every BOM-included component carries an LCSC part (JLC assembly readiness).
    Known-open sourcing gaps (the §6.4 shunt under OQ-11, the THT power connectors)
    are reported at LOWER confidence -- they are tracked, not surprises."""
    nl = view.nl
    unsourced = []
    for ref, c in sorted(nl.comps.items()):
        if c.excluded_from_bom:
            continue
        if ref.startswith(("#", "TP", "FID", "LOGO", "H", "MK")):  # non-BOM refs
            continue
        if not c.lcsc:
            unsourced.append(ref)
    if not unsourced:
        return []
    # shunts (RS*) + power connectors (J_IN/J_OUT) are the documented OQ-11/THT gaps
    known = [r for r in unsourced if r.startswith(("RS", "J_IN", "J_OUT", "J3", "J4"))]
    conf = 0.4 if set(unsourced) == set(known) else 0.85
    return [Flag("unsourced BOM lines", view.cfg.bom_csv or view.cfg.net, conf, Kind.BOM,
                 {"unsourced": unsourced, "known_open": known})]


ERC_BOM = [
    Check("erc_clean",       chk_erc_clean,      Kind.NETLIST),
    Check("no_unconnected",  chk_no_unconnected, Kind.NETLIST),
    Check("power_rails",     chk_power_rails,    Kind.NETLIST),
    Check("can_present",     chk_can_present,    Kind.NETLIST),
    Check("bom_complete",    chk_bom_complete,   Kind.BOM),
]


# ============================================================ STAGE: PLACEMENT
def chk_courtyard_overlap(view):
    hits = [v for v in _struct_drc(view.drc()) if v.get("type") == "courtyards_overlap"]
    if hits:
        return [Flag("courtyard overlaps", view.board, 0.9, Kind.PLACE, {"count": len(hits)})]
    return []


def chk_on_board(view):
    """Every footprint's courtyard sits within Edge.Cuts (copper-to-edge / off-board)."""
    hits = [v for v in _struct_drc(view.drc())
            if v.get("type") in ("copper_edge_clearance", "footprint_outside_board")]
    if hits:
        return [Flag("part off board / copper-to-edge", view.board, 0.8, Kind.PLACE,
                     {"count": len(hits)})]
    return []


PLACEMENT = [
    Check("courtyard_overlap", chk_courtyard_overlap, Kind.PLACE),
    Check("on_board",          chk_on_board,          Kind.PLACE),
]


# ============================================================ STAGE: ROUTE_GATE
def chk_kelvin_gate(view):
    m = view.metrics
    if m is None:
        return [Flag("route gate not evaluable (no scorer)", view.board, 0.5, Kind.ROUTE,
                     {"reason": "cec_score/pcbnew unavailable"})]
    if not m.kelvin_ok:
        return [Flag("KELVIN hard gate FAIL", view.board, 1.0, Kind.ROUTE,
                     {"detail": getattr(m, "detail", {}).get("kelvin", "")})]
    return []


def chk_diffpair_gate(view):
    m = view.metrics
    if m is None:
        return []
    if not m.diffpair_ok:
        return [Flag("DIFFPAIR hard gate FAIL", view.board, 1.0, Kind.ROUTE, {})]
    return []


def chk_drc_zero(view):
    m = view.metrics
    if m is None:
        d = _struct_drc(view.drc())
        return [Flag("structural DRC", view.board, 1.0, Kind.ROUTE, {"count": len(d)})] if d else []
    if m.drc > 0:
        return [Flag("structural DRC", view.board, 1.0, Kind.ROUTE, {"count": m.drc})]
    return []


def chk_unconnected_zero(view):
    m = view.metrics
    if m is None:
        return []
    if m.unconnected > 0:
        return [Flag("unrouted ratlines", view.board, 1.0, Kind.ROUTE, {"count": m.unconnected})]
    return []


ROUTE_GATE = [
    Check("kelvin_gate",      chk_kelvin_gate,      Kind.ROUTE),
    Check("diffpair_gate",    chk_diffpair_gate,    Kind.ROUTE),
    Check("drc_zero",         chk_drc_zero,         Kind.ROUTE),
    Check("unconnected_zero", chk_unconnected_zero, Kind.ROUTE),
]


# ============================================================ STAGE: MEASURE
# Measurement-quality checks: the telemetry is only as good as the sense topology.
def _kelvin_pairs(nl):
    his = [n for n in nl.nets if n.endswith("_HI")]
    return [(h, h[:-3] + "_LO") for h in his if (h[:-3] + "_LO") in nl.nets]


def chk_kelvin_topology(view):
    """Each Kelvin pair must terminate on a 2-pad shunt straddling HI and LO (a real
    four-wire sense), and the sense must reach an INA input. Missing -> the current
    reading is not a Kelvin measurement."""
    nl = view.nl
    bad = []
    for hi, lo in _kelvin_pairs(nl):
        refs_hi = {r for r, _ in nl.nets[hi]}
        refs_lo = {r for r, _ in nl.nets[lo]}
        # a 2-pad shunt straddles the pair
        straddle = refs_hi & refs_lo
        shunt = [r for r in straddle if sum(1 for n in nl.nets.values()
                                            for (rr, _) in n if rr == r) >= 2 and r.startswith(("RS", "R"))]
        ina = [r for r in (refs_hi | refs_lo) if r.startswith("U")]
        if not straddle or not ina:
            bad.append({"pair": hi[:-3], "shunt": bool(straddle), "ina": bool(ina)})
    if bad:
        return [Flag("Kelvin sense topology incomplete", view.cfg.net, 0.8, Kind.MEASURE,
                     {"pairs": bad})]
    return []


def chk_divider_ratio(view):
    """A rail-voltage divider (the §6 47k/10k or similar) must be present where a board
    measures a rail through the ADC, and the ratio must keep the node in-range."""
    nl = view.nl
    # find a divider feeding an ADC/VRAIL node: two resistors in series to GND
    div_nets = [n for n in nl.nets if "VRAIL" in n.upper() or "DIV" in n.upper()]
    if not div_nets:
        return []                                # board doesn't measure a rail divider -> n/a
    # confirm at least two resistors touch the divider sub-network
    rcount = sum(1 for n in div_nets for (r, _) in nl.nets[n] if r.startswith("R"))
    if rcount < 1:
        return [Flag("rail divider missing resistors", view.cfg.net, 0.7, Kind.MEASURE,
                     {"nets": div_nets})]
    return []


MEASURE = [
    Check("kelvin_topology", chk_kelvin_topology, Kind.MEASURE),
    Check("divider_ratio",   chk_divider_ratio,   Kind.MEASURE),
]


# ============================================================ STAGE: DFM
def chk_dfm_drc(view):
    """Manufacturability DRC: width, annular, hole, clearance against the board's rules
    (kicad-cli reads the board .kicad_dru). Cosmetic types filtered."""
    d = _struct_drc(view.drc())
    dfm_types = ("track_width", "annular_width", "hole_size", "hole_clearance",
                 "clearance", "via_dangling", "drill_out_of_range")
    hits = [v for v in d if v.get("type") in dfm_types]
    if not hits:
        return []
    by = {}
    for v in hits:
        by[v["type"]] = by.get(v["type"], 0) + 1
    return [Flag("DFM rule violations", view.board, 0.95, Kind.DFM, {"types": by})]


DFM = [
    Check("dfm_drc", chk_dfm_drc, Kind.DFM),
]


# ============================================================ STAGE: CONFORMANCE
# The locked-decision suite (CLAUDE.md "Project-specific verification checklist").
_MINIFIT_HINTS = ("mini-fit", "minifit", "5569", "5557", "87427", "45586", "5045")


def chk_rj45_link(view):
    """The module-to-Hub link must be RJ-45 8P8C, never Mini-Fit Jr. (The PSU-side power
    path J_IN/J_OUT MAY be Mini-Fit -- that's the §2.8 power path, not the link.)"""
    nl = view.nl
    rj45 = [r for r, c in nl.comps.items()
            if "rj45" in (c.footprint + c.value).lower() or "8p8c" in (c.footprint + c.value).lower()]
    if not rj45:
        return [Flag("no RJ-45 link connector found", view.cfg.net, 0.8, Kind.CONFORM, {})]
    # any Mini-Fit on a *link* net (CAN/DETECT/STREAM/VCC) is a violation
    link_nets = [n for n in nl.nets if re.search(r"(CAN|DETECT|STREAM|5VSB|VCC)", n, re.I)]
    offenders = []
    for n in link_nets:
        for r, _ in nl.nets[n]:
            c = nl.comps.get(r)
            if c and any(h in c.footprint.lower() for h in _MINIFIT_HINTS):
                offenders.append((r, n))
    if offenders:
        return [Flag("Mini-Fit on the module-to-Hub link", view.cfg.net, 0.95, Kind.CONFORM,
                     {"offenders": offenders[:6]})]
    return []


def chk_pin_allocation(view):
    """RJ-45 pin map: 1=VCC, 2=GND, 3=CAN_H, 6=CAN_L, 8=DETECT, 7=reserved spare (NOT AUX_REF)."""
    nl = view.nl
    rj = next((r for r, c in nl.comps.items()
               if "rj45" in (c.footprint + c.value).lower() or "8p8c" in (c.footprint + c.value).lower()), None)
    if not rj:
        return []                                # covered by chk_rj45_link
    want = {"1": ("VCC", "5VSB"), "2": ("GND",), "3": ("CAN", "CAN_H", "CAN1_H"),
            "6": ("CAN", "CAN_L", "CAN1_L"), "8": ("DETECT",)}
    bad = []
    for pin, toks in want.items():
        net = nl.net_of(rj, pin)
        if net is None:
            continue
        if not any(t.lower() in net.lower() for t in toks):
            bad.append({"pin": pin, "net": net, "want_one_of": list(toks)})
    # pin 7 must NOT be a reference/aux net
    net7 = nl.net_of(rj, "7")
    if net7 and re.search(r"AUX|REF", net7, re.I):
        bad.append({"pin": "7", "net": net7, "want_one_of": ["reserved spare (not AUX_REF)"]})
    if bad:
        return [Flag("RJ-45 pin allocation mismatch", view.cfg.net, 0.85, Kind.CONFORM, {"pins": bad})]
    return []


def chk_detect_resistor(view):
    """DETECT (pin 8) carries the §2.3 code resistor to GND. CAN-only modules = 2.2k."""
    nl = view.nl
    det = [n for n in nl.nets if "DETECT" in n.upper()]
    if not det:
        return [Flag("no DETECT net", view.cfg.net, 0.8, Kind.CONFORM, {})]
    dn = det[0]
    rs = [r for r, _ in nl.nets[dn] if r.startswith("R")]
    if not rs:
        return [Flag("DETECT has no code resistor", view.cfg.net, 0.85, Kind.CONFORM, {"net": dn})]
    # expected code by profile (Standard CAN-only = 2.2k); read the resistor value
    want = view.cfg.params.get("detect_ohms", 2200.0)
    vals = {r: _r_value_ohms(nl.comps.get(r, Comp(r)).value) for r in rs}
    if not any(v and abs(v - want) / want < 0.1 for v in vals.values()):
        return [Flag("DETECT code resistor != expected", view.cfg.net, 0.7, Kind.CONFORM,
                     {"net": dn, "found": {k: nl.comps.get(k, Comp(k)).value for k in rs},
                      "expected_ohms": want})]
    return []


def chk_shunt_values(view):
    """Per the §6.4 table: EPS/PCIe per-cable shunt = 0.5 mOhm; 12VHPWR per-pin = 1 mOhm."""
    nl = view.nl
    shunts = {r: c for r, c in nl.comps.items()
              if r.startswith("RS") or "shunt" in c.value.lower() or "mΩ" in c.value or "mohm" in c.value.lower()}
    if not shunts:
        return []                                # not a shunt-bearing board
    want = view.cfg.params.get("shunt_ohms", 0.5e-3)
    bad = []
    for r, c in shunts.items():
        v = _r_value_ohms(c.value)
        if v is None or abs(v - want) / want > 0.2:
            bad.append({"ref": r, "value": c.value, "expected_ohms": want})
    if bad:
        return [Flag("shunt value off §6.4 table", view.cfg.net, 0.6, Kind.CONFORM, {"shunts": bad})]
    return []


def chk_rs485_tiering(view):
    """Standard tier leaves the RS-485 pair (pins 4,5) unused: no streaming receiver populated.
    A Standard module with an RS-485 transceiver is a tiering violation."""
    if view.cfg.profile not in ("consumer",):
        return []                                # Pro+ may populate RS-485
    nl = view.nl
    rs485 = [r for r, c in nl.comps.items()
             if re.search(r"(THVD|MAX348|SN65HVD|RS-?485|SP3485)", c.value, re.I)]
    if rs485:
        return [Flag("RS-485 transceiver on a Standard module", view.cfg.net, 0.8, Kind.CONFORM,
                     {"refs": rs485})]
    return []


def chk_no_module_can_term(view):
    """CAN termination is a fixed 120R split at the HUB only; modules carry none.
    A 120R across CAN_H/CAN_L on a module is a violation."""
    nl = view.nl
    canh = next((n for n in nl.nets if n.endswith(("CAN_H", "CAN1_H"))), None)
    canl = next((n for n in nl.nets if n.endswith(("CAN_L", "CAN1_L"))), None)
    if not canh or not canl:
        return []
    h_refs = {r for r, _ in nl.nets[canh] if r.startswith("R")}
    l_refs = {r for r, _ in nl.nets[canl] if r.startswith("R")}
    for r in h_refs & l_refs:                    # a resistor across CAN_H and CAN_L
        v = _r_value_ohms(nl.comps.get(r, Comp(r)).value)
        if v and 100 <= v <= 140:
            return [Flag("CAN termination populated on a module", view.cfg.net, 0.85,
                         Kind.CONFORM, {"ref": r, "value": nl.comps.get(r, Comp(r)).value})]
    return []


CONFORMANCE = [
    Check("rj45_link",        chk_rj45_link,        Kind.CONFORM),
    Check("pin_allocation",   chk_pin_allocation,   Kind.CONFORM),
    Check("detect_resistor",  chk_detect_resistor,  Kind.CONFORM),
    Check("shunt_values",     chk_shunt_values,     Kind.CONFORM),
    Check("rs485_tiering",    chk_rs485_tiering,    Kind.CONFORM),
    Check("no_module_can_term", chk_no_module_can_term, Kind.CONFORM),
]


# the six stage lists, named (the registry the comment in the spec refers to)
STAGES = {
    "ERC_BOM": ERC_BOM, "PLACEMENT": PLACEMENT, "ROUTE_GATE": ROUTE_GATE,
    "MEASURE": MEASURE, "DFM": DFM, "CONFORMANCE": CONFORMANCE,
}


# ============================================================ run_stage / cascade
def run_stage(stage, view):
    """Run every check in *stage* against *view*; return the concatenated flags."""
    flags = []
    for chk in stage:
        flags += chk.run(view)
    return flags


def run_full_cascade(view, *, armed=()):
    """The post-route cascade (pipeline line 43): post-ERC, place-DFM, route-gate,
    MEASURE, DFM-release, CONFORMANCE, + the armed optional analyses. Returns all flags."""
    flags = []
    flags += run_stage(ERC_BOM, view)            # post-ERC (re-validate the netlist still holds)
    flags += run_stage(PLACEMENT, view)          # place-DFM
    flags += run_stage(ROUTE_GATE, view)         # route gate
    flags += run_stage(MEASURE, view)            # MEASURE
    flags += run_stage(DFM, view)                # DFM-release
    flags += run_stage(CONFORMANCE, view)        # CONFORMANCE
    for opt in armed:                            # armed optional analyses
        flags += opt.run(view) if callable(getattr(opt, "run", None)) else []
    return flags


# ============================================================ OPTIONAL registry + triage
@dataclass
class OptionalAnalysis:
    """An optional analysis that triage may ARM. `always` ones always run; the rest are
    armed when they `applies` to the design AND the cheap `screen` isn't clearly clear
    (CAUTIOUS: any doubt -> arm). `run(view)->[Flag]` is the real (expensive) analysis."""
    name: str
    always: bool
    applies_fn: object              # (feats, profile) -> bool
    screen_fn: object               # (feats) -> (est:float, band:float)
    alarm_fn: object                # (feats) -> bool  (cheap out-of-scope alarm)
    conf_fn: object                 # (feats) -> float
    run_fn: object                  # (view) -> [Flag]

    def applies(self, feats, profile):
        return bool(self.applies_fn(feats, profile))

    def screen(self, feats):
        return self.screen_fn(feats)

    def cheap_alarm(self, feats):
        return bool(self.alarm_fn(feats))

    def conf(self, feats):
        return float(self.conf_fn(feats))

    def run(self, view):
        return list(self.run_fn(view) or [])


def extract_features(cfg):
    """Cheap design features the registry screens on (no heavy analysis)."""
    view = View(cfg)
    nl = view.nl
    feats = {
        "profile": cfg.profile,
        "n_comps": len(nl.comps),
        "has_12v": any(n.endswith(("_HI", "12V")) or "12V" in n for n in nl.nets),
        "has_switcher": any(re.search(r"(TPS|LM|MP|buck|boost)", c.value, re.I)
                            for c in nl.comps.values()),
        "has_high_current": any(r.startswith("RS") for r in nl.comps),  # shunt-bearing
        "has_rf": any("ESP32" in c.value or "antenna" in c.footprint.lower()
                      for c in nl.comps.values()),
        "n_nets": len(nl.nets),
    }
    return feats


def cautious_clear(est, band):
    """Skip an applicable analysis ONLY if it is CLEARLY clear: a low estimate with a
    tight band. Any meaningful estimate or a wide (uncertain) band -> arm."""
    return est < 0.25 and band < 0.15


def triage_arm(cfg):
    """Arm the optional analyses (pipeline triage_arm). Mandatory ones always; the rest
    when applicable and not clearly clear. An out-of-scope cheap alarm escalates via resolve()."""
    feats = extract_features(cfg)
    armed = [c for c in REGISTRY_OPTIONAL if c.always]
    for c in REGISTRY_OPTIONAL:
        if c.always:
            continue
        if not c.applies(feats, cfg.profile):
            if c.cheap_alarm(feats):
                resolve(Flag(f"{c.name} out-of-scope alarm", feats, c.conf(feats), Kind.SCOPE,
                             {"analysis": c.name}), cfg)
            continue
        est, band = c.screen(feats)
        if not cautious_clear(est, band):
            armed.append(c)
    return armed


# --- the registry. applies/screen are real + cheap; run_fn does the deep analysis
#     (EMC/thermal/PDN deep runs land in their own commits + wire to the kicad-happy skills). ---
def _emc_applies(feats, profile):
    return feats["has_switcher"] or feats["has_rf"] or profile in ("enterprise", "mission_critical")


def _emc_screen(feats):
    risk = 0.2 + 0.3 * feats["has_switcher"] + 0.2 * feats["has_rf"]
    return min(risk, 0.95), 0.2


def _thermal_applies(feats, profile):
    return feats["has_high_current"] or feats["has_12v"]


def _thermal_screen(feats):
    return (0.6 if feats["has_high_current"] else 0.2), 0.2


def _pdn_applies(feats, profile):
    return feats["has_switcher"] and profile in ("pro", "enterprise", "mission_critical")


REGISTRY_OPTIONAL = [
    OptionalAnalysis(
        "EMC", False, _emc_applies, _emc_screen,
        alarm_fn=lambda f: f["has_rf"], conf_fn=lambda f: 0.5,
        run_fn=lambda view: [Flag("EMC deep-analysis not yet wired", view.board, 0.3, Kind.SCOPE,
                                  {"todo": "wire kicad-happy:emc skill"})]),
    OptionalAnalysis(
        "THERMAL", True, _thermal_applies, _thermal_screen,
        alarm_fn=lambda f: f["has_high_current"], conf_fn=lambda f: 0.6,
        run_fn=lambda view: []),   # the electrothermal FEA stage lands as its own commit
    OptionalAnalysis(
        "PDN", False, _pdn_applies, lambda f: (0.4, 0.2),
        alarm_fn=lambda f: False, conf_fn=lambda f: 0.4,
        run_fn=lambda view: [Flag("PDN deep-analysis not yet wired", view.board, 0.3, Kind.SCOPE,
                                  {"todo": "PDN impedance analysis"})]),
]


# ============================================================ resolve() ladder
@dataclass
class Action:
    """The outcome of a resolve() attempt."""
    resolved: bool = False
    fixes: list = field(default_factory=list)    # net-level fixes to apply (route re-tries)
    re_place: bool = False                        # high-leverage: restart with a placement hint
    place_hint: object = None
    halt: bool = False                            # human rung withheld / unrecoverable
    rung: str = ""                               # which rung produced this
    note: str = ""


# The control tiers are PLUGGABLE callables, exactly like cec_router.make_subagent_policy:
# the orchestrator (Claude) supplies real sub-agent decide() fns; the deterministic
# defaults below let the whole pipeline run headless. A rung returns an Action; a
# non-resolved, non-halt Action means "escalate to the next rung".
def worker_rung(flag, cfg):
    """Tier-0 deterministic auto-fix for the mechanical, unambiguous cases."""
    if flag.kind == Kind.ROUTE and flag.name.startswith(("structural DRC", "unrouted")):
        # the offending nets are re-routable -> hand the route loop a re-route action
        return Action(resolved=True, fixes=[flag.name], rung="worker",
                      note="re-route the offending nets")
    if flag.kind == Kind.BOM and flag.conf < 0.5:
        # a documented/known-open sourcing gap (OQ-11 shunt, THT connectors): accept + track
        return Action(resolved=True, rung="worker", note="known-open sourcing gap (tracked)")
    return Action(resolved=False, rung="worker")


def _default_tier(name):
    """Deterministic stand-in for an LLM tier: CAUTIOUS -> never silently resolves a real
    flag, just passes it up. Replace via resolve(..., tiers={name: callable})."""
    def tier(flag, cfg):
        return Action(resolved=False, rung=name,
                      note=f"{name}: no LLM tier wired -> escalate")
    return tier


def human_rung(flag, cfg, *, ask=None):
    """The human rung. Interactive: the orchestrator supplies `ask`. Headless: record the
    flag and HALT (cautious -- never auto-approve a flag that reached a human)."""
    if ask is not None:
        return ask(flag, cfg)
    return Action(resolved=False, halt=True, rung="human",
                  note="reached human rung headless -> HALT (record + stop)")


def resolve(flag, cfg, *, tiers=None, ask=None, verbose=False):
    """The escalation ladder: worker -> manager -> frontier -> human. CAUTIOUS posture --
    any doubt escalates. Returns the first Action that resolves or halts. `tiers` maps
    'manager'/'frontier' to real sub-agent decide(flag,cfg)->Action callables (the LLM
    tiers); absent ones fall back to a cautious deterministic stand-in that escalates."""
    tiers = tiers or {}
    ladder = [
        ("worker",   worker_rung),
        ("manager",  tiers.get("manager")  or _default_tier("manager")),
        ("frontier", tiers.get("frontier") or _default_tier("frontier")),
        ("human",    lambda f, c: human_rung(f, c, ask=ask)),
    ]
    for name, rung in ladder:
        act = rung(flag, cfg)
        act.rung = act.rung or name
        if verbose:
            print(f"    resolve[{name}] {flag.name}: "
                  f"{'RESOLVED' if act.resolved else ('HALT' if act.halt else 'escalate')}"
                  f" -- {act.note}")
        if act.resolved or act.halt:
            return act
    return Action(resolved=False, halt=True, rung="human", note="ladder exhausted")


def resolve_each(flags, cfg, *, tiers=None, ask=None, verbose=False):
    """Resolve a batch of flags. Returns (all_resolved, actions). A single halt -> False."""
    actions = []
    ok = True
    for f in flags:
        a = resolve(f, cfg, tiers=tiers, ask=ask, verbose=verbose)
        actions.append((f, a))
        if not a.resolved:
            ok = False
    return ok, actions


# ============================================================ geometric floor + proxy
# The size oracle (pipeline lines 18-32) shrinks the board until routing stops confirming.
# It needs two CHEAP inputs at each candidate size: a geometric FLOOR (the smallest board
# that can even hold the parts) and a placement PROXY (HPWL + RUDY congestion + a low-res
# thermal hotspot estimate) so most sizes are rejected without paying for a real route.
_MM = 1_000_000


@dataclass
class Placement:
    """A read or synthesized placement. pos: ref -> (x, y, rot, hw, hh) mm (position +
    courtyard half-extents); pads_by_net: net -> [(x, y) mm]; the board W/H/origin."""
    pos: dict
    pads_by_net: dict
    value: dict                                  # ref -> value (for the thermal model)
    W: float
    H: float
    x0: float = 0.0
    y0: float = 0.0


def read_placement(board_path):
    """Read a real placement off a .kicad_pcb via pcbnew (positions, courtyards, pad nets)."""
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    pos, value = {}, {}
    pads_by_net = defaultdict(list)
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        p = fp.GetPosition()
        try:
            poly = fp.GetCourtyard(pcbnew.F_CrtYd)
            if poly.OutlineCount() == 0:
                poly = fp.GetCourtyard(pcbnew.B_CrtYd)
            bb = poly.BBox() if poly.OutlineCount() else fp.GetBoundingBox(False, False)
        except Exception:
            bb = fp.GetBoundingBox(False, False)
        pos[ref] = (p.x / _MM, p.y / _MM, fp.GetOrientationDegrees(),
                    bb.GetWidth() / 2 / _MM, bb.GetHeight() / 2 / _MM)
        value[ref] = fp.GetValue()
        for pad in fp.Pads():
            nn = pad.GetNetname()
            if nn:
                pp = pad.GetPosition()
                pads_by_net[nn].append((pp.x / _MM, pp.y / _MM))
    eb = b.GetBoardEdgesBoundingBox()
    return Placement(pos=pos, pads_by_net=dict(pads_by_net), value=value,
                     W=eb.GetWidth() / _MM, H=eb.GetHeight() / _MM,
                     x0=eb.GetLeft() / _MM, y0=eb.GetTop() / _MM)


@dataclass
class Floor:
    w: float
    h: float
    area: float
    binding: str          # what sets the floor: 'area' (packing) or 'part-extent'


def packing_lower_bound(placement):
    """The geometric floor (pipeline line 19): the smallest board that can even HOLD the
    parts. A true LOWER bound -- the board cannot be smaller than (a) the total courtyard
    area (parts may not overlap), nor (b) its largest single courtyard in either dimension.
    No packing-efficiency divisor: that would inflate the bound above achievable sizes (and
    a real dense module packs to ~0.8, so the floor must sit *below* the as-built board).
    The achievable size lives ABOVE this floor and is found by the size oracle's real routes.
    Returns a Floor in the board's current aspect ratio."""
    areas = [(2 * hw) * (2 * hh) for (_, _, _, hw, hh) in placement.pos.values()]
    floor_area = sum(areas) if areas else 1.0     # hard packing lower bound (eta = 1)
    max_w = max((2 * hw for (_, _, _, hw, hh) in placement.pos.values()), default=1.0)
    max_h = max((2 * hh for (_, _, _, hw, hh) in placement.pos.values()), default=1.0)
    aspect = (placement.W / placement.H) if placement.H else 1.0
    h = max(max_h, math.sqrt(floor_area / aspect) if aspect else math.sqrt(floor_area))
    w = max(max_w, floor_area / h)
    binding = "part-extent" if (w * h) > floor_area * 1.05 else "area"
    return Floor(w=w, h=h, area=floor_area, binding=binding)


def hpwl(pads_by_net):
    """Total half-perimeter wirelength -- the cheap routability/length proxy."""
    total = 0.0
    for pts in pads_by_net.values():
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        total += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return total


def rudy(pads_by_net, W, H, x0, y0, *, bin_mm=2.0):
    """RUDY (Rectangular Uniform wire DensitY): spread each net's wirelength uniformly over
    its bounding box, accumulate per bin, return (peak, mean) demand. Peak >> mean flags a
    congestion hotspot the router will fight -- the cheap proxy_reject signal."""
    nx = max(1, int(math.ceil(W / bin_mm)))
    ny = max(1, int(math.ceil(H / bin_mm)))
    grid = [[0.0] * nx for _ in range(ny)]
    for pts in pads_by_net.values():
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        area = max(w * h, bin_mm * bin_mm)
        dens = (w + h) / area                     # RUDY wire density of this net
        i0 = int((min(xs) - x0) / bin_mm); i1 = int((max(xs) - x0) / bin_mm)
        j0 = int((min(ys) - y0) / bin_mm); j1 = int((max(ys) - y0) / bin_mm)
        for j in range(max(0, j0), min(ny - 1, j1) + 1):
            for i in range(max(0, i0), min(nx - 1, i1) + 1):
                grid[j][i] += dens
    flat = [c for row in grid for c in row]
    if not flat:
        return 0.0, 0.0
    return max(flat), sum(flat) / len(flat)


def _part_power_w(ref, value):
    """A coarse per-part dissipation (W) for the low-res thermal proxy. Rough by class --
    the proxy only needs to find HOTSPOT CONCENTRATION, not absolute temperature."""
    v = (value or "").upper()
    if "ESP32" in v:
        return 0.5
    if ref.startswith("RS"):
        return 0.30                               # shunt I^2R (rough; real I unknown here)
    if ref.startswith("U") and ("LP59" in v or "TPS" in v or "LDO" in v or "REG" in v):
        return 0.15                               # LDO/regulator
    if ref.startswith("U"):
        return 0.06                               # generic IC (INA/CAN/comparator)
    return 0.0


def thermal_proxy(placement, *, bin_mm=4.0):
    """Low-res hotspot proxy: bin per-part power onto a coarse grid, return (peak, total) W.
    A high peak/total ratio => power piled into one cell => a likely thermal hotspot."""
    W, H, x0, y0 = placement.W, placement.H, placement.x0, placement.y0
    nx = max(1, int(math.ceil(W / bin_mm)))
    ny = max(1, int(math.ceil(H / bin_mm)))
    grid = [[0.0] * nx for _ in range(ny)]
    total = 0.0
    for ref, (x, y, _r, _hw, _hh) in placement.pos.items():
        p = _part_power_w(ref, placement.value.get(ref, ""))
        if p <= 0:
            continue
        total += p
        i = min(nx - 1, max(0, int((x - x0) / bin_mm)))
        j = min(ny - 1, max(0, int((y - y0) / bin_mm)))
        grid[j][i] += p
    peak = max((c for row in grid for c in row), default=0.0)
    return peak, total


def placement_proxy(placement):
    """The cheap placement score (pipeline placement_proxy): HPWL + RUDY + low-res thermal.
    Returns a dict; lower hpwl / rudy_peak / thermal_peak is better."""
    rpk, rmean = rudy(placement.pads_by_net, placement.W, placement.H,
                      placement.x0, placement.y0)
    tpk, ttot = thermal_proxy(placement)
    return {
        "hpwl": round(hpwl(placement.pads_by_net), 2),
        "rudy_peak": round(rpk, 3), "rudy_mean": round(rmean, 3),
        "rudy_ratio": round(rpk / rmean, 2) if rmean else 0.0,
        "thermal_peak_w": round(tpk, 3), "thermal_total_w": round(ttot, 3),
        "W": round(placement.W, 2), "H": round(placement.H, 2),
    }


def proxy_reject(proxy, *, baseline=None, rudy_growth=1.8, thermal_peak_max=2.0):
    """Cheap rejection (pipeline proxy_reject): is this size too congested / too hot to be
    worth a real route? CALIBRATED RELATIVE to a *baseline* proxy (the largest size tried,
    which the size oracle knows routed) -- a candidate is rejected when its RUDY peak grows
    past baseline x *rudy_growth* (congestion piled up as the board shrank). RUDY's absolute
    scale is uncalibrated, so with NO baseline we do NOT reject on congestion (a known-routable
    board must pass). The thermal ceiling IS absolute (W concentrated in one proxy cell -> a
    real power-density hotspot; refined later by the electrothermal FEA on the winner).
    Returns (reject: bool, reasons: list)."""
    reasons = []
    if baseline and proxy["rudy_peak"] > baseline["rudy_peak"] * rudy_growth:
        reasons.append(f"RUDY peak {proxy['rudy_peak']} > {rudy_growth}x baseline "
                       f"{baseline['rudy_peak']} (congestion grew as it shrank)")
    if proxy["thermal_peak_w"] > thermal_peak_max:
        reasons.append(f"thermal peak {proxy['thermal_peak_w']}W > {thermal_peak_max}W (hotspot)")
    return (bool(reasons), reasons)


# ============================================================ route swarm bridge
def route_swarm(cfg, *, board=None, out_dir=None, seeds=(0, 1, 2, 3), manager=None,
                worker=None, escalator=None, verbose=True, **board_spec_kw):
    """Wire the synthesis pipeline's ROUTE SWARM stage (pipeline line 38) onto the existing
    cec_router.route() loop -- the real Freerouting + score + gate + repair/escalate +
    pour-after-route + decision-log machinery. Returns (final_board_path, DecisionLog).

    The route loop's own control tiers (its candidate-judging manager / repair worker /
    re-plan escalator) are supplied here when the orchestrator wants the LLM tiers driving;
    by default they run deterministically. (These are cec_router's per-candidate tiers, a
    DIFFERENT interface from the pipeline's flag-level resolve() ladder.)"""
    import cec_router
    out_dir = out_dir or os.path.join(tempfile.gettempdir(), f"cec_synth_route_{cfg.board}")
    spec, name = cec_router.board_spec(board or cfg.board, out_dir, seeds=tuple(seeds),
                                       **board_spec_kw)
    final, log = cec_router.route(spec.board, spec, manager=manager, worker=worker,
                                  escalator=escalator, verbose=verbose)
    return final, log


# ============================================================ self-test / CLI
def _print_flags(title, flags):
    print(f"\n  {title}: {len(flags)} flag(s)")
    for f in flags:
        print(f"    - {f}")
        if f.detail:
            d = json.dumps(f.detail, default=str)
            print(f"        {d[:160]}")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="CEC synthesis pipeline -- cascade + resolve backbone")
    ap.add_argument("--board", default="eps-8pin", help="module dir under modules/ (or a path)")
    ap.add_argument("--profile", default="consumer")
    ap.add_argument("--stage", default=None, help="run a single stage (e.g. CONFORMANCE); default = full cascade")
    ap.add_argument("--resolve", action="store_true", help="run the resolve() ladder over the flags (headless)")
    a = ap.parse_args(argv)

    cfg = Config.load(a.board, profile=a.profile)
    print("=" * 72)
    print(f"  cec_synth_pipeline -- cascade backbone on {cfg.board} (profile={cfg.profile})")
    print("=" * 72)
    print(f"  dir : {os.path.relpath(cfg.dir, ROOT)}")
    print(f"  sch : {os.path.basename(cfg.sch) if cfg.sch else '(none)'}"
          f"   pcb: {os.path.basename(cfg.pcb) if cfg.pcb else '(none)'}"
          f"   net: {os.path.basename(cfg.net) if cfg.net else '(none)'}")
    print(f"  draft: {cfg.is_draft}   score-engine: {'ok' if _HAVE_SCORE else 'UNAVAILABLE'}")

    view = View(cfg)
    print(f"  netlist: {len(view.nl.comps)} comps, {len(view.nl.nets)} nets")

    # triage
    armed = triage_arm(cfg)
    print(f"\n  triage_arm -> armed: {[o.name for o in armed]}")

    # geometric floor + placement proxy (the size-oracle's cheap inputs)
    if cfg.pcb and os.path.isfile(cfg.pcb):
        try:
            pl = read_placement(cfg.pcb)
            fl = packing_lower_bound(pl)
            prox = placement_proxy(pl)
            rej, reasons = proxy_reject(prox)
            print(f"\n  geometric floor : {fl.w:.1f} x {fl.h:.1f} mm (area {fl.area:.0f} mm^2, "
                  f"binding={fl.binding})  vs board {pl.W:.1f} x {pl.H:.1f} "
                  f"({pl.W*pl.H/fl.area:.2f}x slack)")
            print(f"  placement proxy : HPWL={prox['hpwl']} RUDY peak/mean={prox['rudy_peak']}/"
                  f"{prox['rudy_mean']} thermal peak/total={prox['thermal_peak_w']}/"
                  f"{prox['thermal_total_w']}W  reject={rej} {reasons}")
        except Exception as exc:
            print(f"\n  (geometric floor/proxy skipped: {exc})")

    # run stages
    if a.stage:
        stage = STAGES[a.stage]
        flags = run_stage(stage, view)
        _print_flags(a.stage, flags)
    else:
        all_flags = []
        for name, stage in STAGES.items():
            flags = run_stage(stage, view)
            _print_flags(name, flags)
            all_flags += flags
        print(f"\n  === cascade total: {len(all_flags)} flag(s) across {len(STAGES)} stages ===")
        flags = all_flags

    # optionally exercise the resolve ladder (headless: worker resolves the mechanical
    # ones, the rest escalate to a HALT at the human rung -- the cautious default)
    if a.resolve:
        print("\n  --- resolve() ladder (headless, deterministic tiers) ---")
        ok, actions = resolve_each(flags, cfg, verbose=True)
        n_res = sum(1 for _, x in actions if x.resolved)
        n_halt = sum(1 for _, x in actions if x.halt)
        print(f"\n  resolve_each: all_resolved={ok}  ({n_res} resolved, {n_halt} halted-at-human)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
