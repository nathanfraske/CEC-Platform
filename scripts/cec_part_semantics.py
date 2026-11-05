"""Exact, data-declared procurement semantics for physical PCB features.

Exclusion from an assembly BOM alone is not evidence that an object is made
by the PCB fabricator.  For example, an accidentally excluded IC still needs
an orderable identity.  No reference name, footprint substring or free-form
description is an authority for this classification.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping


FABRICATED_PCB_FEATURE = "fabricated_pcb_feature"

# Library assets for the authored bare pigtail fields. These are PCB lands,
# not unselected connector housings. Cable/pigtail assembly and fit remain
# separate requirements. Exact pairs prevent a populated connector using the
# same logical pin count from inheriting their procurement classification.
BARE_SOLDER_FIELDS = (
    {"lib_id": "cec:CEC_ATX_24",
     "footprint": "cec-Connector_Generic:ATX24_Daughterboard_Field_P4.20mm",
     "procurement_kind": FABRICATED_PCB_FEATURE, "in_bom": False},
    {"lib_id": "cec:CEC_CONN_2x4",
     "footprint": "cec-Connector_Generic:EPS8_Daughterboard_Field_P4.20mm",
     "procurement_kind": FABRICATED_PCB_FEATURE, "in_bom": False},
    {"lib_id": "cec:CEC_CONN_2x4",
     "footprint": "cec-Connector_Generic:PCIe8_Daughterboard_Field_P4.20mm",
     "procurement_kind": FABRICATED_PCB_FEATURE, "in_bom": False},
)


def is_fabricated_pcb_feature(
        record: Mapping, declarations: Iterable[Mapping]) -> bool:
    """Match a source record to an exact, non-purchased asset declaration.

    The declaration comes from a trusted asset registry, not instance prose.
    A changed symbol, changed footprint, missing BOM flag, or newly attached
    purchase identity must be reviewed instead of inheriting an exemption.
    This classifies procurement only; electrical, geometry, material, fit and
    other qualification requirements are deliberately unaffected.
    """
    if (record.get("in_bom") is not False
            or record.get("on_board") is not True
            or record.get("dnp") is not False):
        return False
    identity = (record.get("lib_id"), record.get("footprint"))
    if not all(isinstance(value, str) and value for value in identity):
        return False
    props = record.get("props", {})
    if not isinstance(props, Mapping) or any(
            str(props.get(field, "")).strip() for field in ("MPN", "LCSC")):
        return False
    return any(
        declaration.get("procurement_kind") == FABRICATED_PCB_FEATURE
        and declaration.get("in_bom") is False
        and not declaration.get("mpn") and not declaration.get("lcsc")
        and identity == (declaration.get("lib_id"), declaration.get("footprint"))
        for declaration in declarations
    )
