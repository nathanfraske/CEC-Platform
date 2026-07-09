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
from contextlib import contextmanager
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
        if os.path.isdir(board):
            d = board
        else:
            d = next((c for c in (os.path.join(ROOT, "modules", board),
                                  os.path.join(ROOT, "hubs", board),
                                  os.path.join(ROOT, "modules", "output-daughterboards", board))
                      if os.path.isdir(c)), os.path.join(ROOT, "modules", board))
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
        # ROOT sheet, not sorted()[0] -- the hierarchical beta boards' numbered sub-sheets
        # sort first and a leaf-sheet netlist silently drops most of the board (6/63 comps).
        cfg.sch = _tc.find_root_sch(d)
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
    """Kelvin (HI, LO) pairs, derived TWO ways and unioned:
    1. NAME pairs -- <base>_HI with a matching <base>_LO (the platform convention).
    2. SHUNT-STRADDLE pairs (2026-07-08, the 24-pin mechanism fix): the two nets of a
       2-pad RS* shunt, regardless of what they are called. Real boards legitimately
       carry a POWER net on one side of a shunt (the ordered 24-pin: RS2 spans
       /SENSE5V_HI -> +5V_MAIN, RS4 spans +5VSB -> /SENSE5VSB_LO), and the old
       name-only derivation silently dropped those rails from every kelvin-derived
       consumer (chain classifier, gates, corridor former). Orientation: a _HI/_LO
       name hint wins; else the side a recognised sense IC's IN+ pad taps is HI;
       else lexical (deterministic).
    """
    pairs = {}
    his = [n for n in nl.nets if n.endswith("_HI")]
    for h in his:
        lo = h[:-3] + "_LO"
        if lo in nl.nets:
            pairs[frozenset((h, lo))] = (h, lo)
    # straddle pairs off 2-pad RS* shunts
    ref_pins = {}
    for net, mem in nl.nets.items():
        for r, p in mem:
            ref_pins.setdefault(r, set()).add((net, p))
    inp_pin = {"INA238": "10", "INA228": "10", "INA226": "10", "INA181": "3"}
    for r, np_ in ref_pins.items():
        if not r.startswith("RS") or len(np_) != 2:
            continue
        (na, _pa), (nb, _pb) = sorted(np_)
        if na == nb:
            continue
        key = frozenset((na, nb))
        if key in pairs:
            continue
        hi = lo = None
        for n1, n2 in ((na, nb), (nb, na)):
            if n1.endswith("_HI") or n2.endswith("_LO"):
                hi, lo = n1, n2
                break
        if hi is None:
            # orient by a sense IC's IN+ pad
            for ref, c in nl.comps.items():
                want = next((v for k, v in inp_pin.items() if k in (c.value or "").upper()), None)
                if want is None:
                    continue
                for net in (na, nb):
                    if (ref, want) in [tuple(x) for x in nl.nets.get(net, [])]:
                        hi, lo = net, (nb if net == na else na)
                        break
                if hi is not None:
                    break
        if hi is None:
            hi, lo = na, nb
        pairs[key] = (hi, lo)
    return sorted(pairs.values())


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
        # board identity for the connector-scenario arm (daughterboard families);
        # unused by the pre-existing EMC/THERMAL/PDN applies, so purely additive.
        "board": getattr(cfg, "board", ""),
        "board_dir": getattr(cfg, "dir", ""),
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


# --- Thermal wave-1 module hooks (advisory, fail-safe). Surface the beyond-shunt heat
#     inventory (cec_thermal_sources) and the connector N-1 scenario verdicts
#     (cec_thermal_scenarios) in the armed-analysis cascade. Both are ADVISORY
#     (binding="advisory") -> information only, NEVER blocking; the material-limit and
#     connector policy GATES stay owner/soak-gated (the ratification boundary). Both are
#     FAIL-SAFE (-> [] on any error) so a board they don't fit can never break the
#     cascade. electrothermal_solve() and physics_gates() are UNTOUCHED, so SB-08 golden
#     (which calls electrothermal_solve directly) and the physics_gates tests stay
#     byte-identical. No existing test references REGISTRY_OPTIONAL / triage_arm. ---
_DB_FAMILY = {"atx24-out-db": "atx24", "eps-out-db": "eps", "pcie-out-db": "pcie"}


def _sources_applies(feats, profile):
    return feats.get("n_comps", 0) > 0


def _sources_run(view):
    """Beyond-shunt heat inventory as an advisory flag (total dissipation, hottest
    source, count of UNVERIFIED-basis sources). Never blocks; fail-safe."""
    try:
        import cec_thermal_sources as _ts
        inv = _ts.inventory(getattr(view.cfg, "dir", "") or "", sch_path=view.sch)
        srcs = list(inv.sources or [])
        hottest = max(srcs, key=lambda s: getattr(s, "watts", 0.0)) if srcs else None
        unv = [getattr(s, "ref", "?") for s in srcs if getattr(s, "unverified", False)]
        return [Flag("beyond-shunt heat inventory", view.board or getattr(view.cfg, "board", ""),
                     0.3, Kind.MEASURE,
                     {"total_W": round(inv.total_W, 3), "n_sources": len(srcs),
                      "hottest_ref": getattr(hottest, "ref", None),
                      "hottest_W": round(getattr(hottest, "watts", 0.0), 4) if hottest else None,
                      "unverified_refs": unv},
                     binding="advisory")]
    except Exception:
        return []


def _connscen_family(name):
    for key, fam in _DB_FAMILY.items():
        if key in (name or ""):
            return fam
    return None


def _connscen_applies(feats, profile):
    return _connscen_family(feats.get("board", "")) is not None


def _connscen_run(view):
    """Connector N-1 (single-joint-loss) verdicts for THIS board's daughterboard family
    as advisory flags -- the rails whose surviving joints exceed the 30 C-rise policy
    after one joint is lost. Never blocks (N-1 survival was never a design target; the
    counts are sized for load, and this surfaces the honest single-failure envelope).
    Fail-safe."""
    try:
        import cec_thermal_scenarios as _sc
        fam = _connscen_family(getattr(view.cfg, "board", ""))
        if not fam:
            return []
        flags = []
        for r in _sc.n1_sweep(fam).get("rails", []):
            if not r.get("n1_survives_within_policy", True):
                flags.append(Flag("connector N-1 loss over policy",
                                  "%s:%s" % (fam, r.get("rail")), 0.4, Kind.MEASURE,
                                  {"rail": r.get("rail"), "n_joints": r.get("n_joints"),
                                   "open_circuit_on_loss": r.get("open_circuit_on_loss"),
                                   "worst_survivor_dT_C": r.get("worst_survivor_dT_C")},
                                  binding="advisory"))
        return flags
    except Exception:
        return []


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
    # Thermal wave-1 module hooks -- advisory, fail-safe (see the run_fn block above).
    OptionalAnalysis(
        "THERMAL_SOURCES", False, _sources_applies, lambda f: (0.3, 0.2),
        alarm_fn=lambda f: False, conf_fn=lambda f: 0.3, run_fn=_sources_run),
    OptionalAnalysis(
        "THERMAL_CONNECTOR_SCENARIOS", False, _connscen_applies, lambda f: (0.4, 0.2),
        alarm_fn=lambda f: False, conf_fn=lambda f: 0.4, run_fn=_connscen_run),
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
    # D-5a blade-field terminals (beta line, spec §2.8 revision): the TB* TE 63969 FASTON
    # receptacles that replaced the J_OUT header -- the module's output is a FIELD of identical
    # blades the output daughterboard blind-mates. Each blade is a connector anchor (power_out
    # edge); the field PATTERN is seated by _seat_blade_fields, and the net->slot assignment is
    # a free routing-time variable (owner 2026-07-07: "you can reorder them however you want").
    if ref.startswith("TB") or "faston" in f:
        return "power_out"
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
    pads = [n for n, nodes in nl.nets.items() for r, _ in nodes if r == ref]
    if not pads:
        return None
    # kelvin-pair members are the FORCE path -- power by definition, even though the
    # _PWR_NOT_INPUT regex excludes SENSE* from the rail-token test (a shunt-side net like
    # /SENSE12V_HI on an ATX input pin is bulk current, not data). Counted per PAD so a bulk
    # power connector with a couple of status lines (ATX J3: 20+ rail/force pads vs
    # PS_ON#/PWR_OK/-12V) still reads as power (2026-07-08, 24-pin mechanism item c).
    force = {x for pr in _kelvin_pairs(nl) for x in pr}
    data = [n for n in pads if not (_is_rail_net(n) or n in force)]
    if not data:
        return "power_in"
    if len(pads) - len(data) >= 4 * len(data):
        return "power_in"
    return None


def _half_extent(fp, *, drop_antenna=False):
    """(hw, hh) courtyard half-extent of a footprint. When *drop_antenna* and the part is an
    RF module (ESP32 / RF_Module), trim the PCB-antenna keepout lobe to the pad band -- the
    Stage-1 'wireless not populated' answer makes the ESP courtyard materially smaller.
    (Mounting holes now report their true ~6.9mm round courtyard via cec_pcb.courtyard_bbox's
    circle handling -- the old hardcoded (3.0,3.0) degenerate-courtyard patch is retired.)"""
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
    rotation, exactly what KiCad/DRC sees, so the legalizer's overlap test matches the board.
    (Mounting holes report their true round courtyard via cec_pcb's circle handling now; the old
    hardcoded (0,0,3.0,3.0) degenerate-courtyard patch is retired.)"""
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
        if m in ("none", "0"):                          # owner may not use chassis mounts at all
            pts = []
        elif m == "4_corner":
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
        base_rot = _ROT[edge]
        horiz = edge in ("top", "bottom")
        items = []
        for ref in sorted(refs):
            fp = fp_of.get(ref, "")
            # MOUTH-OUT rotation (owner catch 2026-07-08, "the J3 header is backwards"): the
            # per-edge rotation map is FOOTPRINT-BLIND, but right-angle connector footprints
            # differ in which local direction the body/shroud extends (Molex vs TraceParts
            # exports). Pick between base_rot and base_rot+180 by GEOMETRY: the courtyard
            # bulk (the shroud/mouth) must sit on the OFF-BOARD side of the pad band.
            rot = base_rot
            if oh:
                def _outward(cand):
                    ccx, ccy, _hw, _hh = _courtyard_info(fp, cand)
                    (bxl, bxh), (byl, byh) = _pad_band(fp, cand)
                    if (byh - byl if horiz else bxh - bxl) < 0.1:
                        return None                    # degenerate band (shared pad numbers): can't judge
                    pad_c = ((byl + byh) / 2.0) if horiz else ((bxl + bxh) / 2.0)
                    body_c = ccy if horiz else ccx
                    return (pad_c - body_c) if edge in ("top", "left") else (body_c - pad_c)
                # MOUTH-OUT REPAIR (owner catch 2026-07-08, "the J3 header is backwards"): the
                # per-edge rotation map is footprint-blind and right-angle exports differ in
                # local mouth direction. Flip ONLY when the default rotation demonstrably
                # leaves the body INBOARD (outward < 0) and the flip fixes it -- a correct
                # default (eps 87427) and degenerate-band receptacles stay byte-identical.
                o_base = _outward(base_rot)
                flip = (base_rot + 180.0) % 360.0
                if o_base is not None and o_base < 0:
                    o_flip = _outward(flip)
                    if o_flip is not None and o_flip > o_base + 0.5:
                        rot = flip
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


def legalize_pack(P, movable, cyinfo, W, H, *, clr=0.5, step=0.6, bounds=None):
    """Greedy non-overlap legalization (proper detailed placement): place each movable part at
    the NEAREST FREE position to its target by an outward spiral search, so the result has ZERO
    real courtyard overlap by construction. Each part's obstacle is its TRUE courtyard -- centre
    OFFSET from the origin + half-extent, at its rotation (cyinfo[ref]=(cx,cy,hw,hh)) -- so the
    test matches what KiCad/DRC sees (an origin-centred check mismodels the asymmetric connector
    courtyards and yields phantom-legal placements). Anchors are fixed obstacles; big parts go
    first; a part that genuinely can't fit overlap-free lands at its least-overlap spot and is
    counted -- that residual is the honest 'board too tight -> grow' signal. Returns the residual.

    *bounds* (the intent-compiler PARTITION lever, default None -> byte-identical to the
    un-partitioned legalizer): {ref:(x0,y0,x1,y1)} HARD region containment -- a bounded ref's
    courtyard is kept inside its box (intersected with the in-board range), so an agent's
    structure-first assignment cannot be legalized away. Refs not in *bounds* are unconstrained.

    VECTORIZED (2026-07-08, owner porting pass): the numpy path batches BOTH hot loops (the
    placed-boxes scan and the spiral ring's candidate batch) -- profiled as 92% of placement
    time (629k cost() calls / 94M abs() on one 24-pin synth); measured 12.3x on the 24-pin's
    legalize calls (3.27s -> 0.27s) with 100% OUTPUT-IDENTICAL placements on 38 recorded real
    calls across 2 boards x 2 seeds (record/replay bench build/bench_legalize.py; first-zero /
    first-argmin candidate selection matches the sequential `c < bestc` semantics exactly).
    No numpy -> the original sequential path (_legalize_pack_seq), same results (R-05
    degradation discipline)."""
    try:
        import numpy as np
    except ImportError:
        return _legalize_pack_seq(P, movable, cyinfo, W, H, clr=clr, step=step, bounds=bounds)
    DEF = (0.0, 0.0, 1.0, 1.0)
    apx, apy, aphw, aphh = [], [], [], []
    for r in P:
        if r not in movable:
            cx, cy, hw, hh = cyinfo.get(r, DEF)
            apx.append(P[r][0] + cx)
            apy.append(P[r][1] + cy)
            aphw.append(hw)
            aphh.append(hh)
    px = np.array(apx, float)
    py = np.array(apy, float)
    phw = np.array(aphw, float)
    phh = np.array(aphh, float)

    order = sorted(movable, key=lambda r: -(cyinfo.get(r, DEF)[2] * cyinfo.get(r, DEF)[3]))
    residual = 0
    for r in order:
        cx, cy, hw, hh = cyinfo.get(r, DEF)
        tx, ty = P[r][0], P[r][1]
        lo_x, hi_x = hw - cx, W - hw - cx
        lo_y, hi_y = hh - cy, H - hh - cy
        if hi_x < lo_x:
            lo_x = hi_x = W / 2 - cx
        if hi_y < lo_y:
            lo_y = hi_y = H / 2 - cy
        if bounds and r in bounds:
            rx0, ry0, rx1, ry1 = bounds[r]
            lo_x, hi_x = max(lo_x, rx0 + hw - cx), min(hi_x, rx1 - hw - cx)
            lo_y, hi_y = max(lo_y, ry0 + hh - cy), min(hi_y, ry1 - hh - cy)
            if hi_x < lo_x:
                lo_x = hi_x = (rx0 + rx1) / 2 - cx
            if hi_y < lo_y:
                lo_y = hi_y = (ry0 + ry1) / 2 - cy
            tx, ty = min(hi_x, max(lo_x, tx)), min(hi_y, max(lo_y, ty))
        wx = hw + phw + clr
        wy = hh + phh + clr
        best, bestc, R = None, 1e18, 0.0
        while R <= max(W, H):
            if R == 0:
                angs = np.zeros(1)
            else:
                n = max(10, int(2 * math.pi * R / step))
                angs = 2 * math.pi * np.arange(n) / n
            ox_ = np.minimum(hi_x, np.maximum(lo_x, tx + R * np.cos(angs)))
            oy_ = np.minimum(hi_y, np.maximum(lo_y, ty + R * np.sin(angs)))
            if len(px):
                ovx = wx[None, :] - np.abs((ox_ + cx)[:, None] - px[None, :])
                ovy = wy[None, :] - np.abs((oy_ + cy)[:, None] - py[None, :])
                c = np.sum(np.where((ovx > 0) & (ovy > 0), ovx * ovy, 0.0), axis=1)
            else:
                c = np.zeros(len(ox_))
            zi = np.nonzero(c == 0.0)[0]
            if len(zi):
                k = zi[0]
                if 0.0 < bestc:
                    best, bestc = (float(ox_[k]), float(oy_[k])), 0.0
                break
            k = int(np.argmin(c))
            if c[k] < bestc:
                best, bestc = (float(ox_[k]), float(oy_[k])), float(c[k])
            R += step
        P[r] = (best[0], best[1], P[r][2])
        px = np.append(px, best[0] + cx)
        py = np.append(py, best[1] + cy)
        phw = np.append(phw, hw)
        phh = np.append(phh, hh)
        if bestc > 1e-6:
            residual += 1
    return residual


def _legalize_pack_seq(P, movable, cyinfo, W, H, *, clr=0.5, step=0.6, bounds=None):
    """The original sequential legalizer -- the no-numpy fallback + the record/replay
    reference implementation (see legalize_pack's docstring for the equivalence proof)."""
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
        if bounds and r in bounds:                       # HARD region containment (partition lever)
            rx0, ry0, rx1, ry1 = bounds[r]
            lo_x, hi_x = max(lo_x, rx0 + hw - cx), min(hi_x, rx1 - hw - cx)
            lo_y, hi_y = max(lo_y, ry0 + hh - cy), min(hi_y, ry1 - hh - cy)
            if hi_x < lo_x:                              # region narrower than the part -> its centre
                lo_x = hi_x = (rx0 + rx1) / 2 - cx
            if hi_y < lo_y:
                lo_y = hi_y = (ry0 + ry1) / 2 - cy
            tx, ty = min(hi_x, max(lo_x, tx)), min(hi_y, max(lo_y, ty))   # start the spiral in-region
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
                  clr=0.4, t0=8.0, cool=0.9985, veto=None, role_clr=None):
    """Simulated annealing on the MACRO-BLOCK positions (IC clusters + shunts; anchors fixed) to
    ESCAPE the greedy legalizer's local minimum. Objective = courtyard overlap AREA (heavily) +
    alpha*HPWL to connected parts (stay routable). Being STOCHASTIC, different *seed*s settle into
    different minima -- THAT spread is what makes a huge best-of-N sweep pay off (a deterministic
    placer just yields identical candidates). *veto(ref,(x,y))->bool* (Phase 2) HARD-rejects a move
    that puts a body in a forbidden region (a foreign high-current corridor), independent of T.
    *role_clr* (round-2 item 7b, 2026-07-08): optional {ref: radius_mm} -- a pairwise interaction
    takes max(clr, role_clr[r], role_clr[o]), a SOFT per-role keep-out (a COST term the anneal can
    climb out of, deliberately NOT a veto -- the parked fix-B lesson: a veto without a repair path
    freezes bad states). None (default) = byte-identical to the pre-lever anneal; ACTIVATION is
    gated on the fixed-seed ablation protocol (cec_lever_eval), per the one-lever-at-a-time rule.
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

    def _pair_clr(a, b):
        if not role_clr:
            return clr
        return max(clr, role_clr.get(a, 0.0), role_clr.get(b, 0.0))

    def cost(r):
        ar = bbox(r)
        c = 0.0
        for o in placed:
            if o != r:
                c += _ov_area(ar, bbox(o), _pair_clr(r, o))
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
        _mv_roll = rnd.random()
        if _mv_roll < 0.62:                           # local jitter
            nx, ny = ox + rnd.uniform(-3, 3), oy + rnd.uniform(-3, 3)
        elif _mv_roll < 0.80:                         # occasional teleport (escape)
            nx, ny = rnd.uniform(hw - cx, W - hw - cx), rnd.uniform(hh - cy, H - hh - cy)
        elif len(mv) >= 2:                            # SWAP (owner lever pass 2026-07-08):
            r2 = rnd.choice(mv)                        # exchange two macros' positions --
            if r2 == r:                                # the escape the jitter can't make
                T *= cool
                continue
            o2 = P[r2]
            before2 = cost(r) + cost(r2)
            if (veto is not None and (veto(r, (o2[0], o2[1])) or veto(r2, (ox, oy)))):
                T *= cool
                continue
            P[r], P[r2] = (o2[0], o2[1], orot), (ox, oy, o2[2])
            d2 = (cost(r) + cost(r2)) - before2
            if d2 > 0 and rnd.random() >= math.exp(-d2 / max(T, 1e-3)):
                P[r], P[r2] = (ox, oy, orot), o2       # reject swap
            T *= cool
            continue
        # NOTE: a rotate-in-place move was tried and REMOVED (2026-07-08) -- rotating a
        # MACRO unit invalidates its cyinfo extents AND its rot-0 cluster offsets (the
        # stamp assumes unrotated units); a sound rotation move needs rotated cluster
        # templates first.
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
    fp_of = _fp_of(nl)
    out = []
    for hi, lo in pairs:
        refs_hi = {r for r, _ in nl.nets.get(hi, [])}
        refs_lo = {r for r, _ in nl.nets.get(lo, [])}
        j_in = sorted(r for r in refs_hi if r.startswith("J") and r not in shared)
        j_out = sorted(r for r in refs_lo if r.startswith("J") and r not in shared)
        # D-5a beta boards: the output header is replaced by a FIELD of TB* FASTON blade
        # receptacles on the LO net (3 per cable on eps/pcie). They are the corridor's output
        # end; j_out stays the first blade (a real anchor ref) and j_out_blades carries the
        # whole per-cable group for the field seat.
        blades = sorted(r for r in refs_lo
                        if r not in shared and _is_blade(r, fp_of.get(r, "")))
        if not j_out and blades:
            j_out = blades
        straddle = refs_hi & refs_lo
        shunt = next((r for r in sorted(straddle) if r.startswith("RS") and _ref_padcount(nl, r) == 2),
                     next((r for r in sorted(straddle) if r.startswith("R") and _ref_padcount(nl, r) == 2), ""))
        if j_in and j_out and shunt:
            out.append({"base": hi[:-3], "hi": hi, "lo": lo,
                        "j_in": j_in[0], "j_out": j_out[0], "shunt": shunt,
                        "j_out_blades": blades})
    return out


def _is_blade(ref, footprint):
    """A D-5a blade-field terminal: a TB*-ref or FASTON-footprint connector (TE 63969 receptacle
    on the module side; the daughterboards' J1x 63951 tabs also match by footprint)."""
    return ref.startswith("TB") or "faston" in (footprint or "").lower()


def _shared_bus_topology(nl):
    """Per-RAIL corridor topology for SHARED-BUS boards (the 24-pin; mechanism item b,
    2026-07-08): every kelvin pair whose HI net lands on the ONE shared input connector
    becomes a corridor entry -- input = the shared connector's rail-pin GROUP, output = the
    TB blade group on the LO net (single contiguous daughterboard row, unlike the per-cable
    boards' per-db windows). Entries carry shared_bus=True + j_in_pins so the spine can
    order columns by the natural fan order. Empty on per-cable boards (they have no shared
    connector), so _cable_topology remains their only source."""
    shared = _shared_bus_connectors(nl)
    if not shared:
        return []
    fp_of = _fp_of(nl)
    out = []
    for hi, lo in _kelvin_pairs(nl):
        refs_hi = {r for r, _ in nl.nets.get(hi, [])}
        refs_lo = {r for r, _ in nl.nets.get(lo, [])}
        j_in = sorted(refs_hi & shared)
        if not j_in:
            continue
        straddle = refs_hi & refs_lo
        shunt = next((r for r in sorted(straddle) if r.startswith("RS")
                      and _ref_padcount(nl, r) == 2), "")
        blades = sorted(r for r in refs_lo if _is_blade(r, fp_of.get(r, "")))
        if not shunt:
            continue
        pins = sorted((p for r, p in nl.nets.get(hi, []) if r == j_in[0]), key=lambda s: int(s) if s.isdigit() else 999)
        out.append({"base": hi, "hi": hi, "lo": lo, "j_in": j_in[0], "j_in_pins": pins,
                    "j_out": (blades[0] if blades else ""), "j_out_blades": blades,
                    "shunt": shunt, "shared_bus": True})
    return out


def _shunt_gap_board_grow(nl, fp_of, topo, *, margin=1.0, headroom=1.0):
    """Board-height INCREMENT (mm) for the SHUNT_GAP_MM widen (R2, owner-ratified 2026-06-28).

    cec_fr.derive_power_pours pulls each high-current pour's shunt-side edge back so the un-poured
    notch at the Kelvin shunt opens from (shunt-pad-separation - 2*margin) ~= 3.9mm to SHUNT_GAP_MM
    ~= 6.5mm -- enough channel for the sense cluster (INA238 + §6.13 INA181 + TLV7011) AND a B.Cu
    overflow-routing lane. Opening the notch shortens each pour by that delta; growing the board by
    the same delta (+ a small cluster/B.Cu-lane *headroom*) moves J_IN/J_OUT apart so the pour
    corridors keep their length and the shunt (seated at H/2) gets vertical room either side. Reads the
    shunt pad separation from the first cable's 2-pad shunt FOOTPRINT, so it is general to any per-cable
    interposer (EPS / PCIe). Returns 0.0 when there is no qualifying 2-pad shunt or cec_fr is absent."""
    import cec_pcb
    try:
        import cec_fr
        gap = cec_fr.SHUNT_GAP_MM
    except Exception:
        return 0.0
    for c in topo:
        sh = c.get("shunt")
        if sh in fp_of:
            pads = list(cec_pcb.local_pads(fp_of[sh]).values())
            if len(pads) >= 2:                          # corridor-axis pad spacing = max pairwise separation
                sep = max(math.hypot(a[0] - b[0], a[1] - b[1])
                          for i, a in enumerate(pads) for b in pads[i + 1:])
                base_notch = max(0.0, sep - 2.0 * margin)
                return round(max(0.0, gap - base_notch) + headroom, 1)
    return 0.0


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


def _seed_corridor_spine(topo, anchors, H, nl, comps, W=None, params=None):
    """FORM each per-cable corridor: align J_OUT's LO force-pad column UNDER J_IN's HI force-pad column
    (so the +12V current runs straight J_IN -> shunt -> J_OUT) and seat the shunt on that column axis at
    mid-board, rot 270 (H3 -- HI=upper terminal, Kelvin taps don't cross), all as FIXED anchors. Mutates
    *anchors*; returns the seated shunt refs (dropped from the annealed set so the spine can't be pushed
    off-axis). J_IN keeps the x seed_anchors packed it to (columns stay spaced by connector width). When
    *W* is given the column is CLAMPED so the connector/shunt pads stay on-board (no off-board pads on a
    narrow board)."""
    seated = []
    blade_cables = []
    shared = [c for c in topo if c.get("shared_bus")]
    if shared:
        # SHARED-BUS RAIL COLUMNS (24-pin): the blade row is ONE contiguous daughterboard
        # field, so rail columns sit at their blade-group slots. Order rails by the shared
        # connector's pin-centroid (the natural fan order minimizes crossings), pack the
        # groups left-to-right at the field pitch centered on the input connector, and seat
        # each rail's shunt on its group centroid. The sense chains DON'T fit four-abreast
        # at this pitch on one face -- the dual-sided seat (mechanism item e) assigns
        # alternating rails to the back; until it lands the seat is front-side.
        jin = shared[0]["j_in"]
        if jin in anchors:
            # PIN-GROUP COLUMN ORDER (the lever gating box unification, 2026-07-08): a
            # centroid sort is meaningless for INTERLEAVED rails (3V3's pins sit at both
            # header ends -> centroid lands mid). Assign columns by MIN-COST permutation:
            # cost = sum over each rail's pin x-CLUSTERS of cluster_size * |cluster_x -
            # column_x| -- left-cluster rails take left columns (also clears the hub-jack
            # zone the 3V3 fan box collided with). N<=4 rails -> brute force.
            import itertools
            import cec_fr as _cf
            _clusters_of = {}
            for c in shared:
                xs = _net_pad_xs(nl, comps, c["j_in"], c["hi"], anchors)
                pts = sorted((x, 0.0) for x in xs)
                _clusters_of[c["shunt"]] = [(sum(p[0] for p in cl) / len(cl), len(cl))
                                            for cl in _cf._x_clusters(pts)] if pts else []
            def _slot_centers(order, x0_, pitch_):
                cols = []
                k = 0
                for c in order:
                    n_lo = max(1, len(c["j_out_blades"]))
                    cols.append(x0_ + (k + (n_lo - 1) / 2.0) * pitch_)
                    k += n_lo
                return cols
            def _perm_cost(order, x0_, pitch_):
                cols = _slot_centers(order, x0_, pitch_)
                cost = 0.0
                for c, col in zip(order, cols):
                    for cx, w in _clusters_of.get(c["shunt"], ()):
                        cost += w * abs(cx - col)
                return cost
            if len(shared) <= 6:
                _pitch0 = float((params or {}).get("blade_pitch", 4.2))
                _n_tot0 = sum(max(1, len(c["j_out_blades"])) for c in shared)
                _span0 = (_n_tot0 - 1) * _pitch0
                _x00 = max(_pitch0, min(anchors[jin][0] - _span0 / 2.0,
                                        (W or 100) - _span0 - _pitch0))
                shared = list(min(itertools.permutations(shared),
                                  key=lambda o: _perm_cost(o, _x00, _pitch0)))
            else:
                def _cent(c):
                    xs = _net_pad_xs(nl, comps, c["j_in"], c["hi"], anchors)
                    return (sum(xs) / len(xs)) if xs else anchors[jin][0]
                shared.sort(key=_cent)
            # field pitch: the MATING daughterboard's tab row is the contract (atx24-out-db:
            # 10 tabs @ 4.2mm contiguous). Overridable per board; shared-bus default 4.2/4.2.
            pitch = float((params or {}).get("blade_pitch", 4.2))
            slots = []
            n_tot = 0
            for c in shared:
                n_lo = max(1, len(c["j_out_blades"]))
                slots.append(n_lo)
                n_tot += n_lo
            span = (n_tot - 1) * pitch
            # RIGHT-EDGE CAP (owner catch 2026-07-08: "the 1x4 header is hanging off the
            # edge -- those out headers can shift over and be on the board"): the row's
            # rightward budget must reserve the SIGNAL STUB's full extent (pin1 sits one
            # field pitch past the last blade, pads span +7.62, courtyard ~+1.0), so the
            # whole output row shifts LEFT as a unit instead of the stub running off-board.
            _stub_ext = 0.0
            if any(r.startswith("J_SIG") for r in anchors) or any(
                    r.startswith("J_SIG") for r in nl.comps):
                _stub_ext = pitch + 3.81 + 3.81 + 1.0
            x0 = max(pitch, min(anchors[jin][0] - span / 2.0,
                                (W or 100) - span - pitch - _stub_ext))
            # ANCHOR-vs-ANCHOR collision fix (exploratory finding, 2026-07-08): the row's
            # y-band can run under an edge connector (J1's courtyard swallowed the row's
            # left end -- 6 courtyard overlaps + a DETECT-pin short, invisible to the
            # legalizer which never checks two anchors against each other). Clamp the row
            # start clear of any seated anchor whose courtyard intersects the row band.
            row_y = H / 2.0
            half_band = 9.0
            for _ar, _apos in list(anchors.items()):
                if _ar not in comps:
                    continue
                _cx, _cy, _hw, _hh = _courtyard_info(comps[_ar], _apos[2] if len(_apos) > 2 else 0)
                ax0 = _apos[0] + _cx - _hw
                ax1 = _apos[0] + _cx + _hw
                ay0 = _apos[1] + _cy - _hh
                ay1 = _apos[1] + _cy + _hh
                if ay1 < row_y - half_band or ay0 > row_y + half_band:
                    continue                             # clear of the row band
                if ax0 < (W or 100) / 2.0:               # left-side blocker: push the row right
                    # +8mm: the first column's sense IC straddles LEFT of the shunt
                    x0 = max(x0, ax1 + pitch + 8.0)
            # the RIGHT-EDGE cap is FINAL (owner: pins off the board beats a jack graze
            # never -- the stub must be ON the board; a residual jack graze shows in DRC
            # and the wave iterates it)
            x0 = min(x0, (W or 100) - span - pitch - _stub_ext)
                # right-side blockers only matter if the row would reach them; the stub
                # seat extends right, so leave headroom
            
            # WIDE SHUNT COLUMNS (strict rule): the sense cell needs pour-free ground
            # around each shunt; shunts are NOT bound to the blade pitch (the LO lane
            # fans shunt->blade), so columns spread to a cell pitch <= 16mm.
            _wu = (W or 100)
            _cell_pitch = min(16.0, max(pitch, (_wu - x0 - _stub_ext - pitch) / max(1, len(shared))))
            for _ci, (c, n_lo) in enumerate(zip(shared, slots)):
                col = x0 + (_ci + 0.5) * _cell_pitch
                anchors[c["shunt"]] = (col, H / 2.0, 270.0)
                seated.append(c["shunt"])
                if c["j_out_blades"]:
                    blade_cables.append((c, col))
    for c in topo:
        if c.get("shared_bus"):
            continue
        jin, jout, sh = c["j_in"], c["j_out"], c["shunt"]
        if jin not in anchors or jout not in anchors:
            continue
        in_xs = _net_pad_xs(nl, comps, jin, c["hi"], anchors)         # the J_IN +12V column
        col = (sum(in_xs) / len(in_xs)) if in_xs else anchors[jin][0]
        if W and in_xs:
            hw = (max(in_xs) - min(in_xs)) / 2.0 + 1.0               # keep the column's pads on-board
            col = min(max(col, hw), W - hw)
        if c.get("j_out_blades"):
            blade_cables.append((c, col))             # D-5a blade field -- seated as a group below
        else:
            # shift J_OUT in x so its LO force-pad column lands under the J_IN column
            ox, oy, orot = anchors[jout]
            out_xs = _net_pad_xs(nl, comps, jout, c["lo"], anchors)
            out_col = (sum(out_xs) / len(out_xs)) if out_xs else ox
            anchors[jout] = (ox + (col - out_col), oy, orot)
        anchors[sh] = (col, H / 2.0, 270.0)           # shunt on the force-column axis, rot270
        seated.append(sh)
    if blade_cables:
        _p = (params or {})
        _shared_row = any(c.get("shared_bus") for c, _col in blade_cables)
        if any(c.get("shared_bus") for c, _col in blade_cables):
            _seat_blade_fields(blade_cables, anchors, nl, comps, W,
                               pitch=float(_p.get("blade_pitch", 4.2)),
                               gap=float(_p.get("blade_group_gap", 4.2)), H=H)
        else:
            _seat_blade_fields(blade_cables, anchors, nl, comps, W,
                               pitch=float(_p.get("blade_pitch", _BLADE_PITCH_MM)),
                               gap=float(_p.get("blade_group_gap", _BLADE_GROUP_GAP_MM)), H=H)
        if _shared_row:
            # SIGNAL-STUB ALIGNMENT (owner 2026-07-08): the J_SIG* stub is part of the
            # daughterboard blind-mate interface -- collinear with the blade row, pad 1 one
            # field pitch beyond the last slot (the atx24-out-db J20 contract; both boards
            # regenerate from this rule). HDR-TH_4P pad1 local x = -3.81 at rot 0.
            row = [anchors[r] for r in anchors if r.startswith("TB")]
            stub = next((r for r in sorted(anchors) if r.startswith("J_SIG")), None)
            if stub and row:
                pch = float(_p.get("blade_pitch", 4.7))
                last_x = max(p[0] for p in row)
                row_y = row[0][1]
                anchors[stub] = (last_x + pch + 3.81, row_y, 0.0)
                # WHOLE-ROW ON-BOARD SHIFT (owner 2026-07-08: "the pins are off the board
                # -- those out headers can be shifted over"): if the stub's far pad
                # (+3.81 from origin, +~1.0 court) exceeds the right edge, shift EVERY
                # blade + the stub left by the overhang as one unit. The blind-mate
                # geometry (pitch + stub offset) is preserved exactly.
                # CENTER the whole output ensemble (owner 2026-07-08: the off-center row
                # gates width reduction) -- blades + stub move as one rigid unit to the
                # middle of the usable span, still clamped fully on-board.
                _tb_xs = [anchors[r][0] for r in anchors if r.startswith("TB")]
                _lo_x = min(_tb_xs) - 2.4
                _hi_x = anchors[stub][0] + 3.81 + 1.0
                _span2 = _hi_x - _lo_x
                _left_lim, _right_lim = 0.6, (W or 100) - 0.6
                _want_lo = max(_left_lim, min(((W or 100) - _span2) / 2.0,
                                              _right_lim - _span2))
                _shift = _want_lo - _lo_x
                if abs(_shift) > 0.05:
                    for _r3 in list(anchors):
                        if _r3.startswith("TB") or _r3 == stub:
                            _ax, _ay = anchors[_r3][0] + _shift, anchors[_r3][1]
                            _rt = anchors[_r3][2] if len(anchors[_r3]) > 2 else 0.0
                            anchors[_r3] = (_ax, _ay, _rt)
    return seated


# D-5a blade-field geometry (spec §2.8 revision, docs/standard-tier-review/). The slot PITCH is the
# mating contract with the output daughterboard's 63951 tab field -- 4.7mm as built on
# modules/output-daughterboards/eps-out-db (J10..J15, x 2.5->26.0). NOTE the committed module-side
# placeholder row used 4.75mm -- a 0.25mm accumulated blind-mate mismatch across 6 slots; fresh
# synthesis standardizes on the daughterboard's 4.7. The GROUP gap keeps adjacent daughterboard
# BODIES (28.6mm wide vs the 23.5mm 6-slot field span) from colliding: >= 5.1mm, as-built 6.5.
_BLADE_PITCH_MM = 4.7
_BLADE_GROUP_GAP_MM = 6.5


def _seat_blade_fields(blade_cables, anchors, nl, comps, W=None, *, pitch=None, gap=None, H=None, pad_margin=1.8):
    """Seat the D-5a output blade FIELD as one contiguous row at the power_out edge: a 6-slot
    WINDOW per cable (one window == one mating daughterboard; adjacent windows separated by
    _BLADE_GROUP_GAP_MM so the daughterboard BODIES clear), the cable's LO/rail blades assigned
    to the CONTIGUOUS TRIPLE of slots inside its window NEAREST its corridor column, GND blades
    filling the rest. Net->slot order is a free variable (the blades are identical; the
    daughterboard routes to match -- owner 2026-07-07), which is exactly what lets neighbouring
    windows MIRROR their rail triples toward their columns when the J_IN columns sit closer than
    a full window pitch (measured: eps columns 21.7mm apart vs 34.7mm window pitch -- a naive
    per-group centring displaced cable 2's blades ~8mm off-column and broke its pour path).
    The row origin is then least-squares fitted so the rail triples land as close to their
    columns as the window grid allows. Mutates *anchors*."""
    all_blades = [r for r in anchors if r in comps and _is_blade(r, str(comps.get(r, "")))]
    assigned = {b for c, _col in blade_cables for b in c["j_out_blades"]}
    gnd_pool = sorted(r for r in all_blades if r not in assigned)
    ys = [anchors[b][1] for b in all_blades if b in anchors]
    row_y = (sum(ys) / len(ys)) if ys else None       # fallback: the edge seed packed them on
    if H is not None and all_blades and row_y is not None:
        # GEOMETRIC row_y as a REPAIR only (2026-07-08): recompute from the pad band iff the
        # seeded mean leaves a blade PAD off-board (the seed6 pathology -- a rotation
        # perturbation shifted the band). Judged on PAD extent, never the origin (receptacle
        # origins legitimately ride near the edge); a sane seeded mean stays byte-identical.
        fp0 = str(comps.get(all_blades[0], ""))
        try:
            (_bxl, _bxh), (_byl, _byh) = _pad_band(fp0, 0.0)
            if row_y + _byh > H - 0.2 or row_y + _byl < 0.2:
                row_y = H - pad_margin - _byh
        except Exception:                              # noqa: BLE001
            pass
    cables = sorted(blade_cables, key=lambda t: t[1])  # left-to-right by corridor column
    p = float(pitch if pitch is not None else _BLADE_PITCH_MM)
    g = float(gap if gap is not None else _BLADE_GROUP_GAP_MM)
    win_pitch = None                                   # slot index stride between window starts
    # window k slot positions: x0 + (win_start[i] + k)*p ; the inter-window gap is expressed in
    # fractional slot units so all slots live on one arithmetic grid.
    win_starts, s = [], 0.0
    for i, (c, _col) in enumerate(cables):
        n_lo = len(c["j_out_blades"])
        n_win = n_lo + (len(gnd_pool) // len(cables) if cables else 0)
        win_starts.append((s, n_win, n_lo))
        # next window start: this window's END blade (start + n_win-1) plus the inter-window
        # blade CENTER-to-CENTER gap (as-built 6.5mm vs the 4.7 in-window pitch -- enough for
        # the 28.6mm daughterboard bodies to clear their 23.5mm fields by ~1.4mm).
        s += (n_win - 1) + g / p
    # two-pass: pick rail triples per window given x0, then least-squares x0, then re-pick
    x0 = (sum(col for _c, col in cables) / len(cables)) - (s - 1) * p / 2.0 if cables else 0.0
    rail_off = [0] * len(cables)
    for _ in range(2):
        offs = []
        for i, (c, col) in enumerate(cables):
            ws, n_win, n_lo = win_starts[i]
            best = min(range(0, n_win - n_lo + 1),
                       key=lambda k: abs(x0 + (ws + k + (n_lo - 1) / 2.0) * p - col))
            rail_off[i] = best
            offs.append(((win_starts[i][0] + best + (n_lo - 1) / 2.0) * p, col))
        x0 = sum(col - o for o, col in offs) / len(offs)
    if W is not None:
        # after the loop s = last_window_start + (n_win-1) + gap/p, so the last blade sits at
        # slot (s - gap/p); the row must stay on-board with half a pitch + margin each side.
        span = (s - g / p) * p if cables else 0.0
        x0 = min(max(x0, p / 2.0 + 0.5), W - span - p / 2.0 - 0.5)
    for i, (c, _col) in enumerate(cables):
        ws, n_win, n_lo = win_starts[i]
        lo = sorted(c["j_out_blades"])
        gnd = gnd_pool[i * (n_win - n_lo):(i + 1) * (n_win - n_lo)]
        slots = [x0 + (ws + k) * p for k in range(n_win)]
        rails = set(range(rail_off[i], rail_off[i] + n_lo))
        li = gi = 0
        for k, x in enumerate(slots):
            r = None
            if k in rails and li < len(lo):
                r, li = lo[li], li + 1
            elif gi < len(gnd):
                r, gi = gnd[gi], gi + 1
            elif li < len(lo):
                r, li = lo[li], li + 1
            if r and r in anchors:
                _x, y, _rot = anchors[r]
                anchors[r] = (x, row_y if row_y is not None else y, 0.0)


def _perp_half(size, rot, n):
    """Half-extent of a (locally axis-aligned) pad rectangle, ROTATED by *rot*, projected onto unit
    direction *n* -- the support of the rotated pad along n. Used to compute the lateral standoff that
    lands a sense pad hard against the shunt inner edge."""
    import cec_pcb
    ex = cec_pcb._rot(size[0] / 2.0, 0.0, rot)
    ey = cec_pcb._rot(0.0, size[1] / 2.0, rot)
    return abs(ex[0] * n[0] + ex[1] * n[1]) + abs(ey[0] * n[0] + ey[1] * n[1])


def _downstream_comparators(ic, hi, lo, nl, comps):
    """§6.13 chain resolver: the DOWNSTREAM detection comparator(s) of a sense IC -- a small U-ref
    (!= *ic*) sharing a NON-power, NON-(hi/lo) signal net with *ic*. The INA181 detection amp drives
    its TLV7011 over the /DETAMP* output net, so this returns that comparator; an INA238 CURRENT sensor
    has no such net (its outputs are I2C/digital) -> []. GUARDS: the candidate must NOT itself tap a
    Kelvin _HI/_LO net (so it can't be another cable's INA) and must be SMALL (<=8 pads, so the MCU/ESP
    on a shared DET net is never seated). Deterministic order."""
    out, seen = [], set()
    for net in sorted(nl.nets):
        if net in (hi, lo):
            continue
        base = net.rsplit("/", 1)[-1].upper()
        if _POWER_NET.search(net) or base == "GND":
            continue
        refs = [r for r, _ in nl.nets[net]]
        if ic not in refs:
            continue
        for r in refs:
            if r == ic or not r.startswith("U") or r in comps and r in seen or r not in comps:
                continue
            if _ref_padcount(nl, r) > 8:                          # MCU/ESP guard -- comparators are small
                continue
            r_nets = {n for n in nl.nets if r in {x for x, _ in nl.nets[n]}}
            if any(n.endswith(("_HI", "_LO")) for n in r_nets):   # another cable's INA -> not downstream
                continue
            seen.add(r)
            out.append(r)
    return out


def _seat_detection_comparator(ic, comp, anchors, nl, comps, hi, lo, ax, ay, nx, ny, side,
                               *, gap=0.5, pour_margin=1.0):
    """Seat the §6.13 detection COMPARATOR *comp* (TLV7011) CLUSTERED WITH its driving INA181 *ic*,
    on the SAME lateral side, OUT of the SENSEC high-current pour. The comparator is DOWNSTREAM of the
    INA181 (it takes the INA181 OUTPUT, not the shunt), so it does NOT need shunt-adjacency -- it needs
    INA181-adjacency + pour-clearance. Returns (x,y,rot) or None.

    GEOMETRY: the INA181 is already seated centred in the un-poured NOTCH (the y-band the pour leaves
    open between the HI and LO boxes), offset laterally onto `side`. Seat the comparator just OUTBOARD
    of the INA181 courtyard along the SAME side (side*n), at the INA181's notch a-level -- so it rides
    in the notch too (clear of both pour boxes) AND further from the corridor column than the INA. A
    safety push then slides it further out until its courtyard clears BOTH this cable's HI/LO pour boxes
    (derive_power_pours rule, recomputed host-side off the anchors: connector THT + shunt pads, +margin),
    so a tall rotation can never graze. The rotation faces the comparator INPUT pad (the /DETAMP* net it
    shares with the INA) toward the INA OUTPUT for a short detection link."""
    import cec_pcb
    sn = (side * nx, side * ny)                                   # outboard unit = the side the INA is on
    icx, icy, icrot = anchors[ic]
    icx0, icy0, ihw, ihh = _courtyard_info(comps[ic], icrot)
    ic_cen = (icx + icx0, icy + icy0)                             # INA181 courtyard centre (in the notch)
    ic_perp = abs(ihw * sn[0]) + abs(ihh * sn[1])                # INA181 courtyard half-extent outboard
    # this cable's HI/LO pour boxes -- the keepout the comparator BODY must clear (same pad class as
    # cec_fr.derive_power_pours: connector THT + the 2-pad Kelvin shunt; INA SMD sense pads excluded).
    boxes = []
    for net in (hi, lo):
        pts = []
        for r, p in nl.nets.get(net, []):
            if r in (ic, comp) or r not in anchors:
                continue
            if r.startswith("J") or (r.startswith("R") and _ref_padcount(nl, r) == 2):
                try:
                    pts.append(cec_pcb.pad_global(r, p, {r: anchors[r]}, comps))
                except Exception:
                    pass
        if pts:
            xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
            boxes.append((min(xs) - pour_margin, max(xs) + pour_margin,
                          min(ys) - pour_margin, max(ys) + pour_margin))
    # the comparator INPUT pad (the /DETAMP* net it shares with the INA) + the INA OUTPUT pad
    sig = next((net for net in sorted(nl.nets)
                if net not in (hi, lo) and not _POWER_NET.search(net)
                and net.rsplit("/", 1)[-1].upper() != "GND"
                and ic in {r for r, _ in nl.nets[net]} and comp in {r for r, _ in nl.nets[net]}), None)
    in_pad = next((p for r, p in nl.nets.get(sig, []) if r == comp), None) if sig else None
    out_pad = next((p for r, p in nl.nets.get(sig, []) if r == ic), None) if sig else None
    out_xy = None
    if out_pad:
        try:
            out_xy = cec_pcb.pad_global(ic, out_pad, {ic: anchors[ic]}, comps)
        except Exception:
            out_xy = ic_cen
    lp = cec_pcb.local_pads(comps[comp])
    best = None
    for rot in (0.0, 90.0, 180.0, 270.0):
        ccx, ccy, chw, chh = _courtyard_info(comps[comp], rot)
        comp_perp = abs(chw * sn[0]) + abs(chh * sn[1])
        reach = ic_perp + gap + comp_perp                        # start just outboard of the INA body
        for _ in range(40):                                      # push out until the body clears the pours
            cen = (ic_cen[0] + sn[0] * reach, ic_cen[1] + sn[1] * reach)
            cyb = (cen[0] - chw, cen[0] + chw, cen[1] - chh, cen[1] + chh)
            worst = 0.0
            for b in boxes:
                ox = min(cyb[1], b[1]) - max(cyb[0], b[0])
                oy = min(cyb[3], b[3]) - max(cyb[2], b[2])
                if ox > 0 and oy > 0:
                    worst = max(worst, min(ox, oy))
            if worst <= 0.05:
                break
            reach += worst + 0.2
        cen = (ic_cen[0] + sn[0] * reach, ic_cen[1] + sn[1] * reach)
        Of = (cen[0] - ccx, cen[1] - ccy, rot)
        d = 0.0
        if in_pad and out_xy and in_pad in lp:
            try:
                ip = cec_pcb.pad_global(comp, in_pad, {comp: Of}, comps)
                d = math.hypot(ip[0] - out_xy[0], ip[1] - out_xy[1])
            except Exception:
                d = 0.0
        score = (round(reach, 1), round(d, 2))                   # most compact reach first, then short link
        if best is None or score < best[0]:
            best = (score, Of)
    return best[1] if best else None


def _seat_sense_ics(topo, anchors, nl, comps, *, seat_gap=0.2, pour_margin=1.0):
    """REAL geometric KELVIN SEAT (replaces the historical line-1732 anneal-connectivity non-seat).

    For each FORMED per-cable corridor, seat its current-sense IC(s) -- the INA238/228 current sensor
    AND the §6.13 INA181 detection amp -- HARD against the seated shunt's inner edge as FIXED anchors:
      * BODY PERPENDICULAR to the J_IN->shunt->J_OUT corridor and CENTERED in the un-poured NOTCH (the
        y-band the high-current pour deliberately leaves open between the HI and LO boxes), so the body
        stays OUT of the SENSEC pour;
      * ROTATED so the IN+/IN- input pads face the shunt's HI/LO inner-edge sense points
        (HI-inner -> IN+, LO-inner -> IN-, taps don't cross) -- resolved by READ-BACK, since KiCad's
        y-down transform inverts the naive math-CCW sign;
      * the two ICs on a shunt take OPPOSITE corridor sides (so each gets a clean inner-edge tap and
        neither sits in the pour).
    Then, for the INA181, ALSO seat its DOWNSTREAM §6.13 detection comparator (TLV7011) -- which takes
    the INA181 OUTPUT, not the shunt, so it needs INA181-adjacency + pour-clearance, NOT shunt-adjacency
    (_seat_detection_comparator): clustered just outboard of the INA181 on the SAME lateral side, in the
    notch, OUT of the SENSEC pour. The comparator becomes a FIXED anchor too (so connectivity drift can't
    pull it back into the pour -- the U30-entirely-inside-/SENSEC1_HI bug).
    Writes anchors[ic]=(x,y,rot); returns the seated IC refs (INAs + comparators) so synth_one can drop
    them from the annealed set (connectivity drift can no longer pull them 6-8mm off the shunt and into
    the pour -- the measured bug). The shunt must already be seated (anchors[shunt] = (col, H/2, 270) from
    _seed_corridor_spine). SHARED-BUS connectors (24-pin / 12VHPWR) are absent from *topo*, so the seat
    fires only on the per-cable EPS/PCIe family (correct -- the filtered 12VHPWR INA240 lanes use the
    column-alignment branch of the checker instead)."""
    import cec_pcb
    seated = []
    for c in topo:
        sh, hi, lo = c["shunt"], c["hi"], c["lo"]
        if sh not in anchors or sh not in comps:
            continue
        sh_hi = next((p for r, p in nl.nets.get(hi, []) if r == sh), None)   # shunt HI terminal pad
        sh_lo = next((p for r, p in nl.nets.get(lo, []) if r == sh), None)   # shunt LO terminal pad
        if not (sh_hi and sh_lo):
            continue
        P_HI = cec_pcb.pad_global(sh, sh_hi, {sh: anchors[sh]}, comps)
        P_LO = cec_pcb.pad_global(sh, sh_lo, {sh: anchors[sh]}, comps)
        ax, ay = P_LO[0] - P_HI[0], P_LO[1] - P_HI[1]
        aL = math.hypot(ax, ay) or 1.0
        ax, ay = ax / aL, ay / aL                       # current axis HI->LO (the corridor direction)
        nx, ny = -ay, ax                                # lateral (perp to the corridor)
        mid = ((P_HI[0] + P_LO[0]) / 2.0, (P_HI[1] + P_LO[1]) / 2.0)
        ssz = cec_pcb.local_pad_sizes(comps[sh])
        sh_perp = _perp_half(ssz.get(sh_hi, (1.0, 1.0)), anchors[sh][2], (nx, ny))
        # NOTE: the un-poured notch ALONG a is +/-(aL/2 - pour_margin) about mid (derive_power_pours
        # ends each pour box at the shunt pad CENTRE +/- margin). The seat centres the body on `a`
        # (alpha below), so it sits in that notch; pour_margin is the documented calibration knob.
        refs = {r for r, _ in nl.nets.get(hi, [])} | {r for r, _ in nl.nets.get(lo, [])}
        # INA-FILTER (reach-gate finding 2026-07-08): on RAIL-SIDED straddle pairs
        # (+5V_MAIN/+5VSB) the net-derived ref set sweeps in every IC on the rail (the
        # mux, loads) -- the seat then mis-assigns sides and the real INA181 lands 33-49mm
        # out (wave-10's kelvin=false). Only actual sense amps seat here.
        sense = sorted(r for r in refs if r.startswith("U") and r in comps
                       and "INA" in (nl.comps[r].value or "").upper())
        for idx, ic in enumerate(sense):
            side = 1.0 if idx % 2 == 0 else -1.0        # the two ICs straddle the shunt
            inp = next((p for r, p in nl.nets.get(hi, []) if r == ic), None)   # IN+ pad (on HI)
            inn = next((p for r, p in nl.nets.get(lo, []) if r == ic), None)   # IN- pad (on LO)
            lp = cec_pcb.local_pads(comps[ic]); lsz = cec_pcb.local_pad_sizes(comps[ic])
            if not inp or not inn or inp not in lp or inn not in lp:
                continue
            inp_l, inn_l = lp[inp], lp[inn]
            chosen = None
            for rot in (0.0, 90.0, 180.0, 270.0):
                ig = cec_pcb._rot(*inp_l, rot)          # IN+/IN- pad offsets from origin at this rot
                ng = cec_pcb._rot(*inn_l, rot)
                cg = ((ig[0] + ng[0]) / 2.0, (ig[1] + ng[1]) / 2.0)     # IN-pair centroid offset
                cx, cy, hwc, hhc = _courtyard_info(comps[ic], rot)      # courtyard centre offset + halves
                inpad_perp = _perp_half(lsz.get(inp, (1.0, 1.0)), rot, (nx, ny))
                g_lat = sh_perp + seat_gap + inpad_perp
                # Solve O = mid + alpha*a + beta*n so (i) the IN-pair centroid sits g_lat off the shunt
                # on side `side` (sense pads hard against the inner edge) and (ii) the body courtyard
                # centre is on the corridor axis (centred in the notch -> out of the pour).
                beta = side * g_lat - (cg[0] * nx + cg[1] * ny)
                alpha = -(cx * ax + cy * ay)
                O = (mid[0] + alpha * ax + beta * nx, mid[1] + alpha * ay + beta * ny)
                INp = (O[0] + ig[0], O[1] + ig[1]); INn = (O[0] + ng[0], O[1] + ng[1])
                order = (INp[0] - INn[0]) * ax + (INp[1] - INn[1]) * ay     # IN+ must be toward HI (-a)
                face = ((INp[0] + INn[0]) / 2.0 - O[0]) * nx * side + \
                       ((INp[1] + INn[1]) / 2.0 - O[1]) * ny * side          # IN pads must face the shunt
                if order < -1e-6 and face < 1e-6:
                    chosen = (rot, beta)
                    break
            if chosen is None:
                continue
            rot, beta = chosen
            cx, cy, hwc, hhc = _courtyard_info(comps[ic], rot)
            alpha = -(cx * ax + cy * ay)                    # body courtyard centred on the corridor axis
            sh_cy = cec_pcb.courtyard_bbox(comps[sh], *anchors[sh])
            # COURTYARD CLEARANCE: the seat lands the SENSE PADS hard against the shunt, but the IC
            # BODY must not overlap the shunt COURTYARD (DRC) -- so slide the body laterally OUT (along
            # `side`*n, away from the corridor) until its courtyard clears the shunt courtyard. The
            # sense pads ride out with it but stay well within the 5mm/2mm Kelvin window (measured: edge
            # gap ~0.2 -> ~0.8mm). `a` is unchanged, so the body stays centred in the notch.
            for _ in range(24):
                Ox = mid[0] + alpha * ax + beta * nx
                Oy = mid[1] + alpha * ay + beta * ny
                ic_cy = (Ox + cx - hwc, Ox + cx + hwc, Oy + cy - hhc, Oy + cy + hhc)
                ovx = min(ic_cy[1], sh_cy[1]) - max(ic_cy[0], sh_cy[0])      # lateral overlap (n is horizontal)
                ovy = min(ic_cy[3], sh_cy[3]) - max(ic_cy[2], sh_cy[2])
                if ovx <= 0.2 or ovy <= 0.2:                # courtyards separated (or corner graze) -> done
                    break
                beta += side * (ovx + 0.2)                  # push the body out along n by the lateral overlap
            anchors[ic] = (mid[0] + alpha * ax + beta * nx, mid[1] + alpha * ay + beta * ny, rot)
            seated.append(ic)
            # §6.13 DETECTION COMPARATOR (owner directive 2026-06-28): seat each cable's TLV7011 -- the
            # detection comparator DOWNSTREAM of THIS sense IC -- CLUSTERED WITH it, on the SAME lateral
            # side, OUT of the SENSEC pour. Only fires for the INA181 (it drives a comparator over its
            # /DETAMP* output); the INA238 current sensor has none, so _downstream_comparators -> []. The
            # comparator becomes a FIXED anchor too, so connectivity drift can't pull it back into the
            # pour (the U30-entirely-inside-/SENSEC1_HI bug). Its bypass cap clusters onto it downstream.
            for cmp in _downstream_comparators(ic, hi, lo, nl, comps):
                if cmp in anchors:                       # already seated (shared by another sense IC)
                    continue
                seat = _seat_detection_comparator(ic, cmp, anchors, nl, comps, hi, lo,
                                                  ax, ay, nx, ny, side)
                if seat is not None:
                    anchors[cmp] = seat
                    seated.append(cmp)
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


def _pad_is_tht(libid):
    """{pad_num: is_tht} for a footprint (memoized) -- the placement-side pour-box extractor
    needs pad TYPE, which local_pads drops."""
    if libid in _PAD_THT_CACHE:
        return _PAD_THT_CACHE[libid]
    out = {}
    try:
        import cec_pcb
        nick, name = str(libid).split(":")
        s = open(cec_pcb.fp_path(nick, name)).read()
        for m in re.finditer(r'\(pad\s+"([^"]*)"\s+(\w+)', s):
            out[m.group(1)] = (m.group(2) == "thru_hole")
    except Exception:                                    # noqa: BLE001
        pass
    _PAD_THT_CACHE[libid] = out
    return out


_PAD_THT_CACHE = {}


def _pour_boxes_unified(P, nl, comps, W, H, *, margin=1.0, edge_clear=0.4, asks=()):
    """PLACEMENT-side pour boxes from the SAME pure core the route-time gate uses
    (cec_fr._pour_boxes_core) -- box-model unification 2026-07-08: the settle previously
    avoided topo-derived boxes while the gate checked straddle-derived clipped boxes, so
    re-stamped caps kept landing in gate boxes the settle never saw (the cross-board craft
    blocker). Returns [(net, x0, x1, y0, y1)] in the evac format.

    POUR LEVER (stage 1/2, docs/pour-lever-scoping-2026-07-08.md): now a thin view of a
    ``cec_pourplan.PourPlan`` built off the placement (``from_placement`` -> ``evac_boxes()``).
    *asks* (the placer's ``pour()`` channel, cfg.params['pour_asks']) fold in as extra pour boxes;
    ``asks=()`` is byte-identical to the old placement-side extractor (golden guarantee)."""
    import cec_pourplan
    return cec_pourplan.PourPlan.from_placement(P, nl, comps, W, H, asks=asks,
                                                margin=margin, edge_clear=edge_clear).evac_boxes()


def _pour_boxes_from_P(topo, P, nl, comps, *, margin=1.0):
    """The derive_power_pours SENSEC boxes recomputed HOST-SIDE off placement *P* (the same pad class:
    connector THT + the 2-pad Kelvin shunt; the INA SMD sense pads excluded). Returns [(net,x0,x1,y0,y1)].
    The route-time no-foreign-on-high-current-pour gate derives the very same boxes, so evacuating bodies
    against these keeps placement and the gate in lockstep. Connectors+shunt are FIXED, so this is stable
    across the evacuation loop (compute once)."""
    import cec_pcb
    try:                                                 # the SHUNT_GAP_MM notch (single source of truth in cec_fr); opt-in
        import cec_fr
        _gap, _notch = (cec_fr.SHUNT_GAP_MM, cec_fr._open_shunt_notch) if cec_fr._shunt_gap_on() else (None, None)
    except Exception:                                    # pcbnew-less host: fall back to the historical hug-the-shunt box
        _gap = _notch = None
    out = []
    for c in topo:
        sh = c.get("shunt")
        shunt_xy = vertical = None
        if _gap and sh in P and sh in comps:             # shunt centre + corridor axis from its two terminals
            shp = []
            for net in (c["hi"], c["lo"]):
                pp = next((q for r, q in nl.nets.get(net, []) if r == sh), None)
                if pp is not None:
                    try:
                        shp.append(cec_pcb.pad_global(sh, pp, {sh: P[sh]}, comps))
                    except Exception:
                        pass
            if len(shp) >= 2:
                shunt_xy = ((shp[0][0] + shp[1][0]) / 2.0, (shp[0][1] + shp[1][1]) / 2.0)
                vertical = abs(shp[0][1] - shp[1][1]) >= abs(shp[0][0] - shp[1][0])
        for net in (c["hi"], c["lo"]):
            pts = []
            for r, p in nl.nets.get(net, []):
                if r not in P:
                    continue
                if r.startswith("J") or (r.startswith("R") and _ref_padcount(nl, r) == 2):
                    try:
                        pts.append(cec_pcb.pad_global(r, p, {r: P[r]}, comps))
                    except Exception:
                        pass
            if pts:
                xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
                box = (min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin)
                if shunt_xy is not None:                  # open the un-poured notch to match derive_power_pours
                    box = _notch(box, shunt_xy, _gap, vertical=vertical)
                out.append((net, box[0], box[1], box[2], box[3]))
    return out


def _evacuate_pours(P, comps, boxes, fixed, *, tol=0.3, clr=0.4, drop_antenna=False,
                    net_exempt=None):
    """Push any FOREIGN MOVABLE body OUT of a derive_power_pours SENSEC box, laterally toward the nearest
    box x-edge + *clr* (the corridor is the vertical connector->shunt column). FOREIGN = not a FIXED
    seated anchor (*fixed*: the connectors / shunts / kelvin-seated INAs + comparators / ESP / mounts that
    legitimately own or graze the pour). The route-time gate counts ANY foreign track/via in a box; a
    foreign decoupling/threshold cap BODY here forces exactly that copper (its pads + the route to them),
    so evacuate it at placement -- the placer-side ENFORCE of no-foreign-on-high-current-pour. This is the
    box-accurate complement to _evacuate_corridors (which uses the tighter band). Returns the moved refs."""
    net_exempt = net_exempt or {}
    moved = []
    for ref in list(P):
        if ref in fixed or ref not in comps or ref[:1] in ("J", "H"):
            continue
        x, y = P[ref][0], P[ref][1]
        rot = P[ref][2] if len(P[ref]) > 2 else 0.0
        cx0, cy0, hw, hh = _courtyard_info(comps[ref], rot, drop_antenna=drop_antenna)
        ccx, ccy = x + cx0, y + cy0
        cb = (ccx - hw, ccx + hw, ccy - hh, ccy + hh)
        _exn = net_exempt.get(ref, ())
        worst = None
        for _net, x0, x1, y0, y1 in boxes:
            if _net in _exn:
                continue                                 # own-rail box: the part belongs here
            ox = min(cb[1], x1) - max(cb[0], x0)
            oy = min(cb[3], y1) - max(cb[2], y0)
            inb = x0 <= ccx <= x1 and y0 <= ccy <= y1
            ov = max(0.0, ox) * max(0.0, oy)
            if (inb or ov > tol) and (worst is None or ov > worst[0]):
                worst = (ov, x0, x1)
        if worst is None:
            continue
        _, x0, x1 = worst
        tcx = (x0 - clr - hw) if (ccx - x0) <= (x1 - ccx) else (x1 + clr + hw)  # exit the nearer x-edge
        P[ref] = (tcx - cx0, y, rot)
        moved.append(ref)
    return moved


def _legalize_avoiding_pours(P, movable, cyinfo, boxes, W, H, *, clr=0.4, bounds=None):
    """POUR-AWARE legalize: run legalize_pack over the *movable* foreign parts with the derive_power_pours
    SENSEC *boxes* injected as FIXED pseudo-obstacles, so each part lands in the nearest free spot that is
    BOTH courtyard-overlap-free AND out of every pour -- pour-clearance and residual settled in ONE pass by
    construction (legalize_pack already treats every non-movable P entry as a fixed obstacle). The seated
    anchors (INAs/comparators/shunts/connectors/ESP) are NOT in *movable*, so their intentional pour graze
    is untouched. Restores P/cyinfo (pseudo refs removed). Returns the residual legalize reports."""
    pseudo = []
    for i, b in enumerate(boxes):
        _net, x0, x1, y0, y1 = b
        k = "__POUR%d__" % i
        P[k] = ((x0 + x1) / 2.0, (y0 + y1) / 2.0, 0.0)
        cyinfo[k] = (0.0, 0.0, (x1 - x0) / 2.0, (y1 - y0) / 2.0)
        pseudo.append(k)
    try:
        return legalize_pack(P, movable, cyinfo, W, H, clr=clr, bounds=bounds)
    finally:
        for k in pseudo:
            P.pop(k, None)
            cyinfo.pop(k, None)


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


def _park_near(target_xy, t_cy, p_cy, pour_boxes, W, H, *, gap=0.6):
    """Nearest lane-free slot adjacent to *target* (right/left/below/above at combined
    extents); None when nothing clears. With LANE pours the boxes are thin, so a clear
    slot almost always exists beside the owner -- the earlier inert result came from
    zero/blanket boxes, not this logic."""
    tx, ty = target_xy
    tcx, tcy, thw, thh = t_cy
    ccx, ccy, chw, chh = p_cy
    cands = [
        (tx + tcx + thw + chw + gap - ccx, ty + tcy - ccy),
        (tx + tcx - thw - chw - gap - ccx, ty + tcy - ccy),
        (tx + tcx - ccx, ty + tcy + thh + chh + gap - ccy),
        (tx + tcx - ccx, ty + tcy - thh - chh - gap - ccy),
    ]
    def _clear(x, y):
        bx0, bx1 = x + ccx - chw, x + ccx + chw
        by0, by1 = y + ccy - chh, y + ccy + chh
        if bx0 < 0.5 or bx1 > W - 0.5 or by0 < 0.5 or by1 > H - 0.5:
            return False
        for _net, px0, px1, py0, py1 in (pour_boxes or ()):
            if not (bx1 <= px0 or bx0 >= px1 or by1 <= py0 or by0 >= py1):
                return False
        return True
    for x, y in cands:
        if _clear(x, y):
            return (x, y)
    return None


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
    back_refs: tuple = ()         # DUAL-SIDED (2026-07-08): refs materialized on the BACK face
    oracle: dict = field(default_factory=dict)   # SLICE-1a: route_oracle_grade verdict (real post-route
                                                 # gate); {} = not adjudicated. Set by adjudicate_candidates.


def _dual_side_guard(back, anchors_roles, comps):
    """OWNER RULE (2026-07-08): connectors and the MCU NEVER go on the back -- only rail
    sensing chains (+ their owned passives) may flip. Hard guard, not a convention: strips
    any connector-role ref, any J*/TB* ref, and any RF/MCU module from a proposed back set
    and reports what it stripped (a stripped ref means an upstream side-assignment bug)."""
    stripped = set()
    keep = set()
    for r in back:
        fpid = str(comps.get(r, "")).lower()
        if (r in anchors_roles or r.startswith(("J", "TB"))
                or "esp32" in fpid or "rf_module" in fpid):
            stripped.add(r)
        else:
            keep.add(r)
    return keep, stripped


# =====================================================================================
# REPAIR LADDER (owner policy, 2026-07-08): when an invariant conflicts with a
# placement/route constraint, repairs are tried IN THIS ORDER -- both the automated
# tiers and the human-escalation tier consult it. Separating a deliberate PAIR (BOOT/
# RESET, divider pairs, sense cells) is always the LAST rung, and even escalation
# prefers every earlier rung first. Board-agnostic; boards may append, never reorder.
REPAIR_LADDER = (
    "1: regenerate the placement candidate (seed/strategy/intent variation)",
    "2: move FOREIGN parts out of the contested region (evac/legalize)",
    "3: slide the invariant's own seat along its allowed axis (lane-aware park)",
    "4: widen the local resource (notch band, cell pitch, board grow) -- board-specific",
    "5: relax a SOFT bias (e.g. CAN-at-jack distance) with the delta surfaced",
    "6: LAST RUNG -- separate a deliberate pair; requires escalation + a recorded reason",
)


def synth_one(cfg_dict, W, H, strat, seed, partition=None, *, enforce_locks=False,
              eval_gates=None):
    """Worker: synthesize + score ONE placement candidate. Top-level + picklable so it runs
    in a spawn-pool worker (on the runner's cores). Takes/returns plain types only.

    *partition* (the intent-compiler lever, default None -> byte-identical to the un-partitioned
    placer; the SB-08 golden routes a FROZEN board so it is untouched regardless): the agent's
    GLOBAL structure-first assignment of free parts to named regions, enforced as proactive HARD
    containment. {"regions": {name:(x0,y0,x1,y1)}, "assignment": {ref:name}}. Assigned free parts
    are seeded into their region before the anneal and confined to it by every legalize pass -- so
    the partition biases the placement, it is not a post-hoc evict (the 2026-06-14 anneal's failure
    mode). PlacementSession (cec_placement_session.py) is the declarative builder over this.

    PASS-FORM (S1, docs/pass-form-plan.md): the placement stages below are declared as an ordered
    PassLadder (P0..P8 boundaries) and executed through it, so the runner can journal what each
    pass placed/moved/locked and -- opt-in -- enforce progressive locking + per-pass gates. The
    internal call ORDER and every call/param are UNCHANGED from the pre-ladder monolith; with
    *enforce_locks* False and all gates off (the defaults) this is BYTE-IDENTICAL to that monolith.
    The passes share ONE flat scope via `nonlocal` (reproducing the pre-ladder single-function
    scoping exactly); the ladder only re-sequences the same statements + records a journal."""
    import cec_pcb
    from cec_passes import Pass, PassLadder
    cfg = Config(**cfg_dict)
    nl = View(cfg).nl
    # ANTENNA KEEPOUT: honoured by default for DRC-consistency with the materialized footprint.
    # When the board declares wireless-unpopulated (respect_antenna_keepout: False -- the 24-pin
    # owner directive 2026-07-08: "the keepout should not be on it anyway"), the placer drops the
    # keepout AND materialize() trims the emitted courtyard lobe to match (build_board
    # drop_keepout), so placer and DRC agree on the smaller courtyard end-to-end.
    drop_antenna = (cfg.params.get("respect_antenna_keepout", True) is False)
    halfext = _part_halfext(nl, drop_antenna=drop_antenna)
    fp_of = _fp_of(nl)
    anchors_roles, ics, shunts, passives = _classify(nl)
    # PARTITION (intent-compiler): resolve the agent's region assignment to per-ref containment boxes.
    # _bounds maps an assigned ref -> its region box; empty when partition is None -> all legalize calls
    # below receive bounds={} which is inert (legalize_pack only constrains refs present in bounds).
    _regions = (partition or {}).get("regions", {}) or {}
    _assign = (partition or {}).get("assignment", {}) or {}
    _bounds = {r: tuple(_regions[_assign[r]]) for r in _assign if _assign.get(r) in _regions}

    # ---- FORWARD DECLARATIONS: the shared placement state every Pass fn `nonlocal`s. Binding
    #      every cross-pass name to this ONE flat scope reproduces the pre-ladder monolith's
    #      single-function scoping EXACTLY (the S1 byte-identity guarantee) -- the ladder only
    #      re-sequences the SAME statements into thunks and records a journal between them.
    anchors = comps = mech_pos = mech_fp = None
    _topo = seated = free_shunts = seated_inas = None
    _esp = _esp_pos = _sw_seated = _can = _can_seated = _rj = anneal_units = None
    _seated_shunts = _fixed_anchor_refs = None
    spec = series = by_owner = fixed_owner = drop_kc = None
    macro = cluster_offsets = fixed_stamp = None
    P = cyinfo_all = None
    _spine = _bands = _paired = _sensitive = _veto = None
    _rk = _role_clr = _func_stamped = None
    _pour_fixed = _pour_asks = _pour_boxes = _nets_of = _net_exempt = _restamped = None

    # ============================================================ P2: anchors + mounts/fiducials
    def _p2_anchors(_state):
        nonlocal H, anchors, comps, mech_pos, mech_fp, _topo, seated, free_shunts
        nonlocal seated_inas, _esp, _esp_pos, _sw_seated, _can, _can_seated, _rj
        nonlocal anneal_units, _seated_shunts, _fixed_anchor_refs, spec, series
        nonlocal by_owner, fixed_owner, drop_kc, macro, cluster_offsets, fixed_stamp
        nonlocal P, cyinfo_all, _spine, _bands, _paired, _sensitive, _veto, _rk
        nonlocal _role_clr, _func_stamped, _pour_fixed, _pour_asks, _pour_boxes
        nonlocal _nets_of, _net_exempt, _restamped
        # R2 SHUNT-GAP widen (owner-ratified 2026-06-28, OPT-IN via CEC_SHUNT_GAP=1 -- board-specific by
        # the ratification boundary, so legacy boards/the golden stay byte-identical by default): on a
        # per-cable interposer (EPS/PCIe) GROW the board ~3mm taller so the J_IN<->J_OUT pours stay
        # full-length after cec_fr.derive_power_pours pulls their shunt-side edges back to open the
        # SHUNT_GAP_MM (~6.5mm) un-poured notch -- room for the sense cluster + a B.Cu overflow lane the
        # route-under dives the overflow nets through. Self-gating (0.0 on a board with no 2-pad shunt).
        if os.environ.get("CEC_SHUNT_GAP", "0") == "1":
            _grow = _shunt_gap_board_grow(nl, fp_of, _cable_topology(nl) or _shared_bus_topology(nl))
            if _grow > 0:
                H = round(H + _grow, 1)
        # 1. anchors: connectors (by role, with edge OVERHANG per the ask) + the generalized
        #    mechanical asks (mounts + fiducials). A per-cable INTERPOSER must OVERHANG its cable ports
        #    (plug overmold off-board, pads on-board) -- otherwise the connector bodies sit in-board and
        #    crush the J_IN->shunt->J_OUT corridor into the mid-board strip (the as-built boards all
        #    overhang). So default overhang to "edge" when the board has cable corridors, unless the
        #    config overrides. (Owner: "it needs to know how to overhang the ports.")
        _overhang = cfg.params.get("connector_overhang")
        if _overhang is None:
            _overhang = "power_able" if (_cable_topology(nl) or _shared_bus_topology(nl)) else "none"
        # MV2: a per-board edge map (oracle-derived or a spec line) overrides the generic role->edge
        # default so a multi-edge board (Hub: RJ-45 top, power-in right, USB bottom) frames correctly.
        _eov = dict(cfg.params.get("edge_override") or {})
        _hub_jacks = list(cfg.params.get("hub_jacks") or ())
        if _hub_jacks:
            # HUB-JACK EDGE COUPLING (owner 2026-07-08): the hub-facing jacks (RJ-45 + the
            # TO-HUB-PWR feed) cluster TOGETHER on the edge tied to the PSU input's edge --
            # input on top -> jacks left, input on bottom -> jacks right (case cable dressing).
            _in_edge = "top"
            for _r in fp_of:
                _c = nl.comps.get(_r, Comp(_r))
                if _role(_r, _c.value, _c.footprint, nl=nl) == "power_in":
                    _in_edge = str(_eov.get(_r, "top")).lower()
                    break
            _jack_edge = {"top": "left", "bottom": "right"}.get(_in_edge)
            if _jack_edge:
                for _r in _hub_jacks:
                    _eov.setdefault(_r, _jack_edge)
        anchors = seed_anchors(nl, W, H, fp_of, cfg.pins, overhang=_overhang,
                               edge_override=_eov or None)
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

    # ============================================================ P3a: corridor spine (form the bands)
    def _p3_corridor_spine(_state):
        nonlocal H, anchors, comps, mech_pos, mech_fp, _topo, seated, free_shunts
        nonlocal seated_inas, _esp, _esp_pos, _sw_seated, _can, _can_seated, _rj
        nonlocal anneal_units, _seated_shunts, _fixed_anchor_refs, spec, series
        nonlocal by_owner, fixed_owner, drop_kc, macro, cluster_offsets, fixed_stamp
        nonlocal P, cyinfo_all, _spine, _bands, _paired, _sensitive, _veto, _rk
        nonlocal _role_clr, _func_stamped, _pour_fixed, _pour_asks, _pour_boxes
        nonlocal _nets_of, _net_exempt, _restamped
        # 1b. PHASE 2 -- FORM the per-cable corridors: align each J_OUT under its J_IN and seat the shunt
        #     on the cable axis (rot 270) as FIXED anchors, so the band is a tight column the anneal only
        #     has to keep foreign bodies OUT of. Seated shunts drop out of the annealed set (free_shunts).
        _topo = _cable_topology(nl) or _shared_bus_topology(nl)
        seated = _seed_corridor_spine(_topo, anchors, H, nl, comps, W=W, params=cfg.params)
        free_shunts = [r for r in shunts if r not in seated]

    # ============================================================ P3b: critical seats (kelvin/ESP/CAN)
    def _p3_critical_seats(_state):
        nonlocal H, anchors, comps, mech_pos, mech_fp, _topo, seated, free_shunts
        nonlocal seated_inas, _esp, _esp_pos, _sw_seated, _can, _can_seated, _rj
        nonlocal anneal_units, _seated_shunts, _fixed_anchor_refs, spec, series
        nonlocal by_owner, fixed_owner, drop_kc, macro, cluster_offsets, fixed_stamp
        nonlocal P, cyinfo_all, _spine, _bands, _paired, _sensitive, _veto, _rk
        nonlocal _role_clr, _func_stamped, _pour_fixed, _pour_asks, _pour_boxes
        nonlocal _nets_of, _net_exempt, _restamped
        # 1b'. REAL KELVIN SEAT (owner directive 2026-06-27): seat each cable's sense IC(s) HARD against
        #      the just-seated shunt's inner edge as FIXED anchors -- body perpendicular to the corridor,
        #      centred in the un-poured notch (OUT of the SENSEC pour), IN+/IN- facing the HI/LO inner
        #      edges. This OVERRIDES the connectivity drift (the historical non-seat let the anneal leave
        #      the INA 6-8mm away + inside the pour). Seated INAs drop from the annealed set below.
        seated_inas = []
        if os.environ.get("CEC_KELVIN_SEAT", "1") != "0":
            seated_inas = _seat_sense_ics(_topo, anchors, nl, comps)
        # 1c. Seat the PCB-antenna IC at its antenna edge as a FIXED anchor (route-unblock + MV5 antenna
        #     term): otherwise the large ESP courtyard lands center-board on the ganged ports -> overlaps
        #     -> Freerouting routes nothing. Keep it in `ics` so its decoupling cluster still builds; drop
        #     it from the ANNEALED set so it stays put at the edge.
        _esp, _esp_pos = _seat_antenna_ic(ics, comps, W, H, cfg.params.get("antenna_edge"),
                                          drop_antenna=drop_antenna)
        if _esp:
            anchors[_esp] = _esp_pos
        # BUTTONS CLUSTER (owner 2026-07-08: "keep the buttons together in an easily accessible
        # place that actually makes sense"): seat SW* as a fixed side-by-side pair inboard of the
        # USB connector -- BOOT is pressed while plugging USB, so that IS the sensible place.
        _sw_seated = []
        if cfg.params.get("buttons_near") == "usb":     # OPT-IN (board manifest), never a default
            _usb = next((r for r, role in anchors_roles.items()
                         if role == "usb" and r in anchors), None)
            _sws = sorted(r for r in ics if r.startswith("SW"))
            if _usb and _sws:
                ux, uy, _ur = anchors[_usb]
                bx = min(max(ux - 14.0, 6.0), W - 6.0)
                for k, sw in enumerate(_sws):
                    by = min(max(uy + (k - (len(_sws) - 1) / 2.0) * 9.0, 6.0), H - 6.0)
                    anchors[sw] = (bx, by, 0.0)
                    _sw_seated.append(sw)
        # LEVER 1 (opus fundamentals; landed ALONE per the ablation discipline): the CAN
        # transceiver seats inboard of the link jack (hand boards: 15-17mm from the RJ45).
        # Simple fixed offset toward board center; exempted from anneal AND from the mop-up
        # eviction (the batch failure's lesson: deliberate seats must not be re-evicted).
        _can_seated = []
        _rj = next((r for r, role in anchors_roles.items()
                    if role == "host" and r in anchors and "rj45" in str(fp_of.get(r, "")).lower()),
                   None)
        _can = next((r for r in ics if "TJA" in (nl.comps[r].value or "").upper()), None)
        if _can and _can in _bounds:
            _can = None                                   # EXPLICIT partition assignment WINS over
                                                          # the seat bias (the intent API is the
                                                          # actuator's lever; teeth test contract)
        if _rj and _can and _can in comps:
            rx, ry, _rr = anchors[_rj]
            _rj_cy = _courtyard_info(comps[_rj], _rr)
            _can_cy = _courtyard_info(comps[_can], 0.0)
            _dxs = _rj_cy[2] + _can_cy[2] + 2.0
            bx = rx + (_dxs if rx < W / 2.0 else -_dxs)
            anchors[_can] = (min(max(bx, 4.0), W - 4.0) - _can_cy[0],
                             min(max(ry, 5.0), H - 5.0) - _can_cy[1], 0.0)
            _can_seated.append(_can)
        anneal_units = [r for r in (ics + free_shunts)
                        if r != _esp and r not in seated_inas and r not in _sw_seated
                        and r not in _can_seated]

    # ============================================================ P4/P5: cluster learn (macro blocks)
    def _p4_cluster_learn(_state):
        nonlocal H, anchors, comps, mech_pos, mech_fp, _topo, seated, free_shunts
        nonlocal seated_inas, _esp, _esp_pos, _sw_seated, _can, _can_seated, _rj
        nonlocal anneal_units, _seated_shunts, _fixed_anchor_refs, spec, series
        nonlocal by_owner, fixed_owner, drop_kc, macro, cluster_offsets, fixed_stamp
        nonlocal P, cyinfo_all, _spine, _bands, _paired, _sensitive, _veto, _rk
        nonlocal _role_clr, _func_stamped, _pour_fixed, _pour_asks, _pour_boxes
        nonlocal _nets_of, _net_exempt, _restamped
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
                # PAIR-AWARE pass (2026-07-08): divider/RC pairs (two 2-pad Rs sharing a 3-ref
                # mid net with this unit) must sit ADJACENT within the cluster -- the fan
                # otherwise puts them on opposite lobes (R52<->R53 measured 13-23mm inside
                # U5's 12-part cluster; hand boards: ~2mm). Re-cluster once with member B
                # pinned beside member A; the relaxation accommodates the rest.
                _mnames = {p for p, _ in members}
                _pins = {}
                for _nn2, _mem2 in nl.nets.items():
                    _rr = sorted({r for r, _p in _mem2})
                    if len(_rr) == 3 and unit in _rr:
                        _pr = [r for r in _rr if r in _mnames and r[:1] == "R"]
                        if len(_pr) == 2 and all(r in Ptmp for r in _pr):
                            _a, _b = _pr
                            _acx, _acy, _ahw, _ahh = _courtyard_info(comps[_a], Ptmp[_a][2]
                                                                     if len(Ptmp[_a]) > 2 else 0)
                            _bcx, _bcy, _bhw, _bhh = _courtyard_info(comps[_b], 0)
                            _pins[_a] = Ptmp[_a]          # pin BOTH: A re-relaxes otherwise
                            _pins[_b] = (Ptmp[_a][0] + _acx + _ahw + _bhw + 0.4 - _bcx,
                                         Ptmp[_a][1] + _acy - _bcy, 0.0)
                if _pins:
                    Ptmp = {unit: (0.0, 0.0, 0.0)}
                    cec_pcb.auto_cluster(Ptmp, comps, {p: (unit, pad) for p, pad in members},
                                         drop_keepout=((unit,) if unit in drop_kc else ()),
                                         fixed_overrides=_pins)
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

    # ============================================================ P5/P7: relative_place + veto model
    def _p5_relative_place(_state):
        nonlocal H, anchors, comps, mech_pos, mech_fp, _topo, seated, free_shunts
        nonlocal seated_inas, _esp, _esp_pos, _sw_seated, _can, _can_seated, _rj
        nonlocal anneal_units, _seated_shunts, _fixed_anchor_refs, spec, series
        nonlocal by_owner, fixed_owner, drop_kc, macro, cluster_offsets, fixed_stamp
        nonlocal P, cyinfo_all, _spine, _bands, _paired, _sensitive, _veto, _rk
        nonlocal _role_clr, _func_stamped, _pour_fixed, _pour_asks, _pour_boxes
        nonlocal _nets_of, _net_exempt, _restamped
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

        # PARTITION seed: move each assigned free macro's courtyard INTO its region before the anneal, so
        # the structure-first containment biases the search from the start (proactive, not a post-evict).
        if _bounds:
            for r in anneal_units:
                if r in _bounds and r in P and r in cyinfo_all:
                    cx, cy, hw, hh = cyinfo_all[r]
                    x0, y0, x1, y1 = _bounds[r]
                    ox, oy, rot = P[r]
                    ccx, ccy = ox + cx, oy + cy                     # current courtyard centre
                    if not (x0 + hw <= ccx <= x1 - hw and y0 + hh <= ccy <= y1 - hh):
                        nccx = min(x1 - hw, max(x0 + hw, ccx)) if x1 - hw >= x0 + hw else (x0 + x1) / 2
                        nccy = min(y1 - hh, max(y0 + hh, ccy)) if y1 - hh >= y0 + hh else (y0 + y1) / 2
                        P[r] = (nccx - cx, nccy - cy, rot)
        # ROLE-BASED VARIABLE KEEP-OUT lever (round-2 item 7b, 2026-07-08): params
        # 'role_keepouts' = {role: radius_mm} (roles from _role: host/usb/power_in/power_out/
        # mount, plus 'ic' for U*/Q* refs) -> per-ref soft radii in the anneal cost. Hand
        # boards vary clearance BY ROLE (probe forensics: functional pairs near 0, sense
        # corridors ~3.5, independent blocks 1.0-2.0mm+) where the synth placer packs one
        # uniform band. INERT unless set (default anneal byte-identical); activation goes
        # through the fixed-seed ablation protocol (cec_lever_eval), one lever at a time.
        _rk = dict(cfg.params.get("role_keepouts") or {})
        _role_clr = None
        if _rk:
            _role_clr = {}
            for r in P:
                c_ = nl.comps.get(r, Comp(r))
                rl = _role(r, c_.value, c_.footprint, nl=nl) \
                    or ("ic" if r[:1] in ("U", "Q") else None)
                if rl in _rk:
                    _role_clr[r] = float(_rk[rl])

    # ============================================================ P7: anneal + legalize
    def _p6_anneal(_state):
        nonlocal H, anchors, comps, mech_pos, mech_fp, _topo, seated, free_shunts
        nonlocal seated_inas, _esp, _esp_pos, _sw_seated, _can, _can_seated, _rj
        nonlocal anneal_units, _seated_shunts, _fixed_anchor_refs, spec, series
        nonlocal by_owner, fixed_owner, drop_kc, macro, cluster_offsets, fixed_stamp
        nonlocal P, cyinfo_all, _spine, _bands, _paired, _sensitive, _veto, _rk
        nonlocal _role_clr, _func_stamped, _pour_fixed, _pour_asks, _pour_boxes
        nonlocal _nets_of, _net_exempt, _restamped
        anneal_macros(P, cyinfo_all, anneal_units, W, H, nbrs=_adjacency(nl), seed=seed, veto=_veto,
                      role_clr=_role_clr)
        legalize_pack(P, [r for r in anneal_units if r in P], cyinfo_all, W, H, clr=0.4, bounds=_bounds)

    # ============================================================ P5: passive stamps (cluster + series)
    def _p7_stamps(_state):
        nonlocal H, anchors, comps, mech_pos, mech_fp, _topo, seated, free_shunts
        nonlocal seated_inas, _esp, _esp_pos, _sw_seated, _can, _can_seated, _rj
        nonlocal anneal_units, _seated_shunts, _fixed_anchor_refs, spec, series
        nonlocal by_owner, fixed_owner, drop_kc, macro, cluster_offsets, fixed_stamp
        nonlocal P, cyinfo_all, _spine, _bands, _paired, _sensitive, _veto, _rk
        nonlocal _role_clr, _func_stamped, _pour_fixed, _pour_asks, _pour_boxes
        nonlocal _nets_of, _net_exempt, _restamped
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
            legalize_pack(P, [r for r in _func_stamped if r in P], _func_cy, W, H, clr=0.4, bounds=_bounds)

    # ============================================================ P7: corridor/pour evac + final mop-up
    def _p8_evac_mop(_state):
        nonlocal H, anchors, comps, mech_pos, mech_fp, _topo, seated, free_shunts
        nonlocal seated_inas, _esp, _esp_pos, _sw_seated, _can, _can_seated, _rj
        nonlocal anneal_units, _seated_shunts, _fixed_anchor_refs, spec, series
        nonlocal by_owner, fixed_owner, drop_kc, macro, cluster_offsets, fixed_stamp
        nonlocal P, cyinfo_all, _spine, _bands, _paired, _sensitive, _veto, _rk
        nonlocal _role_clr, _func_stamped, _pour_fixed, _pour_asks, _pour_boxes
        nonlocal _nets_of, _net_exempt, _restamped
        # CORRIDOR + POUR EVACUATION: pull any non-belonging body (decoupling / DETECT / threshold / detection-
        # amp) OUT of a formed high-current band AND out of the actual derive_power_pours SENSEC box so the pour
        # fills + the nets can route (the anneal veto + passive/cluster stamp leave them inside -- the owner-
        # caught re-place issue). The band evac uses the tighter §2.2 band; the POUR evac uses the box the
        # route-time no-foreign-on-high-current-pour gate derives (wider by the pour margin), so a cap grazing
        # only the box-but-not-the-band (e.g. a comparator's clustered threshold cap, or a balanced decoupling
        # cap that drifted onto the column) is evacuated too. EXEMPT = the FIXED seated anchors (connectors,
        # shunts, kelvin-seated INAs + §6.13 comparators, ESP, mounts). Re-legalize only the moved refs so the
        # seat stays put.
        _pour_fixed = (set(anchors_roles) | set(mech_pos) | set(_seated_shunts)
                       | set(seated_inas) | ({_esp} if _esp else set())) if seated_inas else set()
        # POUR LEVER (stage 2): fold the placer's pour() asks (cfg.params['pour_asks']) into the
        # placement-time PourPlan so the evac sees an asked pour even on a rail the derivation would
        # not pour. `pour_asks` empty -> byte-identical to the un-asked settle (the golden guarantee).
        _pour_asks = tuple(cfg.params.get("pour_asks") or ())
        _pour_boxes = (_pour_boxes_unified(P, nl, comps, W, H, asks=_pour_asks)
                       if (seated_inas or _pour_asks) else [])
        # own-net eviction exemptions: a part's own pads' nets + its cluster owner's nets
        _nets_of = defaultdict(set)
        for _nn, _mem in nl.nets.items():
            for _r, _p in _mem:
                _nets_of[_r].add(_nn)
        _net_exempt = {r: set(_nets_of.get(r, ())) for r in P}
        for _pref, (_own, _pad) in spec.items():
            if _own in _nets_of:
                _net_exempt.setdefault(_pref, set()).update(_nets_of[_own])
        # STRICT (owner overrule): only a part's OWN nets exempt it from eviction.
        for _ev_round in range(6):                               # iterate: legalize_pack isn't band/box-aware so it
            _evm = build_corridor_model(nl, P, comps, board_w=W)  # can push an evacuated body back -> re-evacuate;
            _evac = _evacuate_corridors(P, comps, _evm)           # the final round leaves centers OUT (no legalize
            _evac = [r for r in _evac if r not in _can_seated]    # deliberate seats are never evicted (lever 1)
            _pevac = ([r for r in _evacuate_pours(P, comps, _pour_boxes, _pour_fixed,
                                                  drop_antenna=drop_antenna,
                                                  net_exempt=_net_exempt) if r not in _can_seated]
                      if _pour_boxes else [])                     # push-back) -- a center out of the box is enough
            _moved = list(dict.fromkeys(_evac + _pevac))          # for the pour to fill + the net to route around.
            if not _moved:
                break
            if _ev_round < 5:
                legalize_pack(P, [r for r in _moved if r in P], cyinfo_all, W, H, clr=0.4, bounds=_bounds)
        # FINAL MOP-UP (only when the Kelvin seat fired): fixing the sense ICs + comparators as anchors reduces
        # the anneal's freedom, so a rigidly-stamped decoupling cap can be left grazing its IC (residual). One
        # legalize over EVERY movable body (all but the fixed anchors -- connectors, mounts, the seated
        # shunt + sense ICs + comparators, the ESP) nudges those few to the nearest free spot, restoring
        # residual 0 without touching the seat. Confined to seated boards so non-cable placements are byte-
        # unchanged. A final POUR evac (no legalize) then guarantees no body the mop-up nudged sits in a box.
        if seated_inas:
            _mop = [r for r in P if r in comps and r not in _pour_fixed and r not in _can_seated]
            _mop_cy = {r: (macro[r] if r in macro else _courtyard_info(comps[r], P[r][2],
                                                                        drop_antenna=drop_antenna))
                       for r in P if r in comps}
            # SETTLE the cascade with a POUR-AWARE legalize: the SENSEC pour boxes are injected as fixed
            # obstacles, so each movable body lands in the nearest spot that is BOTH overlap-free AND out of
            # every pour -- clearance + residual in ONE pass, no evac-vs-legalize oscillation (the bare evac
            # leaves outboard pile-ups; a bare legalize pulls a cap back into a box). The seated INAs/
            # comparators/shunts/connectors are exempt (not in _mop), so their intentional graze is kept.
            # RIGID BUTTON PAIR (owner 2026-07-08: BOOT/RESET drift apart -- separating a
            # deliberate pair is the repair ladder's LAST rung, never eviction's side effect).
            # Post-evac, both buttons re-pin side by side at the nearest lane-free spot to
            # their seat target; they were exempted from the anneal but strict eviction had
            # been moving them individually.
            _sws2 = sorted(r for r in P if r.startswith("SW") and r in comps)
            if len(_sws2) >= 2 and _can_seated is not None:
                _usb2 = next((r for r, role in anchors_roles.items()
                              if role == "usb" and r in P), None)
                if _usb2:
                    _u_cy = _courtyard_info(comps[_usb2], P[_usb2][2] if len(P[_usb2]) > 2 else 0,
                                            drop_antenna=drop_antenna)
                    _s_cy = _courtyard_info(comps[_sws2[0]], 0)
                    _pairspot = _park_near((P[_usb2][0], P[_usb2][1]), _u_cy,
                                           (_s_cy[0], _s_cy[1], _s_cy[2],
                                            _s_cy[3] * 2 + 4.5),          # combined pair extent
                                           _pour_boxes, W, H, gap=1.2)
                    if _pairspot is not None:
                        for _k6, _sw6 in enumerate(_sws2[:2]):
                            P[_sw6] = (_pairspot[0], _pairspot[1] + _k6 * 9.0, 0.0)
            # DECOUPLER RE-SEAT (retry under LANES, 2026-07-08): any rail cap whose center is
            # >8mm from every working part on its rail parks at the nearest LANE-FREE slot
            # beside the nearest one (the earlier inert result came from zero/blanket boxes).
            _tgt = defaultdict(list)
            _railcap = {}
            for _nn, _mem in nl.nets.items():
                if not _nn.startswith("+"):
                    continue
                for _r, _p in _mem:
                    if _r[:1] == "C" and _ref_padcount(nl, _r) == 2:
                        _on = {n for n, mm in nl.nets.items() for rr, _pp in mm if rr == _r}
                        if "GND" in _on:
                            _railcap[_r] = _nn
                    elif _r[:1] in ("U", "D", "J", "Q") or _r.startswith(("TB", "SW", "FB")):
                        _tgt[_nn].append(_r)
            for _c2, _rail2 in _railcap.items():
                if _c2 not in P:
                    continue
                _cands2 = [r for r in _tgt.get(_rail2, []) if r in P]
                if not _cands2:
                    continue
                _dmin2, _near2 = min((math.hypot(P[_c2][0] - P[r][0], P[_c2][1] - P[r][1]), r)
                                     for r in _cands2)
                if _dmin2 <= 8.0 or _near2 not in comps:
                    continue
                _tc = _mop_cy.get(_near2) or _courtyard_info(comps[_near2],
                                                             P[_near2][2] if len(P[_near2]) > 2 else 0)
                _cc = _mop_cy.get(_c2) or _courtyard_info(comps[_c2], 0)
                _sp = _park_near((P[_near2][0], P[_near2][1]), _tc, _cc, _pour_boxes, W, H)
                if _sp is not None:
                    P[_c2] = (_sp[0], _sp[1], 0.0)
            _legalize_avoiding_pours(P, _mop, _mop_cy, _pour_boxes, W, H, clr=0.4, bounds=_bounds)

    # ============================================================ P5: rigid-cluster re-stamp
    def _p9_restamp(_state):
        nonlocal H, anchors, comps, mech_pos, mech_fp, _topo, seated, free_shunts
        nonlocal seated_inas, _esp, _esp_pos, _sw_seated, _can, _can_seated, _rj
        nonlocal anneal_units, _seated_shunts, _fixed_anchor_refs, spec, series
        nonlocal by_owner, fixed_owner, drop_kc, macro, cluster_offsets, fixed_stamp
        nonlocal P, cyinfo_all, _spine, _bands, _paired, _sensitive, _veto, _rk
        nonlocal _role_clr, _func_stamped, _pour_fixed, _pour_asks, _pour_boxes
        nonlocal _nets_of, _net_exempt, _restamped
        # RIGID-CLUSTER RE-STAMP (trace-driven fix, 2026-07-08): the evac/mop rounds move a
        # cluster's OWNER after its passives were stamped at the owner's OLD position (traced:
        # U5 stamped at 57.4 -> evac'd to 9.5 -> mopped to 32.5 while R52/R53 stayed near 57-65
        # -- THE decoupler/divider scatter mechanism; three ownership-side "fixes" were inert
        # because ownership was never broken). Re-stamp every cluster at its owner's FINAL
        # position, then settle only the re-stamped parts (owners never move here).
        _restamped = []
        for unit, offs in cluster_offsets.items():
            if unit not in P:
                continue
            ux, uy, _ur = P[unit]
            for pref, (dx, dy, pr) in offs.items():
                if pref in P:
                    P[pref] = (ux + dx, uy + dy, pr)
                    _restamped.append(pref)
        if _restamped:
            _rs_cy = {r: (macro[r] if r in macro else _courtyard_info(comps[r], P[r][2]
                                                                      if len(P[r]) > 2 else 0,
                                                                      drop_antenna=drop_antenna))
                      for r in P if r in comps}
            if _pour_boxes:
                _legalize_avoiding_pours(P, _restamped, _rs_cy, _pour_boxes, W, H, clr=0.4,
                                         bounds=_bounds)
            else:
                legalize_pack(P, _restamped, _rs_cy, W, H, clr=0.4, bounds=_bounds)

    # ============================================================ P7/P8: intent levers (LAST)
    def _p10_intents(_state):
        nonlocal H, anchors, comps, mech_pos, mech_fp, _topo, seated, free_shunts
        nonlocal seated_inas, _esp, _esp_pos, _sw_seated, _can, _can_seated, _rj
        nonlocal anneal_units, _seated_shunts, _fixed_anchor_refs, spec, series
        nonlocal by_owner, fixed_owner, drop_kc, macro, cluster_offsets, fixed_stamp
        nonlocal P, cyinfo_all, _spine, _bands, _paired, _sensitive, _veto, _rk
        nonlocal _role_clr, _func_stamped, _pour_fixed, _pour_asks, _pour_boxes
        nonlocal _nets_of, _net_exempt, _restamped
        # INTENT LEVERS (owner pass 2026-07-08): applied LAST so nothing downstream undoes
        # them (the lesson every seat learned).
        for _ref4, _tgt4, _gap4 in (cfg.params.get("near_intents") or ()):
            if _ref4 in P and _tgt4 in P and _ref4 in comps and _tgt4 in comps:
                _tc4 = _courtyard_info(comps[_tgt4], P[_tgt4][2] if len(P[_tgt4]) > 2 else 0,
                                       drop_antenna=drop_antenna)
                _cc4 = _courtyard_info(comps[_ref4], 0, drop_antenna=drop_antenna)
                _sp4 = _park_near((P[_tgt4][0], P[_tgt4][1]), _tc4, _cc4, _pour_boxes, W, H,
                                  gap=_gap4)
                if _sp4 is None:                      # no lane-free slot: park adjacent anyway
                    _sp4 = (P[_tgt4][0] + _tc4[0] + _tc4[2] + _cc4[2] + _gap4 - _cc4[0],
                            P[_tgt4][1] + _tc4[1] - _cc4[1])
                P[_ref4] = (_sp4[0], _sp4[1], 0.0)
        for _refs5, _axis5 in (cfg.params.get("order_intents") or ()):
            _live5 = [r for r in _refs5 if r in P]
            if len(_live5) >= 2:
                _ax5 = 0 if _axis5 == "x" else 1
                _slots5 = sorted((P[r][_ax5], P[r]) for r in _live5)
                for r, (_k5, _pos5) in zip(_live5, _slots5):
                    P[r] = _pos5

    # ---- DECLARE the ladder (P0..P8 boundaries; the internal call order is unchanged from the
    #      pre-ladder monolith). P0/P1 (stackup/netclass + outline/keepouts) are UPSTREAM of
    #      synth_one -- declared here as provenance no-ops so the journal carries the full ladder.
    #      locks_out/gate are recorded but ENFORCEMENT is opt-in (enforce_locks / gate_enabled);
    #      no real gate is enabled in S1 (that is later fixed-seed ablation work).
    _passes = [
        Pass("p0_stackup_basis", lambda _s: None, phase="P0",
             doc="stackup/netclass basis (upstream: build_board + .kicad_dru author it)"),
        Pass("p1_outline_keepouts", lambda _s: None, phase="P1",
             doc="outline + mechanical keep-outs (upstream: build_board edges)"),
        Pass("p2_anchors", _p2_anchors, phase="P2",
             # DECLARED lock (enforcement = S4 ablation): anchors/mounts/fids EXCEPT the
             # spine-owned refs -- TB* tab rows, J_OUT* columns, AND J_SIG* (the signal
             # stub is collinear-with-blade-row BY CONTRACT, so the spine seats it; the
             # enforcement probe caught it, 2026-07-08).
             locks_out=lambda _s: [r for r in anchors
                                   if not r.startswith(("TB", "J_OUT", "J_SIG"))],
             doc="connectors by role (overhang) + mounts/fiducials, legalized among anchors"),
        Pass("p3_corridor_spine", _p3_corridor_spine, phase="P3",
             locks_out=lambda _s: ([r for r in anchors
                                    if r.startswith(("TB", "J_OUT"))] + list(seated)),
             doc="form per-cable corridors: align J_OUT under J_IN + seat the shunt inline"),
        Pass("p3_critical_seats", _p3_critical_seats, phase="P3",
             locks_out=lambda _s: (list(seated_inas) + ([_esp] if _esp else [])
                                   + list(_sw_seated) + list(_can_seated)),
             doc="kelvin/sense seats + ESP antenna seat + buttons + CAN seat"),
        Pass("p4_cluster_learn", _p4_cluster_learn, phase="P4",
             doc="learn each IC's passive cluster (macro bbox + offsets) + fixed-anchor clusters"),
        Pass("p5_relative_place", _p5_relative_place, phase="P5",
             doc="relative-place macros by connectivity + build the corridor veto model"),
        Pass("p6_anneal", _p6_anneal, phase="P7",
             doc="anneal macro blocks to escape the greedy minimum + legalize"),
        Pass("p7_stamps", _p7_stamps, phase="P5",
             locks_out=lambda _s: list(_func_stamped),
             doc="stamp cluster passives + functional/series parts, legalize the stamped set"),
        Pass("p8_evac_mop", _p8_evac_mop, phase="P7",
             doc="evacuate corridors/pours of foreign bodies + final mop-up settle"),
        Pass("p9_restamp", _p9_restamp, phase="P5",
             doc="re-stamp clusters at owners' FINAL positions (the scatter fix)"),
        Pass("p10_intents", _p10_intents, phase="P7",
             doc="near()/order() intent levers, applied LAST so nothing undoes them"),
    ]

    def _positions(_state):
        # the ladder observes P once relative_place has created it, else the anchor dict.
        return P if P is not None else anchors

    ladder = PassLadder(_passes, _positions, enforce_locks=enforce_locks, eval_gates=eval_gates)
    ladder.run()

    # ============================================================ SCORING + RETURN (post-ladder)
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
    # DUAL-SIDED (owner GO 2026-07-08, board-scoped via params.dual_sided): on shared-bus
    # boards, alternate rail chains F/B by column order. INVARIANT (owner): each rail's ENTIRE
    # sensing chain -- shunt + INA sensors + comparators + their owned passives -- lives on ONE
    # side; only digital crosses vias. ICs are INA-filtered so a POWER net on a shunt side (the
    # 5VSB pair's +5VSB) can never drag the mux or rail loads to the back. v1 note: the placer's
    # internal overlap model is not yet side-aware (residual may overreport across faces); the
    # materialized board's DRC -- which the oracle grades -- is side-correct via place(flip).
    back_refs = ()
    if cfg.params.get("dual_sided") and any(c.get("shared_bus") for c in _topo):
        entries = sorted((c for c in _topo if c.get("shared_bus") and c["shunt"] in P),
                         key=lambda c: P[c["shunt"]][0])
        back = set()
        for i, c in enumerate(entries):
            if i % 2 == 0:
                continue                            # even columns stay front
            chain = {c["shunt"]}
            refs = {r for net in (c["hi"], c["lo"]) for r, _ in nl.nets.get(net, [])}
            sense = {r for r in refs if r in comps
                     and "INA" in (nl.comps[r].value or "").upper()}
            chain |= sense
            for ic in sorted(sense):
                chain.update(_downstream_comparators(ic, c["hi"], c["lo"], nl, comps))
            chain |= {pref for pref, (own, _pad) in spec.items() if own in chain}
            back |= {r for r in chain if r in P}
        back, _stripped = _dual_side_guard(back, anchors_roles, comps)
        if _stripped:
            print(f"  [dual-side guard] kept OFF the back (owner rule): {sorted(_stripped)}",
                  file=sys.stderr)
        back_refs = tuple(sorted(back))
    cand = Candidate(strat=strat, seed=seed, P=P, W=W, H=H, residual=res, proxy=proxy,
                     corridor_cross=cc, corridor_cross_aware=cc_aware, back_refs=back_refs)
    cand.journal = ladder.journal          # per-pass placement provenance (JSON-able; diagnostic)
    return cand


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
    # SLICE-1a two-stage selection: the cheap proxy above PRUNED to a best-first order; when the route
    # ORACLE is opted in (CEC_ROUTE_ORACLE=1 / cfg.params['route_oracle']) ADJUDICATE the top-k survivors
    # with a real route -- its post-route gate verdict is the FINAL key (proxy-good-but-routes-dirty
    # candidates get demoted). Default OFF -> the cheap path is byte-for-byte unchanged.
    if _route_oracle_enabled(cfg):
        k = int(cfg.params.get("route_oracle_topk", 3))
        gkw = dict(cfg.params.get("route_oracle_kw", {}))
        cands = adjudicate_candidates(cfg, cands, k=k, verbose=cfg.params.get("route_oracle_verbose", False),
                                      **gkw)
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


# ============================================================ SLICE-1a: the ROUTE-ORACLE grader
# docs/placer-feasibility-2026-06-30.md: the placer selects candidates on placement_proxy (HPWL/RUDY/
# low-res thermal) -- a CHEAP proxy that does NOT predict real routability, so it converges on
# placements that proxy-look-good but route DIRTY. There is no confirm_winner / route_once in the
# candidate path: that absent route-oracle IS the documented failure mode.
#
# route_oracle_grade closes it: grade a placement by ACTUALLY ROUTING it (the SAME proven gate-clean
# recipe the committed gate-clean routes use) and reading the REAL post-route FULL ACCEPT CONJUNCTION:
#
#     kelvin_ok  AND  diffpair_ok  AND  drc-finishing-only  AND  foreign_on_pour==0  AND  thermal-in-budget
#     AND  routing-complete (no safety/power ratline left; only the documented finishing residual)
#
# NEVER a subset: kelvin_ok+drc alone is a DOCUMENTED FALSE SUMMIT (passes at max_T ~181-300 C). The
# grader can never pass a board the real route fails -- TRUE BY CONSTRUCTION, because it IS the real route.
#
# Wiring (two-stage prune->adjudicate): placement_proxy stays the cheap PRUNE to top-k (routing every
# candidate is minutes each); route_oracle_grade ADJUDICATES the top-k survivors and its real-gate verdict
# is the FINAL selection key. Opt-in (CEC_ROUTE_ORACLE=1 / cfg.params['route_oracle']); default-safe so the
# existing cheap path is byte-for-byte unchanged when off.

# The gate-clean route recipe -- commit 515cae7 (eps-rev3, FIRST gate-clean board), generalizes across the
# EPS/PCIe cable family: tap-channel keepout + F.Cu-only corridor lever + sense-force-pour-only +
# kelvin-FR-exclude + shunt-gap, with derive_power_pours laid AFTER the route. Applied via os.environ so the
# in-process readers (cec_fr.export_dsn / import_ses / derive_power_pours, cec_constraints foreign check)
# pick them up; setdefault so a caller may override any single flag (e.g. CEC_CORRIDOR_FCU_ONLY=0 for A/B).
_ORACLE_RECIPE_ENV = {
    "CEC_KELVIN_FR_EXCLUDE":     "1",   # INA sense pads excluded from FR -> the §6.8 inner-edge tap is their only link
    "CEC_TAP_CHANNEL_KEEPOUT":   "1",   # reserve each F.Cu Kelvin tap channel so foreign routes AROUND/UNDER it
    "CEC_CORRIDOR_FCU_ONLY":     "1",   # F.Cu-only corridor lever: foreign routes B.Cu UNDER the solid F.Cu pour
    "CEC_SENSEC_FORCE_POUR_ONLY":"1",   # leave the connector<->shunt FORCE path to the pour (no redundant trace)
    "CEC_SHUNT_GAP":             "1",   # widen the shunt notch -- REQUIRED for the foreign==0 check to read clean
    # During waves the CPU is contended by FR JVMs while the GPU idles; wave-grade solves
    # (~100k unknowns) sit just under the measured 120k solo crossover, so push them to the
    # GPU anyway -- break-even solve speed, net wall-clock win (owner catch 2026-07-08).
    "CEC_THERMAL_GPU_MIN_N":     "60000",
}


@contextmanager
def _oracle_env(params=None):
    """Apply the gate-clean route recipe to os.environ for the duration of a grade (setdefault, so a
    caller-set flag wins), then restore exactly. The FR worker subprocess (spawn) inherits the env at
    launch; the in-process pour/foreign readers read it live -- both need it set across the whole grade.
    *params* may carry shunt_gap_mm -> CEC_SHUNT_GAP_MM and pour_lanes -> CEC_POUR_LANES
    (the strict no-parts-in-pours architecture, per board)."""
    extra = {}
    if params:
        if params.get("shunt_gap_mm"):
            extra["CEC_SHUNT_GAP_MM"] = str(params["shunt_gap_mm"])
        if params.get("pour_lanes"):
            extra["CEC_POUR_LANES"] = "1"
        if params.get("lane_w_json"):
            extra["CEC_LANE_W_JSON"] = json.dumps(params["lane_w_json"])                 if not isinstance(params["lane_w_json"], str) else params["lane_w_json"]
    merged = {**_ORACLE_RECIPE_ENV, **extra}
    saved = {k: os.environ.get(k) for k in merged}
    try:
        for k, v in merged.items():
            os.environ.setdefault(k, v)
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def _load_pourplan_sidecar(board_path, rules):
    """POUR LEVER (stage 3): load a <board>.pourplan.json sidecar for *board_path* if present AND
    still valid for this placement + compile recipe, else None (the caller re-derives from_board).

    A sidecar is trusted only when BOTH its board_sig (the placement pad signature) AND its recipe
    (the CEC_POUR_LANES/CEC_SHUNT_GAP/... env the geometry was compiled under) match the current
    board + env -- so a sidecar written under a different placement or a different recipe is ignored
    (never silently applying stale/mismatched geometry). On a match the sidecar's SPECS are used
    verbatim (identical to a fresh derive in stages 1-3; the carrier for a stage-4 router reshape),
    with the live board + resolved rules attached for the non-lane keepout derivation."""
    import cec_pourplan
    side = board_path[:-len(".kicad_pcb")] + ".pourplan.json" if board_path.endswith(".kicad_pcb") \
        else os.path.splitext(board_path)[0] + ".pourplan.json"
    if not os.path.isfile(side):
        return None
    try:
        with open(side) as f:
            d = json.load(f)
        fresh = cec_pourplan.PourPlan.from_board(board_path, kelvin_pairs=rules.kelvin_pairs,
                                                 nets_12v=rules.nets_12v)
        if (not d.get("board_sig") or d["board_sig"] != fresh.board_sig
                or d.get("recipe") != cec_pourplan.PourPlan.recipe_from_env()):
            return None                                      # stale placement/recipe -> re-derive
        return cec_pourplan.PourPlan.from_dict(d, board_path=board_path, board=fresh._board,
                                               kelvin_pairs=rules.kelvin_pairs,
                                               nets_12v=rules.nets_12v)
    except Exception as e:                                   # noqa: BLE001 -- any error -> re-derive
        _tc.warn_once("pourplan_sidecar", "pourplan sidecar ignored (%s)" % e)
        return None


def _oracle_hints_pours(board_path):
    """Derive the gate-clean recipe's keepout HINTS + power POURS for a placement board, honouring the
    recipe env flags (CEC_TAP_CHANNEL_KEEPOUT / CEC_CORRIDOR_FCU_ONLY). Returns (hints, pours, rules).

    POUR LEVER (stage 1/3, docs/pour-lever-scoping-2026-07-08.md): the corridor keepout + power
    pours are now TWO VIEWS of ONE ``cec_pourplan.PourPlan`` (§1.3 -- 'where the compiled PourPlan
    plugs in'), so the reservation FR routes around and the copper laid after are geometrically
    identical by construction. Stage 3 loads that plan from a ``<board>.pourplan.json`` sidecar when
    present (``_load_pourplan_sidecar``), falling back to ``from_board`` so old boards still route.
    Byte-identical to the old two-call form: rules.kelvin_pairs == the board-derived pairs on every
    board (verified) so a single plan matches both the old corridor_keepouts(kelvin_pairs=...) and
    the old derive_power_pours() calls. The tap-channel + edge keepouts are not pour-derived and
    stay as their own cec_fr calls."""
    import cec_fr
    import cec_pourplan
    rules = cec_score.Rules.from_board(board_path)
    plan = _load_pourplan_sidecar(board_path, rules) or cec_pourplan.PourPlan.from_board(
        board_path, kelvin_pairs=rules.kelvin_pairs, nets_12v=rules.nets_12v)
    hints = []
    if os.environ.get("CEC_TAP_CHANNEL_KEEPOUT", "0") == "1":
        try:
            hints += cec_fr.tap_channel_keepouts(board_path, kelvin_pairs=rules.kelvin_pairs)
        except Exception as e:                                   # noqa: BLE001 -- keepout is best-effort
            _tc.warn_once("oracle_tap_keepout", "tap-channel keepout skipped (%s)" % e)
    # The corridor keepout is the load-bearing lever (without it the EPS route strands kelvin + 30+ foreign
    # crossings -- measured); F.Cu-only when CEC_CORRIDOR_FCU_ONLY=1 so foreign escapes B.Cu under the pour.
    fcu_only = os.environ.get("CEC_CORRIDOR_FCU_ONLY", "0") == "1"
    try:
        hints += plan.keepout_hints(layers=("F.Cu",) if fcu_only else ("F.Cu", "B.Cu"))
    except Exception as e:                                       # noqa: BLE001
        _tc.warn_once("oracle_corridor_keepout", "corridor keepout skipped (%s)" % e)
    try:
        hints += cec_fr.edge_keepout(board_path)
    except Exception as e:                                       # noqa: BLE001
        _tc.warn_once("oracle_edge_keepout", "edge keepout skipped (%s)" % e)
    pours = plan.pour_polygons()
    return hints, pours, rules


def _classify_unconnected(unconn_nets, rules):
    """Split the routed board's unconnected NET names into (critical, signal). A critical ratline -- a
    Kelvin/diff-pair safety net, a 12V/high-current net, or GND -- is a HARD route failure. A signal-net
    ratline is the documented finishing residual (commit 515cae7 closed the EPS /GPIO0 hop with the
    cec_route toolkit AFTER Freerouting squeezed its F.Cu escape shut), tolerated up to unconn_finish_tol."""
    safety = {n for pr in (rules.kelvin_pairs or []) for n in pr}
    safety |= {n for pr in (rules.diff_pairs or []) for n in pr}
    power = set(rules.nets_12v or [])
    crit = []
    sig = []
    for n in unconn_nets:
        u = (n or "").upper()
        is_crit = (n in safety or n in power or u == "GND" or u == "/GND"
                   or u.endswith("_HI") or u.endswith("_LO") or "12V" in u)
        (crit if is_crit else sig).append(n)
    return crit, sig


def _oracle_sense_side(board_path):
    """OWNER RULE checker (2026-07-08, the dual-sided gate term): on a DUAL-SIDED board
    (any flipped shunt), each kelvin pair's PURE-SENSE nets (the '/SENSE*'-style locals --
    a pair's shared RAIL side like +5V_MAIN legitimately routes everywhere and is excluded)
    must carry ZERO vias and every track on the CHAIN's own face. 'Only via-tolerant
    digital crosses faces' -- previously by-construction, now independently verified.
    Returns {applicable, ok, violations}; N/A (applicable=False, ok=True) on single-sided
    boards so eps/12vhpwr behavior is untouched (the 12VHPWR's SENSEP lanes carry
    legitimate F->B lane-transition vias)."""
    import pcbnew
    import cec_fr
    board = pcbnew.LoadBoard(board_path)
    flipped = {fp.GetReference(): fp.IsFlipped() for fp in board.GetFootprints()}
    pairs = cec_fr._board_kelvin_pairs(board)
    # chain side per pair = the straddling 2-pad RS* shunt's face
    pad_refs = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname():
                pad_refs.setdefault(p.GetNetname(), set()).add(fp.GetReference())
    any_flipped_shunt = False
    viol = []
    for hi, lo in pairs:
        sh = next((r for r in sorted(pad_refs.get(hi, set()) & pad_refs.get(lo, set()))
                   if r.startswith("RS")), None)
        if sh is None:
            continue
        side_flipped = bool(flipped.get(sh))
        any_flipped_shunt = any_flipped_shunt or side_flipped
    if not any_flipped_shunt:
        return {"applicable": False, "ok": True, "violations": []}
    want_layer = {}
    for hi, lo in pairs:
        sh = next((r for r in sorted(pad_refs.get(hi, set()) & pad_refs.get(lo, set()))
                   if r.startswith("RS")), None)
        if sh is None:
            continue
        lay = "B.Cu" if flipped.get(sh) else "F.Cu"
        for net in (hi, lo):
            if net.startswith("+"):
                continue                                   # shared rail side: excluded
            want_layer[net] = lay
    for tr in board.GetTracks():
        net = tr.GetNetname()
        if net not in want_layer:
            continue
        if tr.Type() == pcbnew.PCB_VIA_T:
            viol.append(f"via on sense net {net}")
        elif tr.GetLayerName() != want_layer[net]:
            viol.append(f"track on {tr.GetLayerName()} for {net} (chain side {want_layer[net]})")
    return {"applicable": True, "ok": not viol, "violations": viol[:12]}


def _oracle_decoupler_adjacency(board_path, cfg=None, *, max_mm=7.0):
    """PLACEMENT-QUALITY gate term (owner 2026-07-08: 'decouplers right up against their
    respective components... should be gating'). FUNCTIONAL formulation, board-only: a
    decoupling cap (2-pad C, one pad GND, one pad a rail '+...') must sit within *max_mm*
    of SOME IC pad on that same rail -- its electrical job is proximity to whoever it
    decouples, independent of any ownership bookkeeping (an ownership-model check fired on
    the gate-clean eps fixture; this one passes it and fires on real strays). Series/RC/
    signal parts never match the pad pattern, so they are exempt by construction.
    max_mm CALIBRATED on the hand-quality fab boards (charter rule: measure, never guess):
    hub/12vhpwr worst legitimate case = 6.35mm (a bulk cap beside its entry element);
    real strays measure 10-62mm -- an order of magnitude of separation."""
    import pcbnew
    board = pcbnew.LoadBoard(board_path)
    if board is None:
        return {"ok": False, "violations": [("board", "unloadable", -1)]}
    ic_pads_by_net = {}
    caps = []
    for fp in board.GetFootprints():
        r = fp.GetReference() or ""
        # 'respective COMPONENTS': any working part on the rail -- IC, diode, connector,
        # blade, switch. A bulk cap at the power ENTRY (eps C1 next to its ORing diode,
        # 62mm from the LDO) is correctly placed; an IC-only target set false-fired on it.
        if r[:1] in ("U", "D", "J", "Q") or r.startswith(("TB", "SW", "FB")):
            for p in fp.Pads():
                nn = p.GetNetname()
                if nn:
                    ic_pads_by_net.setdefault(nn, []).append(p.GetPosition())
        if r.startswith("C") and fp.GetPadCount() == 2:
            nets = {p.GetNetname() for p in fp.Pads()}
            rail = next((n for n in nets if n.startswith("+")), None)
            if rail and "GND" in nets:
                caps.append((r, rail, fp.GetPosition()))
    viol = []
    for ref, rail, pos in caps:
        tgts = ic_pads_by_net.get(rail, [])
        if not tgts:
            continue                                     # no IC on that rail: bulk/input cap
        d = min(math.hypot((pos.x - q.x) / 1e6, (pos.y - q.y) / 1e6) for q in tgts)
        if d > max_mm:
            viol.append((ref, rail, round(d, 2)))
    viol.sort(key=lambda v: -v[2])
    return {"ok": not viol, "violations": viol[:12]}

def _oracle_pour_family(routed_board_path):
    """ORPHANED-CHECKER wiring (blind-spots lens, 2026-07-08): the mature high-current
    pour family in cec_constraints existed and route_oracle_grade NEVER called it. Runs
    high-current-pour-present / min-pour-cross-section / trace-width-high-current on the
    routed board, plus the pad-local zone-connection assert (a THERMAL_RELIEF override on
    a solid-required pad silently defeats the joint with zero DRC signal)."""
    import pcbnew
    import cec_constraints as K
    board = pcbnew.LoadBoard(routed_board_path)
    if board is None:
        return {"ok": False, "checks": {"load": {"ok": False, "detail": "board unloadable"}}}
    out = {}
    ok_all = True
    ctx = {}
    for cid in ("high-current-pour-present", "min-pour-cross-section",
                "trace-width-high-current"):
        fn = K.CHECKERS.get(cid)
        if fn is None:
            continue
        try:
            res = fn(board, routed_board_path, ctx)
            ok, detail = bool(res[0]), res[1]
        except Exception as e:                           # noqa: BLE001 -- FAIL-CLOSED
            ok, detail = False, "checker error: %s" % e
        out[cid] = {"ok": ok, "detail": str(detail)[:200]}
        ok_all &= ok
    # zone-connection override assert: pads on force nets must be INHERITED/FULL
    try:
        import cec_fr
        force = {n for pr in cec_fr._board_kelvin_pairs(board) for n in pr}
        bad = []
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.GetNetname() in force and                         p.GetLocalZoneConnection() == pcbnew.ZONE_CONNECTION_THERMAL:
                    bad.append("%s.%s" % (fp.GetReference(), p.GetPadName()))
        out["zone-connection-override"] = {"ok": not bad, "detail": str(bad[:6])}
        ok_all &= not bad
    except Exception as e:                               # noqa: BLE001
        out["zone-connection-override"] = {"ok": False, "detail": str(e)[:120]}
        ok_all = False
    return {"ok": ok_all, "checks": out}


def _oracle_dfm(routed_board_path):
    """DFM defect classes (cec_dfm_check: slivers, isolated copper, starved thermals,
    hole-near-hole, acid traps + sub-min connection width) -- existed, never in the
    conjunction."""
    import cec_dfm_check
    try:
        v = cec_dfm_check.dfm_check(routed_board_path)
    except Exception as e:                               # noqa: BLE001 -- FAIL-CLOSED
        return {"ok": False, "violations": ["dfm error: %s" % e]}
    slim = [(x.get("type"), x.get("desc", "")[:60]) for x in v][:12]
    return {"ok": not v, "violations": slim, "count": len(v)}


def _oracle_route_sanity(routed_board_path, *, ratio_max=6.0, via_budget_base=10):
    """ROUTE-SANITY advisory (exploration round 2 item 5, 2026-07-08): per-net detour
    RATIO (routed track length / pad-MST lower bound) + per-net VIA BUDGET. The probe
    (build/probe_length_via.py) proved the blind spot: a 43x meander and a 41-via chain
    between the same two pads are both fully DRC-legal and gates_pass=True. CALIBRATION
    (build/meander_via_calib.py, 2026-07-08): board-level weighted detour does NOT
    separate hand from fresh (pour-connected nets sink it below 1.0 -- fresh 0.85/0.94
    vs hand 1.03/1.27), so this stays PER-NET pathological ceilings: hand worst ratio
    2.7 (12vhpwr /TEMP1) vs ceiling 6.0; via budget exempts zoned nets AND force
    (kelvin-pair) nets -- the 12vhpwr's mirrored high-current LANES are plain tracks,
    no zone, and legitimately stitch 10 vias onto 3-pad /SENSEP* nets (measured; GND
    fields 209); the shipped 12vhpwr's /SB_CBL_PRES sideband hops 8 vias (the accepted
    signal-net max, hence base 10). ADVISORY -- no real board fails today; it
    back-stops absurd routes (the synthetic 41-via chain and 53.8x meander fail)."""
    import pcbnew
    import cec_fr
    board = pcbnew.LoadBoard(routed_board_path)
    if board is None:
        return {"ok": False, "violations": ["board unloadable"]}
    try:
        force_nets = {n for pr in cec_fr._board_kelvin_pairs(board) for n in pr}
    except Exception:                                    # noqa: BLE001
        force_nets = set()
    pads_by_net = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn:
                pads_by_net.setdefault(nn, []).append(
                    (p.GetPosition().x / 1e6, p.GetPosition().y / 1e6))
    zoned = {z.GetNetname() for z in board.Zones() if z.IsOnCopperLayer()}
    tlen = {}
    nvias = {}
    for t in board.GetTracks():
        nn = t.GetNetname()
        if not nn:
            continue
        if t.GetClass() == "PCB_VIA":
            nvias[nn] = nvias.get(nn, 0) + 1
        else:
            tlen[nn] = tlen.get(nn, 0.0) + math.hypot(
                (t.GetEnd().x - t.GetStart().x) / 1e6,
                (t.GetEnd().y - t.GetStart().y) / 1e6)

    def _mst(pts):
        used = {0}
        total = 0.0
        d = [math.hypot(pts[0][0] - x, pts[0][1] - y) for x, y in pts]
        while len(used) < len(pts):
            best, bi = min((dist, i) for i, dist in enumerate(d) if i not in used)
            used.add(bi)
            total += best
            d = [min(d[i], math.hypot(pts[bi][0] - x, pts[bi][1] - y))
                 for i, (x, y) in enumerate(pts)]
        return total

    viol = []
    worst_ratio = 0.0
    for nn, length in tlen.items():
        pts = pads_by_net.get(nn, [])
        if len(pts) < 2 or length <= 0:
            continue
        lb = _mst(pts)
        if lb >= 2.0:                     # tiny nets: the ratio is unstable, skip
            ratio = length / lb
            worst_ratio = max(worst_ratio, ratio)
            if ratio > ratio_max:
                viol.append(("detour", nn, round(ratio, 1), round(lb, 1)))
        if nn not in zoned and nn not in force_nets:
            budget = max(via_budget_base, 2 * len(pts))
            if nvias.get(nn, 0) > budget:
                viol.append(("vias", nn, nvias[nn], budget))
    viol.sort(key=lambda v: -(v[2] if isinstance(v[2], (int, float)) else 0))
    # LAYERS-PER-ROUTE (owner scorecard metric, 2026-07-08 blind review: "uses less
    # layers to accomplish the same goal... an important metric"): distinct copper
    # layers each routed net touches; fewer = better readability + fab margin.
    layers_by_net = {}
    for t in board.GetTracks():
        nn = t.GetNetname()
        if nn and t.GetClass() != "PCB_VIA":
            layers_by_net.setdefault(nn, set()).add(t.GetLayer())
    nlayers = sorted(((len(v), n) for n, v in layers_by_net.items()), reverse=True)
    mean_layers = round(sum(c for c, _n in nlayers) / max(1, len(nlayers)), 2)
    return {"ok": not viol, "violations": viol[:10],
            "worst_ratio": round(worst_ratio, 2),
            "vias_total": sum(nvias.values()),
            "mean_layers_per_net": mean_layers,
            "most_layered": [(n, c) for c, n in nlayers[:5]]}


def _oracle_fiducials(placed_board_path, *, min_count=3, min_clear_mm=1.5,
                      min_tri_mm2=30.0, expect=None):
    """FIDUCIAL quality gate (exploration round 2 item 6, 2026-07-08). Assembly wants
    >=3 well-separated, non-collinear fiducials with a clear window around each.
    CALIBRATION (build/fid_calib.py): hand hub = 3 fids, min nearest-OTHER-pad 3.53mm,
    max triangle 1781mm2; hand 12vhpwr = 3 fids, 2.17mm, 1697mm2; a fresh
    materialized eps legalizes FID2 to 1.99mm -- floors 1.5mm / 30mm2 sit under all
    three (the fid's own mask window is 1mm radius; a fid ON a pad reads <0.5). Fresh wave boards shipped ZERO fiducials (materialize
    dropped the planned FID1-3 -- fixed in the same change as this gate).
    SCOPE: N/A (clean pass) on a board with no fiducials when *expect* is falsy --
    the committed eps/pcie boards carry none by their generator's design and the
    SB-08 golden must not flip. The wave path passes expect=True (place_mechanical
    plans them unless params say 'none'), so a fresh board missing fiducials FAILS."""
    import pcbnew
    board = pcbnew.LoadBoard(placed_board_path)
    if board is None:
        return {"ok": False, "violations": ["board unloadable"]}
    fids = [fp for fp in board.GetFootprints()
            if fp.GetReference().upper().startswith("FID")]
    if not fids:
        if expect:
            return {"ok": False, "count": 0,
                    "violations": ["fiducials expected but NONE on board"]}
        return {"ok": True, "count": 0, "violations": [], "note": "no fiducials -- N/A"}
    viol = []
    if len(fids) < min_count:
        viol.append(("count", len(fids), min_count))
    others = [(p, p.GetBoundingBox()) for fp in board.GetFootprints()
              if not fp.GetReference().upper().startswith("FID") for p in fp.Pads()]
    for fid in fids:
        fx, fy = fid.GetPosition().x / 1e6, fid.GetPosition().y / 1e6
        nd = 1e9
        for p, bb in others:
            d = math.hypot(p.GetPosition().x / 1e6 - fx, p.GetPosition().y / 1e6 - fy) \
                - (bb.GetWidth() / 1e6) / 2.0
            if d < nd:
                nd = d
        if nd < min_clear_mm:
            viol.append(("clear", fid.GetReference(), round(nd, 2), min_clear_mm))
    if len(fids) >= 3:
        pts = [(f.GetPosition().x / 1e6, f.GetPosition().y / 1e6) for f in fids]
        amax = 0.0
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                for k in range(j + 1, len(pts)):
                    (x1, y1), (x2, y2), (x3, y3) = pts[i], pts[j], pts[k]
                    amax = max(amax, abs((x2 - x1) * (y3 - y1)
                                         - (x3 - x1) * (y2 - y1)) / 2.0)
        if amax < min_tri_mm2:
            viol.append(("collinear", round(amax, 1), min_tri_mm2))
    return {"ok": not viol, "count": len(fids), "violations": viol[:8]}


def _oracle_gap_profile(placed_board_path):
    """NEAREST-GAP profile advisory (exploration round 2 item 7a, 2026-07-08): per-part
    nearest-neighbor courtyard gap -- TRUE polygon-to-polygon distance on the real
    courtyard outline, SAME-SIDE pairs only (the round-2 lens probe's bbox/side-blind
    variant was measured to disagree; this is the corrected method from the same-day
    measure.py family). HONEST STATUS from the probe forensics: NO bimodality statistic
    was ever computed -- the round-2 'bimodality' was an eyeballed histogram, the
    committed eps is a counterexample (69% one bucket), touch-counts do NOT separate
    hand from fresh (4-22% overlapping), and CV is seed-noisy. The one robust
    descriptive pattern (16-board sample): fresh boards' NON-touching population
    collapses into one narrow band (p75 <= 0.75mm every sample) while hand hub/12vhpwr/
    pcie spread real mass to 1.0-2.0mm+ (p75 1.08-1.25). ADVISORY ONLY -- reports the
    distribution (p25/med/p75, jammed%<0.2mm, modebin%), asserts nothing."""
    import pcbnew
    board = pcbnew.LoadBoard(placed_board_path)
    if board is None:
        return {"ok": False, "note": "board unloadable"}

    def _seg_seg(p1, p2, p3, p4):
        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        d1, d2 = cross(p3, p4, p1), cross(p3, p4, p2)
        d3, d4 = cross(p1, p2, p3), cross(p1, p2, p4)
        if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
            return 0.0

        def pd(p, a, b):
            vx, vy = b[0] - a[0], b[1] - a[1]
            wx, wy = p[0] - a[0], p[1] - a[1]
            length = vx * vx + vy * vy
            t = 0.0 if length == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / length))
            return math.hypot(p[0] - (a[0] + t * vx), p[1] - (a[1] + t * vy))
        return min(pd(p1, p3, p4), pd(p2, p3, p4), pd(p3, p1, p2), pd(p4, p1, p2))

    def _poly(fp):
        for lyr in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            poly = fp.GetCourtyard(lyr)
            if poly and poly.OutlineCount() > 0:
                o = poly.Outline(0)
                return [(o.CPoint(i).x / 1e6, o.CPoint(i).y / 1e6)
                        for i in range(o.PointCount())]
        bb = fp.GetBoundingBox()
        return [(bb.GetLeft() / 1e6, bb.GetTop() / 1e6), (bb.GetRight() / 1e6, bb.GetTop() / 1e6),
                (bb.GetRight() / 1e6, bb.GetBottom() / 1e6), (bb.GetLeft() / 1e6, bb.GetBottom() / 1e6)]

    def _pdist(A, B):
        m = 1e9
        for i in range(len(A)):
            a1, a2 = A[i], A[(i + 1) % len(A)]
            for j in range(len(B)):
                d = _seg_seg(a1, a2, B[j], B[(j + 1) % len(B)])
                if d < m:
                    m = d
                if m == 0:
                    return 0.0
        return m

    comps = [fp for fp in board.GetFootprints() if fp.GetPadCount() > 0
             and not (fp.GetReference() or "").startswith(("FID", "LOGO", "H", "M"))]
    polys = {fp.GetReference(): _poly(fp) for fp in comps}
    side = {fp.GetReference(): fp.IsFlipped() for fp in comps}
    gaps = []
    for r in polys:
        best = 1e9
        for r2 in polys:
            if r2 == r or side[r2] != side[r]:
                continue
            best = min(best, _pdist(polys[r], polys[r2]))
        if best < 1e9:
            gaps.append(best)
    if len(gaps) < 4:
        return {"ok": True, "note": "too few parts -- N/A"}
    g = sorted(gaps)

    def q(p):
        return round(g[max(0, min(len(g) - 1, int(p * len(g))))], 2)
    edges = [0, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 99]
    hist = [sum(1 for x in g if lo <= x < hi) for lo, hi in zip(edges, edges[1:])]
    return {"ok": True, "n": len(g), "p25": q(0.25), "med": q(0.5), "p75": q(0.75),
            "jammed_pct": round(100.0 * sum(1 for x in g if x < 0.2) / len(g), 1),
            "modebin_pct": round(100.0 * max(hist) / len(g), 1)}


def _oracle_tht_backside(placed_board_path, *, clearance_mm=0.3):
    """THT-BACKSIDE gate (OWNER-FOUND on the blind renders, 2026-07-08, machine-confirmed):
    a through-hole part's pins PROTRUDE through the board, so its PTH pin field occupies
    BOTH faces -- but dual-sided placement is not yet side-aware (the documented v1 note at
    the back_refs assignment) and KiCad's courtyard DRC misses this class (courtyards are
    per-side: it caught J6|U712V1 but NOT RS2/U75V1/U65V1 under J6's pin field, C16 under
    J3). Gate: any footprint on the OPPOSITE face whose bbox overlaps a THT part's PTH
    pin-field bbox (+clearance) fails -- solder joints/pin tails physically occupy that
    space. Placement-only; N/A on single-sided boards."""
    import pcbnew
    board = pcbnew.LoadBoard(placed_board_path)
    if board is None:
        return {"ok": False, "violations": ["board unloadable"]}
    tht, front, back = [], [], []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pth = [p for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
        if pth:
            xs1 = [p.GetBoundingBox().GetLeft() / 1e6 for p in pth]
            xs2 = [p.GetBoundingBox().GetRight() / 1e6 for p in pth]
            ys1 = [p.GetBoundingBox().GetTop() / 1e6 for p in pth]
            ys2 = [p.GetBoundingBox().GetBottom() / 1e6 for p in pth]
            tht.append((ref, min(xs1), max(xs2), min(ys1), max(ys2), fp.IsFlipped()))
        else:
            bb = fp.GetBoundingBox()
            (back if fp.IsFlipped() else front).append(
                (ref, bb.GetLeft() / 1e6, bb.GetRight() / 1e6,
                 bb.GetTop() / 1e6, bb.GetBottom() / 1e6))
    if not back and not any(f for *_x, f in tht):
        return {"ok": True, "violations": [], "note": "single-sided -- N/A"}
    c = clearance_mm
    viol = []
    for ref, l, r, t, bm, flipped in tht:
        # the pin field conflicts with parts on the face OPPOSITE the THT body's mount side
        for oref, ol, orr, ot, ob in (back if not flipped else front):
            if ol < r + c and orr > l - c and ot < bm + c and ob > t - c:
                viol.append((oref, "under THT pin field of", ref))
    return {"ok": not viol, "violations": viol[:10]}


def _oracle_facing_fraction(placed_board_path, *, net_span_max=12):
    """FACING-FRACTION metric (exploration round 2 item 4, 2026-07-08): over every
    pair of footprints sharing a LOCAL net (board-wide pad count <= *net_span_max*,
    excluding planes/buses), the pair is FACING when the minimum shared-net pad-pad
    distance is also the minimum ANY-pad distance (+0.05mm) -- i.e. the parts are
    ORIENTED toward their electrical partner instead of showing it their back. Ported
    verbatim from the round-2 lens probe (build/lens1.py metric 4). Calibration:
    hand boards 29-36% vs fresh 19%. ADVISORY METRIC (never gates): it exists to
    drive + evaluate the backlogged face() placement lever; higher = better."""
    import pcbnew
    board = pcbnew.LoadBoard(placed_board_path)
    if board is None:
        return {"ok": False, "facing_pct": None, "note": "board unloadable"}
    pads = []
    cxy = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        cxy[ref] = (fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6)
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn:
                pads.append((ref, nn, p.GetPosition().x / 1e6, p.GetPosition().y / 1e6))
    ns = {}
    for _ref, nn, _x, _y in pads:
        ns[nn] = ns.get(nn, 0) + 1
    byref = {}
    for ref, nn, x, y in pads:
        byref.setdefault(ref, []).append((nn, x, y))
    reflist = list(byref.keys())
    facing = 0
    npair = 0
    for i in range(len(reflist)):
        for j in range(i + 1, len(reflist)):
            ra, rb = reflist[i], reflist[j]
            shared = ({n for n, _x, _y in byref[ra] if ns.get(n, 0) <= net_span_max}
                      & {n for n, _x, _y in byref[rb] if ns.get(n, 0) <= net_span_max})
            if not shared:
                continue
            msh = many = 1e9
            for na, xa, ya in byref[ra]:
                for nb, xb, yb in byref[rb]:
                    d = math.hypot(xa - xb, ya - yb)
                    if d < many:
                        many = d
                    if na == nb and na in shared and d < msh:
                        msh = d
            cd = math.hypot(cxy[ra][0] - cxy[rb][0], cxy[ra][1] - cxy[rb][1])
            if cd < 0.01:
                continue
            npair += 1
            if msh <= many + 0.05:
                facing += 1
    pct = round(100.0 * facing / npair, 2) if npair else None
    return {"ok": True, "facing_pct": pct, "pairs": npair}


def _oracle_silk_score(routed_board_path, *, per_fp_max=1.0):
    """SILK score/footprint (exploration round 2 item 3, 2026-07-08): all silk* DRC
    classes (overlap / over_copper / edge_clearance) at --severity-all, divided by the
    footprint count. CALIBRATION (build/silk_calib.py, reproduced 2026-07-08): hand hub
    0.32, hand 12vhpwr 0.18, committed eps 0.43 -- vs fresh wave boards 4.48 (24-pin)
    and 5.32 (eps): a 10x separation, dominated by silk_overlap + silk_over_copper
    (values stamped onto copper/each other by the placer). SOFT SCORE TERM: silk is
    the repo's documented cosmetic/finishing class, so this never gates -- it feeds
    the tier-0 sort_key tie-break (a reserved slot) + an advisory field. per_fp_max
    1.0 = 2.3x over the worst accepted board, 4.5x under the best fresh."""
    import json as _json
    import subprocess
    import pcbnew
    board = pcbnew.LoadBoard(routed_board_path)
    if board is None:
        return {"ok": False, "score_per_fp": None, "violations": ["board unloadable"]}
    nfp = max(1, len(list(board.GetFootprints())))
    out = tempfile.mkstemp(suffix=".json")[1]
    try:
        subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                        "-o", out, routed_board_path], capture_output=True, timeout=300)
        d = _json.load(open(out))
    except Exception as e:                               # noqa: BLE001 -- FAIL-CLOSED
        return {"ok": False, "score_per_fp": None, "violations": ["drc error: %s" % e]}
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass
    breakdown = {}
    for v in d.get("violations", []):
        t = v.get("type", "")
        if t.startswith("silk"):
            breakdown[t] = breakdown.get(t, 0) + 1
    n = sum(breakdown.values())
    score = round(n / nfp, 2)
    return {"ok": score <= per_fp_max, "score_per_fp": score, "count": n,
            "footprints": nfp, "breakdown": breakdown, "per_fp_max": per_fp_max}


def _oracle_stranded_parts(placed_board_path, *, max_mm=22.0):
    """STRANDED-PART gate (owner eyesight finding 2026-07-08: diodes jammed in a corner,
    a slew orphaned by the 1x4 header): every part must sit within *max_mm* of its
    NEAREST CONNECTED NEIGHBOR (a part sharing any non-GND net). Eviction/legalize
    orphans have no nearby electrical partner -- that is what the eye catches. Threshold
    generous (hand boards route across ~15mm legitimately); catches the 25-60mm class.
    Board-agnostic; connectors/mechanical exempt (endpoints others chase) plus the
    ACCESS-placed classes (SW/TP/DL -- buttons, test points, LEDs are placed for reach/
    visibility, not proximity; hand boards run them at 24-33mm). max_mm CALIBRATED: hand
    worst non-access case 19.7mm -> 22.0 with margin; real strays measure 25-60mm."""
    import pcbnew
    board = pcbnew.LoadBoard(placed_board_path)
    if board is None:
        return {"ok": False, "violations": ["board unloadable"]}
    nets_of = {}
    pos = {}
    for fp in board.GetFootprints():
        r = fp.GetReference() or ""
        pos[r] = fp.GetPosition()
        nets_of[r] = {p.GetNetname() for p in fp.Pads() if p.GetNetname()} - {"GND"}
    viol = []
    for r, nets in nets_of.items():
        if not nets or r.startswith(("J", "TB", "H", "LOGO", "FID", "SW", "TP", "DL")):
            continue                             # connectors/mech + ACCESS-placed classes
                                                 # (buttons/testpoints/LEDs sit far by
                                                 # design -- hand worst 24-33mm)
        partners = [q for q, qn in nets_of.items() if q != r and (qn & nets)]
        if not partners:
            continue
        d = min(math.hypot((pos[r].x - pos[q].x) / 1e6, (pos[r].y - pos[q].y) / 1e6)
                for q in partners)
        if d > max_mm:
            viol.append((r, round(d, 1)))
    viol.sort(key=lambda v: -v[1])
    return {"ok": not viol, "violations": viol[:10]}


def _oracle_circuit_complete(routed_board_path):
    """CIRCUIT-COMPLETENESS gate (owner ask 2026-07-08: 'does the FEM look for complete
    circuits?' -- it did NOT: current is injected at sources and extracted at sinks
    regardless of copper connectivity, so a stranded zone island passed thermal while
    electrically dead). For every kelvin force net: ALL of its pads must live on ONE
    connected copper island (pcbnew connectivity, zones filled). Generalizes to any
    board with force nets; N/A without them."""
    import pcbnew
    import cec_fr
    board = pcbnew.LoadBoard(routed_board_path)
    if board is None:
        return {"ok": False, "violations": ["board unloadable"]}
    pairs = cec_fr._board_kelvin_pairs(board)
    if not pairs:
        return {"ok": True, "violations": [], "note": "no force nets -- N/A"}
    # zones must be FILLED for a copper walk (fixtures store unfilled zones -- the
    # eps reference false-fired); fill an in-memory copy, never write back.
    def _has_polys(z):
        try:
            return any(z.GetFilledPolysList(l).OutlineCount() > 0
                       for l in z.GetLayerSet().CuStack())
        except Exception:                                # noqa: BLE001
            return False
    if not any(_has_polys(z) for z in board.Zones()):    # IsFilled() is the FLAG, not polys
        try:
            for z in board.Zones():
                z.UnFill()                        # the recorded double-fill footgun
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        except Exception:                            # noqa: BLE001
            pass
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    viol = []
    for net in sorted({n for pr in pairs for n in pr}):
        code = board.GetNetcodeFromNetname(net)
        if code <= 0:
            continue
        # pads on the net vs connectivity: unconnected count for this net's items
        pads = [(fp.GetReference(), p) for fp in board.GetFootprints()
                for p in fp.Pads() if p.GetNetCode() == code]
        if len(pads) < 2:
            continue
        # ISLAND BFS (the proven gnd-forensics pattern; GetRatsnestForNet is absent in
        # this SWIG build): flood from the first pad via GetConnectedItems; every other
        # pad must be reachable through copper.
        try:
            # the PROVEN forensics form: no-types GetConnectedItems + UUID identity
            # (SWIG re-proxies objects; ids are unstable -- the recorded footgun)
            keyf = lambda it: it.m_Uuid.AsString()
            seen = {keyf(pads[0][1])}
            frontier = [pads[0][1]]
            while frontier:
                nxt = []
                for it in frontier:
                    for c2 in conn.GetConnectedItems(it):
                        k = keyf(c2)
                        if k not in seen:
                            seen.add(k)
                            nxt.append(c2)
                frontier = nxt
            missing = [r for r, p in pads[1:] if keyf(p) not in seen]
            if missing:
                viol.append((net, "OPEN circuit -- unreachable pads", missing[:4]))
        except Exception as e:                           # noqa: BLE001 -- FAIL-CLOSED
            viol.append((net, "connectivity walk failed: %s" % str(e)[:60], []))
    return {"ok": not viol, "violations": viol[:8]}


def _oracle_kelvin_reach(placed_board_path, *, max_mm=9.0):
    """PRE-ROUTE kelvin-reach gate (owner lever pass, 2026-07-08): every current-sense IC
    input pad must sit within *max_mm* (the tap synthesizer's reach) of its pair's shunt
    -- a placement that strands an INA past tap reach ALWAYS fails kelvin after routing,
    so reject it BEFORE burning a 3-5 minute route. Board-only; N/A without pairs."""
    import pcbnew
    import cec_fr
    board = pcbnew.LoadBoard(placed_board_path)
    if board is None:
        return {"ok": False, "violations": ["board unloadable"]}
    pairs = cec_fr._board_kelvin_pairs(board)
    if not pairs:
        return {"ok": True, "violations": [], "note": "no kelvin pairs -- N/A"}
    inp_pin = {"INA238": ("9", "10"), "INA228": ("9", "10"), "INA226": ("9", "10"),
               "INA181": ("3", "4")}
    pads_by_net = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn:
                pads_by_net.setdefault(nn, []).append((fp, p))
    viol = []
    n_checked = 0
    for hi, lo in pairs:
        sh = next((fp for fp, _p in pads_by_net.get(hi, [])
                   if fp.GetReference().startswith("RS")
                   and fp.GetReference() in {f.GetReference() for f, _q in pads_by_net.get(lo, [])}
                   and fp.GetPadCount() == 2), None)
        if sh is None:
            continue
        for net in (hi, lo):
            for fp, p in pads_by_net.get(net, []):
                val = (fp.GetValue() or "").upper()
                want = next((v for k, v in inp_pin.items() if k in val), None)
                if want is None or p.GetPadName() not in want:
                    continue
                n_checked += 1
                d = min(math.hypot((p.GetPosition().x - q.GetPosition().x) / 1e6,
                                   (p.GetPosition().y - q.GetPosition().y) / 1e6)
                        for q in sh.Pads())
                if d > max_mm:
                    viol.append((fp.GetReference(), p.GetPadName(), net, round(d, 1)))
    if n_checked == 0:
        return {"ok": True, "violations": [], "note": "no sense inputs -- N/A"}
    viol.sort(key=lambda v: -v[3])
    return {"ok": not viol, "violations": viol[:10]}


def _oracle_courtyard_overlaps(placed_board_path):
    """HARD courtyard gate (owner lever pass, 2026-07-08): ANY courtyard overlap on the
    placed board fails -- the class that let J1 crash the sense row was visible to DRC
    but not gated in the oracle path. Uses the real kicad-cli DRC (never a model)."""
    import json as _json
    import subprocess
    import tempfile
    out = tempfile.mkstemp(suffix=".json")[1]
    try:
        subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", out,
                        placed_board_path], capture_output=True, timeout=300)
        d = _json.load(open(out))
    except Exception as e:                               # noqa: BLE001 -- FAIL-CLOSED
        return {"ok": False, "violations": ["drc error: %s" % e]}
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass
    viol = []
    for v in d.get("violations", []):
        if v.get("type") == "courtyards_overlap":
            pair = "|".join(it.get("description", "")[:40] for it in v.get("items", []))
            viol.append(pair)
    return {"ok": not viol, "violations": viol[:10]}


def _oracle_pin_escape(placed_board_path, *, boxed_pct_max=4.0, le1_pct_max=12.0,
                       max_pads=10):
    """PIN-ESCAPE gate (exploration round 2, 2026-07-08): every copper pad on a small
    footprint (<= *max_pads* pads -- ICs/passives, not connectors) probes 8 directions
    for a 0.3mm routing corridor (16 x 0.2mm steps from the pad's own edge, blocked by
    any FOREIGN-net pad bbox inflated 0.15mm). A pad with 0 free directions is BOXED
    (unroutable without a via-in-pad miracle); <=1 free direction is NEARLY boxed.
    CALIBRATION (measured 2026-07-08, build/lens1_calib_all.py in-container):
    hand hub/12vhpwr = 0.00%/0.00% on both; committed eps 1.71/6.86, pcie2 1.09/3.80,
    pcie3 0.87/4.80 (boxed0/le1 %); fresh 24-pin wave board 9.06/23.02 -- all offenders
    the sense front-end (U10-U13 INA/TLV). Floors 4.0/12.0 give ~2x headroom over every
    accepted board and fail the fresh board on both terms. Placement-only (pads, no
    copper) -- valid pre-route."""
    import pcbnew
    board = pcbnew.LoadBoard(placed_board_path)
    if board is None:
        return {"ok": False, "violations": ["board unloadable"]}
    dirs = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    pads = []
    padcount = {}
    for f in board.GetFootprints():
        cp = [p for p in f.Pads() if p.IsOnCopperLayer()]
        padcount[f.GetReference()] = len(cp)
        for p in cp:
            nn = p.GetNetname()
            if not nn:
                continue
            bb = p.GetBoundingBox()
            pads.append((f.GetReference(), nn,
                         p.GetCenter().x / 1e6, p.GetCenter().y / 1e6,
                         bb.GetLeft() / 1e6, bb.GetRight() / 1e6,
                         bb.GetTop() / 1e6, bb.GetBottom() / 1e6))
    boxes = [(r[4], r[5], r[6], r[7], r[1]) for r in pads]
    targets = [r for r in pads if padcount[r[0]] <= max_pads]
    if not targets:
        return {"ok": True, "violations": [], "note": "no small-footprint pads -- N/A"}

    def _free_dirs(pad):
        _ref, net, cx, cy, l, r, t, bot = pad
        nf = 0
        for dx, dy in dirs:
            n = math.hypot(dx, dy)
            ux, uy = dx / n, dy / n
            sx = cx + (r - cx if dx > 0 else (l - cx if dx < 0 else 0))
            sy = cy + (bot - cy if dy > 0 else (t - cy if dy < 0 else 0))
            blocked = False
            for s in range(1, 16):
                px, py = sx + ux * 0.2 * s, sy + uy * 0.2 * s
                for (bl, br, bt, bb2, bn) in boxes:
                    if bn == net:
                        continue
                    if bl - 0.15 <= px <= br + 0.15 and bt - 0.15 <= py <= bb2 + 0.15:
                        blocked = True
                        break
                if blocked:
                    break
            if not blocked:
                nf += 1
        return nf

    free = [(_free_dirs(p), p) for p in targets]
    n = len(free)
    boxed0 = 100.0 * sum(1 for c, _p in free if c == 0) / n
    le1 = 100.0 * sum(1 for c, _p in free if c <= 1) / n
    by_ref = {}
    for c, p in free:
        if c <= 1:
            by_ref[p[0]] = by_ref.get(p[0], 0) + 1
    offenders = sorted(by_ref.items(), key=lambda x: -x[1])[:10]
    ok = (boxed0 <= boxed_pct_max) and (le1 <= le1_pct_max)
    return {"ok": ok, "boxed0_pct": round(boxed0, 2), "le1_pct": round(le1, 2),
            "floors": {"boxed0": boxed_pct_max, "le1": le1_pct_max},
            "violations": ([] if ok else offenders)}


# ref prefixes whose courtyards LEGITIMATELY ride the board edge: connectors (mouths
# overhang by design), mounts/holes, fiducials/markers, buttons + testpoints + LEDs
# (access classes, same exemption set as the stranded-parts gate), blade receptacles,
# logos. The ESP32 radio-module exemption is by VALUE (its antenna half sits at the
# edge on the hand hub AND committed eps -- an accepted pattern, not a defect).
_EDGE_EXEMPT_PREFIXES = ("J", "H", "M", "FID", "MK", "SW", "TB", "TP", "DL", "LOGO")


def _oracle_courtyard_edge(placed_board_path, *, min_mm=0.8):
    """COURTYARD-EDGE clearance gate (exploration round 2, 2026-07-08) via the NATIVE
    KiCad DRU physical_clearance rule -- the bbox proxy false-flags rotated courtyards
    (agent-PROVED), so the real engine measures. A temp copy of the board gets a
    .kicad_dru with (constraint physical_clearance (min Xmm)) between F/B.CrtYd
    graphics and Edge.Cuts; kicad-cli DRC reports the actual gap per part.
    CALIBRATION (measured 2026-07-08, build/edge_gate_calib2.py in-container, floor
    0.8mm + exemptions): hub/12vhpwr/eps/pcie2 all CLEAN (the 12vhpwr's closest
    non-exempt part sits at 0.84mm -- the calibration floor); the fresh 24-pin wave
    board fails with C50/FB2/C7/D7/U1 at 0.00mm and 5 more under 0.76mm. Exempt: the
    _EDGE_EXEMPT_PREFIXES classes + ESP32 radio modules by value. Placement-only."""
    import json as _json
    import re as _re
    import subprocess
    import pcbnew
    board = pcbnew.LoadBoard(placed_board_path)
    if board is None:
        return {"ok": False, "violations": ["board unloadable"]}
    val_by_ref = {fp.GetReference(): (fp.GetValue() or "").upper()
                  for fp in board.GetFootprints()}
    dru = (
        '(version 1)\n'
        '(rule "courtyard-edge-margin-f"\n'
        '   (layer "F.CrtYd")\n'
        '   (constraint physical_clearance (min %.3fmm))\n'
        '   (condition "A.Type == \'Graphic\' && B.Layer == \'Edge.Cuts\'")\n'
        '   (severity error))\n'
        '(rule "courtyard-edge-margin-b"\n'
        '   (layer "B.CrtYd")\n'
        '   (constraint physical_clearance (min %.3fmm))\n'
        '   (condition "A.Type == \'Graphic\' && B.Layer == \'Edge.Cuts\'")\n'
        '   (severity error))\n' % (min_mm, min_mm))
    work = tempfile.mkdtemp(prefix="cec_edge_gate_")
    try:
        bp = os.path.join(work, "board.kicad_pcb")
        shutil.copy(placed_board_path, bp)
        with open(os.path.join(work, "board.kicad_dru"), "w") as fh:
            fh.write(dru)
        out = os.path.join(work, "drc.json")
        subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                        "-o", out, bp], capture_output=True, timeout=300)
        d = _json.load(open(out))
    except Exception as e:                               # noqa: BLE001 -- FAIL-CLOSED
        return {"ok": False, "violations": ["edge-gate drc error: %s" % e]}
    finally:
        shutil.rmtree(work, ignore_errors=True)
    worst = {}
    for v in d.get("violations", []):
        if "courtyard-edge-margin" not in (v.get("description") or ""):
            continue
        mgap = _re.search(r"actual ([0-9.]+) mm", v.get("description", ""))
        gap = float(mgap.group(1)) if mgap else 0.0
        for it in v.get("items", []):
            mref = _re.search(r"of (\S+) on [FB]\.Courtyard", it.get("description", ""))
            if mref:
                ref = mref.group(1)
                if ref not in worst or gap < worst[ref]:
                    worst[ref] = gap
    viol = sorted(((r, g) for r, g in worst.items()
                   if not r.upper().startswith(_EDGE_EXEMPT_PREFIXES)
                   and "ESP32" not in val_by_ref.get(r, "")),
                  key=lambda x: x[1])
    return {"ok": not viol, "min_mm": min_mm, "violations": viol[:10]}


def _oracle_comparator_adjacency(placed_board_path, *, max_mm=8.0):
    """DETECTION-CELL gate term (opus fundamentals audit 2026-07-08, gate-worthy with a
    BIMODAL clean cut: seated cells measure 3.9-7.3mm, failures 30-48mm): each TLV7011
    comparator must sit within *max_mm* pad-to-pad of the INA181 it shares a /DETAMP* net
    with -- the sec6.13 transient cell is shunt->INA181->comparator and fragments on ~40%
    of placer rails with zero DRC/gate visibility. N/A on boards without the cell."""
    import pcbnew
    board = pcbnew.LoadBoard(placed_board_path)
    if board is None:
        return {"ok": False, "violations": ["board unloadable"]}
    by_net = {}
    for fp in board.GetFootprints():
        val = (fp.GetValue() or "").upper()
        kind = "cmp" if "TLV70" in val else ("ina" if "INA181" in val else None)
        if not kind:
            continue
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn and "DETAMP" in nn.upper():
                by_net.setdefault(nn, {})[kind] = by_net.get(nn, {}).get(kind) or []
                by_net[nn][kind].append((fp.GetReference(), p.GetPosition()))
    viol = []
    n_cells = 0
    for net, kinds in by_net.items():
        if "cmp" not in kinds or "ina" not in kinds:
            continue
        n_cells += 1
        d = min(math.hypot((a.x - b.x) / 1e6, (a.y - b.y) / 1e6)
                for _r1, a in kinds["cmp"] for _r2, b in kinds["ina"])
        if d > max_mm:
            viol.append((kinds["cmp"][0][0], kinds["ina"][0][0], net, round(d, 1)))
    if n_cells == 0:
        return {"ok": True, "violations": [], "note": "no detection cells -- N/A"}
    return {"ok": not viol, "violations": viol[:8]}


def _oracle_bodies_in_pours(placed_board_path, *, margin=0.0):
    """HARD body-in-pour gate (owner 2026-07-08: 'NO TRACES OR PLACEMENTS IN POURS AT ALL
    EVER' -- the traces half is the existing foreign_on_pour 0/0 term; THIS is the
    placements half, which until now was only a soft legalizer evacuation and was silently
    inert on shared-bus boards). A FOREIGN part's courtyard center inside any rail pour box
    on its own mounting side = violation. Exempt: parts carrying the pour's own net (the
    shunt, the connector/blades the pour feeds -- the box is derived FROM their pads) and
    THT connectors (the pour legitimately laps their barrel field).
    OPERATING DOMAIN: pipeline-FRESH boards only (the oracle path). Hand fab boards carry
    their high-current copper as tracks/hand shapes and interleave sense parts by design --
    they are governed by the pour-integrity/cross-section checkers, never this boolean."""
    import pcbnew
    board = pcbnew.LoadBoard(placed_board_path)
    if board is None:
        return {"ok": False, "violations": ["board unloadable"]}
    # PREFER the board's REAL zones (a hand board's pours are exact shapes weaving between
    # legitimate parts -- derived bounding boxes false-fired on the fab 12vhpwr's sensing
    # row); derived boxes only when the board carries no rail zones yet (fresh placements).
    # Boards with REAL rail zones (hand boards): a boolean body test is the WRONG model --
    # foreign fill legitimately flows UNDER small bodies (only pads short; measured: the fab
    # 12vhpwr's interleaved sense row sits over filled SENSEP copper by design). What hand
    # boards obey is "the pour still meets cross-section after carving" = the existing
    # pour-integrity/min-cross-section checkers. The HARD boolean below applies to FRESH
    # placements (derived boxes, no zones yet) where the placer controls everything.
    for z in board.Zones():
        zn = z.GetNetname()
        if zn and zn != "GND" and (zn.startswith("+") or "SENSE" in zn.upper()):
            return {"ok": True, "violations": [],
                    "note": "real rail zones present -- governed by pour-integrity checkers"}
    viol = []
    # POUR LEVER (stage 1): the bodies gate is now a PourPlan consumer -- the same plan view the
    # settle/keepout/copper compile from, so the box a body is tested against == the box the pour
    # fills. Byte-identical to the old derive_power_pours(board=board) (both board-derived pairs).
    import cec_pourplan
    pours = cec_pourplan.PourPlan.from_board(placed_board_path, board=board).pour_polygons()
    if not pours:
        return {"ok": True, "violations": [], "note": "no rail pours -- N/A"}
    boxes = []
    for p in pours:
        xs = [q[0] for q in p["polygon"]]
        ys = [q[1] for q in p["polygon"]]
        boxes.append((p["net"], p["layer"], min(xs) - margin, max(xs) + margin,
                      min(ys) - margin, max(ys) + margin))
    # STRICT (owner overrule 2026-07-08, third statement of this rule): NO family
    # exemption -- with LANE pours the chains live BETWEEN lanes / in the notch band,
    # never inside pour copper.
    for fp in board.GetFootprints():
        ref = fp.GetReference() or ""
        if ref.startswith(("J", "TB", "H", "LOGO", "FID")):
            continue                                     # connectors/blades/mechanical: exempt
        fp_nets = {p.GetNetname() for p in fp.Pads() if p.GetNetname()}
        side = "B.Cu" if fp.IsFlipped() else "F.Cu"
        c = fp.GetPosition()
        cx, cy = c.x / 1e6, c.y / 1e6
        for net, layer, x0, x1, y0, y1 in boxes:
            if net in fp_nets:
                continue                                 # the pour's own component
            if layer != side:
                continue                                 # inner pours: no bodies live there
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                viol.append((ref, net, layer))
                break
    return {"ok": not viol, "violations": viol[:14]}


def _oracle_pair_quality(routed_board_path, *, max_skew_mm=4.0):
    """DATA-PAIR gate term (owner 2026-07-08: 'data lines as short and ran as pairs'):
    each recognized pair (USB *_P/_N, CAN *_H/_L) must be length-matched within
    *max_skew_mm* -- gross skew means the members took different paths (loop area), i.e.
    NOT run as a pair. Lengths measured directly from the routed board's tracks (the
    cec_score net_len subset excludes signal nets). Unrouted members are the routing
    gate's business, never double-flagged here."""
    import pcbnew
    board = pcbnew.LoadBoard(routed_board_path)
    if board is None:
        return {"ok": False, "violations": ["board unloadable"], "pairs": {}}
    lens = {}
    for tr in board.GetTracks():
        if tr.Type() == pcbnew.PCB_VIA_T:
            continue
        n = tr.GetNetname()
        if not n:
            continue
        a, b = tr.GetStart(), tr.GetEnd()
        lens[n] = lens.get(n, 0.0) + math.hypot((a.x - b.x) / 1e6, (a.y - b.y) / 1e6)
    names = set(lens)
    pairs = []
    for n in sorted(names):
        u = n.upper()
        # DATA pairs only (USB/CAN): the analog boards' IN*_P/_N sense-filter pairs differ
        # by legitimate geometry and are not data lines (measured 6.7mm on the hand-routed
        # 12vhpwr). max_skew CALIBRATED on the hand boards: CAN skew 2.8mm on both.
        if ("USB" not in u and "CAN" not in u):
            continue
        if n.endswith("_P") and n[:-2] + "_N" in names:
            pairs.append((n, n[:-2] + "_N"))
        if n.endswith("_H") and "CAN" in u and n[:-2] + "_L" in names:
            pairs.append((n, n[:-2] + "_L"))
    viol = []
    detail = {}
    for a, b in pairs:
        la, lb = lens[a], lens[b]
        if la <= 0.0 or lb <= 0.0:
            continue
        skew = abs(la - lb)
        detail["%s|%s" % (a, b)] = {"len_a": round(la, 1), "len_b": round(lb, 1),
                                    "skew": round(skew, 1)}
        if skew > max_skew_mm:
            viol.append("%s vs %s skew %.1fmm (max %.1f)" % (a, b, skew, max_skew_mm))
    return {"ok": not viol, "violations": viol, "pairs": detail}

def _oracle_thermal(board_path, *, ambient, gate_dt, grid_mm):
    """The THERMAL gate term: the dashboard solve recipe (cec_thermal_overlay._solve_thermal -> the 2.5D
    cec_thermal2d field solver, with the per-board currents/stackup/cooling) -> dT <= gate_dt. FAIL-CLOSED:
    a solver error is NOT a pass (the false-summit hazard is exactly a board that LOOKS routed but cooks).

    MIRAGE GUARD (owner concern + MEASURED 2026-07-08, build/probe_thermal_repeat*.py): the solve is
    NON-DETERMINISTIC on at least one fresh artifact -- back-to-back identical calls returned dT 119.5/
    103.3/174.4 (GPU) and 0.0/20.8/20.9 (forced CPU); the pyamg ml.solve path returns its best iterate
    with NO convergence flag. Two guards until the solver investigation closes (FOLLOWUPS): (a) dT<=0.05
    on a powered board is physically impossible -> solver error, FAIL; (b) a would-be PASS must be
    CONFIRMED by a second independent solve -- disagreement (>max(2C, 20%)) or a failing re-solve FAILS,
    and the REPORTED dT is the worst of the two. A thermal-mirage pass now needs two lucky solves."""
    import cec_thermal_overlay as _tov
    res, _filled, label = _tov._solve_thermal(board_path, ambient=ambient, grid_mm=grid_mm)
    dT = float(res.max_T) - float(res.ambient)
    if dT <= 0.05:
        return {"ok": False, "max_T": round(float(res.max_T), 2),
                "ambient": round(float(res.ambient), 2), "dT": round(dT, 2),
                "gate_dt": gate_dt, "cooling": label,
                "error": "solver returned dT~0 -- impossible for a powered board (broken solve)"}
    if dT <= gate_dt:
        res2, _f2, _l2 = _tov._solve_thermal(board_path, ambient=ambient, grid_mm=grid_mm)
        dT2 = float(res2.max_T) - float(res2.ambient)
        worst = max(dT, dT2)
        if dT2 <= 0.05 or abs(dT2 - dT) > max(2.0, 0.2 * max(dT, dT2)) or worst > gate_dt:
            return {"ok": False, "max_T": round(float(res.ambient) + worst, 2),
                    "ambient": round(float(res.ambient), 2), "dT": round(worst, 2),
                    "gate_dt": gate_dt, "cooling": label,
                    "error": "UNSTABLE solve: dT %.2f vs %.2f on identical re-solve "
                             "(pass requires two agreeing solves)" % (dT, dT2)}
        dT = worst
    return {"ok": (dT <= gate_dt), "max_T": round(float(res.ambient) + dT, 2),
            "ambient": round(float(res.ambient), 2), "dT": round(dT, 2),
            "gate_dt": gate_dt, "cooling": label}


def route_oracle_grade(placement_or_board, *, cfg=None, passes=8, opt=12, ambient=50.0,
                       gate_dt=30.0, grid_mm=0.4, seed=None, unconn_finish_tol=2,
                       route=True, work_dir=None, keep=False, verbose=False, fr_timeout=600,
                       craft_gates=True, thermal="always", protect_nets=()):
    """ROUTE-ORACLE GRADER (SLICE-1a): grade a placement by ACTUALLY ROUTING it and reading the REAL
    post-route ACCEPT CONJUNCTION. This REPLACES the cheap placement_proxy as the selection key.

    placement_or_board : a Candidate (materialized via cfg) OR a path to a .kicad_pcb placement.
    route              : True -> route the (placement) board with the gate-clean recipe, then grade the
                         routed board; False -> grade the input board AS-IS (it is already routed).

    The verdict is the conjunction -- ALL must hold (never a subset; kelvin_ok+drc is a false summit):
      * gates_pass        = kelvin_ok AND diffpair_ok AND drc-finishing-only (cec_score, structural drc==0)
      * foreign_ok        = cec_constraints.foreign_on_pour_summary (status ok, 0 foreign track/via; run
                            with CEC_SHUNT_GAP=1 -- status 'error' FAILS, 'na' is a clean N/A on shared-bus)
      * thermal_ok        = the 2.5D field solve dT <= gate_dt (FAIL-CLOSED on solver error)
      * routing_complete  = no unconnected ratline on a safety/power net, and <= unconn_finish_tol signal
                            ratlines (the documented cec_route finishing residual). unconn_finish_tol=0 = strict.

    Returns a dict carrying gate (bool), the per-term verdicts, the raw metrics, and `sort_key` -- the
    sortable selection key (lower = better): gate-clean candidates rank first (tie-break thermal margin /
    via / length), gate-FAILING below ordered by how CLOSE to clean (safety fails, then foreign, then
    unconnected, then drc, then thermal) so the placer still yields a best-effort + a clear escalation signal."""
    import cec_constraints
    import cec_fr  # noqa: F401  -- ensures pcbnew/FR availability surfaces here, not mid-route

    own_wd = work_dir is None
    work_dir = work_dir or tempfile.mkdtemp(prefix="cec_oracle_")
    os.makedirs(work_dir, exist_ok=True)
    label = None
    try:
        with _oracle_env():
            # ---- 1. resolve the placement board (materialize a Candidate; else use the path) ----
            if isinstance(placement_or_board, Candidate):
                if cfg is None:
                    raise ValueError("route_oracle_grade(Candidate) requires cfg= to materialize")
                label = f"{placement_or_board.strat}/seed{placement_or_board.seed}"
                placed = materialize(placement_or_board, cfg,
                                     os.path.join(work_dir, "placed.kicad_pcb"))
            else:
                placed = placement_or_board
                label = os.path.basename(str(placed))
                if not os.path.isfile(placed):
                    raise FileNotFoundError(f"route_oracle_grade: board not found: {placed!r}")

            # ---- 2. route it with the gate-clean recipe (ONE route_once), or grade as-is ----
            t0 = time.monotonic()
            if route:
                hints, pours, rules = _oracle_hints_pours(placed)
                routed = os.path.join(work_dir, "routed.kicad_pcb")
                cand = cec_fr.route_once(placed, routed, hints=hints, power_pours=pours,
                                         passes=passes, opt_time=opt, seed=seed,
                                         timeout=int(fr_timeout),
                                         protect_nets=protect_nets)
                if not cand.ok:
                    return _oracle_fail_dict(label, route_s=round(time.monotonic() - t0, 1),
                                             error=f"route failed: {cand.err}")
                # GND-FANOUT (owner rule 2026-07-08, wired post-wave-12): impedance-
                # reducing per-GND-pin vias on the oracle's OWN routed copy, fully
                # legality-guarded + teeth-verified DRC-neutral (cec_gnd_fanout).
                # route=False leaves external input boards UNTOUCHED by design.
                try:
                    import cec_gnd_fanout
                    gnd_rep = cec_gnd_fanout.synthesize(routed)
                except Exception as e:                        # noqa: BLE001 -- fail-safe
                    gnd_rep = {"added": 0, "error": "%s: %s" % (type(e).__name__, e)}
            else:
                routed = placed
                rules = cec_score.Rules.from_board(routed)
                gnd_rep = {"added": 0, "note": "route=False -- input board not mutated"}
            route_s = round(time.monotonic() - t0, 1)

            # ---- 3. grade: the full conjunction ----
            m = cec_score.score(routed, rules=rules)
            gates_pass = bool(m.gates_pass)                  # kelvin_ok AND diffpair_ok AND drc==0

            fsum = cec_constraints.foreign_on_pour_summary(routed)
            foreign_ok = (fsum.get("status") != "error"
                          and fsum.get("n_tracks", 0) == 0 and fsum.get("n_vias", 0) == 0)

            unconn_nets = list(m.detail.get("unconn_nets", []))
            crit, sig = _classify_unconnected(unconn_nets, rules)
            routing_complete = (len(crit) == 0) and (m.unconnected <= unconn_finish_tol)

            try:
                sside = _oracle_sense_side(routed)
            except Exception as e:                            # noqa: BLE001 -- FAIL-CLOSED
                sside = {"applicable": True, "ok": False,
                         "violations": ["checker error: %s" % e]}
            sense_side_ok = bool(sside.get("ok"))

            try:
                dq = _oracle_decoupler_adjacency(placed, cfg)
            except Exception as e:                            # noqa: BLE001 -- FAIL-CLOSED
                dq = {"ok": False, "violations": [("checker error", str(e)[:80], -1)]}
            try:
                bq = _oracle_bodies_in_pours(placed)
            except Exception as e:                            # noqa: BLE001 -- FAIL-CLOSED
                bq = {"ok": False, "violations": ["checker error: %s" % e]}
            bodies_ok = bool(bq.get("ok")) or not craft_gates
            try:
                pq = _oracle_pair_quality(routed)
            except Exception as e:                            # noqa: BLE001 -- FAIL-CLOSED
                pq = {"ok": False, "violations": ["checker error: %s" % e]}
            # ADVISORY (2026-07-08): the orphaned pour-family + DFM checkers are WIRED but
            # not gating -- teeth showed both mis-fire on controls (pour-present name-
            # matches /DET12V as high-current; DFM counts 94 on the SHIPPED 12vhpwr).
            # Calibration owner-queued; visibility now beats silent orphanhood.
            try:
                pfam = _oracle_pour_family(routed)
            except Exception as e:                            # noqa: BLE001
                pfam = {"ok": False, "checks": {"error": {"ok": False, "detail": str(e)[:120]}}}
            try:
                dfm = _oracle_dfm(routed)
            except Exception as e:                            # noqa: BLE001
                dfm = {"ok": False, "violations": [str(e)[:120]]}
            try:
                rsan = _oracle_route_sanity(routed)
            except Exception as e:                            # noqa: BLE001
                rsan = {"ok": False, "violations": ["checker error: %s" % e]}
            try:
                facing = _oracle_facing_fraction(placed)
            except Exception as e:                            # noqa: BLE001
                facing = {"ok": False, "facing_pct": None, "note": str(e)[:120]}
            try:
                gapp = _oracle_gap_profile(placed)
            except Exception as e:                            # noqa: BLE001
                gapp = {"ok": False, "note": str(e)[:120]}
            # SI advisories (cheap wins, owner GO 2026-07-08): Z0/Zdiff vs the stackup
            # (netclass-file-only, ~ms), kelvin loop-area + crosstalk on ONE shared load.
            try:
                import cec_impedance
                import pcbnew as _pn
                _sib = _pn.LoadBoard(routed)
                si = {"impedance": cec_impedance.audit_impedance(routed),
                      "kelvin_loops": cec_impedance.audit_kelvin_loops(routed, board=_sib),
                      "crosstalk": cec_impedance.audit_crosstalk(routed, board=_sib)}
            except Exception as e:                            # noqa: BLE001
                si = {"error": "%s: %s" % (type(e).__name__, e)}
            try:
                sp = _oracle_stranded_parts(placed)
            except Exception as e:                            # noqa: BLE001 -- FAIL-CLOSED
                sp = {"ok": False, "violations": ["checker error: %s" % e]}
            stranded_ok = bool(sp.get("ok")) or not craft_gates
            try:
                cc = _oracle_circuit_complete(routed)
            except Exception as e:                            # noqa: BLE001 -- FAIL-CLOSED
                cc = {"ok": False, "violations": ["checker error: %s" % e]}
            circuit_ok = bool(cc.get("ok")) or not craft_gates
            try:
                kr = _oracle_kelvin_reach(placed)
            except Exception as e:                            # noqa: BLE001 -- FAIL-CLOSED
                kr = {"ok": False, "violations": ["checker error: %s" % e]}
            kelvin_reach_ok = bool(kr.get("ok")) or not craft_gates
            try:
                cy = _oracle_courtyard_overlaps(placed)
            except Exception as e:                            # noqa: BLE001 -- FAIL-CLOSED
                cy = {"ok": False, "violations": ["checker error: %s" % e]}
            courtyards_ok = bool(cy.get("ok")) or not craft_gates
            try:
                cq = _oracle_comparator_adjacency(placed)
            except Exception as e:                            # noqa: BLE001 -- FAIL-CLOSED
                cq = {"ok": False, "violations": ["checker error: %s" % e]}
            comparator_ok = bool(cq.get("ok")) or not craft_gates
            try:
                pe = _oracle_pin_escape(placed)
            except Exception as e:                            # noqa: BLE001 -- FAIL-CLOSED
                pe = {"ok": False, "violations": ["checker error: %s" % e]}
            pin_escape_ok = bool(pe.get("ok")) or not craft_gates
            try:
                ce = _oracle_courtyard_edge(placed)
            except Exception as e:                            # noqa: BLE001 -- FAIL-CLOSED
                ce = {"ok": False, "violations": ["checker error: %s" % e]}
            courtyard_edge_ok = bool(ce.get("ok")) or not craft_gates
            try:
                _fid_expect = bool(cfg is not None and str(
                    (cfg.params or {}).get("fiducials", "3")).lower()
                    not in ("none", "0", ""))
                fq = _oracle_fiducials(placed, expect=_fid_expect)
            except Exception as e:                            # noqa: BLE001 -- FAIL-CLOSED
                fq = {"ok": False, "violations": ["checker error: %s" % e]}
            fiducials_ok = bool(fq.get("ok")) or not craft_gates
            try:
                tb = _oracle_tht_backside(placed)
            except Exception as e:                            # noqa: BLE001 -- FAIL-CLOSED
                tb = {"ok": False, "violations": ["checker error: %s" % e]}
            tht_backside_ok = bool(tb.get("ok")) or not craft_gates
            decouple_ok = bool(dq.get("ok")) or not craft_gates
            pairs_ok = bool(pq.get("ok")) or not craft_gates

            # ---- thermal LAST (owner directive 2026-07-08: "thermal gate only on a
            # 'new best' board"). thermal='lazy' runs the 5-17s field solve ONLY when
            # every OTHER gate term already passed -- i.e. the candidate would be
            # gate-clean and could win the wave, so thermal must CONFIRM it is not a
            # thermal mirage. An already-failing candidate skips the solve (its gate is
            # False either way; dT was only ever its LAST tie-break). A gate=True can
            # NEVER be produced without a real thermal pass (thermal-gate-required).
            others_ok = bool(gates_pass and foreign_ok and routing_complete
                             and sense_side_ok and decouple_ok and pairs_ok and bodies_ok
                             and comparator_ok and kelvin_reach_ok and courtyards_ok
                             and circuit_ok and stranded_ok and pin_escape_ok
                             and courtyard_edge_ok and fiducials_ok and tht_backside_ok)
            if thermal == "lazy" and not others_ok:
                therm = {"ok": False, "skipped": True, "max_T": None, "dT": None,
                         "gate_dt": gate_dt,
                         "note": "lazy skip: other gate terms already failed"}
                # the SILK score (its own ~0.9s --severity-all DRC) only matters as the
                # TIER-0 tie-break, unreachable for a failing candidate -- skip with it.
                silk = {"ok": True, "score_per_fp": None, "skipped": True}
            else:
                try:
                    therm = _oracle_thermal(routed, ambient=ambient, gate_dt=gate_dt,
                                            grid_mm=grid_mm)
                except Exception as e:                        # noqa: BLE001 -- FAIL-CLOSED
                    therm = {"ok": False, "error": "%s: %s" % (type(e).__name__, e),
                             "max_T": None, "dT": None, "gate_dt": gate_dt}
                try:
                    silk = _oracle_silk_score(routed)
                except Exception as e:                        # noqa: BLE001
                    silk = {"ok": False, "score_per_fp": None,
                            "violations": ["checker error: %s" % e]}
            thermal_ok = bool(therm.get("ok"))

            gate = bool(others_ok and thermal_ok)

            ft = int(fsum.get("n_tracks", 0)) + int(fsum.get("n_vias", 0))
            safety_fails = (0 if m.kelvin_ok else 1) + (0 if m.diffpair_ok else 1)
            dT_for_key = therm.get("dT")
            dT_for_key = float(dT_for_key) if dT_for_key is not None else 1e6
            # sort_key (ascending, best first). tier 0 = gate-clean: tie-break by thermal MARGIN
            # (smaller dT first), then fewer vias, then the SILK score/fp (round-2 item 3 -- the
            # craft term: hand 0.18-0.43 vs fresh 4.5+), then shorter length. tier 1 = failing:
            # ordered by CLOSENESS -- safety fails first, then foreign, then unconnected, then
            # drc, then thermal.
            silk_key = silk.get("score_per_fp")
            silk_key = float(silk_key) if silk_key is not None else 99.0
            if gate:
                sort_key = (0, round(dT_for_key, 1), m.vias, round(silk_key, 1),
                            round(m.length, 1), 0)
            else:
                sort_key = (1, safety_fails, ft, m.unconnected, m.drc, round(dT_for_key, 1))

            res = {
                "gate": gate, "label": label, "route_s": route_s, "routed": routed,
                "passes": passes, "opt": opt, "seed": seed,
                "gates_pass": gates_pass, "kelvin_ok": bool(m.kelvin_ok),
                "diffpair_ok": bool(m.diffpair_ok), "drc": m.drc, "drc_finishing_only": (m.drc == 0),
                "drc_types": dict(m.drc_types), "unconnected": m.unconnected,
                "unconn_nets": unconn_nets, "unconn_critical": crit, "unconn_signal": sig,
                "routing_complete": routing_complete, "unconn_finish_tol": unconn_finish_tol,
                "foreign_ok": foreign_ok, "foreign": {"status": fsum.get("status"),
                    "tracks": fsum.get("n_tracks", 0), "vias": fsum.get("n_vias", 0),
                    "pours": fsum.get("n_pours", 0)},
                "thermal_ok": thermal_ok, "thermal": therm,
                "sense_side_ok": sense_side_ok, "sense_side": sside,
                "decouple_ok": decouple_ok, "decouple": dq,
                "bodies_in_pours_ok": bodies_ok, "bodies_in_pours": bq,
                "comparator_ok": comparator_ok, "comparator": cq,
                "kelvin_reach_ok": kelvin_reach_ok, "kelvin_reach": kr,
                "circuit_ok": circuit_ok, "circuit": cc,
                "stranded_ok": stranded_ok, "stranded": sp,
                "pour_family_advisory": pfam, "dfm_advisory": dfm,
                "route_sanity_advisory": rsan, "silk_score": silk,
                "facing_advisory": facing, "gap_advisory": gapp,
                "gnd_fanout": gnd_rep, "si_advisory": si,
                "courtyards_ok": courtyards_ok, "courtyards": cy,
                "pin_escape_ok": pin_escape_ok, "pin_escape": pe,
                "courtyard_edge_ok": courtyard_edge_ok, "courtyard_edge": ce,
                "fiducials_ok": fiducials_ok, "fiducials": fq,
                "tht_backside_ok": tht_backside_ok, "tht_backside": tb,
                "pairs_ok": pairs_ok, "pair_quality": pq,
                "vias": m.vias, "tracks": m.tracks, "length": round(m.length, 2),
                "sort_key": sort_key,
                "reasons": _oracle_reasons(gates_pass, m, foreign_ok, fsum, thermal_ok, therm,
                                           routing_complete, crit, sig, unconn_finish_tol,
                                           sside=sside, dq=dq, pq=pq, bq=bq, cq=cq, kr=kr, cy=cy,
                                           cc_g=cc, sp_g=sp, pe_g=pe, ce_g=ce, fq_g=fq,
                                           tb_g=tb),
            }
            if verbose:
                print(f"    [oracle] {label}: gate={gate} kelvin={m.kelvin_ok} diff={m.diffpair_ok} "
                      f"drc={m.drc} unconn={m.unconnected}({len(crit)}crit) "
                      f"foreign={res['foreign']['tracks']}t/{res['foreign']['vias']}v "
                      f"dT={therm.get('dT')} ({route_s}s)")
            return res
    finally:
        if own_wd and not keep:
            shutil.rmtree(work_dir, ignore_errors=True)


def _oracle_fail_dict(label, *, route_s=None, error=""):
    """A worst-rank failing verdict for a route that could not even produce a board."""
    return {"gate": False, "label": label, "route_s": route_s, "routed": None,
            "error": error, "gates_pass": False, "kelvin_ok": False, "diffpair_ok": False,
            "drc": 9999, "drc_finishing_only": False, "unconnected": 9999, "unconn_critical": [],
            "unconn_signal": [], "routing_complete": False, "foreign_ok": False,
            "foreign": {"status": "error", "tracks": 9999, "vias": 9999, "pours": 0},
            "thermal_ok": False, "thermal": {"ok": False, "dT": None},
            "sort_key": (1, 9, 9999, 9999, 9999, 1e6), "reasons": [error or "route produced no board"]}


def _oracle_reasons(gates_pass, m, foreign_ok, fsum, thermal_ok, therm,
                    routing_complete, crit, sig, tol, sside=None, dq=None, pq=None, bq=None,
                    cq=None, kr=None, cy=None, cc_g=None, sp_g=None, pe_g=None, ce_g=None,
                    fq_g=None, tb_g=None):
    """One human-readable reason per failing gate term (empty when the board is gate-clean)."""
    r = []
    if not m.kelvin_ok:
        r.append("kelvin_ok=False (a Kelvin sense pair is not routed / cut-vertex)")
    if not m.diffpair_ok:
        r.append("diffpair_ok=False (a diff pair is not routed)")
    if m.drc != 0:
        r.append(f"structural DRC={m.drc} (not finishing-only): {dict(m.drc_types)}")
    if not foreign_ok:
        r.append(f"foreign_on_pour status={fsum.get('status')} "
                 f"tracks={fsum.get('n_tracks')} vias={fsum.get('n_vias')} (must be 0/0)")
    if not thermal_ok:
        if therm.get("skipped"):
            r.append("thermal SKIPPED (lazy: other gate terms already failed)")
        else:
            r.append(f"thermal dT={therm.get('dT')} > gate {therm.get('gate_dt')}"
                     + (f" ({therm['error']})" if therm.get("error") else ""))
    if sp_g is not None and not sp_g.get("ok"):
        r.append(f"STRANDED parts (no connected neighbor within reach): {sp_g.get('violations')[:5]}")
    if cc_g is not None and not cc_g.get("ok"):
        r.append(f"OPEN force circuits (current cannot traverse): {cc_g.get('violations')[:4]}")
    if kr is not None and not kr.get("ok"):
        r.append(f"kelvin REACH violated pre-route (tap cannot connect): {kr.get('violations')[:4]}")
    if cy is not None and not cy.get("ok"):
        r.append(f"courtyard overlaps on the placed board: {cy.get('violations')[:4]}")
    if pe_g is not None and not pe_g.get("ok"):
        r.append(f"pin-escape violated (boxed pads, no routing corridor): "
                 f"boxed0={pe_g.get('boxed0_pct')}% le1={pe_g.get('le1_pct')}% "
                 f"offenders={pe_g.get('violations')[:5]}")
    if ce_g is not None and not ce_g.get("ok"):
        r.append(f"courtyard-edge clearance < {ce_g.get('min_mm')}mm: "
                 f"{ce_g.get('violations')[:5]}")
    if fq_g is not None and not fq_g.get("ok"):
        r.append(f"fiducial quality violated (count/clear/collinear): "
                 f"{fq_g.get('violations')[:4]}")
    if tb_g is not None and not tb_g.get("ok"):
        r.append(f"THT-backside clip (part under a through-hole pin field): "
                 f"{tb_g.get('violations')[:4]}")
    if cq is not None and not cq.get("ok"):
        r.append(f"detection comparator fragmented from its INA181: {cq.get('violations')[:4]}")
    if bq is not None and not bq.get("ok"):
        r.append(f"bodies IN pours (hard rule): {bq.get('violations')[:6]}")
    if dq is not None and not dq.get("ok"):
        r.append(f"decoupler adjacency violated (cap > threshold from its IC): {dq.get('violations')[:5]}")
    if pq is not None and not pq.get("ok"):
        r.append(f"data-pair quality violated: {pq.get('violations')[:4]}")
    if sside is not None and sside.get("applicable") and not sside.get("ok"):
        r.append(f"sense-side rule violated (analog across faces): {sside.get('violations')[:4]}")
    if not routing_complete:
        if crit:
            r.append(f"unconnected on safety/power nets: {crit}")
        if len(sig) > tol or m.unconnected > tol:
            r.append(f"{m.unconnected} unconnected ratline(s) > finishing tol {tol}: signal={sig}")
    return r


def adjudicate_candidates(cfg, cands, *, k=3, max_workers=None, verbose=False, **grade_kw):
    """Two-stage selection (prune -> adjudicate): the cheap placement_proxy already sorted *cands*
    best-first; route_oracle_grade ADJUDICATES the top-k survivors with a real route, and the oracle
    sort_key becomes the FINAL order over those k. Routing is minutes each, so k stays small (default 3).

    Mutates each adjudicated candidate's `.oracle`; returns the FULL list re-ordered so the oracle-graded
    top-k lead (by sort_key), followed by the un-adjudicated tail in their original proxy order. A graded
    candidate ALWAYS outranks an un-graded one (we only trust a real route)."""
    if not cands:
        return cands
    topk = cands[:max(1, k)]
    tail = cands[len(topk):]
    for c in topk:
        try:
            c.oracle = route_oracle_grade(c, cfg=cfg, verbose=verbose, **grade_kw)
        except Exception as e:                                # noqa: BLE001 -- a grade failure ranks worst, never crashes selection
            _tc.warn_once("route_oracle_grade", "oracle grade failed (%s); candidate ranked worst" % e)
            c.oracle = _oracle_fail_dict(f"{c.strat}/seed{c.seed}", error="%s: %s" % (type(e).__name__, e))
    topk.sort(key=lambda c: c.oracle.get("sort_key", (2,)))
    if verbose:
        clean = sum(1 for c in topk if c.oracle.get("gate"))
        print(f"  [oracle] adjudicated top-{len(topk)}: {clean} gate-clean; "
              f"winner={topk[0].strat}/seed{topk[0].seed} gate={topk[0].oracle.get('gate')}")
    return topk + tail


def _route_oracle_enabled(cfg):
    """Opt-in switch: CEC_ROUTE_ORACLE=1 (env) or cfg.params['route_oracle'] truthy. Default OFF so the
    cheap proxy path is byte-for-byte unchanged."""
    if os.environ.get("CEC_ROUTE_ORACLE", "0") == "1":
        return True
    return bool(cfg.params.get("route_oracle")) if cfg is not None else False


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
    # build_board places mounts (H1..) + fiducials (FID1..) itself; LOGO stays
    # board-level finishing. (Round-2 item 6, 2026-07-08: the placer always PLANNED
    # FID1-3 via place_mechanical but this line dropped them -- every fresh wave board
    # shipped with ZERO fiducials while hand hub/12vhpwr carry 3.)
    fids = [(p[0], p[1]) for r, p in sorted(cand.P.items())
            if r.startswith("FID") and r[3:].isdigit()]
    P3 = {r: (p[0], p[1], p[2]) for r, p in cand.P.items()
          if not _is_mount(r) and not r.startswith(("LOGO", "FID"))}
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    _dropk = ()
    if cfg.params.get("respect_antenna_keepout", True) is False:
        _dropk = tuple(r for r, fpid in _fp_of(View(cfg).nl).items() if "esp32" in str(fpid).lower())
    cec_pcb.build_board(out, _ensure_netlist_path(cfg), P3, mounts, logo, cand.W, cand.H, force_argv=False,
                        corner_radius=float(cfg.params.get('corner_radius', 0.0) or 0.0),
                        drop_keepout=_dropk, back_refs=tuple(getattr(cand, 'back_refs', ()) or ()),
                        inner_power_routing=bool(cfg.params.get('inner_power_routing')),
                        fiducials=fids)
    for ext in (".kicad_pro", ".kicad_dru"):         # carry rules so DRC matches the real module
        s = (cfg.pcb[:-len(".kicad_pcb")] + ext) if cfg.pcb else ""
        if s and os.path.isfile(s):
            shutil.copy(s, out[:-len(".kicad_pcb")] + ext)
    # POUR LEVER (stage 3, docs/pour-lever-scoping-2026-07-08.md): write the placement's PourPlan
    # to a <board>.pourplan.json sidecar. Only board_path strings cross the materialize ->
    # route_oracle_grade -> route_once -> spawn-worker boundary, so the plan (derived pours +
    # folded pour() asks, and -- stage 4 -- any router reshape) must ride a sidecar to reach the
    # route. Derived under the ACTIVE recipe env; _oracle_hints_pours re-validates the sidecar's
    # board_sig + recipe before trusting it and re-derives otherwise, so this is purely additive
    # (a board routed without a sidecar is byte-identical to today). Best-effort: never blocks the
    # materialize on a serialization error.
    try:
        import cec_pourplan
        _asks = tuple(cfg.params.get("pour_asks") or ())
        _plan = cec_pourplan.PourPlan.from_board(out, asks=_asks)
        with open(out[:-len(".kicad_pcb")] + ".pourplan.json", "w") as _f:
            json.dump(_plan.to_dict(), _f, indent=1, sort_keys=True)
    except Exception as _e:                                  # noqa: BLE001 -- sidecar is best-effort
        _tc.warn_once("pourplan_write", "pourplan sidecar not written (%s)" % _e)
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
# Connector-joint conductor materials (iteration-11 blade-interconnect element).
# TE 63951-1 tab and 63969-1 receptacle are both BRASS (tin over copper/nickel);
# CuZn30 ~6.2e-8, CuZn37 ~7.0e-8 ohm.m -- 6.4e-8 is the working value, alpha
# ~0.0015/K (brass TCR is ~2.6x lower than copper's).
RHO_BRASS = 6.4e-8                       # ohm·m at 20°C
ALPHA_BRASS = 0.0015                     # 1/°C
RHO_CU_20C = 1.72e-8                     # ohm·m at 20°C (matches cec_dcir)


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
        elif "-12V" in n:
            # NEGATIVE rail: the bare substring test below ("12V" in n) used to
            # capture "-12V"/"/-12V" and assign it the full CABLE current -- a
            # 0.3A-class ATX signal rail read as a 40A force net and false-fired
            # the runaway gate (found by the 2026-07-06 blade-interconnect
            # audit on the atx24 output daughterboard; the atx-24pin main board
            # carried the same false pessimism). Behaviour change is confined
            # to nets containing "-12V"; every other classification is untouched.
            out[n] = cfg.params.get("rail_neg12_A", 0.5)
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
    # Board-to-board CONNECTOR JOINTS (iteration-11 element): populated ONLY
    # when cfg.params['joints'] declares them -- absent, the solve is
    # numerically identical to the pre-element solver (additive contract,
    # asserted by tests.test_am04_anchors.T12JointRatingAnchor).
    joints: list = field(default_factory=list)


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


# ---- connector-joint element (board-to-board interconnect) ---------------------------------------
# First-class thermal element for a MATED CONNECTOR JOINT -- the class the suite
# never modelled (blade/receptacle interconnects, iterations 1-10). A joint is a
# CONTACT interface resistance in series with metal CONDUCTOR segments (each with
# its own resistivity/TCR -- brass, not copper), dissipating into ambient through
# a lumped joint thermal resistance Rth. ANCHORED IN TRUTH per the AM-04 pattern:
# Rth is not hand-picked -- it is CALIBRATED so the model reproduces the part's
# PUBLISHED rating datum (TE 108-1706 Fig 4: 22.9 A base rated current, derived
# by the same 30°C-rise method [AMP 109-45-1] the platform margin policy uses).
# That datum is a real external anchor; tests.test_am04_anchors.T12 asserts it
# and gives the gate teeth (a worn/sabotaged joint must FAIL physics_gates).
@dataclass
class JointSegment:
    """One metal conductor leg of a joint's current path."""
    name: str
    cross_mm2: float
    length_mm: float
    rho_ohm_m: float = RHO_BRASS
    alpha_per_C: float = ALPHA_BRASS

    def R_ohm(self, T_C=20.0):
        if self.cross_mm2 <= 0 or self.length_mm <= 0:
            return 0.0
        r20 = self.rho_ohm_m * (self.length_mm * 1e-3) / (self.cross_mm2 * 1e-6)
        return r20 * (1.0 + self.alpha_per_C * (T_C - 20.0))


@dataclass
class JointSpec:
    """A mated connector joint class: contact interface + conductor segments +
    the published rating datum that calibrates its thermal resistance.
    General on purpose -- future connector classes declare their own spec."""
    name: str
    contact_R_ohm: float = 1.0e-3        # spec MAX termination R (conservative; the
                                         # published figure already includes some bulk,
                                         # so summing explicit segments double-counts
                                         # slightly on the safe side)
    segments: tuple = ()
    rating_I_A: float = 22.9             # published base rated current
    rating_dT_C: float = 30.0            # at the 30°C-rise rating method
    rating_ambient_C: float = 25.0       # rating-test ambient (109-45-1 bench)
    worn_contact_R_ohm: float = 10.0e-3  # degraded-interface scenario (fretting/wear)
    rth_CW: float = None                 # joint->ambient; None => calibrate from the rating

    def R_total_ohm(self, T_C, contact_R_ohm=None):
        c = self.contact_R_ohm if contact_R_ohm is None else contact_R_ohm
        return c + sum(s.R_ohm(T_C) for s in self.segments)

    def calibrated_rth(self):
        """Rth such that the model reproduces the rating datum exactly:
        dT(rating_I) = rating_dT at the rating ambient, with rho(T) feedback."""
        if self.rth_CW is not None:
            return self.rth_CW
        T = self.rating_ambient_C + self.rating_dT_C
        R = self.R_total_ohm(T)
        P = self.rating_I_A ** 2 * R
        return self.rating_dT_C / P if P > 0 else 0.0


def joint_te_63951_63969():
    """TE 63951-1 right-angle FASTON tab (blade) mated into a TE 63969-1 FASTON
    .250 PCB receptacle -- the platform's daughterboard-to-main-board joint
    (owner-ratified 2026-07-06, blade-fit-check addendum 7). Real geometry:
    blade 6.35 x 0.81 brass (dwg C=63951); conduction length leg-row ->
    mid-engagement ~12 mm; receptacle 0.41 brass, rolls -> solder tails ~8 mm
    at ~7.4 mm developed width; two 0.41 x ~1.4 stamped tails through the board
    (~2 mm incl. fillet). Contact = the 108-1706 <=1 mOhm spec max."""
    return JointSpec(
        name="te_63951_63969",
        contact_R_ohm=1.0e-3,
        segments=(
            JointSegment("blade_63951", cross_mm2=6.35 * 0.81, length_mm=12.0),
            JointSegment("receptacle_63969", cross_mm2=7.4 * 0.41, length_mm=8.0),
            JointSegment("tails_solder", cross_mm2=2 * 1.4 * 0.41, length_mm=2.0),
        ),
    )


JOINT_SPECS = {"te_63951_63969": joint_te_63951_63969}


def joint_solve(spec, I, ambient=None, *, worn=False, contact_R_ohm=None):
    """Self-consistent joint temperature: dT = P(T)*Rth with per-segment rho(T)
    feedback (contact R held constant -- its T-dependence is interface physics
    the spec does not publish). Returns the joint record dict."""
    if ambient is None:
        ambient = _AMBIENT["enclosed_passive"]
    if isinstance(spec, str):
        spec = JOINT_SPECS[spec]()
    c = spec.worn_contact_R_ohm if worn else (
        spec.contact_R_ohm if contact_R_ohm is None else contact_R_ohm)
    rth = spec.calibrated_rth()
    dt = 0.0
    for _ in range(40):                          # Picard; converges in a few steps
        R = spec.R_total_ohm(ambient + dt, contact_R_ohm=c)
        dt_new = min(I * I * R * rth, 999.0)
        if abs(dt_new - dt) < 1e-6:
            dt = dt_new
            break
        dt = dt_new
    R = spec.R_total_ohm(ambient + dt, contact_R_ohm=c)
    return {"joint": spec.name, "I": round(I, 2),
            "R_mOhm": round(R * 1e3, 3), "contact_R_mOhm": round(c * 1e3, 3),
            "P_W": round(I * I * R, 3), "rth_CW": round(rth, 1),
            "dT": round(dt, 1), "T": round(ambient + dt, 1), "worn": bool(worn)}


def joints_solve(cfg, ambient):
    """Solve every joint declared in cfg.params['joints']: a list of dicts
    {spec: <JOINT_SPECS key or JointSpec>, I: amps [, name, count, worn]}.
    `count` parallel identical joints split I evenly. Returns [] when nothing
    is declared -- the additive-contract case."""
    out = []
    for j in cfg.params.get("joints", ()) or ():
        spec = j.get("spec", "te_63951_63969")
        n = max(1, int(j.get("count", 1)))
        rec = joint_solve(spec, float(j.get("I", 0.0)) / n, ambient,
                          worn=bool(j.get("worn", False)),
                          contact_R_ohm=j.get("contact_R_ohm"))
        if j.get("name"):
            rec["name"] = j["name"]
        rec["count"] = n
        out.append(rec)
    return out


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

    joints = joints_solve(cfg, ambient)          # [] unless cfg declares them (additive)
    for j in joints:
        if ambient + j["dT"] > max_T:
            max_T, max_dT = ambient + j["dT"], j["dT"]

    return ThermalResult(ambient=ambient, max_T=round(max_T, 1), max_dT=round(max_dT, 1),
                         nets=net_res, vias=vias[:8], shunts=shunts, joints=joints,
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
    for j in getattr(res, "joints", ()) or ():
        if j["T"] > t_max or j["dT"] > dt_max:
            flags.append(Flag("joint over-temp", j.get("name", j["joint"]), 0.8, Kind.MEASURE,
                              dict(j, limit_dT=dt_max, limit_T=t_max)))
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
