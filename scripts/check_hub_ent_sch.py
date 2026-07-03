#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Verification harness for hubs/hub-enterprise/, per the protocol in
# hubs/hub-enterprise/SCHEMATIC-PLAN.md section 2. Grows one assertion block
# per sheet as sheets are captured; today it covers sheet 01 (power-input)
# plus whole-project hygiene (ERC regression guard, library registration,
# placeholder-sheet sanity). Run:
#
#   python3 scripts/check_hub_ent_sch.py
#
# Exits 0 on pass, non-zero on any failed assertion (printed to stderr).
import json, os, re, subprocess, sys, tempfile

ROOTDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_DIR = os.path.join(ROOTDIR, "hubs", "hub-enterprise")
ROOT_SCH = os.path.join(BOARD_DIR, "hub-enterprise.kicad_sch")

FAILURES = []


def check(cond, msg):
    if not cond:
        FAILURES.append(msg)
    else:
        print(f"  OK   {msg}")


def fail(msg):
    FAILURES.append(msg)


# ---------------------------------------------------------------------------
# netlist parsing helpers (same balanced-paren carve as scripts/cec_sch.py)
# ---------------------------------------------------------------------------
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
    nets = {}
    for m in re.finditer(r'\(net\s*\n\s*\(code "\d+"\)\s*\n\s*\(name "([^"]+)"\)', txt):
        block = carve(txt, m.start())
        nodes = re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', block)
        nets.setdefault(m.group(1), []).extend(nodes)
    comps = {}
    for m in re.finditer(r'\(comp\s*\n\s*\(ref "([^"]+)"\)', txt):
        ref = m.group(1)
        block = carve(txt, m.start())
        value = re.search(r'\(value "([^"]*)"\)', block)
        fields = dict(re.findall(r'\(field\s*\n\s*\(name "([^"]+)"\)\s*"([^"]*)"', block))
        comps[ref] = {"value": value.group(1) if value else "", "fields": fields}
    return nets, comps


def net_named(nets, suffix):
    """Return the net whose name ends with `suffix` (handles the /01-power-input/
    sheet-scope prefix KiCad applies to LOCAL nets that have no matching global
    power symbol, vs. bare names for truly global power nets)."""
    for name in nets:
        if name == suffix or name.endswith("/" + suffix):
            return name, set(nets[name])
    return None, set()


def main():
    print(f"=== hub-enterprise verification ({BOARD_DIR}) ===")

    # -----------------------------------------------------------------
    # 0. project scaffolding present
    # -----------------------------------------------------------------
    for f in ("hub-enterprise.kicad_pro", "hub-enterprise.kicad_sch",
              "01-power-input.kicad_sch", "sym-lib-table", "fp-lib-table", "DRAFT"):
        check(os.path.isfile(os.path.join(BOARD_DIR, f)), f"project file present: {f}")

    # -----------------------------------------------------------------
    # 0a. sheet-01 format correction (owner, 2026-07-02): 01-power-input is now
    # a THIN PARENT (sheet symbols only, no components, no dashed-frame section
    # graphics) fanning out to seven leaf sheets, one per functional block.
    # -----------------------------------------------------------------
    LEAF_SHEETS = ("01a-efuse-main", "01b-efuse-5vsb", "01c-efuse-ext",
                   "01d-cascade", "01e-holdup", "01f-buck-3v3", "01g-rail-sense")
    parent_path = os.path.join(BOARD_DIR, "01-power-input.kicad_sch")
    if os.path.isfile(parent_path):
        parent_txt = open(parent_path).read()
        # a REAL component instance is a `(symbol (lib_id "...") ...)` placement
        # referencing a non-power library; the thin parent's ONLY placed
        # `(symbol ...)` instances are the 3 GND/rail-style global power stamps
        # (cec-power:+5V_MAIN etc, needed so the +5V_MAIN/+5VSB/+5V_SYS
        # hierarchical labels aren't label_dangling -- see build_thin_parent's
        # global_power_exports) -- those are connectivity markers, not BOM
        # parts, exactly like every leaf's own PWR_FLAG/power-port stamps.
        real_lib_ids = re.findall(r'\(lib_id "([^"]+)"\)', parent_txt)
        non_power = [l for l in real_lib_ids if not l.startswith("cec-power:")]
        check(not non_power,
              f"01-power-input.kicad_sch (thin parent) carries no components "
              f"(found non-power lib_ids: {non_power})")
        check("(type dash)" not in parent_txt,
              "01-power-input.kicad_sch (thin parent) carries no dashed-frame section graphics")
        check(parent_txt.count("(sheet\n") == len(LEAF_SHEETS),
              f"01-power-input.kicad_sch instantiates exactly {len(LEAF_SHEETS)} leaf sheets "
              f"(found {parent_txt.count('(sheet' + chr(10))})")
    for name in LEAF_SHEETS:
        p = os.path.join(BOARD_DIR, f"{name}.kicad_sch")
        check(os.path.isfile(p), f"leaf sheet present: {name}.kicad_sch")
        if os.path.isfile(p):
            txt = open(p).read()
            check("(type dash)" not in txt,
                  f"{name}.kicad_sch carries no dashed-frame section graphics "
                  "(one functional block, one sheet, one title -- not a dashed sub-section)")
            check(f'(title "CEC Hub -- Enterprise (ENT): {name}"' in txt,
                  f"{name}.kicad_sch carries a proper per-sheet title")

    for num, name in (("02", "02-compute-core"), ("03", "03-compute-rails"),
                       ("04", "04-storage"), ("05", "05-module-ports"),
                       ("06", "06-t1-dataplane"), ("07", "07-uplink"),
                       ("08", "08-secio-aux"), ("09", "09-watchdog")):
        p = os.path.join(BOARD_DIR, f"{name}.kicad_sch")
        check(os.path.isfile(p), f"placeholder sheet present: {name}.kicad_sch")
        if os.path.isfile(p):
            txt = open(p).read()
            check("CAPTURE PENDING" in txt, f"{name}.kicad_sch marked capture-pending")
            check("(symbol\n" not in txt and "(symbol \"" not in txt,
                  f"{name}.kicad_sch carries no components yet")

    symtab = open(os.path.join(BOARD_DIR, "sym-lib-table")).read()
    for nick in ("cec", "cec-vendor", "cec-power", "cec-ent-power", "cec-ent-net",
                 "cec-ent-mcu", "cec-ent-compute", "cec-ent-hub-local"):
        check(f'(name "{nick}")' in symtab, f"sym-lib-table registers {nick}")
    fptab = open(os.path.join(BOARD_DIR, "fp-lib-table")).read()
    for nick in ("cec", "cec-Capacitor_SMD", "cec-Resistor_SMD", "cec-Package_DFN_QFN",
                 "cec-Package_TO_SOT_SMD", "cec-Connector_JST", "cec-Diode_SMD",
                 "cec-ent-power", "cec-ent-net", "cec-ent-mcu", "cec-ent-compute",
                 "cec-ent-hub-local"):
        check(f'(name "{nick}")' in fptab, f"fp-lib-table registers {nick}")

    # -----------------------------------------------------------------
    # 1. ERC across the whole hierarchy -- must be EXACTLY the documented-benign
    #    classes (a regression guard: any NEW violation type fails the check).
    # -----------------------------------------------------------------
    KNOWN_BENIGN = {
        "lib_symbol_mismatch":  "generator lib_symbols-cache cosmetic mismatch (repo-wide known class)",
        "pin_not_connected":    "sheet-01's 15 hierarchical exports have no consumer yet (sheets 02-09 are placeholders)",
        "pin_to_pin":           "TPS25940LRVCR's 5 parallel power_out OUT pins tied together (required multi-pin eFuse design)",
        "isolated_pin_label":   "RESET_3V3: a single forward-looking label, no consumer captured yet",
        "endpoint_off_grid":    "warning-only: a leaf sheet-pin's X MUST sit exactly on its box's real edge (not "
                                "gridsnapped) for kicad-cli to bind it into the flattened net at all -- verified "
                                "empirically during the 2026-07-02 re-sheeting (a gridsnapped X parses fine but "
                                "silently drops the connection); the resulting stub wire is then off the 1.27mm "
                                "cosmetic grid by construction. All 19 occurrences are severity=warning.",
    }
    with tempfile.TemporaryDirectory() as td:
        erc_json = os.path.join(td, "erc.json")
        r = subprocess.run(
            ["kicad-cli", "sch", "erc", "--exit-code-violations", "--format", "json",
             "-o", erc_json, ROOT_SCH],
            capture_output=True, text=True)
        check(os.path.isfile(erc_json), "kicad-cli sch erc produced a report")
        d = json.load(open(erc_json))
        found = {}
        for sheet in d.get("sheets", []):
            for v in sheet.get("violations", []):
                found[v["type"]] = found.get(v["type"], 0) + 1
        unexpected = sorted(set(found) - set(KNOWN_BENIGN))
        check(not unexpected, f"ERC has no unexpected violation types (found: {unexpected})")
        for t, why in KNOWN_BENIGN.items():
            print(f"  ..  ERC {t}: {found.get(t, 0)} occurrences ({why})")

    # -----------------------------------------------------------------
    # netlist (flattened across the hierarchy)
    # -----------------------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        net_path = os.path.join(td, "hub-enterprise.net")
        r = subprocess.run(
            ["kicad-cli", "sch", "export", "netlist", "-o", net_path, ROOT_SCH],
            capture_output=True, text=True)
        check(r.returncode == 0, f"kicad-cli sch export netlist succeeded ({r.stderr.strip()})")
        nets, comps = parse_netlist(net_path)

    # -----------------------------------------------------------------
    # 1a. re-sheeting must be electrically inert: same 59 components, and the
    # SAME flattened connectivity -- compared by NODE SET (ignoring net names/
    # sheet-path prefixes, which necessarily changed since nets now live one
    # level deeper) against the pre-restructure (flat sheet-01) baseline
    # captured in this same session. 46 connectivity groups, verified via
    # `python3 conn_snapshot.py` bit-for-bit equal (0 missing / 0 extra) run
    # against the committed pre-2026-07-02 01-power-input.kicad_sch.
    # -----------------------------------------------------------------
    real_comps = [r for r in comps if not r.startswith("#")]
    check(len(real_comps) == 59, f"component count unchanged by the re-sheeting (expected 59, got {len(real_comps)})")
    groups = sorted(frozenset(v) for v in nets.values())
    n_groups = len(groups)
    check(n_groups == 46,
          f"flattened connectivity group count unchanged by the re-sheeting "
          f"(expected 46, matching the pre-restructure flat sheet-01 baseline; got {n_groups})")

    # -----------------------------------------------------------------
    # 2. sheet-01 assertion block (BOM-D power-input)
    # -----------------------------------------------------------------
    print("--- sheet 01 (power-input) assertions ---")

    # a) eFuse OUT -> cascade IN chain, one per source
    _, main_out = net_named(nets, "MAIN_EF_OUT")
    _, svb_out = net_named(nets, "SVB_EF_OUT")
    _, ext_out = net_named(nets, "EXT_EF_OUT")
    _, stage_a = net_named(nets, "STAGE_A_OUT")
    _, sys5v = net_named(nets, "+5V_SYS")

    check({("U101", "4"), ("U101", "5"), ("U101", "6"), ("U101", "7"), ("U101", "8")} <= main_out,
          "U_EF1 (MAIN_5V eFuse) OUT pins 4-8 tied together")
    check(("U105", "6") in main_out and ("U105", "7") in main_out,
          "U_EF1.OUT -> U_PC2 (stage B) PR1/IN1 (MAIN_5V is stage-B's priority input)")
    check({("U102", "4"), ("U102", "5"), ("U102", "6"), ("U102", "7"), ("U102", "8")} <= svb_out,
          "U_EF2 (5VSB eFuse) OUT pins 4-8 tied together")
    check(("U104", "6") in svb_out and ("U104", "7") in svb_out,
          "U_EF2.OUT -> U_PC1 (stage A) PR1/IN1 (5VSB is stage-A's priority input)")
    check({("U103", "4"), ("U103", "5"), ("U103", "6"), ("U103", "7"), ("U103", "8")} <= ext_out,
          "U_EF3 (EXT eFuse) OUT pins 4-8 tied together")
    check(("U104", "2") in ext_out and ("U104", "3") in ext_out,
          "U_EF3.OUT -> U_PC1 (stage A) IN2/CP2 (EXT is stage-A's non-priority input)")
    check(("U104", "1") in stage_a and ("U104", "8") in stage_a
          and ("U105", "2") in stage_a and ("U105", "3") in stage_a,
          "U_PC1 (stage A) OUT -> U_PC2 (stage B) IN2/CP2 (cascade chain)")
    check(("U105", "1") in sys5v and ("U105", "8") in sys5v,
          "U_PC2 (stage B) OUT -> +5V_SYS (merged system rail)")

    # b) ILIM values present and correct (bom-d computed values). cec_sch's
    # shared R_Small formatter (fmt_res, reused by this generator) appends the
    # Ω sign to whole-number k values ("10k"->"10kΩ") but leaves decimal ones
    # alone ("45.3k" stays "45.3k") -- a cosmetic quirk of the shared helper,
    # not an electrical difference, so normalize it away before comparing.
    def val(ref):
        return comps.get(ref, {}).get("value", "").replace("Ω", "")

    check(val("R104") == "24.9k", f"R_ILIM MAIN_5V = 24.9k (24.9k -> 3.53A typ); got {val('R104')!r}")
    check(val("R110") == "42.2k", f"R_ILIM 5VSB = 42.2k (42.2k -> 2.08A typ); got {val('R110')!r}")
    check(val("R116") == "42.2k", f"R_ILIM EXT = 42.2k (42.2k -> 2.08A typ); got {val('R116')!r}")
    check(val("R119") == "27k" and val("R120") == "27k",
          f"R_ILIM(PC) cascade = 27k on both stages; got {val('R119')!r}/{val('R120')!r}")
    _, ilim_main = net_named(nets, "ILIM_MAIN")
    check(("R104", "1") in ilim_main and ("U101", "17") in ilim_main, "R104 lands on U101's ILIM pin (17)")
    _, ilim_svb = net_named(nets, "ILIM_SVB")
    check(("R110", "1") in ilim_svb and ("U102", "17") in ilim_svb, "R110 lands on U102's ILIM pin (17)")
    _, ilim_ext = net_named(nets, "ILIM_EXT")
    check(("R116", "1") in ilim_ext and ("U103", "17") in ilim_ext, "R116 lands on U103's ILIM pin (17)")

    # UVLO/OVLO divider values (4.49V UV / 5.75V OV per bom-d's derivation)
    for grp, r1, r2, r3 in (("MAIN", "R101", "R102", "R103"),
                             ("SVB", "R107", "R108", "R109"),
                             ("EXT", "R113", "R114", "R115")):
        check(val(r1) == "45.3k" and val(r2) == "2.80k" and val(r3) == "10k",
              f"{grp} eFuse UVLO/OVLO divider = 45.3k/2.80k/10k "
              f"(got {val(r1)!r}/{val(r2)!r}/{val(r3)!r})")

    # c) rail-sense dividers land on their own named (exported) nets
    for label, hi_ref, lo_ref, sense_net, raw_net in (
            ("MAIN_5V raw", "R123", "R124", "SENSE_MAIN", "+5V_MAIN"),
            ("5VSB raw",    "R125", "R126", "SENSE_SVB",  "+5VSB"),
            ("EXT raw",     "R127", "R128", "SENSE_EXT",  "EXT_5V"),
            ("+5V_SYS",     "R129", "R130", "SENSE_SYS",  "+5V_SYS")):
        check(val(hi_ref) == "47k" and val(lo_ref) == "10k",
              f"rail-sense divider ({label}) = 47k/10k (got {val(hi_ref)!r}/{val(lo_ref)!r})")
        _, sense_conns = net_named(nets, sense_net)
        check((hi_ref, "2") in sense_conns and (lo_ref, "1") in sense_conns,
              f"{sense_net} divider tap lands on the named sense net")
        _, raw_conns = net_named(nets, raw_net)
        check((hi_ref, "1") in raw_conns,
              f"{sense_net}'s top resistor taps the {raw_net} rail (upstream of its eFuse where applicable)")

    # d) no cross-source short: the three raw source nets, the three eFuse-OUT
    #    nets, the cascade intermediate, and the merged system rail must all be
    #    pairwise DISJOINT node sets (a short would show up as unexpected overlap).
    _, main_raw = net_named(nets, "+5V_MAIN")
    _, svb_raw = net_named(nets, "+5VSB")
    _, ext_raw = net_named(nets, "EXT_5V")
    groups = {
        "+5V_MAIN": main_raw, "+5VSB": svb_raw, "EXT_5V": ext_raw,
        "MAIN_EF_OUT": main_out, "SVB_EF_OUT": svb_out, "EXT_EF_OUT": ext_out,
        "STAGE_A_OUT": stage_a, "+5V_SYS": sys5v,
    }
    names = list(groups)
    shorted = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            overlap = groups[a] & groups[b]
            if overlap:
                shorted.append((a, b, overlap))
    check(not shorted, f"no cross-source short among the 8 power-stage nets (found: {shorted})")

    # e) every real part carries Manufacturer + MPN (BOM-D traceability)
    missing_bom = []
    for ref, info in comps.items():
        if ref.startswith("#"):
            continue
        f = info["fields"]
        if not (f.get("Manufacturer") and f.get("MPN")):
            missing_bom.append(ref)
    check(not missing_bom, f"every sheet-01 part carries Manufacturer+MPN (missing: {missing_bom})")

    # f) platform conformance: no Mini-Fit Jr anywhere on this sheet (the
    # module-to-Hub link / Hub bulk power connector is locked to RJ-45 / JST-XH;
    # sheet01 has neither an RJ-45 port nor Mini-Fit Jr, by design)
    mini_fit = [ref for ref, info in comps.items()
                if "Mini-Fit" in info["fields"].get("Footprint", "") or "5569" in info["fields"].get("Footprint", "")]
    check(not mini_fit, f"no Mini-Fit Jr connector on sheet 01 (found: {mini_fit})")

    # -----------------------------------------------------------------
    # 3. root sheet-01 instance exposes exactly the planned 15 hierarchical pins
    # -----------------------------------------------------------------
    root_txt = open(ROOT_SCH).read()
    m = re.search(r'\(sheet\n.*?"Sheetname" "01-power-input".*?(?=\n\t\(sheet\n|\n\t\(text|\n\t\(sheet_instances)',
                   root_txt, re.S)
    check(m is not None, "root sheet carries a 01-power-input sheet instance")
    if m:
        pins = re.findall(r'\(pin "([^"]+)"', m.group(0))
        expected = {"+5V_MAIN", "+5VSB", "EXT_5V", "+5V_SYS", "+3V3",
                    "PG_MAIN", "FLT_MAIN", "PG_SVB", "FLT_SVB", "PG_EXT", "FLT_EXT",
                    "SENSE_MAIN", "SENSE_SVB", "SENSE_EXT", "SENSE_SYS"}
        check(set(pins) == expected,
              f"root's 01-power-input sheet symbol exposes exactly the 15 planned exports "
              f"(got {sorted(set(pins) ^ expected)} diff)")

    # -----------------------------------------------------------------
    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}):", file=sys.stderr)
        for f in FAILURES:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"All checks passed ({len(comps)} components on sheet 01, "
          f"{len(nets)} nets in the flattened hierarchy).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
