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

import cec_toolchain as _tc  # noqa: E402  -- dependency-free; safe on a KiCad-less box (R-05)

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
    # CL-03 Ruling 4: `binding` is ORTHOGONAL to kind and to conf (an advisory
    # netlist assert and an advisory distance check are different kinds;
    # confidence and bindingness are different dimensions). Advisory flags
    # carry the ADV-<entry-id> namespace via entry_id and can NEVER block --
    # enforcement lives at the aggregation points (human_signoff, the cascade
    # loop), never by trusting producers. Default "gate" = full back-compat.
    binding: str = "gate"         # "gate" | "advisory"
    entry_id: str = None          # corpus entry behind an advisory flag

    def __repr__(self):
        w = self.where if isinstance(self.where, str) else type(self.where).__name__
        adv = " ADV" if self.binding == "advisory" else ""
        return f"Flag[{self.kind.value}:{self.name}{adv} conf={self.conf:.2f} @{w}]"


def gate_flags(flags):
    """The blocking subset -- every pass/fail predicate filters through this."""
    return [f for f in flags if getattr(f, "binding", "gate") == "gate"]


def assert_no_advisory(flags, where):
    """Belt and suspenders (CL-03 R4): any code path that HALTS on flags
    asserts no advisory flag reached its input set, so a future consumer
    cannot accidentally block on ADV."""
    adv = [f for f in flags if getattr(f, "binding", "gate") == "advisory"]
    if adv:
        raise AssertionError("%s received %d advisory flag(s) in a blocking "
                             "input set: %s" % (where, len(adv), adv[:3]))


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
        # MV2/MV4 oracle knobs (None = off; a reference path turns on Stage-1 derivation, the MV4
        # composite normalizer, and the MV3 similarity diagnostic):
        "oracle_reference_path": None, "proxy_weights": None,
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
        self._drc_path = None                    # JSON path of the single DRC run (R-02)
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
        # DEGRADE (R-05): on a KiCad-less box, cascade stages that only need the netlist
        # (CONFORMANCE etc.) still run against an empty netlist instead of a traceback.
        if not _tc.have_kicad_cli():
            _tc.warn_once("synth_netlist",
                          "kicad-cli absent -- netlist-derived stages degrade to empty. "
                          + _tc.KICAD_CLI_HINT)
            return Netlist(comps={}, nets={})
        out = os.path.join(tempfile.gettempdir(), f"cec_synth_{os.getpid()}.net")
        subprocess.run([_tc.kicad_cli(), "sch", "export", "netlist", "-o", out, self.sch],
                       capture_output=True)
        return Netlist.from_file(out) if os.path.isfile(out) else Netlist(comps={}, nets={})

    @property
    def metrics(self):
        if self._metrics is None and _HAVE_SCORE and self.board and os.path.isfile(self.board):
            # R-02: feed the View's single DRC run into score() (drc_json=) so metrics and
            # drc() consumers share ONE kicad-cli DRC instead of two runs of the same check.
            self.drc()
            self._metrics = cec_score.score(self.board, drc_json=self._drc_path)
        return self._metrics

    def drc(self):
        if self._drc is None:
            if self.board and os.path.isfile(self.board):
                self._drc, self._drc_path = _run_drc(self.board, keep_json=True)
            else:
                self._drc = {}
        return self._drc

    def erc(self):
        if self._erc is None:
            self._erc = _run_erc(self.sch) if self.sch else {}
        return self._erc


def _run_drc(board, keep_json=False):
    cli = _tc.require_kicad_cli("DRC")          # FAIL FAST with the install hint (R-05)
    # mkstemp: unique per CALL (getpid-keyed names collide under in-process concurrency, R-02)
    fd, out = tempfile.mkstemp(prefix="cec_synth_drc_", suffix=".json")
    os.close(fd)
    subprocess.run([cli, "pcb", "drc", "--exit-code-violations",
                    "--format", "json", "-o", out, board], capture_output=True)
    try:
        d = json.load(open(out))
    except Exception:
        d = {}
    if keep_json:                               # caller reuses the JSON (View.metrics, R-02)
        return d, (out if os.path.isfile(out) else None)
    try:
        os.unlink(out)
    except OSError:
        pass
    return d


def _run_erc(sch):
    cli = _tc.require_kicad_cli("ERC")          # FAIL FAST with the install hint (R-05)
    fd, out = tempfile.mkstemp(prefix="cec_synth_erc_", suffix=".json")  # per-call unique (R-02)
    os.close(fd)
    subprocess.run([cli, "sch", "erc", "--exit-code-violations",
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


def chk_netclass_geometry(view):
    """CL-25: per-net via/track geometry vs the .kicad_pro netclass minima -- the post-route
    enforcement Freerouting cannot provide (it provably ignores netclass widths). Delegates
    to the cec_constraints stable-ID checker; degrades to no-flag when pcbnew is absent."""
    try:
        import pcbnew
        import cec_constraints as K
        board = pcbnew.LoadBoard(view.board)
        ok, detail = K.CHECKERS["netclass-geometry-conformance"](board, view.board, {})[:2]
    except Exception:
        return []                                # R-05 posture: degrade, never crash the stage
    if ok is False:
        return [Flag("netclass geometry under minima", view.board, 0.95, Kind.DFM,
                     {"detail": detail, "check_id": "netclass-geometry-conformance"})]
    return []


DFM = [
    Check("dfm_drc", chk_dfm_drc, Kind.DFM),
    Check("netclass_geometry", chk_netclass_geometry, Kind.DFM),   # CL-25
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


def corpus_advisory_flags(view):
    """CL-03 R1/R4: evaluate the COMPILED ADVISORY set for this board --
    structured staging entries run as the advisory-mode version of their
    deterministic artifact (`ADV-<entry-id>`). Evaluated this wave:
    checker_binding targets (the bound check runs, its fires re-bound
    advisory) and param deltas (R7: staging proposes X against active Y).
    Review NOTES are bundle material, never cascade flags. Degrades to
    no-flags when the compiled tree is absent (run the compiler first)."""
    import dataclasses
    try:
        import cec_corpus_compile as CC
    except Exception:                            # noqa: BLE001
        return []
    flags = []
    arts = CC.load_board_artifacts(view.cfg.board)
    by_name = {c.name: c for stage in STAGES.values() for c in stage}
    for row in arts.get("checker_bindings", []):
        if row.get("binding") != "advisory":
            continue
        chk = by_name.get((row.get("params") or {}).get("checker"))
        if chk is None:
            continue
        for f in chk.run(view):
            flags.append(dataclasses.replace(f, binding="advisory",
                                             entry_id=row.get("entry_id")))
    for d in CC.evaluate_param_deltas():
        flags.append(Flag("ADV-%s: %s" % (d["entry_id"], d["msg"]), view.board or "",
                          0.3, Kind.CONFORM, dict(d), binding="advisory",
                          entry_id=d["entry_id"]))
    return flags


def run_full_cascade(view, *, armed=()):
    """The post-route cascade (pipeline line 43): post-ERC, place-DFM, route-gate,
    MEASURE, DFM-release, CONFORMANCE, + the armed optional analyses + the CL-03
    corpus ADVISORY set. Returns all flags -- callers that HALT must filter
    through gate_flags() (advisory can never block)."""
    flags = []
    flags += run_stage(ERC_BOM, view)            # post-ERC (re-validate the netlist still holds)
    flags += run_stage(PLACEMENT, view)          # place-DFM
    flags += run_stage(ROUTE_GATE, view)         # route gate
    flags += run_stage(MEASURE, view)            # MEASURE
    flags += run_stage(DFM, view)                # DFM-release
    flags += run_stage(CONFORMANCE, view)        # CONFORMANCE
    for opt in armed:                            # armed optional analyses
        flags += opt.run(view) if callable(getattr(opt, "run", None)) else []
    flags += corpus_advisory_flags(view)         # CL-03 ADV (shadow evidence)
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


def proxy_reject(proxy, *, baseline=None, rudy_growth=1.8, thermal_peak_max=2.0, corridor_max=None):
    """Cheap rejection (pipeline proxy_reject): is this size too congested / too hot to be
    worth a real route? CALIBRATED RELATIVE to a *baseline* proxy (the largest size tried,
    which the size oracle knows routed) -- a candidate is rejected when its RUDY peak grows
    past baseline x *rudy_growth* (congestion piled up as the board shrank). RUDY's absolute
    scale is uncalibrated, so with NO baseline we do NOT reject on congestion (a known-routable
    board must pass). The thermal ceiling IS absolute (W concentrated in one proxy cell -> a
    real power-density hotspot; refined later by the electrothermal FEA on the winner).
    Phase 1: *corridor_max* (OPT-IN, default None=off) hard-rejects a placement whose
    corridor_cross exceeds it -- never waste a route on a known sandwich (H2). Left off by
    default so a board whose seed nudge has not yet reached a corridor-clean basin still routes
    its best-ranked candidate (the sort already prefers low corridor_cross); enable it only once
    a clean candidate is reliably produced, or the size oracle could reject every candidate.
    Returns (reject: bool, reasons: list)."""
    reasons = []
    if baseline and proxy["rudy_peak"] > baseline["rudy_peak"] * rudy_growth:
        reasons.append(f"RUDY peak {proxy['rudy_peak']} > {rudy_growth}x baseline "
                       f"{baseline['rudy_peak']} (congestion grew as it shrank)")
    if proxy["thermal_peak_w"] > thermal_peak_max:
        reasons.append(f"thermal peak {proxy['thermal_peak_w']}W > {thermal_peak_max}W (hotspot)")
    if corridor_max is not None and proxy.get("corridor_cross", 0) > corridor_max:
        reasons.append(f"corridor_cross {proxy.get('corridor_cross', 0)} > {corridor_max} "
                       f"(foreign signal forced through a high-current band)")
    return (bool(reasons), reasons)


def proxy_score(proxy, *, weights=None, ref_proxy=None):
    """MV4: the composite placement RANK score (lower = better). With NO reference it returns
    EXACTLY proxy['hpwl'] -- the prior sort key -- so boards with no oracle are byte-for-byte
    unchanged. With a reference each term is normalized by the reference's value (so HPWL / RUDY /
    thermal are commensurate -- the reference sets only the SCALE, never the relative priority) and
    combined HPWL-dominant; the small RUDY/thermal weights break ties toward the less-congested /
    cooler candidate without ever overriding a real wirelength win. *hub_penalty* (MV5, 0=ideal)
    rides in at a small weight when present. Weights are cfg.params['proxy_weights'] knobs."""
    if ref_proxy is None:
        return float(proxy.get("hpwl", 0.0))
    w = {"hpwl": 1.0, "rudy": 0.25, "thermal": 0.15, "hub": 0.5}
    if weights:
        w.update(weights)

    def n(key, rk):
        base = ref_proxy.get(rk) or 0.0
        return (proxy.get(key, 0.0) / base) if base else 0.0

    return (w["hpwl"] * n("hpwl", "hpwl")
            + w["rudy"] * n("rudy_peak", "rudy_peak")
            + w["thermal"] * n("thermal_peak_w", "thermal_peak_w")
            + w["hub"] * float(proxy.get("hub_penalty", 0.0)))


# ============================================================ MV2/MV3: the reference ORACLE
# Use the committed fab-ready board (the oracle) to (MV2) derive the per-board Stage-1 INPUTS that
# fix the synth frame and (MV3) score how close a candidate is to it -- treating the reference like
# the holdout set (docs/placer-upgrade-2026-06-14/anti-overfit-charter.md): VALIDATE against it,
# never tune toward it. The GENERAL rule is "connectors group on an edge by function"; WHICH edge /
# what size / where the mounts go are per-board inputs derived here, tagged board-specific, and never
# laundered into a corpus rule. The similarity score is a DIAGNOSTIC only -- it must never enter a
# sort or score key (that would drive the placer to COPY the board).
_REF_CACHE = {}


def _have_pcbnew():
    try:
        import pcbnew  # noqa: F401
        return True
    except Exception:
        return False


def _is_mount_ref(ref):
    """A mechanical mount-hole reference (synth H1.., or a board's M*/MK*/MH* mounts)."""
    return bool(re.fullmatch(r"(H|M|MK|MH)\d+", ref or ""))


def _edge_of(x, y, x0, y0, W, H):
    """The board edge a point is nearest to, in a frame whose top-left is (x0, y0)."""
    d = {"left": x - x0, "right": (x0 + W) - x, "top": y - y0, "bottom": (y0 + H) - y}
    return min(d, key=d.get)


def _bbox_diag(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys))


def _read_reference_cached(path):
    key = (path, os.path.getmtime(path))
    if key not in _REF_CACHE:
        _REF_CACHE[key] = read_placement(path)
    return _REF_CACHE[key]


def oracle_stage1_answers(cfg, ref_pcb):
    """MV2: derive the per-board Stage-1 INPUTS from a fab-ready reference (the oracle) so the synth
    frame matches reality instead of the broken role->edge default. Returns:
      size_target_wh          : the reference outline (W, H);
      edge_override           : {connector_ref: edge} by binning each connector to its nearest edge;
      mount_pos_override      : {mount_ref: (x, y)} in board-frame-RELATIVE coords;
      antenna_edge            : the edge the PCB-antenna IC faces (for MV5's antenna term);
      respect_antenna_keepout : True when an RF/ESP module is present.
    Per the charter these are board-specific INPUTS (validated, never a general rule). If the
    derivation cannot reproduce the reference's own anchor edges, the derivation is wrong -- the MV2
    validation test rounds this map back through seed_anchors against ground truth."""
    pl = _read_reference_cached(ref_pcb)
    nl = View(cfg).nl
    fp_of = _fp_of(nl)
    x0, y0, W, H = pl.x0, pl.y0, pl.W, pl.H
    out = {"size_target_wh": (round(W, 2), round(H, 2))}
    edge_override = {}
    for ref in fp_of:
        c = nl.comps.get(ref)
        if _role(ref, c.value, c.footprint, nl=nl) not in ("host", "usb", "power_in", "power_out"):
            continue
        if ref not in pl.pos:
            continue
        x, y = pl.pos[ref][0], pl.pos[ref][1]
        edge_override[ref] = _edge_of(x, y, x0, y0, W, H)
    out["edge_override"] = edge_override
    mounts = {ref: (round(p[0] - x0, 2), round(p[1] - y0, 2))
              for ref, p in pl.pos.items() if _is_mount_ref(ref)}
    if mounts:
        out["mount_pos_override"] = mounts
    esp = [r for r in fp_of if "esp32" in (fp_of[r] or "").lower()
           or "rf_module" in (fp_of[r] or "").lower()]
    if esp and esp[0] in pl.pos:
        x, y = pl.pos[esp[0]][0], pl.pos[esp[0]][1]
        out["antenna_edge"] = _edge_of(x, y, x0, y0, W, H)
        out["respect_antenna_keepout"] = True
    return out


def apply_oracle_stage1(cfg):
    """Fill cfg.params with the oracle-derived Stage-1 inputs when cfg.params['oracle_reference_path']
    points at a real reference (and pcbnew is available). Uses setdefault so a value the HUMAN already
    set wins (human answers override the oracle). Idempotent + a no-op with no reference. Returns cfg
    (mutated in place)."""
    refp = cfg.params.get("oracle_reference_path")
    if not (refp and os.path.isfile(refp) and _have_pcbnew()):
        return cfg
    if cfg.params.get("_oracle_applied"):
        return cfg
    try:
        derived = oracle_stage1_answers(cfg, refp)
    except Exception as e:                             # a broken reference must be VISIBLE, not silent
        _tc.warn_once("oracle_stage1", "oracle Stage-1 derivation failed (%r); placing without the "
                      "reference frame -- the result may be structurally wrong: %s" % (refp, e))
        return cfg
    for k, v in derived.items():
        cfg.params.setdefault(k, v)
    cfg.params["_oracle_applied"] = True
    return cfg


def _oracle_reference(cfg):
    """(reference Placement, reference proxy) for the configured oracle, or (None, None). The proxy is
    the normalizer for MV4's composite and the reference HPWL anchor for MV3's similarity."""
    refp = cfg.params.get("oracle_reference_path")
    if not (refp and os.path.isfile(refp) and _have_pcbnew()):
        return None, None
    try:
        pl = _read_reference_cached(refp)
        return pl, placement_proxy(pl)
    except Exception as e:
        _tc.warn_once("oracle_reference", "could not read the oracle reference %r (%s); MV3/MV4 "
                      "diagnostics + normalization disabled this run" % (refp, e))
        return None, None


def oracle_similarity(cand, ref_pl, nl, *, weights=None):
    """MV3: reproduce-the-reference similarity in [0, 1] -- a DIAGNOSTIC ONLY (never a sort/score key;
    optimizing it would drive the placer to COPY the board, the over-fit the charter forbids). Four
    pure structural terms, each board aligned to its own origin: (a) fraction of connectors on the
    same edge; (b) per-anchor distance bucket (<5mm / <15mm); (c) IC-cluster bbox-diagonal ratio
    (cluster tightness); (d) HPWL closeness. The candidate is assumed in a 0-origin frame; the
    reference is translated by (-x0, -y0). A term whose inputs are absent (no connectors / no
    clusters / no reference HPWL) is DROPPED and the score renormalized over the present terms, so
    identity == 1.0 on ANY board and the number stays comparable across boards (a structurally-absent
    term must not dilute it toward 0). Returns (score, details)."""
    w = weights or {"edge": 0.35, "dist": 0.25, "cluster": 0.15, "hpwl": 0.25}
    P = cand.P
    rx0, ry0 = ref_pl.x0, ref_pl.y0
    refpos = {r: (p[0] - rx0, p[1] - ry0) for r, p in ref_pl.pos.items()}
    fp_of = _fp_of(nl)
    conns = [r for r in fp_of
             if _role(r, nl.comps[r].value, nl.comps[r].footprint, nl=nl)
             in ("host", "usb", "power_in", "power_out") and r in P and r in refpos]
    present = {}                                       # term -> value, only when the inputs exist
    # (a) edge match + (b) anchor distance bucket -- both require connectors
    if conns:
        em = sum(_edge_of(P[r][0], P[r][1], 0.0, 0.0, cand.W, cand.H)
                 == _edge_of(refpos[r][0], refpos[r][1], 0.0, 0.0, ref_pl.W, ref_pl.H) for r in conns)
        present["edge"] = em / len(conns)
        ds = [1.0 if (d := math.hypot(P[r][0] - refpos[r][0], P[r][1] - refpos[r][1])) < 5
              else (0.5 if d < 15 else 0.0) for r in conns]
        present["dist"] = sum(ds) / len(ds)
    # (c) IC-cluster tightness ratio
    _a, ics, _s, passives = _classify(nl)
    spec, _series = derive_passive_spec(nl, passives, [r for r in ics if not r.startswith("SW")])
    by_owner = defaultdict(list)
    for pref, (own, _pad) in spec.items():
        by_owner[own].append(pref)
    ratios = []
    for ic, members in by_owner.items():
        cg = [g for g in ([ic] + members) if g in P]
        rg = [g for g in ([ic] + members) if g in refpos]
        if len(cg) < 2 or len(rg) < 2:
            continue
        cd, rd = _bbox_diag([P[g] for g in cg]), _bbox_diag([refpos[g] for g in rg])
        if rd <= 1e-6 and cd <= 1e-6:
            ratios.append(1.0)
        elif rd <= 1e-6 or cd <= 1e-6:
            ratios.append(0.0)
        else:
            ratios.append(min(cd, rd) / max(cd, rd))
    if ratios:
        present["cluster"] = sum(ratios) / len(ratios)
    # (d) HPWL closeness
    rhpwl = hpwl(ref_pl.pads_by_net)
    chpwl = float(cand.proxy.get("hpwl", 0.0))
    if rhpwl:
        present["hpwl"] = max(0.0, 1.0 - abs(chpwl - rhpwl) / rhpwl)
    wsum = sum(w[k] for k in present) or 1.0          # renormalize over PRESENT terms
    score = sum(w[k] * v for k, v in present.items()) / wsum
    details = {k: round(present.get(k, -1.0), 3) for k in ("edge", "dist", "cluster", "hpwl")}
    details.update({"n_conn": len(conns), "ref_hpwl": round(rhpwl, 1), "cand_hpwl": round(chpwl, 1)})
    return round(score, 3), details


# ============================================================ place + proxy + consent
# The constructive placer (pipeline place_with_consent, lines 77-86): seed the anchors
# (connectors at edges by ROLE, mounts at corners), honor user pins, then relative-place
# the rest by net connectivity under a strategy, legalize the overlaps, and score by the
# cheap proxy. A handful of strategy/seed VARIANTS -- and the candidate sweep runs on a
# PARALLEL spawn pool (max_workers), the same runner-capable pattern as cec_fr, so a large
# candidate count offloads onto the self-hosted runner's cores.
STRATEGIES = ("dataflow", "thermal_separated", "compact")


def _role(ref, value, fp, nl=None):
    """Anchor role of a part, or None if it's a free (relative-placed) part. MV2 (general fix): a
    bare J* connector is classified by the FUNCTION of the nets on its pads -- the underlying WHY is
    'function determines edge-grouping' (a connector carrying only power rails + GND is a power
    input, one carrying data is a host port). Passing *nl* enables that net-derived classification;
    without it we fall back to the ref-name heuristic (IN/OUT substrings), which mis-keys a power-in
    connector like J_5VSB (no 'IN' substring) onto the host edge. The WHICH-edge a role lands on is
    a separate, per-board input (oracle edge_override), never baked here."""
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
        return (_connector_net_role(ref, nl) if nl is not None else None) or "host"
    return None


# A connector-scoped power-RAIL test: a power-delivery net carries GND or a voltage-rail TOKEN
# (5V / 5VSB / 3V3 / 12V / VBUS / VCC / VDD / VIN ...), allowing prefixes/suffixes the strict
# end-anchored _is_power_net misses (the Hub names its inputs /MAIN_5V_RAW, /5VSB_RAW, /5V_HOLD).
# Used ONLY for connector role classification -- _is_power_net (decoupling ownership) is untouched.
_RAIL_TOKEN = re.compile(r"(^|/|_)(GND|P?GND|AGND|VBUS|VCC|VDD|VIN|VSB|\+?\d+V\d*)", re.I)
# A net that carries a voltage token but is NOT a current-carrying rail: an ADC sense tap, a
# detect/reference line, or a status flag. These are DATA for connector classification and are NOT
# part of the power-input loop for the MV5 cohesion term.
_PWR_NOT_INPUT = re.compile(r"(SENSE|DET|REF|FLAG)", re.I)


def _is_rail_net(n):
    base = n.rsplit("/", 1)[-1]
    if _PWR_NOT_INPUT.search(n) or _PWR_NOT_INPUT.search(base):
        return False                                  # a sense/detect/reference/flag tap is not a rail
    return bool(_RAIL_TOKEN.search(n)) or bool(_RAIL_TOKEN.search(base))


def _connector_net_role(ref, nl):
    """Classify a connector by the FUNCTION of the nets on its pads (the principle behind edge
    grouping): a pure power-delivery connector (every pad on a power rail or GND, no data/CAN/diff
    net) is a 'power_in'; a connector carrying any non-rail net -- including an ADC sense/reference
    tap like /KVM_3V3_REF, which is DATA not a rail -- is a host/data port. Returns a role or None
    when it cannot tell (no nets resolved -> caller falls back to 'host')."""
    nets = [n for n, nodes in nl.nets.items() if any(r == ref for r, _ in nodes)]
    if not nets:
        return None
    nonrail = [n for n in nets if not _is_rail_net(n)]
    return "power_in" if not nonrail else None


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
        role = _role(ref, c.value, c.footprint, nl=nl)
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


def _signal_nets_of(ref, nets_of):
    """The non-power signal nets a part sits on (the ones that determine its FUNCTION). A net is
    'signal' here if it is not a global rail/GND AND not a sense FORCE net (*_HI/_LO) -- those last
    are the high-current Kelvin path, owned by the shunt, never a generic signal that binds a cap."""
    return {n for n in nets_of.get(ref, set()) if not _is_power_net(n)}


def _is_gnd_net(n):
    base = n.rsplit("/", 1)[-1].upper()
    return base in ("GND", "AGND", "PGND", "GNDA", "GNDD")


def _series_endpoints(nl, pref, owner_cands, nets_of):
    """If *pref* is a 2-terminal SERIES element bridging two DIFFERENT power/signal nets (NEITHER GND),
    return ((endpA, padA, netA), (endpB, padB, netB)) -- the owner ref + its pad nearest each end. The
    canonical case is the SS34 ORing diode between /VBUS (J5) and the +5VSB rail (LDO/Hub feed): both
    nets are rails so it has no SIGNAL owner and used to scatter, but topologically it sits ON the
    VBUS->rail path, so we anchor it on the segment between the two endpoints.

    A part is NOT a series element (-> None, caller falls back to cluster ownership) when:
      * it is not a clean 2-terminal part (one net per pad);
      * either net is GND -- a GND-referenced 2-pin part is DECOUPLING/bypass, not a series pass element
        (this is what stops every bypass cap from being mis-read as a VBUS->rail bridge);
      * both pads share the same net; or
      * an endpoint owner can't be resolved on one of the nets.

    Endpoint selection per net: the owner-candidate (IC/connector/shunt) on that net with the FEWEST
    nodes on the net -- a real point-to-point terminus (J5 on /VBUS, U3 the LDO on +5VSB), not a part
    deep in a fanned plane. The two endpoints must be DISTINCT owners (else it's a stub, not a bridge)."""
    pad_net = {}
    for n in nets_of.get(pref, set()):
        for r, p in nl.nets.get(n, []):
            if r == pref:
                pad_net[p] = n
    if len(pad_net) != 2:
        return None
    (pa, na), (pb, nb) = sorted(pad_net.items())
    if na == nb or _is_gnd_net(na) or _is_gnd_net(nb):
        return None

    def best_endpoint(net):
        cands = []
        for r, p in nl.nets.get(net, []):
            if r in owner_cands and r != pref:
                fan = sum(1 for rr, _ in nl.nets.get(net, []) if rr == r)
                cands.append((fan, r, p))
        if not cands:
            return None
        cands.sort()
        return cands[0][1], cands[0][2]

    A = best_endpoint(na)
    B = best_endpoint(nb)
    if not A or not B or A[0] == B[0]:
        return None
    return (A[0], A[1], na), (B[0], B[1], nb)


def derive_passive_spec(nl, passives, ic_refs, anchor_refs=None):
    """Generalize the hand PASSIVE_SPEC to FUNCTIONAL grouping: ref -> (owner, owner_pad). A part's
    owner is the ANCHOR (IC, connector J*, OR shunt RS*) it shares the most non-power SIGNAL nets with.

    Broadening the owner set beyond ICs (the owner-caught gap 2026-06-27) is what lets a foreign part
    sit at its TRUE function instead of scattering: the USB CC pull-downs couple only to the USB-C
    connector (/USB_CC1,2 reach J5 alone), the DETECT ESD diode couples only to the host RJ-45 (J1.8),
    so each now OWNS onto that connector at the relevant pad -- and a connector-owned cluster naturally
    sits at the board I/O edge, OUT of the SENSEC high-current corridors (functional grouping is also
    the root corridor-cleanliness fix, not the symptom-patch evacuator).

    Roles (all derived from netlist topology, no per-board hardcoding):
      * series-element -- a 2-terminal part whose two nets reach two DIFFERENT anchors (the SS34 between
        J5.VBUS and the +5VSB rail). It has no signal owner (both nets are rails) but sits ON the path;
        we hand it back with owner=the lower-fanout endpoint anchor and a SERIES marker via the second
        return (placed mid-segment by the caller).
      * connector/pull -- strongest SIGNAL coupling is a connector (CC pull-downs -> J5, DETECT ESD ->
        J1): cluster ON that connector at its pad on the shared net.
      * filter/sense -- strongest SIGNAL coupling is an IC (RC/filter caps -> their INA/comparator).
      * decoupling (unchanged) -- a part on power+GND ONLY is BALANCED across the ICs on that rail
        (distributed decoupling). NEVER owned by a connector/shunt (they are not decoupling seats).
      * INA-at-shunt -- the kelvin seat is the existing corridor-spine + anneal connectivity, untouched.

    owner_pad = the owner's pad on a shared net (signal preferred for a connector/IC functional owner;
    power preferred for a pure-decoupling cap). This feeds cec_pcb.auto_cluster -- the same density
    engine -- now also seated at a connector/shunt anchor pad.

    Returns (spec, series): spec = {ref:(owner, pad)}; series = {ref:((aRef,aPad),(bRef,bPad))} for
    series elements (the caller places them on the segment between the two endpoint anchors)."""
    anchor_refs = set(anchor_refs or [])
    nets_of = defaultdict(set)
    for n, nodes in nl.nets.items():
        for r, _p in nodes:
            nets_of[r].add(n)
    ic_set = set(ic_refs)
    # the FUNCTIONAL owner candidates = ICs + connectors + shunts (anything that anchors a cluster)
    owner_cands = list(ic_set | anchor_refs)
    cand_nets = {o: nets_of[o] for o in owner_cands}
    load = {ic: 0 for ic in ic_refs}                    # decoupling-balance counter (ICs only)
    spec, series = {}, {}
    for pref in passives:
        pnets = nets_of.get(pref, set())
        if not pnets:
            continue
        psig = _signal_nets_of(pref, nets_of)
        # 1. strongest NON-POWER signal coupling, over the broadened owner set (IC | connector | shunt)
        sig = []
        for o, on in cand_nets.items():
            if o == pref:
                continue
            shared_sig = psig & on
            if shared_sig:
                # tie-break: more shared signals first, then a connector/shunt over an IC for a part
                # whose ONLY signal reach is that connector (CC pull-down), then a stable ref order.
                is_anchor = 1 if o in anchor_refs else 0
                sig.append((len(shared_sig), is_anchor, o))
        if sig:
            owner = _pick_signal_owner(sig)
            pad = _owner_pad(nl, owner, (psig & nets_of[owner]) or (pnets & nets_of[owner]))
            if pad:
                spec[pref] = (owner, pad)
            continue
        # 2. no signal owner -> SERIES element? (two distinct anchor endpoints on its two nets)
        ep = _series_endpoints(nl, pref, owner_cands, nets_of)
        if ep:
            (aR, aP, _na), (bR, bP, _nb) = ep
            # owner = the lower-fanout endpoint anchor (a real terminus), so the cluster bbox tracks it;
            # the caller overrides its position to the segment midpoint.
            owner = aR
            pad = aP
            spec[pref] = (owner, pad)
            series[pref] = ((aR, aP), (bR, bP))
            continue
        # 3. pure decoupling -> BALANCE across the rail ICs (never a connector/shunt seat)
        pwr_ics = [ic for ic in ic_refs if (pnets & cand_nets.get(ic, set()))]
        if not pwr_ics:
            continue
        owner = min(pwr_ics, key=lambda ic: load[ic])
        load[owner] += 1
        pad = _owner_pad(nl, owner, pnets & nets_of[owner])
        if pad:
            spec[pref] = (owner, pad)
    return spec, series


def _pick_signal_owner(sig):
    """Resolve the strongest-signal-coupling owner from [(n_shared_sig, is_anchor, ref)]. Most shared
    signal nets wins; a connector/shunt anchor breaks a tie over an IC (a part whose signal reach is a
    connector belongs ON it -- the CC pull-down case); ref order is the final deterministic tie-break."""
    return max(sig, key=lambda t: (t[0], t[1], t[2]))[2]


def place_mechanical(W, H, params):
    """Place mounting holes + fiducials per the GENERALIZED Stage-1 asks (mount_holes / fiducials).
    Returns ({ref:(x,y,rot)}, {ref:libid}) for the board-level mechanical parts (H1.., FID1..) that
    are NOT in the netlist. e = edge inset. These become fixed obstacles for the placer (keep parts
    off the screw heads / fiducial windows) and are emitted at materialize time."""
    pos, fp = {}, {}
    e = 3.5   # edge inset of the mount CENTER. NOTE: bumping this to clear the M3-pad edge-clearance DRC
    #           (pad radius ~3.2mm vs 0.5mm rule) collides H3 with the left-edge cable corridor and aborts
    #           the placer worker -- the proper fix is to cohere parts around inset mounts, not just move
    #           the mount (FOLLOWUPS 2026-06-26). 3.5 keeps the placer stable; mount edge-clearance is a
    #           cosmetic finishing DRC the GUI clears.
    # MV2: a per-board mount-position INPUT (board-frame-relative coords derived from the reference
    # oracle, or a spec line) overrides the generic pattern -- mounts are board-specific inputs, not
    # a rule. Clamped in-board so a slightly different sweep size can't push a screw off the edge.
    override = params.get("mount_pos_override") or {}
    if override:
        pts = [(min(W - e, max(e, float(x))), min(H - e, max(e, float(y))))
               for _r, (x, y) in sorted(override.items())]
    else:
        m = params.get("mount_holes", "3_2logic_1conn")
        if m == "4_corner":
            pts = [(e, e), (W - e, e), (e, H - e), (W - e, H - e)]
        elif m == "2_diag":
            pts = [(e, e), (W - e, H - e)]
        else:                                           # 3: 2 logic-side (right) + 1 conn-side (left)
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


_ROLE_EDGE = {"power_in": "top", "power_out": "bottom", "host": "right", "usb": "right"}


def seed_anchors(nl, W, H, fp_of, pins, *, overhang="none", margin=1.5, pad_margin=1.8,
                 edge_override=None):
    """Place connector anchors at board edges. The edge a connector goes to is, by default, its
    role's generic edge (power_in->top, power_out->bottom, host/usb->right); MV2's *edge_override*
    {ref: 'top'|'bottom'|'left'|'right'} REPLACES that per connector -- it is a per-board INPUT
    (derived from the reference oracle by edge-binning, or a spec line), NOT a baked rule, and it is
    what lets a real board spread its connectors over several edges (the Hub's RJ-45 on top,
    power-in on the right, USB on the bottom). With *overhang* != 'none' a connector is seated by its
    PAD BAND at the edge so its body/courtyard hangs OFF-board (pads on-board) -- the area lever the
    condensed boards use, and what lets two tall cable connectors fit a short board. 'none' seats the
    whole courtyard on-board. Honors user pins last. Returns {ref:(x,y,rot)}."""
    edge_override = edge_override or {}
    _VALID_EDGES = ("top", "bottom", "left", "right")
    roles = defaultdict(list)            # ref -> edge (role-default, then per-board override)
    by_edge = defaultdict(list)
    for ref in fp_of:
        r = _role(ref, nl.comps.get(ref, Comp(ref)).value, nl.comps.get(ref, Comp(ref)).footprint,
                  nl=nl)
        if not r or r == "mount":
            continue
        roles[r].append(ref)
        ov = edge_override.get(ref)
        if ov is not None:                            # validate the per-board/human input (M3)
            ov = str(ov).strip().lower()
            if ov not in _VALID_EDGES:
                _tc.warn_once("seed_anchors_edge_" + ref,
                              "seed_anchors: ignoring invalid edge_override[%r]=%r "
                              "(expected one of %s); using the role default"
                              % (ref, edge_override.get(ref), _VALID_EDGES))
                ov = None
        edge = ov or _ROLE_EDGE.get(r)
        if edge:
            by_edge[edge].append(ref)
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

    for edge in ("top", "bottom", "left", "right"):
        place_edge(by_edge.get(edge, []), edge)
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
                  clr=0.4, t0=8.0, cool=0.9985, veto=None):
    """Simulated annealing on the MACRO-BLOCK positions (IC clusters + shunts; anchors fixed) to
    ESCAPE the greedy legalizer's local minimum. Objective = courtyard overlap AREA (heavily) +
    alpha*HPWL to connected parts (stay routable). Being STOCHASTIC, different *seed*s settle into
    different minima -- THAT spread is what makes a huge best-of-N sweep pay off (a deterministic
    placer just yields identical candidates). *veto(ref,(x,y))->bool* (Phase 2) HARD-rejects a move
    that puts a body in a forbidden region (a foreign high-current corridor), independent of T.
    Mutates P in place; returns P."""
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
            for n in sorted(nbrs.get(r, ())):           # sorted: deterministic across processes
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
        if veto is not None and veto(r, (nx, ny)):    # PHASE 2 hard veto -> never enter a foreign band
            T *= cool
            continue
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
            ns = [P[n] for n in sorted(nbrs.get(r, ())) if n in P]   # sorted: process-deterministic
            if not ns:
                continue
            tx = sum(p[0] for p in ns) / len(ns)
            ty = sum(p[1] for p in ns) / len(ns)
            if strat == "compact":                   # pull harder toward neighbours
                tx = 0.7 * tx + 0.3 * P[r][0]
                ty = 0.7 * ty + 0.3 * P[r][1]
            elif strat == "thermal_separated" and r in hot:   # nudge hot parts apart
                for h in sorted(hot):                # sorted: tx is mutated in-loop, order matters
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


# ============================================================ STAGE: CORRIDOR MODEL
# The domain model the placer is blind to (CLAUDE.md action item -2, placement-strategy
# 2026-06-14 §2.1). A high-current cable runs J_IN -> shunt -> J_OUT; that band is reserved
# for the pour (high-current-corridor-keepout / high-current-pour-integrity). A foreign signal
# net forced THROUGH a band cuts the pour on its layer (the eps-8pin ~300C thin-neck failure).
# corridor_cross_count turns "foreign_cross" into a pre-route, pure-geometry NUMBER the placer
# can rank on; build_corridor_model derives the bands from the netlist (no per-board hardcoding),
# reusing _kelvin_pairs + the same CONNECTOR+shunt pad class derive_power_pours pours (the INA SMD
# sense pads excluded) -- so the placement-time corridor and the route-time pour keepout track the
# same J_IN->shunt->J_OUT current path. The band is meaningful only once the corridor is FORMED
# (shunt inline, J_IN/J_OUT aligned); a degenerate near-board-wide band is guarded out, not trusted.
def _pad_xy_global(nl, ref, pad, P, comps):
    """Global (x,y) of *ref*'s *pad* from the placement P, or the part origin / None. Used to put a
    SERIES element on the segment between its two endpoint anchors (the SS34 between J5.VBUS and the
    +5VSB-rail feed)."""
    import cec_pcb
    if ref not in P or ref not in comps:
        return None
    try:
        return cec_pcb.pad_global(ref, pad, {ref: P[ref]}, comps)
    except Exception:
        return (P[ref][0], P[ref][1])


def _net_pads_global(nl, net, P, comps):
    """Global (x,y) of every pad on *net*, from the placement P (ref->(x,y,rot)) + footprints.
    pad_global is a pure footprint-text parse (no pcbnew), so this runs host-side."""
    import cec_pcb
    pts = []
    for ref, pin in nl.nets.get(net, []):
        if ref not in P or ref not in comps:
            continue
        try:
            pts.append(cec_pcb.pad_global(ref, pin, {ref: P[ref]}, comps))
        except Exception:
            pts.append((P[ref][0], P[ref][1]))           # fall back to the part origin
    return pts


def _ref_padcount(nl, ref):
    """How many net-pad nodes *ref* has across the netlist (a 2-pad shunt straddles HI/LO)."""
    return sum(1 for nodes in nl.nets.values() for (r, _p) in nodes if r == ref)


def _corridor_net_role(net, corridor_nets):
    """net -> {power_corridor, decouple, sense, signal}. Only role=='signal' nets can be a
    corridor offender (a power rail / GND / the sense pair itself never 'crosses' its band)."""
    if net in corridor_nets:
        return "power_corridor"
    base = net.rsplit("/", 1)[-1].upper()
    if _POWER_NET.search(net) or base == "GND":
        return "decouple"
    # a Kelvin/INA sense net (force pair _HI/_LO, or the post-filter INA input _P/_N) is part of
    # the cable's own sensing, not a foreign signal -- the 12VHPWR INA240 inputs are /IN{n}_P/_N.
    # (USB_D_P/_N is conservatively swept in too; it lives at the board edge, never the corridor.)
    if net.endswith(("_HI", "_LO", "_P", "_N")) or base.startswith(("SENSEC", "ISENSE")):
        return "sense"
    return "signal"


@dataclass
class Cable:
    """One high-current lane: its Kelvin pair, the straddling shunt, the sense ICs on it, and
    the reserved band rect (global mm, x-inflated by the signal clearance)."""
    base: str                     # e.g. "/SENSEC2"
    hi: str
    lo: str
    shunt: str                    # RS{n} (2-pad straddle), or "" if none resolved
    sense_ics: list               # INA/INA181 refs on hi or lo
    band: tuple                   # (x0, x1, y0, y1)
    formed: bool = True           # False if the corridor is degenerate (J_IN/shunt/J_OUT not collinear)


@dataclass
class CorridorModel:
    """Built once per synth (placement-strategy §2.1). The placer reads this to rank/veto."""
    cables: list                  # [Cable]
    bands: dict                   # base -> (x0, x1, y0, y1)
    corridor_nets: set            # {each cable's hi, lo} -- the ONLY nets allowed inside its band
    hot: set                      # {RS*, J_IN*, J_OUT*, LDO} refs
    sensitive: set                # {INA/INA181, REF3030, ESP32 U1} refs (paired INA exempt for its own band)


def _hot_sensitive(nl):
    """(hot, sensitive) ref sets per §2.1: HOT = shunts + power connectors + LDO; SENSITIVE =
    every current-sense IC + voltage reference + the ESP. Derived from ref + value (no hardcoding)."""
    hot, sensitive = set(), set()
    for ref, c in nl.comps.items():
        v = (c.value or "").upper()
        if ref.startswith("RS") or ("MINI-FIT" in v or "12V" in v or "EPS" in v) and ref.startswith("J"):
            hot.add(ref)
        if ref.startswith("J") and ("IN" in ref.upper() or "OUT" in ref.upper()):
            hot.add(ref)
        if "LP59" in v or "TPS6" in v or "LDO" in v or "REG" in v:
            hot.add(ref)
        if "INA" in v or "REF30" in v or "ESP32" in v:
            sensitive.add(ref)
    return hot, sensitive


def _corridor_band_pads(nl, hi, lo, band_refs, P, comps):
    """Global pads on the HI/LO nets restricted to *band_refs* (the cable connectors + shunt) --
    excludes the INA sense pads, so the band is the J_IN->shunt->J_OUT current path, not the
    sense fan-out. This mirrors cec_fr.derive_power_pours (THT connector pads + the 2-pad shunt)."""
    import cec_pcb
    pts = []
    for net in (hi, lo):
        for ref, pin in nl.nets.get(net, []):
            if ref not in band_refs or ref not in P or ref not in comps:
                continue
            try:
                pts.append(cec_pcb.pad_global(ref, pin, {ref: P[ref]}, comps))
            except Exception:
                pts.append((P[ref][0], P[ref][1]))
    return pts


def _band_formed(band, W, *, max_frac=0.55):
    """A corridor is FORMED only if its band is a tight column -- J_IN/shunt/J_OUT roughly collinear.
    A band wider than max_frac of the board means the shunt is not inline or J_IN/J_OUT are not
    aligned (the synth placer before corridor formation), so corridor_cross over it is meaningless
    (a near-board-wide band can't be straddled -> a FALSE clean). Also flags the 24-pin shared-bus
    connector, whose multi-rail _HI/_LO pads span the whole board (not a per-cable corridor)."""
    x0, x1, _y0, _y1 = band
    return (x1 - x0) <= max(1.0, max_frac * W)


def _shared_bus_connectors(nl):
    """J refs that serve MORE THAN ONE Kelvin pair -- a shared-bus / multi-rail connector (the 24-pin
    ATX J3/J4, the 12VHPWR J3/J4). The per-cable J_IN->shunt->J_OUT corridor model does NOT apply to
    those (a Phase-5 per-pin variant), so the model + the rank key + the checkers all N/A them."""
    serves = defaultdict(set)
    for hi, lo in _kelvin_pairs(nl):
        for net in (hi, lo):
            for r, _ in nl.nets.get(net, []):
                if r.startswith("J"):
                    serves[r].add(hi[:-3])
    return {r for r, ps in serves.items() if len(ps) > 1}


def build_corridor_model(nl, P, comps, *, x_clr=1.5, board_w=None):
    """Derive the CorridorModel (§2.1) from the netlist + a placement. The band of cable n is the
    bbox over the cable CONNECTOR (J*) + shunt pads on its HI/LO nets -- the J_IN->shunt->J_OUT
    current path, the SAME pad class cec_fr.derive_power_pours pours (THT connector + 2-pad shunt;
    the INA's SMD sense pads are EXCLUDED so they don't inflate the band and swallow the channel).
    Inflated *x_clr* mm on the signal-channel (x) sides. A band wider than ~half the board is marked
    NOT formed (shunt not inline / connectors not aligned) -- corridor_cross ignores it (a wide band
    can't be straddled, which would read as a FALSE clean). SHARED-BUS pairs (a connector serving >1
    Kelvin pair, 24-pin/12VHPWR) are SKIPPED -- the per-cable corridor model does not apply, so the
    rank key stays inert there (matching _cable_topology + the checkers). Pure geometry; no pcbnew."""
    if board_w is None:
        board_w = max((P[r][0] for r in P), default=100.0) + 10.0
    shared = _shared_bus_connectors(nl)
    cables, bands, corridor_nets = [], {}, set()
    for hi, lo in _kelvin_pairs(nl):
        corridor_nets.add(hi)
        corridor_nets.add(lo)
        refs_hi = {r for r, _ in nl.nets.get(hi, [])}
        refs_lo = {r for r, _ in nl.nets.get(lo, [])}
        if {r for r in (refs_hi | refs_lo) if r.startswith("J")} & shared:
            continue                                       # shared-bus connector -> Phase-5 variant
        straddle = refs_hi & refs_lo                       # a part on BOTH halves = the shunt
        shunt = next((r for r in sorted(straddle)          # prefer the RS-named shunt
                      if r.startswith("RS") and _ref_padcount(nl, r) == 2),
                     next((r for r in sorted(straddle)
                           if r.startswith("R") and _ref_padcount(nl, r) == 2), ""))
        band_refs = {r for r in (refs_hi | refs_lo) if r.startswith("J")}
        if shunt:
            band_refs.add(shunt)
        pts = _corridor_band_pads(nl, hi, lo, band_refs, P, comps)
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        band = (min(xs) - x_clr, max(xs) + x_clr, min(ys), max(ys))
        base = hi[:-3]
        bands[base] = band
        sense_ics = sorted(r for r in (refs_hi | refs_lo) if r.startswith("U"))
        cables.append(Cable(base=base, hi=hi, lo=lo, shunt=shunt, sense_ics=sense_ics,
                            band=band, formed=_band_formed(band, board_w)))
    hot, sensitive = _hot_sensitive(nl)
    return CorridorModel(cables=cables, bands=bands, corridor_nets=corridor_nets,
                         hot=hot, sensitive=sensitive)


def corridor_cross_count(pads_by_net, bands, corridor_nets, *, signal_only=True, board_w=None):
    """The corridor predictor (placement-strategy §2.3 / §0): how many (foreign SIGNAL net, band)
    pairs are forced THROUGH a high-current band. A net crosses band_n when its pad-bbox y-overlaps
    the band AND it has a pad strictly LEFT of the band x-range AND a pad strictly RIGHT of it -- it
    must terminate on both x-sides, so an IN-PLANE route on the pour layer crosses the corridor. NOTE
    this is a PREDICTOR, not a hard invariant: it is layer-agnostic and has no model of the top/bottom
    channels, so it OVER-counts what a router must actually cut -- a crossing can be routed AROUND (an
    in-plane channel) or UNDER (a non-pour layer). A net that merely terminates at a band edge (one pad
    inside) is NOT a through-cross. A DEGENERATE band
    (wider than ~half the board: shunt not inline / connectors not aligned) is SKIPPED -- it can't be
    straddled, so counting it would read as a false clean; pass *board_w* to enable that guard. Pure
    geometry on the pads_by_net the proxy already builds; 0 over FORMED bands == corridor-clean. NOTE:
    this counts (net, band) pairs, so a net crossing two bands scores 2."""
    usable = {b: rect for b, rect in bands.items()
              if board_w is None or _band_formed(rect, board_w)}
    total = 0
    for net, pts in pads_by_net.items():
        if net in corridor_nets or len(pts) < 2:
            continue
        if signal_only and _corridor_net_role(net, corridor_nets) != "signal":
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
        for base, (X0, X1, Y0, Y1) in usable.items():
            if by1 >= Y0 and by0 <= Y1 and bx0 < X0 and bx1 > X1:
                total += 1
    return total


def channels_of(bands, W, H, *, channel_min=2.0, margin=1.0, board_w=None):
    """The clear top/bottom horizontal CHANNELS above/below ALL formed corridor bands (close-the-loop
    2026-06-27). The route-time corridor keepout (cec_fr.corridor_keepouts) clips each pour+keepout to
    the connector-pad rows -- NOT the full board height -- so the strip above the highest band top and
    below the lowest band bottom is physically clear of pour/keepout on BOTH layers, and a foreign net
    routed along it crosses NO corridor in-plane. Returns (top, bot) as (y0, y1) strips (or None for a
    channel shorter than channel_min). No formed bands -> (None, None) (a shared-bus board, no corridor
    to escape)."""
    formed = [r for b, r in bands.items() if board_w is None or _band_formed(r, board_w)]
    if not formed:
        return None, None
    top_y1 = min(r[2] for r in formed) - margin            # above the highest band top (Y0)
    bot_y0 = max(r[3] for r in formed) + margin            # below the lowest band bottom (Y1)
    top = (margin, top_y1) if (top_y1 - margin) >= channel_min else None
    bot = (bot_y0, H - margin) if (H - margin - bot_y0) >= channel_min else None
    return top, bot


def _body_clear(chan, x0, x1, foreign_bodies):
    """True iff the channel y-strip chan=(y0,y1) is clear of every foreign IC courtyard bbox across
    [x0,x1] -- i.e. a net spanning x0..x1 can run along the channel without hitting a body."""
    if chan is None:
        return False
    cy0, cy1 = chan
    for (fx0, fx1, fy0, fy1) in foreign_bodies:
        if fx1 >= x0 and fx0 <= x1 and fy1 >= cy0 and fy0 <= cy1:
            return False
    return True


def channels_feasible(bands, W, H, *, channel_h=2.5, margin=1.0, board_w=None):
    """The seed-time GROW trigger: True iff the board is tall enough to hold the corridor band height
    plus a usable channel above AND below. When False, the driver grows H (w_grow('H')) and re-seeds --
    a bounded deterministic step, NOT a search (this is what replaces the 384-round hill-climb)."""
    formed = [r for b, r in bands.items() if board_w is None or _band_formed(r, board_w)]
    if not formed:
        return True
    return (min(r[2] for r in formed) - margin) >= channel_h and (H - max(r[3] for r in formed) - margin) >= channel_h


def corridor_cross_channel_aware(pads_by_net, bands, corridor_nets, foreign_bodies, W, H, *,
                                 channel_min=2.0, margin=1.0, signal_only=True, board_w=None):
    """HONEST corridor predictor == predicted post-route F.Cu clips. Same straddle test as
    corridor_cross_count, but a straddle is only COUNTED when it CANNOT escape via a body-clear top/
    bottom channel. The old metric is layer-agnostic + channel-blind, so it OVER-counts and -- crucially
    -- is UNREACHABLE to 0 (the hub->per-cable fan-out is a topological x-straddle invariant for K>=2
    cables). This metric reaches 0 by construction once the channels are reserved (foreign bodies kept
    out of them): every straddle either routes along a clear channel (cost 0) or is the irreducible set
    the loop routes UNDER on B.Cu. Reaching 0 here == corridor-clean by construction. Returns the count
    of straddles genuinely forced through a pour on F.Cu."""
    top, bot = channels_of(bands, W, H, channel_min=channel_min, margin=margin, board_w=board_w)
    usable = {b: rect for b, rect in bands.items()
              if board_w is None or _band_formed(rect, board_w)}
    total = 0
    for net, pts in pads_by_net.items():
        if net in corridor_nets or len(pts) < 2:
            continue
        if signal_only and _corridor_net_role(net, corridor_nets) != "signal":
            continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
        if not any(by1 >= Y0 and by0 <= Y1 and bx0 < X0 and bx1 > X1
                   for (X0, X1, Y0, Y1) in usable.values()):
            continue                                       # doesn't straddle any formed band
        if _body_clear(top, bx0, bx1, foreign_bodies) or _body_clear(bot, bx0, bx1, foreign_bodies):
            continue                                       # escapes along a clear channel -> cuts no pour
        total += 1                                         # genuinely forced through a pour on F.Cu
    return total


# --------------------------------------------------------- Phase 2: corridor FORMATION
# corridor_cross only discriminates once the corridor is FORMED: J_IN above the shunt above J_OUT in
# one tight column. The constructive placer left shunts free (anywhere) and packed J_IN/J_OUT on their
# edges independently, so the band degenerated to ~board width. Phase 2 SEEDS the corridor spine
# deterministically -- align J_OUT under J_IN, seat the shunt on the cable axis at rot 270 (H3) -- so
# the band is a tight column and the anneal then only has to keep foreign bodies OUT of it (the veto).
def _cable_topology(nl):
    """Per per-cable Kelvin pair, the corridor parts from the NETLIST alone (no positions):
    {base, hi, lo, j_in (J* on hi), j_out (J* on lo), shunt (RS 2-pad straddle)}. SHARED-BUS pairs
    (a J ref serving >1 pair -- 24-pin / 12VHPWR) are excluded: their corridor is a Phase-5 per-pin
    variant, not a J_IN->shunt->J_OUT column."""
    pairs = _kelvin_pairs(nl)
    shared = _shared_bus_connectors(nl)
    out = []
    for hi, lo in pairs:
        refs_hi = {r for r, _ in nl.nets.get(hi, [])}
        refs_lo = {r for r, _ in nl.nets.get(lo, [])}
        j_in = sorted(r for r in refs_hi if r.startswith("J") and r not in shared)
        j_out = sorted(r for r in refs_lo if r.startswith("J") and r not in shared)
        straddle = refs_hi & refs_lo
        shunt = next((r for r in sorted(straddle) if r.startswith("RS") and _ref_padcount(nl, r) == 2),
                     next((r for r in sorted(straddle) if r.startswith("R") and _ref_padcount(nl, r) == 2), ""))
        if j_in and j_out and shunt:
            out.append({"base": hi[:-3], "hi": hi, "lo": lo,
                        "j_in": j_in[0], "j_out": j_out[0], "shunt": shunt})
    return out


def _net_pad_xs(nl, comps, ref, net, P):
    """Global x of every pad of *ref* on *net* (the cable's force column)."""
    import cec_pcb
    xs = []
    for r, pin in nl.nets.get(net, []):
        if r != ref:
            continue
        try:
            x, _y = cec_pcb.pad_global(ref, pin, {ref: P[ref]}, comps)
            xs.append(x)
        except Exception:
            pass
    return xs


def _net_pad_centroid_x(nl, comps, ref, net, P):
    """Mean global x of *ref*'s pads on *net* (the cable's force column). J_IN(rot180) pads extend one
    way, J_OUT(rot0) the other from the origin, so aligning ORIGINS misaligns the current columns ~12mm;
    aligning these CENTROIDS is what tightens the band to one connector width (the as-built geometry)."""
    xs = _net_pad_xs(nl, comps, ref, net, P)
    return (sum(xs) / len(xs)) if xs else P[ref][0]


def _seed_corridor_spine(topo, anchors, H, nl, comps, W=None):
    """FORM each per-cable corridor: align J_OUT's LO force-pad column UNDER J_IN's HI force-pad column
    (so the +12V current runs straight J_IN -> shunt -> J_OUT) and seat the shunt on that column axis at
    mid-board, rot 270 (H3 -- HI=upper terminal, Kelvin taps don't cross), all as FIXED anchors. Mutates
    *anchors*; returns the seated shunt refs (dropped from the annealed set so the spine can't be pushed
    off-axis). J_IN keeps the x seed_anchors packed it to (columns stay spaced by connector width). When
    *W* is given the column is CLAMPED so the connector/shunt pads stay on-board (no off-board pads on a
    narrow board)."""
    seated = []
    for c in topo:
        jin, jout, sh = c["j_in"], c["j_out"], c["shunt"]
        if jin not in anchors or jout not in anchors:
            continue
        in_xs = _net_pad_xs(nl, comps, jin, c["hi"], anchors)         # the J_IN +12V column
        col = (sum(in_xs) / len(in_xs)) if in_xs else anchors[jin][0]
        if W and in_xs:
            hw = (max(in_xs) - min(in_xs)) / 2.0 + 1.0               # keep the column's pads on-board
            col = min(max(col, hw), W - hw)
        # shift J_OUT in x so its LO force-pad column lands under the J_IN column
        ox, oy, orot = anchors[jout]
        out_xs = _net_pad_xs(nl, comps, jout, c["lo"], anchors)
        out_col = (sum(out_xs) / len(out_xs)) if out_xs else ox
        anchors[jout] = (ox + (col - out_col), oy, orot)
        anchors[sh] = (col, H / 2.0, 270.0)           # shunt on the force-column axis, rot270
        seated.append(sh)
    return seated


def _corridor_veto(ref, xy, bands, sensitive, paired_ina):
    """HARD veto (placement-strategy §2.2 H1): a HOT/SENSITIVE part body may not sit inside a FOREIGN
    cable's FORMED band. *bands* maps base -> {"band":(x0,x1,y0,y1), "formed":bool}; *paired_ina* maps
    base -> the INA refs EXEMPT for that band (their own cable -- Kelvin needs them adjacent). Returns
    True if *ref* at *xy* violates."""
    if ref not in sensitive:
        return False
    x, y = xy[0], xy[1]
    for base, cab in bands.items():
        if not cab["formed"] or ref in paired_ina.get(base, ()):
            continue
        X0, X1, Y0, Y1 = cab["band"]
        if X0 <= x <= X1 and Y0 <= y <= Y1:
            return True
    return False


def _evacuate_corridors(P, comps, model, *, margin=0.8):
    """RE-PLACE fix (owner-caught 2026-06-27): move any body whose CENTER sits inside a FORMED high-current
    band OUT to the nearest band edge + margin (the corridor is the vertical connector->shunt column, so
    evacuate in x). A foreign body in a SENSEC pour BLOCKS the fill AND its nets can't be routed (the
    net-aware keepout then strands them). EXEMPT: the band's own shunt + sense ICs (Kelvin needs them
    adjacent to the shunt) and edge connectors (J*) / mounts (H*). The anneal veto only covers sensitive
    ICs and the decoupling/DETECT passives are STAMPED into the band via their owner offset, so evacuate
    them here. Returns the list of moved refs (re-legalize them after)."""
    own = {c.shunt for c in model.cables} | {i for c in model.cables for i in c.sense_ics}
    moved = []
    for c in model.cables:
        if not c.formed:
            continue
        X0, X1, Y0, Y1 = c.band
        for ref in list(P):
            if ref in own or ref[:1] in ("J", "H"):
                continue
            pr = P[ref]
            x, y, rot = pr[0], pr[1], (pr[2] if len(pr) > 2 else 0.0)
            if X0 <= x <= X1 and Y0 <= y <= Y1:                  # center inside a high-current band
                nx = (X0 - margin) if (x - X0) < (X1 - x) else (X1 + margin)
                P[ref] = (nx, y, rot)
                moved.append(ref)
    return moved


def _board_corridor_model(board):
    """(model, P) from a live pcbnew board -- the loop/tier entry into the corridor domain. Builds the
    netlist + placement off the board (the same shape as read_placement) and the CorridorModel."""
    comps, nets, P, vals = {}, defaultdict(list), {}, {}
    for fp in board.GetFootprints():
        r = fp.GetReference()
        comps[r] = fp.GetFPIDAsString()
        vals[r] = fp.GetValue()
        pos = fp.GetPosition()
        P[r] = (pos.x / 1e6, pos.y / 1e6, fp.GetOrientationDegrees())
        for pad in fp.Pads():
            nn = pad.GetNetname()
            if nn:
                nets[nn].append((r, pad.GetPadName()))
    nl = Netlist(comps={r: Comp(ref=r, value=vals[r], footprint=comps[r]) for r in comps},
                 nets=dict(nets))
    eb = board.GetBoardEdgesBoundingBox()
    W = max(1.0, eb.GetWidth() / 1e6)
    return build_corridor_model(nl, P, comps, board_w=W), P


def corridor_violations(board_path):
    """SENSITIVE part bodies that sit inside a FOREIGN FORMED corridor band -- the placement-time
    body-in-band fault the §2.2 veto prevents at seed time, here detected on an EXISTING board so a
    cec_place refine pass or a cec_router manager tier can EVICT them (the placement-side analogue of
    the routing corridor-avoid lever). Returns [{"ref", "band":(x0,x1,y0,y1), "base"}], shared-bus
    boards yield [] (no per-cable corridor). Loads its own board (pcbnew)."""
    import pcbnew
    model, P = _board_corridor_model(pcbnew.LoadBoard(board_path))
    bands = {c.base: {"band": c.band, "formed": c.formed} for c in model.cables}
    paired = {c.base: set(c.sense_ics) for c in model.cables}
    out = []
    for ref in sorted(model.sensitive):
        if ref not in P:
            continue
        for base, cab in bands.items():
            if not cab["formed"] or ref in paired.get(base, ()):
                continue
            X0, X1, Y0, Y1 = cab["band"]
            if X0 <= P[ref][0] <= X1 and Y0 <= P[ref][1] <= Y1:
                out.append({"ref": ref, "band": cab["band"], "base": base})
                break
    return out


# ============================================================ MV5: Hub-domain structural terms
# Four net-derived geometric quality terms for a multi-port Hub-class board, each with a stated
# physical WHY (anti-overfit charter rule 1) and NO hardcoded reference value: (1) ganged identical
# connectors want uniform pitch (panel cutouts + cable clearance + matched length); (2) a PCB-antenna
# part radiates off a board edge (RF); (3) the power input chain stays cohesive (loop area + IR drop);
# (4) a diff-pair endpoint sits near its driver (length match). Terms are 0..1 (higher = better);
# hub_penalty = mean(1 - term) folds into the MV4 proxy_score at a small weight. GATED to fire only
# on a board with >=2 ganged RJ-45 ports + an ESP, so cable/sensing modules are untouched.
# The front-end power-input loop is identified TOPOLOGICALLY (not by the reference board's net
# spelling, charter rule 1): it is the set of SMALL-FANOUT rail nets -- the point-to-point INPUT
# rails that connect a power-in connector through the mux/hold-up/LDO -- as distinct from the
# DISTRIBUTED rails (the output plane, the logic rail, GND), which fan out to the whole board. On any
# board the input rails connect O(few) parts while a distribution rail connects O(tens); a fanout cap
# cleanly separates them (Hub: input rails fan 4-5 vs +5VSB 22 / +3V3 16 / GND 78). A per-board
# cfg.params['power_input_nets'] override (substrings) is the escape hatch when a board's topology
# is unusual. USB VBUS falls out naturally (its connector branch lifts its fanout above the cap).
_PWR_LOOP_MAX_FANOUT = 6


@dataclass
class HubModel:
    ports: list            # ganged RJ-45 connector refs (identical footprint)
    esp: str               # the PCB-antenna IC ref ('' if none)
    antenna_edge: str      # the edge the antenna should face ('' = use nearest)
    power_refs: list       # power front-end refs (on a small-fanout input rail)
    usb: str               # the USB connector ref ('' if none)
    active: bool           # whether the hub terms should fire
    esp_cy: tuple = None   # the ESP courtyard (cx,cy,hw,hh) at its placed rotation (for the antenna term)


def _power_input_nets(nl, override=None):
    """The front-end input-loop nets: a per-board override (list of name substrings) if given, else
    the GENERIC topological derivation -- rail nets (voltage token, not a sense/detect/ref/flag tap)
    whose fanout is small enough to be a point-to-point input rail rather than a distributed plane."""
    if override:
        toks = [t.lower() for t in override]
        return [n for n in nl.nets if any(t in n.lower() for t in toks)]
    return [n for n, nodes in nl.nets.items()
            if _is_rail_net(n) and len(nodes) <= _PWR_LOOP_MAX_FANOUT]


def build_hub_model(nl, P, comps, *, antenna_edge="", power_input_nets=None):
    """Identify the Hub-domain anchors from the netlist + placement (pure geometry/strings, no
    pcbnew). *comps* is ref->libid (footprint). active iff >=2 ganged RJ-45 ports + an ESP -- the
    gate that keeps cable modules (1 port) and sensing modules inert. *power_input_nets* is the
    optional per-board override for the front-end loop (see _power_input_nets)."""
    def fp(r):
        return (comps.get(r) or (nl.comps.get(r).footprint if r in nl.comps else "") or "").lower()
    ports = sorted(r for r in P if "rj45" in fp(r) or "8p8c" in fp(r))
    esp = next((r for r in sorted(P) if "esp32" in fp(r) or "rf_module" in fp(r)), "")
    usb = next((r for r in sorted(P) if r.startswith("J") and "usb" in fp(r)), "")
    # the front-end ACTIVE cluster (mux + hold-up cap + LDO), minus the edge-anchored connectors
    # (whose position is set by role, not cohesion): the cohesion WHY is input-loop area / IR drop.
    loop_nets = set(_power_input_nets(nl, power_input_nets))
    prefs = sorted({r for n in loop_nets for r, _p in nl.nets.get(n, ())
                    if r in P and not r.startswith("J")})
    esp_cy = None
    if esp and esp in P and esp in comps:
        try:
            esp_cy = _courtyard_info(comps[esp], P[esp][2])   # courtyard at the placed rotation
        except Exception:
            esp_cy = None
    return HubModel(ports=ports, esp=esp, antenna_edge=antenna_edge, power_refs=prefs, usb=usb,
                    active=(len(ports) >= 2 and bool(esp)), esp_cy=esp_cy)


def hub_score(model, P, W, H):
    """Score the MV5 Hub-domain terms on a placement (P: ref->(x,y,rot)). Returns a dict with each
    present term in 0..1 (higher=better), `active`, and `hub_penalty`=mean(1-term) (0=ideal). Inert
    (hub_penalty 0, active False) when the model is not a Hub. The PCB-antenna courtyard keepout
    (respected at materialize) already forbids parts UNDER the antenna; the antenna TERM here only
    rewards the lobe facing OFF a board edge."""
    if not model.active:
        return {"active": False, "hub_penalty": 0.0}
    terms = {}
    pts = [P[r] for r in model.ports if r in P]
    if len(pts) >= 2:
        edges = [_edge_of(p[0], p[1], 0.0, 0.0, W, H) for p in pts]
        dom = max(set(edges), key=edges.count)
        on_edge = sum(e == dom for e in edges) / len(edges)
        horiz = dom in ("top", "bottom")
        coords = sorted(p[0] if horiz else p[1] for p in pts)
        gaps = [b - a for a, b in zip(coords, coords[1:])]
        mean_g = sum(gaps) / len(gaps)
        stdev = math.sqrt(sum((g - mean_g) ** 2 for g in gaps) / len(gaps)) if gaps else 0.0
        # coefficient of variation (stdev/mean) -- a SCALE-FREE uniformity measure, so the term has
        # no hidden mm-scale knee and reads the same on any board pitch. (With 2 ports there is one
        # gap -> cv 0 -> 1.0 regardless of spacing; the term is meaningful for >=3 ganged ports.)
        cv = (stdev / mean_g) if mean_g > 1e-6 else 0.0
        terms["port_even"] = round((1.0 / (1.0 + cv)) * on_edge, 3)
    if model.esp in P:
        ex, ey = P[model.esp][0], P[model.esp][1]
        want = model.antenna_edge or _edge_of(ex, ey, 0.0, 0.0, W, H)
        if model.esp_cy:                              # distance from the COURTYARD's near edge (incl.
            cx, cy, hw, hh = model.esp_cy             # the antenna keepout) to the board edge -- not
            d = {"left": ex + cx - hw, "right": W - (ex + cx + hw),   # the footprint ORIGIN, which can
                 "top": ey + cy - hh, "bottom": H - (ey + cy + hh)}.get(want, 0.0)  # sit far in.
            d = max(0.0, d)
        else:
            d = {"left": ex, "right": W - ex, "top": ey, "bottom": H - ey}.get(
                want, min(ex, W - ex, ey, H - ey))
        # the reward decays to 0 over a quarter of the SHORT board dimension -- i.e. the antenna IC's
        # courtyard should sit against its edge so its lobe clears the board interior (board-relative
        # scale, no copied reference value; parts UNDER the lobe are handled by the courtyard keepout).
        terms["antenna"] = round(max(0.0, 1.0 - d / (0.25 * min(W, H) or 1.0)), 3)
    pr = [P[r] for r in model.power_refs if r in P]
    if len(pr) >= 2:
        xs = [p[0] for p in pr]
        ys = [p[1] for p in pr]
        frac = ((max(xs) - min(xs)) * (max(ys) - min(ys))) / (W * H) if W * H else 1.0
        # principled linear cohesion (smaller footprint fraction = tighter loop); no magic divisor
        # so the metric never red-by-design penalizes the hand board's own front-end.
        terms["power_cluster"] = round(max(0.0, 1.0 - min(frac, 1.0)), 3)
    if model.usb in P and model.esp in P:
        d = math.hypot(P[model.usb][0] - P[model.esp][0], P[model.usb][1] - P[model.esp][1])
        terms["usb_prox"] = round(max(0.0, 1.0 - d / (math.hypot(W, H) or 1.0)), 3)
    pen = (sum(1.0 - v for v in terms.values()) / len(terms)) if terms else 0.0
    out = {"active": True, "hub_penalty": round(pen, 3)}
    out.update(terms)
    return out


def _seat_antenna_ic(ics, comps, W, H, antenna_edge, *, drop_antenna=False, margin=1.8):
    """Seat the PCB-antenna IC against its antenna EDGE as a fixed anchor, returning (ref,(x,y,rot))
    or (None,None). An RF/ESP module is EDGE-CONSTRAINED (its lobe must radiate off a board edge --
    an RF principle, the WHY), so it is anchored like a connector, not placed as a free IC. Without
    this the synth placer drops the large ESP courtyard center-board onto the ganged ports -> courtyard
    overlaps -> Freerouting routes nothing (measured: 1 wire vs 389 on the hand placement). The EDGE
    is the per-board antenna_edge input; the position is derived from the footprint courtyard, never
    copied from the reference. Rot 0 -- the macro/cluster offsets are built at rot 0, so seating the
    ESP unrotated keeps its decoupling cluster valid; the antenna TERM scores edge PROXIMITY (position),
    independent of rotation. (The precise antenna-faces-off-edge orientation is a refinement.)"""
    if not antenna_edge:
        return None, None
    esp = next((r for r in ics if "esp32" in (comps.get(r, "") or "").lower()
                or "rf_module" in (comps.get(r, "") or "").lower()), None)
    if not esp or esp not in comps:
        return None, None
    cx, cy, hw, hh = _courtyard_info(comps[esp], 0.0, drop_antenna=drop_antenna)
    if antenna_edge == "left":
        x, y = margin + hw - cx, H / 2.0 - cy
    elif antenna_edge == "right":
        x, y = W - margin - hw - cx, H / 2.0 - cy
    elif antenna_edge == "top":
        x, y = W / 2.0 - cx, margin + hh - cy
    else:                                              # bottom
        x, y = W / 2.0 - cx, H - margin - hh - cy
    return esp, (x, y, 0.0)


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
    corridor_cross: int = 0       # OLD (unreachable) predictor -- tiebreak diagnostic only
    corridor_cross_aware: int = 0  # HONEST channel-aware predictor (== F.Cu clips, reachable to 0) -- PRIMARY rank key
    similarity: float = -1.0      # MV3: reproduce-the-reference diagnostic (-1 = not computed)
    similarity_detail: dict = field(default_factory=dict)


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
    #    mechanical asks (mounts + fiducials). A per-cable INTERPOSER must OVERHANG its cable ports
    #    (plug overmold off-board, pads on-board) -- otherwise the connector bodies sit in-board and
    #    crush the J_IN->shunt->J_OUT corridor into the mid-board strip (the as-built boards all
    #    overhang). So default overhang to "edge" when the board has cable corridors, unless the
    #    config overrides. (Owner: "it needs to know how to overhang the ports.")
    _overhang = cfg.params.get("connector_overhang")
    if _overhang is None:
        _overhang = "power_able" if _cable_topology(nl) else "none"
    # MV2: a per-board edge map (oracle-derived or a spec line) overrides the generic role->edge
    # default so a multi-edge board (Hub: RJ-45 top, power-in right, USB bottom) frames correctly.
    anchors = seed_anchors(nl, W, H, fp_of, cfg.pins, overhang=_overhang,
                           edge_override=cfg.params.get("edge_override"))
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
    # 1b. PHASE 2 -- FORM the per-cable corridors: align each J_OUT under its J_IN and seat the shunt
    #     on the cable axis (rot 270) as FIXED anchors, so the band is a tight column the anneal only
    #     has to keep foreign bodies OUT of. Seated shunts drop out of the annealed set (free_shunts).
    seated = _seed_corridor_spine(_cable_topology(nl), anchors, H, nl, comps, W=W)
    free_shunts = [r for r in shunts if r not in seated]
    # 1c. Seat the PCB-antenna IC at its antenna edge as a FIXED anchor (route-unblock + MV5 antenna
    #     term): otherwise the large ESP courtyard lands center-board on the ganged ports -> overlaps
    #     -> Freerouting routes nothing. Keep it in `ics` so its decoupling cluster still builds; drop
    #     it from the ANNEALED set so it stays put at the edge.
    _esp, _esp_pos = _seat_antenna_ic(ics, comps, W, H, cfg.params.get("antenna_edge"),
                                      drop_antenna=drop_antenna)
    if _esp:
        anchors[_esp] = _esp_pos
    anneal_units = [r for r in (ics + free_shunts) if r != _esp]
    # 2. MACRO BLOCKS: auto_cluster each IC's passives in ISOLATION (IC at origin) to learn the
    #    cluster's full bbox + each passive's offset. Placing the bare IC then fanning passives into
    #    a tight gap fails (the condensed boards SPREAD ICs to leave cluster room) -- so we place the
    #    cluster as one macro and legalize with its full bbox, reserving the room.
    #    FUNCTIONAL grouping (owner-caught 2026-06-27): the owner set is broadened to ICs + connectors
    #    + seated shunts, so a part's owner is its true FUNCTIONAL anchor (CC pull-downs -> J5, DETECT
    #    ESD -> J1, SS34 -> the VBUS->+5VSB segment, decoupling -> its IC). A part owned by a FIXED
    #    anchor (connector / seated shunt) clusters relative to that anchor's pad and is STAMPED after
    #    placement (fixed_clusters); only IC/free-shunt owners become annealed macro blocks.
    _seated_shunts = [r for r in shunts if r not in free_shunts]
    _fixed_anchor_refs = set(anchors_roles) | set(_seated_shunts)   # connectors (J*/host/usb) + seated shunts
    spec, series = derive_passive_spec(nl, passives, [r for r in ics if not r.startswith("SW")],
                                       anchor_refs=_fixed_anchor_refs)
    by_owner = defaultdict(list)
    fixed_owner = defaultdict(list)                     # parts owned by a FIXED anchor (connector/shunt)
    for pref, (own, pad) in spec.items():
        if pref in series:                              # series elements are placed mid-segment, not clustered
            continue
        if own in ics + free_shunts:
            by_owner[own].append((pref, pad))
        elif own in _fixed_anchor_refs:
            fixed_owner[own].append((pref, pad))
    drop_kc = tuple(r for r in comps if "esp32" in comps[r].lower()) if drop_antenna else ()
    macro = {}                                          # unit -> (cx,cy,hw,hh) cluster bbox @origin
    cluster_offsets = {}                                # unit -> {pref:(dx,dy,rot)}
    for unit in ics + free_shunts:
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
    # 2b. FIXED-ANCHOR clusters: a part owned by a connector / seated shunt (CC pull-downs on J5, DETECT
    #     ESD on J1) clusters at that anchor's pad. The anchor is already at its final (fixed) position,
    #     so auto_cluster places the parts in absolute coords; we record them for a direct stamp after
    #     the macro placement (they are NOT annealed -- they ride their anchor). This is the functional
    #     grouping that pulls the foreign I/O parts to the board edge connectors, OUT of the corridors.
    fixed_stamp = {}                                    # pref -> (x,y,rot) absolute
    for unit, members in fixed_owner.items():
        if unit not in anchors or unit not in comps:
            continue
        Pfx = {unit: anchors[unit]}
        cec_pcb.auto_cluster(Pfx, comps, {p: (unit, pad) for p, pad in members})
        for p, _pad in members:
            if p in Pfx:
                fixed_stamp[p] = Pfx[p]
    # 3. place the MACROS (ICs+shunts) by connectivity, legalized with their full cluster bbox
    P, _ = relative_place(anchors, nl, W, H, fp_of, drop_antenna=drop_antenna,
                          strat=strat, seed=seed, only=ics + free_shunts, cyinfo_override=macro)
    # 3b. ANNEAL the macros to escape the greedy minimum (compaction + the diversity engine), then
    #     a final greedy snap from the annealed start. Full cyinfo = macro bbox for ICs/shunts,
    #     real courtyard for the fixed anchors.
    cyinfo_all = {}
    for r in P:
        if r in macro:
            cyinfo_all[r] = macro[r]
        elif r in comps:
            cyinfo_all[r] = _courtyard_info(comps[r], P[r][2], drop_antenna=drop_antenna)
    # PHASE 2 hard veto: build the corridor model on the SEEDED spine (J_IN/J_OUT/shunt now placed) and
    # forbid any HOT/SENSITIVE body from entering a FOREIGN cable's formed band (paired INA exempt for
    # its own band -- Kelvin). Keeps the detection ICs + ESP out of the corridors.
    _spine = build_corridor_model(nl, P, comps, board_w=W)
    _bands = {c.base: {"band": c.band, "formed": c.formed} for c in _spine.cables}
    _paired = {c.base: set(c.sense_ics) for c in _spine.cables}
    _sensitive = _spine.sensitive

    def _veto(ref, xy):
        return _corridor_veto(ref, xy, _bands, _sensitive, _paired)

    anneal_macros(P, cyinfo_all, anneal_units, W, H, nbrs=_adjacency(nl), seed=seed, veto=_veto)
    legalize_pack(P, [r for r in anneal_units if r in P], cyinfo_all, W, H, clr=0.4)
    # 4. stamp each cluster's passives relative to its placed unit (rigid macro)
    for unit, offs in cluster_offsets.items():
        if unit not in P:
            continue
        ux, uy, _ur = P[unit]
        for pref, (dx, dy, pr) in offs.items():
            P[pref] = (ux + dx, uy + dy, pr)
    # 4b. FUNCTIONAL stamps: the fixed-anchor (connector/shunt) clusters in their pre-computed absolute
    #     coords, and the SERIES elements on the segment between their two endpoint anchors. The fixed
    #     anchor (J*) does not move during anneal, so its absolute cluster coords are still valid here.
    _func_stamped = []
    for pref, xyr in fixed_stamp.items():
        if pref in comps:
            P[pref] = xyr
            _func_stamped.append(pref)
    for pref, ((aR, aP), (bR, bP)) in series.items():
        if pref not in comps:
            continue
        pa = _pad_xy_global(nl, aR, aP, P, comps)
        pb = _pad_xy_global(nl, bR, bP, P, comps)
        if pa is None or pb is None:
            continue
        mx, my = (pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0   # midpoint of the VBUS->rail segment
        rot = 90.0 if abs(pb[1] - pa[1]) > abs(pb[0] - pa[0]) else 0.0   # orient along the segment
        P[pref] = (mx, my, rot)
        _func_stamped.append(pref)
    # the functional target lands a part AT its connector pad / mid-segment -- which is a DENSE I/O
    # cluster (J1/J5 + the CC pull-downs all share the right edge). Legalize the stamped parts to the
    # NEAREST FREE spot to that target so they keep the functional adjacency but don't overlap a
    # connector body (the SS34 was landing on top of J1/J5/R9 -> 3 of the 5 residual overlaps + a
    # route-time short). Owners (the connectors/shunts) are fixed obstacles, so the parts ride near them.
    if _func_stamped:
        _func_cy = {}
        for r in P:
            if r in macro:
                _func_cy[r] = macro[r]
            elif r in comps:
                _func_cy[r] = _courtyard_info(comps[r], P[r][2], drop_antenna=drop_antenna)
        legalize_pack(P, [r for r in _func_stamped if r in P], _func_cy, W, H, clr=0.4)
    # CORRIDOR EVACUATION: pull any non-belonging body (decoupling / DETECT / detection-amp) OUT of a formed
    # high-current band so the SENSEC pour fills + the nets can route (the anneal veto + passive stamp leave
    # them inside -- the owner-caught re-place issue). Re-legalize only the moved refs so the Kelvin-seated
    # shunt + sense ICs stay put.
    for _ev_round in range(6):                               # iterate: legalize_pack isn't band-aware so it can
        _evm = build_corridor_model(nl, P, comps, board_w=W)  # push an evacuated body back -> re-evacuate; the
        _evac = _evacuate_corridors(P, comps, _evm)           # final round leaves centers OUT (no legalize push-
        if not _evac:                                         # back) -- a center out of the band is enough for
            break                                             # the pour to fill + the net to route around it.
        if _ev_round < 5:
            legalize_pack(P, [r for r in _evac if r in P], cyinfo_all, W, H, clr=0.4)
    res = _count_overlaps(P, comps, drop_antenna=drop_antenna)   # honest DRC-accurate residual
    obj = _placement_obj(cfg, P, W, H, halfext, nl)
    # Phase 1: the corridor model on the FINAL placement -> how many foreign signals are forced
    # through a FORMED high-current band. The rank key + a pre-route reject (proxy_reject). The
    # board_w degeneracy guard means a placement that has NOT yet formed its corridors (shunt not
    # inline / J_IN/J_OUT not aligned -- the pre-Phase-2 state) scores 0 honestly (inert), rather
    # than a FALSE clean from a near-board-wide band. So the rank key only discriminates once
    # corridors are formed (Phase 2) or on a well-formed board.
    model = build_corridor_model(nl, P, comps, board_w=W)
    cc = corridor_cross_count(obj.pads_by_net, model.bands, model.corridor_nets, board_w=W)
    # CHANNEL-AWARE corridor cross (close-the-loop 2026-06-27): the HONEST, REACHABLE metric. The old
    # corridor_cross_count is unreachable to 0 (the hub->per-cable fan-out is a topological straddle
    # invariant), so it stalled the hill-climb at 15-24. cc_aware == predicted post-route F.Cu clips: a
    # straddle that escapes via a body-clear top/bottom channel cuts no pour. It IS reachable to 0 -> the
    # PRIMARY rank key. Foreign bodies = the foreign IC courtyards (NOT the corridor anchors) -- they are
    # what can block a channel.
    _anchors = {c.shunt for c in model.cables} | {i for c in model.cables for i in c.sense_ics}
    _fbodies = []
    for _r, _pr in P.items():
        if _r[:1] == "U" and _r not in _anchors and _r in comps:
            _bx, _by, _brot = _pr[0], _pr[1], (_pr[2] if len(_pr) > 2 else 0)
            _cx, _cy, _hw, _hh = _courtyard_info(comps[_r], _brot)
            _fbodies.append((_bx + _cx - _hw, _bx + _cx + _hw, _by + _cy - _hh, _by + _cy + _hh))
    cc_aware = corridor_cross_channel_aware(obj.pads_by_net, model.bands, model.corridor_nets,
                                            _fbodies, W, H, board_w=W)
    proxy = placement_proxy(obj)
    proxy["corridor_cross"] = cc
    proxy["corridor_cross_aware"] = cc_aware
    # MV5: Hub-domain structural quality (inert/0 on non-Hub boards via build_hub_model's gate).
    hs = hub_score(build_hub_model(nl, P, comps, antenna_edge=cfg.params.get("antenna_edge", ""),
                                   power_input_nets=cfg.params.get("power_input_nets")), P, W, H)
    proxy["hub_penalty"] = hs["hub_penalty"]
    proxy["hub_terms"] = {k: v for k, v in hs.items() if k not in ("active", "hub_penalty")}
    return Candidate(strat=strat, seed=seed, P=P, W=W, H=H, residual=res, proxy=proxy,
                     corridor_cross=cc, corridor_cross_aware=cc_aware)


def _candidate_sort_key(c):
    """The production candidate rank key (best-first): legality, then corridor-cleanliness, then the
    MV4 composite proxy_score. similarity (MV3) is intentionally NOT here -- ranking toward the
    reference is the over-fit the charter forbids; it stays a reported diagnostic only."""
    return (c.residual, c.corridor_cross_aware, c.corridor_cross,
            c.proxy.get("proxy_score", c.proxy.get("hpwl", 0.0)))


def place_candidates(cfg, W, H, *, strategies=STRATEGIES, seeds=(0,), max_workers=None):
    """Generate the placement candidates (strategy x seed), in PARALLEL on a spawn pool.
    Mirrors cec_fr.generate_batch's runner-capable design: a large candidate count offloads
    onto the self-hosted runner's cores (max_workers=0/None -> min(#candidates, CPUs)).
    Returns the candidates sorted best-first by (residual, corridor_cross, proxy_score)."""
    cfg = apply_oracle_stage1(cfg)                   # MV2: fill edge_override/mount/antenna inputs
    ref_pl, ref_proxy = _oracle_reference(cfg)       # MV3/MV4: reference placement + normalizer
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
    # MV4: composite rank score (== HPWL exactly when there is no oracle -> zero behaviour change on
    # boards without a reference). MV3: similarity is a DIAGNOSTIC stored on the candidate, NEVER a
    # sort key (the charter forbids ranking toward the reference).
    weights = cfg.params.get("proxy_weights")
    for c in cands:
        c.proxy["proxy_score"] = round(proxy_score(c.proxy, weights=weights, ref_proxy=ref_proxy), 3)
    if ref_pl is not None:
        try:
            nl = View(cfg).nl
            for c in cands:
                c.similarity, c.similarity_detail = oracle_similarity(c, ref_pl, nl)
        except Exception as e:
            _tc.warn_once("oracle_similarity", "similarity diagnostic failed (%s); candidates "
                          "ranked normally, similarity left unset" % e)
    # Phase 1: corridor_cross is the PRIMARY rank key after legality -- a corridor-clean candidate
    # ALWAYS beats a sandwich, regardless of proxy_score (which used to tie them at residual==0).
    # NOTE similarity (MV3) is DELIBERATELY ABSENT from the key (charter: a diagnostic, never a rank).
    cands.sort(key=_candidate_sort_key)
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
    if verbose:                                        # MV3: surface the top-3 with the diagnostics
        for c in cands[:3]:
            sim = f" sim={c.similarity}" if c.similarity >= 0 else ""
            print(f"    cand {c.strat:16s} seed{c.seed} residual={c.residual} "
                  f"cc={c.corridor_cross} HPWL={c.proxy['hpwl']} "
                  f"score={c.proxy.get('proxy_score')} RUDYpk={c.proxy['rudy_peak']}{sim}")
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
def _ensure_netlist_path(cfg):
    """Return a usable .net path for cfg (MV1): its committed netlist if present, else export it ONCE
    from the schematic to a temp file. Boards like the Hub ship no committed *.net, so Config.load sets
    cfg.net='' and a direct build_board would parse_netlist(open('')) -> FileNotFoundError. Generation
    already tolerates this (View.nl sch-exports); only the materialize WRITE step needed it."""
    if cfg.net and os.path.isfile(cfg.net):
        return cfg.net
    if not (cfg.sch and os.path.isfile(cfg.sch)):
        raise FileNotFoundError(f"cannot materialize {cfg.board!r}: no netlist and no schematic")
    safe = re.sub(r"[^A-Za-z0-9]+", "_", str(cfg.board)).strip("_") or "board"
    out = os.path.join(tempfile.gettempdir(), f"cec_synth_mat_{safe}_{os.getpid()}.net")
    subprocess.run([_tc.kicad_cli(), "sch", "export", "netlist", "-o", out, cfg.sch], capture_output=True)
    if not os.path.isfile(out):
        raise FileNotFoundError(f"netlist export failed for {cfg.sch!r} (kicad-cli)")
    return out


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
    cec_pcb.build_board(out, _ensure_netlist_path(cfg), P3, mounts, logo, cand.W, cand.H, force_argv=False)
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
    if _tc.have_kicad_cli():                    # DEGRADE: render is optional (R-05)
        subprocess.run([_tc.kicad_cli(), "pcb", "render", "-o", png, board], capture_output=True)
    else:
        _tc.warn_once("synth_render", "kicad-cli absent -- skipping render. " + _tc.KICAD_CLI_HINT)
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
    k=0.048 external / 0.024 internal) -> dT = (I/(k·A^0.725))^(1/0.44).
    CL-03 R7: k resolves compiled-PROMOTED first (corpus entries
    thermal.k_ipc.external/internal), else these hand literals -- which a
    promotion PR reconciles (a fitted IPC-2152 k lands as a NEW Class C entry,
    never an edit; see the corpus entry notes)."""
    if cross_mm2 <= 0 or I <= 0:
        return 0.0
    area_mils2 = cross_mm2 * 1550.0031
    hand = 0.048 if external else 0.024
    try:
        import cec_facts
        k = cec_facts.compiled_param(
            "thermal.k_ipc.external" if external else "thermal.k_ipc.internal", hand)
    except Exception:                                         # noqa: BLE001
        k = hand
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
    nets: dict                  # net -> {I, cross_mm2, J, dT, T, poured} (+ transient fields if modelled)
    vias: list                  # worst vias
    shunts: list                # shunt dissipators
    # AM-04 Ruling 9: calibration encodes ACCURACY (has reality vouched for the
    # number), per (family, quantity) -- NEVER conflated with Flag.binding,
    # which encodes AUTHORITY. Uncalibrated thermal gates still BLOCK (the
    # solver's tested property is conservatism; cautious posture stands).
    calibration: str = "uncalibrated"   # "uncalibrated" | "bench:<label-ref>"


# ---- transient current model ---------------------------------------------------------------------
# The cable design current is NOT sustained: the GPU draws a lower SUSTAINED baseline (the "saner
# longer peak") with brief TRANSIENT spikes to the peak (the 40A figure). Steady heating is governed
# by the RMS current over the copper's thermal time constant (a ms spike << tau adds little heat);
# the PEAK still matters for the instantaneous excursion + via fusing (and is what the platform's
# §6.10/§6.13 transient capture measures). Opt-in via cfg.params['transient'] (a dict); absent -> the
# old steady-at-peak behaviour (backward compatible).
def _is_cable_net(net):
    return net.endswith(("_HI", "_LO")) or "12V" in net or net.rsplit("/", 1)[-1] == "GND"


def _rms_current(i_peak, cfg, is_cable):
    """Thermal-effective (RMS-over-tau) current for a cable net under the transient model: a sustained
    baseline = sustained_ratio x peak, at the peak for peak_duty of the time. Non-cable / no-model -> peak."""
    tm = cfg.params.get("transient")
    if not tm or not is_cable:
        return i_peak
    ratio = float(tm.get("sustained_ratio", 0.5))     # the sustained 'longer peak' as a fraction of peak
    duty = float(tm.get("peak_duty", 0.05))           # fraction of time at the transient peak
    i_sus = i_peak * ratio
    return math.sqrt(i_sus * i_sus * (1.0 - duty) + i_peak * i_peak * duty)


def _transient_excursion(dt_steady_at_peak, cfg):
    """Extra dT from ONE transient pulse, bounded by the thermal time constant: a pulse much shorter
    than tau heats far less than its steady value. dT_pulse = dt_steady_peak * (1 - exp(-t_pulse/tau))."""
    tm = cfg.params.get("transient") or {}
    t_s = float(tm.get("peak_ms", 5.0)) / 1000.0
    tau = float(tm.get("tau_s", 10.0))
    return dt_steady_at_peak * (1.0 - math.exp(-t_s / max(tau, 1e-6)))


def _flow_axis(bb):
    """Dominant current-flow axis (0=x, 1=y) from a pad bbox [xmin,xmax,ymin,ymax]: the
    longer pad spread is the source->sink direction. Returns (axis, span_mm)."""
    xext, yext = bb[1] - bb[0], bb[3] - bb[2]
    return (0, xext) if xext >= yext else (1, yext)


def _min_cut(features):
    """Serial min-cut of a net's copper along its flow axis. `features` is a list of
    (lo, hi, cross_mm2, ext_cross_mm2, is_pour): each spans [lo,hi] on the flow axis and
    contributes `cross_mm2` of copper there (ext_cross_mm2 = the part on an OUTER layer).
    The thermally-governing cross-section is the BOTTLENECK -- the minimum, over positions
    copper occupies, of the PARALLEL copper crossing that position. Series segments do NOT
    add (summing them was the AM-04 segment-sum debt).

    When the net is POURED, the pour is the force conductor (the platform routes high
    current as copper area, not traces); the cut is then restricted to the pour's flow
    span so a zero-current sense/Kelvin stub that merely shares the net but sits OUTSIDE
    the force path cannot masquerade as a 40A series neck (the over-correction the naive
    min-cut would make -- the mirror of the old over-count). Returns (min_cross_mm2,
    external_bool) where external reflects the bottleneck cut's layer (IPC k, debt #3).
    Degenerate (all zero-width) -> the single largest feature."""
    if not features:
        return 0.0, False
    pours = [f for f in features if f[4]]
    span = (min(f[0] for f in pours), max(f[1] for f in pours)) if pours else None
    pts = sorted({p for f in features for p in (f[0], f[1])})
    best, best_ext = None, False
    for i in range(len(pts) - 1):
        mid = 0.5 * (pts[i] + pts[i + 1])
        if span and not (span[0] <= mid <= span[1]):         # outside the force-path span
            continue
        tot = ext = 0.0
        for lo, hi, cs, ecs, _ in features:
            if lo <= mid <= hi:
                tot += cs
                ext += ecs
        if tot > 0 and (best is None or tot < best):
            best, best_ext = tot, (ext >= 0.5 * tot)
    if best is None:                                         # all zero-width (or empty span)
        lo, hi, cs, ecs, _ = max(features, key=lambda f: f[2])
        return cs, (cs > 0 and ecs >= 0.5 * cs)
    return best, best_ext


def _via_cluster_sizes(pts, thr=3.0):
    """Single-linkage cluster of via positions (mm); returns the cluster size for each via.
    Vias at ONE layer transition (a via pair / stitching field) are a parallel group the
    net current splits across; the old nvias[net] divisor split across EVERY via on the
    net, under-counting current per via on a multi-transition net (debt fix #2)."""
    n = len(pts)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if abs(pts[i][0] - pts[j][0]) <= thr and abs(pts[i][1] - pts[j][1]) <= thr:
                parent[find(i)] = find(j)
    from collections import Counter
    roots = [find(i) for i in range(n)]
    cnt = Counter(roots)
    return [cnt[roots[i]] for i in range(n)]


def electrothermal_solve(board_path, cfg, *, ambient=None):
    """Solve the analytic electrothermal model on a ROUTED board: per high-current net the
    SERIAL MIN-CUT copper cross-section (the bottleneck cut perpendicular to current flow,
    NOT the sum of every series segment + pour), the Picard dT; per via the per-transition-
    cluster split current + barrel cross-section; per shunt the I^2R dissipation. Returns a
    ThermalResult. (Approximations documented inline; this is the analytic first model.)"""
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

    # Per-net copper as flow-axis features for the SERIAL MIN-CUT. The old model summed
    # every track segment + pour layer into one parallel cross -- but series copper adds
    # RESISTANCE, not area, so the effective cross was inflated and dT read optimistic
    # (~5x on the cable lanes; the AM-04 micro-board pins the 3-segment case at 1.044 sum
    # vs 0.348 min-cut). Outer-layer membership is read by layer ID (rename-proof) and
    # drives the IPC k per feature, not by whether the net happens to be poured.
    OUTER = (pcbnew.F_Cu, pcbnew.B_Cu)
    feat = defaultdict(list)              # net -> [(lo, hi, cross_mm2, ext_cross_mm2)]
    poured = set()
    via_pts = defaultdict(list)           # net -> [(x, y, drill_mm)]
    flow = {n: (_flow_axis(pad_bb[n])[0] if n in pad_bb else 1) for n in cur}
    for t in b.GetTracks():
        net = t.GetNetname(); I = cur.get(net, 0.0)
        if I <= 0:
            continue
        ax = flow.get(net, 1)
        if t.Type() == pcbnew.PCB_TRACE_T:
            ext = t.GetLayer() in OUTER
            cs = (t.GetWidth() / 1e6) * ((2 if ext else 1) * CU_OZ_MM)
            s, e = t.GetStart(), t.GetEnd()
            a0 = (s.x if ax == 0 else s.y) / 1e6
            a1 = (e.x if ax == 0 else e.y) / 1e6
            feat[net].append((min(a0, a1), max(a0, a1), cs, cs if ext else 0.0, False))
        elif t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            via_pts[net].append((p.x / 1e6, p.y / 1e6, t.GetDrillValue() / 1e6))
    for z in b.Zones():
        net = z.GetNetname(); I = cur.get(net, 0.0)
        if I <= 0:
            continue
        poured.add(net)
        ax = flow.get(net, 1)
        for layer in z.GetLayerSet().Seq():
            ext = layer in OUTER
            try:
                poly = z.GetFilledPolysList(layer)
                area = poly.Area() / 1e12                     # planar mm^2 (per layer)
            except Exception:
                area = 0.0
            if area <= 0:
                continue
            bbp = poly.BBox()                                # pour extent ALONG the flow axis
            lo = (bbp.GetLeft() if ax == 0 else bbp.GetTop()) / 1e6
            hi = (bbp.GetRight() if ax == 0 else bbp.GetBottom()) / 1e6
            span = max(hi - lo, 2.0)
            cs = (area / span) * ((2 if ext else 1) * CU_OZ_MM)   # avg perpendicular cut
            feat[net].append((lo, hi, cs, cs if ext else 0.0, True))

    cross, cross_ext = {}, {}             # net -> serial min-cut (mm^2), bottleneck-is-outer
    for net, fl in feat.items():
        mc, ext = _min_cut(fl)
        if mc > 0:
            cross[net], cross_ext[net] = mc, ext

    net_res = {}
    max_T, max_dT = ambient, 0.0
    for net, I_peak in cur.items():
        if I_peak <= 0 or cross.get(net, 0) <= 0:
            continue
        c = cross[net]
        is_cable = _is_cable_net(net)
        I = _rms_current(I_peak, cfg, is_cable)              # thermal-effective (RMS-over-tau) current
        ext = cross_ext.get(net, net in poured)              # IPC k by the bottleneck's actual layer
        dt = _picard_dt(I, c, ambient, external=ext)
        rec = {"I": round(I, 1), "cross_mm2": round(c, 4), "J": round(I / c, 1),
               "dT": round(dt, 1), "T": round(ambient + dt, 1), "poured": net in poured}
        if cfg.params.get("transient") and is_cable and I_peak > I + 0.05:
            dt_peak = _picard_dt(I_peak, c, ambient, external=ext)   # if peak were sustained
            exc = _transient_excursion(dt_peak, cfg)
            rec.update({"I_peak": round(I_peak, 1), "J_peak": round(I_peak / c, 1),
                        "dT_transient": round(exc, 1), "T_peak": round(ambient + dt + exc, 1)})
        net_res[net] = rec
        T_hot = rec.get("T_peak", rec["T"])
        if T_hot > max_T:
            max_T, max_dT = T_hot, dt + rec.get("dT_transient", 0.0)

    vias = []
    for net, pts in via_pts.items():
        I_peak = cur.get(net, 0.0)
        if I_peak <= 0:
            continue
        is_cable = _is_cable_net(net)
        I = _rms_current(I_peak, cfg, is_cable)
        if net in poured:
            # Vias stitching a poured net (GND plane, mirror-poured force lane) are PARALLEL
            # paths of one plane-to-plane transition the plane copper already bridges -- the
            # current spreads across all of them, it is not funneled through any single via.
            sizes = [len(pts)] * len(pts)
        else:
            # A non-poured net's vias are discrete SERIES transitions; the full net current
            # crosses each, split only among the vias co-located at that transition cluster.
            sizes = _via_cluster_sizes([(x, y) for x, y, _ in pts])
        for idx, (x, y, drill) in enumerate(pts):
            iv = I / max(1, sizes[idx])                      # split among the vias at THIS transition
            cv = math.pi * drill * 0.025                     # plated barrel ~25um
            dt = _picard_dt(iv, cv, ambient, external=True)
            rec = {"net": net, "I_via": round(iv, 2), "drill_mm": round(drill, 3),
                   "J": round(iv / cv, 1) if cv else 0, "dT": round(dt, 1), "T": round(ambient + dt, 1)}
            if cfg.params.get("transient") and is_cable and cv and I_peak > I + 0.05:
                rec["J_peak"] = round((I_peak / max(1, sizes[idx])) / cv, 1)   # peak J for fusing
            vias.append(rec)
    vias.sort(key=lambda v: -v["T"])

    shunts = []
    for fp in b.GetFootprints():
        if not fp.GetReference().startswith("RS"):
            continue
        R = _r_value_ohms(fp.GetValue()) or 0.5e-3
        # The shunt carries the current of the net it STRADDLES -- read it from the
        # per-net current model (which honours cfg.params['net_currents'] overrides;
        # essential on per-pin boards like the 12VHPWR where the per-cable default
        # would be ~4x high). Fall back to cable_current_A when the pads' nets are
        # not in the model (e.g. an unnetted fixture).
        pad_amps = [cur.get(p.GetNetname(), 0.0) for p in fp.Pads()]
        I_peak = max(pad_amps) if any(a > 0 for a in pad_amps) \
            else cfg.params.get("cable_current_A", 40.0)
        I = _rms_current(I_peak, cfg, True)                  # shunt heats on RMS (steady I^2R)
        P = I * I * R
        dt = P * cfg.params.get("shunt_rth_CW", 25.0)        # 2512 shunt+pad thermal resistance °C/W
        shunts.append({"ref": fp.GetReference(), "R_ohm": R, "I": round(I, 1), "P_W": round(P, 3),
                       "dT": round(dt, 1), "T": round(ambient + dt, 1)})
        if ambient + dt > max_T:
            max_T, max_dT = ambient + dt, dt

    return ThermalResult(ambient=ambient, max_T=round(max_T, 1), max_dT=round(max_dT, 1),
                         nets=net_res, vias=vias[:8], shunts=shunts,
                         calibration=_calibration_state(cfg, "hotspot"))


def _calibration_state(cfg, quantity):
    """AM-04 R9: the (family, quantity) calibration latch. A CL-13 bench label
    for THIS board family and THIS quantity flips it; a hotspot label says
    nothing about DC-IR. Reads the ledger label stream; degrades to
    'uncalibrated' when no ledger/labels exist."""
    try:
        import cec_facts
        import cec_ledger
        board = getattr(cfg, "board", None) or ""
        b = cec_facts.find_board(board)
        fams = set(b["families"]) if b else {board}
        for rec in cec_ledger.read_decisions():
            lab = rec.get("label") or rec.get("extra") or {}
            if (lab.get("quantity") == quantity
                    and set(lab.get("families") or [lab.get("family")]) & fams):
                return "bench:%s" % rec.get("decision_id", rec.get("run_id", "label"))
    except Exception:                                         # noqa: BLE001
        pass
    return "uncalibrated"


def physics_gates(res, cfg):
    """J / temperature-rise / derating gates on a ThermalResult. Transient-aware: a SUSTAINED over-temp
    (computed on the RMS current) is the real blocking thermal fault; a brief TRANSIENT peak excursion
    is gated against a higher allowance (T_max_transient_C); peak current density is checked against a
    FUSING ceiling (J_fuse_A_mm2) rather than the sustained J ceiling."""
    flags = []
    dt_max = cfg.params.get("dT_max_C", 30.0)
    t_max = cfg.params.get("T_max_C", 105.0)
    t_max_tr = cfg.params.get("T_max_transient_C", t_max + 20.0)   # brief-excursion allowance
    j_max = cfg.params.get("J_max_A_mm2", 100.0)             # SUSTAINED current density ceiling
    j_fuse = cfg.params.get("J_fuse_A_mm2", 400.0)           # TRANSIENT peak fusing ceiling
    for net, r in res.nets.items():
        if r["T"] > t_max or r["dT"] > dt_max:               # SUSTAINED over-temp -- the real fault
            flags.append(Flag("conductor over-temp", net, 0.85, Kind.MEASURE,
                              {"dT": r["dT"], "T": r["T"], "I": r["I"], "cross_mm2": r["cross_mm2"],
                               "poured": r["poured"], "limit_dT": dt_max, "limit_T": t_max}))
        elif r.get("T_peak", r["T"]) > t_max_tr:             # brief peak excursion past its allowance
            flags.append(Flag("transient over-temp", net, 0.6, Kind.MEASURE,
                              {"T_peak": r.get("T_peak"), "dT_transient": r.get("dT_transient"),
                               "I_peak": r.get("I_peak"), "limit_T_transient": t_max_tr}))
        elif r["J"] > j_max:
            flags.append(Flag("current density high", net, 0.6, Kind.MEASURE,
                              {"J": r["J"], "limit": j_max}))
        elif r.get("J_peak", 0) > j_fuse:                    # transient peak J -> fusing risk
            flags.append(Flag("transient fusing risk", net, 0.6, Kind.MEASURE,
                              {"J_peak": r.get("J_peak"), "I_peak": r.get("I_peak"), "limit_fuse": j_fuse}))
    for v in res.vias:
        if v["T"] > t_max or v["dT"] > dt_max:
            flags.append(Flag("via over-temp", v["net"], 0.7, Kind.MEASURE, dict(v, limit_T=t_max)))
            break                                            # one representative via flag
    for v in res.vias:
        if v.get("J_peak", 0) > j_fuse:
            flags.append(Flag("transient via fusing", v["net"], 0.6, Kind.MEASURE, dict(v, limit_fuse=j_fuse)))
            break
    for s in res.shunts:
        if s["T"] > t_max or s["dT"] > dt_max:
            flags.append(Flag("shunt over-temp", s["ref"], 0.8, Kind.MEASURE, dict(s, limit_T=t_max)))
    # AM-04 R9: every thermal flag carries the calibration mark. Accuracy label
    # ONLY -- the flags stay binding="gate" (blocking-with-the-mark; demoting
    # uncalibrated thermal to advisory would convert an honesty label into an
    # authority downgrade, the exact conflation the binding field prevents).
    for f in flags:
        f.detail.setdefault("calibration", getattr(res, "calibration", "uncalibrated"))
    return flags


def field_electrothermal_solve(board_path, cfg, *, grid_mm=None, backend="auto"):
    """HIGH-FIDELITY thermal tier: the 2.5D FIELD solve (scripts/cec_thermal2d.py -- the solver the owner
    built; see memory cec-thermal2d-field-solver). It rasterizes the REAL copper, couples layers through
    REAL via barrels, and sub-grid anti-aliases thin traces, so it resolves the LOCAL current-density /
    temperature hotspots the lumped per-net electrothermal_solve AVERAGES AWAY -- it catches a shredded-
    pour neck at ~2635 A/mm^2 / 858C that the analytic reports as 83 A/mm^2 / 181C. Returns a result
    shaped for physics_gates (nets dict + max_T/max_dT), with the raw field result on .field. Needs the
    cec_thermal2d deps (shapely + scipy/pyamg; optional cupy for the GPU backend on the 5090)."""
    import cec_thermal2d as t2d
    import pcbnew
    from types import SimpleNamespace
    amb = float(cfg.params.get("ambient_C", 50.0))
    grid = grid_mm if grid_mm is not None else float(cfg.params.get("thermal_grid_mm", 0.15))
    b = pcbnew.LoadBoard(board_path)
    board_nets = sorted({t.GetNetname() for t in b.GetTracks() if t.GetNetname()})
    ncur = _net_currents(cfg, board_nets)
    fr = t2d.solve_board_thermal(board_path, net_currents=ncur, grid_mm=grid, ambient=amb, backend=backend)
    nets = {}                                                 # per-net maxT/maxJ already capture the via +
    for net, mt in fr.per_net_maxT.items():                   # neck hotspots (the field couples via barrels)
        I = ncur.get(net, 0.0)
        if not I or I <= 0:
            continue
        nets[net] = {"T": mt, "dT": mt - amb, "I": I, "J": fr.per_net_maxJ.get(net, 0.0),
                     "cross_mm2": 0.0, "poured": True}
    return SimpleNamespace(max_T=fr.max_T, max_dT=fr.max_T - amb, ambient=amb, grid_mm=grid,
                           nets=nets, vias=[], shunts=[], calibration="uncalibrated", field=fr)


def physics(board_path, cfg, armed=()):
    """Pipeline physics(routed, cfg, armed): run the electrothermal FEA + J/T/derating gates.
    (PDN and other armed deep analyses hang here too when present.) Returns (ThermalResult, flags).
    CEC_THERMAL_FIELD=1 (or cfg.params['thermal_field']) selects the HIGH-FIDELITY field solve
    (field_electrothermal_solve / cec_thermal2d) instead of the lumped analytic -- the field tier is
    what catches the local shredded-neck / via-fusing hotspots. Falls back to the analytic on any field-
    solver error (deps absent, etc.) so the gate never silently skips."""
    res = None
    if os.environ.get("CEC_THERMAL_FIELD") == "1" or cfg.params.get("thermal_field"):
        try:
            res = field_electrothermal_solve(board_path, cfg)
        except Exception:                                     # noqa: BLE001 -- analytic fallback, never skip
            res = None
    if res is None:
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
    human present is NOT a release). Returns True iff signed off.
    CL-03 R4: the blocking count filters binding==gate -- an advisory flag can
    NEVER feed it (it is still SHOWN to an interactive human, labeled ADV)."""
    blocking = [f for f in flags if f.conf >= 0.5
                and getattr(f, "binding", "gate") == "gate"]
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

    # 4. physics + full cascade, re-route/re-place on failure (bounded).
    #    CL-03 R4: the loop, resolve ladder, and sign-off see GATE flags only --
    #    advisory fires are recorded (shadow evidence) and shown, never driving
    #    escalation, never blocking, never feeding the residual.
    rview = View(cfg, board=routed)
    residual, adv_fires = [], []
    for it in range(max_loops):
        all_flags = run_full_cascade(rview, armed=armed)    # 6 stages + armed + ADV
        adv_fires = [f for f in all_flags
                     if getattr(f, "binding", "gate") == "advisory"]
        flags = gate_flags(all_flags)
        m = rview.metrics
        rec("physics_cascade", iteration=it, n_flags=len(flags),
            n_advisory=len(adv_fires), gates_pass=(m.gates_pass if m else None))
        if not flags:
            residual = []
            break
        assert_no_advisory(flags, "run_pipeline cascade loop")
        okc, acts = resolve_each(flags, cfg, ask=ask, tiers=tiers)
        residual = [f for (f, a) in acts if not a.resolved]
        actionable = any(a.re_place or a.fixes for _, a in acts)
        if okc or not actionable:
            break                                            # all resolved, or nothing to re-try

    # 4b. ADV fires -> the per-run ledger sidecar (CL-03 R4: per-fire capture
    #     from day one -- PC-01, capture cannot be retroactive; AM-06 sharding).
    if adv_fires:
        try:
            import cec_ledger
            cec_ledger.adv_fires(
                [{"entry_id": f.entry_id, "board": cfg.board,
                  "locus": str(f.where)[:200], "binding": f.binding,
                  "name": f.name} for f in adv_fires], board=cfg.board)
        except Exception as exc:                             # noqa: BLE001
            rec("adv_ledger_degraded", error=repr(exc))

    # 5. sign-off (human_signoff itself ALSO filters binding -- belt+suspenders)
    assert_no_advisory(residual, "human_signoff residual")
    signed = human_signoff(routed, cfg, residual, ask=ask)
    rec("signoff", signed=signed, residual=len(residual), advisory=len(adv_fires))

    # 6. ALWAYS freeze the decision log + the board (release if signed, else the withheld board for
    #    review) so the run is never void -- the verdict + log are the deliverable either way.
    out_dir = out_dir or os.path.join(tempfile.gettempdir(), f"cec_release_{cfg.board}")
    os.makedirs(out_dir, exist_ok=True)
    logp = os.path.join(out_dir, f"{cfg.board}-decision-log.json")
    # SB-01: the frozen log carries the determinism manifest (self-describing log).
    try:
        import cec_ledger
        log["manifest"] = cec_ledger.manifest()
    except Exception:
        pass
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
    # SB-01: durable ledger line (fail-safe; a missing cec-runs repo never breaks a run).
    try:
        import cec_ledger
        lrec = cec_ledger.append(board=cfg.board, mode="synth-run",
                                 verdict=("RELEASED" if signed else "WITHHELD"),
                                 board_file=(out_board or None), input_board=cfg.pcb,
                                 netlist=(cfg.net if cfg.net and os.path.isfile(cfg.net) else None),
                                 artifact=os.path.relpath(out_dir, ROOT) if out_dir.startswith(ROOT) else out_dir,
                                 parent_run_id=os.environ.get("CEC_PARENT_RUN_ID"))
        print(f"  [ledger] {lrec['run_id']}")
    except Exception as e:
        print(f"  [ledger] append skipped: {type(e).__name__}: {e}", file=sys.stderr)
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
                 "residual": best.residual, "corridor_cross": best.corridor_cross,
                 "proxy": best.proxy, "proxy_score": best.proxy.get("proxy_score"),
                 "similarity": best.similarity, "similarity_detail": best.similarity_detail,
                 "n_candidates": len(cands), "board": os.path.relpath(board, ROOT)}
        if render and _tc.have_kicad_cli():     # DEGRADE: render is optional (R-05)
            png = board[:-len(".kicad_pcb")] + "-top.png"
            subprocess.run([_tc.kicad_cli(), "pcb", "render", "-o", png, board], capture_output=True)
            if os.path.isfile(png):
                entry["render"] = os.path.relpath(png, ROOT)
        elif render:
            _tc.warn_once("synth_render", "kicad-cli absent -- skipping render. " + _tc.KICAD_CLI_HINT)
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
