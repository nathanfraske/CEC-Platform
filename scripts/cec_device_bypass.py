#!/usr/bin/env python3
"""Shared selected-device bypass rules for placement and board verification."""
import re


FIXED_DEVICE_RULES = (
    ("INA238", "6", "100n", "INA238"),
    ("INA181", "6", "100n", "INA181"),
    ("INA180", "5", "100n", "INA180"),
    ("INA240", "6", "100n", "INA240"),
    ("74AHCT244", "20", "100n", "74AHCT244"),
    ("SN74AHCT1G08", "5", "100n", "SN74AHCT1G08"),
    ("74LVC1G17", "5", "100n", "SN74LVC1G17"),
    ("REF3030", "1", "100n", "REF3030"),
    ("TPS3839", "3", "100n", "TPS3839"),
    ("TLV7011", "5", "100n", "TLV7011"),
    ("TJA1051", "3", "100n", "TJA1051"),
)


def capacitance_f(value):
    """Parse compact PCB/schematic capacitance notation into farads."""
    text = (value or "").strip().lower().replace("µ", "u").replace("μ", "u")
    text = text.replace(" ", "").removesuffix("f")
    embedded = re.fullmatch(r"(\d+)([pnum])(\d+)", text)
    if embedded:
        number = float("%s.%s" % (embedded.group(1), embedded.group(3)))
        prefix = embedded.group(2)
    else:
        plain = re.fullmatch(r"(\d+(?:\.\d+)?)([pnum]?)", text)
        if not plain:
            return None
        number = float(plain.group(1))
        prefix = plain.group(2)
    return number * {"": 1.0, "p": 1e-12, "n": 1e-9,
                     "u": 1e-6, "m": 1e-3}[prefix]


def kind_compatible(kind, farads):
    if farads is None:
        return False
    if kind == "100n":
        return abs(farads - 100e-9) <= 1e-15
    if kind == "at-least-1u":
        return farads + 1e-15 >= 1e-6
    if kind == "at-least-10u":
        return farads + 1e-15 >= 10e-6
    return farads > 0


def requirements_for_value(value, project_max_mm=3.5):
    """Yield (pin, kind, max_mm, source) requirements for a fitted device."""
    value = value or ""
    for token, pin, kind, source in FIXED_DEVICE_RULES:
        if token in value:
            yield pin, kind, project_max_mm, source
            break

    if "ESP32-C6-MINI-1" in value or "ESP32-S3-MINI-1" in value:
        yield "3", "100n", project_max_mm, "ESP32 peripheral schematic"
    elif "ESP32-S3-WROOM-1" in value:
        yield "2", "100n", project_max_mm, "ESP32 peripheral schematic"

    if "LP5907" in value:
        yield "1", "at-least-1u", 10.0, "LP5907"
        yield "5", "at-least-1u", 100.0, "LP5907"
    if "TLV62569" in value:
        yield "4", "at-least-10u", 2.0, "TLV62569"
    if "TLV75533" in value:
        pins = (("6", "ldo-input"), ("1", "ldo-output")) \
            if "PDRVR" in value else (("1", "ldo-input"), ("5", "ldo-output"))
        for pin, role in pins:
            yield pin, "at-least-1u", 2.0, "TLV75533:" + role
    if "TPS2121" in value:
        for pin, role in (("7", "IN1"), ("2", "IN2"), ("1", "OUT")):
            yield pin, "any", project_max_mm, "TPS2121:" + role
