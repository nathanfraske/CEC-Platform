#!/usr/bin/env python3
# One-shot splice: ATX CONTROL-SIGNAL INTERACTION block on the 24-pin rev3 (beta).
# Owner-approved 2026-07-14 (study: docs/standard-tier-review/
# atx24-sense-wire-interaction-study-2026-07-14.md; owner-queue §1 row RULED):
#   (a) restore the alpha's PWR_OK + PS_ON# read taps (1k + 74LVC1G17 Schmitt
#       buffer, 5V-tolerant input at 3V3 VCC — netmap §4 pattern; rev3 had
#       regressed them to bare pass-throughs),
#   (b) NEW PS_ON# open-drain drive: AO3400A, gate 100R series from MCU with a
#       100k pull-down so reset/brownout/crash = RELEASED (fail-safe),
#   (c) NEW −12V rail measurement: divider hung +3V3↔−12V (15k/100k) so the node
#       sits 1.15–1.46V across the ±10% rail band (2.87V = rail-at-0V, 3.3V =
#       wire absent — all in-window, all separable), 10k series + BAT54S clamp
#       into an ADC pin (single-fault safe: 3V3 collapse clamps at −0.3V/~127µA),
#   (d) PESD5V0S1BA ESD clamps on PS_ON# + PWR_OK (owner: "may as well clamp").
# MCU pins (free, non-strapping; C6 straps are IO8/IO9/IO15): IO2=ADC −12V,
# IO3=PSON_DRIVE (plain pin, no boot pull — scope-verify at first article),
# IO4=PWROK_SENSE, IO5=PSON_SENSE.
# Label-driven like the flat sheet; idempotent-guarded; netlist verified by the
# runner (see the ERC/netlist-diff step in the same session).
import sys, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cec_sch

SCH = os.path.join(HERE, "..", "beta", "atx-24pin-rev3", "24pin-module.kicad_sch")
PROJECT = "24pin-module"
GRID = 1.27

txt = open(SCH).read()
ROOT = re.search(r'\(uuid "([0-9a-f-]{36})"\)', txt).group(1)

NEW_REFS = ["U4", "U8", "Q1", "D3", "D4", "D5",
            "R70", "R71", "R72", "R73", "R74", "R75", "R76",
            "C62", "C63", "C64"]
for r in NEW_REFS:
    if re.search(r'\(property "Reference" "' + re.escape(r) + r'"', txt):
        raise SystemExit(f"REFUSE: {r} already present -- splice already applied?")

# ---------- 1. lib_symbols: pull 74LVC1G17 / Q_NMOS_GSD / BAT54S from the vendor lib ----------
VENDOR = open(os.path.join(HERE, "..", "lib", "vendor", "cec-vendor.kicad_sym")).read()
add_blocks = []
for name in ("74LVC1G17", "Q_NMOS_GSD", "BAT54S"):
    if f'(symbol "cec-vendor:{name}"' in txt:
        continue
    blk = cec_sch.symbol_block(VENDOR, name)
    add_blocks.append(cec_sch.reindent(cec_sch._namespace(blk, name, "cec-vendor"), 2))
if add_blocks:
    # insert before the lib_symbols closing paren: find "\t(lib_symbols" block end
    i = txt.index("\t(lib_symbols")
    blk = cec_sch.carve(txt, i)
    txt = txt.replace(blk, blk[:-2].rstrip() + "\n" + "\n".join(add_blocks) + "\n\t)", 1)

# ---------- 2. pin geometry from the file's own (now-updated) lib cache ----------
def pins_of(libname, source=None):
    t = source or txt
    m = re.search(r'\(symbol "' + re.escape(libname) + r'"', t)
    return cec_sch.pin_table(cec_sch.carve(t, m.start()))

PIN = {
    "LVC":  pins_of("cec-vendor:74LVC1G17"),
    "FET":  pins_of("cec-vendor:Q_NMOS_GSD"),
    "BAT":  pins_of("cec-vendor:BAT54S"),
    "R":    pins_of("cec-vendor:R_Small"),
    "C":    pins_of("cec-vendor:C_Small"),
    "D":    pins_of("cec-vendor:D_Schottky"),
    "MCU":  pins_of("cec-vendor:ESP32-C6-MINI-1-N4"),
}

pwr_n = [1000]  # next #PWR number (max in file = 991)

def gsnap(v):
    return round(v / GRID) * GRID

def stub_and_target(ax, ay, ang, L=2.54):
    if ang == 0:
        return gsnap(ax - L), gsnap(ay), 180
    if ang == 180:
        return gsnap(ax + L), gsnap(ay), 0
    if ang == 270:
        return gsnap(ax), gsnap(ay - L), 90
    if ang == 90:
        return gsnap(ax), gsnap(ay + L), 270
    raise ValueError(ang)

out = []

def emit_part(ref, name, val, ox, oy, pinkey, fp, props=None):
    out.append(cec_sch.emit_symbol(ref, "cec-vendor", name, val, ox, oy,
                                   sorted(PIN[pinkey].keys()), PROJECT, ROOT,
                                   fp=fp, props=props))

def wire_pin(pinkey, xy, pinnum, net_or_power):
    ox, oy = xy
    lx, ly, ang, _len = PIN[pinkey][pinnum]
    ax, ay = ox + lx, oy - ly
    ex, ey, lang = stub_and_target(ax, ay, ang)
    out.append(cec_sch.emit_wire(ax, ay, ex, ey))
    if isinstance(net_or_power, tuple):
        _, symname = net_or_power
        ref = f"#PWR0{pwr_n[0]}"; pwr_n[0] += 1
        out.append(cec_sch.emit_global_power(symname, ex, ey, PROJECT, ROOT, ref))
    else:
        out.append(cec_sch.emit_label(net_or_power, ex, ey, lang))

FP_SOT235 = "cec-Package_TO_SOT_SMD:SOT-23-5"
FP_FET    = "cec-Package_TO_SOT_SMD:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR"
FP_BAT    = "cec-Package_TO_SOT_SMD:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-TL"
FP_SOD    = "cec-Diode_SMD:D_SOD-323"
FP_R      = "cec-Resistor_SMD:R_0402_1005Metric"
FP_C      = "cec-Capacitor_SMD:C_0402_1005Metric"

LVC_PROPS = {"MPN": "SN74LVC1G17DBVR", "Manufacturer": "Texas Instruments",
             "LCSC": "C7836",
             "Datasheet": "https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf"}
PESD_PROPS = {"MPN": "PESD5V0S1BA", "Manufacturer": "Diodes Inc / PANJIT (platform part)",
              "LCSC": "C5261083"}

# ---------- 3. the block (free region measured empty x346-429 / y243-291) ----------
out.append(cec_sch.emit_section(
    "ATX CONTROL-SIGNAL INTERACTION  PS_ON#/PWR_OK/-12V  (owner-approved 2026-07-14)",
    346.71, 243.84, 429.26, 290.83))

# --- PWR_OK read: ATX_PWROK -> R70 1k -> U4 74LVC1G17 -> PWROK_SENSE (MCU IO4) ---
emit_part("R70", "R_Small", "1kΩ", 353.06, 252.73, "R", FP_R,
          {"MPN": "0402WGF1001TCE", "Manufacturer": "UNI-ROYAL", "LCSC": "C11702",
           "Note": "PWR_OK tap series R (alpha/netmap §4 pattern)"})
wire_pin("R", (353.06, 252.73), "1", "ATX_PWROK")
wire_pin("R", (353.06, 252.73), "2", "PWROK_BUF")
emit_part("U4", "74LVC1G17", "74LVC1G17", 369.57, 252.73, "LVC", FP_SOT235,
          dict(LVC_PROPS, Note="PWR_OK Schmitt buffer: 5V-tolerant input at 3V3 VCC, "
               "high-Z tap, clean edge for T_pwr_ok (100-500ms) timing on IO4"))
wire_pin("LVC", (369.57, 252.73), "2", "PWROK_BUF")
wire_pin("LVC", (369.57, 252.73), "4", "PWROK_SENSE")
wire_pin("LVC", (369.57, 252.73), "5", ("PWR", "+3V3"))
wire_pin("LVC", (369.57, 252.73), "3", ("PWR", "GND"))
lx, ly, _a, _l = PIN["LVC"]["1"]
out.append(cec_sch.emit_noconnect(369.57 + lx, 252.73 - ly))
emit_part("C62", "C_Small", "100nF", 384.81, 252.73, "C", FP_C)
wire_pin("C", (384.81, 252.73), "1", ("PWR", "+3V3"))
wire_pin("C", (384.81, 252.73), "2", ("PWR", "GND"))
emit_part("D4", "D_Schottky", "PESD5V0S1BA", 393.70, 252.73, "D", FP_SOD,
          dict(PESD_PROPS, Note="PWR_OK ESD clamp (owner 2026-07-14: clamp both "
               "signal taps; DETECT-pin posture)"))
wire_pin("D", (393.70, 252.73), "1", "ATX_PWROK")   # cathode -> line
wire_pin("D", (393.70, 252.73), "2", ("PWR", "GND"))

# --- PS_ON# read: ATX_PSON -> R71 1k -> U8 -> PSON_SENSE (MCU IO5) ---
emit_part("R71", "R_Small", "1kΩ", 353.06, 264.16, "R", FP_R,
          {"MPN": "0402WGF1001TCE", "Manufacturer": "UNI-ROYAL", "LCSC": "C11702",
           "Note": "PS_ON# tap series R"})
wire_pin("R", (353.06, 264.16), "1", "ATX_PSON")
wire_pin("R", (353.06, 264.16), "2", "PSON_BUF")
emit_part("U8", "74LVC1G17", "74LVC1G17", 369.57, 264.16, "LVC", FP_SOT235,
          dict(LVC_PROPS, Note="PS_ON# Schmitt buffer: high-Z (does not load the "
               "PSU's internal pull-up); firmware interlock reads line-vs-own-drive"))
wire_pin("LVC", (369.57, 264.16), "2", "PSON_BUF")
wire_pin("LVC", (369.57, 264.16), "4", "PSON_SENSE")
wire_pin("LVC", (369.57, 264.16), "5", ("PWR", "+3V3"))
wire_pin("LVC", (369.57, 264.16), "3", ("PWR", "GND"))
lx, ly, _a, _l = PIN["LVC"]["1"]
out.append(cec_sch.emit_noconnect(369.57 + lx, 264.16 - ly))
emit_part("C63", "C_Small", "100nF", 384.81, 264.16, "C", FP_C)
wire_pin("C", (384.81, 264.16), "1", ("PWR", "+3V3"))
wire_pin("C", (384.81, 264.16), "2", ("PWR", "GND"))
emit_part("D3", "D_Schottky", "PESD5V0S1BA", 393.70, 264.16, "D", FP_SOD,
          dict(PESD_PROPS, Note="PS_ON# ESD clamp"))
wire_pin("D", (393.70, 264.16), "1", "ATX_PSON")
wire_pin("D", (393.70, 264.16), "2", ("PWR", "GND"))

# --- PS_ON# drive: MCU IO3 -> R72 100R -> gate (R73 100k PD) -> Q1 AO3400A open-drain ---
emit_part("Q1", "Q_NMOS_GSD", "AO3400A", 414.02, 264.16, "FET", FP_FET,
          {"MPN": "AO3400A", "Manufacturer": "AOS", "LCSC": "C20917",
           "Note": "PS_ON# OPEN-DRAIN drive (owner-approved 2026-07-14): wired-OR "
                   "with the motherboard, can force PSU ON, can never source. "
                   "100k gate pull-down = released at reset/crash (fail-safe). "
                   "Line is 5.25V max vs 30V rating; sink budget 10mA vs Vol<1mV."})
wire_pin("FET", (414.02, 264.16), "1", "PSON_GATE")
wire_pin("FET", (414.02, 264.16), "3", "ATX_PSON")
wire_pin("FET", (414.02, 264.16), "2", ("PWR", "GND"))
emit_part("R72", "R_Small", "100Ω", 353.06, 278.13, "R", FP_R,
          {"MPN": "RC0402JR-07100RL", "Manufacturer": "YAGEO", "LCSC": "C106233",
           "Note": "gate series R from IO3"})
wire_pin("R", (353.06, 278.13), "1", "PSON_DRIVE")
wire_pin("R", (353.06, 278.13), "2", "PSON_GATE")
emit_part("R73", "R_Small", "100kΩ", 361.95, 278.13, "R", FP_R,
          {"MPN": "0402WGF1003TCE", "Manufacturer": "UNI-ROYAL", "LCSC": "C25741",
           "Note": "gate pull-down: default RELEASED (safety-critical, do not DNP)"})
wire_pin("R", (361.95, 278.13), "1", "PSON_GATE")
wire_pin("R", (361.95, 278.13), "2", ("PWR", "GND"))

# --- -12V sense: +3V3 -R74 15k- node -R75 100k- ATX_NEG12V ; node -R76 10k- ADC (IO2) ---
emit_part("R74", "R_Small", "15kΩ", 372.11, 278.13, "R", FP_R,
          {"MPN": "0402WGF1502TCE", "Manufacturer": "UNI-ROYAL", "LCSC": "C25756",
           "Note": "-12V divider top (to +3V3): node = 1.30V @ -12.0V rail, "
                   "2.87V @ rail-0V, 3.3V @ wire-absent -- all in ADC window"})
wire_pin("R", (372.11, 278.13), "1", ("PWR", "+3V3"))
wire_pin("R", (372.11, 278.13), "2", "NEG12V_DIV")
emit_part("R75", "R_Small", "100kΩ", 381.00, 278.13, "R", FP_R,
          {"MPN": "0402WGF1003TCE", "Manufacturer": "UNI-ROYAL", "LCSC": "C25741",
           "Note": "-12V divider bottom (to /ATX_NEG12V); rail load 133uA"})
wire_pin("R", (381.00, 278.13), "1", "NEG12V_DIV")
wire_pin("R", (381.00, 278.13), "2", "ATX_NEG12V")
emit_part("R76", "R_Small", "10kΩ", 389.89, 278.13, "R", FP_R,
          {"MPN": "0402WGF1002TCE", "Manufacturer": "UNI-ROYAL", "LCSC": "C25744",
           "Note": "ADC series R: limits single-fault clamp current to ~127uA"})
wire_pin("R", (389.89, 278.13), "1", "NEG12V_DIV")
wire_pin("R", (389.89, 278.13), "2", "NEG12V_ADC")
emit_part("C64", "C_Small", "100nF", 398.78, 278.13, "C", FP_C)
wire_pin("C", (398.78, 278.13), "1", "NEG12V_ADC")
wire_pin("C", (398.78, 278.13), "2", ("PWR", "GND"))
emit_part("D5", "BAT54S", "BAT54S", 411.48, 278.13, "BAT", FP_BAT,
          {"MPN": "BAT54S", "Manufacturer": "(easyeda vendored, argb precedent)",
           "LCSC": "C545549",
           "Note": "dual clamp on the ADC pin: series pair A1(p1)=GND -> mid(p3)="
                   "node = LOW clamp at -0.3V; mid -> K2(p2)=+3V3 = high clamp. "
                   "VERIFY p1/p3/p2 = A1/mid/K2 against the C545549 land at first "
                   "article (symbol pin-name text is sloppy; drawing verified)."})
wire_pin("BAT", (411.48, 278.13), "1", ("PWR", "GND"))
wire_pin("BAT", (411.48, 278.13), "2", ("PWR", "+3V3"))
wire_pin("BAT", (411.48, 278.13), "3", "NEG12V_ADC")

# ---------- 4. MCU stubs (U1 at 275.59,204.47 rot0): remove NCs, add labels ----------
MCU_XY = (275.59, 204.47)
MCU_NETS = {"5": "NEG12V_ADC", "6": "PSON_DRIVE", "9": "PWROK_SENSE", "10": "PSON_SENSE"}
for pad, net in MCU_NETS.items():
    lx, ly, ang, _l = PIN["MCU"][pad]
    ax, ay = MCU_XY[0] + lx, MCU_XY[1] - ly
    nc = re.search(r'\t\(no_connect\s*\(at ' + re.escape(cec_sch.f(ax)) + ' '
                   + re.escape(cec_sch.f(ay)) + r'\)\s*\(uuid "[^"]+"\)\s*\)\n?', txt)
    if not nc:
        raise SystemExit(f"REFUSE: expected no_connect at U1 pad {pad} ({ax},{ay}) not found")
    txt = txt[:nc.start()] + txt[nc.end():]
    ex, ey, lang = stub_and_target(ax, ay, ang)
    out.append(cec_sch.emit_wire(ax, ay, ex, ey))
    out.append(cec_sch.emit_label(net, ex, ey, lang))

# ---------- 5. splice ----------
blob = "\n".join(out) + "\n"
idx = txt.rindex("\t(sheet_instances")
new = txt[:idx] + blob + txt[idx:]
open(SCH, "w").write(new)
print(f"spliced {len(out)} s-expr elements (+{len(add_blocks)} lib symbols); "
      f"file -> {len(new)} bytes")
