"""A fixed symptom cannot pay for a new symptom elsewhere on a board."""

import copy
import math

import pytest

from cec_pipeline.craft import compare, inventory


def report(*issues, headings=(), power=()):
    return dict(complete=True, track_uuid_scope=None, issues=list(issues),
                issue_count=len(issues), non_octilinear=list(headings),
                non_octilinear_count=len(headings),
                power_contours=dict(complete=True, findings=list(power), finding_count=len(power)))


def acute(*, at=(2, 3), angle=45, uid="source", net="CONTROL", layer="B.Cu"):
    return dict(type="acute_backtrack", net=net, layer=layer, at_mm=list(at),
                opening_angle_deg=angle, track_uuids=[uid], severity="advisory",
                neighbors_mm=[[1, 2], [4, 5]], widths_mm=[0.2])


def test_equal_count_substitution_is_a_regression():
    before, after = inventory(report(acute())), inventory(report(acute(at=(4, 3))))
    delta = compare(before, after)
    assert delta["complete"] and not delta["ok"]
    assert len(delta["new_or_worsened"]) == 1
    assert delta["source_finding_count"] == delta["candidate_finding_count"] == 1


def test_more_total_improvement_cannot_hide_a_new_type_net_or_face():
    for changed in (dict(type="covered_backtrack"), dict(net="OTHER"), dict(layer="F.Cu")):
        new = dict(acute(), **changed)
        delta = compare(inventory(report(acute(), acute(at=(8, 9)))), inventory(report(new)))
        assert not delta["ok"]


def test_uuid_prose_and_incident_order_are_not_physical_identity():
    a, b = acute(), acute(uid="reconstructed")
    b["message"] = "New explanatory prose"
    b["neighbors_mm"].reverse()
    assert compare(inventory(report(a)), inventory(report(b)))["ok"]


def test_worsened_angle_fails_but_same_locus_improvement_is_allowed():
    source = inventory(report(acute(angle=45)))
    assert not compare(source, inventory(report(acute(angle=25))))["ok"]
    assert compare(source, inventory(report(acute(angle=65))))["ok"]


def test_multiplicity_is_preserved():
    assert not compare(inventory(report(acute())), inventory(report(acute(), acute())))["ok"]


def test_explicit_target_must_disappear_not_merely_improve():
    raw = report(acute())
    source = inventory(raw)
    target = raw["issues"][0]["semantic_id"]
    assert compare(source, inventory(report()), target_ids=[target])["ok"]
    remaining = compare(source, inventory(report(acute(angle=65))), target_ids=[target])
    assert remaining["complete"] and not remaining["ok"]
    assert remaining["uncleared_targets"] == [target]
    assert not compare(source, source, target_ids=["b" * 64])["complete"]


def test_unknown_unlocated_incomplete_and_inconsistent_observations_refuse():
    for mutate in (
        lambda r: r.update(complete=False),
        lambda r: r.update(track_uuid_scope=["one"]),
        lambda r: r.update(issue_count=2),
        lambda r: r["power_contours"].update(complete=False),
        lambda r: r["issues"][0].update(type="future_unreviewed_diagnostic"),
        lambda r: r["issues"][0].pop("at_mm"),
        lambda r: r["issues"][0].pop("opening_angle_deg"),
        lambda r: r["issues"][0].update(opening_angle_deg=math.nan),
        lambda r: r["issues"][0].update(opening_angle_deg=True),
    ):
        value = report(acute())
        mutate(value)
        with pytest.raises(ValueError):
            inventory(value)


def test_semantic_receipt_cannot_forge_identity_or_nonfinite_metric():
    source = inventory(report(acute()))
    for mutate in (
        lambda r: r.update(schema=True),
        lambda r: r["findings"][0].update(id="0" * 64),
        lambda r: r["findings"][0].update(residual_sha256="not a hash"),
        lambda r: r["findings"][0]["metrics"].update(blocking=math.inf),
    ):
        candidate = copy.deepcopy(source)
        mutate(candidate)
        assert not compare(source, candidate)["complete"]


def test_heading_reconstruction_does_not_depend_on_endpoint_direction():
    row = dict(type="non_octilinear_segment", net="CONTROL", layer="F.Cu",
               start_mm=[1, 1], end_mm=[3, 3.01], heading_error_nm=10000,
               severity="advisory", uuid="old")
    reverse = dict(row, uuid="new", start_mm=row["end_mm"], end_mm=row["start_mm"])
    assert compare(inventory(report(headings=[row])), inventory(report(headings=[reverse])))["ok"]


def test_power_shape_changes_cannot_hide_behind_same_type_and_count():
    row = dict(type="wide_round_elbow", net="SUPPLY", layer="F.Cu", at_mm=[1, 2],
               width_mm=2, narrow_width_mm=2, severity="review")
    assert not compare(inventory(report(power=[row])),
                       inventory(report(power=[dict(row, width_mm=3)])))["ok"]
