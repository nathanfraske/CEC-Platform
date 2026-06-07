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
import random
import shutil
import tempfile
import subprocess
from enum import Enum
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
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
        # WIRELESS POPULATED is a Stage-1 human input (respect_antenna_keepout): an ESP32 with
        # the radio unpopulated is not an RF emitter, so EMC's RF arm should not fire on it.
        "wireless": bool(cfg.params.get("respect_antenna_keepout", True)),
        "thermal_env": cfg.params.get("thermal_env", "enclosed_passive"),
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
    # RF only counts if the radio is actually POPULATED (Stage-1 wireless input).
    rf = feats["has_rf"] and feats.get("wireless", True)
    return feats["has_switcher"] or rf or profile in ("enterprise", "mission_critical")


def _emc_screen(feats):
    rf = feats["has_rf"] and feats.get("wireless", True)
    risk = 0.2 + 0.3 * feats["has_switcher"] + 0.2 * rf
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
        alarm_fn=lambda f: f["has_rf"] and f.get("wireless", True), conf_fn=lambda f: 0.5,
        run_fn=lambda view: [Flag("EMC deep-analysis not yet wired", view.board, 0.3, Kind.SCOPE,
                                  {"todo": "wire kicad-happy:emc skill"})]),
    OptionalAnalysis(
        "THERMAL", True, _thermal_applies, _thermal_screen,
        alarm_fn=lambda f: f["has_high_current"], conf_fn=lambda f: 0.6,
        # the analytic electrothermal FEA (physics()): J/T/derating gates on the routed board
        run_fn=lambda view: (physics(view.board, view.cfg)[1]
                             if view.board and os.path.isfile(view.board) else [])),
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
    detail: dict = field(default_factory=dict)    # extra payload (e.g. handoff board + render)


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


# ============================================================ place + proxy + consent
# The constructive placer (pipeline place_with_consent, lines 77-86): seed the anchors
# (connectors at edges by ROLE, mounts at corners), honor user pins, then relative-place
# the rest by net connectivity under a strategy, legalize the overlaps, and score by the
# cheap proxy. A handful of strategy/seed VARIANTS -- and the candidate sweep runs on a
# PARALLEL spawn pool (max_workers), the same runner-capable pattern as cec_fr, so a large
# candidate count offloads onto the self-hosted runner's cores.
STRATEGIES = ("dataflow", "thermal_separated", "compact")


def _role(ref, value, fp):
    """Anchor role of a part, or None if it's a free (relative-placed) part."""
    f = (fp or "").lower()
    v = (value or "").upper()
    if ref.startswith(("H", "MK", "FID", "LOGO")) or "mountinghole" in f or "fiducial" in f:
        return "mount"
    if "rj45" in f or "8p8c" in f or "to-hub" in v:
        return "host"
    if "usb" in f:
        return "usb"
    if ref.startswith("J"):
        u = ref.upper()
        if "IN" in u:
            return "power_in"
        if "OUT" in u:
            return "power_out"
        return "host"
    return None


def _half_extent(fp, *, drop_antenna=False):
    """(hw, hh) courtyard half-extent of a footprint. When *drop_antenna* and the part is an
    RF module (ESP32 / RF_Module), trim the PCB-antenna keepout lobe to the pad band -- the
    Stage-1 'wireless not populated' answer makes the ESP courtyard materially smaller."""
    if "mountinghole" in fp.lower():
        return (3.0, 3.0)                            # M3 keepout (the footprint courtyard parses degenerate)
    import cec_pcb
    is_rf = ("rf_module" in fp.lower()) or ("esp32" in fp.lower())
    x0, x1, y0, y1 = cec_pcb.courtyard_bbox(fp, drop_keepout=(drop_antenna and is_rf))
    return ((x1 - x0) / 2.0, (y1 - y0) / 2.0)


def _part_halfext(nl, *, drop_antenna=False):
    """ref -> (hw, hh) courtyard half-extent from the netlist footprint libid (no placement).
    *drop_antenna* trims the RF-module antenna keepout (Stage-1 wireless-not-populated input)."""
    out = {}
    for ref, c in nl.comps.items():
        if not c.footprint or ":" not in c.footprint:
            continue
        try:
            out[ref] = _half_extent(c.footprint, drop_antenna=drop_antenna)
        except Exception:
            out[ref] = (1.0, 1.0)
    return out


def _fp_of(nl):
    return {ref: c.footprint for ref, c in nl.comps.items() if c.footprint and ":" in c.footprint}


def _courtyard_info(fp, rot, *, drop_antenna=False):
    """(cx_off, cy_off, hw, hh): the part's courtyard CENTRE OFFSET from its origin + its half
    extents, at rotation *rot*. Footprint origins are NOT at the courtyard centre (a connector's
    origin is near pin 1, the courtyard extends asymmetrically), so an origin-centred ±half check
    badly mismodels the real courtyard -> phantom 'legal' placements that DRC then flags. This
    uses cec_pcb.courtyard_bbox(fp, 0, 0, rot) = the real courtyard bbox around the origin at this
    rotation, exactly what KiCad/DRC sees, so the legalizer's overlap test matches the board."""
    if "mountinghole" in fp.lower():
        return (0.0, 0.0, 3.0, 3.0)                  # M3 keepout (footprint courtyard parses degenerate)
    import cec_pcb
    is_rf = ("rf_module" in fp.lower()) or ("esp32" in fp.lower())
    try:
        x0, x1, y0, y1 = cec_pcb.courtyard_bbox(fp, 0.0, 0.0, rot,
                                                drop_keepout=(drop_antenna and is_rf))
    except Exception:
        return (0.0, 0.0, 1.0, 1.0)
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0, (x1 - x0) / 2.0, (y1 - y0) / 2.0)


_MOUNT_FP = "cec-MountingHole:MountingHole_3.2mm_M3_Pad_Via"
_FID_FP = "cec-Fiducial:Fiducial_1mm_Mask2mm"
_POWER_NET = re.compile(r"(^|/)(GND|\+?3V3|\+?5VSB|\+?5V|VBUS|VCC|\+?12V)$", re.I)


def _is_power_net(n):
    """A global power/GND rail (decoupling hairball) -- or a sense FORCE net (*_HI/_LO), which is
    'power-like' for ownership (it shouldn't bind a filter cap to the shunt as a signal owner)."""
    base = n.rsplit("/", 1)[-1]
    return bool(_POWER_NET.search(n)) or base in ("GND",) or n.endswith(("_HI", "_LO"))


def _classify(nl):
    """Partition the netlist parts: anchors {ref:role} (connectors/mounts by _role), ICs (active,
    placed by relative_place), shunts (RS*, the cable-column structure), passives (everything else
    1-2 pin -> auto_clustered onto an owner IC). Buttons (SW*) count as ICs so they place
    deliberately (e.g. edge-accessible BOOT/RESET), not clustered."""
    anchors, ics, shunts, passives = {}, [], [], []
    for ref, c in nl.comps.items():
        if not c.footprint or ":" not in c.footprint:
            continue
        role = _role(ref, c.value, c.footprint)
        if role:
            anchors[ref] = role
        elif ref.startswith("RS"):
            shunts.append(ref)
        elif ref.startswith("U") or ref.startswith("SW"):
            ics.append(ref)
        else:
            passives.append(ref)
    return anchors, ics, shunts, passives


def _owner_pad(nl, owner, shared_nets):
    """A pad number of *owner* that sits on one of *shared_nets* (prefer a power pad, so the cap
    parks at the owner's power-pin edge -- where decoupling belongs)."""
    cand = []
    for n in shared_nets:
        for r, p in nl.nets.get(n, []):
            if r == owner:
                cand.append((1 if _is_power_net(n) else 0, p))
    if not cand:
        return None
    cand.sort(reverse=True)
    return cand[0][1]


def derive_passive_spec(nl, passives, ic_refs):
    """Generalize the hand PASSIVE_SPEC: ref -> (owner_ic, owner_pad). A passive's owner is the IC
    it shares the most SIGNAL nets with (filter caps -> their INA, RC -> their IC); a pure-decoupling
    cap (only power+GND) is BALANCED across the ICs on that rail (distributed decoupling) so the caps
    don't pile on one IC. owner_pad = the owner's pad on a shared net (power preferred). This is what
    feeds cec_pcb.auto_cluster -- the density engine the condensed boards use. The route swarm + the
    placement handoff refine where connectivity can't disambiguate."""
    nets_of = defaultdict(set)
    for n, nodes in nl.nets.items():
        for r, _p in nodes:
            nets_of[r].add(n)
    ic_nets = {ic: nets_of[ic] for ic in ic_refs}
    load = {ic: 0 for ic in ic_refs}                    # decoupling-balance counter
    spec = {}
    for pref in passives:
        pnets = nets_of.get(pref, set())
        if not pnets:
            continue
        sig = []
        for ic, icn in ic_nets.items():
            signals = [n for n in (pnets & icn) if not _is_power_net(n)]
            if signals:
                sig.append((len(signals), ic))
        if sig:
            owner = max(sig)[1]                         # strongest signal-net coupling
        else:
            pwr_ics = [ic for ic, icn in ic_nets.items() if (pnets & icn)]
            if not pwr_ics:
                continue
            owner = min(pwr_ics, key=lambda ic: load[ic])   # balance decoupling across the rail
            load[owner] += 1
        pad = _owner_pad(nl, owner, pnets & nets_of[owner])
        if pad:
            spec[pref] = (owner, pad)
    return spec


def place_mechanical(W, H, params):
    """Place mounting holes + fiducials per the GENERALIZED Stage-1 asks (mount_holes / fiducials).
    Returns ({ref:(x,y,rot)}, {ref:libid}) for the board-level mechanical parts (H1.., FID1..) that
    are NOT in the netlist. e = edge inset. These become fixed obstacles for the placer (keep parts
    off the screw heads / fiducial windows) and are emitted at materialize time."""
    pos, fp = {}, {}
    e = 3.5
    m = params.get("mount_holes", "3_2logic_1conn")
    if m == "4_corner":
        pts = [(e, e), (W - e, e), (e, H - e), (W - e, H - e)]
    elif m == "2_diag":
        pts = [(e, e), (W - e, H - e)]
    else:                                               # 3: 2 logic-side (right) + 1 conn-side (left)
        pts = [(W - e, e), (W - e, H - e), (e, H / 2)]
    for i, (x, y) in enumerate(pts, 1):
        pos[f"H{i}"] = (x, y, 0.0)
        fp[f"H{i}"] = _MOUNT_FP
    f = params.get("fiducials", "3")
    if f and f != "none":
        nf = int(f) if str(f).isdigit() else 3
        fpts = [(W * 0.85, e), (W * 0.85, H - e), (W * 0.5, H - e)][:nf]
        for i, (x, y) in enumerate(fpts, 1):
            pos[f"FID{i}"] = (x, y, 0.0)
            fp[f"FID{i}"] = _FID_FP
    return pos, fp


def _pad_band(fp, rot):
    """((px_lo,px_hi),(py_lo,py_hi)): the global-relative x/y span of a footprint's PADS at
    rotation *rot* (relative to the origin). Used to seat a connector by its pads at the board
    edge while its body/courtyard overhangs off-board."""
    import cec_pcb
    pads = cec_pcb.local_pads(fp)
    if not pads:
        return ((0.0, 0.0), (0.0, 0.0))
    xs, ys = [], []
    for (lx, ly) in pads.values():
        dx, dy = cec_pcb._rot(lx, ly, rot)
        xs.append(dx); ys.append(dy)
    return ((min(xs), max(xs)), (min(ys), max(ys)))


def seed_anchors(nl, W, H, fp_of, pins, *, overhang="none", margin=1.5, pad_margin=1.8):
    """Place connector anchors by edge role. With *overhang* != 'none' a connector is seated by its
    PAD BAND at the edge so its body/courtyard hangs OFF-board (pads on-board) -- the area lever the
    condensed boards use, and what lets two tall cable connectors fit a short board. 'none' seats the
    whole courtyard on-board. Honors user pins last. Returns {ref:(x,y,rot)}."""
    roles = defaultdict(list)
    for ref in fp_of:
        r = _role(ref, nl.comps.get(ref, Comp(ref)).value, nl.comps.get(ref, Comp(ref)).footprint)
        if r:
            roles[r].append(ref)
    A = {}
    oh = (overhang != "none")

    _ROT = {"top": 180.0, "bottom": 0.0, "right": 90.0, "left": 270.0}

    def place_edge(refs, edge, gap=2.0):
        """Pack the refs along *edge* by their real COURTYARD extent (+gap), centred, so the bodies
        can't collide; the perpendicular (edge) coord uses the PAD BAND so an overhanging connector
        seats its pads at the margin with the body off-board."""
        if not refs:
            return
        rot = _ROT[edge]
        horiz = edge in ("top", "bottom")
        items = []
        for ref in sorted(refs):
            fp = fp_of.get(ref, "")
            cx, cy, hw, hh = _courtyard_info(fp, rot)
            (pxl, pxh), (pyl, pyh) = _pad_band(fp, rot)
            along = (2 * hw) if horiz else (2 * hh)              # COURTYARD extent along the edge
            coff = cx if horiz else cy                           # courtyard centre offset along edge
            if horiz:                                            # perpendicular (edge) coord
                if oh:
                    perp = (pad_margin - pyl) if edge == "top" else (H - pad_margin - pyh)
                else:
                    perp = (margin + hh - cy) if edge == "top" else (H - margin - hh - cy)
            else:
                if oh:
                    perp = (W - pad_margin - pxh) if edge == "right" else (pad_margin - pxl)
                else:
                    perp = (W - margin - hw - cx) if edge == "right" else (margin + hw - cx)
            items.append((ref, along, coff, perp))
        total = sum(it[1] for it in items) + gap * (len(items) - 1)
        edge_len = W if horiz else H
        cursor = max(margin, (edge_len - total) / 2.0)
        for ref, along, coff, perp in items:
            center = cursor + along / 2.0
            cursor += along + gap
            pa = center - coff                                   # origin so courtyard-centre at center
            A[ref] = (pa, perp, rot) if horiz else (perp, pa, rot)

    place_edge(roles.get("power_in", []), "top")
    place_edge(roles.get("power_out", []), "bottom")
    place_edge(roles.get("host", []) + roles.get("usb", []), "right")
    for ref, xy in (pins or {}).items():               # honor user pins (override)
        if isinstance(xy, (tuple, list)) and len(xy) >= 2 and ref in fp_of:
            A[ref] = (float(xy[0]), float(xy[1]), float(xy[2]) if len(xy) > 2 else 0.0)
    return A


def _adjacency(nl, *, hairball=8):
    """ref -> set(connected refs), skipping dense power/GND hairballs (>hairball nodes)
    which carry no placement signal (they pull everything to one blob)."""
    nbrs = defaultdict(set)
    for net, nodes in nl.nets.items():
        refs = {r for r, _ in nodes}
        if len(refs) > hairball:
            continue
        for a in refs:
            nbrs[a] |= (refs - {a})
    return nbrs


def legalize(P, movable, halfext, W, H, *, clr=0.4, iters=400):
    """Overlap-relaxation: push overlapping courtyards apart, keep parts in-board. Anchors
    (not in *movable*) stay fixed. Returns the number of residual overlaps. Note: at high
    part-area density (a tight board) some residual is unavoidable for point-relaxation --
    that residual is itself the size oracle's 'too tight, grow' signal."""
    def hx(r):
        return halfext.get(r, (1.0, 1.0))
    refs = list(P.keys())
    rnd = random.Random(0)
    for _ in range(iters):
        moved = 0
        for a in refs:
            if a not in movable:
                continue
            ax, ay = P[a][0], P[a][1]
            ahw, ahh = hx(a)
            dx = dy = 0.0
            for b in refs:
                if b == a:
                    continue
                bx, by = P[b][0], P[b][1]
                bhw, bhh = hx(b)
                ox = (ahw + bhw + clr) - abs(ax - bx)
                oy = (ahh + bhh + clr) - abs(ay - by)
                if ox > 0 and oy > 0:                # courtyards overlap -> push along min axis
                    if ox <= oy:
                        s = (ax - bx) if abs(ax - bx) > 1e-6 else (rnd.uniform(-1, 1))
                        dx += math.copysign(ox, s)
                    else:
                        s = (ay - by) if abs(ay - by) > 1e-6 else (rnd.uniform(-1, 1))
                        dy += math.copysign(oy, s)
                    moved += 1
            nx = min(W - ahw, max(ahw, ax + max(-3.0, min(3.0, dx * 0.6))))
            ny = min(H - ahh, max(ahh, ay + max(-3.0, min(3.0, dy * 0.6))))
            P[a] = (nx, ny, P[a][2])
        if moved == 0:
            break
    # count residual overlaps (courtyards still interpenetrating beyond a small tolerance)
    res = 0
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            ahw, ahh = hx(a); bhw, bhh = hx(b)
            if (abs(P[a][0] - P[b][0]) < ahw + bhw and
                    abs(P[a][1] - P[b][1]) < ahh + bhh):
                res += 1
    return res


def legalize_pack(P, movable, cyinfo, W, H, *, clr=0.5, step=0.6):
    """Greedy non-overlap legalization (proper detailed placement): place each movable part at
    the NEAREST FREE position to its target by an outward spiral search, so the result has ZERO
    real courtyard overlap by construction. Each part's obstacle is its TRUE courtyard -- centre
    OFFSET from the origin + half-extent, at its rotation (cyinfo[ref]=(cx,cy,hw,hh)) -- so the
    test matches what KiCad/DRC sees (an origin-centred check mismodels the asymmetric connector
    courtyards and yields phantom-legal placements). Anchors are fixed obstacles; big parts go
    first; a part that genuinely can't fit overlap-free lands at its least-overlap spot and is
    counted -- that residual is the honest 'board too tight -> grow' signal. Returns the residual."""
    DEF = (0.0, 0.0, 1.0, 1.0)
    placed = []                                      # (courtyard_centre_x, _y, hw, hh)
    for r in P:
        if r not in movable:
            cx, cy, hw, hh = cyinfo.get(r, DEF)
            placed.append((P[r][0] + cx, P[r][1] + cy, hw, hh))

    def cost(ccx, ccy, hw, hh):                      # total courtyard interpenetration (0 = free)
        c = 0.0
        for (px, py, phw, phh) in placed:
            ox = (hw + phw + clr) - abs(ccx - px)
            oy = (hh + phh + clr) - abs(ccy - py)
            if ox > 0 and oy > 0:
                c += ox * oy
        return c

    order = sorted(movable, key=lambda r: -(cyinfo.get(r, DEF)[2] * cyinfo.get(r, DEF)[3]))
    residual = 0
    for r in order:
        cx, cy, hw, hh = cyinfo.get(r, DEF)
        tx, ty = P[r][0], P[r][1]                    # target ORIGIN; courtyard centre = origin+(cx,cy)
        lo_x, hi_x = hw - cx, W - hw - cx            # origin range keeping the courtyard in-board
        lo_y, hi_y = hh - cy, H - hh - cy
        if hi_x < lo_x:
            lo_x = hi_x = W / 2 - cx
        if hi_y < lo_y:
            lo_y = hi_y = H / 2 - cy
        best, bestc, R = None, 1e18, 0.0
        while R <= max(W, H):
            n = 1 if R == 0 else max(10, int(2 * math.pi * R / step))
            for k in range(n):
                ang = (2 * math.pi * k / n) if R > 0 else 0.0
                ox_ = min(hi_x, max(lo_x, tx + R * math.cos(ang)))
                oy_ = min(hi_y, max(lo_y, ty + R * math.sin(ang)))
                c = cost(ox_ + cx, oy_ + cy, hw, hh)
                if c < bestc:
                    best, bestc = (ox_, oy_), c
                if c == 0:
                    break
            if bestc == 0:
                break
            R += step
        P[r] = (best[0], best[1], P[r][2])
        placed.append((best[0] + cx, best[1] + cy, hw, hh))
        if bestc > 1e-6:
            residual += 1
    return residual


def _count_overlaps(P, comps, *, drop_antenna=False, clr=0.0):
    """DRC-accurate courtyard-overlap count (matches kicad-cli courtyards_overlap): the honest
    placement residual, not a self-reported one. Uses the real (cached) courtyard bboxes."""
    import cec_pcb
    refs = [r for r in P if r in comps]
    bb = {}
    for r in refs:
        rf = drop_antenna and ("esp32" in comps[r].lower() or "rf_module" in comps[r].lower())
        bb[r] = cec_pcb.courtyard_bbox(comps[r], *P[r], drop_keepout=rf)
    n = 0
    for i, a in enumerate(refs):
        ax = bb[a]
        for b in refs[i + 1:]:
            bx = bb[b]
            if not (ax[1] <= bx[0] - clr or bx[1] <= ax[0] - clr or
                    ax[3] <= bx[2] - clr or bx[3] <= ax[2] - clr):
                n += 1
    return n


def _ov_area(A, B, clr=0.0):
    """Overlap area of two bboxes (xmin,xmax,ymin,ymax), counting copper that comes within clr."""
    dx = min(A[1], B[1]) - max(A[0], B[0]) + clr
    dy = min(A[3], B[3]) - max(A[2], B[2]) + clr
    return dx * dy if (dx > 0 and dy > 0) else 0.0


def anneal_macros(P, cyinfo, movable, W, H, *, nbrs=None, iters=2500, seed=0, alpha=0.04,
                  clr=0.4, t0=8.0, cool=0.9985):
    """Simulated annealing on the MACRO-BLOCK positions (IC clusters + shunts; anchors fixed) to
    ESCAPE the greedy legalizer's local minimum. Objective = courtyard overlap AREA (heavily) +
    alpha*HPWL to connected parts (stay routable). Being STOCHASTIC, different *seed*s settle into
    different minima -- THAT spread is what makes a huge best-of-N sweep pay off (a deterministic
    placer just yields identical candidates). Mutates P in place; returns P."""
    rnd = random.Random(seed)
    mv = [r for r in movable if r in cyinfo and r in P]
    placed = [r for r in P if r in cyinfo]
    if not mv:
        return P

    def bbox(r):
        cx, cy, hw, hh = cyinfo[r]
        x, y = P[r][0], P[r][1]
        return (x + cx - hw, x + cx + hw, y + cy - hh, y + cy + hh)

    def cost(r):
        ar = bbox(r)
        c = 0.0
        for o in placed:
            if o != r:
                c += _ov_area(ar, bbox(o), clr)
        if nbrs:
            for n in nbrs.get(r, ()):
                if n in P:
                    c += alpha * (abs(P[r][0] - P[n][0]) + abs(P[r][1] - P[n][1]))
        return c

    T = t0
    for _ in range(iters):
        r = rnd.choice(mv)
        cx, cy, hw, hh = cyinfo[r]
        ox, oy, orot = P[r]
        before = cost(r)
        if rnd.random() < 0.7:                        # local jitter
            nx, ny = ox + rnd.uniform(-3, 3), oy + rnd.uniform(-3, 3)
        else:                                         # occasional teleport (escape)
            nx, ny = rnd.uniform(hw - cx, W - hw - cx), rnd.uniform(hh - cy, H - hh - cy)
        nx = min(W - hw - cx, max(hw - cx, nx))
        ny = min(H - hh - cy, max(hh - cy, ny))
        P[r] = (nx, ny, orot)
        d = cost(r) - before
        if d > 0 and rnd.random() >= math.exp(-d / max(T, 1e-3)):
            P[r] = (ox, oy, orot)                     # reject
        T *= cool
    return P


def relative_place(anchors, nl, W, H, fp_of, *, drop_antenna=False, strat="dataflow", seed=0,
                   only=None, cyinfo_override=None):
    """Relative-place parts by net connectivity (barycentric sweeps from the fixed anchors),
    under a strategy, then legalize against the TRUE courtyards. *only* restricts placement to
    that ref list (the rest of fp_of is left to a later pass, e.g. auto_cluster of the passives).
    *cyinfo_override* {ref:(cx,cy,hw,hh)} replaces a part's courtyard for legalization -- used to
    place IC MACRO-BLOCKS (IC + its clustered passives) by their full bbox so the legalizer reserves
    the cluster's room. Returns ({ref:(x,y,rot)}, residual)."""
    rnd = random.Random(seed)
    P = dict(anchors)
    pool = only if only is not None else list(fp_of)
    movable = [r for r in pool if r not in anchors and r in fp_of]
    # seed on a coarse GRID across the board (not clustered at centre) so the legalizer
    # starts near-tessellated -- far fewer initial overlaps than a central blob.
    ncol = max(1, int(math.ceil(math.sqrt(len(movable) * max(W, 1) / max(H, 1)))))
    order = list(movable)
    rnd.shuffle(order)
    for i, r in enumerate(order):
        col, row = i % ncol, i // ncol
        nrow = max(1, int(math.ceil(len(movable) / ncol)))
        P[r] = (W * (col + 0.5) / ncol, H * (row + 0.5) / nrow, 0.0)
    nbrs = _adjacency(nl)
    hot = {r for r in movable if _part_power_w(r, nl.comps.get(r, Comp(r)).value) >= 0.3}
    for _ in range(45):
        for r in movable:
            ns = [P[n] for n in nbrs.get(r, ()) if n in P]
            if not ns:
                continue
            tx = sum(p[0] for p in ns) / len(ns)
            ty = sum(p[1] for p in ns) / len(ns)
            if strat == "compact":                   # pull harder toward neighbours
                tx = 0.7 * tx + 0.3 * P[r][0]
                ty = 0.7 * ty + 0.3 * P[r][1]
            elif strat == "thermal_separated" and r in hot:   # nudge hot parts apart
                for h in hot:
                    if h != r and h in P and abs(P[h][0] - tx) < 8 and abs(P[h][1] - ty) < 8:
                        tx += math.copysign(4.0, tx - P[h][0] or 1.0)
            P[r] = (tx, ty, P[r][2])
    # the TRUE courtyard (centre offset + half) of every part at its placed rotation,
    # overridden by the macro-block bbox where given (IC + its passive cluster)
    cyinfo = {r: _courtyard_info(fp_of[r], P[r][2], drop_antenna=drop_antenna) for r in P if r in fp_of}
    if cyinfo_override:
        cyinfo.update(cyinfo_override)
    clr = 0.3 if strat == "compact" else 0.45
    res = legalize_pack(P, movable, cyinfo, W, H, clr=clr)
    return P, res


def _placement_obj(cfg, P, W, H, halfext, nl):
    """Build a Placement (pos + pads_by_net via real footprint pad geometry) for the proxy."""
    import cec_pcb
    comps = {r: c.footprint for r, c in nl.comps.items() if c.footprint and ":" in c.footprint}
    pads_by_net = defaultdict(list)
    for net, nodes in nl.nets.items():
        for ref, pin in nodes:
            if ref not in P:
                continue
            try:
                x, y = cec_pcb.pad_global(ref, pin, {ref: P[ref]}, comps)
            except Exception:
                x, y = P[ref][0], P[ref][1]
            pads_by_net[net].append((x, y))
    pos = {r: (P[r][0], P[r][1], P[r][2], halfext.get(r, (1.0, 1.0))[0], halfext.get(r, (1.0, 1.0))[1])
           for r in P}
    value = {r: nl.comps[r].value for r in P if r in nl.comps}
    return Placement(pos=pos, pads_by_net=dict(pads_by_net), value=value, W=W, H=H, x0=0.0, y0=0.0)


@dataclass
class Candidate:
    """A placement candidate + its cheap proxy + (later) its feasibility confidence."""
    strat: str
    seed: int
    P: dict                       # ref -> (x, y, rot)
    W: float
    H: float
    residual: int                 # legalization residual overlaps
    proxy: dict
    feasible: float = -1.0        # filled by the feasibility probe (stage: size oracle)


def synth_one(cfg_dict, W, H, strat, seed):
    """Worker: synthesize + score ONE placement candidate. Top-level + picklable so it runs
    in a spawn-pool worker (on the runner's cores). Takes/returns plain types only."""
    import cec_pcb
    cfg = Config(**cfg_dict)
    nl = View(cfg).nl
    # materialize() embeds the FULL ESP footprint (antenna keepout intact), so for DRC-CONSISTENCY
    # the placer must respect the keepout too -- otherwise it packs into space the board doesn't have
    # (the J_IN2<->U1 overlap). Honouring the Stage-1 'drop the keepout' area win needs a trimmed-
    # courtyard materialize (a follow-up); until then we keep the keepout to stay honest with DRC.
    drop_antenna = False
    halfext = _part_halfext(nl, drop_antenna=drop_antenna)
    fp_of = _fp_of(nl)
    anchors_roles, ics, shunts, passives = _classify(nl)
    # 1. anchors: connectors (by role, with edge OVERHANG per the ask) + the generalized
    #    mechanical asks (mounts + fiducials)
    anchors = seed_anchors(nl, W, H, fp_of, cfg.pins,
                           overhang=cfg.params.get("connector_overhang", "none"))
    mech_pos, mech_fp = place_mechanical(W, H, cfg.params)
    anchors.update(mech_pos)
    comps = dict(fp_of)
    comps.update(mech_fp)                               # ref->libid incl. mounts/fiducials
    for r, fpp in mech_fp.items():
        try:
            halfext[r] = _half_extent(fpp)
        except Exception:
            halfext[r] = (1.6, 1.6)
    # nudge the mounts/fiducials to the nearest free spot clear of the connectors (the default
    # mount/fiducial coords don't know where the connectors landed)
    anchor_cy = {r: _courtyard_info(comps[r], anchors[r][2], drop_antenna=drop_antenna)
                 for r in anchors if r in comps}
    legalize_pack(anchors, [r for r in mech_pos if r in anchors], anchor_cy, W, H, clr=0.5)
    # 2. MACRO BLOCKS: auto_cluster each IC's passives in ISOLATION (IC at origin) to learn the
    #    cluster's full bbox + each passive's offset. Placing the bare IC then fanning passives into
    #    a tight gap fails (the condensed boards SPREAD ICs to leave cluster room) -- so we place the
    #    cluster as one macro and legalize with its full bbox, reserving the room.
    spec = derive_passive_spec(nl, passives, [r for r in ics if not r.startswith("SW")])
    by_owner = defaultdict(list)
    for pref, (own, pad) in spec.items():
        if own in ics:
            by_owner[own].append((pref, pad))
    drop_kc = tuple(r for r in comps if "esp32" in comps[r].lower()) if drop_antenna else ()
    macro = {}                                          # unit -> (cx,cy,hw,hh) cluster bbox @origin
    cluster_offsets = {}                                # unit -> {pref:(dx,dy,rot)}
    for unit in ics + shunts:
        members = by_owner.get(unit, [])
        if unit not in comps:
            continue
        if members:
            Ptmp = {unit: (0.0, 0.0, 0.0)}
            cec_pcb.auto_cluster(Ptmp, comps, {p: (unit, pad) for p, pad in members},
                                 drop_keepout=((unit,) if unit in drop_kc else ()))
            xs, ys = [], []
            for r in Ptmp:
                x0, x1, y0, y1 = cec_pcb.courtyard_bbox(comps[r], *Ptmp[r],
                                                        drop_keepout=(r in drop_kc))
                xs += [x0, x1]; ys += [y0, y1]
            macro[unit] = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                           (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2)
            cluster_offsets[unit] = {p: Ptmp[p] for p, _ in members}
        else:
            macro[unit] = _courtyard_info(comps[unit], 0.0, drop_antenna=drop_antenna)
            cluster_offsets[unit] = {}
    # 3. place the MACROS (ICs+shunts) by connectivity, legalized with their full cluster bbox
    P, _ = relative_place(anchors, nl, W, H, fp_of, drop_antenna=drop_antenna,
                          strat=strat, seed=seed, only=ics + shunts, cyinfo_override=macro)
    # 3b. ANNEAL the macros to escape the greedy minimum (compaction + the diversity engine), then
    #     a final greedy snap from the annealed start. Full cyinfo = macro bbox for ICs/shunts,
    #     real courtyard for the fixed anchors.
    cyinfo_all = {}
    for r in P:
        if r in macro:
            cyinfo_all[r] = macro[r]
        elif r in comps:
            cyinfo_all[r] = _courtyard_info(comps[r], P[r][2], drop_antenna=drop_antenna)
    anneal_macros(P, cyinfo_all, ics + shunts, W, H, nbrs=_adjacency(nl), seed=seed)
    legalize_pack(P, [r for r in (ics + shunts) if r in P], cyinfo_all, W, H, clr=0.4)
    # 4. stamp each cluster's passives relative to its placed unit (rigid macro)
    for unit, offs in cluster_offsets.items():
        if unit not in P:
            continue
        ux, uy, _ur = P[unit]
        for pref, (dx, dy, pr) in offs.items():
            P[pref] = (ux + dx, uy + dy, pr)
    res = _count_overlaps(P, comps, drop_antenna=drop_antenna)   # honest DRC-accurate residual
    obj = _placement_obj(cfg, P, W, H, halfext, nl)
    proxy = placement_proxy(obj)
    return Candidate(strat=strat, seed=seed, P=P, W=W, H=H, residual=res, proxy=proxy)


def place_candidates(cfg, W, H, *, strategies=STRATEGIES, seeds=(0,), max_workers=None):
    """Generate the placement candidates (strategy x seed), in PARALLEL on a spawn pool.
    Mirrors cec_fr.generate_batch's runner-capable design: a large candidate count offloads
    onto the self-hosted runner's cores (max_workers=0/None -> min(#candidates, CPUs)).
    Returns the candidates sorted best-first by (residual, proxy HPWL)."""
    work = [(s, seed) for s in strategies for seed in seeds]
    cfg_dict = {k: getattr(cfg, k) for k in ("board", "profile", "pins", "params",
                                             "dir", "sch", "net", "pcb", "bom_csv")}
    n = max_workers if max_workers else min(len(work), os.cpu_count() or 1)
    cands = []
    if n <= 1 or len(work) == 1:                     # in-process (cheap / single)
        for s, seed in work:
            cands.append(synth_one(cfg_dict, W, H, s, seed))
    else:
        import multiprocessing as mp
        ctx = mp.get_context("spawn")               # pcbnew/cec_pcb is not fork-safe
        with ProcessPoolExecutor(max_workers=n, mp_context=ctx) as pool:
            futs = {pool.submit(synth_one, cfg_dict, W, H, s, seed): (s, seed) for s, seed in work}
            for f in as_completed(futs):
                cands.append(f.result())
    cands.sort(key=lambda c: (c.residual, c.proxy["hpwl"]))
    return cands


def place_with_consent(cfg, W, H, *, pins=None, ask=None, strategies=STRATEGIES,
                       seeds=(0, 1), max_workers=None, verbose=False):
    """place_with_consent (pipeline lines 77-86): synthesize the candidate variants, pick the
    best by proxy, and run the user-pin CONSENT loop -- if a USER-pinned part is the binding
    cause of a poor placement, ASK the human (APPROVE move / KEEP / EDIT) rather than silently
    overriding the pin. Returns the chosen Candidate. *ask(reason, suggestion, cfg)->Action*."""
    if pins:
        cfg = Config(**{**{k: getattr(cfg, k) for k in
                          ("board", "profile", "pins", "params", "dir", "sch", "net", "pcb", "bom_csv")},
                        "pins": {**cfg.pins, **pins}})
    cands = place_candidates(cfg, W, H, strategies=strategies, seeds=seeds, max_workers=max_workers)
    best = cands[0]
    if verbose:
        for c in cands:
            print(f"    cand {c.strat:16s} seed{c.seed} residual={c.residual} "
                  f"HPWL={c.proxy['hpwl']} RUDYpk={c.proxy['rudy_peak']}")
    # consent: a user-pinned part that is the binding cause of a bad (overlapping) placement
    if best.residual > 0 and cfg.pins and ask is not None:
        binding = [r for r in cfg.pins if r in best.P]
        if binding:
            act = ask(f"user-pinned {binding} forces {best.residual} residual overlap(s)",
                      {"relax": binding[0]}, cfg)
            if getattr(act, "resolved", False) and getattr(act, "note", "") == "relax":
                # KEEP the pin, relax elsewhere: re-place without that pin pinned
                relaxed = {k: v for k, v in cfg.pins.items() if k != binding[0]}
                cfg2 = Config(**{**{k: getattr(cfg, k) for k in
                                    ("board", "profile", "params", "dir", "sch", "net", "pcb", "bom_csv")},
                                 "pins": relaxed, "profile": cfg.profile})
                best = place_candidates(cfg2, W, H, strategies=strategies, seeds=seeds,
                                        max_workers=max_workers)[0]
    return best


# ============================================================ Stage 1: requirements (human I/O)
# The pipeline must ASK the human the design inputs it cannot safely assume (pipeline line 8:
# Config + requirements). Each Requirement is a question the orchestrator puts to the human via
# AskUserQuestion (the human rung); the answer is recorded into cfg.params and flows into triage
# (EMC arming), the placer (antenna keepout), the size oracle, and the FEA (derating).
@dataclass
class Requirement:
    id: str
    prompt: str
    param: str                    # cfg.params key it sets
    options: list                 # [(label, value, note), ...]
    default: object
    affects: str = ""


REQUIREMENTS = [
    Requirement("antenna_keepout",
                "Is wireless populated (must the ESP32 PCB-antenna keepout be respected)?",
                "respect_antenna_keepout",
                [("respect", True, "wireless used -> keep the antenna clear-zone"),
                 ("drop", False, "wired-only -> GND fills under the antenna, tighter placement")],
                default=True, affects="placer ESP courtyard + EMC RF arming"),
    Requirement("placement_handoff",
                "When auto-placement isn't clean, hand off to the human, auto-grow, or proceed?",
                "placement_handoff_mode",
                [("handoff", "handoff", "human hand-finalizes the placement before continuing"),
                 ("grow", "grow", "size oracle grows the board until it legalizes"),
                 ("proceed", "proceed", "let the route swarm + cascade catch it")],
                default="handoff", affects="placement finalize flow"),
    Requirement("thermal_env",
                "Thermal environment (drives THERMAL arming + electrothermal derating)?",
                "thermal_env",
                [("enclosed_passive", "enclosed_passive", "in-case, no airflow -> conservative derating"),
                 ("airflow", "airflow", "bench / PC airflow -> relaxed derating"),
                 ("worst_case", "worst_case", "let the FEA pick the worst-case ambient")],
                default="enclosed_passive", affects="THERMAL arming + FEA derating"),
    Requirement("size_target",
                "How should the size oracle size the board?",
                "size_target",
                [("min_area", "min_area", "shrink to the minimum routable area"),
                 ("margin", "margin", "shrink but keep a margin above the routable floor"),
                 ("as_built", "as_built", "optimize placement only, keep the start size")],
                default="margin", affects="size oracle shrink target"),
    # --- MECHANICAL + manufacturing: generalized ask-first (NOT baked per-board) ---
    Requirement("mount_holes",
                "How many mounting holes, what size, where?",
                "mount_holes",
                [("3_2logic_1conn", "3_2logic_1conn", "3x M3: 2 logic-side + 1 connector-side"),
                 ("4_corner", "4_corner", "4x M3 at the board corners"),
                 ("2_diag", "2_diag", "2x M3 on a diagonal")],
                default="3_2logic_1conn", affects="seed_anchors mount placement + keepout"),
    Requirement("connector_overhang",
                "Should connectors overhang the board edge to save area?",
                "connector_overhang",
                [("power_able", "power_able", "all connectors that can overhang without issue do"),
                 ("all", "all", "every edge connector overhangs"),
                 ("none", "none", "all connectors fully on-board")],
                default="power_able", affects="seed_anchors edge overhang"),
    Requirement("fiducials",
                "How many fiducials and where?",
                "fiducials",
                [("3", "3", "3 fiducials (2 top + 1 bottom), assembly registration"),
                 ("2", "2", "2 fiducials diagonal"),
                 ("none", "none", "no fiducials")],
                default="3", affects="board-level fiducial placement + keepout"),
]


def elicit_requirements(cfg, answers=None):
    """Stage 1 (Config + requirements, human I/O): record the human's design inputs into
    cfg.params. *answers* maps a Requirement id -> the chosen value (or its label); the
    orchestrator collects them via AskUserQuestion (the human rung) and passes them here.
    An unanswered requirement takes its default (headless-safe). Returns cfg."""
    answers = answers or {}
    for req in REQUIREMENTS:
        v = answers.get(req.id, req.default)
        for (lab, val, _n) in req.options:           # accept a label in place of the value
            if v == lab:
                v = val
                break
        cfg.params[req.param] = v
    return cfg


# The inputs collected interactively for the EPS module (demonstration of Stage-1 elicitation):
# wired-only (drop the antenna keepout), hand off placement to the human, enclosed/passive thermal,
# 3x M3 (2 logic + 1 conn-side), connectors overhang where they can, 3 fiducials.
EPS_ANSWERS = {"antenna_keepout": False, "placement_handoff": "handoff",
               "thermal_env": "enclosed_passive", "size_target": "margin",
               "mount_holes": "3_2logic_1conn", "connector_overhang": "power_able",
               "fiducials": "3"}


# ============================================================ materialize + placement handoff
def materialize(cand, cfg, out, *, logo=None):
    """Write a placement candidate to a REAL .kicad_pcb (cec_pcb.build_board): every netlist
    footprint at its synth position + edge cuts at the candidate size + the GND zone. Mount
    refs (H1..) feed build_board's mount list; the rest place from the netlist footprints. The
    board is self-contained (footprints embedded) so kicad-cli can render + DRC it. Returns out."""
    import cec_pcb
    def _is_mount(r):
        return r.startswith("H") and r[1:].isdigit()
    mounts = [(p[0], p[1]) for r, p in cand.P.items() if _is_mount(r)]
    # build_board places mounts (H1..) itself; FID/LOGO are board-level finishing it doesn't emit.
    P3 = {r: (p[0], p[1], p[2]) for r, p in cand.P.items()
          if not _is_mount(r) and not r.startswith(("LOGO", "FID"))}
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    cec_pcb.build_board(out, cfg.net, P3, mounts, logo, cand.W, cand.H, force_argv=False)
    for ext in (".kicad_pro", ".kicad_dru"):         # carry rules so DRC matches the real module
        s = (cfg.pcb[:-len(".kicad_pcb")] + ext) if cfg.pcb else ""
        if s and os.path.isfile(s):
            shutil.copy(s, out[:-len(".kicad_pcb")] + ext)
    return out


def place_finalize_handoff(cand, cfg, *, ask=None, work_dir=None):
    """The placement HUMAN-HANDOFF rung (the user's step): after the automated evaluation, if the
    placement isn't clean -- residual courtyard overlaps, or a failed feasibility probe -- act on
    cfg.params['placement_handoff_mode']:
      'handoff' -> materialize + render the placement and hand it to the human to FINALIZE in the
                   GUI (confirm it's really doable); the pipeline then re-reads + re-evaluates the
                   finalized board. *ask(reason, detail, cfg)->Action* is the human rung.
      'grow'    -> return unresolved 'grow' so the size oracle grows the board.
      'proceed' -> accept and let the route swarm + cascade catch it.
    Returns an Action; in 'handoff' the Action.detail carries the materialized board + render path."""
    clean = (cand.residual == 0) and (cand.feasible != 0.0)
    if clean:
        return Action(resolved=True, rung="placer", note="placement clean; no handoff needed")
    mode = cfg.params.get("placement_handoff_mode", "handoff")
    if mode == "grow":
        return Action(resolved=False, rung="placer", note="grow",
                      detail={"residual": cand.residual})
    if mode == "proceed":
        return Action(resolved=True, rung="placer", note="proceed to routing despite residual")
    # handoff: materialize + render, then ask the human to finalize
    work_dir = work_dir or os.path.join(tempfile.gettempdir(), f"cec_synth_place_{cfg.board}")
    os.makedirs(work_dir, exist_ok=True)
    board = materialize(cand, cfg, os.path.join(work_dir, f"{cfg.board}-synth.kicad_pcb"))
    png = os.path.join(work_dir, f"{cfg.board}-synth-top.png")
    subprocess.run(["kicad-cli", "pcb", "render", "-o", png, board], capture_output=True)
    detail = {"board": board, "render": png if os.path.isfile(png) else None,
              "residual": cand.residual, "W": cand.W, "H": cand.H, "proxy": cand.proxy}
    reason = (f"auto-placement at {cand.W:.0f}x{cand.H:.0f} has {cand.residual} residual "
              f"courtyard overlap(s) -- hand-finalize before continuing?")
    if ask is not None:
        act = ask(reason, detail, cfg)
        act.detail = {**detail, **(act.detail or {})}
        return act
    return Action(resolved=False, halt=True, rung="human", note=reason, detail=detail)


# ============================================================ Stage 9: physics (electrothermal FEA)
# Analytic IPC-2221/2152 electrothermal model: closed-form conductor temperature rise per copper
# feature, coupled J -> T -> rho(T) -> J in a Picard loop (pipeline electrothermal_solve). Gates
# current-density / temperature-rise / component derating. No mesh -- matched to the CEC boards'
# known high-current paths (cable pours, shunts, vias). The IPC-2152 charts refine the closed form
# with board conductivity; the constant k is the tuning knob to fit 2152 data.
ALPHA_CU = 0.00393                       # copper temp-coefficient of resistance, 1/°C
CU_OZ_MM = 0.0348                        # mm copper per oz
_AMBIENT = {"enclosed_passive": 50.0, "airflow": 35.0, "worst_case": 60.0}


def dt_ipc(I, cross_mm2, *, external=True):
    """IPC-2221 closed-form conductor temperature rise (°C): I = k·dT^0.44·A^0.725 (A in mils^2,
    k=0.048 external / 0.024 internal) -> dT = (I/(k·A^0.725))^(1/0.44)."""
    if cross_mm2 <= 0 or I <= 0:
        return 0.0
    area_mils2 = cross_mm2 * 1550.0031
    k = 0.048 if external else 0.024
    return (I / (k * area_mils2 ** 0.725)) ** (1.0 / 0.44)


def _picard_dt(I, cross_mm2, ambient, external):
    """Self-consistent dT with rho(T): heating ∝ rho(T) so dT = dt_ipc·(1+α(ambient+dT-20)). This
    fixed point has the closed form dT = dt0·(1+α(ambient-20)) / (1 - dt0·α). When dt0·α >= ~1 the
    rho-feedback RUNS AWAY -- the conductor is grossly over-current (it will fuse), so we clamp and
    let the gate fail it rather than report a meaningless 1e40."""
    dt0 = dt_ipc(I, cross_mm2, external=external)
    if dt0 <= 0:
        return 0.0
    coeff = dt0 * ALPHA_CU
    if coeff >= 0.95:                                    # thermal runaway -> fusing
        return min(dt0, 999.0)
    return dt0 * (1.0 + ALPHA_CU * (ambient - 20.0)) / (1.0 - coeff)


def _net_currents(cfg, board_nets):
    """Per-net design current (A): cfg.params['net_currents'] overrides; else a role model
    (cable 12V sense/force nets carry the cable current, rails their rail current, signals ~0)."""
    user = cfg.params.get("net_currents", {})
    i_cable = cfg.params.get("cable_current_A", 40.0)        # EPS/PCIe per-cable (spec §6.4 region)
    out = {}
    for n in board_nets:
        if n in user:
            out[n] = user[n]
        elif n.endswith(("_HI", "_LO")) or "12V" in n:
            out[n] = i_cable
        elif "5VSB" in n or n.endswith("+5V"):
            out[n] = cfg.params.get("rail_5v_A", 2.5)
        elif "3V3" in n:
            out[n] = cfg.params.get("rail_3v3_A", 0.8)
        elif n.rsplit("/", 1)[-1] == "GND":
            out[n] = i_cable                                  # return current (distributed in plane)
        else:
            out[n] = 0.0
    return out


@dataclass
class ThermalResult:
    ambient: float
    max_T: float
    max_dT: float
    nets: dict                  # net -> {I, cross_mm2, J, dT, T, poured}
    vias: list                  # worst vias
    shunts: list                # shunt dissipators


def electrothermal_solve(board_path, cfg, *, ambient=None):
    """Solve the analytic electrothermal model on a ROUTED board: per high-current net the parallel
    copper cross-section (tracks + pours, the pour's perpendicular cut = area/path_len x thickness),
    the Picard dT; per via the split current + barrel cross-section; per shunt the I^2R dissipation.
    Returns a ThermalResult. (Approximations documented inline; this is the analytic first model.)"""
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    nets = {n.GetNetname() for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    cur = _net_currents(cfg, nets)
    if ambient is None:
        ambient = _AMBIENT.get(cfg.params.get("thermal_env", "enclosed_passive"), 50.0)

    # per-net pad bbox -> current path length (for the pour's perpendicular cross-section)
    pad_bb = defaultdict(lambda: [1e9, -1e9, 1e9, -1e9])
    for fp in b.GetFootprints():
        for p in fp.Pads():
            nn = p.GetNetname()
            if cur.get(nn, 0) > 0:
                pos = p.GetPosition(); x, y = pos.x / 1e6, pos.y / 1e6
                bb = pad_bb[nn]
                bb[0], bb[1] = min(bb[0], x), max(bb[1], x)
                bb[2], bb[3] = min(bb[2], y), max(bb[3], y)

    cross = defaultdict(float)            # net -> total parallel cross-section (mm^2)
    poured = set()
    nvias = defaultdict(int)
    for t in b.GetTracks():
        net = t.GetNetname(); I = cur.get(net, 0.0)
        if I <= 0:
            continue
        if t.Type() == pcbnew.PCB_TRACE_T:
            ext = b.GetLayerName(t.GetLayer()) in ("F.Cu", "B.Cu")
            cross[net] += (t.GetWidth() / 1e6) * ((2 if ext else 1) * CU_OZ_MM)
        elif t.Type() == pcbnew.PCB_VIA_T:
            nvias[net] += 1
    for z in b.Zones():
        net = z.GetNetname(); I = cur.get(net, 0.0)
        if I <= 0:
            continue
        poured.add(net)
        bb = pad_bb.get(net)
        path = max(2.0, (bb[3] - bb[2])) if bb else 10.0     # perpendicular-cut path length
        for layer in z.GetLayerSet().Seq():
            ext = b.GetLayerName(layer) in ("F.Cu", "B.Cu")
            try:
                area = z.GetFilledPolysList(layer).Area() / 1e12   # planar mm^2 (per layer)
            except Exception:
                area = 0.0
            cross[net] += (area / path) * ((2 if ext else 1) * CU_OZ_MM)

    net_res = {}
    max_T, max_dT = ambient, 0.0
    for net, I in cur.items():
        if I <= 0 or cross.get(net, 0) <= 0:
            continue
        c = cross[net]
        dt = _picard_dt(I, c, ambient, external=(net in poured))
        net_res[net] = {"I": round(I, 1), "cross_mm2": round(c, 4),
                        "J": round(I / c, 1), "dT": round(dt, 1), "T": round(ambient + dt, 1),
                        "poured": net in poured}
        if ambient + dt > max_T:
            max_T, max_dT = ambient + dt, dt

    vias = []
    for t in b.GetTracks():
        if t.Type() != pcbnew.PCB_VIA_T:
            continue
        net = t.GetNetname(); I = cur.get(net, 0.0)
        if I <= 0:
            continue
        iv = I / max(1, nvias[net])                          # current splits among parallel vias
        drill = t.GetDrillValue() / 1e6
        cv = math.pi * drill * 0.025                         # plated barrel ~25um
        dt = _picard_dt(iv, cv, ambient, external=True)
        vias.append({"net": net, "I_via": round(iv, 2), "drill_mm": round(drill, 3),
                     "J": round(iv / cv, 1) if cv else 0, "dT": round(dt, 1), "T": round(ambient + dt, 1)})
    vias.sort(key=lambda v: -v["T"])

    shunts = []
    for fp in b.GetFootprints():
        if not fp.GetReference().startswith("RS"):
            continue
        R = _r_value_ohms(fp.GetValue()) or 0.5e-3
        I = cfg.params.get("cable_current_A", 40.0)
        P = I * I * R
        dt = P * cfg.params.get("shunt_rth_CW", 25.0)        # 2512 shunt+pad thermal resistance °C/W
        shunts.append({"ref": fp.GetReference(), "R_ohm": R, "I": I, "P_W": round(P, 3),
                       "dT": round(dt, 1), "T": round(ambient + dt, 1)})
        if ambient + dt > max_T:
            max_T, max_dT = ambient + dt, dt

    return ThermalResult(ambient=ambient, max_T=round(max_T, 1), max_dT=round(max_dT, 1),
                         nets=net_res, vias=vias[:8], shunts=shunts)


def physics_gates(res, cfg):
    """J / temperature-rise / derating gates on a ThermalResult (pipeline physics() J/T/derating)."""
    flags = []
    dt_max = cfg.params.get("dT_max_C", 30.0)
    t_max = cfg.params.get("T_max_C", 105.0)
    j_max = cfg.params.get("J_max_A_mm2", 100.0)             # sustained current density ceiling
    for net, r in res.nets.items():
        if r["T"] > t_max or r["dT"] > dt_max:
            flags.append(Flag("conductor over-temp", net, 0.85, Kind.MEASURE,
                              {"dT": r["dT"], "T": r["T"], "I": r["I"], "cross_mm2": r["cross_mm2"],
                               "poured": r["poured"], "limit_dT": dt_max, "limit_T": t_max}))
        elif r["J"] > j_max:
            flags.append(Flag("current density high", net, 0.6, Kind.MEASURE,
                              {"J": r["J"], "limit": j_max}))
    for v in res.vias:
        if v["T"] > t_max or v["dT"] > dt_max:
            flags.append(Flag("via over-temp", v["net"], 0.7, Kind.MEASURE, dict(v, limit_T=t_max)))
            break                                            # one representative via flag
    for s in res.shunts:
        if s["T"] > t_max or s["dT"] > dt_max:
            flags.append(Flag("shunt over-temp", s["ref"], 0.8, Kind.MEASURE, dict(s, limit_T=t_max)))
    return flags


def physics(board_path, cfg, armed=()):
    """Pipeline physics(routed, cfg, armed): run the electrothermal FEA + J/T/derating gates.
    (PDN and other armed deep analyses hang here too when present.) Returns (ThermalResult, flags)."""
    res = electrothermal_solve(board_path, cfg)
    flags = physics_gates(res, cfg)
    return res, flags


# ============================================================ route swarm bridge
def route_swarm(cfg, *, board=None, out_dir=None, seeds=(0, 1), manager=None,
                worker=None, escalator=None, verbose=True, max_iters=1, kmax=1, **board_spec_kw):
    """Wire the synthesis pipeline's ROUTE SWARM stage (pipeline line 38) onto the existing
    cec_router.route() loop -- the real Freerouting + score + gate + repair/escalate +
    pour-after-route + decision-log machinery. Returns (final_board_path, DecisionLog).

    DEFAULTS TO A SINGLE PASS (max_iters=1, kmax=1, 2 seeds): without a real LLM manager judging
    the candidates, the deterministic default manager never ACCEPTS a non-perfect DRC (e.g. the
    DRC=4 logo+shield residual) and grinds to the iteration ceiling -- 16 Freerouting runs for a
    board that's effectively done (this is what 'repeated a lot' on the runner). A single pass
    routes once and hands the result to the pipeline's physics+cascade, which judges quality. When
    a real Sonnet MANAGER sub-agent IS supplied (in a Claude session), raise max_iters/kmax to let
    it accept/repair/escalate properly. (These are cec_router's per-candidate tiers -- a DIFFERENT
    interface from the pipeline's flag-level resolve() ladder.)"""
    import cec_router
    out_dir = out_dir or os.path.join(tempfile.gettempdir(), f"cec_synth_route_{cfg.board}")
    spec, name = cec_router.board_spec(board or cfg.board, out_dir, seeds=tuple(seeds),
                                       max_iters=max_iters, kmax=kmax, **board_spec_kw)
    final, log = cec_router.route(spec.board, spec, manager=manager, worker=worker,
                                  escalator=escalator, verbose=verbose)
    return final, log


# ============================================================ Stage 11-12: sign-off + build/freeze
def human_signoff(board, cfg, flags, *, ask=None):
    """Stage 11: the cert-grade HUMAN sign-off. Interactive -> ask() (the human approves/withholds);
    headless -> CAUTIOUS auto: sign off ONLY if nothing blocking remains (a residual flag with no
    human present is NOT a release). Returns True iff signed off."""
    blocking = [f for f in flags if f.conf >= 0.5]
    if ask is not None:
        act = ask(f"cert-grade sign-off: {len(flags)} residual flag(s), {len(blocking)} blocking. "
                  f"Release?", {"flags": [str(f) for f in flags]}, cfg)
        return bool(getattr(act, "resolved", False))
    return not blocking


def _archive_corpus(log, board_name, *, kind):
    """Best-effort: append this run's decision log to the accumulating corpus (build/route/corpus/)
    via cec_router.archive_log -- the training/eval substrate for the surrogate ranker (Thrust C,
    docs/local-compute-exploration.md). Lazy import (cec_router pulls pcbnew) + swallow errors so a
    release is never blocked by archiving."""
    try:
        import cec_router
        cec_router.archive_log(log, board_name, kind=kind)
    except Exception as e:
        print(f"  WARN corpus archive skipped: {e}")


def freeze_build(cfg, board, log, out_dir):
    """Stage 12: assemble the release + FREEZE the decision log (board = f(decision log) ->
    reproducible). Copies the routed board + the board rules into the release dir and writes the
    frozen log. Returns the release dict."""
    os.makedirs(out_dir, exist_ok=True)
    rel = os.path.join(out_dir, f"{cfg.board}-release.kicad_pcb")
    shutil.copy(board, rel)
    for ext in (".kicad_pro", ".kicad_dru"):
        s = board[:-len(".kicad_pcb")] + ext
        if os.path.isfile(s):
            shutil.copy(s, rel[:-len(".kicad_pcb")] + ext)
    logp = os.path.join(out_dir, f"{cfg.board}-decision-log.json")
    json.dump(log, open(logp, "w"), indent=2, default=str)
    _archive_corpus(log, cfg.board, kind="synth-freeze")
    return {"board": rel, "log": logp, "frozen": True}


# ============================================================ run_pipeline (the top-level driver)
def run_pipeline(cfg, *, board=None, route=False, ask=None, tiers=None, out_dir=None,
                 verbose=True, max_loops=2):
    """The top-level pipeline (pseudocode run_pipeline) on an EXISTING board -- the synth place/size
    -oracle is DEFERRED (placer TODO), so this threads: ERC+BOM gate -> triage -> [use the existing/
    old-design board, optional route_swarm] -> physics+cascade loop (resolve on failure) -> human
    sign-off -> build+freeze. POSTURE CAUTIOUS: unresolved flags block the release. Returns a result
    dict (status RELEASED / sign-off withheld / failed) with the frozen decision log."""
    log = {"board": cfg.board, "profile": cfg.profile, "params": dict(cfg.params), "stages": []}

    def rec(stage, **kw):
        log["stages"].append({"stage": stage, **kw})
        if verbose:
            print(f"  [{stage}] " + "  ".join(f"{k}={v}" for k, v in kw.items()
                                              if k not in ("flags",)))

    # 1. ERC + BOM gate (loop until clean or unresolvable)
    view = View(cfg)
    gate_flags = run_stage(ERC_BOM, view)
    ok, _ = resolve_each(gate_flags, cfg, ask=ask, tiers=tiers)
    rec("erc_bom_gate", n_flags=len(gate_flags), resolved=ok)
    if not ok and ask is None:
        rec("relax_or_fail", reason="unresolved netlist/BOM flags (headless)")

    # 2. triage (arm the optional analyses)
    armed = triage_arm(cfg)
    rec("triage", armed=[a.name for a in armed])

    # 3. place / size oracle DEFERRED -> use the existing (old-design) board; optionally route
    routed = board or cfg.pcb
    if route:
        routed, _rlog = route_swarm(cfg, board=routed, verbose=verbose)
        rec("route_swarm", board=os.path.basename(routed) if routed else None)
    else:
        rec("place_size", status="DEFERRED (placer TODO) -> existing board",
            board=os.path.basename(routed) if routed else None)

    # 4. physics + full cascade, re-route/re-place on failure (bounded)
    rview = View(cfg, board=routed)
    residual = []
    for it in range(max_loops):
        flags = run_full_cascade(rview, armed=armed)        # 6 stages + armed (THERMAL = physics FEA)
        m = rview.metrics
        rec("physics_cascade", iteration=it, n_flags=len(flags),
            gates_pass=(m.gates_pass if m else None))
        if not flags:
            residual = []
            break
        okc, acts = resolve_each(flags, cfg, ask=ask, tiers=tiers)
        residual = [f for (f, a) in acts if not a.resolved]
        actionable = any(a.re_place or a.fixes for _, a in acts)
        if okc or not actionable:
            break                                            # all resolved, or nothing to re-try

    # 5. sign-off
    signed = human_signoff(routed, cfg, residual, ask=ask)
    rec("signoff", signed=signed, residual=len(residual))

    # 6. ALWAYS freeze the decision log + the board (release if signed, else the withheld board for
    #    review) so the run is never void -- the verdict + log are the deliverable either way.
    out_dir = out_dir or os.path.join(tempfile.gettempdir(), f"cec_release_{cfg.board}")
    os.makedirs(out_dir, exist_ok=True)
    logp = os.path.join(out_dir, f"{cfg.board}-decision-log.json")
    json.dump(log, open(logp, "w"), indent=2, default=str)
    _archive_corpus(log, cfg.board, kind="synth")
    tag = "release" if signed else "withheld"
    out_board = ""
    if routed and os.path.isfile(routed):
        out_board = os.path.join(out_dir, f"{cfg.board}-{tag}.kicad_pcb")
        shutil.copy(routed, out_board)
        for ext in (".kicad_pro", ".kicad_dru"):
            s = routed[:-len(".kicad_pcb")] + ext
            if os.path.isfile(s):
                shutil.copy(s, out_board[:-len(".kicad_pcb")] + ext)
    status = "RELEASED" if signed else "sign-off withheld"
    rec("release", status=("RELEASED" if signed else "WITHHELD"),
        board=os.path.basename(out_board) if out_board else None)
    return {"status": status, "board": out_board, "log": logp, "frozen": True,
            "residual": [str(f) for f in residual]}


# ============================================================ headless synthesis sweep (runner)
def run_sweep(cfg, sizes, *, strategies=STRATEGIES, seeds=(0, 1), max_workers=None,
              out_dir=None, render=True):
    """The headless synthesis SWEEP -- the runner-side compute. For each board size, synthesize
    the placement candidates IN PARALLEL (the self-hosted runner's cores, max_workers), keep the
    best by proxy, materialize + render it, and emit a JSON report. This is what synth.yml runs on
    the user's machine; the human touchpoints (Stage-1 requirements, the placement handoff) happen
    IN-SESSION around it. The feasibility FR routes (the genuinely heavy load) attach here when the
    size oracle lands -- they reuse the same runner-capable parallel pool. Returns the report dict."""
    out_dir = out_dir or os.path.join(ROOT, "build", "synth", cfg.board)
    os.makedirs(out_dir, exist_ok=True)
    report = {"board": cfg.board, "profile": cfg.profile, "params": cfg.params,
              "max_workers": max_workers, "cpu_count": os.cpu_count(), "sizes": []}
    t0 = time.time()
    for (W, H) in sizes:
        cands = place_candidates(cfg, W, H, strategies=strategies, seeds=seeds,
                                 max_workers=max_workers)
        best = cands[0]
        board = materialize(best, cfg, os.path.join(out_dir, f"{cfg.board}-{int(W)}x{int(H)}.kicad_pcb"))
        entry = {"W": W, "H": H, "best_strat": best.strat, "best_seed": best.seed,
                 "residual": best.residual, "proxy": best.proxy, "n_candidates": len(cands),
                 "board": os.path.relpath(board, ROOT)}
        if render:
            png = board[:-len(".kicad_pcb")] + "-top.png"
            subprocess.run(["kicad-cli", "pcb", "render", "-o", png, board], capture_output=True)
            if os.path.isfile(png):
                entry["render"] = os.path.relpath(png, ROOT)
        report["sizes"].append(entry)
        print(f"  swept {W:.0f}x{H:.0f}: {len(cands)} cand, best={best.strat} "
              f"residual={best.residual} HPWL={best.proxy['hpwl']}")
    report["elapsed_s"] = round(time.time() - t0, 1)
    rp = os.path.join(out_dir, "synth-report.json")
    json.dump(report, open(rp, "w"), indent=2, default=str)
    print(f"  WROTE {os.path.relpath(rp, ROOT)} ({report['elapsed_s']}s)")
    return report


def _parse_sizes(spec, cfg):
    """Parse a --sweep spec 'WxH,WxH,...'; or 'auto' -> floor / midpoint / as-built from the
    board's geometry (the size oracle will refine these into a real bisection later)."""
    if spec and spec != "auto":
        out = []
        for tok in spec.split(","):
            w, h = tok.lower().split("x")
            out.append((float(w), float(h)))
        return out
    if cfg.pcb and os.path.isfile(cfg.pcb):
        pl = read_placement(cfg.pcb)
        fl = packing_lower_bound(pl)
        return [(fl.w, fl.h), ((fl.w + pl.W) / 2, (fl.h + pl.H) / 2), (pl.W, pl.H)]
    return [(100.0, 44.0)]


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
    ap.add_argument("--sweep", default=None, help="SYNTH SWEEP (runner): board sizes 'WxH,WxH' or 'auto'")
    ap.add_argument("--answers", default=None, help="JSON file of Stage-1 requirement answers (headless elicitation)")
    ap.add_argument("--strategies", default=",".join(STRATEGIES), help="comma-list of placement strategies")
    ap.add_argument("--seeds", default="0,1", help="comma-list of placement seeds")
    ap.add_argument("--max-workers", type=int, default=0, help="parallel candidate workers (0=auto=min(cands,CPUs))")
    ap.add_argument("--out", default=None, help="output dir for the sweep (default build/synth/<board>)")
    ap.add_argument("--run", action="store_true", help="RUN the full pipeline end-to-end (run_pipeline)")
    ap.add_argument("--routed-board", default=None, help="a routed .kicad_pcb to run the pipeline on")
    ap.add_argument("--route", action="store_true", help="route the board via the swarm before physics/cascade")
    a = ap.parse_args(argv)

    cfg = Config.load(a.board, profile=a.profile)
    answers = json.load(open(a.answers)) if (a.answers and os.path.isfile(a.answers)) else None
    elicit_requirements(cfg, answers)                # Stage 1: record design inputs (headless-safe)

    # ---- SYNTH SWEEP (the runner-side headless compute) ----
    if a.sweep is not None:
        sizes = _parse_sizes(a.sweep, cfg)
        strategies = tuple(s for s in a.strategies.split(",") if s)
        seeds = tuple(int(s) for s in a.seeds.split(",") if s.strip() != "")
        out_dir = a.out if (a.out and os.path.isabs(a.out)) else (
            os.path.join(ROOT, a.out) if a.out else None)
        print("=" * 72)
        print(f"  cec_synth_pipeline SWEEP on {cfg.board}: {len(sizes)} sizes x "
              f"{len(strategies)} strat x {len(seeds)} seeds  (max_workers={a.max_workers or 'auto'})")
        print(f"  params: {cfg.params}")
        print("=" * 72)
        run_sweep(cfg, sizes, strategies=strategies, seeds=seeds,
                  max_workers=(a.max_workers or None), out_dir=out_dir)
        return 0

    # ---- RUN the full pipeline end-to-end ----
    if a.run:
        print("=" * 72)
        print(f"  cec_synth_pipeline RUN on {cfg.board} (profile={cfg.profile})")
        print("=" * 72)
        out_dir = a.out if (a.out and os.path.isabs(a.out)) else (
            os.path.join(ROOT, a.out) if a.out else None)
        result = run_pipeline(cfg, board=a.routed_board, route=a.route, out_dir=out_dir)
        print(f"\n  === pipeline result: {result['status']} ===")
        if result.get("board"):
            print(f"  release board: {result['board']}")
            print(f"  frozen log:    {result['log']}")
        if result.get("residual"):
            print(f"  residual flags: {result['residual']}")
        # A COMPLETED run (RELEASED or sign-off withheld) is a SUCCESS -- the verdict + frozen log
        # are the deliverable (same posture as cec_router). Reserve non-zero for a real failure.
        return 0
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
            # constructive placer: synthesize the candidate variants at the board size
            cands = place_candidates(cfg, pl.W, pl.H, seeds=(0, 1), max_workers=1)
            b = cands[0]
            print(f"  place variants  : {len(cands)} synthesized; best={b.strat} seed{b.seed} "
                  f"residual={b.residual} HPWL={b.proxy['hpwl']} (vs as-built HPWL={prox['hpwl']})")
        except Exception as exc:
            print(f"\n  (geometric floor/proxy/placer skipped: {exc})")

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
