#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_sym_audit -- SYMBOL PIN-TYPE AUDITOR (T2, docs/schematic-quality-charter.md)
# ============================================================================
# Why: ERC's pin-type checking (power-pin-driven-by-two-outputs, output-to-
# output collisions, etc.) is only as strong as the electrical types baked
# into the symbols it reads. easyeda-pulled symbols routinely carry
# "Unspecified" (or a uniform passive/bidirectional type) across the board,
# which silently defeats that whole class of ERC check. On a 484-ball part
# (cec-ent-compute:MPFS095T_FCVG484) a single mistyped power/reference pin is
# exactly the kind of thing that hides best -- one pin lost in hundreds, ERC
# never even looks at it because its type says "don't check me".
#
# This tool is READ-ONLY (report mode) by default. It parses any .kicad_sym
# (KiCad 10 s-expression format) with a small real s-expression reader (not
# regex-on-the-whole-file -- see the schematic-quality charter's "calibrate,
# don't guess" principle), extracts every pin's number/name/electrical type,
# and applies a conservative set of NAME-HEURISTIC proposals (never an
# assertion) for what the type probably should be, each carrying its own
# confidence tier (high/med/low).
#
# Two independent finding rules (both required by the T2 spec):
#   1. ANY pin currently typed "unspecified" is ALWAYS a finding (regardless
#      of whether a heuristic could even name a better type for it).
#   2. A pin whose CURRENT type contradicts a HIGH-confidence proposal is a
#      finding even if the current type isn't "unspecified" (e.g. a VDD pin
#      that was typed "passive").
# Medium/low-confidence mismatches are also surfaced (informational) so nothing
# gets lost, but only HIGH-confidence findings gate the CLI exit code -- this
# is the sheet-02 gate docs/schematic-quality-charter.md wires T2 into.
#
# --fix mode is NOT the default and is intentionally inconvenient to reach:
# it only ever applies HIGH-confidence fixes, and only after writing a
# reviewable before/after log to --review-out (a human-visible diff is the
# gate; this pass never invokes --fix on the real cec-ent libraries, that is
# the sheet-02 human-reviewed step described in the charter).
#
# Usage:
#   python3 scripts/cec_sym_audit.py --audit lib/cec-ent-power.kicad_sym ...
#   python3 scripts/cec_sym_audit.py --audit-all
#   python3 scripts/cec_sym_audit.py --fix lib/foo.kicad_sym --review-out /tmp/review.txt
#
# Exit code: 0 if no HIGH-confidence findings across the requested libraries,
# 1 otherwise (a real gate a CI job or the sheet-02 pass can rely on).
# ============================================================================

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VALID_ELECTRICAL_TYPES = {
    "input", "output", "bidirectional", "tri_state", "passive", "free",
    "unspecified", "power_in", "power_out", "open_collector", "open_drain",
    "no_connect",
}

CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


# ---------------------------------------------------------------------------
# a small, real s-expression reader (no regex-on-the-whole-file guessing --
# KiCad 10 .kicad_sym is genuine s-expr; strings can contain literal '(' ')'
# and escaped quotes, which line-oriented regex reliably mis-splits on long
# Description/Datasheet property strings -- exactly the kind of thing this
# repo's libraries carry a lot of).
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List:
    tokens = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "(" or c == ")":
            tokens.append(c)
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            tokens.append(("STR", "".join(buf)))
            i = j + 1
            continue
        j = i
        while j < n and text[j] not in " \t\r\n()":
            j += 1
        tokens.append(("ATOM", text[i:j]))
        i = j
    return tokens


def parse_sexpr(text: str):
    """Parse one top-level s-expression form into nested python lists/strs."""
    tokens = _tokenize(text)
    pos = 0

    def read():
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            lst = []
            while tokens[pos] != ")":
                lst.append(read())
            pos += 1  # consume ')'
            return lst
        if tok == ")":
            raise ValueError("unexpected ')' in kicad_sym")
        kind, val = tok
        return val

    return read()


# ---------------------------------------------------------------------------
# symbol / pin extraction
# ---------------------------------------------------------------------------

@dataclass
class Pin:
    number: str
    name: str
    etype: str


@dataclass
class SymbolDef:
    name: str
    pins: List[Pin] = field(default_factory=list)


def _find_child(node, tag):
    for child in node:
        if isinstance(child, list) and child and child[0] == tag:
            return child
    return None


def _pin_from_node(node) -> Pin:
    etype = node[1] if len(node) > 1 and isinstance(node[1], str) else "unspecified"
    name_node = _find_child(node, "name")
    number_node = _find_child(node, "number")
    name = name_node[1] if name_node and len(name_node) > 1 else ""
    number = number_node[1] if number_node and len(number_node) > 1 else "?"
    return Pin(number=number, name=name, etype=etype)


def _collect_pins(node, out: List[Pin]):
    if isinstance(node, list):
        if node and node[0] == "pin":
            out.append(_pin_from_node(node))
            return  # a pin node's children (alt-name effects etc) aren't pins
        for child in node:
            if isinstance(child, list):
                _collect_pins(child, out)


def load_symbols(path: str) -> List[SymbolDef]:
    """Parse a .kicad_sym file into top-level SymbolDef entries (each with
    every pin gathered from its nested unit/style sub-blocks)."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    root = parse_sexpr(text)
    if not isinstance(root, list) or not root or root[0] != "kicad_symbol_lib":
        raise ValueError(f"{path}: not a kicad_symbol_lib file")
    symbols = []
    for item in root[1:]:
        if isinstance(item, list) and item and item[0] == "symbol":
            name = item[1] if len(item) > 1 else "?"
            pins: List[Pin] = []
            _collect_pins(item, pins)
            symbols.append(SymbolDef(name=name, pins=pins))
    return symbols


# ---------------------------------------------------------------------------
# name-heuristic proposals
# ---------------------------------------------------------------------------
# Each rule below implements exactly one bullet from the T2 spec (plus a
# clearly-labeled EXT block of conservative extensions found useful against
# the real cec-ent-* libraries during calibration -- see the charter's
# "calibrate, don't guess" principle). Every rule returns
# (proposed_type_or_None, confidence, rule_id, note) or None if it doesn't
# match. proposed_type is None only for the flag-only XTAL/OSC rule -- it
# still produces a finding (a note to go verify), just no assertion.

GPIO_RE = re.compile(r"^(GPIO|HSIO)_?\d+", re.I)


def _normalize(alt: str) -> str:
    """Strip KiCad overbar syntax ~{...}, leading '/', '+' etc, collapse any
    run of non-alphanumerics to '_', and pad with sentinel underscores so a
    plain re.search for '_XYZ_' reliably finds a whole-token match at either
    end of the string too."""
    s = alt.replace("~{", "").replace("}", "")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()
    return f"_{s}_"


Proposal = Tuple[Optional[str], str, str, str]  # (etype, confidence, rule_id, note)


def _rule_nc(alt_pad: str) -> Optional[Proposal]:
    if alt_pad == "_NC_":
        return ("no_connect", "high", "NC", "not-connected pin (NC)")
    return None


def _rule_gnd(alt_pad: str) -> Optional[Proposal]:
    for tok in ("GND", "VSS", "AGND", "PGND", "DGND", "SGND", "PWR_GND"):
        if f"_{tok}" in alt_pad or alt_pad.count(tok):
            if re.search(rf"_{tok}[A-Z0-9]*_", alt_pad):
                return ("power_in", "high", "GND",
                         f"ground-return pin ({tok} family)")
    return None


def _rule_vdd(alt_pad: str) -> Optional[Proposal]:
    if re.search(r"_A?D?VDD[A-Z0-9]*_", alt_pad):
        return ("power_in", "high", "VDD", "supply-rail pin (VDD family)")
    if re.search(r"_V(CC|BAT|PP)[A-Z0-9]*_", alt_pad):
        return ("power_in", "high", "VDD", "supply-rail pin (VCC/VBAT/VPP family)")
    if re.search(r"_P?S?VIN[A-Z0-9]*_", alt_pad):
        return ("power_in", "high", "VDD", "supply-rail pin (VIN family)")
    if re.search(r"_\d+V\d*_", alt_pad):
        return ("power_in", "high", "VDD", "supply-rail pin (bare voltage token, e.g. 3V3/5V0)")
    return None


def _rule_thermal(alt_pad: str) -> Optional[Proposal]:
    for tok in ("EP", "EPAD", "PAD", "THERMAL", "THERMALPAD"):
        if re.search(rf"_{tok}_", alt_pad):
            return ("power_in", "medium", "THERMAL",
                     "exposed/thermal pad -- flag, don't assert (verify GND tie; "
                     "could legitimately be 'passive' on some parts)")
    return None


def _rule_control_input(alt_pad: str) -> Optional[Proposal]:
    if re.search(r"_(EN|ENABLE)_", alt_pad):
        return ("input", "high", "EN", "enable/control pin (EN/ENABLE)")
    if re.search(r"_N?CS\d*_", alt_pad):
        return ("input", "high", "CS",
                 "chip-select pin (CS/nCS) -- orientation-dependent, verify "
                 "against the datasheet if this part is the bus MASTER "
                 "(a master-side CS is normally an output)")
    if re.search(r"_N?(RST|RESET)(B)?_", alt_pad) or "DEVRST" in alt_pad:
        return ("input", "high", "RST",
                 "reset pin (RST/nRST/DEVRST) -- verify if this part can "
                 "itself drive a reset OUTPUT to other devices")
    return None


def _rule_bus_bidir(alt_pad: str) -> Optional[Proposal]:
    if re.search(r"_SDA\d*_", alt_pad) or re.search(r"_SDIO\d*_", alt_pad):
        return ("bidirectional", "high", "BUS", "I2C/SDIO data pin")
    if re.search(r"_MDIO_", alt_pad):
        return ("bidirectional", "high", "BUS", "MDIO management-bus pin")
    if alt_pad in ("_D+_", "_D-_", "_DP_", "_DM_"):
        return ("bidirectional", "high", "BUS", "USB/differential data pin")
    if re.search(r"_DAT\d*_", alt_pad):
        return ("bidirectional", "high", "BUS", "DATn bus pin")
    return None


def _rule_output(alt_pad: str) -> Optional[Proposal]:
    if re.search(r"_(DO|TX\d*)_", alt_pad) or re.search(r"OUT\d*_$", alt_pad):
        return ("output", "medium", "OUT",
                 "likely-output pin (OUT/DO/TX suffix) -- unless this is a "
                 "bidirectional bus, or the TX/RX naming is relative to the "
                 "OTHER side of the interface (this part may be the "
                 "receiver of a signal named TX_*)")
    return None


def _has_databus_hint(alt_pad: str) -> bool:
    """True if a '_'-delimited subtoken of alt_pad is a bare data-bus lane
    name (IOn / DATn / Dn). Names like 'RESET_IO3' or 'DO_IO1' bundle a
    directional control/output hint together with a quad-mode data-bus
    alternate IN THE SAME '/'-alt segment (no further slash to split on) --
    this is exactly the W25Q256JVFIQ pin-1 shape ('/HOLD_/RESET_IO3', truly
    bidirectional in QPI mode). Used to force a conflict rather than assert
    a single confident direction over a data-capable ball."""
    inner = alt_pad.strip("_")
    for tok in inner.split("_"):
        if re.fullmatch(r"IO\d+", tok) or re.fullmatch(r"DAT\d+", tok) or re.fullmatch(r"D\d+", tok):
            return True
    return False


# --- extensions (EXT*), calibrated against the real cec-ent-* libraries ---

_JTAG_EXACT = {"TDI": "input", "TMS": "input", "TCK": "input", "TDO": "output"}


def _rule_ext_jtag(alt_pad: str) -> Optional[Proposal]:
    for name, etype in _JTAG_EXACT.items():
        if alt_pad == f"_{name}_":
            return (etype, "medium", "EXT-JTAG", "JTAG/TAP pin (extension heuristic)")
    if re.search(r"_TRST(B)?_", alt_pad):
        return ("input", "medium", "EXT-JTAG",
                 "JTAG TAP reset pin (extension heuristic)")
    return None


def _rule_ext_refclk(alt_pad: str) -> Optional[Proposal]:
    if "REFCLK" in alt_pad or "CLKIN" in alt_pad:
        return ("input", "medium", "EXT-CLK",
                 "reference/input clock pin (extension heuristic)")
    return None


def _rule_ext_vref(alt_pad: str) -> Optional[Proposal]:
    if "VREF" in alt_pad:
        return ("input", "medium", "EXT-VREF",
                 "reference-voltage pin (extension heuristic; some house "
                 "conventions type these power_in instead -- verify)")
    return None


def _rule_xtal(alt_pad: str) -> Optional[Proposal]:
    if "XTAL" in alt_pad or re.search(r"_OSC(IN|OUT)?_", alt_pad) or alt_pad in ("_XO_", "_XI_", "_X1_", "_X2_"):
        return (None, "low", "XTAL",
                 "crystal/oscillator pin -- flag only, direction depends on "
                 "circuit role (resonator vs external-oscillator-driven)")
    return None


# Order matters: first match per alt-name string wins. NC before anything
# else (an "NC" token must never fall through to another rule); GND before
# VDD (both are narrow/disjoint so order doesn't matter between them, kept
# for readability); control/bus/output/ext rules after the unambiguous ones.
_RULES = [
    _rule_nc,
    _rule_gnd,
    _rule_vdd,
    _rule_thermal,
    _rule_bus_bidir,
    _rule_control_input,
    _rule_ext_jtag,
    _rule_ext_refclk,
    _rule_ext_vref,
    _rule_output,
    _rule_xtal,
]


def _propose_for_alt(alt: str) -> Optional[Proposal]:
    alt_pad = _normalize(alt)
    for rule in _RULES:
        p = rule(alt_pad)
        if p:
            return p
    return None


def is_gpio_multifunction(pin_name: str) -> bool:
    """True if any '/'-joined alt-function name on this pin looks like a
    general-purpose I/O ball (GPIOn / HSIOn, with or without an underscore).
    These pins are legitimately multi-purpose on FPGA/SoC-class parts (the
    cec-ent-compute MPFS is exactly this case) -- 'bidirectional' is a
    defensible type for them and we do not second-guess a more specific
    current type (e.g. 'output' when the design fixes one alt function)."""
    return any(GPIO_RE.match(a.strip()) for a in pin_name.split("/") if a.strip())


def propose(pin_name: str) -> Optional[Proposal]:
    """Reconcile proposals across every '/'-joined alt-function name on a
    pin. Returns None if no rule matched any alt. If alts disagree on a
    concrete (non-None) type, the pin is genuinely ambiguous (a real
    multi-function ball whose alternate functions run opposite directions,
    e.g. a JTAG TDO shared with a plain GPIO) -- report that as a low-
    confidence, no-assertion finding rather than silently picking one."""
    alts = [a.strip() for a in pin_name.split("/") if a.strip()]
    if not alts:
        return None
    proposals: List[Proposal] = []
    for a in alts:
        p = _propose_for_alt(a)
        if p is not None:
            proposals.append(p)
        ap = _normalize(a)
        if _has_databus_hint(ap) and not (p is not None and p[0] == "bidirectional"):
            proposals.append((
                "bidirectional", "low", "DATAHINT",
                f"alt '{a}' carries a bare IOn/DATn data-bus lane token -- "
                "likely bidirectional in an alternate (e.g. quad-SPI) mode"
            ))
    if not proposals:
        return None
    concrete_types = {p[0] for p in proposals if p[0] is not None}
    if len(concrete_types) > 1:
        names = ", ".join(f"{p[0]}({p[2]})" for p in proposals if p[0] is not None)
        return (None, "low", "CONFLICT",
                f"conflicting alt-function directions across '{pin_name}': {names} "
                "-- manual review required")
    if len(concrete_types) == 1:
        etype = concrete_types.pop()
        matching = [p for p in proposals if p[0] == etype]
        best = max(matching, key=lambda p: CONFIDENCE_RANK[p[1]])
        notes = "; ".join(sorted({p[3] for p in matching}))
        rule_ids = "+".join(sorted({p[2] for p in matching}))
        return (etype, best[1], rule_ids, notes)
    # every matching rule was flag-only (e.g. XTAL) -> surface the first
    return proposals[0]


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------

# A proposed type is considered SATISFIED (no finding) if the current type
# is this specific, strictly-as-informative-or-better KiCad variant of it --
# e.g. a pin the OUT-rule calls 'output' that is already typed 'power_out'
# is not a bug, it's a MORE specific correct type; same for an MDIO/SDA bus
# pin already typed 'open_collector' instead of plain 'bidirectional'.
# Deliberately NOT applied to 'power_in' from the VDD/GND rules (a supply
# pin merely typed 'input' IS the exact bug class T2 exists to catch, so
# power_in stays exact-match only).
_COMPATIBLE_ALIASES = {
    "output": {"output", "power_out", "open_collector", "open_drain"},
    "input": {"input", "power_in"},
    "bidirectional": {"bidirectional", "open_collector", "open_drain", "tri_state"},
}


@dataclass
class Finding:
    symbol: str
    pin_number: str
    pin_name: str
    current_type: str
    proposed_type: Optional[str]
    confidence: str
    rule: str
    note: str


def audit_symbol(sym: SymbolDef) -> List[Finding]:
    findings: List[Finding] = []
    for pin in sym.pins:
        current = pin.etype
        if current not in VALID_ELECTRICAL_TYPES:
            # not itself this tool's concern (a KiCad-invalid file), but worth
            # a loud finding since ERC would choke on it too.
            findings.append(Finding(sym.name, pin.number, pin.name, current,
                                     None, "high", "INVALID",
                                     f"'{current}' is not a valid KiCad electrical type"))
            continue

        gpio_flex = is_gpio_multifunction(pin.name)
        prop = propose(pin.name)

        if gpio_flex:
            # legitimately multi-purpose; only flag if currently unspecified
            # or a type that can't plausibly cover an active multi-function
            # ball (no_connect/passive), never second-guess output/input/
            # bidirectional against each other.
            if current == "unspecified":
                findings.append(Finding(sym.name, pin.number, pin.name, current,
                                         "bidirectional", "low", "GPIO",
                                         "GPIO/HSIO multi-function pin -- "
                                         "'bidirectional' is plausible but not asserted"))
            elif current in ("no_connect", "passive"):
                findings.append(Finding(sym.name, pin.number, pin.name, current,
                                         "bidirectional", "medium", "GPIO",
                                         f"GPIO/HSIO multi-function pin typed '{current}', "
                                         "which cannot represent an active multi-function ball"))
            continue

        if prop is None:
            if current == "unspecified":
                findings.append(Finding(sym.name, pin.number, pin.name, current,
                                         None, "low", "NOMATCH",
                                         "no heuristic match; manual review required "
                                         "(pin type is 'unspecified')"))
            continue

        proposed_type, confidence, rule_id, note = prop
        if current == "unspecified":
            findings.append(Finding(sym.name, pin.number, pin.name, current,
                                     proposed_type, confidence, rule_id, note))
        elif proposed_type is not None and proposed_type != current:
            if current in _COMPATIBLE_ALIASES.get(proposed_type, set()):
                continue  # e.g. proposed 'output', current already 'power_out'
            findings.append(Finding(sym.name, pin.number, pin.name, current,
                                     proposed_type, confidence, rule_id,
                                     f"{note} (currently '{current}')"))
    return findings


def audit_library(path: str) -> Tuple[List[Finding], int]:
    """Returns (findings, symbol_count)."""
    symbols = load_symbols(path)
    findings: List[Finding] = []
    for sym in symbols:
        findings.extend(audit_symbol(sym))
    return findings, len(symbols)


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

def _fmt_table(lib_path: str, findings: List[Finding]) -> str:
    lines = []
    lines.append(f"--- {lib_path} ---")
    if not findings:
        lines.append("  (clean -- no findings)")
        return "\n".join(lines)
    widths = {
        "sym": max([len("symbol")] + [len(f.symbol) for f in findings]),
        "pin": max([len("pin")] + [len(f.pin_number) for f in findings]),
        "name": max([len("name")] + [len(f.pin_name) for f in findings]),
        "cur": max([len("current")] + [len(f.current_type) for f in findings]),
        "prop": max([len("proposed")] + [len(f.proposed_type or "-") for f in findings]),
        "conf": max([len("conf")] + [len(f.confidence) for f in findings]),
    }
    header = (f"  {'symbol':{widths['sym']}}  {'pin':{widths['pin']}}  "
              f"{'name':{widths['name']}}  {'current':{widths['cur']}}  "
              f"{'proposed':{widths['prop']}}  {'conf':{widths['conf']}}  note")
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    order = {"high": 0, "medium": 1, "low": 2}
    for f in sorted(findings, key=lambda f: (order.get(f.confidence, 9), f.symbol, f.pin_number)):
        lines.append(
            f"  {f.symbol:{widths['sym']}}  {f.pin_number:{widths['pin']}}  "
            f"{f.pin_name:{widths['name']}}  {f.current_type:{widths['cur']}}  "
            f"{(f.proposed_type or '-'):{widths['prop']}}  {f.confidence:{widths['conf']}}  {f.note}"
        )
    return "\n".join(lines)


def _summary_counts(findings: List[Finding]):
    counts = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f.confidence] = counts.get(f.confidence, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_audit(paths: List[str]) -> int:
    any_high = False
    total = {"high": 0, "medium": 0, "low": 0}
    per_lib = []
    for path in paths:
        try:
            findings, nsyms = audit_library(path)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"--- {path} ---")
            print(f"  ERROR parsing: {exc}")
            any_high = True
            continue
        print(_fmt_table(path, findings))
        counts = _summary_counts(findings)
        for k in total:
            total[k] += counts[k]
        per_lib.append((path, nsyms, counts))
        if counts["high"] > 0:
            any_high = True
        print()

    print("=== summary ===")
    for path, nsyms, counts in per_lib:
        print(f"  {path}: {nsyms} symbols -- high={counts['high']} "
              f"medium={counts['medium']} low={counts['low']}")
    print(f"  TOTAL: high={total['high']} medium={total['medium']} low={total['low']}")
    return 1 if any_high else 0


def _all_libs() -> List[str]:
    pattern = os.path.join(ROOT, "**", "*.kicad_sym")
    return sorted(glob.glob(pattern, recursive=True))


def apply_high_confidence_fixes(path: str, review_out: str) -> int:
    """Rewrite ONLY high-confidence proposals on `path`, after writing a
    full before/after review log to `review_out`. Never touches medium/low
    findings, never invents a type where the proposal was flag-only (None).
    This is a plain textual patch of each pin's electrical-type token (the
    token immediately after `(pin `), so structure/formatting/comments and
    every other field are untouched -- reviewable as a normal file diff."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()

    findings, _ = audit_library(path)
    high = [f for f in findings if f.confidence == "high" and f.proposed_type]
    if not high:
        with open(review_out, "w", encoding="utf-8") as fh:
            fh.write(f"# cec_sym_audit --fix review for {path}\n# no high-confidence fixes to apply\n")
        return 0

    # Re-walk the raw text pin-by-pin so we can locate and patch the exact
    # `(pin <TYPE> ` occurrence for each (symbol, pin number) pair, using the
    # same real parser to get authoritative source spans.
    tokens = _tokenize(text)
    # Reparse while tracking source offsets is more machinery than this pass
    # needs; instead do a targeted re-scan: find every `(pin TYPE` opening
    # and its following (name "...") / (number "...") to identify which
    # finding it corresponds to, then splice just the TYPE token.
    pin_open_re = re.compile(r"\(pin\s+(\w+)\s+\w+")
    review_lines = [f"# cec_sym_audit --fix review for {path}", f"# {len(high)} high-confidence change(s)", ""]
    out_chunks = []
    pos = 0
    remaining = {(f.symbol, f.pin_number, f.pin_name): f for f in high}
    current_symbol = None
    symbol_name_re = re.compile(r'\(symbol\s+"([^"]+)"')
    # Walk the file top-to-bottom, tracking the most recent top-level symbol
    # name and patching each pin-open match whose (symbol, number, name)
    # triple is in `remaining`.
    search_pos = 0
    while True:
        m = re.search(r'\(symbol\s+"([^"]+)"|\(pin\s+(\w+)\s+(\w+)', text[search_pos:])
        if not m:
            out_chunks.append(text[search_pos:])
            break
        abs_start = search_pos + m.start()
        out_chunks.append(text[search_pos:abs_start])
        if m.group(1) is not None:
            name = m.group(1)
            if not re.search(r"_\d+_\d+$", name):
                current_symbol = name
            out_chunks.append(m.group(0))
            search_pos = abs_start + len(m.group(0))
            continue
        # a pin-open match; look ahead a bounded window for its name/number
        etype, shape = m.group(2), m.group(3)
        window = text[abs_start:abs_start + 1200]
        name_m = re.search(r'\(name\s+"([^"]*)"', window)
        num_m = re.search(r'\(number\s+"([^"]*)"', window)
        pin_name = name_m.group(1) if name_m else ""
        pin_number = num_m.group(1) if num_m else "?"
        key = (current_symbol, pin_number, pin_name)
        finding = remaining.get(key)
        if finding is not None and finding.current_type == etype:
            new_type = finding.proposed_type
            review_lines.append(
                f"{current_symbol}: pin {pin_number} '{pin_name}': "
                f"{etype} -> {new_type}  ({finding.rule}: {finding.note})"
            )
            out_chunks.append(f"(pin {new_type} {shape}")
            del remaining[key]
        else:
            out_chunks.append(m.group(0))
        search_pos = abs_start + len(m.group(0))

    new_text = "".join(out_chunks)
    with open(review_out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(review_lines) + "\n")

    applied = len(high) - len(remaining)
    if remaining:
        print(f"WARNING: {len(remaining)} high-confidence finding(s) could not be "
              f"located for patching: {list(remaining.keys())}", file=sys.stderr)

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    print(f"Applied {applied} high-confidence fix(es) to {path}; review log: {review_out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="T2 symbol pin-TYPE auditor (docs/schematic-quality-charter.md). "
                    "Report mode by default; --fix is explicit and always writes a review log first.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--audit", nargs="+", metavar="LIB", help="audit one or more .kicad_sym files")
    g.add_argument("--audit-all", action="store_true", help="audit every .kicad_sym under the repo")
    g.add_argument("--fix", metavar="LIB", help="apply ONLY high-confidence fixes to this .kicad_sym")
    ap.add_argument("--review-out", metavar="FILE", help="required with --fix: where to write the before/after review log")
    args = ap.parse_args(argv)

    if args.fix:
        if not args.review_out:
            ap.error("--fix requires --review-out")
        return apply_high_confidence_fixes(args.fix, args.review_out)

    paths = args.audit if args.audit else _all_libs()
    return cmd_audit(paths)


if __name__ == "__main__":
    sys.exit(main())
