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


# Some devices require a high-frequency capacitor between two supply domains,
# not from one domain to ground.  Keep this separate from FIXED_DEVICE_RULES:
# both contracts apply to a TJA1051T/3 (VCC-to-GND on pin 3 and VIO-to-VCC
# between pins 5 and 3), and treating the second capacitor as an ordinary
# ground bypass encodes the wrong EMC circuit.
RAIL_TO_RAIL_DEVICE_RULES = (
    ("TJA1051T/3", "5", "3", "100n",
     "NXP AH1014 Rev. 1.5 sec. 8.9: VIO-to-VCC"),
    ("TJA1051TK/3", "5", "3", "100n",
     "NXP AH1014 Rev. 1.5 sec. 8.9: VIO-to-VCC"),
    ("TJA1042/3", "5", "3", "100n",
     "NXP AH1014 Rev. 1.5 sec. 8.9: VIO-to-VCC"),
)


def reference_affinity(cap_ref, owner_ref):
    """Whether two reference designators declare the same numbered cell.

    C30 beside U30 is a common schematic convention and the placement side of
    the pipeline has always used it as its strongest deterministic ownership
    tie-break.  Keep the rule deliberately narrow: both refs must end in the
    same decimal number.  Callers additionally apply it only to single-supply
    owners; a multi-rail selector such as U4 cannot unambiguously own C4 by
    name alone.  Boards without this convention continue to use the ordinary
    topology/value/distance matcher.
    """
    cap = re.search(r"(\d+)$", str(cap_ref or ""))
    owner = re.search(r"(\d+)$", str(owner_ref or ""))
    return bool(cap and owner and cap.group(1) == owner.group(1))


def local_bypass_technology(value, footprint):
    """Whether a capacitor may own a selected-device local bypass role.

    Local bypass ownership is a high-frequency placement/routing contract, not
    a generic capacitance-on-the-rail query.  A bulk electrolytic, polymer or
    tantalum reservoir may be essential to the PDN, but it cannot substitute
    for the ceramic at the IC pins.  Unknown footprints remain eligible for
    legacy/imported designs; known bulk technologies fail closed.
    """
    text = "%s %s" % (value or "", footprint or "")
    normalized = text.lower().replace("-", "_")
    bulk_tokens = (
        "cp_elec", "cp_radial", "capacitor_tht", "supercap",
        "tantalum", "polymer",
    )
    return not any(token in normalized for token in bulk_tokens)


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
    if kind == "local-hf":
        # A large ceramic reservoir is still useful for load-step energy, but
        # it must not own the device's high-frequency pin-bypass role.  Keep
        # the value ceiling intentionally broad enough for 100 nF or 1 uF
        # X5R/X7R implementations; footprint technology is checked
        # independently by ``local_bypass_technology``.
        return 0 < farads <= 1e-6 + 1e-15
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
            yield pin, "local-hf", project_max_mm, "TPS2121:" + role


def rail_to_rail_requirements_for_value(value, project_max_mm=3.5):
    """Yield local two-supply bypass contracts.

    Rows are ``(supply_pin, return_pin, kind, max_mm, source)``.  "return"
    identifies the capacitor's other terminal and does not imply ground.
    Callers resolve both actual pad net names from the fitted device, so the
    rule stays valid when projects rename their 3.3 V or 5 V domains.
    """
    value = value or ""
    for token, supply_pin, return_pin, kind, source in \
            RAIL_TO_RAIL_DEVICE_RULES:
        if token in value:
            yield supply_pin, return_pin, kind, project_max_mm, source
