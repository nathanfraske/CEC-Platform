#!/usr/bin/env python3
"""One-shot, idempotent Hub Standard Rev2 LP5907 -> TLV62569 migration.

The Hub does not contain the 12VHPWR current-measurement analog front end, so
it does not receive the TLV75533 post-LDO.  This splice keeps the existing
input-selection/hold-up nets and replaces only the 3V3 regulator stage:

    /LOGIC_REG_IN -> TLV62569 -> 2.2uH -> +3V3

The existing local input/output capacitors C2/C3 become 10uF.  Existing
distributed +3V3 decoupling brings nominal COUT to about 20.3uF, inside the
TLV62569's characterized 10uF..47uF range; no new bulk capacitor is added.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cec_sch  # noqa: E402

SCH = os.path.join(ROOT, "beta", "hub-standard-rev2", "hub-standard-rev2.kicad_sch")
LIB = os.path.join(ROOT, "lib", "vendor", "cec-vendor.kicad_sym")
PROJECT = "hub-standard-rev2"
ROOT_UUID = "aa22b2b4-0e2b-481a-a188-ee3f43fcbaa8"


def ensure_3v3_power_flag(text):
    """Mark the passive L1 output as the source that drives the +3V3 rail."""
    if 'property "Reference" "#FLG9304"' in text:
        return text
    insert_at = text.rindex("\t(sheet_instances")
    flag = cec_sch.emit_global_power(
        "PWR_FLAG", 374.65, 78.74, PROJECT, ROOT_UUID, "#FLG9304")
    return text[:insert_at] + flag + "\n" + text[insert_at:]


def carve(text, start):
    depth = 0
    for end in range(start, len(text)):
        if text[end] == "(":
            depth += 1
        elif text[end] == ")":
            depth -= 1
            if depth == 0:
                return text[start:end + 1]
    raise ValueError("unterminated s-expression")


def symbol_instance(text, ref):
    match = re.search(r'\(property "Reference" "' + re.escape(ref) + r'"', text)
    if not match:
        raise SystemExit(f"REFUSE: {ref} not found")
    start = text.rindex("\t(symbol\n", 0, match.start())
    return start, carve(text, start)


def remove_wire(text, a, b):
    for match in re.finditer(r"\t\(wire\n", text):
        block = carve(text, match.start())
        points = re.findall(r"\(xy ([\d.\-]+) ([\d.\-]+)\)", block)
        if len(points) == 2 and set(points) == {tuple(map(str, a)), tuple(map(str, b))}:
            return text.replace(block, "", 1)
    raise SystemExit(f"REFUSE: wire {a}<->{b} not found")


def update_regulator_semantics(text):
    """Retire the old LDO naming and strap EN to the selected regulator VIN."""
    text = text.replace('"LDO_IN"', '"LOGIC_REG_IN"')
    text = text.replace(
        "ties the LDO input straight to +5V_HOLD, identical to the pre-beta wiring. "
        "Desolder + populate RJ_BUCK to move to the rung-3 path.",
        "ties the logic-regulator input straight to +5V_HOLD. Desolder + populate "
        "RJ_BUCK to use the alternate pre-regulated input path.")
    text = text.replace(
        "feeds the LDO from the wide-Vin buck's regulated output instead of raw +5V_HOLD.",
        "feeds the logic regulator from the wide-Vin buck output instead of raw +5V_HOLD.")

    # The LP5907 used a separate EN strap to +5V_HOLD.  The TLV62569 should
    # instead enable whenever whichever jumper-selected VIN source is present.
    try:
        text = remove_wire(text, (347.98, 67.31), (344.17, 67.31))
    except SystemExit:
        pass
    old_en_label = re.search(
        r'\t\(label "\+5V_HOLD"\s*\n?\s*\(at 344\.17 67\.31 180\)', text)
    if old_en_label:
        block = carve(text, old_en_label.start())
        text = text.replace(block, "", 1)
    if not re.search(r'\(label "LOGIC_REG_IN" \(at 347\.98 67\.31', text):
        insert_at = text.rindex("\t(sheet_instances")
        label = cec_sch.emit_label("LOGIC_REG_IN", 347.98, 67.31, 180)
        text = text[:insert_at] + label + "\n" + text[insert_at:]
    return text


def update_cap(text, ref):
    start, block = symbol_instance(text, ref)
    del start
    if '"1uF"' not in block:
        raise SystemExit(f"REFUSE: {ref} is not the expected 1uF capacitor")
    block2 = block.replace('(property "Value" "1uF"', '(property "Value" "10uF"', 1)
    block2 = re.sub(r'(property "MPN" ")[^"]+', r'\1CL10A106MA8NRNC', block2, count=1)
    block2 = re.sub(r'(property "LCSC" ")[^"]+', r'\1C96446', block2, count=1)
    block2 = re.sub(
        r'(property "Description" ")[^"]*',
        rf'\1TLV62569 {"input" if ref == "C2" else "output"} capacitor, 10uF X5R 25V',
        block2, count=1)
    return text.replace(block, block2, 1)


def pin_xy(pin_table, pin, x, y):
    lx, ly, _angle, _length = pin_table[pin]
    return x + lx, y - ly


def main():
    text = open(SCH).read()
    _start, old_u3 = symbol_instance(text, "U3")
    if "TLV62569DBVR" in old_u3:
        updated = update_regulator_semantics(text)
        updated = ensure_3v3_power_flag(updated)
        if updated != text:
            open(SCH, "w").write(updated)
            print("hub-standard-rev2: refreshed TLV62569 input/enable semantics")
        else:
            print("hub-standard-rev2: TLV62569 migration already applied")
        return 0
    if "LP5907" not in old_u3:
        raise SystemExit("REFUSE: U3 is neither the expected LP5907 nor migrated TLV62569")

    lib_text = open(LIB).read()
    if '(symbol "cec-vendor:TLV62569DBVR"' not in text:
        source = cec_sch.symbol_block(lib_text, "TLV62569DBVR")
        cached = cec_sch.reindent(cec_sch._namespace(source, "TLV62569DBVR", "cec-vendor"), 2)
        lib_start = text.index("\t(lib_symbols")
        lib_block = carve(text, lib_start)
        text = text.replace(lib_block, lib_block[:-2].rstrip() + "\n" + cached + "\n\t)", 1)

    cached_match = re.search(r'\(symbol "cec-vendor:TLV62569DBVR"', text)
    buck_pins = cec_sch.pin_table(carve(text, cached_match.start()))
    new_u3 = cec_sch.emit_symbol(
        "U3", "cec-vendor", "TLV62569DBVR", "TLV62569DBVR", 355.6, 67.31,
        sorted(buck_pins, key=int), PROJECT, ROOT_UUID,
        fp="cec-Package_TO_SOT_SMD:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BL",
        props={
            "Manufacturer": "Texas Instruments", "MPN": "TLV62569DBVR",
            "LCSC": "C141836", "Datasheet": "https://www.ti.com/lit/ds/symlink/tlv62569.pdf",
            "Description": "2A synchronous buck; Hub +3V3 direct regulator (no post-LDO required)",
        })
    text = text.replace(old_u3, new_u3, 1)

    text = update_cap(text, "C2")
    text = update_cap(text, "C3")

    # Break the former LP5907 OUT -> +3V3 wire.  With the replacement symbol,
    # the same pin coordinate is TLV62569 SW and must feed only L1.
    text = remove_wire(text, (363.22, 64.77), (365.76, 64.77))
    nc = re.search(
        r'\t\(no_connect\s*\n?\s*\(at 360\.68 67\.31\)\s*\n?\s*\(uuid "[^"]+"\)\s*\n?\s*\)',
        text)
    if not nc:
        raise SystemExit("REFUSE: expected U3.NC marker not found")
    text = text[:nc.start()] + text[nc.end():]

    l_pins = cec_sch.pin_table(cec_sch.symbol_block(lib_text, "L_Small"))
    r_pins = cec_sch.pin_table(cec_sch.symbol_block(lib_text, "R_Small"))
    out = []

    lx, ly = 374.65, 76.2
    out.append(cec_sch.emit_symbol(
        "L1", "cec-vendor", "L_Small", "2.2uH", lx, ly,
        sorted(l_pins, key=int), PROJECT, ROOT_UUID,
        fp="cec-Inductor_SMD:VLS252010HBX-2R2M-1",
        props={"Manufacturer": "TDK", "MPN": "VLS252010HBX-2R2M-1",
               "LCSC": "C88527",
               "Description": "2.2uH shielded buck inductor, 2.3A Isat max / 1.76A thermal-rated"}))
    l1 = pin_xy(l_pins, "1", lx, ly)
    l2 = pin_xy(l_pins, "2", lx, ly)
    out.append(cec_sch.emit_label("BUCK_SW_3V3", *l1, 0))
    out.append(cec_sch.emit_global_power("+3V3", *l2, PROJECT, ROOT_UUID, "#PWR9301"))
    out.append(cec_sch.emit_global_power("PWR_FLAG", *l2, PROJECT, ROOT_UUID, "#FLG9304"))

    r39x, r39y = 388.62, 76.2
    out.append(cec_sch.emit_symbol(
        "R39", "cec-vendor", "R_Small", "453k", r39x, r39y,
        sorted(r_pins, key=int), PROJECT, ROOT_UUID,
        fp="cec-Resistor_SMD:R_0402_1005Metric",
        props={"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF4533TCE",
               "LCSC": "C27009", "Description": "Hub buck FB top; 3.318V nominal"}))
    r391 = pin_xy(r_pins, "1", r39x, r39y)
    r392 = pin_xy(r_pins, "2", r39x, r39y)
    out.append(cec_sch.emit_global_power("+3V3", *r391, PROJECT, ROOT_UUID, "#PWR9302"))
    out.append(cec_sch.emit_label("BUCK_FB_3V3", *r392, 0))

    r40x, r40y = 388.62, 88.9
    out.append(cec_sch.emit_symbol(
        "R40", "cec-vendor", "R_Small", "100k", r40x, r40y,
        sorted(r_pins, key=int), PROJECT, ROOT_UUID,
        fp="cec-Resistor_SMD:R_0402_1005Metric",
        props={"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF1003TCE",
               "LCSC": "C25741", "Description": "Hub buck FB bottom; 100k per TI recommendation"}))
    r401 = pin_xy(r_pins, "1", r40x, r40y)
    r402 = pin_xy(r_pins, "2", r40x, r40y)
    out.append(cec_sch.emit_label("BUCK_FB_3V3", *r401, 0))
    out.append(cec_sch.emit_global_power("GND", *r402, PROJECT, ROOT_UUID, "#PWR9303"))

    # New U3 pin coordinates deliberately match the former LP5907 input,
    # enable, ground and output locations.  Only SW and FB need new labels.
    out.append(cec_sch.emit_label("BUCK_SW_3V3", 363.22, 64.77, 0))
    out.append(cec_sch.emit_label("BUCK_FB_3V3", 363.22, 67.31, 0))

    insert_at = text.rindex("\t(sheet_instances")
    text = text[:insert_at] + "\n".join(out) + "\n" + text[insert_at:]
    text = update_regulator_semantics(text)
    open(SCH, "w").write(text)
    print("hub-standard-rev2: U3 migrated to TLV62569 direct buck; added L1/R39/R40; C2/C3 -> 10uF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
