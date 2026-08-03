#!/usr/bin/env python3
"""cec_spice_sanity -- bounded whole-board DC topology sanity via ngspice.

Owner ask
2026-07-15: "SPICE as a sanity check -- does this short if I give it 5V anywhere;
are there wires that pass ERC but don't act the way we want").

This is not precision analog or functional simulation. It is a deterministic
harness that:
  1. compiles the KiCad netlist into a conservative normal-state DC deck,
  2. derives physical source rails from connector pins, injects each source
     separately in every independent TPS2121 position combination, and checks
     source current for short-class paths,
  3. injects all recognized rails together and checks for a source sinking
     current through a non-isolating path,
  4. reports single-source rail coupling as diagnostic information, and
  5. exposes an explicit --path pin-to-pin impedance probe.

The normal sanity run does not prove rail-domain correctness, transient
behavior, protection thresholds, analog accuracy, firmware behavior, or signal
integrity. Those limitations and every unmodeled conduction component are
included in the report. --require-signoff fails closed unless the bounded DC
scope has no findings and no coverage gaps.

Run (in the routing container -- ngspice lives there):
    python3 scripts/cec_spice_sanity.py --board beta/hub-standard-rev2 [--json]

Model honesty: known signal ICs use supply-load-only models with signal pins
high impedance. Unknown ICs, transistors, and switches are explicit coverage
gaps instead of silent opens. Adding a platform part requires a reviewed
PIN_MODELS entry or a dedicated topology model.
"""
import argparse
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import cec_toolchain
import cec_sch_gates

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _ngspice_executable():
    """Select a batch-safe ngspice executable.

    The official Windows bundle ships both ``ngspice.exe`` (GUI) and
    ``ngspice_con.exe`` (console).  Resolving the generic name on Windows can
    therefore open one GUI window per deck.  An explicit override always wins;
    otherwise prefer the console build when it is available.
    """
    resolved = cec_toolchain.ngspice_console()
    if resolved:
        return resolved
    # Never fall back to ngspice.exe on Windows.  That executable is the GUI
    # frontend in the official bundle and one invocation per deck can leave a
    # stack of persistent "Parse" windows.
    return "ngspice_con.exe" if os.name == "nt" else "ngspice"


NGSPICE = _ngspice_executable()

# ---------------------------------------------------------------- netlist
def parse_netlist(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        s = handle.read()
    comps = {}
    for m in re.finditer(r'\(comp\s*\(ref "([^"]+)"\)\s*\(value "([^"]*)"', s):
        comps[m.group(1)] = m.group(2)
    nets = {}
    for b in re.split(r"\n\t\t\(net\n", s)[1:]:
        m = re.search(r'\(name "([^"]+)"\)', b)
        nodes = re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', b)
        nets[m.group(1)] = nodes
    return comps, nets


def _filter_assembly(comps, nets, schematic_inventory):
    """Remove parts that are absent from the default physical assembly."""
    excluded = {
        ref for ref, rec in schematic_inventory.items()
        if rec.get("dnp") or not rec.get("on_board", True)
    }
    if not excluded:
        return comps, nets
    filtered_comps = {ref: val for ref, val in comps.items()
                      if ref not in excluded}
    filtered_nets = {
        net: [(ref, pin) for ref, pin in nodes if ref not in excluded]
        for net, nodes in nets.items()
    }
    return filtered_comps, filtered_nets


def _project_netlist(board_dir):
    """Export and parse the KiCad project root, never a hierarchy leaf."""
    sch = cec_toolchain.find_root_sch(board_dir)
    if not sch:
        raise RuntimeError("no root .kicad_sch found in %s" % board_dir)
    cli = cec_toolchain.require_kicad_cli("SPICE netlist export")
    fd, netf = tempfile.mkstemp(prefix="cec_spice_", suffix=".net")
    os.close(fd)
    os.unlink(netf)
    try:
        run = subprocess.run(
            [cli, "sch", "export", "netlist", "-o", netf, sch],
            capture_output=True, text=True, timeout=120)
        if run.returncode != 0:
            detail = (run.stderr or run.stdout or "no export diagnostic").strip()
            raise RuntimeError(
                "KiCad netlist export exited %d for %s: %s" %
                (run.returncode, sch, detail[-800:]))
        if not os.path.isfile(netf) or os.path.getsize(netf) == 0:
            raise RuntimeError("KiCad netlist export produced no data for %s" % sch)
        comps, nets = parse_netlist(netf)
        comps, nets = _filter_assembly(
            comps, nets, cec_sch_gates.inventory(sch))
        return sch, comps, nets
    finally:
        try:
            os.unlink(netf)
        except OSError:
            pass


def _r_ohms(val):
    # Exact selected-part aliases whose human-readable values are not resistor
    # notation. MF72-5D-20 is specified as 5 ohm nominal at 25 C. This is only
    # its cold resistance, not its heated steady-state resistance.
    aliases = {
        "MF72-5D-20": 5.0,
    }
    exact = (val or "").strip().upper()
    if exact in aliases:
        return aliases[exact]
    v = (val or "").replace("Ω", "").replace("Ω", "")
    v = re.sub(r"ohms?", "", v, flags=re.I)
    v = re.sub(r"^\s*NTC\s+", "", v)   # thermistors: nominal R at 25C
    v = v.strip()
    # IEC/RKM notation uses the multiplier letter as the decimal separator:
    # 0R002 = 2 mOhm, 4R7 = 4.7 Ohm, 1k2 = 1.2 kOhm.
    m = re.match(r"^(\d*)([RrKkMm])(\d+)", v)
    if m:
        whole = m.group(1) or "0"
        x = float(whole + "." + m.group(3))
        mult = {"R": 1.0, "r": 1.0, "k": 1e3, "K": 1e3,
                "m": 1e-3, "M": 1e6}[m.group(2)]
        return x * mult
    m = re.match(r"^([\d.]+)\s*(Meg|m|k|K|M)?", v)
    if not m:
        return None
    x = float(m.group(1))
    mult = {"m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6,
            "Meg": 1e6}.get(m.group(2) or "", 1.0)
    return x * mult


# ---------------------------------------------------------------- pin models
# Per-VALUE (substring match) pin models for platform ICs. Forms:
#   ("supply", pin)              : weak numerical load at a verified supply pin
#   ("hiz",)                     : default for unlisted pins
#   ("ldo", in_pin, out_pin, vout, dropout)
#   ("switch", a_pin, b_pin, state_key)   : selected normal-state path
#   ("diode", a_pin, k_pin, schottky?)    : internal diode a->k
PIN_MODELS = {
    "LP5907": [("ldo", "1", "5", 3.3, 0.12), ("supply", "1")],
    "TLV75533PDRVR": [("ldo", "6", "1", 3.3, 0.238), ("supply", "6")],
    "TLV75533PDBVR": [("ldo", "1", "5", 3.3, 0.238), ("supply", "1")],
    # TLV62569 is handled specially below: its output is calculated from the
    # actual feedback divider instead of hard-coding one board's setpoint.
    "TLV62569": [],
    "TPS2121": [("switch", "1", "8", None)],   # handled specially: IN1/IN2->OUT states
    "TLV7011": [("supply", "5")],
    "ESP32-S3-WROOM-1": [("supply", "2")],
    "ESP32": [("supply", "3")],
    "TJA1051": [("supply", "3"), ("supply", "5")],
    "74AHCT244": [("supply", "20")],
    "SK6812": [("supply", "4")],
    "74LVC1G17": [("supply", "5")],
    "SN74AHCT1G08": [("supply", "5")],
    "74AHCT1G08": [("supply", "5")],
    "INA238": [("supply", "6")],
    "INA228": [("supply", "6")],
    "INA181": [("supply", "6")],
    "INA180": [("supply", "5")],
    # Every current BETA INA240 selection is INA240A3DR in SOIC-8 (D), where
    # VS is pin 6. The TSSOP (PW) variant instead uses pin 5.
    "INA240A3": [("supply", "6")],
    "TPS3839": [("supply", "3")],
    "USBLC6": [],                               # pure ESD pass-through: hi-Z at DC
    "TPS61040": [],                             # DNP ladder: off at DC sanity
    "TPS563201": [],
    "REF3030": [("supply", "1")],
}

_DIODE_SCHOTTKY = ("SS14", "SB120", "SS34", "D_Schottky", "BAT54")
_TVS = ("PESD", "USBLC6", "SMAJ", "SMBJ", "SMCJ", "SMF")


class Deck:
    def __init__(self):
        self.lines = []
        self.notes = []
        self.coverage_gaps = []
        self.partial_models = []
        self.model_classes = {}
        self.nid = 0
        self.aliases = {}

    def n(self, net):
        net = self.aliases.get(net, net)
        if net == "GND":
            return "0"
        return "n_" + re.sub(r"[^A-Za-z0-9]", "_", net)

    def add(self, line):
        self.lines.append(line)

    def modeled(self, ref, model_class, detail=None):
        self.model_classes[ref] = model_class
        if detail:
            self.partial_models.append(f"{ref}: {detail}")

    def gap(self, ref, detail):
        self.model_classes[ref] = "coverage-gap"
        self.coverage_gaps.append(f"{ref}: {detail}")


def _tps2121_pins(nets, ref):
    """Return the verified TPS2121 RUX-12 power pins.

    The selected package assigns IN1=7, IN2=2, and OUT=1/8. Pin 3 is CP2,
    not a second IN2 pin. Keeping this package mapping explicit prevents the
    state-2 model from accidentally switching CP2 onto OUT.
    """
    pinnets = {}
    for net, nodes in nets.items():
        for r, p in nodes:
            if r == ref:
                pinnets[p] = net
    ins = [pin for pin in ("7", "2")
           if pin in pinnets and not pinnets[pin].startswith("unconnected")]
    out = next((pin for pin in ("1", "8") if pin in pinnets), "1")
    return pinnets, ins, out


def _tps2121_states(comps):
    """Enumerate every independent input selection for fitted TPS2121 parts."""
    refs = sorted(ref for ref, value in comps.items() if "TPS2121" in (value or ""))
    if not refs:
        return [({}, "no mux")]
    states = []
    for positions in itertools.product((1, 2), repeat=len(refs)):
        selected = dict(zip(refs, positions))
        state = {"tps2121_positions": selected}
        label = ", ".join(f"{ref}=IN{selected[ref]}" for ref in refs)
        states.append((state, label))
    return states


def _coupling_probe_nets(rails, rail_names, source_net):
    """Probe every external rail plus recognized internal power rails.

    External connector rails do not necessarily begin with a voltage token.
    For example, MAIN_5V_RAW and KVM_5V_RAW must not disappear merely because
    the older internal-rail regular expression does not match their prefixes.
    """
    return [
        net for net in dict.fromkeys([*rails, *rail_names])
        if net != source_net
    ]


def _tps2121_control_findings(comps, nets):
    """Fail before simulation when the platform's fixed-priority straps are wrong."""
    findings = []
    for ref, value in sorted(comps.items()):
        if "TPS2121" not in (value or ""):
            continue
        pins, _ins, _out = _tps2121_pins(nets, ref)
        if pins.get("1") != pins.get("8"):
            findings.append(
                f"TPS2121 CONTROL: {ref} OUT pins 1/8 differ "
                f"({pins.get('1')!r} vs {pins.get('8')!r})")
        if pins.get("3") != "GND":
            findings.append(
                f"TPS2121 CONTROL: {ref} CP2 pin 3 is {pins.get('3')!r}, "
                "not GND; fixed IN1 priority is not selected")
        if pins.get("4") != "GND":
            findings.append(
                f"TPS2121 CONTROL: {ref} OV2 pin 4 is {pins.get('4')!r}, not GND")
        if (not pins.get("6") or pins["6"].startswith("unconnected") or
                pins["6"] == "GND"):
            findings.append(
                f"TPS2121 CONTROL: {ref} PR1 pin 6 is {pins.get('6')!r}; "
                "the fixed-priority threshold is absent")
    return findings


def _net_for_pin(nets, ref, pin):
    return next((net for net, nodes in nets.items() if (ref, pin) in nodes), None)


def _external_source_rails(comps, nets):
    """Return verified external input rails that do not have reusable labels."""
    rails = {}
    for ref, value in comps.items():
        if "SATA_PWR_15P" in (value or ""):
            net = _net_for_pin(nets, ref, "7")
            if net and not net.startswith("unconnected"):
                rails[net] = 5.0
    return rails


def _connector_source_rails(comps, nets):
    """Derive external source nets from reviewed connector pin assignments."""
    pin_net = {
        (ref, pin): net
        for net, nodes in nets.items()
        for ref, pin in nodes
    }
    rails = {}

    def add(ref, pin, voltage):
        net = pin_net.get((ref, str(pin)))
        if net and net != "GND" and not net.startswith("unconnected"):
            rails[net] = float(voltage)

    def add_named_net(ref, pin):
        net = pin_net.get((ref, str(pin)))
        if not net:
            return
        upper = net.upper()
        if "-12V" in upper or "NEG12V" in upper:
            add(ref, pin, -12.0)
        elif "12V" in upper:
            add(ref, pin, 12.0)
        elif "3V3" in upper:
            add(ref, pin, 3.3)
        elif "5V" in upper:
            add(ref, pin, 5.0)

    for ref, value in comps.items():
        upper = (value or "").upper()
        if "USB-C" in upper:
            for pin in ("A4", "A9", "B4", "B9"):
                add(ref, pin, 5.0)
        if "SATA_PWR_15P" in upper:
            add(ref, "7", 5.0)
        if upper == "TO-HUB":
            add(ref, "1", 5.0)
        if upper == "PWR_IN":
            add(ref, "1", 5.0)
            add(ref, "3", 5.0)
        if upper == "CEC_NANOKVM_AUX_5P":
            add(ref, "1", 5.0)
        if upper == "TO-24PIN-STACK-PWR":
            for pin in ("1", "3", "5"):
                add(ref, pin, 5.0)
        if "12V-2X6 IN" in upper:
            for pin in map(str, range(1, 7)):
                add(ref, pin, 12.0)
        if re.fullmatch(r"C\d+ PSU", upper):
            for pin in map(str, range(1, 9)):
                add(ref, pin, 12.0)
        if upper == "ATX-24 PSU":
            for pin in ("1", "2", "12", "13"):
                add(ref, pin, 3.3)
            for pin in ("4", "6", "21", "22", "23"):
                add(ref, pin, 5.0)
            add(ref, "9", 5.0)
            for pin in ("10", "11"):
                add(ref, pin, 12.0)
            add(ref, "14", -12.0)
        if upper == "TE 63951-1":
            add_named_net(ref, "1")
        if "SIGNAL STUB" in upper:
            add_named_net(ref, "1")
    return rails


def _registered_dc_fault_cases(comps, nets):
    """Return explicit fault cases with algorithmic, not hardware, limits."""
    cases = []
    sata_refs = [ref for ref, value in comps.items()
                 if "SATA_PWR_15P" in (value or "")]
    ntc_refs = [ref for ref, value in comps.items()
                if "MF72" in (value or "")]
    if sata_refs and ntc_refs:
        source_net = _net_for_pin(nets, sata_refs[0], "7")
        protected_net = _net_for_pin(nets, ntc_refs[0], "2")
        if source_net and protected_net:
            cases.append({
                "name": "argb-sata-reverse-input",
                "source_net": source_net,
                "source_v": -5.0,
                "probe_net": protected_net,
                # A wrong-way PMOS body diode makes the protected rail follow
                # nearly the full -5 V input. -1 V is only a topology
                # discriminator and is not presented as a component rating.
                "minimum_probe_v": -1.0,
            })
    return cases


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

    # Collapse ideal DC connections instead of inventing a resistance for
    # components whose selected value is exactly 0R. USBLC6-2SC6 pins 1-6
    # and 3-4 are physical flow-through pairs, so they are topology shorts in
    # a normal-state DC deck while their clamp branches remain off.
    parent = {net: net for net in nets}

    def find(net):
        while parent[net] != net:
            parent[net] = parent[parent[net]]
            net = parent[net]
        return net

    def union(a, b):
        if a not in parent or b not in parent:
            return
        ra, rb = find(a), find(b)
        if ra != rb:
            if "GND" in (ra, rb):
                parent[rb if ra == "GND" else ra] = "GND"
            else:
                parent[max(ra, rb)] = min(ra, rb)

    for ref, val in comps.items():
        pref = re.sub(r"[0-9].*$", "", ref)
        pins = sorted(p for r, p in net_of_pin if r == ref)
        if ((pref.startswith("R") or pref in ("FB", "L"))
                and _r_ohms(val) == 0 and len(pins) >= 2):
            union(net_of_pin[(ref, pins[0])], net_of_pin[(ref, pins[1])])
        if "USBLC6-2SC6" in (val or ""):
            for a, b in (("1", "6"), ("3", "4")):
                if (ref, a) in net_of_pin and (ref, b) in net_of_pin:
                    union(net_of_pin[(ref, a)], net_of_pin[(ref, b)])
        if "TPS2121" in (val or ""):
            if (ref, "1") in net_of_pin and (ref, "8") in net_of_pin:
                union(net_of_pin[(ref, "1")], net_of_pin[(ref, "8")])
    d.aliases = {net: find(net) for net in nets}

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
        if pref == "F":
            # The 1 mOhm link is a numerical closed-state topology element,
            # not a claimed fuse/PTC DCR or selected hardware value.
            if len(pins) >= 2:
                d.add(f"R{idx}_{ref} {N(ref, pins[0])} {N(ref, pins[1])} 1m")
                d.modeled(ref, "closed-state-link",
                          "fuse/PTC trip curve and physical DCR are not modeled")
            else:
                d.gap(ref, "fuse/PTC has fewer than two connected pins")
            continue
        if pref.startswith("R") or pref in ("TH", "RT"):
            ohm = _r_ohms(val)
            if ohm is None or len(pins) < 2:
                detail = f"unparsable resistor/thermistor value {val!r}; left open"
                d.notes.append(f"{ref}: {detail}")
                d.gap(ref, detail)
                continue
            if ohm == 0:
                d.modeled(ref, "ideal-dc-link")
                continue
            d.add(f"R{idx}_{ref} {N(ref, pins[0])} {N(ref, pins[1])} {ohm}")
            if (val or "").strip().upper() == "MF72-5D-20":
                d.modeled(
                    ref,
                    "cold-ntc-resistor",
                    "5 ohm R25 topology value only; self-heating, inrush, and residual resistance are not modeled",
                )
            else:
                d.modeled(ref, "resistor")
        elif pref.startswith("C"):
            if len(pins) >= 2:
                d.add(f"R{idx}_{ref} {N(ref, pins[0])} {N(ref, pins[1])} 10G")
            d.modeled(ref, "dc-open-capacitor")
        elif pref in ("FB", "L"):
            if len(pins) >= 2:
                if _r_ohms(val) == 0:
                    d.modeled(ref, "ideal-dc-link")
                    continue
                d.add(f"R{idx}_{ref} {N(ref, pins[0])} {N(ref, pins[1])} 1m")
                d.modeled(ref, "closed-state-link",
                          "magnetic impedance and physical DCR are not modeled")
            else:
                d.gap(ref, "magnetic part has fewer than two connected pins")
        elif pref.startswith("D"):
            if "USBLC6-2SC6" in (val or ""):
                # Flow-through pairs were collapsed above. Its rail clamps
                # are off in this normal-state DC topology model.
                d.modeled(ref, "esd-flow-through",
                          "ESD clamp breakdown and transient response are not modeled")
                continue
            if "BAT54S" in (val or ""):
                # BAT54S dual-series pinout: 1=A1, 3=K1/A2, 2=K2.
                # The platform uses pin 1=GND, pin 3=signal, pin 2=+5 V,
                # producing lower and upper Schottky clamps. Treating this
                # three-pin part as a generic two-pin diode shorts +5 V to GND.
                if all((ref, pin) in net_of_pin for pin in ("1", "2", "3")):
                    d.add(f"D{idx}_{ref}_lo {N(ref, '1')} {N(ref, '3')} DSCH")
                    d.add(f"D{idx}_{ref}_hi {N(ref, '3')} {N(ref, '2')} DSCH")
                    d.modeled(
                        ref,
                        "dual-series-schottky-clamp",
                        "selected diode forward curve, leakage, and transient clamp behavior are not modeled",
                    )
                else:
                    d.gap(ref, "BAT54S is missing one or more of pins 1, 2, and 3")
            elif any(t in val for t in _TVS):
                # TVS line-to-ground orientation only. The generic diode has
                # no avalanche model, so this cannot validate clamp voltage.
                if len(pins) >= 2:
                    d.add(f"D{idx}_{ref} {N(ref, pins[1])} {N(ref, pins[0])} DGEN")
                d.modeled(ref, "tvs-orientation-only",
                          "TVS avalanche voltage and dynamic clamp are not modeled")
            elif any(t in val for t in _DIODE_SCHOTTKY) or pref == "D":
                if len(pins) >= 2:
                    # KiCad diode pin 1=K, pin 2=A.
                    d.add(f"D{idx}_{ref} {N(ref, pins[1])} {N(ref, pins[0])} DSCH")
                d.modeled(ref, "generic-diode",
                          "selected diode forward curve and reverse leakage are not modeled")
            elif pref == "DL":
                d.add(f"R{idx}_{ref} {N(ref, '4')} 0 3.3k")
                d.modeled(ref, "supply-load-only",
                          "addressable LED logic and output behavior are not modeled")
            else:
                d.gap(ref, f"diode-like part {val!r} has no DC model")
        elif pref in ("U", "U_MUX"):
            matched = None
            for key, models in PIN_MODELS.items():
                if key in (val or ""):
                    matched = models
                    break
            if "TPS2121" in (val or ""):
                _pinnets, ins, out = _tps2121_pins(nets, ref)
                positions = state.get("tps2121_positions", {})
                pos = positions.get(ref, state.get("tps2121_pos", 1))
                use = ins[pos - 1] if len(ins) >= pos else (ins[0] if ins else None)
                if use:
                    # TPS2121 has always-on fast reverse-current blocking. A
                    # bidirectional resistor here falsely back-fed an input
                    # whenever a downstream or mezzanine rail powered OUT.
                    # The directed near-ideal diode models only the steady DC
                    # topology. It deliberately does not claim the silicon's
                    # 0.2 A to 2 A detection threshold or 10 us response time.
                    d.add(
                        f"D{idx}_{ref}_sw {N(ref, use)} {N(ref, out)} "
                        "CEC_TPS2121_RCB"
                    )
                for other in ins:
                    if other != use:
                        d.add(f"R{idx}_{ref}_off {N(ref, other)} {N(ref, out)} 10G")
                d.modeled(
                    ref,
                    "two-position-rcb-power-mux",
                    "steady-state reverse-current blocking is directional; priority dynamics, OV, current limit, soft-start, RON, RCB threshold, and RCB response time are not modeled",
                )
                continue
            if "TLV62569" in (val or ""):
                fb_net = net_of_pin.get((ref, "5"))
                divider = []
                for rref, rval in comps.items():
                    if not rref.startswith("R"):
                        continue
                    rpins = [(pin, net) for (rr, pin), net in net_of_pin.items()
                             if rr == rref]
                    if fb_net not in [net for _pin, net in rpins]:
                        continue
                    other = [net for _pin, net in rpins if net != fb_net]
                    if len(other) == 1:
                        divider.append((other[0], _r_ohms(rval)))
                r_bottom = next((r for net, r in divider if net == "GND"), None)
                r_top = next((r for net, r in divider if net != "GND"), None)
                if not r_top or not r_bottom:
                    d.gap(ref, "TLV62569 feedback divider could not be resolved")
                    continue
                vout = 0.6 * (1.0 + r_top / r_bottom)
                d.add(f"B{idx}_{ref}_buck {N(ref, '3')} 0 "
                      f"V = max(0, min({vout:.9g}, V({N(ref, '4')})))")
                d.add(f"R{idx}_{ref}_vinload {N(ref, '4')} 0 1Meg")
                d.modeled(
                    ref, "behavioral-buck-setpoint",
                    "feedback setpoint and DC input ceiling are modeled; switching ripple, "
                    "efficiency, current limit, compensation, startup, and load transient are not modeled",
                )
                continue
            if matched is None:
                detail = f"unmodeled IC {val!r}; all pins left high impedance"
                d.notes.append(f"{ref}: {detail}")
                d.gap(ref, detail)
                continue
            if "LP5907" in (val or "") or "TLV75533" in (val or ""):
                d.modeled(ref, "behavioral-ldo",
                          "EN, current limit, dropout curve, and input/output current transfer are not modeled")
            elif "USBLC6" not in (val or ""):
                d.modeled(ref, "supply-load-only",
                          "signal and protection behavior are not modeled")
            for mdl_idx, mdl in enumerate(matched):
                if mdl[0] == "supply":
                    _, pin = mdl
                    # A weak numerical load prevents a totally floating supply
                    # without fabricating a firmware/mode-dependent IC current.
                    d.add(f"R{idx}_{ref}_ld{mdl_idx} {N(ref, pin)} 0 1Meg")
                elif mdl[0] == "ldo":
                    _, pin_in, pin_out, vout, drop = mdl
                    d.add(f"B{idx}_{ref}_{mdl_idx} {N(ref, pin_out)} 0 "
                          f"V = max(0, min({vout}, V({N(ref, pin_in)}) - {drop}))")
        elif pref.startswith("Q"):
            upper = (val or "").upper()
            if "AO3400A" in upper and all((ref, pin) in net_of_pin for pin in ("1", "2", "3")):
                # AO3400A SOT-23: 1=G, 2=S, 3=D. The switch closes only above
                # the selected datasheet's 2.5 V guaranteed RDS(on) test point.
                # Ron=1m is a numerical topology link, not a claimed device
                # resistance. The intrinsic diode is S -> D.
                d.add(
                    f"S{idx}_{ref} {N(ref, '3')} {N(ref, '2')} "
                    f"{N(ref, '1')} {N(ref, '2')} CEC_AO3400_TOPO"
                )
                d.add(f"D{idx}_{ref}_body {N(ref, '2')} {N(ref, '3')} DSCH")
                d.modeled(
                    ref,
                    "gate-controlled-nmos-topology",
                    "gate state and body-diode direction are modeled; 1 mOhm Ron is numerical and device switching, dissipation, and SOA are not modeled",
                )
            elif "AO4407A" in upper and all((ref, pin) in net_of_pin for pin in ("1", "4", "5")):
                # AO4407A SO-8: 1..3=S, 4=G, 5..8=D. Control is V(S)-V(G),
                # so the topology switch closes once VSG exceeds the selected
                # datasheet's 3.0 V maximum threshold. That proves conduction
                # state only; it does not claim guaranteed RDS(on) at 5 V.
                # The intrinsic diode is D -> S.
                d.add(
                    f"S{idx}_{ref} {N(ref, '5')} {N(ref, '1')} "
                    f"{N(ref, '1')} {N(ref, '4')} CEC_AO4407_TOPO"
                )
                d.add(f"D{idx}_{ref}_body {N(ref, '5')} {N(ref, '1')} DSCH")
                d.modeled(
                    ref,
                    "gate-controlled-pmos-topology",
                    "gate state and body-diode direction are modeled; 1 mOhm Ron is numerical and 5 V RDS(on), dissipation, and SOA are not proven",
                )
            else:
                d.gap(ref, f"transistor {val!r} has no state/model; pins left open")
        elif pref.startswith("SW"):
            control_name = f"{ref} {val}".upper()
            if any(token in control_name for token in ("BOOT", "RESET", "RST")):
                d.modeled(ref, "normally-open-control-switch",
                          "normal open state is modeled; pressed state is not exercised")
            else:
                d.gap(ref, f"switch {val!r} has no selected state; contacts left open")
        elif (pref.startswith("J") or pref in ("TB", "PWR", "TP", "H", "MH")):
            d.modeled(ref, "external-or-annotation")
        elif pins:
            d.gap(ref, f"component class {pref!r} value {val!r} is not modeled")

    d.add(".model DSCH D(IS=1e-6 RS=0.05 N=1.1)")
    d.add(".model DGEN D(IS=1e-12 RS=1 N=1.5)")
    d.add(".model CEC_TPS2121_RCB D(IS=1e-15 RS=1m N=0.01)")
    d.add(".model CEC_AO3400_TOPO SW(Ron=1m Roff=10G Vt=2.5 Vh=0)")
    d.add(".model CEC_AO4407_TOPO SW(Ron=1m Roff=10G Vt=3.0 Vh=0)")
    for i, (net, v) in enumerate(sources):
        d.add(f"Vsrc{i} {d.n(net)} 0 {v}")
    # weak ground reference on every named net so nothing floats
    leak_nodes = set()
    for net in nets:
        node = d.n(net)
        if net != "GND" and not net.startswith("unconnected") and node not in leak_nodes:
            d.add(f"Rleak_{node} {node} 0 100Meg")
            leak_nodes.add(node)
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
    try:
        run_options = {}
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            run_options["creationflags"] = subprocess.CREATE_NO_WINDOW
        run_cwd = cec_toolchain.ngspice_cwd(NGSPICE)
        if run_cwd:
            run_options["cwd"] = run_cwd
        run_options["env"] = cec_toolchain.ngspice_batch_env()
        r = subprocess.run([NGSPICE, "-n", "-b", path], capture_output=True, text=True,
                           timeout=120, **run_options)
        if r.returncode != 0:
            detail = (r.stderr or r.stdout or "no simulator diagnostics").strip()
            raise RuntimeError(f"ngspice exited {r.returncode}: {detail}")
        out = {}
        for m in re.finditer(r"^([a-z0-9_#\(\)vi\.]+) = ([\-\d.e+]+)",
                             r.stdout, re.M | re.I):
            out[m.group(1).lower()] = float(m.group(2))
        if (probes or any(line.startswith("Vsrc") for line in d.lines)) and not out:
            raise RuntimeError(
                "ngspice exited successfully but returned no requested values")
        return out, r.stdout, r.stderr
    finally:
        os.unlink(path)


def _coverage_summary(deck, findings):
    gaps = sorted(set(deck.coverage_gaps))
    partial = sorted(set(deck.partial_models))
    modeled_checks_passed = not findings
    return {
        "component_count": len(deck.model_classes),
        "coverage_gaps": gaps,
        "partial_models": partial,
        "modeled_dc_checks_passed": modeled_checks_passed,
        "signoff_scope": (
            "normal-state DC short, source-fight, and rail-coupling topology plus "
            "registered DC fault-topology cases only"
        ),
        "signoff_ready": modeled_checks_passed and not gaps,
        "functional_signoff_ready": False,
        "limitations": [
            "no transient, startup, fault-energy, thermal, or signal-integrity simulation",
            "no firmware, digital protocol, analog-accuracy, or protection-threshold proof",
            "single-source rail coupling is diagnostic information, not an automatic failure",
        ],
    }


def sanity(board_dir, *, short_amps=0.8, json_out=False):
    board_dir = board_dir.rstrip("/")
    sch, comps, nets = _project_netlist(board_dir)
    findings = _tps2121_control_findings(comps, nets)
    info = []

    rails = _connector_source_rails(comps, nets)
    if not rails:
        raise RuntimeError(
            "root schematic %s exported no recognized source rails from connector pins" % sch)
    rail_names = [n for n in nets if re.match(r"^\+?(3V3|5V|5VSB|12V)", n.lstrip("/+"))]
    mux_states = _tps2121_states(comps)

    for src_net, volts in rails.items():
        for state, state_label in mux_states:
            d = build_deck(comps, nets, state=state,
                           sources=[(src_net, volts)])
            probe_nets = _coupling_probe_nets(rails, rail_names, src_net)
            probes = [d.n(net) for net in probe_nets]
            got, raw, err = run_deck(d, probes)
            isrc = next((v for k, v in got.items() if k.startswith("i(vsrc")), None)
            if isrc is not None and abs(isrc) > short_amps:
                findings.append(f"SHORT-CLASS: {src_net} @ {volts}V ({state_label}) "
                                f"sources {abs(isrc):.2f}A -- low-impedance path")
            # back-feed: other rails' ENTRY nets should stay low
            for other in rails:
                if other == src_net:
                    continue
                v_other = got.get(f"v({d.n(other)})".lower())
                if v_other is not None and v_other > 1.0:
                    info.append(f"couples: {src_net} -> {other} = {v_other:.2f}V "
                                f"({state_label}) -- verify intended (mux/diode path)")
    # COEXISTENCE LEG (owner GO 2026-07-15, #2: mezzanine + cable feeds): energize
    # EVERY rail simultaneously at nominal. A source that SINKS current is being
    # back-fed -- two supplies fighting through a path that should isolate them
    # (mux/ORing contract). Same-net parallel feeds (hub J6 + J_PWR via the mux)
    # pass when the isolation holds; any topology change that breaks it flags here.
    if len(rails) >= 2:
        for state, state_label in mux_states:
            d = build_deck(comps, nets, state=state,
                           sources=list(rails.items()))
            got, raw, err = run_deck(d, [])
            for i, (net, v) in enumerate(rails.items()):
                isrc = got.get(f"i(vsrc{i})")
                if isrc is not None and v * isrc > abs(v) * 0.05:
                    findings.append(
                        f"BACK-FED SOURCE: {net} SINKS {isrc:.3f}A with all rails up "
                        f"({state_label}) -- supplies fighting through a non-isolating path")
                elif isrc is not None and abs(isrc) > short_amps:
                    findings.append(
                        f"SHORT-CLASS (coexist): {net} sources {abs(isrc):.2f}A "
                        f"with all rails up ({state_label})")
    fault_checks = []
    for case in _registered_dc_fault_cases(comps, nets):
        d = build_deck(
            comps, nets,
            sources=[(case["source_net"], case["source_v"])],
        )
        probe = d.n(case["probe_net"])
        got, _raw, _err = run_deck(d, [probe])
        measured = got.get(f"v({probe})".lower())
        passed = measured is not None and measured >= case["minimum_probe_v"]
        fault_checks.append({
            "name": case["name"],
            "source_net": case["source_net"],
            "source_v": case["source_v"],
            "probe_net": case["probe_net"],
            "probe_v": measured,
            "passed": passed,
            "limit_note": "-1 V is a topology discriminator, not a hardware rating",
        })
        if not passed:
            findings.append(
                f"REVERSE-POLARITY TOPOLOGY: {case['source_net']} at "
                f"{case['source_v']:.1f}V drives {case['probe_net']} to "
                f"{measured!r}V; verify PMOS body-diode orientation"
            )
    coverage_deck = build_deck(comps, nets)
    coverage = _coverage_summary(coverage_deck, findings)
    unmod = coverage["coverage_gaps"]
    report = {"board": board_dir, "findings": findings,
              "source_rails": rails, "mux_state_count": len(mux_states),
              "couplings": sorted(set(info)),
              "fault_checks": fault_checks,
              "unmodeled": unmod, "coverage": coverage}
    if json_out:
        print(json.dumps(report, indent=1))
    else:
        print(f"== cec_spice_sanity: {board_dir}")
        for f_ in findings:
            print("  FLAG:", f_)
        for c in report["couplings"]:
            print("  note:", c)
        for check in fault_checks:
            status = "passed" if check["passed"] else "FAILED"
            probe_text = ("missing" if check["probe_v"] is None
                          else f"{check['probe_v']:.3f}V")
            print(f"  fault topology {status}: {check['name']} "
                  f"({check['probe_net']}={probe_text})")
        for u in unmod:
            print("  unmodeled:", u)
        if not findings:
            print("  modeled DC checks passed: no short/source-fight findings")
        if coverage["coverage_gaps"]:
            print(f"  coverage incomplete: {len(coverage['coverage_gaps'])} gap(s); "
                  "bounded DC signoff is not ready")
        elif not findings:
            print("  bounded DC topology coverage complete for the stated scope")
        print("  functional signoff: not provided by this harness")
    return report


def path_impedance(board_dir, ref_a, pin_a, ref_b, pin_b):
    """Teeth primitive: DC impedance between two component pins (drive 1V, read I)."""
    board_dir = board_dir.rstrip("/")
    _sch, comps, nets = _project_netlist(board_dir)
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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--require-signoff", action="store_true",
                    help="fail closed unless bounded DC coverage is complete and clean")
    ap.add_argument("--path", nargs=4, metavar=("REF_A", "PIN_A", "REF_B", "PIN_B"),
                    help="pin-to-pin impedance probe (teeth primitive)")
    a = ap.parse_args(argv)
    if a.path:
        z, msg = path_impedance(a.board, *a.path)
        print(msg)
        return 0
    report = sanity(a.board, json_out=a.json)
    if report["findings"]:
        return 1
    if a.require_signoff and not report["coverage"]["signoff_ready"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
