#!/usr/bin/env python3
"""Deterministic BETA schematic part-selection and topology audit.

This checker deliberately separates facts that CAD can prove from behavior
that still needs simulation or a bench.  It exports each authoritative KiCad
project root, walks the complete hierarchical symbol inventory, checks
selected-part identity and package consistency, and validates critical pin
roles against manufacturer pin tables.

It does not claim transient, EMC, thermal, firmware, or assembly sign-off.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cec_sch  # noqa: E402
import cec_sch_gates  # noqa: E402
import cec_hub_holdup  # noqa: E402
import cec_spice_sanity  # noqa: E402
import cec_toolchain  # noqa: E402
import cec_beta_manifest  # noqa: E402
from cec_normalize_verified_lcsc_parts import VERIFIED  # noqa: E402


SOURCES = {
    "TPS2121": "https://www.ti.com/lit/ds/symlink/tps2121.pdf",
    "LP5907": "https://www.ti.com/lit/ds/symlink/lp5907.pdf",
    "TLV62569": "https://www.ti.com/lit/ds/symlink/tlv62569.pdf",
    "TLV755P": "https://www.ti.com/lit/ds/symlink/tlv755p.pdf",
    "VLS252010HBX-2R2M-1": (
        "https://product.tdk.com/en/search/inductor/inductor/smd/"
        "info?part_no=VLS252010HBX-2R2M-1"
    ),
    "INA180": "https://www.ti.com/lit/ds/symlink/ina180.pdf",
    "INA181": "https://www.ti.com/lit/ds/symlink/ina181.pdf",
    "INA238": "https://www.ti.com/lit/ds/symlink/ina238.pdf",
    "INA240": "https://www.ti.com/lit/ds/symlink/ina240.pdf",
    "TLV7011": "https://www.ti.com/lit/ds/symlink/tlv7011.pdf",
    "TJA1051": "https://www.nxp.com/docs/en/data-sheet/TJA1051.pdf",
    "74AHCT244": (
        "https://assets.nexperia.com/documents/data-sheet/74AHC_AHCT244.pdf"
    ),
    "ESP32-C6-MINI-1": (
        "https://documentation.espressif.com/"
        "esp32-c6-mini-1_mini-1u_datasheet_en.pdf"
    ),
    "ESP32-C6-DevKitC-1": (
        "https://dl.espressif.com/dl/schematics/"
        "esp32-c6-devkitc-1-schematics.pdf"
    ),
    "ESP32-S3-MINI-1": (
        "https://documentation.espressif.com/"
        "esp32-s3-mini-1_mini-1u_datasheet_en.pdf"
    ),
    "ESP32-S3-WROOM-1": (
        "https://www.espressif.com/sites/default/files/documentation/"
        "esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf"
    ),
    "SN74AHCT1G08": "https://www.ti.com/lit/ds/symlink/sn74ahct1g08.pdf",
    "TPS3839": "https://www.ti.com/lit/ds/symlink/tps3839.pdf",
    "AO3400A": "https://www.aosmd.com/res/datasheets/AO3400A.pdf",
    "AO4407A": "https://www.aosmd.com/res/datasheets/AO4407A.pdf",
    "MF72": "https://www.lcsc.com/datasheet/C122780.pdf",
    "2920L700": "https://www.lcsc.com/datasheet/C207092.pdf",
    "REF3030": "https://www.ti.com/lit/ds/symlink/ref3030.pdf",
    "C2687116": (
        "https://datasheet.lcsc.com/lcsc/2206231215_UMW-"
        "Youtai-Semiconductor-Co---Ltd--USBLC6-2SC6_C2687116.pdf"
    ),
    "C5261083": "https://www.lcsc.com/datasheet/C5261083.pdf",
    "C319148": (
        "https://datasheet.lcsc.com/szlcsc/1811141824_XKB-Enterprise-"
        "U262-161N-4BVC11_C319148.pdf"
    ),
    "C5736265": (
        "https://www.lcsc.com/product-detail/"
        "wifi-modules_espressif-systems-esp32-c6-mini-1-n4_C5736265.html"
    ),
    "C38695": "https://www.lcsc.com/product-detail/C38695.html",
    "C80670": "https://www.lcsc.com/product-detail/C80670.html",
    "C141836": "https://www.lcsc.com/product-detail/C141836.html",
    "C487318": "https://www.lcsc.com/product-detail/C487318.html",
    "C138063": "https://www.lcsc.com/product-detail/C138063.html",
    "C2480": "https://www.lcsc.com/product-detail/C2480.html",
    "C404027": "https://www.lcsc.com/product-detail/C404027.html",
    "C88527": "https://www.lcsc.com/product-detail/C88527.html",
    "C27009": "https://www.lcsc.com/product-detail/C27009.html",
    "C25741": "https://www.lcsc.com/product-detail/C25741.html",
    "C132339": "https://www.lcsc.com/product-detail/C132339.html",
    "C485916": "https://www.lcsc.com/product-detail/C485916.html",
    "C2058784": "https://www.lcsc.com/product-detail/C2058784.html",
    "C702117": "https://www.lcsc.com/product-detail/C702117.html",
    "C2868250": "https://www.lcsc.com/product-detail/C2868250.html",
    "C2683360": "https://www.lcsc.com/product-detail/C2683360.html",
    "C113952": "https://www.lcsc.com/product-detail/C113952.html",
    "C192764": "https://www.lcsc.com/product-detail/C192764.html",
    "C96446": "https://www.lcsc.com/product-detail/C96446.html",
    "C15849": "https://www.lcsc.com/product-detail/C15849.html",
    "C23630": "https://www.lcsc.com/product-detail/C23630.html",
    "C17168": "https://www.lcsc.com/product-detail/C17168.html",
    "C545549": "https://www.lcsc.com/product-detail/C545549.html",
    "C15850": "https://www.lcsc.com/product-detail/C15850.html",
    "C29936": "https://www.lcsc.com/product-detail/C29936.html",
    "C1525": "https://product.samsungsem.com/mlcc/CL05B104KO5NNN.do",
    "SN74LVC1G17": "https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf",
}


VERIFIED_LCSC = {
    code: (fields["Manufacturer"], fields["MPN"])
    for code, fields in VERIFIED.items()
}


PACKAGE_RULES = (
    ("TPS2121RUXR", "RUX"),
    ("INA238AIDGSR", "VSSOP-10"),
    ("INA181A2IDBVR", "SOT-23-6"),
    ("INA180A2IDBVR", "SOT-23-5"),
    ("LP5907MFX-3.3/NOPB", "SOT-23-5"),
    ("TLV62569DBVR", "SOT-23-5"),
    ("TLV75533PDBVR", "SOT-23-5"),
    ("VLS252010HBX-2R2M-1", "VLS252010HBX-2R2M-1"),
    ("0402WGF4533TCE", "R_0402_1005Metric"),
    ("0402WGF1003TCE", "R_0402_1005Metric"),
    ("0402WGF5603TCE", "R_0402_1005Metric"),
    ("TLV7011DBVR", "SOT-23-5"),
    ("TJA1051T/3/1J", "SOIC-8"),
    ("74AHCT244PW,118", "TSSOP-20"),
    ("ESP32-C6-MINI-1-N4", "ESP32-C6-MINI-1"),
    ("ESP32-S3-MINI-1-N4R2", "ESP32-S2-MINI-1"),
    ("ESP32-S3-WROOM-1-N16R8", "ESP32-S3-WROOM-1"),
    ("SN74AHCT1G08DBVR", "SOT-23-5"),
    ("TPS3839K33DBZR", "SOT-23"),
    ("AO3400A", "SOT-23-3"),
    ("AO4407A", "SOIC-8"),
    ("REF3030AIDBZR", "REF3030_DBZ3"),
    ("CL10A106MA8NRNC", "C_0603_1608Metric"),
    ("CL10A105KB8NNNC", "C_0603_1608Metric"),
    ("CL10A225KO8NNNC", "C_0603_1608Metric"),
    ("CL21A106KAYNNNE", "C_0805_2012Metric"),
    ("CL10B105KA8NNNC", "C_0603_1608Metric"),
    ("CL05B104KO5NNNC", "C_0402_1005Metric"),
    ("0402WGF0000TCE", "R_0402_1005Metric"),
    ("RC0402FR-0711KL", "R_0402_1005Metric"),
    ("BAT54S", "SOT-23-3"),
    ("87427-0802", "87427-0802"),
)


TPS2121_PIN_NAMES = {
    "1": "OUT", "2": "IN2", "3": "CP2", "4": "OV2",
    "5": "OV1", "6": "PR1", "7": "IN1", "8": "OUT",
    "9": "ST", "10": "ILM", "11": "SS", "12": "GND",
}

TLV62569_PIN_NAMES = {
    "1": "EN", "2": "GND", "3": "SW", "4": "VIN", "5": "FB",
}

TLV75533_PIN_NAMES = {
    "1": "IN", "2": "GND", "3": "EN", "4": "NC", "5": "OUT",
}


ESP32_C6_PIN_NAMES = {
    "1": "GND", "2": "GND", "3": "3V3", "4": "NC", "5": "IO2",
    "6": "IO3", "7": "NC", "8": "EN", "9": "IO4", "10": "IO5",
    "11": "GND", "12": "IO0", "13": "IO1", "14": "GND", "15": "IO6",
    "16": "IO7", "17": "IO12", "18": "IO13", "19": "IO14",
    "20": "IO15", "21": "NC", "22": "IO8", "23": "IO9", "24": "IO18",
    "25": "IO19", "26": "IO20", "27": "IO21", "28": "IO22",
    "29": "IO23", "30": "RXD0", "31": "TXD0", "32": "NC", "33": "NC",
    "34": "NC", "35": "NC",
    **{str(pin): "GND" for pin in range(36, 54)},
}

ESP32_S3_MINI_PIN_NAMES = {
    "1": "GND", "2": "GND", "3": "3V3",
    **{str(pin): f"IO{pin - 4}" for pin in range(4, 23)},
    # Pins 23 and 24 are IO19 and IO20. The reviewed symbol presents their
    # USB alternate functions because that is how both boards use them.
    "23": "USB_D-", "24": "USB_D+", "25": "IO21", "26": "IO26",
    "27": "IO47", "28": "IO33", "29": "IO34", "30": "IO48",
    "31": "IO35", "32": "IO36", "33": "IO37", "34": "IO38",
    "35": "IO39", "36": "IO40", "37": "IO41", "38": "IO42",
    "39": "TXD0", "40": "RXD0", "41": "IO45", "42": "GND",
    "43": "GND", "44": "IO46", "45": "EN",
    **{str(pin): "GND" for pin in range(46, 66)},
}

ESP32_S3_WROOM_PIN_NAMES = {
    "1": "GND", "2": "3V3", "3": "EN", "4": "IO4", "5": "IO5",
    "6": "IO6", "7": "IO7", "8": "IO15", "9": "IO16", "10": "IO17",
    "11": "IO18", "12": "IO8", "13": "USB_D-", "14": "USB_D+",
    "15": "IO3", "16": "IO46", "17": "IO9", "18": "IO10", "19": "IO11",
    "20": "IO12", "21": "IO13", "22": "IO14", "23": "IO21",
    "24": "IO47", "25": "IO48", "26": "IO45", "27": "IO0",
    "28": "IO35", "29": "IO36", "30": "IO37", "31": "IO38",
    "32": "IO39", "33": "IO40", "34": "IO41", "35": "IO42",
    "36": "RXD0", "37": "TXD0", "38": "IO2", "39": "IO1",
    "40": "GND", "41": "GND",
}


def _finding(board: str, severity: str, code: str, message: str, ref: str = ""):
    return {
        "board": board,
        "severity": severity,
        "code": code,
        "ref": ref,
        "message": message,
    }


def discover_projects(beta_root: str) -> list[tuple[str, str, str]]:
    return list(cec_beta_manifest.project_paths(beta_root))


def export_netlist(schematic: str) -> tuple[dict[str, str], dict[str, list[tuple[str, str]]]]:
    cli = cec_toolchain.require_kicad_cli("BETA electrical audit")
    fd, path = tempfile.mkstemp(prefix="cec_beta_audit_", suffix=".net")
    os.close(fd)
    os.unlink(path)
    try:
        run = subprocess.run(
            [cli, "sch", "export", "netlist", "-o", path, schematic],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if run.returncode:
            detail = (run.stderr or run.stdout or "no diagnostic").strip()
            raise RuntimeError(f"netlist export failed for {schematic}: {detail[-1000:]}")
        return cec_spice_sanity.parse_netlist(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def pin_map(nets: dict[str, list[tuple[str, str]]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for net, nodes in nets.items():
        for ref, pin in nodes:
            out.setdefault(ref, {})[pin] = net
    return out


def _nc(net: str | None) -> bool:
    return net is None or net.startswith("unconnected-")


def _gnd(net: str | None) -> bool:
    return net == "GND" or bool(net and net.endswith("/GND"))


def _power(net: str | None) -> bool:
    if _nc(net) or _gnd(net):
        return False
    return bool(net and re.search(r"(?:^|/)(?:\+?3V3|\+?5V|\+?5VSB|VCC|VBUS)", net))


def _connected_non_ground(net: str | None) -> bool:
    return not _nc(net) and not _gnd(net)


def _role(net: str | None) -> str:
    if _nc(net):
        return "NC"
    if _gnd(net):
        return "GND"
    tail = (net or "").split("/")[-1].lstrip("+")
    if "CAN_H" in tail:
        return "CAN_H"
    if "CAN_L" in tail:
        return "CAN_L"
    if "DETECT" in tail:
        return "DETECT"
    if any(x in tail for x in ("5V", "VCC")):
        return "POWER5"
    return tail


def _require_pin(findings, board, ref, pins, pin, predicate, expected):
    net = pins.get(pin)
    if not predicate(net):
        findings.append(_finding(
            board,
            "BLOCKER",
            "PIN_ROLE",
            f"pin {pin} is {net!r}; expected {expected}",
            ref,
        ))


def _require_connected(findings, board, ref, pins, *numbers):
    for pin in numbers:
        _require_pin(findings, board, ref, pins, pin, lambda n: not _nc(n), "connected")


def _require_distinct(findings, board, ref, pins, a, b, purpose):
    na, nb = pins.get(a), pins.get(b)
    if not _nc(na) and not _nc(nb) and na == nb:
        findings.append(_finding(
            board,
            "BLOCKER",
            "PIN_SHORT",
            f"pins {a}/{b} share {na!r}; expected distinct {purpose} nets",
            ref,
        ))


def _fitted(rec: dict) -> bool:
    return rec.get("on_board", True) and not rec.get("dnp", False)


CAPACITOR_SPECS = {
    # Exact identities and dielectric families were checked against the
    # manufacturer/distributor records listed in SOURCES.  Effective
    # capacitance after voltage and temperature derating is deliberately not
    # inferred from these nominal records.
    "C1525": {"farads": 100e-9, "dielectric": "X7R", "package": "0402"},
    "C29936": {"farads": 1e-6, "dielectric": "X7R", "package": "0603"},
    "C15849": {"farads": 1e-6, "dielectric": "X5R", "package": "0603"},
    "C15850": {"farads": 10e-6, "dielectric": "X5R", "package": "0805"},
    "C96446": {"farads": 10e-6, "dielectric": "X5R", "package": "0603"},
}


def capacitance_f(value: str) -> float | None:
    """Parse the compact capacitor values used by the BETA schematics."""
    text = (value or "").strip().lower().replace("µ", "u").replace("μ", "u")
    text = text.replace(" ", "").removesuffix("farads").removesuffix("farad")
    text = text.removesuffix("f")
    embedded = re.fullmatch(r"(\d+)([pnum])(\d+)", text)
    if embedded:
        number = float(f"{embedded.group(1)}.{embedded.group(3)}")
        prefix = embedded.group(2)
    else:
        plain = re.fullmatch(r"(\d+(?:\.\d+)?)([pnum]?)", text)
        if not plain:
            return None
        number = float(plain.group(1))
        prefix = plain.group(2)
    scale = {"": 1.0, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3}
    return number * scale[prefix]


def _rail_capacitors(inventory, pins_by_ref):
    """Return fitted two-terminal capacitors that bridge one rail to GND."""
    out = []
    for ref, rec in sorted(inventory.items()):
        if not ref.startswith("C") or not _fitted(rec):
            continue
        nets = [net for net in pins_by_ref.get(ref, {}).values() if not _nc(net)]
        if len(nets) != 2 or not any(_gnd(net) for net in nets):
            continue
        rail = next((net for net in nets if not _gnd(net)), None)
        farads = capacitance_f(rec.get("value", ""))
        if rail and farads is not None:
            out.append({"ref": ref, "rail": rail, "farads": farads, "rec": rec})
    return out


def _bypass_requirements(inventory, pins_by_ref):
    """Build source-backed, per-device 100 nF bypass requirements.

    The electrical pass proves only that distinct capacitors exist on the
    correct supply nets.  Physical ownership and distance are checked from the
    PCB by cec_constraints; this function never treats a shared bulk capacitor
    as multiple local bypass parts.
    """
    rules = (
        ("INA238", "6", "required", "INA238"),
        ("INA181", "6", "required", "INA181"),
        ("INA180", "5", "required", "INA180"),
        ("INA240", "6", "required", "INA240"),
        ("74AHCT244", "20", "required", "74AHCT244"),
        ("SN74AHCT1G08", "5", "required", "SN74AHCT1G08"),
        ("74LVC1G17", "5", "required", "SN74LVC1G17"),
        ("REF3030", "1", "recommended", "REF3030"),
        ("TPS3839", "3", "recommended", "TPS3839"),
        ("TLV7011", "5", "recommended", "TLV7011"),
        ("TJA1051", "3", "recommended", "TJA1051"),
    )
    requirements = []
    for ref, rec in sorted(inventory.items()):
        if not _fitted(rec):
            continue
        value = rec.get("value", "")
        for token, supply_pin, strength, source in rules:
            if token not in value:
                continue
            rail = pins_by_ref.get(ref, {}).get(supply_pin)
            if not _nc(rail) and not _gnd(rail):
                requirements.append({
                    "ref": ref,
                    "rail": rail,
                    "pin": supply_pin,
                    "strength": strength,
                    "source": source,
                })
            break

        if "ESP32-C6-MINI-1" in value or "ESP32-S3-MINI-1" in value:
            supply_pin = "3"
        elif "ESP32-S3-WROOM-1" in value:
            supply_pin = "2"
        else:
            supply_pin = None
        if supply_pin:
            rail = pins_by_ref.get(ref, {}).get(supply_pin)
            if not _nc(rail) and not _gnd(rail):
                requirements.append({
                    "ref": ref,
                    "rail": rail,
                    "pin": supply_pin,
                    "strength": "recommended",
                    "source": "ESP32 module peripheral schematic",
                })
    return requirements


def _assign_distinct_bypass_caps(requirements, capacitors):
    """Assign one exact-nominal 100 nF rail capacitor to each requirement."""
    eligible = [cap for cap in capacitors if abs(cap["farads"] - 100e-9) <= 1e-15]
    by_rail = {}
    for cap in eligible:
        by_rail.setdefault(cap["rail"], []).append(cap)
    for caps in by_rail.values():
        caps.sort(key=lambda cap: (
            cap["rec"].get("props", {}).get("LCSC", "") not in CAPACITOR_SPECS,
            cap["ref"],
        ))
    assigned = {}
    used = set()
    # Mandatory parts receive inventory first.  This does not infer physical
    # ownership; it only proves that the schematic contains enough distinct
    # capacitors on the right nets.
    ordered = sorted(requirements, key=lambda req: (
        req["strength"] != "required", req["rail"], req["ref"]
    ))
    for req in ordered:
        cap = next((candidate for candidate in by_rail.get(req["rail"], [])
                    if candidate["ref"] not in used), None)
        if cap:
            assigned[req["ref"]] = cap
            used.add(cap["ref"])
    return assigned


def _cap_selected_and_verified(cap) -> tuple[bool, str]:
    rec = cap["rec"]
    props = rec.get("props", {})
    code = props.get("LCSC", "")
    spec = CAPACITOR_SPECS.get(code)
    if not re.fullmatch(r"C\d+", code) or not props.get("MPN"):
        return False, "no exact LCSC and MPN selection"
    if spec is None:
        return False, f"{code} dielectric and nominal value are not in the verified capacitor table"
    if spec["dielectric"] not in {"X5R", "X7R"}:
        return False, f"{code} uses {spec['dielectric']}, not X5R/X7R"
    if abs(spec["farads"] - cap["farads"]) > max(1e-15, cap["farads"] * 1e-6):
        return False, f"{code} identity disagrees with schematic value"
    return True, f"{code} {spec['dielectric']}"


def check_passives(board, inventory, pins_by_ref):
    """Audit stability capacitors, device bypassing, and passive identity."""
    findings = []
    capacitors = _rail_capacitors(inventory, pins_by_ref)
    requirements = _bypass_requirements(inventory, pins_by_ref)
    assigned = _assign_distinct_bypass_caps(requirements, capacitors)
    for req in requirements:
        cap = assigned.get(req["ref"])
        severity = "BLOCKER" if req["strength"] == "required" else "WARN"
        if cap is None:
            findings.append(_finding(
                board, severity, "DEVICE_BYPASS_MISSING",
                f"{req['source']} {req['strength']} 100 nF bypass for supply "
                f"pin {req['pin']} on {req['rail']}; no distinct capacitor is available",
                req["ref"],
            ))
            continue
        selected, detail = _cap_selected_and_verified(cap)
        if not selected:
            findings.append(_finding(
                board, severity, "CRITICAL_CAP_SELECTION",
                f"assigned bypass {cap['ref']} on {req['rail']} is not fully verified: {detail}",
                req["ref"],
            ))
    if requirements and len(assigned) == len(requirements):
        findings.append(_finding(
            board, "INFO", "DEVICE_BYPASS_COVERAGE",
            f"schematic provides {len(assigned)} distinct nominal 100 nF capacitors "
            "for all audited device supply requirements; PCB proximity is a separate gate",
        ))

    caps_by_rail = {}
    for cap in capacitors:
        caps_by_rail.setdefault(cap["rail"], []).append(cap)

    ldos = []
    for ref, rec in sorted(inventory.items()):
        if "LP5907" not in rec.get("value", "") or not _fitted(rec):
            continue
        pins = pins_by_ref.get(ref, {})
        input_net, output_net = pins.get("1"), pins.get("5")
        ldos.append((ref, input_net, output_net))
        selected_stability_caps = []
        for label, rail in (("input", input_net), ("output", output_net)):
            candidates = sorted(
                (cap for cap in caps_by_rail.get(rail, []) if cap["farads"] >= 1e-6),
                key=lambda cap: (cap["farads"], cap["ref"]),
            )
            if not candidates:
                findings.append(_finding(
                    board, "BLOCKER", "LP5907_STABILITY_CAP_MISSING",
                    f"{label} rail {rail!r} lacks the nominal >=1 uF capacitor required for stability",
                    ref,
                ))
                continue
            cap = candidates[0]
            selected_stability_caps.append(cap)
            selected, detail = _cap_selected_and_verified(cap)
            if not selected:
                findings.append(_finding(
                    board, "BLOCKER", "CRITICAL_CAP_SELECTION",
                    f"LP5907 {label} capacitor {cap['ref']} on {rail} is not fully verified: {detail}",
                    ref,
                ))
        if len(selected_stability_caps) == 2:
            refs = "/".join(cap["ref"] for cap in selected_stability_caps)
            findings.append(_finding(
                board, "WARN", "LP5907_EFFECTIVE_CAPACITANCE",
                f"{refs} meet the nominal topology, but CAD does not prove the LP5907 "
                "minimum 0.7 uF effective capacitance after tolerance, DC bias, and temperature",
                ref,
            ))

        output_total = sum(cap["farads"] for cap in caps_by_rail.get(output_net, []))
        input_total = sum(cap["farads"] for cap in caps_by_rail.get(input_net, []))
        reasons = []
        if output_total > 10e-6 + 1e-15:
            reasons.append(
                f"nominal output-node capacitance is {output_total * 1e6:.3g} uF, "
                "above the documented 10 uF application range"
            )
        if input_total + 1e-15 < output_total:
            reasons.append(
                f"nominal input capacitance {input_total * 1e6:.3g} uF is below "
                f"output-node capacitance {output_total * 1e6:.3g} uF for fast-load guidance"
            )
        if reasons:
            findings.append(_finding(
                board, "BLOCKER", "LP5907_CAP_NETWORK_UNVALIDATED",
                "; ".join(reasons) + "; stability and transient behavior require an approved capacitor network",
                ref,
            ))

    modern_supply_outputs = set()
    for ref, rec in sorted(inventory.items()):
        value = rec.get("value", "")
        if not _fitted(rec) or ("TLV62569" not in value and "TLV75533" not in value):
            continue
        pins = pins_by_ref.get(ref, {})
        if "TLV62569" in value:
            input_net = pins.get("4")
            sw_net = pins.get("3")
            output_net = None
            for lref, lrec in inventory.items():
                if not lref.startswith("L") or not _fitted(lrec):
                    continue
                lpins = pins_by_ref.get(lref, {})
                if sw_net in lpins.values():
                    other = [net for net in lpins.values() if net != sw_net]
                    if len(other) == 1:
                        output_net = other[0]
                        break
            requirements = (("input", input_net, 4.7e-6, None),
                            ("output", output_net, 10e-6, 47e-6))
            if output_net:
                modern_supply_outputs.add(output_net)
        else:
            input_net, output_net = pins.get("1"), pins.get("5")
            requirements = (("input", input_net, 1e-6, None),
                            ("output", output_net, 1e-6, 200e-6))
            if output_net:
                modern_supply_outputs.add(output_net)

        for label, rail, minimum, maximum in requirements:
            candidates = sorted(
                (cap for cap in caps_by_rail.get(rail, [])
                 if cap["farads"] + 1e-15 >= minimum),
                key=lambda cap: (cap["farads"], cap["ref"]),
            )
            total = sum(cap["farads"] for cap in caps_by_rail.get(rail, []))
            if not candidates:
                findings.append(_finding(
                    board, "BLOCKER", "REGULATOR_CAP_MISSING",
                    f"{value} {label} rail {rail!r} lacks the required nominal "
                    f">={minimum * 1e6:g} uF ceramic capacitance", ref))
                continue
            selected, detail = _cap_selected_and_verified(candidates[0])
            if not selected:
                findings.append(_finding(
                    board, "BLOCKER", "CRITICAL_CAP_SELECTION",
                    f"{value} {label} capacitor {candidates[0]['ref']} is not fully verified: {detail}",
                    ref))
            if maximum is not None and total > maximum + 1e-15:
                findings.append(_finding(
                    board, "BLOCKER", "REGULATOR_CAP_RANGE",
                    f"{value} {label} node totals {total * 1e6:.3g} uF nominal, above "
                    f"the reviewed {maximum * 1e6:g} uF range", ref))
        findings.append(_finding(
            board, "INFO", "REGULATOR_CAP_NETWORK",
            f"{value} nominal input/output capacitor network is inside the reviewed datasheet range",
            ref))

    for mcu_ref, mcu_rec in sorted(inventory.items()):
        value = mcu_rec.get("value", "")
        if not _fitted(mcu_rec) or "ESP32-" not in value:
            continue
        if "ESP32-C6-MINI-1" in value:
            supply_pin = "3"
        elif "ESP32-S3-MINI-1" in value:
            supply_pin = "3"
        elif "ESP32-S3-WROOM-1" in value:
            supply_pin = "2"
        else:
            continue
        supply_net = pins_by_ref.get(mcu_ref, {}).get(supply_pin)
        feeding = [ref for ref, _input, output in ldos if output == supply_net]
        if feeding:
            findings.append(_finding(
                board, "BLOCKER", "REGULATOR_HEADROOM_UNPROVEN",
                f"{','.join(feeding)} is rated for 250 mA, but the repository does not contain "
                f"a reviewed worst-case {supply_net} load budget for {value}, sensing, CAN, "
                "and housekeeping loads under the required wireless-disabled firmware mode",
                mcu_ref,
            ))
        if (supply_net not in modern_supply_outputs and
                not any(cap["farads"] >= 22e-6 for cap in caps_by_rail.get(supply_net, []))):
            findings.append(_finding(
                board, "WARN", "ESP32_REFERENCE_BULK_DEVIATION",
                f"{value} peripheral schematic shows 22 uF plus 100 nF on the module supply, "
                f"but {supply_net} has no nominal >=22 uF capacitor; do not add it until the "
                "regulator and total output-capacitance conflict is resolved",
                mcu_ref,
            ))
        elif supply_net in modern_supply_outputs:
            total = sum(cap["farads"] for cap in caps_by_rail.get(supply_net, []))
            findings.append(_finding(
                board, "INFO", "ESP32_REVIEWED_REGULATOR_NETWORK",
                f"{value} is fed by the reviewed regulator topology with "
                f"{total * 1e6:.3g} uF nominal distributed capacitance on {supply_net}",
                mcu_ref,
            ))

    # TPS2121 does not prescribe a universal capacitor value.  It does require
    # bypass capacitors on IN1, IN2, and OUT to be close and X5R/X7R.  Shared
    # rails are common in a cascaded mux, so a node-existence test is not
    # sufficient: assign a distinct selected ceramic to every device pin.
    # The PCB checker independently repeats one-to-one ownership with the
    # actual pad-to-pad distance.
    tps_requirements = []
    for ref, rec in sorted(inventory.items()):
        if "TPS2121" not in rec.get("value", "") or not _fitted(rec):
            continue
        pins = pins_by_ref.get(ref, {})
        for pin, label in (("7", "IN1"), ("2", "IN2"), ("1", "OUT")):
            rail = pins.get(pin)
            tps_requirements.append({"ref": ref, "pin": pin, "label": label, "rail": rail})
    tps_used = set()
    tps_assigned = {}
    for req in sorted(tps_requirements, key=lambda item: (item["rail"] or "", item["ref"], item["pin"])):
        candidates = sorted(caps_by_rail.get(req["rail"], []), key=lambda cap: cap["ref"])
        verified = [cap for cap in candidates
                    if cap["ref"] not in tps_used and _cap_selected_and_verified(cap)[0]]
        if verified:
            cap = verified[0]
            tps_assigned[(req["ref"], req["pin"])] = cap
            tps_used.add(cap["ref"])
            continue
        detail = "no rail-to-GND capacitor" if not candidates else "no unassigned verified X5R/X7R selection"
        findings.append(_finding(
            board, "BLOCKER", "TPS2121_BYPASS_NODE",
            f"{req['label']} pin {req['pin']} on {req['rail']!r} has {detail}; "
            "the datasheet calls for close X5R/X7R bypassing on IN1, IN2, and OUT",
            req["ref"],
        ))
    if tps_requirements and len(tps_assigned) == len(tps_requirements):
        findings.append(_finding(
            board, "INFO", "TPS2121_BYPASS_COVERAGE",
            f"{len(tps_assigned)} TPS2121 IN1/IN2/OUT pins have distinct exact X5R/X7R capacitors; "
            "PCB placement proximity remains independently gated",
        ))

    unresolved = []
    for ref, rec in sorted(inventory.items()):
        if not _fitted(rec) or not ref.startswith(("R", "C", "L", "FB", "FL")):
            continue
        props = rec.get("props", {})
        if not props.get("MPN") and not re.fullmatch(r"C\d+", props.get("LCSC", "")):
            unresolved.append(ref)
    if unresolved:
        findings.append(_finding(
            board, "WARN", "PASSIVE_SELECTION_INCOMPLETE",
            f"{len(unresolved)} fitted passive(s) lack both an exact MPN and LCSC order code: "
            + ", ".join(unresolved[:16]) + ("..." if len(unresolved) > 16 else ""),
        ))
    return findings


def _two_pin_bridge(pins: dict[str, str], first: str | None,
                    second_predicate) -> bool:
    """Return true when a two-terminal part bridges first to an accepted net."""
    if _nc(first):
        return False
    connected = [net for net in pins.values() if not _nc(net)]
    if len(connected) != 2 or first not in connected:
        return False
    other = connected[1] if connected[0] == first else connected[0]
    return second_predicate(other)


def _has_pullup(inventory, pins_by_ref, net, ohms=10000.0) -> bool:
    for ref, rec in inventory.items():
        if not ref.startswith("R") or not _fitted(rec):
            continue
        if cec_spice_sanity._r_ohms(rec.get("value", "")) != ohms:
            continue
        if _two_pin_bridge(pins_by_ref.get(ref, {}), net, _power):
            return True
    return False


def _has_ground_switch(inventory, pins_by_ref, net) -> bool:
    for ref, rec in inventory.items():
        if not ref.startswith("SW") or not _fitted(rec):
            continue
        if _two_pin_bridge(pins_by_ref.get(ref, {}), net, _gnd):
            return True
    return False


def _check_mcu_service_straps(findings, board, ref, inventory, pins_by_ref,
                              en_pin, boot_pin, *, c6_io8_pin=None):
    """Prove the manual reset and download-mode topology from the netlist.

    The 10 kohm GPIO8 pull-up for ESP32-C6 follows Espressif's DevKitC-1
    reference schematic.  The C6 module datasheet says joint download boot
    requires GPIO8=1 and GPIO9=0, while GPIO8 has no internal default bias.
    """
    mcu_pins = pins_by_ref.get(ref, {})
    en_net = mcu_pins.get(en_pin)
    boot_net = mcu_pins.get(boot_pin)
    if not _has_pullup(inventory, pins_by_ref, en_net):
        findings.append(_finding(
            board, "BLOCKER", "MCU_EN_BIAS",
            f"EN pad {en_pin} lacks the fitted 10 kohm pull-up used by the "
            "reset network", ref))
    if not _has_ground_switch(inventory, pins_by_ref, en_net):
        findings.append(_finding(
            board, "BLOCKER", "MCU_RESET_SWITCH",
            f"EN pad {en_pin} lacks a fitted manual reset switch to GND", ref))
    if not _has_ground_switch(inventory, pins_by_ref, boot_net):
        findings.append(_finding(
            board, "BLOCKER", "MCU_BOOT_SWITCH",
            f"boot strap pad {boot_pin} lacks a fitted manual BOOT switch to GND",
            ref))
    if c6_io8_pin is not None:
        io8_net = mcu_pins.get(c6_io8_pin)
        if not _has_pullup(inventory, pins_by_ref, io8_net):
            findings.append(_finding(
                board, "BLOCKER", "ESP32_C6_GPIO8_STRAP",
                f"GPIO8 pad {c6_io8_pin} lacks the 10 kohm pull-up required to "
                "make GPIO8=1 deterministic while GPIO9 is held low for joint "
                "download boot", ref))


def _symbol_named_pins(root_sch: str, rec: dict, cache: dict) -> dict[str, str]:
    path = os.path.join(os.path.dirname(root_sch), rec["sheet"])
    key = (path, rec["lib_id"])
    if key in cache:
        return cache[key]
    if path not in cache:
        with open(path, encoding="utf-8", errors="replace") as handle:
            cache[path] = cec_sch_gates._lib_blocks(handle.read())
    block = cache[path].get(rec["lib_id"], "")
    out = {}
    pin_start = re.compile(
        r"\(pin\s+(?:input|output|bidirectional|tri_state|passive|power_in|"
        r"power_out|open_collector|open_emitter|no_connect|unspecified)\s+"
    )
    for match in pin_start.finditer(block):
        pin = cec_sch.carve(block, match.start())
        name = re.search(r'\(name\s+"((?:[^"\\]|\\.)*)"', pin)
        number = re.search(r'\(number\s+"((?:[^"\\]|\\.)*)"', pin)
        if name and number:
            out[cec_sch_gates.L._unescape(number.group(1))] = (
                cec_sch_gates.L._unescape(name.group(1))
            )
    cache[key] = out
    return out


def _check_mcu_pin_table(findings, board, ref, root_sch, rec, pins, cache,
                         expected, supply_pin, en_pin):
    """Compare the embedded symbol input to the selected module pin table."""
    _check_named_pin_table(
        findings, board, ref, root_sch, rec, cache, expected,
        "selected module symbol",
    )
    for pin, name in expected.items():
        if name == "GND":
            _require_pin(findings, board, ref, pins, pin, _gnd, "GND")
        elif name == "NC" and not _nc(pins.get(pin)):
            findings.append(_finding(
                board, "BLOCKER", "PIN_ROLE",
                f"manufacturer NC pad {pin} is tied to {pins.get(pin)!r}", ref))
    _require_pin(findings, board, ref, pins, supply_pin, _power, "3.3 V supply")
    _require_connected(findings, board, ref, pins, en_pin)


def _check_named_pin_table(findings, board, ref, root_sch, rec, cache,
                           expected, description):
    """Compare an embedded schematic symbol with a manufacturer pin table."""
    names = _symbol_named_pins(root_sch, rec, cache)
    mismatches = []
    for pin in sorted(set(expected) | set(names), key=lambda x: int(x)):
        if names.get(pin) != expected.get(pin):
            mismatches.append(f"{pin}:{names.get(pin)!r}!={expected.get(pin)!r}")
    if mismatches:
        findings.append(_finding(
            board, "BLOCKER", "SYMBOL_PIN_TABLE",
            f"{description} differs from the manufacturer table: "
            + ", ".join(mismatches[:12]), ref))


def check_topology(board, root_sch, inventory, pins_by_ref):
    findings = []
    symbol_cache = {}
    for ref, rec in sorted(inventory.items()):
        if rec["dnp"] or not rec["on_board"]:
            continue
        value = rec["value"]
        pins = pins_by_ref.get(ref, {})

        if "BAT54S" in value:
            _require_pin(findings, board, ref, pins, "1", _gnd, "lower-clamp GND")
            _require_pin(findings, board, ref, pins, "2", _power, "upper-clamp supply")
            _require_connected(findings, board, ref, pins, "3")

        if "TPS2121" in value:
            _check_named_pin_table(
                findings, board, ref, root_sch, rec, symbol_cache,
                TPS2121_PIN_NAMES, "selected TPS2121 symbol",
            )
            _require_pin(findings, board, ref, pins, "12", _gnd, "GND")
            _require_pin(findings, board, ref, pins, "3", _gnd,
                         "CP2 low for fixed IN1 priority")
            _require_pin(findings, board, ref, pins, "4", _gnd,
                         "OV2 disabled low")
            _require_connected(findings, board, ref, pins, "1", "2", "5", "6", "7", "8", "10", "11")
            if pins.get("1") != pins.get("8"):
                findings.append(_finding(
                    board, "BLOCKER", "PIN_ROLE",
                    f"OUT pins 1/8 differ: {pins.get('1')!r} vs {pins.get('8')!r}", ref))
            _require_distinct(findings, board, ref, pins, "1", "2", "OUT vs IN2")
            _require_distinct(findings, board, ref, pins, "1", "7", "OUT vs IN1")

        elif "TLV62569" in value:
            _check_named_pin_table(
                findings, board, ref, root_sch, rec, symbol_cache,
                TLV62569_PIN_NAMES, "selected TLV62569 symbol",
            )
            _require_pin(findings, board, ref, pins, "2", _gnd, "GND")
            _require_connected(findings, board, ref, pins, "1", "3", "4", "5")
            _require_distinct(findings, board, ref, pins, "3", "4", "SW vs VIN")
            _require_distinct(findings, board, ref, pins, "3", "5", "SW vs FB")
            if pins.get("1") != pins.get("4"):
                findings.append(_finding(
                    board, "BLOCKER", "BUCK_ENABLE_SOURCE",
                    f"EN pin 1 is {pins.get('1')!r}, not the selected VIN net "
                    f"{pins.get('4')!r}", ref))

            sw_net = pins.get("3")
            fb_net = pins.get("5")
            output_net = None
            inductors = []
            for lref, lrec in inventory.items():
                if not lref.startswith("L") or not _fitted(lrec):
                    continue
                lpins = pins_by_ref.get(lref, {})
                if sw_net not in lpins.values():
                    continue
                other = [net for net in lpins.values() if net != sw_net]
                if len(other) == 1:
                    inductors.append((lref, lrec, other[0]))
            if len(inductors) != 1:
                findings.append(_finding(
                    board, "BLOCKER", "BUCK_INDUCTOR_TOPOLOGY",
                    f"SW net {sw_net!r} has {len(inductors)} fitted series-inductor candidates; expected one",
                    ref))
            else:
                lref, lrec, output_net = inductors[0]
                if lrec.get("props", {}).get("MPN") != "VLS252010HBX-2R2M-1":
                    findings.append(_finding(
                        board, "BLOCKER", "BUCK_INDUCTOR_SELECTION",
                        f"{lref} is not the reviewed VLS252010HBX-2R2M-1 2.2 uH part",
                        ref))

            top = bottom = None
            for rref, rrec in inventory.items():
                if not rref.startswith("R") or not _fitted(rrec):
                    continue
                rpins = pins_by_ref.get(rref, {})
                if fb_net not in rpins.values():
                    continue
                other = [net for net in rpins.values() if net != fb_net]
                if len(other) != 1:
                    continue
                record = (rref, rrec, cec_spice_sanity._r_ohms(rrec["value"]))
                if output_net is not None and other[0] == output_net:
                    top = record
                elif _gnd(other[0]):
                    bottom = record
            expected_top = 453e3 if board == "hub-standard-rev2" else 560e3
            if not top or not bottom:
                findings.append(_finding(
                    board, "BLOCKER", "BUCK_FEEDBACK_TOPOLOGY",
                    "feedback divider is not proven from buck output through FB to GND",
                    ref))
            elif not (math.isclose(top[2] or 0.0, expected_top, rel_tol=1e-9) and
                      math.isclose(bottom[2] or 0.0, 100e3, rel_tol=1e-9)):
                findings.append(_finding(
                    board, "BLOCKER", "BUCK_FEEDBACK_VALUE",
                    f"reviewed divider is {expected_top/1e3:g}k/100k; CAD has "
                    f"{top[0]}={top[2]} and {bottom[0]}={bottom[2]} ohm",
                    ref))
            elif output_net is not None:
                nominal = 0.6 * (1.0 + top[2] / bottom[2])
                findings.append(_finding(
                    board, "INFO", "BUCK_OUTPUT_SETPOINT",
                    f"CAD proves {top[0]}/{bottom[0]} feedback divider; nominal output is "
                    f"{nominal:.3f} V on {output_net}", ref))

        elif "TLV75533" in value:
            _check_named_pin_table(
                findings, board, ref, root_sch, rec, symbol_cache,
                TLV75533_PIN_NAMES, "selected TLV75533 symbol",
            )
            _require_pin(findings, board, ref, pins, "2", _gnd, "GND")
            _require_pin(findings, board, ref, pins, "1", _connected_non_ground,
                         "connected non-ground input supply")
            _require_pin(findings, board, ref, pins, "5", _power, "regulated output")
            _require_connected(findings, board, ref, pins, "3")
            _require_distinct(findings, board, ref, pins, "1", "5", "LDO input/output")
            if pins.get("1") != pins.get("3"):
                findings.append(_finding(
                    board, "BLOCKER", "LDO_ENABLE_SOURCE",
                    f"EN pin 3 is {pins.get('3')!r}, not input net {pins.get('1')!r}", ref))
            if not _nc(pins.get("4")):
                findings.append(_finding(
                    board, "BLOCKER", "PIN_ROLE", f"NC pin 4 is tied to {pins.get('4')!r}", ref))

        elif "TLV7011" in value:
            _require_pin(findings, board, ref, pins, "2", _gnd, "GND")
            _require_pin(findings, board, ref, pins, "5", _power, "supply rail")
            _require_connected(findings, board, ref, pins, "1", "3", "4")
            _require_distinct(findings, board, ref, pins, "3", "4", "comparator input")

        elif "INA181" in value:
            _require_pin(findings, board, ref, pins, "2", _gnd, "GND")
            _require_pin(findings, board, ref, pins, "6", _power, "supply rail")
            _require_connected(findings, board, ref, pins, "1", "3", "4", "5")
            _require_distinct(findings, board, ref, pins, "3", "4", "shunt Kelvin")

        elif "INA180" in value:
            _require_pin(findings, board, ref, pins, "2", _gnd, "GND")
            _require_pin(findings, board, ref, pins, "5", _power, "supply rail")
            _require_connected(findings, board, ref, pins, "1", "3", "4")
            _require_distinct(findings, board, ref, pins, "3", "4", "shunt Kelvin")

        elif "INA238" in value:
            _require_pin(findings, board, ref, pins, "7", _gnd, "GND")
            _require_pin(findings, board, ref, pins, "6", _power, "supply rail")
            _require_connected(findings, board, ref, pins, "1", "2", "4", "5", "8", "9", "10")
            _require_distinct(findings, board, ref, pins, "9", "10", "shunt Kelvin")

        elif "INA240" in value and "SOIC-8" in rec["footprint"]:
            _require_pin(findings, board, ref, pins, "2", _gnd, "GND")
            _require_pin(findings, board, ref, pins, "6", _power, "supply rail")
            _require_pin(findings, board, ref, pins, "3", _gnd, "ground-referenced REF2")
            _require_pin(findings, board, ref, pins, "7", _gnd, "ground-referenced REF1")
            _require_connected(findings, board, ref, pins, "1", "5", "8")
            _require_distinct(findings, board, ref, pins, "1", "8", "shunt sense")

        elif "LP5907" in value:
            _require_pin(findings, board, ref, pins, "2", _gnd, "GND")
            # The input is often diode-fed and therefore has an anonymous net
            # name such as Net-(D3-K).  Connectivity, not the net label, proves
            # that the pin is supplied.
            _require_pin(findings, board, ref, pins, "1", _connected_non_ground,
                         "connected non-ground input supply")
            _require_pin(findings, board, ref, pins, "5", _power, "regulated output")
            _require_connected(findings, board, ref, pins, "3")
            _require_distinct(findings, board, ref, pins, "1", "5", "LDO input/output")
            if not _nc(pins.get("4")):
                findings.append(_finding(
                    board, "BLOCKER", "PIN_ROLE", f"NC pin 4 is tied to {pins.get('4')!r}", ref))

        elif "TJA1051" in value:
            _require_pin(findings, board, ref, pins, "2", _gnd, "GND")
            _require_pin(findings, board, ref, pins, "3", _power, "5 V VCC")
            _require_pin(findings, board, ref, pins, "5", _power, "3.3 V VIO")
            _require_connected(findings, board, ref, pins, "1", "4", "6", "7")
            _require_distinct(findings, board, ref, pins, "6", "7", "CAN_H/CAN_L")

        elif "74AHCT244" in value:
            _require_pin(findings, board, ref, pins, "10", _gnd, "GND")
            _require_pin(findings, board, ref, pins, "20", _power, "5 V VCC")
            _require_pin(findings, board, ref, pins, "1", _gnd, "enabled /OE1 low")
            _require_pin(findings, board, ref, pins, "19", _gnd, "enabled /OE2 low")
            for a, y in (("2", "18"), ("4", "16"), ("6", "14"), ("8", "12"),
                         ("17", "3"), ("15", "5"), ("13", "7"), ("11", "9")):
                _require_connected(findings, board, ref, pins, a, y)
                _require_distinct(findings, board, ref, pins, a, y, "buffer input/output")

        elif "74LVC1G17" in value:
            _require_pin(findings, board, ref, pins, "3", _gnd, "GND")
            _require_pin(findings, board, ref, pins, "5", _power, "supply rail")
            _require_connected(findings, board, ref, pins, "2", "4")
            _require_distinct(findings, board, ref, pins, "2", "4", "buffer input/output")

        elif "SN74AHCT1G08" in value:
            _require_pin(findings, board, ref, pins, "3", _gnd, "GND")
            _require_pin(findings, board, ref, pins, "5", _power, "4.5 V to 5.5 V supply")
            _require_connected(findings, board, ref, pins, "1", "2", "4")
            if pins.get("1") != pins.get("2"):
                findings.append(_finding(
                    board, "BLOCKER", "PIN_ROLE",
                    f"AND inputs 1/2 are {pins.get('1')!r}/{pins.get('2')!r}; "
                    "the selected level-shifter topology requires them tied", ref))
            _require_distinct(findings, board, ref, pins, "1", "4", "logic input/output")

        elif "TPS3839" in value:
            _require_pin(findings, board, ref, pins, "1", _gnd, "GND")
            _require_pin(findings, board, ref, pins, "3", _power, "monitored 3.3 V rail")
            _require_connected(findings, board, ref, pins, "2")

        elif "REF3030" in value:
            _require_pin(findings, board, ref, pins, "1", _power, "input supply")
            _require_pin(findings, board, ref, pins, "3", _gnd, "GND")
            _require_connected(findings, board, ref, pins, "2")
            _require_distinct(findings, board, ref, pins, "1", "2", "reference input/output")

        if "ESP32-C6-MINI-1" in value:
            _check_mcu_pin_table(
                findings, board, ref, root_sch, rec, pins, symbol_cache,
                ESP32_C6_PIN_NAMES, "3", "8")
            _check_mcu_service_straps(
                findings, board, ref, inventory, pins_by_ref,
                "8", "23", c6_io8_pin="22")
        elif "ESP32-S3-MINI-1" in value:
            _check_mcu_pin_table(
                findings, board, ref, root_sch, rec, pins, symbol_cache,
                ESP32_S3_MINI_PIN_NAMES, "3", "45")
            _check_mcu_service_straps(
                findings, board, ref, inventory, pins_by_ref, "45", "4")
            if value.endswith("N4R2") and not _nc(pins.get("26")):
                findings.append(_finding(
                    board, "BLOCKER", "VARIANT_PIN_USE",
                    f"N4R2 reserves IO26 for embedded PSRAM, but pad 26 is {pins.get('26')!r}", ref))
        elif "ESP32-S3-WROOM-1" in value:
            _check_mcu_pin_table(
                findings, board, ref, root_sch, rec, pins, symbol_cache,
                ESP32_S3_WROOM_PIN_NAMES, "2", "3")
            _check_mcu_service_straps(
                findings, board, ref, inventory, pins_by_ref, "3", "27")
            if rec["props"].get("MPN", "").endswith("N16R8"):
                for pin in ("28", "29", "30"):
                    if not _nc(pins.get(pin)):
                        findings.append(_finding(
                            board, "BLOCKER", "VARIANT_PIN_USE",
                            f"N16R8 uses pad {pin} for octal PSRAM, but it is {pins.get(pin)!r}", ref))
    return findings


def check_bom(board, inventory):
    findings = []
    selection_prefixes = ("U", "Q", "D", "J", "F", "L", "RS", "SW")
    datasheet_prefixes = ("U", "Q")
    for ref, rec in sorted(inventory.items()):
        props = rec["props"]
        # Global and hierarchical power symbols are connectivity annotations,
        # not physical BOM items.  Some legacy generators assigned them PWRxxx
        # references instead of #PWRxxx, so the reference alone is insufficient.
        if rec.get("lib_id", "").startswith("cec-power:"):
            continue
        assembled = rec["on_board"] and not rec["dnp"]
        if rec["dnp"] and rec["in_bom"]:
            findings.append(_finding(
                board, "WARN", "DNP_IN_BOM",
                "DNP part remains in the source BOM and must be filtered by assembly variant",
                ref))
        if not assembled:
            continue
        description = props.get("Description", "")
        fabricated_feature = (
            "Daughterboard_Field" in rec["footprint"] or
            "NOT a stocked/purchased part" in description
        )
        if not rec["footprint"]:
            findings.append(_finding(
                board, "BLOCKER", "MISSING_FOOTPRINT", "assembled part has no footprint", ref))
        text = " ".join((rec["value"], props.get("MPN", ""), props.get("Manufacturer", "")))
        if "TBD" in text.upper():
            findings.append(_finding(
                board, "BLOCKER", "UNSELECTED_PART", f"assembled selection is unresolved: {text}", ref))

        lcsc = props.get("LCSC", "")
        valid_order_code = bool(re.fullmatch(r"C\d+", lcsc))
        if ref.startswith(selection_prefixes) and not fabricated_feature:
            selection_text = " ".join((props.get("Manufacturer", ""),
                                         props.get("MPN", ""))).lower()
            explicit_connector_selection = (
                bool(props.get("MPN")) and
                "generic" not in selection_text and
                "tbd" not in selection_text
            )
            generic_connector = (
                ref.startswith("J") and (
                    "generic" in selection_text or
                    ("Connector_PinHeader" in rec["footprint"] and
                     not explicit_connector_selection)
                )
            )
            for field in ("Manufacturer", "MPN"):
                if not props.get(field):
                    severity = "WARN"
                    # An exact order code is sufficient to identify an item,
                    # even when the human-readable fields are absent.  Without
                    # either an MPN or an order code, critical ICs, connectors,
                    # shunts, and semiconductors are not orderable selections.
                    if (field == "MPN" and not valid_order_code and
                            not generic_connector and
                            ref.startswith(("U", "Q", "J", "RS"))):
                        severity = "BLOCKER"
                    findings.append(_finding(
                        board, severity, "MISSING_BOM_FIELD", f"assembled part lacks {field}", ref))
            if generic_connector:
                findings.append(_finding(
                    board, "BLOCKER", "GENERIC_CONNECTOR_SELECTION",
                    "assembled connector uses a generic placeholder instead of a mating orderable part",
                    ref))
        if ref.startswith(datasheet_prefixes) and not props.get("Datasheet"):
            findings.append(_finding(
                board, "WARN", "MISSING_DATASHEET", "active part has no instance datasheet link", ref))

        manufacturer = props.get("Manufacturer", "")
        if re.fullmatch(r"C\d+", manufacturer):
            findings.append(_finding(
                board, "BLOCKER", "BOM_FIELD_SWAP", "Manufacturer contains an LCSC order code", ref))
        if lcsc and not re.fullmatch(r"C\d+", lcsc):
            findings.append(_finding(
                board, "BLOCKER", "BOM_FIELD_SWAP", f"LCSC field is not an order code: {lcsc!r}", ref))
        if lcsc in VERIFIED_LCSC:
            expected_manufacturer, expected_mpn = VERIFIED_LCSC[lcsc]
            if (manufacturer, props.get("MPN", "")) != (expected_manufacturer, expected_mpn):
                findings.append(_finding(
                    board, "BLOCKER", "SELECTED_PART_IDENTITY",
                    f"{lcsc} resolves to {expected_manufacturer} {expected_mpn}, not "
                    f"{manufacturer} {props.get('MPN', '')}", ref))

        mpn = props.get("MPN", "")
        for expected_mpn, footprint_token in PACKAGE_RULES:
            if mpn == expected_mpn and footprint_token not in rec["footprint"]:
                findings.append(_finding(
                    board, "BLOCKER", "PACKAGE_MISMATCH",
                    f"{mpn} requires footprint family {footprint_token}; got {rec['footprint']}", ref))
    return findings


def _ov1_divider(inventory, pins_by_ref, mux_ref):
    """Return the selected OV1 top/bottom resistors when CAD proves the divider.

    TPS2121 pin 5 is OV1 and pin 7 is IN1.  The top resistor must connect OV1
    to IN1 and the bottom resistor must connect OV1 to GND.  This deliberately
    rejects value-only guesses and grounded or otherwise different networks.
    """
    mux_pins = pins_by_ref.get(mux_ref, {})
    ov_net = mux_pins.get("5")
    in1_net = mux_pins.get("7")
    if _nc(ov_net) or _gnd(ov_net) or _nc(in1_net):
        return None
    top = bottom = None
    for ref, rec in inventory.items():
        if (not ref.startswith("R") or rec["dnp"] or not rec["on_board"] or
                ref == mux_ref):
            continue
        resistor_pins = pins_by_ref.get(ref, {})
        if ov_net not in resistor_pins.values():
            continue
        other_nets = [net for net in resistor_pins.values() if net != ov_net]
        if len(other_nets) != 1:
            continue
        record = (ref, rec, cec_spice_sanity._r_ohms(rec["value"]))
        if other_nets[0] == in1_net:
            top = record
        elif _gnd(other_nets[0]):
            bottom = record
    return (top, bottom) if top and bottom else None


def _check_tps2121_ovp(board, inventory, pins_by_ref):
    findings = []
    has_lp5907 = any(
        "LP5907" in rec["value"] and rec["on_board"] and not rec["dnp"]
        for rec in inventory.values()
    )
    for ref, rec in sorted(inventory.items()):
        if "TPS2121" not in rec["value"] or rec["dnp"] or not rec["on_board"]:
            continue
        ov_net = pins_by_ref.get(ref, {}).get("5")
        divider = _ov1_divider(inventory, pins_by_ref, ref)
        if divider:
            top, bottom = divider
            r_top, r_bottom = top[2], bottom[2]
            if not r_top or not r_bottom:
                continue
            nominal = 1.06 * (1.0 + r_top / r_bottom)
            message = (
                f"CAD proves {top[0]}={r_top:g} ohm and {bottom[0]}={r_bottom:g} ohm "
                f"on OV1; TPS2121 rising trip is {nominal:.3f} V nominal"
            )
            # The selected UNI-ROYAL WGF parts are 1%.  TPS2121 rising VREF is
            # 1.01 V min and 1.10 V max.  Evaluate both resistor extremes as
            # inputs, rather than trusting the nominal-only result.
            if (top[1]["props"].get("MPN") == "0402WGF4702TCE" and
                    bottom[1]["props"].get("MPN") == "0402WGF1002TCE"):
                trip_min = 1.01 * (1.0 + r_top * 0.99 / (r_bottom * 1.01))
                trip_max = 1.10 * (1.0 + r_top * 1.01 / (r_bottom * 0.99))
                message += f" and {trip_min:.3f} to {trip_max:.3f} V at specified extremes"
                if has_lp5907 and trip_max > 6.0:
                    message += "; the board contains an LP5907 with 6.0 V VIN absolute maximum"
                    findings.append(_finding(
                        board, "BLOCKER", "OVP_MARGIN", message, ref))
                else:
                    findings.append(_finding(
                        board, "WARN", "OVP_THRESHOLD", message, ref))
            else:
                findings.append(_finding(
                    board, "WARN", "OVP_THRESHOLD", message, ref))
        elif _gnd(ov_net):
            severity = "BLOCKER" if has_lp5907 else "WARN"
            message = "OV1 is tied to GND, so this mux stage provides no IN1 overvoltage cutoff"
            if has_lp5907:
                message += "; the board contains an LP5907 with 6.0 V VIN absolute maximum"
            findings.append(_finding(board, severity, "OVP_DISABLED", message, ref))
    return findings


def _check_hub_holdup(board, inventory, pins_by_ref):
    """Prove source-loss detection is upstream of the isolated reservoir.

    This check is intentionally reference-specific because these nets form one
    ratified safety/persistence cell.  A value-only search could accept a
    second, unrelated divider or a reservoir on the wrong side of D1.
    """
    if board != "hub-standard-rev2":
        return []
    findings = []

    def blocker(ref, message):
        findings.append(_finding(
            board, "BLOCKER", "HOLDUP_SOURCE_DROPOUT_TOPOLOGY", message, ref))

    def fitted(ref):
        rec = inventory.get(ref)
        return bool(rec and rec.get("on_board") and not rec.get("dnp"))

    def require_pins(ref, expected):
        actual = pins_by_ref.get(ref, {})
        for pin, net in expected.items():
            if actual.get(pin) != net:
                blocker(ref, f"pin {pin} is {actual.get(pin)!r}, expected {net!r}")

    c1 = inventory.get("C1")
    c1_props = (c1 or {}).get("props", {})
    if (not fitted("C1") or capacitance_f((c1 or {}).get("value", "")) != 4700e-6 or
            c1_props.get("LCSC") != "C487318" or
            c1_props.get("MPN") != "VKMI2101C472MV" or
            c1_props.get("Manufacturer") != "Ymin"):
        blocker("C1", "requires fitted Ymin VKMI2101C472MV / C487318, 4700uF +/-20%")
    require_pins("C1", {"1": "/+5V_HOLD", "2": "GND"})

    d1 = inventory.get("D1")
    d1_props = (d1 or {}).get("props", {})
    if (not fitted("D1") or d1_props.get("LCSC") != "C2480" or
            d1_props.get("MPN") != "SS14"):
        blocker("D1", "requires fitted MDD SS14 / C2480 hold-up isolation diode")
    # KiCad diode convention: pin 1 = cathode, pin 2 = anode.
    require_pins("D1", {"1": "/+5V_HOLD", "2": "+5VSB"})

    if not fitted("RJ_HOLD"):
        blocker("RJ_HOLD", "default hold-up jumper must be fitted")
    require_pins("RJ_HOLD", {"1": "/+5V_HOLD", "2": "/LOGIC_REG_IN"})
    rj_buck = inventory.get("RJ_BUCK")
    if not rj_buck or not rj_buck.get("dnp") or rj_buck.get("in_bom"):
        blocker("RJ_BUCK", "alternate pre-regulator jumper must remain DNP and excluded from BOM")
    require_pins("U3", {"1": "/LOGIC_REG_IN", "4": "/LOGIC_REG_IN"})

    require_pins("R12", {"1": "+5VSB", "2": "/BLACKOUT_SENSE"})
    require_pins("R13", {"1": "/BLACKOUT_SENSE", "2": "GND"})
    require_pins("C12", {"1": "/BLACKOUT_SENSE", "2": "GND"})
    require_pins("U1", {"12": "/BLACKOUT_SENSE", "22": "/PWR_FAIL_INT"})
    require_pins("U8", {
        "1": "/PWR_FAIL_INT", "2": "GND", "3": "/BLACKOUT_SENSE",
        "4": "/COMP_THRESH", "5": "+3V3",
    })
    require_pins("R26", {"1": "+3V3", "2": "/COMP_THRESH"})
    require_pins("R27", {"1": "/COMP_THRESH", "2": "GND"})
    require_pins("R28", {"1": "/PWR_FAIL_INT", "2": "/COMP_THRESH"})
    require_pins("U4", {"1": "GND", "2": "/EN", "3": "+3V3"})

    reviewed = {
        "R12": (47e3, "0402WGF4702TCE"),
        "R13": (27e3, "0402WGF2702TCE"),
        "R26": (11e3, "RC0402FR-0711KL"),
        "R27": (10e3, "0402WGF1002TCE"),
        "R28": (1e6, "0402WGF1004TCE"),
    }
    for ref, (expected_ohms, expected_mpn) in reviewed.items():
        rec = inventory.get(ref) or {}
        actual_ohms = cec_spice_sanity._r_ohms(rec.get("value", ""))
        if (not fitted(ref) or not math.isclose(actual_ohms or 0.0, expected_ohms,
                                                rel_tol=1e-9) or
                rec.get("props", {}).get("MPN") != expected_mpn):
            blocker(ref, f"reviewed source-dropout value/selection is {expected_ohms:g} ohm, {expected_mpn}")
    if (not fitted("C12") or
            not math.isclose(capacitance_f(inventory["C12"]["value"]) or 0.0,
                             10e-9, rel_tol=1e-9)):
        blocker("C12", "BLACKOUT_SENSE filter must be fitted 10nF")

    calculation = cec_hub_holdup.model()
    if calculation["sudden_loss_margin_ms"] <= 0:
        blocker("C1", "minimum-capacitance sudden-loss model does not clear the firmware budget")
    if calculation["trip_to_regulation_headroom_min_V"] <= 0:
        blocker("U8", "worst-low source trip does not precede the reviewed buck regulation floor")

    if not any(f["severity"] == "BLOCKER" for f in findings):
        findings.append(_finding(
            board, "INFO", "HOLDUP_SOURCE_DROPOUT_ORDER",
            f"U8 watches final selected +5VSB ahead of D1 and asserts PWR_FAIL_INT; "
            f"nominal trip {calculation['trip_nominal_V']:.3f} V, bounded "
            f"{calculation['trip_min_V']:.3f}..{calculation['trip_max_V']:.3f} V, "
            f"at least {calculation['trip_to_regulation_headroom_min_V'] * 1e3:.0f} mV "
            "ahead of the reviewed buck regulation floor"))
        findings.append(_finding(
            board, "INFO", "HOLDUP_SUDDEN_LOSS_BUDGET",
            f"C1 minimum 3760uF, 4.15V conservative reservoir start, 3.45V "
            f"regulation floor, 85% conversion and {cec_hub_holdup.HUB_LOAD_A * 1e3:.3f}mA "
            f"load produce {calculation['sudden_loss_hold_ms']:.2f}ms; the 10ms "
            f"trigger-to-durable-commit budget retains {calculation['sudden_loss_margin_ms']:.2f}ms"))
        findings.append(_finding(
            board, "WARN", "HOLDUP_BENCH_OPEN",
            "topology and bounded paper model pass, but OQ-56 still must measure slow-brownout behavior, capacitor ESR/aging/temperature, source decay, load shed, and durable-commit latency"))
    return findings


def check_board_specific(board, inventory, pins_by_ref):
    findings = []
    findings += _check_tps2121_ovp(board, inventory, pins_by_ref)
    findings += _check_hub_holdup(board, inventory, pins_by_ref)
    regulator_contracts = {
        # Loads already include the engineering 20% design margin.
        "12vhpwr-standard": {
            "load_A": 0.233591, "capacity_A": 0.500,
            "post_ldo": True,
        },
        "hub-standard-rev2": {
            # Conservative source capacity is the selected inductor's 1.76 A
            # thermal current rating, below the TLV62569's 2 A IC rating.
            "load_A": 0.215386, "capacity_A": 1.760,
            "post_ldo": False,
        },
    }
    contract = regulator_contracts.get(board)
    if contract:
        bucks = [ref for ref, rec in inventory.items()
                 if "TLV62569" in rec.get("value", "") and _fitted(rec)]
        post_ldos = [ref for ref, rec in inventory.items()
                     if "TLV75533" in rec.get("value", "") and _fitted(rec)]
        legacy = [ref for ref, rec in inventory.items()
                  if "LP5907" in rec.get("value", "") and _fitted(rec)]
        if len(bucks) != 1 or bool(post_ldos) != contract["post_ldo"] or legacy:
            findings.append(_finding(
                board, "BLOCKER", "REGULATOR_ARCHITECTURE",
                f"expected one TLV62569, post-LDO={contract['post_ldo']}, and no LP5907; "
                f"found bucks={bucks}, post-LDOs={post_ldos}, legacy={legacy}"))
        elif contract["post_ldo"] and len(post_ldos) != 1:
            findings.append(_finding(
                board, "BLOCKER", "REGULATOR_ARCHITECTURE",
                f"expected exactly one TLV75533 post-LDO; found {post_ldos}"))
        else:
            load = contract["load_A"]
            capacity = contract["capacity_A"]
            findings.append(_finding(
                board, "INFO", "REGULATOR_LOAD_MARGIN",
                f"reviewed worst-case rail load including 20% margin is {load * 1e3:.3f} mA; "
                f"conservative source capacity is {capacity * 1e3:.0f} mA "
                f"({(capacity - load) / capacity * 100:.1f}% remaining)"))

    if board == "hub-standard-rev2":
        l2 = inventory.get("L2")
        if not l2 or not l2["dnp"] or l2["in_bom"]:
            findings.append(_finding(
                board, "BLOCKER", "HUB_L2_STATE", "L2 must remain DNP and excluded from BOM", "L2"))
        else:
            findings.append(_finding(
                board, "INFO", "HUB_L2_DNP", "L2 is correctly DNP; no inductance selection is required", "L2"))

        priority_contract = {
            "U5": {
                "1": "/PSU_5V", "2": "/USB_VBUS", "3": "GND",
                "6": "/5VSB_RAW", "7": "/5VSB_RAW", "8": "/PSU_5V",
            },
            "U11": {
                "1": "/PSU_5V_KVM", "2": "/KVM_5V_IN", "3": "GND",
                "6": "/PSU_5V", "7": "/PSU_5V", "8": "/PSU_5V_KVM",
            },
            "U7": {
                "1": "+5VSB", "2": "/PSU_5V_KVM", "3": "GND",
                "6": "/MAIN_5V_RAW", "7": "/MAIN_5V_RAW", "8": "+5VSB",
            },
        }
        contract_ok = True
        for mux_ref, expected in priority_contract.items():
            actual = pins_by_ref.get(mux_ref, {})
            for pin, net in expected.items():
                if actual.get(pin) != net:
                    contract_ok = False
                    findings.append(_finding(
                        board, "BLOCKER", "HUB_SOURCE_PRIORITY",
                        f"pin {pin} is {actual.get(pin)!r}, expected {net!r} for "
                        "MAIN_5V > 5VSB > USB > KVM fixed priority",
                        mux_ref,
                    ))
        if contract_ok:
            findings.append(_finding(
                board, "INFO", "HUB_SOURCE_PRIORITY",
                "CAD proves MAIN_5V > 5VSB > USB > KVM fixed priority with CP2 low on all three TPS2121 stages",
            ))

        mux_bypass_contract = {
            # One capacitor per physical mux power pin.  C24/C25 and C26/C28
            # intentionally duplicate shared electrical rails because the PCB
            # must place one local part at each different TPS2121 package.
            "C9": "/5VSB_RAW", "C10": "/USB_VBUS", "C24": "/PSU_5V",
            "C25": "/PSU_5V", "C22": "/KVM_5V_IN", "C26": "/PSU_5V_KVM",
            "C27": "/MAIN_5V_RAW", "C28": "/PSU_5V_KVM", "C15": "+5VSB",
        }
        mux_caps_ok = True
        for cap_ref, rail in mux_bypass_contract.items():
            rec = inventory.get(cap_ref, {})
            cap_pins = pins_by_ref.get(cap_ref, {})
            cap = next((item for item in _rail_capacitors(inventory, pins_by_ref)
                        if item["ref"] == cap_ref), None)
            selected = bool(cap and _cap_selected_and_verified(cap)[0])
            if (not _fitted(rec) or set(cap_pins.values()) != {rail, "GND"} or not selected):
                mux_caps_ok = False
                findings.append(_finding(
                    board, "BLOCKER", "HUB_TPS2121_LOCAL_BYPASS",
                    f"expected fitted exact X5R/X7R capacitor from {rail} to GND for the reviewed mux-pin assignment",
                    cap_ref,
                ))
        if mux_caps_ok:
            findings.append(_finding(
                board, "INFO", "HUB_TPS2121_LOCAL_BYPASS",
                "all nine U5/U11/U7 IN1, IN2, and OUT pins have explicit one-per-pin exact ceramic selections; placement distance is gated after regeneration",
            ))

    if board == "eps-8pin-rev3":
        d2 = pins_by_ref.get("D2", {})
        has_mux = any("TPS2121" in rec["value"] and not rec["dnp"] for rec in inventory.values())
        if ("VBUS" in (d2.get("2") or "") and "5VSB" in (d2.get("1") or "") and not has_mux):
            findings.append(_finding(
                board, "BLOCKER", "LEGACY_USB_ORING",
                "D2 directly Schottky-ORs USB VBUS into +5VSB; the approved TPS2121 plus fuse ingress change is absent",
                "D2"))

    if board == "argb-standard":
        j1 = inventory.get("J1")
        if j1 and (not j1["footprint"] or "TBD" in " ".join(j1["props"].values()).upper()):
            findings.append(_finding(
                board, "BLOCKER", "SATA_CONNECTOR_UNSELECTED",
                "SATA power input has no selected orderable connector or footprint", "J1"))
        j1_pins = pins_by_ref.get("J1", {})
        q1_pins = pins_by_ref.get("Q1", {})
        f1_pins = pins_by_ref.get("F1", {})
        input_net = j1_pins.get("7")
        protected_net = f1_pins.get("1")
        drain_nets = [q1_pins.get(pin) for pin in ("5", "6", "7", "8")]
        source_nets = [q1_pins.get(pin) for pin in ("1", "2", "3")]
        if (_nc(input_net) or any(net != input_net for net in drain_nets) or
                _nc(protected_net) or any(net != protected_net for net in source_nets)):
            findings.append(_finding(
                board, "BLOCKER", "PMOS_REVERSE_POLARITY_ORIENTATION",
                "AO4407A must connect SATA input to drain pins 5..8 and the protected "
                "fuse path to source pins 1..3 so its body diode faces input to load",
                "Q1"))
        if inventory.get("Q1", {}).get("value") == "AO4407A":
            findings.append(_finding(
                board, "BLOCKER", "PMOS_RDS_ON_MARGIN",
                "AO4407A has guaranteed maximum RDS(on) only at VGS=-6 V and -10 V; "
                "this 5 V gate-to-source drive has no guaranteed maximum, so 7 A loss "
                "and thermal margin are not proven",
                "Q1"))
        if inventory.get("F1", {}).get("value") == "2920L700/12MR":
            findings.append(_finding(
                board, "BLOCKER", "PPTC_AMBIENT_DERATING",
                "2920L700/12MR holds 7.00 A only at 20 C; the manufacturer table "
                "reduces hold current to 6.36 A at 40 C and 5.88 A at 50 C",
                "F1"))
        if inventory.get("RT1", {}).get("value") == "MF72-5D-20":
            findings.append(_finding(
                board, "BLOCKER", "NTC_CURRENT_MARGIN",
                "MF72 5D20 is rated for 7 A maximum steady-state at 25 C with about "
                "0.097 ohm residual resistance; the selected 7 A rail has no current "
                "or ambient-temperature margin",
                "RT1"))
    return findings


MEZZ_EXPECTED = {
    "J6P": {"1": "POWER5", "3": "POWER5", "5": "POWER5",
             "2": "GND", "4": "GND", "6": "GND"},
    "J6C": {"1": "GND", "2": "GND", "3": "CAN_H", "4": "NC",
             "5": "CAN_L", "6": "NC", "7": "GND", "8": "GND"},
    "J6D": {"1": "DETECT", "2": "GND", "3": "NC", "4": "GND"},
}


def check_mezzanine(all_boards):
    findings = []
    for board in ("atx-24pin-rev3", "hub-standard-rev2"):
        data = all_boards.get(board)
        if not data:
            findings.append(_finding(board, "BLOCKER", "MEZZ_MISSING", "board missing from audit"))
            continue
        for ref, expected in MEZZ_EXPECTED.items():
            actual = {pin: _role(net) for pin, net in data["pins"].get(ref, {}).items()}
            for pin, role in expected.items():
                if actual.get(pin, "NC") != role:
                    findings.append(_finding(
                        board, "BLOCKER", "MEZZ_PINMAP",
                        f"{ref}.{pin} role is {actual.get(pin, 'NC')}, expected {role}", ref))
    atx = all_boards.get("atx-24pin-rev3", {}).get("inventory", {})
    hub = all_boards.get("hub-standard-rev2", {}).get("inventory", {})
    for ref in MEZZ_EXPECTED:
        if ref not in atx or ref not in hub:
            continue
        if atx[ref]["dnp"] != hub[ref]["dnp"]:
            findings.append(_finding(
                "atx-24pin-rev3+hub-standard-rev2", "BLOCKER",
                "MEZZ_ASSEMBLY_MISMATCH",
                f"{ref} is {'DNP' if atx[ref]['dnp'] else 'fitted'} on the 24-pin board "
                f"but {'DNP' if hub[ref]['dnp'] else 'fitted'} on the Hub",
                ref,
            ))
        if atx[ref]["dnp"] or hub[ref]["dnp"]:
            findings.append(_finding(
                "atx-24pin-rev3+hub-standard-rev2", "BLOCKER",
                "MEZZ_SELECTED_BUT_DNP",
                f"{ref} is selected by the 2026-08-01 owner decision but is DNP on at least one mating board",
                ref,
            ))
        if ("PinHeader" in atx[ref]["footprint"] and
                "PinHeader" in hub[ref]["footprint"]):
            findings.append(_finding(
                "atx-24pin-rev3+hub-standard-rev2", "BLOCKER",
                "MEZZ_MATING_PARTS_UNRESOLVED",
                f"{ref} uses pin-header footprints on both boards; an orderable header/socket pair and stack height are not selected",
                ref,
            ))
    if not any(f["code"] == "MEZZ_PINMAP" for f in findings):
        findings.append(_finding(
            "atx-24pin-rev3+hub-standard-rev2", "INFO", "MEZZ_MATCH",
            "segmented J6P/J6C/J6D pin roles match across both boards"))
    return findings


def check_lcsc_consistency(all_boards):
    """Reject contradictory identities or package sizes for one order code."""
    grouped = {}
    for board, data in all_boards.items():
        for ref, rec in data["inventory"].items():
            if not _fitted(rec):
                continue
            props = rec.get("props", {})
            code = props.get("LCSC", "")
            if not re.fullmatch(r"C\d+", code):
                continue
            entry = grouped.setdefault(code, {
                "Manufacturer": {}, "MPN": {}, "package": {},
            })
            locus = f"{board}:{ref}"
            for field in ("Manufacturer", "MPN"):
                value = props.get(field, "").strip()
                if value:
                    entry[field].setdefault(value, []).append(locus)
            size = re.search(
                r"(01005|0201|0402|0603|0805|1206|1210|2010|2512)",
                rec.get("footprint", ""),
            )
            if size:
                entry["package"].setdefault(size.group(1), []).append(locus)

    findings = []
    for code, fields in sorted(grouped.items()):
        for field, variants in fields.items():
            if len(variants) <= 1:
                continue
            detail = "; ".join(
                f"{value}: {', '.join(sorted(loci)[:4])}"
                for value, loci in sorted(variants.items())
            )
            findings.append(_finding(
                "BETA-cross-board",
                "BLOCKER",
                "LCSC_IDENTITY_CONFLICT" if field != "package" else
                "LCSC_PACKAGE_CONFLICT",
                f"{code} has conflicting {field} records: {detail}",
            ))
    return findings


def check_pour_current_contract():
    """Expose disagreements between the two active pour-current models.

    The geometric pipeline may conservatively use one source, but release
    documentation must not describe either value as verified while the thermal
    adapter and synthesis table disagree.
    """
    import cec_fresh_wave
    import cec_synth_pipeline
    import cec_thermal_overlay

    findings = []
    for board, params in sorted(cec_fresh_wave.BOARD_PARAMS.items()):
        asks = params.get("pour_asks") or ()
        if not asks:
            continue
        cfg = cec_thermal_overlay.board_thermal_config(board, board_hint=board)
        thermal = dict((cfg[0] if cfg else None) or {})
        for net in sorted({ask.get("net") for ask in asks if ask.get("net")}):
            left = thermal.get(net)
            right = cec_synth_pipeline.spec_net_current(board, net)
            if left is None and right is None:
                findings.append(_finding(
                    board, "BLOCKER", "POUR_CURRENT_BASIS_MISSING",
                    f"{net} has a pour ask but neither active current model "
                    "declares a positive design-basis current",
                ))
            elif (left is not None and right is not None and
                  not math.isclose(float(left), float(right),
                                   rel_tol=1e-9, abs_tol=1e-12)):
                findings.append(_finding(
                    board, "BLOCKER", "POUR_CURRENT_MODEL_CONFLICT",
                    f"{net} is {float(left):g} A in board_thermal_config and "
                    f"{float(right):g} A in spec_net_current; the pipeline "
                    "does not have one owner-validated design basis",
                ))
    return findings


def audit(beta_root: str):
    projects = discover_projects(beta_root)
    all_boards = {}
    findings = []
    for board, _directory, schematic in projects:
        components, nets = export_netlist(schematic)
        inventory = cec_sch_gates.inventory(schematic)
        pins = pin_map(nets)
        all_boards[board] = {
            "root": os.path.relpath(schematic, ROOT),
            "components": len(components),
            "inventory": inventory,
            "pins": pins,
        }
        findings += check_bom(board, inventory)
        findings += check_topology(board, schematic, inventory, pins)
        findings += check_passives(board, inventory, pins)
        findings += check_board_specific(board, inventory, pins)

    findings += check_mezzanine(all_boards)
    findings += check_lcsc_consistency(all_boards)
    findings += check_pour_current_contract()
    severities = Counter(f["severity"] for f in findings)
    board_summaries = {}
    for board in sorted(all_boards):
        local = [f for f in findings if f["board"] == board]
        board_summaries[board] = {
            "components": all_boards[board]["components"],
            "inventory_records": len(all_boards[board]["inventory"]),
            "blockers": sum(f["severity"] == "BLOCKER" for f in local),
            "warnings": sum(f["severity"] == "WARN" for f in local),
        }
    return {
        "scope": "authoritative BETA KiCad project roots; candidate copies excluded",
        "projects": len(projects),
        "sources": SOURCES,
        "summary": dict(sorted(severities.items())),
        "boards": board_summaries,
        "findings": sorted(findings, key=lambda f: (
            {"BLOCKER": 0, "WARN": 1, "INFO": 2}.get(f["severity"], 9),
            f["board"], f["code"], f["ref"],
        )),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--beta-root", default=os.path.join(ROOT, "beta"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-out")
    args = parser.parse_args(argv)
    report = audit(args.beta_root)
    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"BETA electrical audit: {report['projects']} projects")
        print("summary:", ", ".join(f"{k}={v}" for k, v in report["summary"].items()))
        for finding in report["findings"]:
            ref = f" {finding['ref']}" if finding["ref"] else ""
            print(f"{finding['severity']:7} {finding['board']}{ref}: "
                  f"[{finding['code']}] {finding['message']}")
    return 1 if report["summary"].get("BLOCKER", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
