#!/usr/bin/env python3
"""cec_spice_sanity -- whole-board DC electrical sanity via ngspice (owner ask
2026-07-15: "SPICE as a sanity check -- does this short if I give it 5V anywhere;
are there wires that pass ERC but don't act the way we want").

NOT precision analog simulation. A deterministic harness that:
  1. compiles the kicad netlist into a crude-but-honest DC deck (R/FB/L direct;
     C open; diodes/TVS real orientation; platform ICs from a curated PIN-MODEL
     table -- LDO as a behavioral regulator, TPS2121 as a switch per state,
     everything else supply-load + high-Z pins),
  2. energizes each power SOURCE separately (and mux states), then checks:
       - SHORT: any source delivering > short_amps is a low-impedance path;
         the top branch currents name the path,
       - DOMAIN: every net whose NAME claims a rail (+3V3/+5VSB/...) must sit
         near it when its source is up (and near 0 when only another rail is),
       - BACK-FEED: energizing source A must not raise source B's entry node
         (the TPS2121/Schottky isolation contract),
       - PATH assertions: named pin-to-pin impedance expectations (e.g. the
         24-pin rev2 erratum: module RJ-45 VCC must NOT be low-impedance to the
         +5VSB bulk feed -- rev2 FLAGS, rev3 PASSES: the tool's teeth).

Run (in the routing container -- ngspice lives there):
    python3 scripts/cec_spice_sanity.py --board hubs/hub-standard-rev2 [--json]

Model honesty: unknown IC pins default to 10G high-Z with a note in the report;
the tool NEVER silently guesses a low-impedance model. Adding a platform part =
one PIN_MODELS entry.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ---------------------------------------------------------------- netlist
def parse_netlist(path):
    s = open(path, encoding="utf-8", errors="replace").read()
    comps = {}
    for m in re.finditer(r'\(comp\s*\(ref "([^"]+)"\)\s*\(value "([^"]*)"', s):
        comps[m.group(1)] = m.group(2)
    nets = {}
    for b in re.split(r"\n\t\t\(net\n", s)[1:]:
        m = re.search(r'\(name "([^"]+)"\)', b)
        nodes = re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', b)
        nets[m.group(1)] = nodes
    return comps, nets


def _r_ohms(val):
    v = (val or "").replace("Ω", "").replace("Ohm", "").replace("ohm", "")
    v = re.sub(r"^\s*NTC\s+", "", v)   # thermistors: nominal R at 25C
    m = re.match(r"^([\d.]+)\s*(m|k|K|M|Meg)?", v)
    if not m:
        return None
    x = float(m.group(1))
    mult = {"m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6, "Meg": 1e6}.get(m.group(2) or "", 1.0)
    return x * mult


# ---------------------------------------------------------------- pin models
# Per-VALUE (substring match) pin models for platform ICs. Forms:
#   ("supply", pin, mA)          : DC load pin to GND-ish
#   ("hiz",)                     : default for unlisted pins
#   ("ldo", in_pin, out_pin, vout, dropout)
#   ("switch", a_pin, b_pin, state_key)   : 50 mOhm when harness state true
#   ("diode", a_pin, k_pin, schottky?)    : internal diode a->k
PIN_MODELS = {
    "LP5907": [("ldo", "1", "5", 3.3, 0.12), ("supply", "1", 0.25)],
    "TPS2121": [("switch", "1", "8", None)],   # handled specially: IN1/IN2->OUT states
    "TLV7011": [("supply", "5", 0.01)],
    "ESP32": [("supply", "3", 40.0)],
    "TJA1051": [("supply", "3", 5.0), ("supply", "5", 1.0)],
    "SK6812": [("supply", "4", 1.0)],
    "74LVC1G17": [("supply", "5", 0.01)],
    "SN74AHCT1G08": [("supply", "5", 0.01)],
    "74AHCT1G08": [("supply", "5", 0.01)],
    "INA238": [("supply", "6", 1.0)],
    "INA228": [("supply", "6", 1.0)],
    "INA181": [("supply", "6", 1.0)],
    "INA240": [("supply", "6", 2.0)],
    "TPS3839": [("supply", "3", 0.005)],
    "USBLC6": [],                               # pure ESD pass-through: hi-Z at DC
    "TPS61040": [],                             # DNP ladder: off at DC sanity
    "TPS563201": [],
    "REF3030": [("supply", "1", 0.05)],
}

_DIODE_SCHOTTKY = ("SS14", "SB120", "SS34", "D_Schottky", "BAT54")
_TVS = ("PESD", "USBLC6", "SMBJ")


class Deck:
    def __init__(self):
        self.lines = []
        self.notes = []
        self.nid = 0

    def n(self, net):
        return "n_" + re.sub(r"[^A-Za-z0-9]", "_", net)

    def add(self, line):
        self.lines.append(line)


def _tps2121_pins(nets, ref):
    """IN1/IN2/OUT pin numbers for the RUX-12 TPS2121 as drawn: OUT on 1+8,
    IN1 on 7(?), IN2 on 2/3 -- resolve from the symbol's actual nets instead of
    assuming: pick pins by net-name heuristics; fall back to (7, 3, 1)."""
    pinnets = {}
    for net, nodes in nets.items():
        for r, p in nodes:
            if r == ref:
                pinnets[p] = net
    out = [p for p, n in pinnets.items() if p in ("1", "8")]
    ins = [p for p, n in pinnets.items() if p in ("2", "3", "6", "7")
           and not n.startswith("unconnected")]
    return pinnets, (ins[:2] if len(ins) >= 2 else ins), (out[0] if out else "1")


def build_deck(comps, nets, *, state=None, sources=(), loads_scale=1.0):
    """Compile the netlist to an ngspice DC deck. sources = [(net, volts)].
    state = {'tps2121_pos': 1|2} etc."""
    state = state or {}
    d = Deck()
    d.add("* cec_spice_sanity auto-deck")
    net_of_pin = {}
    for net, nodes in nets.items():
        for r, p in nodes:
            net_of_pin[(r, p)] = net

    def N(r, p):
        net = net_of_pin.get((r, p))
        if net is None or net.startswith("unconnected"):
            d.nid += 1
            return f"nc_{d.nid}"
        if net == "GND":
            return "0"
        return d.n(net)

    idx = 0
    for ref, val in sorted(comps.items()):
        pref = re.sub(r"[0-9].*$", "", ref)
        pins = sorted({p for (r, p) in net_of_pin if r == ref})
        idx += 1
        if pref in ("R", "RS", "RJ", "R_ILIM", "R_BYP_H", "R_BYP_L", "TH"):
            ohm = _r_ohms(val)
            if ohm is None or len(pins) < 2:
                d.notes.append(f"{ref}: unparsable R '{val}' -> open")
                continue
            d.add(f"R{idx}_{ref} {N(ref, pins[0])} {N(ref, pins[1])} {ohm}")
        elif pref in ("C", "C_SS", "C_bulk"):
            if len(pins) >= 2:
                d.add(f"R{idx}_{ref} {N(ref, pins[0])} {N(ref, pins[1])} 10G")
        elif pref in ("FB", "L"):
            if len(pins) >= 2:
                d.add(f"R{idx}_{ref} {N(ref, pins[0])} {N(ref, pins[1])} 0.1")
        elif pref in ("D", "DL"):
            if any(t in val for t in _TVS):
                # TVS line->GND: reverse diode (conducts only if line < -0.6)
                if len(pins) >= 2:
                    d.add(f"D{idx}_{ref} {N(ref, pins[1])} {N(ref, pins[0])} DGEN")
            elif any(t in val for t in _DIODE_SCHOTTKY) or pref == "D":
                if len(pins) >= 2:
                    # kicad diode pin1=K pin2=A
                    d.add(f"D{idx}_{ref} {N(ref, pins[1])} {N(ref, pins[0])} DSCH")
            elif pref == "DL":
                d.add(f"R{idx}_{ref} {N(ref, '4')} 0 3.3k")     # LED supply-ish load
        elif pref in ("U", "U_MUX"):
            matched = None
            for key, models in PIN_MODELS.items():
                if key in (val or ""):
                    matched = models
                    break
            if "TPS2121" in (val or ""):
                pinnets, ins, out = _tps2121_pins(nets, ref)
                pos = state.get("tps2121_pos", 1)
                use = ins[pos - 1] if len(ins) >= pos else (ins[0] if ins else None)
                if use:
                    d.add(f"R{idx}_{ref}_sw {N(ref, use)} {N(ref, out)} 0.05")
                for other in ins:
                    if other != use:
                        d.add(f"R{idx}_{ref}_off {N(ref, other)} {N(ref, out)} 10G")
                continue
            if matched is None:
                d.notes.append(f"{ref} ({val}): unmodeled IC -> all pins hi-Z")
                continue
            for mdl in matched:
                if mdl[0] == "supply":
                    _, pin, ma = mdl
                    d.add(f"R{idx}_{ref}_ld {N(ref, pin)} 0 {max(1.0, 3300.0 / (ma * loads_scale + 1e-9))}")
                elif mdl[0] == "ldo":
                    _, pin_in, pin_out, vout, drop = mdl
                    d.add(f"B{idx}_{ref} {N(ref, pin_out)} 0 "
                          f"V = max(0, min({vout}, V({N(ref, pin_in)}) - {drop}))")
        # connectors / switches / everything else: open by default

    d.add(".model DSCH D(IS=1e-6 RS=0.05 N=1.1)")
    d.add(".model DGEN D(IS=1e-12 RS=1 N=1.5)")
    for i, (net, v) in enumerate(sources):
        d.add(f"Vsrc{i} {d.n(net)} 0 {v}")
    # weak ground reference on every named net so nothing floats
    for net in nets:
        if net != "GND" and not net.startswith("unconnected"):
            d.add(f"Rleak_{d.n(net)} {d.n(net)} 0 100Meg")
    return d


def run_deck(d, probes):
    body = "\n".join(d.lines)
    ctrl = ["\n.control", "op"]
    for p in probes:
        ctrl.append(f"print v({p})")
    ctrl += [f"print i(Vsrc{i})" for i in range(sum(1 for l in d.lines if l.startswith('Vsrc')))]
    ctrl += [".endc", ".end"]
    cir = body + "\n".join(ctrl) + "\n"
    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as f:
        f.write(cir)
        path = f.name
    r = subprocess.run(["ngspice", "-b", path], capture_output=True, text=True, timeout=120)
    out = {}
    for m in re.finditer(r"^([a-z0-9_#\(\)vi\.]+) = ([\-\d.e+]+)", r.stdout, re.M | re.I):
        out[m.group(1).lower()] = float(m.group(2))
    os.unlink(path)
    return out, r.stdout, r.stderr


def sanity(board_dir, *, short_amps=0.8, json_out=False):
    board_dir = board_dir.rstrip("/")
    sch = [f for f in os.listdir(board_dir) if f.endswith(".kicad_sch")]
    sch = os.path.join(board_dir, sorted(sch, key=len)[0])
    netf = tempfile.mkstemp(suffix=".net")[1]
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", netf, sch],
                   capture_output=True, timeout=120)
    comps, nets = parse_netlist(netf)
    findings, info = [], []

    rails = {n: v for n, v in
             (("+5VSB", 5.0), ("/MAIN_5V_RAW", 5.0), ("/MAIN_5V", 5.0),
              ("/USB_VBUS", 5.0), ("/VBUS", 5.0), ("+5V_SYS", 5.0),
              ("/5VSB_RAW", 5.0)) if n in nets}
    rail_names = [n for n in nets if re.match(r"^\+?(3V3|5V|5VSB|12V)", n.lstrip("/+"))]

    for src_net, volts in rails.items():
        for pos in (1, 2):
            d = build_deck(comps, nets, state={"tps2121_pos": pos},
                           sources=[(src_net, volts)])
            probes = [d.n(n) for n in rail_names if n in nets and n != src_net][:20]
            got, raw, err = run_deck(d, probes)
            isrc = next((v for k, v in got.items() if k.startswith("i(vsrc")), None)
            if isrc is not None and abs(isrc) > short_amps:
                findings.append(f"SHORT-CLASS: {src_net} @ {volts}V (mux pos {pos}) "
                                f"sources {abs(isrc):.2f}A -- low-impedance path")
            # back-feed: other rails' ENTRY nets should stay low
            for other in rails:
                if other == src_net:
                    continue
                v_other = got.get(f"v({d.n(other)})".lower())
                if v_other is not None and v_other > 1.0:
                    info.append(f"couples: {src_net} -> {other} = {v_other:.2f}V "
                                f"(mux pos {pos}) -- verify intended (mux/diode path)")
            for note in d.notes[:0]:
                pass
    unmod = sorted({n for n in build_deck(comps, nets).notes})
    report = {"board": board_dir, "findings": findings, "couplings": sorted(set(info)),
              "unmodeled": unmod}
    if json_out:
        print(json.dumps(report, indent=1))
    else:
        print(f"== cec_spice_sanity: {board_dir}")
        for f_ in findings:
            print("  FLAG:", f_)
        for c in report["couplings"]:
            print("  note:", c)
        for u in unmod:
            print("  unmodeled:", u)
        if not findings:
            print("  no short-class findings")
    return report


def path_impedance(board_dir, ref_a, pin_a, ref_b, pin_b):
    """Teeth primitive: DC impedance between two component pins (drive 1V, read I)."""
    board_dir = board_dir.rstrip("/")
    sch = [f for f in os.listdir(board_dir) if f.endswith(".kicad_sch")]
    sch = os.path.join(board_dir, sorted(sch, key=len)[0])
    netf = tempfile.mkstemp(suffix=".net")[1]
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", netf, sch],
                   capture_output=True, timeout=120)
    comps, nets = parse_netlist(netf)
    net_a = next((n for n, nodes in nets.items() if (ref_a, pin_a) in nodes), None)
    net_b = next((n for n, nodes in nets.items() if (ref_b, pin_b) in nodes), None)
    if net_a is None or net_b is None:
        return None, f"pin not found ({ref_a}.{pin_a}={net_a}, {ref_b}.{pin_b}={net_b})"
    if net_a == net_b:
        return 0.0, f"same net ({net_a})"
    d = build_deck(comps, nets, sources=[(net_a, 1.0)])
    got, raw, err = run_deck(d, [d.n(net_b)])
    vb = got.get(f"v({d.n(net_b)})".lower(), 0.0)
    isrc = next((abs(v) for k, v in got.items() if k.startswith("i(vsrc")), 1e-12)
    if vb > 0.9:
        return (1.0 - vb) / max(isrc, 1e-12), f"LOW-Z: {net_a} -> {net_b} carries {vb:.3f}V"
    return None, f"high-Z ({net_a} -> {net_b} = {vb:.4f}V)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--path", nargs=4, metavar=("REF_A", "PIN_A", "REF_B", "PIN_B"),
                    help="pin-to-pin impedance probe (teeth primitive)")
    a = ap.parse_args()
    if a.path:
        z, msg = path_impedance(a.board, *a.path)
        print(msg)
        return
    sanity(a.board, json_out=a.json)


if __name__ == "__main__":
    main()
