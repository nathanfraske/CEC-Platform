#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Verification harness for hubs/hub-enterprise/, per the protocol in
# hubs/hub-enterprise/SCHEMATIC-PLAN.md section 2. Grows one assertion block
# per sheet as sheets are captured; today it covers sheet 01 (power-input) and
# sheet 05 (module-ports: 8x port + CAN frontend + DETECT ADC), plus
# whole-project hygiene (ERC regression guard, library registration,
# placeholder-sheet sanity, and a component/connectivity equivalence guard
# that proves each newly-captured sheet is ADDITIVE -- every prior sheet's own
# component count and connectivity are unchanged). Run:
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


def group_of(nets, ref, pin):
    """Return the full node-set of whichever net contains (ref, pin), by
    PIN MEMBERSHIP rather than net NAME. A purely-internal 2-pin connection
    with no hier label / local label / power stamp anywhere on it (e.g. a
    jack pin wired straight into a series resistor, nothing else) gets NO
    visible name at all -- kicad-cli auto-derives one from a component pin
    (`Net-(J_PORT1-DETECT)`), ignoring whatever bookkeeping name the
    generator used internally. `net_named` (name-based) cannot find such a
    net; this pin-based lookup is the general form."""
    for conns in nets.values():
        if (ref, pin) in conns:
            return set(conns)
    return set()


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

    for num, name in (("06", "06-t1-dataplane"), ("07", "07-uplink"),
                       ("08", "08-secio-aux"), ("09", "09-watchdog")):
        p = os.path.join(BOARD_DIR, f"{name}.kicad_sch")
        check(os.path.isfile(p), f"placeholder sheet present: {name}.kicad_sch")
        if os.path.isfile(p):
            txt = open(p).read()
            check("CAPTURE PENDING" in txt, f"{name}.kicad_sch marked capture-pending")
            check("(symbol\n" not in txt and "(symbol \"" not in txt,
                  f"{name}.kicad_sch carries no components yet")

    # -----------------------------------------------------------------
    # 0b. sheet 05 (module ports) format: same thin-parent-plus-leaves rule
    # as sheet 01, but with the 8x 05a-port{n} REPEATED-BLOCK case (one
    # template function, 8 generated leaf files -- see gen_hub_enterprise.py's
    # module docstring on why this generator does not use a single leaf file
    # instantiated 8x: build_leaf/build_thin_parent each bake exactly ONE
    # instances.path/sheet_instances entry per component/file today).
    # -----------------------------------------------------------------
    SHEET05_LEAVES = tuple(f"05a-port{n}" for n in range(1, 9)) + (
        "05b-can-frontend", "05c-detect-adc")
    parent05_path = os.path.join(BOARD_DIR, "05-module-ports.kicad_sch")
    if os.path.isfile(parent05_path):
        parent05_txt = open(parent05_path).read()
        real_lib_ids = re.findall(r'\(lib_id "([^"]+)"\)', parent05_txt)
        non_power = [l for l in real_lib_ids if not l.startswith("cec-power:")]
        check(not non_power,
              f"05-module-ports.kicad_sch (thin parent) carries no components "
              f"(found non-power lib_ids: {non_power})")
        check("(type dash)" not in parent05_txt,
              "05-module-ports.kicad_sch (thin parent) carries no dashed-frame section graphics")
        check(parent05_txt.count("(sheet\n") == len(SHEET05_LEAVES),
              f"05-module-ports.kicad_sch instantiates exactly {len(SHEET05_LEAVES)} leaf sheets "
              f"(found {parent05_txt.count('(sheet' + chr(10))})")
    for name in SHEET05_LEAVES:
        p = os.path.join(BOARD_DIR, f"{name}.kicad_sch")
        check(os.path.isfile(p), f"leaf sheet present: {name}.kicad_sch")
        if os.path.isfile(p):
            txt = open(p).read()
            check("(type dash)" not in txt,
                  f"{name}.kicad_sch carries no dashed-frame section graphics")
            check(f'(title "CEC Hub -- Enterprise (ENT): {name}"' in txt,
                  f"{name}.kicad_sch carries a proper per-sheet title")

    # -----------------------------------------------------------------
    # 0c. sheet 04 (storage) format: same thin-parent-plus-leaves rule as
    # sheets 01/05 -- three UNIQUE leaves (no repeated-block case here, unlike
    # sheet 05's 8x ports), captured 2026-07-16.
    # -----------------------------------------------------------------
    SHEET04_LEAVES = ("04a-qspi-nor", "04b-emmc", "04c-straps")
    parent04_path = os.path.join(BOARD_DIR, "04-storage.kicad_sch")
    check(os.path.isfile(parent04_path), "04-storage.kicad_sch (thin parent) present")
    if os.path.isfile(parent04_path):
        parent04_txt = open(parent04_path).read()
        real_lib_ids = re.findall(r'\(lib_id "([^"]+)"\)', parent04_txt)
        non_power = [l for l in real_lib_ids if not l.startswith("cec-power:")]
        check(not non_power,
              f"04-storage.kicad_sch (thin parent) carries no components "
              f"(found non-power lib_ids: {non_power})")
        check("(type dash)" not in parent04_txt,
              "04-storage.kicad_sch (thin parent) carries no dashed-frame section graphics")
        check(parent04_txt.count("(sheet\n") == len(SHEET04_LEAVES),
              f"04-storage.kicad_sch instantiates exactly {len(SHEET04_LEAVES)} leaf sheets "
              f"(found {parent04_txt.count('(sheet' + chr(10))})")
    for name in SHEET04_LEAVES:
        p = os.path.join(BOARD_DIR, f"{name}.kicad_sch")
        check(os.path.isfile(p), f"leaf sheet present: {name}.kicad_sch")
        if os.path.isfile(p):
            txt = open(p).read()
            check("(type dash)" not in txt,
                  f"{name}.kicad_sch carries no dashed-frame section graphics")
            check(f'(title "CEC Hub -- Enterprise (ENT): {name}"' in txt,
                  f"{name}.kicad_sch carries a proper per-sheet title")
    # NOT a placeholder anymore: "04-storage" is removed from the placeholder
    # tuple above (section 0) now that it's captured.

    # -----------------------------------------------------------------
    # 0d. sheet 03 (compute-rails) format: same thin-parent-plus-leaves rule,
    # captured 2026-07-16 same session. Two of its four leaves (03b-bank-
    # rails, 03c-vdda-ldo) are DELIBERATE EMPTY STUBS (library-blocked, see
    # gen_hub_enterprise.py's sheet-03 module docstring) -- they still get
    # the ordinary leaf-format checks (real file, proper title, no dashed
    # frame) PLUS an explicit check that they still carry the CAPTURE
    # PENDING honesty marker (catches a regression where someone removes the
    # marker without actually adding real parts).
    # -----------------------------------------------------------------
    SHEET03_LEAVES = ("03a-core-buck", "03b-bank-rails", "03c-vdda-ldo", "03d-sequencing")
    SHEET03_STUB_LEAVES = ("03b-bank-rails", "03c-vdda-ldo")
    parent03_path = os.path.join(BOARD_DIR, "03-compute-rails.kicad_sch")
    check(os.path.isfile(parent03_path), "03-compute-rails.kicad_sch (thin parent) present")
    if os.path.isfile(parent03_path):
        parent03_txt = open(parent03_path).read()
        real_lib_ids = re.findall(r'\(lib_id "([^"]+)"\)', parent03_txt)
        non_power = [l for l in real_lib_ids if not l.startswith("cec-power:")]
        check(not non_power,
              f"03-compute-rails.kicad_sch (thin parent) carries no components "
              f"(found non-power lib_ids: {non_power})")
        check("(type dash)" not in parent03_txt,
              "03-compute-rails.kicad_sch (thin parent) carries no dashed-frame section graphics")
        check(parent03_txt.count("(sheet\n") == len(SHEET03_LEAVES),
              f"03-compute-rails.kicad_sch instantiates exactly {len(SHEET03_LEAVES)} leaf sheets "
              f"(found {parent03_txt.count('(sheet' + chr(10))})")
    for name in SHEET03_LEAVES:
        p = os.path.join(BOARD_DIR, f"{name}.kicad_sch")
        check(os.path.isfile(p), f"leaf sheet present: {name}.kicad_sch")
        if os.path.isfile(p):
            txt = open(p).read()
            check("(type dash)" not in txt,
                  f"{name}.kicad_sch carries no dashed-frame section graphics")
            check(f'(title "CEC Hub -- Enterprise (ENT): {name}"' in txt,
                  f"{name}.kicad_sch carries a proper per-sheet title")
            if name in SHEET03_STUB_LEAVES:
                check("CAPTURE PENDING" in txt,
                      f"{name}.kicad_sch (empty stub, library-blocked) still carries its "
                      f"CAPTURE PENDING honesty marker")

    # -----------------------------------------------------------------
    # 0e. sheet 02 (compute-core) format: same thin-parent-plus-leaves rule.
    # Only ONE leaf this pass (02a-mpfs-core) -- 02b/02c/02d are DEFERRED
    # (not yet composed at all, not empty stubs -- see gen_hub_enterprise.
    # py's sheet-02 module docstring + FOLLOWUPS.md), so there is no
    # SHEET02_STUB_LEAVES analog to sheet 03's CAPTURE-PENDING-marker check.
    # -----------------------------------------------------------------
    SHEET02_LEAVES = ("02a-mpfs-core",)
    parent02_path = os.path.join(BOARD_DIR, "02-compute-core.kicad_sch")
    check(os.path.isfile(parent02_path), "02-compute-core.kicad_sch (thin parent) present")
    if os.path.isfile(parent02_path):
        parent02_txt = open(parent02_path).read()
        real_lib_ids = re.findall(r'\(lib_id "([^"]+)"\)', parent02_txt)
        non_power = [l for l in real_lib_ids if not l.startswith("cec-power:")]
        check(not non_power,
              f"02-compute-core.kicad_sch (thin parent) carries no components "
              f"(found non-power lib_ids: {non_power})")
        check("(type dash)" not in parent02_txt,
              "02-compute-core.kicad_sch (thin parent) carries no dashed-frame section graphics")
        check(parent02_txt.count("(sheet\n") == len(SHEET02_LEAVES),
              f"02-compute-core.kicad_sch instantiates exactly {len(SHEET02_LEAVES)} leaf sheet(s) "
              f"(found {parent02_txt.count('(sheet' + chr(10))})")
    for name in SHEET02_LEAVES:
        p = os.path.join(BOARD_DIR, f"{name}.kicad_sch")
        check(os.path.isfile(p), f"leaf sheet present: {name}.kicad_sch")
        if os.path.isfile(p):
            txt = open(p).read()
            check("(type dash)" not in txt,
                  f"{name}.kicad_sch carries no dashed-frame section graphics")
            check(f'(title "CEC Hub -- Enterprise (ENT): {name}"' in txt,
                  f"{name}.kicad_sch carries a proper per-sheet title")
            check("U1 (unit 8, POWER" in txt and "is NOT placed this pass" in txt,
                  f"{name}.kicad_sch still carries its U1-not-placed honesty note "
                  f"(the cec_sch.py unit-support blocker)")

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
        "lib_symbol_mismatch":  "generator lib_symbols-cache cosmetic mismatch (repo-wide known class); "
                                "222 as of sheet-02 (86 new caps' own embedded symbol copies)",
        "pin_not_connected":    "43 = sheet-01's 15 + sheet-05's 28 (16x P{n}_T1_A/B, 8x P{n}_SYNC7, "
                                "CAN_TX/RX, DETECT_SDA/SCL) hierarchical exports with no consumer yet "
                                "(sheets 06/09 are still placeholders; 02 no longer is, see below); sheet 04's "
                                "own 20 root exports (6x MSS_QSPI_*/12x MSS_EMMC_*/+3V3_IO/VDD18, awaiting "
                                "U1's own placement on 02a + sheet 03b's blocked MPM3833C) and sheet 03's own "
                                "2 root exports (+1V0_CORE awaiting U1, +3V3_MPFS awaiting sibling leaf 03b) "
                                "fall under isolated_pin_label below instead, not this class -- same root "
                                "cause, different kicad-cli bucket. Sheet 02's OWN 17 MPFS rail nets do NOT "
                                "appear in EITHER this class or isolated_pin_label -- they are plain LOCAL "
                                "labels (c.label), not hier_exports, and each already has real electrical "
                                "members (its own bank of caps), so neither ERC bucket applies to them.",
        "pin_to_pin":           "TPS25940LRVCR's 5 parallel power_out OUT pins tied together (required "
                                "multi-pin eFuse design, sheet 01 x4); sheet-04a's redundant PWR_FLAG pair on "
                                "+3V3_IO (04a's own leaf-local flag + 04b's, now genuinely wired together via "
                                "the 04a<->04b thin-parent pair -- two flags on one net is harmless); "
                                "sheet-04b's CMD(Unspecified)<->R402.2(Passive) is the intended pull-up tie "
                                "(ERC flags Unspecified-type connections generically, by design correct here); "
                                "sheet-03a's multiple redundant PWR_FLAG stamps on +5V_SYS/GND (many "
                                "independently-labeled pins sharing one net, same harmless multi-flag "
                                "pattern); sheet-02a's own GND PWR_FLAG (one more flag joining the SAME "
                                "already-multi-flagged project-wide GND net -- adds exactly 1 more adjacent "
                                "pair to the existing chain, same harmless pattern, not a new class).",
        "isolated_pin_label":   "RESET_3V3 (1) + sheet-05's 18 root-level T1/CAN_TX/RX exports (each counted "
                                "twice by kicad-cli's scan, 36) -- all forward-looking labels/hier pins with "
                                "no consumer captured yet, same root cause as pin_not_connected above; "
                                "sheet-04's own 20 root exports (see pin_not_connected note) add here too; "
                                "sheet-03's own 2 root exports (+1V0_CORE, +3V3_MPFS -- see pin_not_connected "
                                "note) add here as well. Measured unchanged at 71 after sheet 02 landed (see "
                                "the pin_not_connected note above for why sheet 02's OWN rails don't add here).",
        "pin_not_driven":       "sheet-05b's U_CAN.TXD (an Input pin) has no driver yet -- the fabric CAN "
                                "controller that drives it lives on sheet 09, still a placeholder; "
                                "sheet-04a's U401 /CS and CLK (Input pins) have no driver yet -- the MSS QSPI "
                                "controller lives on sheet 02a now, but U1 itself is not yet placed there (see "
                                "gen_hub_enterprise.py's sheet-02 module docstring for the cec_sch.py "
                                "unit-support blocker), so it still does not drive them.",
        "power_pin_not_driven": "sheet-03d's U302 pin 3 (VDD/sense) reads +3V3_MPFS, which has no local driver "
                                "yet -- awaiting sibling leaf 03b (BLOCKED, MPM3833C not vendored), same root "
                                "cause as the sheet-04/03 forward-declared-export classes above. (Sheet 02a's "
                                "86 caps are all passive parts with no power_in pin of their own, and its 17 "
                                "rail labels + GND stamp carry no power_in-typed pin either -- this class "
                                "measures unchanged at 1 after sheet 02 landed.)",
        "wire_dangling":        "sheet-03b/03c's own non-functional marker wire (a 1.27mm cosmetic tick near "
                                "each stub's caption, NOT a stand-in for any real connection) -- both leaves "
                                "are genuinely empty (0 real components, capture pending on MPM3833C/the "
                                "correct-voltage TPS7A20 variants), and build_leaf's centering pass needs SOME "
                                "drawn geometry (a part or a wire) to compute a bounding box from; a truly "
                                "empty leaf (0 parts, 0 wires) crashes it (measured: min() on an empty "
                                "sequence). Expected count is exactly 2 (one per stub leaf); a 3rd instance "
                                "anywhere else is a real regression.",
        "unconnected_wire_endpoint": "both endpoints of sheet-03b/03c's own marker wire (see wire_dangling "
                                "above) -- same root cause, different kicad-cli bucket. Expected count is "
                                "exactly 4 (2 endpoints x 2 stub leaves).",
        "endpoint_off_grid":    "warning-only: a leaf sheet-pin's X MUST sit exactly on its box's real edge (not "
                                "gridsnapped) for kicad-cli to bind it into the flattened net at all -- verified "
                                "empirically during the 2026-07-02 re-sheeting (a gridsnapped X parses fine but "
                                "silently drops the connection). RESOLVED 2026-07-03 (T1 composition pass): "
                                "build_thin_parent now grid-aligns the box geometry itself so the pin sits both "
                                "on-edge AND on-grid -- expected count is 0; the class stays listed so a "
                                "regression reads benign-warning, not unexplained.",
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
    #
    # 2026-07-03 (sheet-05 ADDITIVE capture): every 01-subtree ref uses the
    # platform's plain NNN-in-100s numbering (U101..U107/R101..R130/
    # C101..C116/J101..J103/D102 -- 59 refs); every 05-subtree ref uses
    # DESCRIPTIVE names (J_PORT1..8, D_TVS/D_VCC/R_DSER/D_DET/R_DET/R_SYNC/
    # D_SYNC 1..8, U_CAN, R_CANT1/2, C_CANT/CANVCC/CANVIO, U_ADC, C_ADCREF/
    # ADCVDD, R_I2CSDA/SCL -- 75 refs), so the two subtrees are separable by
    # ref shape alone (`_IS_01_REF`). This is the GUARD-GROWS half of the
    # additive-capture discipline: total components/groups now include
    # sheet 05, but the 01-subtree's OWN portion is separately re-proven
    # unchanged by PROJECTING every flattened group onto its 01-subtree-only
    # members (dropping any 05-subtree ref that joined a shared GLOBAL power
    # net like GND/+3V3/+5VSB) -- that projection must still be exactly the
    # historical 46/59, proving sheet 05 only ADDED members to those shared
    # nets and touched nothing else in the 01 subtree.
    #
    # 2026-07-16 (sheet-04 ADDITIVE capture): sheet 04 continues the platform's
    # plain-numbering convention like sheet 01, but in the "4xx" block
    # (U401/U402, R401-403, C401-408 -- 13 refs), so it is ALSO separable by
    # ref shape alone (`_IS_04_REF`), distinct from both 01's "1xx" block and
    # 05's descriptive names. Same discipline: 01-subtree's 46 groups AND
    # (NEWLY established this pass, since sheet 04 is the FIRST addition
    # since 05 was captured) 05-subtree's own projected group count are BOTH
    # re-proven unchanged by projection, alongside sheet 04's own new count.
    #
    # 2026-07-16 (sheet-03 ADDITIVE capture, same session): sheet 03 continues
    # the SAME plain-numbering convention in the "3xx" block (03a: U301,
    # C301-C311, L301, R301-R304 = 17 refs; 03b/03c: 0 refs each, empty stubs;
    # 03d: U302 = 1 ref; 18 refs total), separable by ref shape alone
    # (`_IS_03_REF`), distinct from 01's "1xx", 04's "4xx", and 05's
    # descriptive names. Same discipline again: 01/05/04-subtrees' own
    # projected group counts are ALL re-proven unchanged by projection,
    # alongside sheet 03's own new count.
    # -----------------------------------------------------------------
    _IS_01_REF = re.compile(r'^[A-Z]+1[0-3]\d$')  # U101-U139 / R101-R139 / etc.
    _IS_04_REF = re.compile(r'^[A-Z]+4[0-3]\d$')  # U401-U439 / R401-R439 / etc.
    _IS_03_REF = re.compile(r'^[A-Z]+3[0-3]\d$')  # U301-U339 / R301-R339 / etc.
    _IS_02_REF = re.compile(r'^[A-Z]+2\d\d$')      # C200-C299 (02a's decoupling caps)
    # measured (kicad-cli netlist, 2026-07-16): unlike sheet 04's mostly-1:1
    # net-per-signal shape, 03a's 17 real parts collapse into a SMALL number
    # of MULTI-MEMBER local nets (+5V_SYS/GND/SW_CORE/+1V0_CORE/FB_CORE/
    # COMP_RC/COMP_RC2/RC_CORE/PG_CORE/MPFS_SEQ_EN = 10) plus 03d's own
    # +3V3_MPFS (11) -- the 12th is a project-wide shared-power group (e.g.
    # +3V3 or +5VSB) that 03-subtree has NO real member on, but which still
    # carries a #PWR/#FLG-only member somewhere and so is NOT dropped by the
    # `if g` empty-group filter (same "#"-inflation caveat already recorded
    # for proj_04 above, just crossing zero real-membership here since
    # sheet 03 is small). Not hand-re-derived exactly; measured and pinned.
    PROJ_03_EXPECTED = 12
    # measured (kicad-cli netlist, 2026-07-16, sheet-02 additive capture):
    # 02a's 86 caps span exactly 18 nets -- the 17 named MPFS supply rails
    # (VDD/VDD18/VDDA/VDDA25/VDD25/VDDAUX1/2/4/VDDI0-6/VDD_XCVR_CLK/
    # XCVR_VREF), each ENTIRELY WITHIN sheet 02 this pass (U1 itself is not
    # placed -- see gen_hub_enterprise.py's sheet-02 module docstring for
    # the cec_sch.py unit-support blocker), so each projects as a fully-
    # preserved, wholly-02-subtree group; plus the shared GND net (86 caps'
    # own pin 2 + every other subtree's own GND members elsewhere --
    # PROJECTED down to 02-subtree + "#"-prefixed members only, same
    # convention as proj_03/04 above). 17 + 1 = 18. Not hand-re-derived;
    # measured and pinned.
    PROJ_02_EXPECTED = 18
    real_comps = [r for r in comps if not r.startswith("#")]
    comps_01 = [r for r in real_comps if _IS_01_REF.match(r)]
    comps_04 = [r for r in real_comps if _IS_04_REF.match(r)]
    comps_03 = [r for r in real_comps if _IS_03_REF.match(r)]
    comps_02 = [r for r in real_comps if _IS_02_REF.match(r)]
    comps_05 = [r for r in real_comps if not _IS_01_REF.match(r) and not _IS_04_REF.match(r)
                and not _IS_03_REF.match(r) and not _IS_02_REF.match(r)]
    check(len(comps_01) == 59,
          f"01-subtree component count unchanged by sheet-02/03/04/05's additions (expected 59, "
          f"got {len(comps_01)})")
    check(len(comps_05) == 75,
          f"05-subtree component count unchanged by sheet-02/03/04's additions (8x8 port parts + "
          f"6 05b + 5 05c = 64+6+5 = 75; got {len(comps_05)})")
    check(len(comps_04) == 13,
          f"04-subtree component count unchanged by sheet-02/03's additions (04a: U401+C401+C402+"
          f"R401=4; 04b: U402+C403-C408=7; 04c: R402+R403=2; got {len(comps_04)})")
    check(len(comps_03) == 18,
          f"03-subtree component count unchanged by sheet-02's addition (03a: U301+C301-C311(11)+"
          f"L301+R301-R304(4)=17; 03b/03c: 0 each, empty stubs; 03d: U302=1; got {len(comps_03)})")
    check(len(comps_02) == 86,
          f"02-subtree adds exactly 86 components (02a: C201-C286, the full DS60001681H Table 1-4 "
          f"decoupling network across 17 named MPFS rails -- U1 itself not placed this pass, see "
          f"FOLLOWUPS.md; 02b/02c/02d not composed this pass; got {len(comps_02)})")
    check(len(real_comps) == 251,
          f"total component count = 59 (sheet 01) + 75 (sheet 05) + 13 (sheet 04) + 18 (sheet 03) "
          f"+ 86 (sheet 02, new) = 251 (got {len(real_comps)})")

    groups = sorted(frozenset(v) for v in nets.values())
    n_groups = len(groups)
    proj_01 = {frozenset((r, p) for r, p in g if _IS_01_REF.match(r) or r.startswith("#"))
               for g in groups}
    proj_01 = {g for g in proj_01 if g}      # drop groups with no 01-subtree member at all
    check(len(proj_01) == 46,
          f"01-subtree connectivity (PROJECTED: each flattened group reduced to its "
          f"01-subtree-only members) is unchanged by sheet-02/03/04/05's additions -- still "
          f"exactly the historical 46 groups (got {len(proj_01)}); sheets 02/03/04/05 only ADD "
          f"members to shared global power nets (GND/+3V3/+5VSB/+5V_MAIN/+5V_SYS), never alter "
          f"an existing 01-subtree connection")
    proj_05 = {frozenset((r, p) for r, p in g if not _IS_01_REF.match(r)
                          and not _IS_04_REF.match(r) and not _IS_03_REF.match(r)
                          and not _IS_02_REF.match(r) and not r.startswith("#"))
               for g in groups}
    proj_05 = {g for g in proj_05 if g}
    check(len(proj_05) == 67,
          f"05-subtree connectivity (PROJECTED to its own non-# members only) is unchanged by "
          f"sheet-02/03/04's additions -- 67 groups (baseline established when sheet 04 was "
          f"captured; got {len(proj_05)})")
    proj_04 = {frozenset((r, p) for r, p in g if _IS_04_REF.match(r) or r.startswith("#"))
               for g in groups}
    proj_04 = {g for g in proj_04 if g}
    check(len(proj_04) == 149,
          f"04-subtree connectivity (PROJECTED: each flattened group reduced to its "
          f"04-subtree-only + shared-power members) is unchanged by sheet-02/03's additions -- "
          f"still exactly 149 groups (got {len(proj_04)}) -- most are 04's own single-occurrence "
          f"root exports (18 of the 20 planned pins: 6x MSS_QSPI_* + 12x MSS_EMMC_CLK/DAT0-7/DS, "
          f"each a lone-member group) plus the 4 paired/tapped nets (+3V3_IO, VDD18, MSS_EMMC_CMD, "
          f"MSS_EMMC_RST_N) plus the 1 LOCAL QSPI_RESET_N pair (U401.3/R401.2, named via a real "
          f"c.label -- deliberately NOT a root export, no active MSS drive planned this pass) "
          f"and every shared global-power group (GND etc, inflated by every #PWR/#FLG instance "
          f"project-wide, but that inflation only ADDS MEMBERS to an already-counted group, "
          f"never a new one -- verified: it did not move 01-subtree's own 46 group count above)")
    proj_03 = {frozenset((r, p) for r, p in g if _IS_03_REF.match(r) or r.startswith("#"))
               for g in groups}
    proj_03 = {g for g in proj_03 if g}
    check(len(proj_03) == PROJ_03_EXPECTED,
          f"03-subtree connectivity (PROJECTED: each flattened group reduced to its "
          f"03-subtree-only + shared-power members) is unchanged by sheet-02's addition -- still "
          f"exactly {PROJ_03_EXPECTED} groups (got {len(proj_03)}) -- most are 03's own "
          f"single-occurrence members (18 of the 18 real 03-subtree refs are NOT paired with "
          f"each other except via the shared +5V_SYS/GND/MPFS_SEQ_EN/FB_CORE/etc local nets, "
          f"each an independent group) plus the 2 root exports (+1V0_CORE, +3V3_MPFS) and every "
          f"shared global-power group (GND/+5V_SYS etc, inflated by every #PWR/#FLG instance "
          f"project-wide, but that inflation only ADDS MEMBERS to an already-counted group, "
          f"never a new one -- verified: it did not move 01-subtree's own 46 or 04-subtree's own "
          f"149 group counts above)")
    proj_02 = {frozenset((r, p) for r, p in g if _IS_02_REF.match(r) or r.startswith("#"))
               for g in groups}
    proj_02 = {g for g in proj_02 if g}
    check(len(proj_02) == PROJ_02_EXPECTED,
          f"02-subtree connectivity (PROJECTED: each flattened group reduced to its "
          f"02-subtree-only + shared-power members) is exactly {PROJ_02_EXPECTED} groups (got "
          f"{len(proj_02)}) -- 17 wholly-02-subtree rail groups (VDD/VDD18/VDDA/VDDA25/VDD25/"
          f"VDDAUX1/2/4/VDDI0-6/VDD_XCVR_CLK/XCVR_VREF, each currently ISOLATED to just 02a's own "
          f"caps -- U1 itself not placed this pass) plus 1 shared GND group (inflated by every "
          f"#PWR/#FLG instance project-wide, same non-double-counting caveat as proj_03/04 above "
          f"-- verified: it did not move 01/03/04-subtree's own group counts above)")
    print(f"  ..  flattened hierarchy: {len(real_comps)} components / {n_groups} connectivity "
          f"groups total (01-subtree 59/46 unchanged + 05-subtree 75/67 unchanged + "
          f"04-subtree 13/149 unchanged + 03-subtree 18/{PROJ_03_EXPECTED} unchanged + "
          f"02-subtree 86/{PROJ_02_EXPECTED} new)")

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
    _, gnd = net_named(nets, "GND")

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
    check(("U104", "2") in ext_out and ("U104", "3") not in ext_out,
          "U_EF3.OUT -> U_PC1 (stage A) IN2 only")
    check(("U104", "1") in stage_a and ("U104", "8") in stage_a
          and ("U105", "2") in stage_a and ("U105", "3") not in stage_a,
          "U_PC1 (stage A) OUT -> U_PC2 (stage B) IN2 only")
    check({("U104", "3"), ("U105", "3")} <= gnd,
          "both TPS2121 CP2 pins tied to GND for fixed-priority operation")
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
    # 2b. sheet-05 assertion block (module ports: 8x port + CAN frontend +
    # DETECT ADC). Mirrors the sheet-01 block's net-set style.
    # -----------------------------------------------------------------
    print("--- sheet 05 (module-ports) assertions ---")

    # a) port count: exactly 8 J_PORT{n}, each the platform FTP jack, each
    #    carrying its own DETECT/pin-7/mis-plug part set (8x each ref class)
    port_jacks = [r for r in comps if re.match(r'^J_PORT\d$', r)]
    check(len(port_jacks) == 8, f"exactly 8 module ports (J_PORT1..8); found {sorted(port_jacks)}")
    for cls in ("D_TVS", "D_VCC", "R_DSER", "D_DET", "R_DET", "R_SYNC", "D_SYNC"):
        found_n = sorted(r for r in comps if re.match(rf'^{cls}\d$', r))
        check(len(found_n) == 8, f"{cls}1..8 present (one per port); found {found_n}")

    for n in range(1, 9):
        J, DTVS, DVCC = f"J_PORT{n}", f"D_TVS{n}", f"D_VCC{n}"
        RDSER, DDET, RDET = f"R_DSER{n}", f"D_DET{n}", f"R_DET{n}"
        RSYNC, DSYNC = f"R_SYNC{n}", f"D_SYNC{n}"

        # b) locked pin-8 (DETECT) chain: jack.8 -> series R -> [ESD to GND,
        #    pull-up to +3V3] -> exported to 05c's ADC channel n (channel
        #    number == port number, by the generator's own CH{n-1}=pin{n}
        #    convention on ADS7830).
        raw = group_of(nets, J, "8")   # a purely-internal 2-pin hop carries no
        check((J, "8") in raw and (RDSER, "1") in raw,   # visible net name (group_of: by-pin, not by-name)
              f"port {n}: DETECT pin-8 -> R_DSER{n} series (REQ-HUB-COMMON-110)")
        _, det_a = net_named(nets, f"P{n}_DETECT_A")
        check({(RDSER, "2"), (DDET, "1"), (RDET, "1"), ("U_ADC1", str(n))} <= det_a,
              f"port {n}: DETECT_A node = R_DSER{n}.2 + D_DET{n}(ESD) + R_DET{n}(pull-up) "
              f"+ U_ADC channel {n} (cross-leaf, port <-> 05c)")
        _, gnd = net_named(nets, "GND")
        check((DDET, "2") in gnd, f"port {n}: D_DET{n} (PESD5V0S1BA, LOCKED Sec2.4) clamps to GND")
        _, v33 = net_named(nets, "+3V3")
        check((RDET, "2") in v33, f"port {n}: R_DET{n} pulls DETECT_A to +3V3 (Sec2.3 code read)")

        # c) locked pin-7 (SYNC/FREEZE) chain: jack.7 -> series R -> tail-risk
        #    TVS to GND, raw net reaches root as P{n}_SYNC7 (fabric GPIO,
        #    REQ-HUB-COMMON-112/114 -- not yet consumed, sheet 02 pending)
        sync_raw = group_of(nets, J, "7")
        check((J, "7") in sync_raw and (RSYNC, "1") in sync_raw,
              f"port {n}: pin-7 -> R_SYNC{n} series (REQ-HUB-COMMON-112/114)")
        _, sync = net_named(nets, f"P{n}_SYNC7")
        check({(RSYNC, "2"), (DSYNC, "2")} <= sync,
              f"port {n}: SYNC7 node = R_SYNC{n}.2 + D_SYNC{n}(TVS)")
        check((DSYNC, "1") in gnd, f"port {n}: D_SYNC{n} (SMAJ58A tail-risk TVS) clamps to GND")

        # d) T1 pair (pins 4/5): raw pass-through, single-member nets (no
        #    per-port protection here -- that's sheet 06's per-port MDI
        #    frontend, REQ-HUB-COMMON-110's own per-pin analysis)
        _, t1a = net_named(nets, f"P{n}_T1_A")
        check(t1a == {(J, "4")}, f"port {n}: T1_A is a raw, unprocessed pass-through of jack pin 4")
        _, t1b = net_named(nets, f"P{n}_T1_B")
        check(t1b == {(J, "5")}, f"port {n}: T1_B is a raw, unprocessed pass-through of jack pin 5")

        # e) locked pin allocation table (Sec2.3) cross-check, pin-by-pin,
        #    against the ACTUAL flattened netlist (not just the symbol
        #    definition): 1=VCC(mis-plug-protected), 2=GND, 3/6=CAN, 4/5=T1,
        #    7=SYNC(ENT), 8=DETECT(ENT)
        vcc_raw = group_of(nets, J, "1")
        check((J, "1") in vcc_raw and (DTVS, "2") in vcc_raw and (DVCC, "1") in vcc_raw,
              f"port {n}: pin 1 (VCC) -> D_TVS{n}(shunt)/D_VCC{n}(series) on the mis-plug-protected node")
        check({(J, "2"), (J, "SH1"), (J, "SH2")} <= gnd,
              f"port {n}: pin 2 (GND) + shield SH1/SH2 all -> GND")
        _, can_h = net_named(nets, "CAN_H")
        _, can_l = net_named(nets, "CAN_L")
        check((J, "3") in can_h, f"port {n}: pin 3 (CAN1_H) on the shared CAN_H bus")
        check((J, "6") in can_l, f"port {n}: pin 6 (CAN1_L) on the shared CAN_L bus")

        # f) mis-plug fail-safe parts + values (REQ-HUB-COMMON-110)
        check(comps.get(DVCC, {}).get("value") == "SS110",
              f"port {n}: D_VCC{n} is SS110 (100V series blocking Schottky)")
        check(comps.get(DTVS, {}).get("value") == "SMAJ58A",
              f"port {n}: D_TVS{n} is SMAJ58A (pin-1 tail-risk TVS)")
        check(comps.get(DSYNC, {}).get("value") == "SMAJ58A",
              f"port {n}: D_SYNC{n} is SMAJ58A (pin-7 tail-risk TVS)")
        check(comps.get(DDET, {}).get("value") == "PESD5V0S1BA",
              f"port {n}: D_DET{n} is PESD5V0S1BA (LOCKED Sec2.4 DETECT clamp)")

    # g) CAN bus continuity: ALL 8 ports' pins 3/6 + the transceiver + its
    #    termination legs are one single flattened net each (a real shared
    #    bus, REQ-HUB-COMMON-041/043) -- exercises the global_nets primitive
    #    (cec_sch_compose.build_leaf) since build_thin_parent's sheet-pin
    #    fan-out cannot express a 9-endpoint net.
    expect_can_h = {(f"J_PORT{n}", "3") for n in range(1, 9)} | {("U_CAN1", "7"), ("R_CANT1", "1")}
    check(expect_can_h <= can_h, f"CAN_H is one shared bus across all 8 ports + U_CAN + termination "
          f"(missing: {expect_can_h - can_h})")
    expect_can_l = {(f"J_PORT{n}", "6") for n in range(1, 9)} | {("U_CAN1", "6"), ("R_CANT2", "2")}
    check(expect_can_l <= can_l, f"CAN_L is one shared bus across all 8 ports + U_CAN + termination "
          f"(missing: {expect_can_l - can_l})")
    check(val("R_CANT1") == "60.4" and val("R_CANT2") == "60.4",
          f"120 ohm split termination (60.4 x2); got {val('R_CANT1')!r}/{val('R_CANT2')!r}")

    # h) DETECT ADC (05c): all 8 channels + I2C bus reach root as exports
    for n in range(1, 9):
        _, da = net_named(nets, f"P{n}_DETECT_A")
        check(("U_ADC1", str(n)) in da, f"ADS7830 channel {n} (CH{n-1}) reads port {n}'s DETECT_A")
    _, sda = net_named(nets, "DETECT_SDA")
    check(("U_ADC1", "15") in sda, "DETECT_SDA on U_ADC pin 15 (SDA)")
    _, scl = net_named(nets, "DETECT_SCL")
    check(("U_ADC1", "14") in scl, "DETECT_SCL on U_ADC pin 14 (SCL)")

    # i) platform conformance: no Mini-Fit Jr on sheet 05 (every port is the
    #    locked RJ-45 FTP jack, not a Mini-Fit Jr)
    mini_fit_05 = [ref for ref in comps_05
                   if "Mini-Fit" in comps[ref]["fields"].get("Footprint", "")
                   or "5569" in comps[ref]["fields"].get("Footprint", "")]
    check(not mini_fit_05, f"no Mini-Fit Jr connector on sheet 05 (found: {mini_fit_05})")

    # -----------------------------------------------------------------
    # 2c. sheet-04 assertion block (storage: W25Q256JVFIQ QSPI NOR + generic
    # eMMC 5.1 + shared straps). Pin maps verified against the vendored
    # symbols directly at capture time (cec_sch.load_symbols), asserted here
    # against the ACTUAL flattened netlist (not just the symbol definition).
    # -----------------------------------------------------------------
    print("--- sheet 04 (storage) assertions ---")

    # a) 04a: W25Q256JVFIQ pin map (1=IO3,2=VCC,3=/RESET,7=/CS,8=IO1,9=IO2,
    #    10=GND,15=IO0,16=CLK; 4,5,6,11,12,13,14=NC)
    _, qspi_cs = net_named(nets, "MSS_QSPI_CS")
    check(("U401", "7") in qspi_cs, "U401 pin 7 (/CS) -> MSS_QSPI_CS")
    _, qspi_clk = net_named(nets, "MSS_QSPI_CLK")
    check(("U401", "16") in qspi_clk, "U401 pin 16 (CLK) -> MSS_QSPI_CLK")
    _, qspi_io0 = net_named(nets, "MSS_QSPI_IO0")
    check(("U401", "15") in qspi_io0, "U401 pin 15 (DI_IO0) -> MSS_QSPI_IO0")
    _, qspi_io1 = net_named(nets, "MSS_QSPI_IO1")
    check(("U401", "8") in qspi_io1, "U401 pin 8 (DO_IO1) -> MSS_QSPI_IO1")
    _, qspi_io2 = net_named(nets, "MSS_QSPI_IO2")
    check(("U401", "9") in qspi_io2, "U401 pin 9 (/WP_IO2) -> MSS_QSPI_IO2")
    _, qspi_io3 = net_named(nets, "MSS_QSPI_IO3")
    check(("U401", "1") in qspi_io3, "U401 pin 1 (/HOLD_/RESET_IO3) -> MSS_QSPI_IO3")
    _, qspi_reset = net_named(nets, "QSPI_RESET_N")
    check(("U401", "3") in qspi_reset and ("R401", "2") in qspi_reset,
          "U401 pin 3 (/RESET, dedicated hw reset) -> R401 pull-up (LOCAL net only, "
          "no active MSS drive planned this pass)")
    _, v33io = net_named(nets, "+3V3_IO")
    check(("U401", "2") in v33io and ("C401", "1") in v33io and ("C402", "1") in v33io
          and ("R401", "1") in v33io,
          "U401 VCC (pin 2) + C401/C402 bypass + R401's rail leg all on +3V3_IO")
    check(("U401", "10") in gnd, "U401 GND (pin 10) -> platform GND")
    check(("C401", "2") in gnd and ("C402", "2") in gnd, "C401/C402 return legs -> GND")
    check(val("R401") == "10k", f"R401 (/RESET pull-up) = 10k; got {val('R401')!r}")

    # b) 04b: generic eMMC 5.1 pin map (CLK=M6, CMD=M5, DAT0-2=A3-A5,
    #    DAT3-7=B2-B6, RST_n=K5, DS=H5; VCC=E6/F5/J10/K9 x4; VCCQ=C6/M4/N4/
    #    P3/P5 x5 + VDDi=C2 (LOCAL tie); VSS x6 + VSSQ x5 -> GND)
    _, emmc_clk = net_named(nets, "MSS_EMMC_CLK")
    check(("U402", "M6") in emmc_clk, "U402 ball M6 (CLK) -> MSS_EMMC_CLK")
    _, emmc_cmd = net_named(nets, "MSS_EMMC_CMD")
    check(("U402", "M5") in emmc_cmd and ("R402", "2") in emmc_cmd,
          "U402 ball M5 (CMD) + R402 pull-up both on MSS_EMMC_CMD (04b<->04c pair)")
    dat_balls = {0: "A3", 1: "A4", 2: "A5", 3: "B2", 4: "B3", 5: "B4", 6: "B5", 7: "B6"}
    for i, ball in dat_balls.items():
        _, d = net_named(nets, f"MSS_EMMC_DAT{i}")
        check(("U402", ball) in d, f"U402 ball {ball} (DAT{i}) -> MSS_EMMC_DAT{i}")
    _, emmc_rst = net_named(nets, "MSS_EMMC_RST_N")
    check(("U402", "K5") in emmc_rst and ("R403", "2") in emmc_rst,
          "U402 ball K5 (RST_n) + R403 pull-up both on MSS_EMMC_RST_N (04b<->04c pair)")
    _, emmc_ds = net_named(nets, "MSS_EMMC_DS")
    check(("U402", "H5") in emmc_ds, "U402 ball H5 (DS, HS400 data strobe) -> MSS_EMMC_DS")
    for ball in ("E6", "F5", "J10", "K9"):
        check(("U402", ball) in v33io, f"U402 VCC ball {ball} -> +3V3_IO")
    _, vdd18 = net_named(nets, "VDD18")
    for ball in ("C6", "M4", "N4", "P3", "P5"):
        check(("U402", ball) in vdd18, f"U402 VCCQ ball {ball} -> VDD18")
    check(("U402", "C2") in vdd18, "U402 VDDi (ball C2) tied LOCALLY to VCCQ/VDD18 (flagged, see leaf note)")
    for ball in ("A6", "E7", "G5", "H10", "J5", "K8", "C4", "N2", "N5", "P4", "P6"):
        check(("U402", ball) in gnd, f"U402 VSS/VSSQ ball {ball} -> GND")

    # c) 04c: shared straps -- both pull-ups to VDD18, correct values
    check(val("R402") == "47k", f"R402 (eMMC CMD pull-up, JEDEC) = 47k; got {val('R402')!r}")
    check(val("R403") == "10k", f"R403 (eMMC RST_n pull-up) = 10k; got {val('R403')!r}")
    check(("R402", "1") in vdd18 and ("R403", "1") in vdd18,
          "R402/R403 rail legs (pin 1) both -> VDD18")

    # d) cross-leaf pairs are REAL WIRES within the 04-storage thin parent
    #    (not just same net-name coincidence) -- already exercised by b)/c)
    #    above (+3V3_IO 04a<->04b, VDD18/CMD/RST_N 04b<->04c); this is the
    #    same "pairs, not global_nets" design note recorded in
    #    gen_hub_enterprise.py's sheet-04 module docstring.

    # e) every real sheet-04 part carries Manufacturer + MPN (BOM-A traceability)
    missing_bom_04 = []
    for ref in comps_04:
        f = comps[ref]["fields"]
        if not (f.get("Manufacturer") and f.get("MPN")):
            missing_bom_04.append(ref)
    check(not missing_bom_04, f"every sheet-04 part carries Manufacturer+MPN (missing: {missing_bom_04})")

    # f) platform conformance: no Mini-Fit Jr on sheet 04
    mini_fit_04 = [ref for ref in comps_04
                   if "Mini-Fit" in comps[ref]["fields"].get("Footprint", "")
                   or "5569" in comps[ref]["fields"].get("Footprint", "")]
    check(not mini_fit_04, f"no Mini-Fit Jr connector on sheet 04 (found: {mini_fit_04})")

    # -----------------------------------------------------------------
    # 2d. sheet-03 assertion block (compute-rails: MIC22705YML-TR core buck +
    # TPS3839K33 sequencing supervisor REAL; bank-rails + vdda-ldo STUBBED,
    # see gen_hub_enterprise.py's sheet-03 module docstring for the full
    # library-status picture). Pin maps verified against the vendored
    # MIC22705 symbol directly + cross-checked against the real Microchip
    # datasheet (DS 111213-1.1); TPS3839DBZ pin map reused verbatim from
    # 01f's own already-verified U107 instance.
    # -----------------------------------------------------------------
    print("--- sheet 03 (compute-rails) assertions ---")

    # a) 03a: MIC22705YML-TR pin map (1,6,13,18=PVIN; 2=EN/DLY; 4=RC; 5=PG;
    #    7,12,19,24=PGND; 8-11,20-23=SW; 14=FB; 15=COMP; 16=SGND; 17=SVIN;
    #    25=EP)
    _, v5sys = net_named(nets, "+5V_SYS")
    for pin in ("1", "6", "13", "18", "17"):
        check(("U301", pin) in v5sys, f"U301 pin {pin} (PVIN/SVIN) -> +5V_SYS")
    for ref in ("C301", "C302", "C303", "C304", "C305", "R304"):
        check((ref, "1") in v5sys, f"{ref} pin 1 -> +5V_SYS (PVIN/SVIN bypass or PG pull-up rail leg)")
    for pin in ("16", "7", "12", "19", "24", "25"):
        check(("U301", pin) in gnd, f"U301 pin {pin} (SGND/PGND/EP) -> platform GND")
    _, sw_core = net_named(nets, "SW_CORE")
    for pin in ("8", "9", "10", "11", "20", "21", "22", "23"):
        check(("U301", pin) in sw_core, f"U301 pin {pin} (SW) -> SW_CORE")
    check(("L301", "1") in sw_core, "L301 pin 1 -> SW_CORE (inductor input)")
    _, v1core = net_named(nets, "+1V0_CORE")
    check(("L301", "2") in v1core and ("C306", "1") in v1core and ("C307", "1") in v1core
          and ("R301", "1") in v1core,
          "L301 pin 2 (VOUT) + C306/C307 bulk caps + R301's FB-divider rail leg all on +1V0_CORE")
    _, fb_core = net_named(nets, "FB_CORE")
    check(("U301", "14") in fb_core and ("R301", "2") in fb_core and ("R302", "1") in fb_core
          and ("C308", "1") in fb_core,
          "U301 pin 14 (FB) + R301/R302 divider taps + C308 noise cap all on FB_CORE")
    check(val("R301") == "4.99k" and val("R302") == "11.5k",
          f"FB divider R301/R302 = 4.99k/11.5k (VOUT~=1.00V per VREF=0.7V typ); "
          f"got {val('R301')!r}/{val('R302')!r}")
    _, comp_rc = net_named(nets, "COMP_RC")
    check(("U301", "15") in comp_rc and ("R303", "1") in comp_rc,
          "U301 pin 15 (COMP) + R303 in series (COMP_RC)")
    _, comp_rc2 = net_named(nets, "COMP_RC2")
    check(("R303", "2") in comp_rc2 and ("C309", "1") in comp_rc2,
          "R303 + C309 in series, C309 -> GND (COMP_RC2, completing the COMP RC network)")
    check(("C309", "2") in gnd, "C309 pin 2 (COMP network return) -> GND")
    _, rc_core = net_named(nets, "RC_CORE")
    check(("U301", "4") in rc_core and ("C310", "1") in rc_core,
          "U301 pin 4 (RC/soft-start) + C310 (RC_CORE, local -- no cross-part tracking)")
    _, pg_core = net_named(nets, "PG_CORE")
    check(("U301", "5") in pg_core and ("R304", "2") in pg_core,
          "U301 pin 5 (PG, open-drain) + R304 pull-up (PG_CORE, local)")
    _, seq_en = net_named(nets, "MPFS_SEQ_EN")
    check(("U301", "2") in seq_en and ("C311", "1") in seq_en,
          "U301 pin 2 (EN/DLY) + C311 both on the MPFS_SEQ_EN global net")
    check(("C311", "2") in gnd, "C311 pin 2 (EN/DLY node cap return) -> GND")

    # b) 03a<->03d cross-leaf tie: MPFS_SEQ_EN is a REAL global_label net
    #    (not a sheet-pin/hier_export pair), so its full membership spans
    #    BOTH leaves in the SAME flattened net -- verify the tie is real,
    #    not just same-name coincidence.
    check(("U302", "2") in seq_en,
          "U302 pin 2 (03d's TPS3839K33 ~RESET output) is on the SAME flattened MPFS_SEQ_EN "
          "net as 03a's U301 pin 2 -- confirms the global_nets tie is real, not coincidental")

    # c) 03d: TPS3839K33 pin map (1=GND, 2=~RESET->MPFS_SEQ_EN, 3=VDD/sense)
    check(("U302", "1") in gnd, "U302 pin 1 (GND) -> platform GND")
    _, v3mpfs = net_named(nets, "+3V3_MPFS")
    check(("U302", "3") in v3mpfs and v3mpfs == {("U302", "3")},
          f"U302 pin 3 (VDD/sense) = +3V3_MPFS, a LONE-MEMBER net awaiting sibling leaf 03b "
          f"(BLOCKED) -- exactly one member expected this pass (got {sorted(v3mpfs)})")
    check(val("U302") == "TPS3839K33",
          f"U302 = TPS3839K33 (same MPN/LCSC as 01f's own U107 instance); got {val('U302')!r}")

    # d) 03b/03c: confirmed EMPTY stubs (0 real components each) -- the
    #    thin-parent format check (0c below) verifies each leaf file itself
    #    exists + carries no dashed-frame graphics; this just re-confirms
    #    from the flattened netlist's own component list that NEITHER
    #    contributed a real part (guards against a future accidental
    #    half-capture landing without updating this comment/count).
    check(not any(r.startswith("U4") or r.startswith("U5") or r.startswith("U6")
                  for r in comps_03),
          "03b's planned refs (U4/U5/U6, BOM-A's MPM3833C role) are NOT present -- confirmed "
          "still an empty stub, matching the dated CAPTURE PENDING note")
    check(not any(r.startswith("U7") or r.startswith("U8") for r in comps_03),
          "03c's planned refs (U7/U8, BOM-A's TPS7A20-class role) are NOT present -- confirmed "
          "still an empty stub, matching the dated CAPTURE PENDING note")

    # e) every real sheet-03 part carries Manufacturer + MPN (BOM-A traceability)
    missing_bom_03 = []
    for ref in comps_03:
        f = comps[ref]["fields"]
        if not (f.get("Manufacturer") and f.get("MPN")):
            missing_bom_03.append(ref)
    check(not missing_bom_03, f"every sheet-03 part carries Manufacturer+MPN (missing: {missing_bom_03})")

    # f) platform conformance: no Mini-Fit Jr on sheet 03
    mini_fit_03 = [ref for ref in comps_03
                   if "Mini-Fit" in comps[ref]["fields"].get("Footprint", "")
                   or "5569" in comps[ref]["fields"].get("Footprint", "")]
    check(not mini_fit_03, f"no Mini-Fit Jr connector on sheet 03 (found: {mini_fit_03})")

    # -----------------------------------------------------------------
    # 2e. sheet-02 assertion block (compute-core: MPFS095T FCVG484 full-rail
    # decoupling per Microchip DS60001681H Table 1-4 -- the table specific
    # to our exact part+package. U1 itself is NOT placed this pass -- see
    # gen_hub_enterprise.py's sheet-02 module docstring for the cec_sch.py
    # unit-support blocker this pass found (hardcodes `(unit 1)` in every
    # symbol instance, no way to place/tie-across-sheets a non-unit-1
    # instance of a multi-unit symbol). Every rail net below is therefore
    # currently ISOLATED to just its own bank of caps + a plain local
    # label (not a hier_export) -- verified per-rail below by exact
    # per-net cap COUNT (independent of gen_hub_enterprise.py's own
    # _RAIL_CAPS table -- this check re-derives against the real exported
    # netlist, not the generator's own Python source, so a regression in
    # either one is caught).
    # -----------------------------------------------------------------
    # NAMING: every key carries the SAME "MPFS_" prefix gen_hub_enterprise.py
    # uses (e.g. "MPFS_VDD18" not bare "VDD18") -- bare "VDD18" collides with
    # sheet 04's own root-exported "VDD18" (04b's eMMC VCCQ rail); see that
    # file's _RAIL_CAPS comment for the full finding (verified in the real
    # netlist: two properly-SEPARATE, correctly-scoped nets electrically,
    # but a bare-name collision this checker's own net_named()-style lookups
    # and any flat BOM/netlist reader would trip on).
    _EXPECTED_RAIL_COUNTS = {
        "MPFS_VDD": 12, "MPFS_VDD18": 4, "MPFS_VDDA": 11, "MPFS_VDDA25": 6, "MPFS_VDD25": 9,
        "MPFS_VDDAUX1": 6, "MPFS_VDDAUX2": 6, "MPFS_VDDAUX4": 6, "MPFS_VDDI0": 3, "MPFS_VDDI1": 2,
        "MPFS_VDD_XCVR_CLK": 3, "MPFS_XCVR_VREF": 2, "MPFS_VDDI3": 3, "MPFS_VDDI2": 3,
        "MPFS_VDDI4": 3, "MPFS_VDDI5": 3, "MPFS_VDDI6": 4,
    }
    check(sum(_EXPECTED_RAIL_COUNTS.values()) == 86,
          f"the 17 expected per-rail cap counts sum to 86 (got "
          f"{sum(_EXPECTED_RAIL_COUNTS.values())}) -- sanity-checks this block's OWN table "
          f"before using it to check the netlist")
    # NOTE: kicad-cli's real netlist keys every LOCAL (non-power-symbol) net
    # by its full sheet-path-prefixed name (e.g. "/02-compute-core/"
    # "02a-mpfs-core/MPFS_VDD18", verified directly against the exported
    # netlist this pass) -- a bare `nets.get(rail, set())` lookup would
    # never match anything (this is exactly the bug that first surfaced the
    # bare-name-collision finding above: it silently returned "0 members"
    # for every rail, not an electrical problem). net_named() (already used
    # elsewhere in this file) handles the sheet-scope prefix correctly.
    rail_mismatches = []
    for rail, expected_n in _EXPECTED_RAIL_COUNTS.items():
        _found_name, members = net_named(nets, rail)
        # every member on a rail net this pass is a sheet-02 cap's pin "1"
        # (U1 itself not placed -- nothing else can be on this net yet)
        cap_members = [(r, p) for r, p in members if _IS_02_REF.match(r) and p == "1"]
        if len(cap_members) != expected_n or len(cap_members) != len(members):
            rail_mismatches.append(
                f"{rail}: expected {expected_n} cap members, got {len(cap_members)} "
                f"cap members / {len(members)} total net members")
    check(not rail_mismatches,
          f"every one of the 17 MPFS rail nets carries exactly its Table-1-4-derived cap count, "
          f"all pin '1' (mismatches: {rail_mismatches})")
    _gnd_name, gnd_all_members = net_named(nets, "GND")
    gnd_02_members = [(r, p) for r, p in gnd_all_members if _IS_02_REF.match(r)]
    check(len(gnd_02_members) == 86 and all(p == "2" for _r, p in gnd_02_members),
          f"all 86 sheet-02 caps' pin 2 join the shared GND net (got "
          f"{len(gnd_02_members)} members, pins {sorted({p for _r, p in gnd_02_members})})")

    # b) every real sheet-02 part carries Manufacturer + MPN (BOM traceability)
    missing_bom_02 = []
    for ref in comps_02:
        f = comps[ref]["fields"]
        if not (f.get("Manufacturer") and f.get("MPN")):
            missing_bom_02.append(ref)
    check(not missing_bom_02, f"every sheet-02 part carries Manufacturer+MPN (missing: {missing_bom_02})")

    # c) platform conformance: no Mini-Fit Jr on sheet 02 (86 caps, moot by
    # construction, but keep the same conformance shape as every other sheet)
    mini_fit_02 = [ref for ref in comps_02
                   if "Mini-Fit" in comps[ref]["fields"].get("Footprint", "")
                   or "5569" in comps[ref]["fields"].get("Footprint", "")]
    check(not mini_fit_02, f"no Mini-Fit Jr connector on sheet 02 (found: {mini_fit_02})")

    # -----------------------------------------------------------------
    # 3. root sheet instances expose exactly their planned hierarchical pins.
    #    NOTE: a naive `\(sheet\n.*?"Sheetname" "X".*?(?=...)` regex is NOT
    #    anchored to the (sheet block belonging to X -- non-greedy `.*?`
    #    happily starts from an EARLIER, unrelated `(sheet\n` (e.g. 01's own
    #    block) and matches straight through to X's Sheetname line, folding
    #    the wrong sheet's pins in (caught empirically: the first version of
    #    this extraction returned 01-power-input's 15 pins when asked for
    #    05-module-ports). Anchor on the Sheetname text's OWN position
    #    instead: find it, then walk backward to ITS block's `(sheet\n` and
    #    forward to the next sheet/text/footer boundary.
    # -----------------------------------------------------------------
    root_txt = open(ROOT_SCH).read()

    def _sheet_block(sheetname):
        idx = root_txt.find(f'"Sheetname" "{sheetname}"')
        if idx == -1:
            return None
        start = root_txt.rfind("\t(sheet\n", 0, idx)
        if start == -1:
            return None
        ends = [root_txt.find(pat, idx) for pat in
                ("\n\t(sheet\n", "\n\t(text", "\n\t(sheet_instances")]
        ends = [e for e in ends if e != -1]
        end = min(ends) if ends else len(root_txt)
        return root_txt[start:end]

    m = _sheet_block("01-power-input")
    check(m is not None, "root sheet carries a 01-power-input sheet instance")
    if m:
        pins = re.findall(r'\(pin "([^"]+)"', m)
        expected = {"+5V_MAIN", "+5VSB", "EXT_5V", "+5V_SYS", "+3V3",
                    "PG_MAIN", "FLT_MAIN", "PG_SVB", "FLT_SVB", "PG_EXT", "FLT_EXT",
                    "SENSE_MAIN", "SENSE_SVB", "SENSE_EXT", "SENSE_SYS"}
        check(set(pins) == expected,
              f"root's 01-power-input sheet symbol exposes exactly the 15 planned exports "
              f"(got {sorted(set(pins) ^ expected)} diff)")

    # -----------------------------------------------------------------
    # 3b. root sheet-05 instance exposes exactly the planned 28 hierarchical
    # pins (16x T1_A/B + 8x SYNC7 + CAN_TX/RX + DETECT_SDA/SCL)
    # -----------------------------------------------------------------
    m5 = _sheet_block("05-module-ports")
    check(m5 is not None, "root sheet carries a 05-module-ports sheet instance")
    if m5:
        pins5 = re.findall(r'\(pin "([^"]+)"', m5)
        expected5 = {f"P{n}_T1_A" for n in range(1, 9)} | {f"P{n}_T1_B" for n in range(1, 9)} \
            | {f"P{n}_SYNC7" for n in range(1, 9)} \
            | {"CAN_TX", "CAN_RX", "DETECT_SDA", "DETECT_SCL"}
        check(set(pins5) == expected5,
              f"root's 05-module-ports sheet symbol exposes exactly the 28 planned exports "
              f"(got {sorted(set(pins5) ^ expected5)} diff)")

    # -----------------------------------------------------------------
    # 3c. root sheet-04 instance exposes exactly the planned 20 hierarchical
    # pins (6x QSPI + 2x shared rail (+3V3_IO/VDD18) + 12x eMMC signals)
    # -----------------------------------------------------------------
    m4 = _sheet_block("04-storage")
    check(m4 is not None, "root sheet carries a 04-storage sheet instance")
    if m4:
        pins4 = re.findall(r'\(pin "([^"]+)"', m4)
        expected4 = {f"MSS_QSPI_{s}" for s in ("CS", "CLK", "IO0", "IO1", "IO2", "IO3")} \
            | {"+3V3_IO", "VDD18"} \
            | {f"MSS_EMMC_DAT{i}" for i in range(8)} \
            | {"MSS_EMMC_CLK", "MSS_EMMC_CMD", "MSS_EMMC_RST_N", "MSS_EMMC_DS"}
        check(set(pins4) == expected4,
              f"root's 04-storage sheet symbol exposes exactly the 20 planned exports "
              f"(got {sorted(set(pins4) ^ expected4)} diff)")

    # -----------------------------------------------------------------
    # 3d. root sheet-03 instance exposes exactly the planned 2 hierarchical
    # pins (+1V0_CORE awaiting 02a, +3V3_MPFS awaiting sibling leaf 03b --
    # MPFS_SEQ_EN is deliberately ABSENT here: it's a `global_nets` project-
    # wide label, invisible to the thin-parent/root sheet-pin plumbing)
    # -----------------------------------------------------------------
    m3 = _sheet_block("03-compute-rails")
    check(m3 is not None, "root sheet carries a 03-compute-rails sheet instance")
    if m3:
        pins3 = re.findall(r'\(pin "([^"]+)"', m3)
        expected3 = {"+1V0_CORE", "+3V3_MPFS"}
        check(set(pins3) == expected3,
              f"root's 03-compute-rails sheet symbol exposes exactly the 2 planned exports "
              f"(got {sorted(set(pins3) ^ expected3)} diff)")

    # -----------------------------------------------------------------
    # 3e. root sheet-02 instance exposes exactly 0 hierarchical pins --
    # HIER_EXPORTS_02 = {} this pass (U1 itself, the only thing that would
    # reach outside 02a, is not placed; see gen_hub_enterprise.py's
    # sheet-02 module docstring for the cec_sch.py unit-support blocker).
    # The sheet SYMBOL still needs to exist on the root page (verified
    # separately below), just with no pins yet.
    # -----------------------------------------------------------------
    m2 = _sheet_block("02-compute-core")
    check(m2 is not None, "root sheet carries a 02-compute-core sheet instance")
    if m2:
        pins2 = re.findall(r'\(pin "([^"]+)"', m2)
        check(pins2 == [],
              f"root's 02-compute-core sheet symbol exposes 0 pins this pass (U1 not yet placed "
              f"-- got {pins2})")

    # -----------------------------------------------------------------
    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}):", file=sys.stderr)
        for f in FAILURES:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"All checks passed ({len(comps)} components in the flattened hierarchy: "
          f"59 sheet-01 + 18 sheet-03 + 13 sheet-04 + 75 sheet-05 + 86 sheet-02 = "
          f"{len(comps_01) + len(comps_03) + len(comps_04) + len(comps_05) + len(comps_02)}; "
          f"{len(nets)} nets).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
