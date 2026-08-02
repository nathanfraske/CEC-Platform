#!/usr/bin/env python3
"""Normalize selected-part identity from verified order and footprint records.

Several BETA schematics paired a real LCSC code with a different vendor's
name or datasheet for a similarly named part.  That is unsafe because the
clamp characteristics are not interchangeable.  This mutator is deliberately
narrow: it updates only order codes whose exact identity was independently
checked against the distributor listing and the selected vendor document.
Two connector footprints also encode an exact manufacturer part number.  Those
are normalized only when the complete footprint library/name matches.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cec_sch_layout as L  # noqa: E402
from cec_fix_eps_rev3_bom_fields import _properties, _set_property  # noqa: E402


VERIFIED = {
    "C5736265": {
        "Manufacturer": "Espressif Systems",
        "MPN": "ESP32-C6-MINI-1-N4",
        "Datasheet": (
            "https://documentation.espressif.com/"
            "esp32-c6-mini-1_mini-1u_datasheet_en.pdf"
        ),
    },
    "C38695": {
        "Manufacturer": "NXP Semiconductors",
        "MPN": "TJA1051T/3/1J",
        "Datasheet": "https://www.nxp.com/docs/en/data-sheet/TJA1051.pdf",
    },
    "C80670": {
        "Manufacturer": "Texas Instruments",
        "MPN": "LP5907MFX-3.3/NOPB",
        "Datasheet": "https://www.ti.com/lit/ds/symlink/lp5907.pdf",
    },
    "C485916": {
        "Manufacturer": "Texas Instruments",
        "MPN": "TPS2121RUXR",
        "Datasheet": "https://www.ti.com/lit/ds/symlink/tps2121.pdf",
    },
    "C2058784": {
        "Manufacturer": "Texas Instruments",
        "MPN": "INA181A2IDBVR",
        "Datasheet": "https://www.ti.com/lit/ds/symlink/ina181.pdf",
    },
    "C702117": {
        "Manufacturer": "Texas Instruments",
        "MPN": "TLV7011DBVR",
        "Datasheet": "https://www.ti.com/lit/ds/symlink/tlv7011.pdf",
    },
    "C2868250": {
        "Manufacturer": "Texas Instruments",
        "MPN": "INA238AIDGSR",
        "Datasheet": "https://www.ti.com/lit/ds/symlink/ina238.pdf",
    },
    "C2683360": {
        "Manufacturer": "Kinghelm",
        "MPN": "KH-RJ45-58-8P8C",
        "Datasheet": "https://www.lcsc.com/datasheet/C2683360.pdf",
    },
    "C113952": {
        "Manufacturer": "MDD (Microdiode Semiconductor)",
        "MPN": "SMAJ5.0A",
        "Datasheet": "https://www.lcsc.com/datasheet/C113952.pdf",
    },
    "C192764": {
        "Manufacturer": "Texas Instruments",
        "MPN": "INA180A2IDBVR",
        "Datasheet": "https://www.ti.com/lit/ds/symlink/ina180.pdf",
    },
    "C2687116": {
        "Manufacturer": "UMW",
        "MPN": "USBLC6-2SC6",
        "Datasheet": (
            "https://datasheet.lcsc.com/lcsc/2206231215_UMW-"
            "Youtai-Semiconductor-Co---Ltd--USBLC6-2SC6_C2687116.pdf"
        ),
    },
    "C5261083": {
        "Manufacturer": "HXY MOSFET",
        "MPN": "PESD5V0S1BA",
        "Datasheet": "https://www.lcsc.com/datasheet/C5261083.pdf",
    },
    "C319148": {
        "Manufacturer": "XKB Connection",
        "MPN": "U262-161N-4BVC11",
        "Datasheet": (
            "https://datasheet.lcsc.com/szlcsc/1811141824_XKB-Enterprise-"
            "U262-161N-4BVC11_C319148.pdf"
        ),
    },
    "C135583": {
        "Manufacturer": "Nexperia",
        "MPN": "74AHCT244PW,118",
        "Datasheet": (
            "https://assets.nexperia.com/documents/data-sheet/"
            "74AHC_AHCT244.pdf"
        ),
    },
    "C720477": {
        "Manufacturer": "XUNPU",
        "MPN": "TS-1088-AR02016",
        "Datasheet": "https://www.lcsc.com/datasheet/C720477.pdf",
    },
    "C2060584": {
        "Manufacturer": "Texas Instruments",
        "MPN": "INA240A3DR",
        "Datasheet": "https://www.ti.com/lit/ds/symlink/ina240.pdf",
    },
    "C3013941": {
        "Manufacturer": "Espressif Systems",
        "MPN": "ESP32-S3-MINI-1-N4R2",
        "Datasheet": (
            "https://documentation.espressif.com/"
            "esp32-s3-mini-1_mini-1u_datasheet_en.pdf"
        ),
    },
    "C2913202": {
        "Manufacturer": "Espressif Systems",
        "MPN": "ESP32-S3-WROOM-1-N16R8",
        "Datasheet": (
            "https://www.espressif.com/sites/default/files/documentation/"
            "esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf"
        ),
    },
    "C113521": {
        "Manufacturer": "Texas Instruments",
        "MPN": "SN74AHCT1G08DBVR",
        "Datasheet": "https://www.ti.com/lit/ds/symlink/sn74ahct1g08.pdf",
    },
    "C96333": {
        "Manufacturer": "Texas Instruments",
        "MPN": "TPS3839K33DBZR",
        "Datasheet": "https://www.ti.com/lit/ds/symlink/tps3839.pdf",
    },
    "C16072": {
        "Manufacturer": "Alpha & Omega Semiconductor",
        "MPN": "AO4407A",
        "Datasheet": "https://www.aosmd.com/res/datasheets/AO4407A.pdf",
    },
    "C20917": {
        "Manufacturer": "Alpha & Omega Semiconductor",
        "MPN": "AO3400A",
        "Datasheet": "https://www.aosmd.com/res/datasheets/AO3400A.pdf",
    },
    "C122780": {
        "Manufacturer": "Nanjing Shiheng Electronics",
        "MPN": "MF72 5D20",
        "Datasheet": "https://www.lcsc.com/datasheet/C122780.pdf",
    },
    "C207092": {
        "Manufacturer": "Littelfuse",
        "MPN": "2920L700/12MR",
        "Datasheet": "https://www.lcsc.com/datasheet/C207092.pdf",
    },
    "C38423": {
        "Manufacturer": "Texas Instruments",
        "MPN": "REF3030AIDBZR",
        "Datasheet": "https://www.ti.com/lit/ds/symlink/ref3030.pdf",
    },
    "C96446": {
        "Manufacturer": "Samsung",
        "MPN": "CL10A106MA8NRNC",
    },
    "C15850": {
        "Manufacturer": "Samsung",
        "MPN": "CL21A106KAYNNNE",
    },
    "C15849": {
        "Manufacturer": "Samsung",
        "MPN": "CL10A105KB8NNNC",
    },
    "C29936": {
        "Manufacturer": "Samsung",
        "MPN": "CL10B105KA8NNNC",
    },
    "C1525": {
        "Manufacturer": "Samsung",
        "MPN": "CL05B104KO5NNNC",
    },
    "C23630": {
        "Manufacturer": "Samsung",
        "MPN": "CL10A225KO8NNNC",
    },
    "C17168": {
        "Manufacturer": "UNI-ROYAL",
        "MPN": "0402WGF0000TCE",
    },
    "C545549": {
        "Manufacturer": "UMW",
        "MPN": "BAT54S",
    },
}


VERIFIED_FOOTPRINTS = {
    "cec-Connector_JST:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal": {
        "Manufacturer": "JST",
        "MPN": "S2B-XH-A(LF)(SN)",
        "LCSC": "C157931",
        "Datasheet": "https://www.lcsc.com/datasheet/C157931.pdf",
    },
    "cec-Connector_Molex:Molex_Mini-Fit_Jr_87427-0802_2x04_P4.20mm_RA": {
        "Manufacturer": "Molex",
        "MPN": "87427-0802",
        "Datasheet": (
            "https://www.molex.com/content/dam/molex/molex-dot-com/products/"
            "automated/en-us/productspecificationpdf/874/87427/"
            "PS-87427-0001-001.pdf"
        ),
    },
}


def normalize_text(text: str) -> tuple[str, list[str]]:
    work = L._strip_lib_symbols(text)
    changed: list[str] = []
    for start, end, _at, ref, _rot, _lib_id, _mir in reversed(L._symbol_spans(work)):
        block = text[start:end]
        props = _properties(block)
        expected = VERIFIED.get(props.get("LCSC", ""))
        if expected is None:
            expected = VERIFIED_FOOTPRINTS.get(props.get("Footprint", ""))
        if not expected:
            continue
        touched = False
        for name, value in expected.items():
            if _properties(block).get(name, "") != value:
                block = _set_property(block, name, value)
                touched = True
        if touched:
            text = text[:start] + block + text[end:]
            changed.append(ref)
    return text, sorted(changed)


def beta_schematics(root: str = ROOT) -> list[str]:
    paths = glob.glob(os.path.join(root, "beta", "**", "*.kicad_sch"), recursive=True)
    return sorted(p for p in paths if "candidate" not in os.path.normpath(p).split(os.sep))


def normalize_file(path: str, *, check: bool = False) -> list[str]:
    with open(path, encoding="utf-8", errors="strict") as handle:
        before = handle.read()
    after, changed = normalize_text(before)
    if not check and after != before:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(after)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    paths = args.paths or beta_schematics()
    pending = []
    for path in paths:
        refs = normalize_file(path, check=args.check)
        if refs:
            pending.append((os.path.relpath(path, ROOT), refs))
            print(f"{os.path.relpath(path, ROOT)}: {', '.join(refs)}")
    if args.check and pending:
        return 1
    if not pending:
        print("verified LCSC identities already normalized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
