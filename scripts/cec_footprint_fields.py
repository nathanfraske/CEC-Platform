#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Carry schematic component metadata into materialized PCB footprints.

KiCad's board-only API exposes footprint fields, while the repository's
headless generators start from an exported schematic inventory/netlist.  Keep
the two representations synchronized so downstream board-only admission can
consume explicit electrical/placement contracts and reviewers retain useful
MPN, sourcing, datasheet, and description metadata.
"""


_STRUCTURAL_FIELDS = {"Reference", "Value", "Footprint"}


def apply_assembly_state(footprint, part):
    """Carry native assembly flags from the live schematic inventory.

    Hidden string fields named DNP are not KiCad's native DNP flag. Keep the
    copper land for unpopulated parts while excluding them from pick/place.
    BOM exclusion is independently authored and must not be inferred from DNP.
    """
    expected = (
        bool(part.get("dnp", False)),
        not bool(part.get("in_bom", True)),
        not bool(part.get("on_board", True)) or bool(part.get("dnp", False)),
    )
    before = (footprint.IsDNP(), footprint.IsExcludedFromBOM(),
              footprint.IsExcludedFromPosFiles())
    if before == expected:
        return 0
    footprint.SetDNP(expected[0])
    footprint.SetExcludedFromBOM(expected[1])
    footprint.SetExcludedFromPosFiles(expected[2])
    return sum(a != b for a, b in zip(before, expected))


def footprint_properties(footprint):
    """Return all readable footprint fields as a plain string mapping."""
    fields = getattr(footprint, "GetFields", lambda: ())()
    out = {}
    for field in fields:
        try:
            name = str(field.GetName())
            value = str(field.GetText())
        except (AttributeError, TypeError):
            continue
        if name:
            out[name] = value
    return out


def apply_schematic_fields(footprint, part):
    """Apply a schematic inventory/Comp record to one PCB footprint.

    Reference, value, and footprint identity are handled by their dedicated
    PCB APIs.  Every other schematic field is copied and hidden by default;
    this preserves machine-readable authority without adding surprise text to
    fabrication layers.  Returns the number of value/visibility changes.
    """
    properties = (part.get("props", {}) if isinstance(part, dict)
                  else getattr(part, "props", {})) or {}
    before = footprint_properties(footprint)
    changed = 0
    for raw_name, raw_value in sorted(properties.items()):
        name = str(raw_name or "").strip()
        if not name or name in _STRUCTURAL_FIELDS:
            continue
        value = str(raw_value or "")
        if before.get(name) != value:
            footprint.SetField(name, value)
            changed += 1
        try:
            field = footprint.GetField(name)
            if field.IsVisible():
                field.SetVisible(False)
                changed += 1
        except (AttributeError, KeyError, TypeError):
            # The value still survived through SetField on APIs without a
            # mutable field proxy; visibility is cosmetic, not authority.
            pass
    return changed
