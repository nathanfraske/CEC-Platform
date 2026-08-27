#!/usr/bin/env python3
"""Retire the obsolete Hub J_PWR feed after the rev3 dead-bug stack.

The 24-pin board selects MAIN_5V versus 5VSB and presents +5V_SYS on
J6P.  The Hub therefore needs two TPS2121 stages, not the former three:

    J6P +5V_SYS ------------------------> U7.IN1
    Hub USB VBUS ----> U11.IN1 --+
    NanoKVM 5V -----> U11.IN2 --+------> U7.IN2

U7.OUT remains +5VSB, upstream of blackout detection and hold-up. U7.ST
replaces the obsolete raw-5VSB ADC input and reports the selected branch.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import cec_sch  # noqa: E402
import splice_usb_ingress_common as sc  # noqa: E402

BOARD = os.path.join(ROOT, "beta", "hub-standard-rev2")
PWR = os.path.join(BOARD, "01-power-input-selection.kicad_sch")
MCU = os.path.join(BOARD, "03-mcu-usb.kicad_sch")
PORTS = os.path.join(BOARD, "04-can-module-ports.kicad_sch")
SENSE = os.path.join(BOARD, "05-kvm-aux-sensors.kicad_sch")
TOP = os.path.join(BOARD, "hub-standard-rev2.kicad_sch")

PROJECT = "hub-standard-rev2"
ROOT_UUID = "aa22b2b4-0e2b-481a-a188-ee3f43fcbaa8"


def _insert_top_level(txt: str, elements: list[str]) -> str:
    blob = "\n".join(elements) + "\n"
    if "\t(sheet_instances" in txt:
        at = txt.rindex("\t(sheet_instances")
        return txt[:at] + blob + txt[at:]
    start = txt.index("(kicad_sch")
    whole = cec_sch.carve(txt, start)
    at = start + len(whole) - 1
    return txt[:at] + blob + txt[at:]


def _remove_no_connect_at(txt: str, x: float, y: float) -> str:
    xy = f"(at {cec_sch.f(x)} {cec_sch.f(y)})"
    blocks = []
    for match in re.finditer(re.escape(xy), txt):
        start = txt.rfind("\t(no_connect", 0, match.start())
        if start < 0:
            continue
        blk = cec_sch.carve(txt, start)
        if start <= match.start() < start + len(blk):
            blocks.append(blk)
    if len(blocks) != 1:
        raise SystemExit(
            f"REFUSE: expected one no_connect at ({x},{y}), found {len(blocks)}"
        )
    return txt.replace(blocks[0], "", 1)


def _remove_component(txt: str, ref: str, lib_id: str, x: float, y: float,
                      *, nc_pins: tuple[str, ...] = ()) -> str:
    pins = sc.get_pin_table(txt, lib_id)
    for pin in sorted(pins, key=lambda p: (len(p), p)):
        if pin in nc_pins:
            px, py, _dx, _dy = sc.pin_pt(pins, pin, x, y)
            txt = _remove_no_connect_at(txt, px, py)
        else:
            txt, _kind, _info = sc.remove_pin_stub(txt, pins, ref, pin, x, y)
    txt, _blk = sc.remove_symbol(txt, ref)
    return txt


def _remove_flag_lane(txt: str, ref: str, x: float,
                      terminal_y: float, flag_y: float) -> str:
    txt = sc.remove_wire_between(txt, x, terminal_y, x, flag_y)
    txt, kind, _info = sc.remove_terminal_at(txt, x, terminal_y)
    if kind not in ("label", "hierarchical_label"):
        raise SystemExit(f"REFUSE: {ref} terminal is {kind}, expected label")
    txt, _blk = sc.remove_symbol(txt, ref)
    return txt


def _sheet_block(txt: str, sheetfile: str) -> str:
    needle = f'(property "Sheetfile" "{sheetfile}"'
    pos = txt.find(needle)
    if pos < 0:
        raise SystemExit(f"REFUSE: root has no sheetfile {sheetfile}")
    start = txt.rfind("\t(sheet\n", 0, pos)
    if start < 0:
        raise SystemExit(f"REFUSE: cannot locate sheet block for {sheetfile}")
    blk = cec_sch.carve(txt, start)
    if not (start <= pos < start + len(blk)):
        raise SystemExit(f"REFUSE: Sheetfile {sheetfile} escaped located block")
    return blk


def _edit_sheet_pin(txt: str, sheetfile: str, old: str,
                    new: str | None, *, shape: str | None = None) -> str:
    blk = _sheet_block(txt, sheetfile)
    needle = f'\t\t(pin "{old}" '
    pos = blk.find(needle)
    if pos < 0:
        raise SystemExit(f"REFUSE: {sheetfile} has no sheet pin {old}")
    pin_blk = cec_sch.carve(blk, pos)
    if new is None:
        new_blk = blk.replace(pin_blk, "", 1)
    else:
        replacement = pin_blk.replace(f'(pin "{old}"', f'(pin "{new}"', 1)
        if shape is not None:
            replacement, count = re.subn(
                r'(\(pin "[^"]+"\s+)(input|output|bidirectional|tri_state|passive)',
                rf'\g<1>{shape}', replacement, count=1)
            if count != 1:
                raise SystemExit(
                    f"REFUSE: could not set {sheetfile}:{new} shape to {shape}")
        new_blk = blk.replace(pin_blk, replacement, 1)
    return txt.replace(blk, new_blk, 1)


def _remove_root_lane(txt: str, sheetfile: str, pin: str,
                      pin_xy: tuple[float, float],
                      terminal_xy: tuple[float, float]) -> str:
    txt = sc.remove_wire_between(txt, *pin_xy, *terminal_xy)
    txt, kind, info = sc.remove_terminal_at(txt, *terminal_xy)
    if kind != "label" or info != pin:
        raise SystemExit(
            f"REFUSE: root lane {sheetfile}:{pin} ended in {kind} {info!r}"
        )
    return _edit_sheet_pin(txt, sheetfile, pin, None)


def migrate_power_sheet() -> None:
    txt = open(PWR, encoding="utf-8").read()
    if '(property "Reference" "J_PWR"' not in txt:
        raise SystemExit("REFUSE: J_PWR already absent; migration already applied")

    removals = (
        ("J_PWR", "cec:CEC_PWR_IN_3P", 39.37, 72.39, ()),
        ("D9", "cec-vendor:PESD5V0S1UL", 171.45, 72.39, ()),
        ("U5", "cec-vendor:TPS2121RUXR", 237.49, 72.39, ("9",)),
        ("R_ILIM1", "cec-vendor:R_Small", 39.37, 171.45, ()),
        ("C_SS1", "cec-vendor:C_Small", 370.84, 107.95, ()),
        ("C9", "cec-vendor:C_Small", 39.37, 107.95, ()),
        ("C24", "cec-vendor:C_Small", 186.69, 107.95, ()),
        ("R33", "cec-vendor:R_Small", 149.86, 171.45, ()),
        ("R34", "cec-vendor:R_Small", 186.69, 171.45, ()),
    )
    for ref, lib_id, x, y, nc in removals:
        txt = _remove_component(txt, ref, lib_id, x, y, nc_pins=nc)

    txt = _remove_flag_lane(txt, "#FLG136", 44.45, 234.95, 245.11)
    txt = _remove_flag_lane(txt, "#FLG141", 125.73, 234.95, 245.11)

    # U11 now takes Hub USB directly on IN1/PR1 and keeps KVM on IN2.
    for x, y in ((223.52, 101.6), (297.18, 165.1),
                 (347.98, 64.77), (347.98, 52.07)):
        txt, old, _tag = sc.rename_label_at(txt, x, y, "USB_VBUS")
        if old != "PSU_5V":
            raise SystemExit(f"REFUSE: expected PSU_5V at ({x},{y}), got {old}")
    txt, kind, old = sc.remove_terminal_at(txt, 223.52, 101.6)
    if kind != "label" or old != "USB_VBUS":
        raise SystemExit(f"REFUSE: USB ingress export drifted: {kind} {old!r}")
    txt = _insert_top_level(
        txt, [sc.emit_hier_label("USB_VBUS", 223.52, 101.6, 0, shape="input")]
    )

    # Rename the surviving primary path and expose it project-wide.
    for x, y in ((97.79, 72.39), (223.52, 165.1),
                 (281.94, 64.77), (281.94, 52.07), (105.41, 234.95)):
        txt, old, _tag = sc.rename_label_at(txt, x, y, "+5V_SYS")
        if old != "MAIN_5V_RAW":
            raise SystemExit(f"REFUSE: expected MAIN_5V_RAW at ({x},{y}), got {old}")
    txt, kind, old = sc.remove_terminal_at(txt, 297.18, 101.6)
    if kind != "hierarchical_label" or old != "MAIN_5V_RAW":
        raise SystemExit(f"REFUSE: primary input export drifted: {kind} {old!r}")
    txt = _insert_top_level(
        txt, [cec_sch.emit_global_label("+5V_SYS", 297.18, 101.6, 0)]
    )

    # U7.ST replaces the obsolete raw-5VSB ADC input.
    mux_pins = sc.get_pin_table(txt, "cec-vendor:TPS2121RUXR")
    px, py, _dx, _dy = sc.pin_pt(mux_pins, "9", 303.53, 72.39)
    txt = _remove_no_connect_at(txt, px, py)
    txt = _insert_top_level(txt, [sc.wire_and_hier_label(
        mux_pins, "U7", "9", 303.53, 72.39,
        "PWR_SOURCE_STATUS", shape="output"
    )])

    old_note = (
        "Power-entry TVS (owner GO 2026-07-15): the J_PWR feed arrives over a "
        "chassis cable from the 24-pin; 5V working, clamps line transients. "
        "DETECT-pin ESD posture extended to the power entry."
    )
    new_note = (
        "Stack-power TVS: J6P receives the consolidated +5V_SYS rail from the "
        "24-pin rev3 selector; 5V working, clamps line transients before U7."
    )
    if txt.count(old_note) != 1:
        raise SystemExit(f"REFUSE: expected one D8 note, found {txt.count(old_note)}")
    txt = txt.replace(old_note, new_note, 1)
    open(PWR, "w", encoding="utf-8", newline="").write(txt)


def migrate_port_sheet() -> None:
    txt = open(PORTS, encoding="utf-8").read()
    pins = sc.get_pin_table(txt, "cec:CEC_CONN_2x3")
    additions = []
    for pin in ("1", "3", "5"):
        txt, kind, info = sc.remove_pin_stub(txt, pins, "J6P", pin, 379.73, 104.14)
        if kind != "power" or info[1] != "+5VSB":
            raise SystemExit(f"REFUSE: J6P.{pin} was not +5VSB: {kind} {info!r}")
        additions.append(
            sc.wire_and_global_label(pins, "J6P", pin, 379.73, 104.14, "+5V_SYS")
        )
    txt = _insert_top_level(txt, additions)
    open(PORTS, "w", encoding="utf-8", newline="").write(txt)


def migrate_sensor_sheet() -> None:
    txt = open(SENSE, encoding="utf-8").read()
    for ref, x in (("R17", 170.18), ("R18", 208.28)):
        txt = _remove_component(txt, ref, "cec-vendor:R_Small", x, 157.48)

    txt, kind, old = sc.remove_terminal_at(txt, 93.98, 151.13)
    if kind != "hierarchical_label" or old != "MAIN_5V_RAW":
        raise SystemExit(f"REFUSE: R15 input drifted: {kind} {old!r}")
    txt = _insert_top_level(
        txt, [cec_sch.emit_global_label("+5V_SYS", 93.98, 151.13, 0)]
    )
    for x, y in ((132.08, 151.13), (93.98, 163.83)):
        txt, old, _tag = sc.rename_label_at(txt, x, y, "5V_SYS_SENSE")
        if old != "MAIN_5V_SENSE":
            raise SystemExit(f"REFUSE: expected MAIN_5V_SENSE at ({x},{y}), got {old}")
    open(SENSE, "w", encoding="utf-8", newline="").write(txt)


def migrate_mcu_sheet() -> None:
    txt = open(MCU, encoding="utf-8").read()
    txt, old, _tag = sc.rename_label_at(txt, 154.94, 104.14, "PWR_SOURCE_STATUS")
    if old != "5VSB_SENSE":
        raise SystemExit(f"REFUSE: MCU status input drifted: {old}")
    txt, kind, old = sc.remove_terminal_at(txt, 154.94, 104.14)
    if kind != "hierarchical_label" or old != "PWR_SOURCE_STATUS":
        raise SystemExit(f"REFUSE: MCU status export drifted: {kind} {old!r}")
    txt = _insert_top_level(
        txt, [sc.emit_hier_label(
            "PWR_SOURCE_STATUS", 154.94, 104.14, 180, shape="input")]
    )
    txt, old, _tag = sc.rename_label_at(txt, 154.94, 101.6, "5V_SYS_SENSE")
    if old != "MAIN_5V_SENSE":
        raise SystemExit(f"REFUSE: MCU 5V system sense drifted: {old}")
    open(MCU, "w", encoding="utf-8", newline="").write(txt)


def migrate_root() -> None:
    txt = open(TOP, encoding="utf-8").read()
    txt = _edit_sheet_pin(
        txt, "01-power-input-selection.kicad_sch", "5VSB_RAW", "PWR_SOURCE_STATUS"
    )
    txt = _edit_sheet_pin(
        txt, "01-power-input-selection.kicad_sch", "KVM_5V_IN", "KVM_5V_IN",
        shape="input"
    )
    txt = _edit_sheet_pin(
        txt, "01-power-input-selection.kicad_sch", "USB_VBUS", "USB_VBUS",
        shape="input"
    )
    txt, old, _tag = sc.rename_label_at(txt, 189.23, 87.63, "PWR_SOURCE_STATUS")
    if old != "5VSB_RAW":
        raise SystemExit(f"REFUSE: root sheet-01 status lane drifted: {old}")
    txt = _remove_root_lane(
        txt, "01-power-input-selection.kicad_sch", "MAIN_5V_RAW",
        (185.42, 97.79), (189.23, 97.79)
    )

    txt = _remove_root_lane(
        txt, "05-kvm-aux-sensors.kicad_sch", "5VSB_RAW",
        (248.92, 271.78), (245.11, 271.78)
    )
    txt = _remove_root_lane(
        txt, "05-kvm-aux-sensors.kicad_sch", "5VSB_SENSE",
        (248.92, 276.86), (245.11, 276.86)
    )
    txt = _remove_root_lane(
        txt, "05-kvm-aux-sensors.kicad_sch", "MAIN_5V_RAW",
        (248.92, 307.34), (245.11, 307.34)
    )
    txt = _edit_sheet_pin(
        txt, "05-kvm-aux-sensors.kicad_sch", "MAIN_5V_SENSE", "5V_SYS_SENSE"
    )
    txt, old, _tag = sc.rename_label_at(txt, 245.11, 312.42, "5V_SYS_SENSE")
    if old != "MAIN_5V_SENSE":
        raise SystemExit(f"REFUSE: root sheet-05 sense lane drifted: {old}")

    txt = _edit_sheet_pin(
        txt, "03-mcu-usb.kicad_sch", "5VSB_SENSE", "PWR_SOURCE_STATUS",
        shape="input"
    )
    txt, old, _tag = sc.rename_label_at(txt, 494.03, 87.63, "PWR_SOURCE_STATUS")
    if old != "5VSB_SENSE":
        raise SystemExit(f"REFUSE: root MCU status lane drifted: {old}")
    txt = _edit_sheet_pin(
        txt, "03-mcu-usb.kicad_sch", "MAIN_5V_SENSE", "5V_SYS_SENSE"
    )
    txt, old, _tag = sc.rename_label_at(txt, 494.03, 148.59, "5V_SYS_SENSE")
    if old != "MAIN_5V_SENSE":
        raise SystemExit(f"REFUSE: root MCU system-sense lane drifted: {old}")
    open(TOP, "w", encoding="utf-8", newline="").write(txt)


def main() -> None:
    migrate_power_sheet()
    migrate_port_sheet()
    migrate_sensor_sheet()
    migrate_mcu_sheet()
    migrate_root()
    print("Hub J_PWR retirement complete: two-stage 3-source topology is live.")


if __name__ == "__main__":
    main()
