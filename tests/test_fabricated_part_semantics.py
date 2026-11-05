"""Procurement exemptions require exact trusted assets, not BOM omission."""
import copy

import pytest

import cec_beta_electrical_audit as audit
import cec_beta_manifest
import cec_part_semantics as semantics
import cec_sch_gates
import cec_xfcn_contract


def declaration():
    return {"lib_id": "arbitrary:EtchedSenseContact",
            "footprint": "different:PlanarCoupon", "in_bom": False,
            "procurement_kind": semantics.FABRICATED_PCB_FEATURE,
            "mpn": "", "lcsc": ""}


def record():
    part = declaration()
    return {"lib_id": part["lib_id"], "footprint": part["footprint"],
            "in_bom": False, "on_board": True, "dnp": False,
            "value": "ETCHED CONTACT", "props": {}}


@pytest.mark.parametrize("ref", ["J987", "U803", "RS19", "UNRELATED"])
def test_exact_typed_declaration_is_independent_of_board_and_reference(ref):
    rec, asset = record(), declaration()
    before = copy.deepcopy((rec, asset))
    assert semantics.is_fabricated_pcb_feature(rec, [asset])
    findings = audit.check_bom("unrelated-board", {ref: rec},
                               fabricated_features=[asset])
    assert not any(f["code"] in {"MISSING_BOM_FIELD", "GENERIC_CONNECTOR_SELECTION"}
                   for f in findings)
    assert (rec, asset) == before


@pytest.mark.parametrize("field,value", [
    ("lib_id", "fixture:UnselectedIC"), ("footprint", "fixture:Other"),
    ("in_bom", True), ("in_bom", None), ("dnp", True),
    ("on_board", False), ("footprint", ""),
])
def test_changed_or_incomplete_source_does_not_inherit_exemption(field, value):
    rec = record()
    rec[field] = value
    assert not semantics.is_fabricated_pcb_feature(rec, [declaration()])


@pytest.mark.parametrize("field,value", [
    ("procurement_kind", "purchased"), ("procurement_kind", None),
    ("in_bom", True), ("mpn", "ORDERABLE-123"), ("lcsc", "C123"),
])
def test_declaration_cannot_be_a_purchased_or_untyped_asset(field, value):
    asset = declaration()
    asset[field] = value
    assert not semantics.is_fabricated_pcb_feature(record(), [asset])


@pytest.mark.parametrize("field", ["MPN", "LCSC"])
def test_purchase_identity_on_instance_requires_reclassification(field):
    rec = record()
    rec["props"][field] = "conflicting-identity"
    assert not semantics.is_fabricated_pcb_feature(rec, [declaration()])


def test_excluded_ic_or_connector_and_instance_prose_are_not_an_exemption():
    rec = record()
    rec["lib_id"] = "arbitrary:UnselectedIC"
    rec["props"]["Description"] = "NOT a stocked/purchased part"
    findings = audit.check_bom("board", {"U17": rec, "J83": rec},
                               fabricated_features=[declaration()])
    assert {f["ref"] for f in findings if f["severity"] == "BLOCKER"
            and f["code"] == "MISSING_BOM_FIELD"} == {"U17", "J83"}


@pytest.mark.parametrize("board", ["output-daughterboards/atx24-out-db",
    "output-daughterboards/eps-out-db", "output-daughterboards/pcie-out-db"])
def test_current_daughters_use_declared_fabricated_features_and_keep_real_bom(board):
    entry = cec_beta_manifest.BY_BOARD[board]
    root = (cec_xfcn_contract.ROOT / "beta" / entry["directory"] / entry["schematic"])
    inv = cec_sch_gates.inventory(str(root))
    features = {ref for ref, rec in inv.items()
                if semantics.is_fabricated_pcb_feature(
                    rec, (*cec_xfcn_contract.PARTS.values(),
                          *semantics.BARE_SOLDER_FIELDS))}
    assert features
    findings = audit.check_bom(board, inv)
    assert not any(f["ref"] in features and f["code"] == "MISSING_BOM_FIELD"
                   for f in findings)
    assert not any(f["severity"] == "BLOCKER" for f in findings)
    # A missing identity on a real connector is still a hard selection error.
    altered = copy.deepcopy(inv)
    probe = record()
    probe["lib_id"], probe["footprint"] = "fixture:PhysicalConnector", "fixture:Part"
    altered["J_UNSELECTED"] = probe
    assert any(f["ref"] == "J_UNSELECTED" and f["severity"] == "BLOCKER"
               for f in audit.check_bom(board, altered))


def test_audit_implementation_identity_covers_semantics_and_asset_registry():
    _, files = audit._implementation_digest()
    assert {"scripts/cec_part_semantics.py", "scripts/cec_xfcn_contract.py"} <= set(files)
