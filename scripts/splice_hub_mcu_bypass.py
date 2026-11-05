#!/usr/bin/env python3
"""Add the Hub WROOM module's missing local 100 nF bypass cell.

The ESP32-S3-WROOM-1 peripheral schematic uses both local bulk energy and a
high-frequency ceramic at VDD33.  C11 is the local bulk cell; this idempotent
source migration adds the distinct high-frequency C36 directly beside U1's
3V3 pin in the readable MCU leaf.  The production placement rule then owns
both capacitors to U1.2 from topology and value, rather than from a board-name
or coordinate exception.
"""
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import cec_sch


SHEET = ROOT / "beta" / "hub-standard-rev2" / "03-mcu-usb.kicad_sch"
PROJECT = "hub-standard-rev2"
INSTANCE = (
    "aa22b2b4-0e2b-481a-a188-ee3f43fcbaa8/"
    "7b6f3d0f-b959-517b-a652-351bfadacf28"
)
REF = "C36"


def main():
    text = SHEET.read_text(encoding="utf-8")
    if f'(property "Reference" "{REF}"' in text:
        print(f"{SHEET}: {REF} already present")
        return 0

    x, y = 165.10, 68.58
    symbol = cec_sch.emit_symbol(
        REF, "cec-vendor", "C_Small", "100nF", x, y, ["1", "2"],
        PROJECT, INSTANCE,
        fp="cec-Capacitor_SMD:C_0402_1005Metric",
        props={
            "Manufacturer": "Samsung",
            "MPN": "CL05B104KO5NNNC",
            "LCSC": "C1525",
            "BypassOwner": "U1.2",
            "Datasheet":
                "https://product.samsungsem.com/mlcc/CL05B104KO5NNN.do",
            "Description":
                "ESP32-S3-WROOM-1 U1 local 100nF X7R VDD33 bypass; "
                "place directly at U1 pin 2 with immediate ground return",
        })
    # Keep reference/value fields compact and outside the U1 body.
    symbol = symbol.replace(
        f'(at {cec_sch.f(x)} {cec_sch.f(y - 15.24)} 0)',
        f'(at {cec_sch.f(x)} {cec_sch.f(y - 6.35)} 0)', 1)
    symbol = symbol.replace(
        f'(at {cec_sch.f(x)} {cec_sch.f(y + 15.24)} 0)',
        f'(at {cec_sch.f(x)} {cec_sch.f(y + 6.35)} 0)', 1)

    elements = [
        symbol,
        # C36.1 joins the endpoint of the existing drawn +3V3 feed to U1.2;
        # ending on the existing node avoids a junction-dependent mid-wire T.
        cec_sch.emit_wire(x, y - 2.54, x, 64.77),
        cec_sch.emit_wire(x, 64.77, 173.99, 64.77),
        # C36.2 has its own short, visible ground return.
        cec_sch.emit_wire(x, y + 2.54, x, y + 5.08),
        cec_sch.emit_global_power(
            "GND", x, y + 5.08, PROJECT, INSTANCE, "#PWR399"),
    ]
    insertion = "\n".join(elements) + "\n"
    marker = "\t(sheet_instances"
    offset = text.rindex(marker)
    SHEET.write_text(text[:offset] + insertion + text[offset:],
                     encoding="utf-8", newline="\n")
    print(f"{SHEET}: added {REF} as U1 VDD33 local bypass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
