#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Verification harness for modules/ent-common/p4-t1-block.kicad_sch -- the
# shared ESP32-P4 + 100BASE-T1 module reference block. Exports the netlist via
# kicad-cli and asserts the electrical facts the block exists to guarantee:
#
#   1. project scaffolding present (kicad_pro/sch/lib-tables)
#   2. ERC is EXACTLY the documented-benign classes (regression guard -- any
#      NEW violation type fails the check)
#   3. the TPS26621 eFuse sits IN SERIES between RJ-45 pin 1 and the LDO input
#      (not bypassed)
#   4. DETECT (pin 8): series R -> [10k ENT-class code resistor + low-cap ESD
#      clamp + the poke-and-ack tap], per REQ-MOD-COMMON-053 / survey 11
#   5. pin 7: series R -> low-cap clamp -> MCU GPIO (SYNC/FREEZE + heartbeat,
#      REQ-MOD-COMMON-013)
#   6. the 100BASE-T1 MDI chain: RJ-45 pins 4/5 -> CMC -> AC-coupling caps ->
#      PHY MDI pins, PHY-side ESD across the same node
#   7. CAN H/L land on RJ-45 pins 3/6 through the TJA1051T/3
#   8. RMII pin-map sanity: every RMII_* net's PHY-side pin FUNCTION NAME (as
#      declared in the vendored DP83TC814S-Q1 symbol, itself hand-derived from
#      TI datasheet SNLS663B Table 5-1) matches what the net name claims --
#      catches an accidental off-by-one pin-number error in the generator.
#
# Run:  python3 modules/ent-common/check_p4_t1_block.py
# Exits 0 on pass, non-zero (with every failure printed) otherwise.
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCH = os.path.join(HERE, "p4-t1-block.kicad_sch")

FAILURES = []


def check(cond, msg):
    if not cond:
        FAILURES.append(msg)
    else:
        print(f"  OK   {msg}")


def fail(msg):
    FAILURES.append(msg)
    print(f"  FAIL {msg}")


# ---------------------------------------------------------------------------
# netlist parsing (same balanced-paren carve as scripts/cec_sch.py /
# scripts/check_hub_ent_sch.py; duplicated rather than imported so this
# checker has no cross-agent-owned-file dependency)
def carve(text, start):
    d = 0
    instr = esc = False
    j = start
    while j < len(text):
        c = text[j]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = False
        else:
            if c == '"':
                instr = True
            elif c == "(":
                d += 1
            elif c == ")":
                d -= 1
                if d == 0:
                    return text[start:j + 1]
        j += 1
    raise ValueError("unbalanced s-expr")


def parse_netlist(path):
    txt = open(path).read()
    nets = {}          # net name -> [(ref, pin), ...]
    pinfuncs = {}       # (ref, pin) -> declared pin-function name
    for m in re.finditer(r'\(net\s*\n\s*\(code "\d+"\)\s*\n\s*\(name "([^"]+)"\)', txt):
        block = carve(txt, m.start())
        for nm in re.finditer(r'\(node\s*\n\s*\(ref "([^"]+)"\)\s*\n\s*\(pin "([^"]+)"\)'
                               r'(?:\s*\n\s*\(pinfunction "([^"]*)"\))?', block):
            ref, pin, pf = nm.group(1), nm.group(2), nm.group(3) or ""
            nets.setdefault(m.group(1), []).append((ref, pin))
            pinfuncs[(ref, pin)] = pf
    comps = {}
    for m in re.finditer(r'\(comp\s*\n\s*\(ref "([^"]+)"\)', txt):
        ref = m.group(1)
        block = carve(txt, m.start())
        value = re.search(r'\(value "([^"]*)"\)', block)
        comps[ref] = value.group(1) if value else ""
    return nets, pinfuncs, comps


def net_of(nets, ref, pin):
    """Which net (bare name, KiCad may prefix local nets with the sheet path)
    carries (ref, pin)? None if not found."""
    for name, nodes in nets.items():
        if (ref, pin) in nodes:
            return name
    return None


def same_net(nets, a, b):
    na, nb = net_of(nets, *a), net_of(nets, *b)
    return na is not None and na == nb


def main():
    print(f"=== ent-common p4-t1-block verification ({HERE}) ===")

    # -----------------------------------------------------------------
    # 1. project scaffolding
    # -----------------------------------------------------------------
    for f in ("p4-t1-block.kicad_sch", "p4-t1-block.kicad_pro",
              "sym-lib-table", "fp-lib-table", "ent-common-local.kicad_sym",
              "gen_p4_t1_block.py", "README.md",
              # hierarchy leaf sheets (2026-07-03 restructure: root = thin
              # parent, one functional block per leaf file)
              "01-power.kicad_sch", "02-misplug-protection.kicad_sch",
              "03-can.kicad_sch", "04-mcu.kicad_sch", "05-t1-phy.kicad_sch",
              "06-usb-debug.kicad_sch"):
        check(os.path.isfile(os.path.join(HERE, f)), f"project file present: {f}")

    # -----------------------------------------------------------------
    # 2. ERC -- exactly the documented-benign classes
    # -----------------------------------------------------------------
    KNOWN_BENIGN = {
        "lib_symbol_mismatch": "generator lib_symbols-cache cosmetic re-serialization mismatch (repo-wide known class)",
        "pin_to_pin": "the vendored ESP32-P4 / DP83TC814S-Q1 / ACT1210L / PESD2ETH100-T symbols type every pin "
                      "'Unspecified' (T2 cec_sym_audit finding, schematic-quality-charter) -- ERC cannot tell an "
                      "'Unspecified' pin is really driving; not a real connectivity defect",
        "pin_not_driven": "same root cause: an MCU/PHY GPIO of declared type 'Unspecified' driving an Input pin "
                           "(e.g. CAN_TX->TXD) reads as 'not driven' -- matches the ALREADY-documented "
                           "'CAN-TXD pin_not_driven' class on modules/eps-8pin",
    }
    with tempfile.TemporaryDirectory() as td:
        erc_json = os.path.join(td, "erc.json")
        r = subprocess.run(
            ["kicad-cli", "sch", "erc", "--exit-code-violations", "--format", "json",
             "-o", erc_json, SCH], capture_output=True, text=True)
        check(os.path.isfile(erc_json), "kicad-cli sch erc produced a report")
        if os.path.isfile(erc_json):
            d = json.load(open(erc_json))
            found = {}
            for sheet in d.get("sheets", []):
                for v in sheet.get("violations", []):
                    found[v["type"]] = found.get(v["type"], 0) + 1
            unexpected = sorted(set(found) - set(KNOWN_BENIGN))
            check(not unexpected, f"ERC has no violation classes beyond the documented-benign set "
                                   f"(unexpected: {unexpected})")
            for k, n in sorted(found.items()):
                print(f"       {n:3d}  {k}  -- {KNOWN_BENIGN.get(k, '** UNTRIAGED **')}")

    # -----------------------------------------------------------------
    # netlist export + parse
    # -----------------------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        net_path = os.path.join(td, "p4-t1-block.net")
        r = subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", net_path, SCH],
                            capture_output=True, text=True)
        check(r.returncode == 0, f"kicad-cli sch export netlist succeeded ({r.stderr.strip()[:200]})")
        if r.returncode != 0:
            print("\n".join(FAILURES), file=sys.stderr)
            sys.exit(1)
        nets, pinfuncs, comps = parse_netlist(net_path)

    # -----------------------------------------------------------------
    # 3. eFuse (U2, TPS26621DRCT) IN SERIES between RJ-45 pin 1 and the LDO
    #    (U3, LP5907) input -- and NOT bypassed (raw and fused rails distinct)
    # -----------------------------------------------------------------
    check(comps.get("U2") == "TPS26621DRCT", "U2 is TPS26621DRCT (the module mis-plug eFuse)")
    check(comps.get("U3") == "LP5907MFX-3.3", "U3 is the LP5907-class 3V3 LDO")
    check(same_net(nets, ("J1", "1"), ("U2", "1")),
          "RJ-45 pin 1 (VCC/+5VSB) feeds the eFuse IN (U2.1) directly")
    check(same_net(nets, ("U2", "10"), ("U3", "1")) and same_net(nets, ("U2", "10"), ("U3", "3")),
          "eFuse OUT (U2.10) feeds the LDO input (U3.1/U3.3)")
    check(not same_net(nets, ("J1", "1"), ("U3", "1")),
          "RJ-45 pin 1 is NOT directly on the LDO-input net (the eFuse is a real series element, not bypassed)")

    # -----------------------------------------------------------------
    # 4. DETECT (pin 8): series R -> [10k code R + ESD clamp + poke tap]
    # -----------------------------------------------------------------
    check(same_net(nets, ("J1", "8"), ("R7", "1")), "DETECT pin 8 feeds the NEW series R (R7) first")
    check(not same_net(nets, ("J1", "8"), ("D1", "1")),
          "the ESD clamp (D1) sits AFTER the series R, not directly on the raw jack pin")
    check(same_net(nets, ("R7", "2"), ("D1", "1")), "series R (R7) feeds the low-cap ESD clamp (D1)")
    check(same_net(nets, ("R7", "2"), ("R8", "1")), "series R (R7) feeds the DETECT code resistor (R8)")
    check(comps.get("R8") == "10kΩ", f"R8 (DETECT code resistor) = 10 kOhm, the ENT CAN+100BASE-T1 class (got {comps.get('R8')!r})")
    check(same_net(nets, ("R8", "2"), ("D1", "2")),
          "the code resistor and the ESD clamp share a return to GND")
    check(net_of(nets, "R8", "2") == "GND", "DETECT code resistor R8 returns to GND")
    check(same_net(nets, ("R7", "2"), ("R9", "1")), "the poke-and-ack tap (R9) taps the same DETECT node")
    check(comps.get("R9") == "100kΩ", f"R9 (poke-and-ack tap) = 100 kOhm (got {comps.get('R9')!r})")
    detect_sense_net = net_of(nets, "R9", "2")
    detect_sense_u1_pins = [p for (r, p) in nets.get(detect_sense_net, []) if r == "U1"]
    check(len(detect_sense_u1_pins) == 1,
          f"the poke-and-ack tap (R9) reaches exactly one ESP32-P4 ADC/GPIO pin (found {detect_sense_u1_pins})")

    # -----------------------------------------------------------------
    # 5. pin 7: series R -> low-cap clamp -> MCU GPIO
    # -----------------------------------------------------------------
    check(same_net(nets, ("J1", "7"), ("R10", "1")), "pin 7 (SYNC/FREEZE) feeds its series R (R10) first")
    check(not same_net(nets, ("J1", "7"), ("D2", "1")),
          "the pin-7 clamp (D2) sits AFTER the series R, not directly on the raw jack pin")
    check(same_net(nets, ("R10", "2"), ("D2", "1")), "pin-7 series R feeds the low-cap clamp (D2)")
    check(net_of(nets, "D2", "2") == "GND", "pin-7 clamp (D2) returns to GND")
    # the post-clamp node must reach a real ESP32-P4 pin (any (U1, pin) node)
    sync7_net = net_of(nets, "R10", "2")
    sync7_u1_pins = [p for (r, p) in nets.get(sync7_net, []) if r == "U1"]
    check(len(sync7_u1_pins) == 1, f"pin-7 node reaches exactly one ESP32-P4 GPIO pin (found {sync7_u1_pins})")

    # -----------------------------------------------------------------
    # 6. 100BASE-T1 MDI chain: jack pins 4/5 -> CMC -> AC-couple -> PHY
    # -----------------------------------------------------------------
    check(comps.get("L1", "").startswith("ACT1210L"), "L1 is the ACT1210L common-mode choke")
    check(comps.get("U6") == "DP83TC814S-Q1", "U6 is the DP83TC814S-Q1 100BASE-T1 PHY")
    check(comps.get("D4") == "PESD2ETH100-T", "D4 is the PESD2ETH100-T PHY-side ESD clamp")
    check(same_net(nets, ("J1", "4"), ("L1", "1")), "RJ-45 pin 4 feeds the CMC (L1.1) first")
    check(same_net(nets, ("J1", "5"), ("L1", "2")), "RJ-45 pin 5 feeds the CMC (L1.2) first")
    check(not same_net(nets, ("J1", "4"), ("U6", "12")), "pin 4 is NOT directly on the PHY MDI pin (CMC+cap sit between)")
    check(same_net(nets, ("L1", "4"), ("C20", "1")), "CMC output (line A) feeds the AC-coupling cap C20")
    check(same_net(nets, ("L1", "3"), ("C21", "1")), "CMC output (line B) feeds the AC-coupling cap C21")
    check(same_net(nets, ("C20", "2"), ("U6", "12")), "coupling cap C20 feeds the PHY TRD_P pin (12)")
    check(same_net(nets, ("C21", "2"), ("U6", "13")), "coupling cap C21 feeds the PHY TRD_M pin (13)")
    check(pinfuncs.get(("U6", "12"), "").startswith("TRD_P"), "PHY pin 12 is really named TRD_P in the vendored symbol")
    check(pinfuncs.get(("U6", "13"), "").startswith("TRD_M"), "PHY pin 13 is really named TRD_M in the vendored symbol")
    check(same_net(nets, ("D4", "1"), ("U6", "12")) and same_net(nets, ("D4", "2"), ("U6", "13")),
          "the PHY-side ESD clamp (D4) sits directly across TRD_P/TRD_M")

    # -----------------------------------------------------------------
    # 7. CAN H/L on RJ-45 pins 3/6 via the TJA1051T/3 (U4)
    # -----------------------------------------------------------------
    check(comps.get("U4") == "TJA1051T/3", "U4 is the TJA1051T/3 CAN transceiver")
    check(same_net(nets, ("J1", "3"), ("U4", "7")), "RJ-45 pin 3 (CAN1_H) lands on the transceiver's CANH pin (7)")
    check(same_net(nets, ("J1", "6"), ("U4", "6")), "RJ-45 pin 6 (CAN1_L) lands on the transceiver's CANL pin (6)")
    check(pinfuncs.get(("J1", "3"), "").startswith("CAN1_H"), "RJ-45 pin 3 is really named CAN1_H in the vendored symbol")
    check(pinfuncs.get(("J1", "6"), "").startswith("CAN1_L"), "RJ-45 pin 6 is really named CAN1_L in the vendored symbol")

    # -----------------------------------------------------------------
    # 8. RMII pin-map sanity vs the TI-datasheet-derived pin names on U6
    # -----------------------------------------------------------------
    EXPECT_PREFIX = {
        "28": "TX_CLK",              # ** flagged as REF_CLK -- unconfirmed, see README **
        "26": "RX_D0",
        "25": "RX_D1",
        "15": "RX_DV",
        "33": "TX_D0",
        "32": "TX_D1",
        "29": "TX_EN",
        "14": "RX_ER",
        "1":  "MDC",
        "36": "MDIO",
        "2":  "INT_N",
        "3":  "RESET_N",
    }
    for pin, prefix in EXPECT_PREFIX.items():
        got = pinfuncs.get(("U6", pin), "")
        check(got.startswith(prefix), f"U6 pin {pin} is named {prefix}* in the vendored DP83TC814S-Q1 symbol (got {got!r})")

    # -----------------------------------------------------------------
    # 9. hierarchy equivalence guard (2026-07-03 restructure) -- same
    #    discipline scripts/check_hub_ent_sch.py grew for the hub's
    #    re-sheeting: component count + flattened connectivity-group
    #    count frozen against the pre-restructure single-sheet baseline
    #    (verified node-set-for-node-set at restructure time: 61 comps,
    #    130 groups of which 53 multi-node, 0 missing / 0 extra).
    # -----------------------------------------------------------------
    real_comps = [r for r in comps if not r.startswith("#")]
    check(len(real_comps) == 61,
          f"component count unchanged by the re-sheeting (expected 61, got {len(real_comps)})")
    groups = sorted(frozenset(v) for v in nets.values())
    check(len(groups) == 130,
          f"flattened connectivity group count unchanged by the re-sheeting "
          f"(expected 130, matching the pre-restructure flat baseline; got {len(groups)})")
    multi = sum(1 for g in groups if len(g) >= 2)
    check(multi == 53,
          f"multi-node connectivity group count unchanged (expected 53, got {multi})")

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S):", file=sys.stderr)
        for m in FAILURES:
            print(f"  - {m}", file=sys.stderr)
        sys.exit(1)
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
