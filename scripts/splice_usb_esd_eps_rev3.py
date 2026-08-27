#!/usr/bin/env python3
"""Add the exact USB D+/D- ESD array to an already-upgraded EPS Rev3."""
from __future__ import annotations

import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cec_beta_manifest  # noqa: E402
import cec_sch  # noqa: E402
import splice_usb_ingress_common as sc  # noqa: E402


ROOT = os.path.abspath(os.path.join(
    HERE, "..", "beta", cec_beta_manifest.BY_BOARD["eps-8pin-rev3"]["directory"]))
SHEET = os.path.join(ROOT, "05-usb-service.kicad_sch")
DONOR = os.path.join(HERE, "..", "beta", "pcie-8pin-3port", "07-usb-flash.kicad_sch")
PROJECT = "eps-8pin-rev3"
PATH = "ef7f6c4c-2dd9-4559-b472-96b33604786a/a18073cb-af35-5864-98f8-48efb88e5d99"


def main() -> int:
    if os.path.basename(ROOT) != "eps-8pin-rev3" or "old-revisions" in ROOT.lower():
        raise SystemExit(f"REFUSE: non-current EPS target {ROOT}")
    text = open(SHEET, encoding="utf-8").read()
    if '(property "Reference" "U4"' not in text:
        raise SystemExit("REFUSE: protected U4 ingress must exist before adding D3")
    if '(property "Reference" "D3"' in text:
        raise SystemExit("REFUSE: D3 already exists in current EPS Rev3 USB sheet")
    text, _ = sc.ensure_lib_symbol(text, "cec-vendor:USBLC6-2SC6", DONOR)
    pins = sc.get_pin_table(text, "cec-vendor:USBLC6-2SC6")
    props = dict(
        Manufacturer="UMW", MPN="USBLC6-2SC6", LCSC="C2687116",
        Datasheet="https://datasheet.lcsc.com/lcsc/2206231215_UMW-Youtai-Semiconductor-Co---Ltd--USBLC6-2SC6_C2687116.pdf",
        Note="Low-capacitance USB D+/D- ESD array with VBUS reference.")
    x, y = sc.gsnap(190.0), sc.gsnap(135.0)
    blobs = [cec_sch.emit_symbol(
        "D3", "cec-vendor", "USBLC6-2SC6", "USBLC6-2SC6", x, y,
        sorted(pins), PROJECT, PATH,
        fp="cec-Package_TO_SOT_SMD:SOT-23-6", props=props)]
    for pin in ("1", "6"):
        blobs.append(sc.wire_and_label(pins, "D3", pin, x, y, "USB_D_P"))
    for pin in ("3", "4"):
        blobs.append(sc.wire_and_label(pins, "D3", pin, x, y, "USB_D_N"))
    blobs.append(sc.wire_and_label(pins, "D3", "5", x, y, "VBUS"))
    blobs.append(sc.wire_and_power(
        pins, "D3", "2", x, y, "GND", PROJECT, PATH, "#PWR540"))
    content = "\n".join(blobs) + "\n"
    at = text.rindex("\t(sheet_instances") if "\t(sheet_instances" in text else None
    if at is None:
        start = text.index("(kicad_sch")
        at = start + len(cec_sch.carve(text, start)) - 1
    text = text[:at] + content + text[at:]
    open(SHEET, "w", encoding="utf-8").write(text)
    print("current EPS Rev3 USB ESD array applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
