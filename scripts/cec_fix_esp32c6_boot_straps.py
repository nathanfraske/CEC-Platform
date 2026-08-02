#!/usr/bin/env python3
"""Add the proven ESP32-C6 GPIO8 download strap pull-up.

The ESP32-C6 module datasheet states that joint download boot requires
GPIO8=1 and GPIO9=0, while GPIO8 has no default internal bias. Espressif's
ESP32-C6-DevKitC-1 reference schematic uses a 10 kohm pull-up on GPIO8.

This is a guarded, idempotent repair for the four BETA C6 schematics that
still left pad 22 unconnected. Check mode is the default. Use --apply to
write the mechanical schematic changes.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cec_sch  # noqa: E402
import cec_sch_gates  # noqa: E402
import cec_sch_layout  # noqa: E402


@dataclass(frozen=True)
class Target:
    relpath: str
    project: str
    instance_path: str
    resistor_y: float
    power_ref: str


TARGETS = (
    Target(
        "beta/eps-8pin/04-mcu.kicad_sch",
        "eps8pin-module",
        "ef7f6c4c-2dd9-4559-b472-96b33604786a/"
        "83ceb2d1-e50f-4838-831a-71136b7d1260",
        160.02,
        "#PWR0799",
    ),
    Target(
        "beta/pcie-8pin-2port/04-mcu.kicad_sch",
        "pcie8pin-2port-module",
        "a0c79a2e-4073-4d8d-b0bf-2c2ed1691f64/"
        "83ceb2d1-e50f-4838-831a-71136b7d1260",
        160.02,
        "#PWR0799",
    ),
    Target(
        "beta/pcie-8pin-3port/04-mcu.kicad_sch",
        "pcie8pin-3port-module",
        "a8ecf94e-f41a-4523-8cf1-1d72f47f3e7e/"
        "83ceb2d1-e50f-4838-831a-71136b7d1260",
        160.02,
        "#PWR0799",
    ),
    Target(
        "beta/eps-8pin-rev3/eps-8pin-rev3.kicad_sch",
        "eps-8pin-rev3",
        "ef7f6c4c-2dd9-4559-b472-96b33604786a",
        130.81,
        "#PWR919",
    ),
)


def _u1_pin(text: str, pin: str) -> tuple[float, float, float, float]:
    work = cec_sch_layout._strip_lib_symbols(text)
    instances = [s for s in cec_sch_layout._symbol_spans(work) if s[3] == "U1"]
    if len(instances) != 1:
        raise RuntimeError(f"expected one U1 instance, found {len(instances)}")
    inst = instances[0]
    lib_id = inst[5]
    if lib_id != "cec-vendor:ESP32-C6-MINI-1-N4":
        raise RuntimeError(f"U1 is {lib_id}, not the selected ESP32-C6 module")
    lib, name = lib_id.split(":", 1)
    block = cec_sch_gates._lib_blocks(text)[lib_id]
    used = {(lib, name): {"block": block, "pins": cec_sch.pin_table(block)}}
    parts = {"U1": (lib, name, "ESP32-C6-MINI-1-N4")}
    placement = {"U1": (inst[2][0], inst[2][1], inst[4])}
    return cec_sch_layout.pin_abs_rot(
        placement, used, parts, "U1", pin)


def _remove_no_connect(text: str, x: float, y: float) -> str:
    matches = []
    for match in re.finditer(r"\(no_connect\b", text):
        block = cec_sch.carve(text, match.start())
        at = re.search(r"\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\)", block)
        if at and abs(float(at.group(1)) - x) < 1e-3 and abs(
                float(at.group(2)) - y) < 1e-3:
            matches.append((match.start(), match.start() + len(block)))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one no-connect at ESP32-C6 GPIO8 ({x:g}, {y:g}), "
            f"found {len(matches)}")
    start, end = matches[0]
    if end < len(text) and text[end] == "\n":
        end += 1
    return text[:start] + text[end:]


def _compact_fields(block: str, x: float, y: float) -> str:
    block = block.replace(
        f"(at {cec_sch.f(x)} {cec_sch.f(y - 15.24)} 0)",
        f"(at {cec_sch.f(x)} {cec_sch.f(y - 6.35)} 0)",
        1,
    )
    return block.replace(
        f"(at {cec_sch.f(x)} {cec_sch.f(y + 15.24)} 0)",
        f"(at {cec_sch.f(x)} {cec_sch.f(y + 6.35)} 0)",
        1,
    )


def repaired_text(text: str, target: Target) -> tuple[str, bool]:
    if re.search(r'\(property\s+"Reference"\s+"R19"', text):
        return text, False
    if target.power_ref in text:
        raise RuntimeError(f"reserved power reference already exists: {target.power_ref}")

    pin_x, pin_y, out_x, out_y = _u1_pin(text, "22")
    if abs(out_x + 1.0) > 1e-6 or abs(out_y) > 1e-6:
        raise RuntimeError(
            f"unexpected GPIO8 outward direction ({out_x:g}, {out_y:g})")
    text = _remove_no_connect(text, pin_x, pin_y)

    stub_x = pin_x - 3.81
    resistor_x = pin_x - 21.59
    resistor_y = target.resistor_y
    props = {
        "Datasheet": "https://www.lcsc.com/product-detail/C25744.html",
        "Manufacturer": "UNI-ROYAL",
        "MPN": "0402WGF1002TCE",
        "LCSC": "C25744",
        "Description": "ESP32-C6 GPIO8 download-strap pull-up",
        "Note": (
            "10 kohm follows Espressif ESP32-C6-DevKitC-1; GPIO8 must be "
            "high with GPIO9 low for joint download boot"
        ),
    }
    resistor = cec_sch.emit_symbol(
        "R19", "cec-vendor", "R_Small", "10k",
        resistor_x, resistor_y, ["1", "2"], target.project,
        target.instance_path,
        fp="cec-Resistor_SMD:R_0402_1005Metric",
        props=props,
    )
    resistor = _compact_fields(resistor, resistor_x, resistor_y)
    top_y = resistor_y - 5.08
    bottom_y = resistor_y + 5.08
    additions = [
        cec_sch.emit_wire(pin_x, pin_y, stub_x, pin_y),
        cec_sch.emit_label("IO8_STRAP", stub_x, pin_y, 180),
        resistor,
        cec_sch.emit_wire(resistor_x, resistor_y - 2.54, resistor_x, top_y),
        cec_sch.emit_global_power(
            "+3V3", resistor_x, top_y, target.project,
            target.instance_path, target.power_ref),
        cec_sch.emit_wire(resistor_x, resistor_y + 2.54, resistor_x, bottom_y),
        cec_sch.emit_label("IO8_STRAP", resistor_x, bottom_y, 270),
    ]
    marker = "\t(sheet_instances"
    index = text.rfind(marker)
    if index < 0:
        # One legacy leaf has no sheet_instances section. KiCad accepts that
        # leaf, so insert immediately before the root schematic's final close.
        index = text.rfind("\n)")
    if index < 0:
        raise RuntimeError("schematic has no safe root insertion point")
    return text[:index] + "\n".join(additions) + "\n" + text[index:], True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    changed = 0
    for target in TARGETS:
        path = os.path.join(ROOT, *target.relpath.split("/"))
        with open(path, encoding="utf-8") as handle:
            original = handle.read()
        updated, needs_change = repaired_text(original, target)
        state = "already repaired"
        if needs_change:
            state = "would repair"
            changed += 1
            if args.apply:
                with open(path, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(updated)
                state = "repaired"
        print(f"{target.relpath}: {state}")
    if changed and not args.apply:
        print(f"{changed} schematic(s) need repair; rerun with --apply")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
