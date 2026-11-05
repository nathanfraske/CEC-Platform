"""Assembly nonregression receives native fault identities, not categories."""

from copy import deepcopy
import math

import pytest

from cec_pipeline.safety import assembly_pair


def evidence(*violations):
    """Synthetic native-schema observations; not physical qualification."""
    return dict(
        schema=1, applicable=True, authority_unchanged=True,
        ok=not violations, violations=list(violations), missing=[], contacts=[],
        hardware=[], vent_reservations=[],
        vertical=dict(complete=True, missing=[], ok=True,
                      vent=dict(ok=True, worst_margin_mm=1.),
                      engagement=dict(ok=True, under_insertion_margin_mm=1.,
                                      over_insertion_margin_mm=1.)),
    )


def collision(refs=("U1", "U2"), margin=-1.):
    return dict(kind="opposing_bodies", refs=list(refs), margin_mm=margin, ok=False)


def receive(monkeypatch, before, after):
    import cec_assembly_envelope as assembly

    monkeypatch.setattr(assembly, "declared_policy", lambda *args: {"same": "contract"})
    observations = iter((before, after))
    monkeypatch.setattr(assembly, "candidate_check", lambda *args: next(observations))
    return assembly_pair("source", "candidate")


@pytest.mark.parametrize("margin,passed", [(-1., True), (-.5, True), (-2., False)])
def test_same_native_collision_compares_signed_severity(monkeypatch, margin, passed):
    result = receive(monkeypatch, evidence(collision()), evidence(collision(margin=margin)))
    assert result["complete"] and result["ok"] is passed
    assert bool(result["worsened_faults"]) is (not passed)
    assert not result["assembly_qualified"]
    assert not result["inherited_faults_qualified"] and not result["release_authority"]


def test_same_count_replacement_is_new_native_fault(monkeypatch):
    result = receive(monkeypatch, evidence(collision()), evidence(collision(("J1", "U3"))))
    assert result["complete"] and not result["ok"]
    assert result["new_faults"] == [("clearance", "opposing_bodies", "J1", "U3")]


def test_extra_fault_in_existing_category_cannot_hide(monkeypatch):
    result = receive(monkeypatch, evidence(collision()),
                     evidence(collision(), collision(("J1", "U3"))))
    assert result["complete"] and not result["ok"] and result["new_faults"]


def test_repaired_debt_and_clean_source(monkeypatch):
    result = receive(monkeypatch, evidence(collision()), evidence())
    assert result["complete"] and result["ok"] and result["assembly_qualified"]
    result = receive(monkeypatch, evidence(), evidence(collision()))
    assert result["complete"] and not result["ok"]


def test_missing_envelopes_have_native_identity(monkeypatch):
    before = evidence()
    before.update(ok=False, missing=[dict(side="carrier", ref="U1", footprint="DIP")])
    assert receive(monkeypatch, before, deepcopy(before))["ok"]
    after = deepcopy(before)
    after["missing"][0]["ref"] = "U2"
    assert not receive(monkeypatch, before, after)["ok"]


@pytest.mark.parametrize("damage", [
    lambda row: row.pop("vertical"),
    lambda row: row.pop("contacts"),
    lambda row: row.update(ok=False),  # Opaque FAIL has no typed fault atoms.
    lambda row: row.update(ok=None),
    lambda row: row.update(ok=1),
    lambda row: row.update(complete=False),
    lambda row: row.update(timed_out=True),
    lambda row: row.update(authority_unchanged=False),
    lambda row: row.update(applicable=False),
    lambda row: row["vertical"].update(complete=False, missing=["gap"]),
    lambda row: row["vertical"]["vent"].update(ok=False),
    lambda row: row.update(unused_coordinate=math.nan),
])
def test_unknown_malformed_or_contradictory_evidence_refuses(monkeypatch, damage):
    after = evidence()
    damage(after)
    result = receive(monkeypatch, evidence(), after)
    assert not result["ok"] and not result["complete"] and result["errors"]
    assert not result["assembly_qualified"]
    # An equally opaque source does not turn absence of evidence into debt.
    assert not receive(monkeypatch, deepcopy(after), after)["ok"]


@pytest.mark.parametrize("damage", [
    lambda row: row["violations"][0].pop("refs"),
    lambda row: row["violations"][0].update(refs=["U1"]),
    lambda row: row["violations"][0].update(kind="opaque"),
    lambda row: row["violations"][0].update(margin_mm=math.inf),
    lambda row: row["violations"][0].update(margin_mm=math.nan),
    lambda row: row["violations"][0].update(margin_mm=0.),
    lambda row: row["violations"].append(deepcopy(row["violations"][0])),
    lambda row: row.update(ok=True),
])
def test_collision_evidence_must_be_complete_and_consistent(monkeypatch, damage):
    after = evidence(collision())
    damage(after)
    result = receive(monkeypatch, evidence(collision()), after)
    assert not result["ok"] and not result["complete"]


def test_hardware_and_vent_faults_do_not_collapse_to_categories(monkeypatch):
    before = evidence()
    before.update(ok=False, hardware=[dict(anchor_pair=["H1", "H2"],
                  conflicts=[["carrier", "U1"]], ok=False)],
                  vent_reservations=[dict(receiver="cover", ref="C1", native_rule_covers=False,
                                         copper_hits=["track_or_via:a"], ok=False)])
    assert receive(monkeypatch, before, deepcopy(before))["ok"]
    after = deepcopy(before)
    after["hardware"][0]["conflicts"] = [["carrier", "U2"]]
    assert not receive(monkeypatch, before, after)["ok"]
    after = deepcopy(before)
    after["vent_reservations"][0]["copper_hits"] = ["track_or_via:b"]
    assert not receive(monkeypatch, before, after)["ok"]


def test_vertical_margins_retain_independent_identity_and_severity(monkeypatch):
    before = evidence()
    before.update(ok=False)
    before["vertical"].update(ok=False)
    before["vertical"]["vent"].update(ok=False, worst_margin_mm=-1.)
    assert receive(monkeypatch, before, deepcopy(before))["ok"]
    after = deepcopy(before)
    after["vertical"]["vent"]["worst_margin_mm"] = -2.
    assert receive(monkeypatch, before, after)["worsened_faults"]
    after = deepcopy(before)
    after["vertical"]["vent"]["worst_margin_mm"] = -.5
    assert receive(monkeypatch, before, after)["ok"]


def test_mating_contacts_retain_numbered_pin_and_offset(monkeypatch):
    before = evidence()
    before.update(ok=False, contacts=[dict(ok=False, mismatched=1, max_offset_mm=.1,
                  contacts=[dict(id="1", distance_mm=.1, role_ok=True, ok=False)])])
    assert receive(monkeypatch, before, deepcopy(before))["ok"]
    after = deepcopy(before)
    after["contacts"][0]["contacts"][0]["id"] = "2"
    assert receive(monkeypatch, before, after)["new_faults"]
    after = deepcopy(before)
    after["contacts"][0]["contacts"][0]["distance_mm"] = .2
    after["contacts"][0]["max_offset_mm"] = .2
    assert receive(monkeypatch, before, after)["worsened_faults"]


def test_no_declared_contract_stays_explicitly_unqualified(monkeypatch):
    import cec_assembly_envelope as assembly

    monkeypatch.setattr(assembly, "declared_policy", lambda *args: None)
    monkeypatch.setattr(assembly, "candidate_check", lambda *args: pytest.fail("no contract"))
    result = assembly_pair("source", "candidate")
    assert result["ok"] and result["complete"]
    assert result["scope"] == "no_declared_cross_board_assembly_contract"
    assert not result["assembly_qualified"] and not result["release_authority"]
