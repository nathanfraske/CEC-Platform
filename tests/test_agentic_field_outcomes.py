"""Semantic blocker outcomes must not borrow progress from other loci."""
from copy import deepcopy

from cec_pipeline.fields import compare, inventory


def report():
    return dict(complete=True, ok=False, applicable=True,
        parallel_angle_limit_deg=15., perpendicular_crossing_min_deg=75.,
        minimum_parallel_mm=1., classified_nets={
            "SW": dict(aggressor=True, victim=False),
            "SENSE": dict(aggressor=False, victim=True)},
        track_geometry={
            "a": dict(net="SW", layer="F.Cu", start_nm=[0,0], end_nm=[5000000,0], width_nm=200000),
            "b": dict(net="SENSE", layer="F.Cu", start_nm=[0,400000], end_nm=[5000000,400000], width_nm=200000)},
        interactions=[dict(track_uuids=["a","b"], nets=["SW","SENSE"], layers=["F.Cu","F.Cu"],
            member_roles=[dict(net="SW", aggressor=True, victim=False),
                          dict(net="SENSE", aggressor=False, victim=True)],
            aggressor="SW", victim="SENSE", angle_deg=0., parallel_overlap_mm=5.,
            center_distance_mm=.4, edge_gap_mm=.2, interaction_reach_mm=1.,
            projected_copper_overlap=False, shield=dict(shielded=False, coverage_pct=0., reason="same routing layer"),
            blocking=True, reason="unshielded parallel aggressor/victim run")])


def test_semantic_identity_survives_uuid_rebuild_and_prose():
    old = report(); new = deepcopy(old)
    new["track_geometry"]["replacement"] = new["track_geometry"].pop("a")
    new["interactions"][0]["track_uuids"][0] = "replacement"
    new["interactions"][0]["shield"]["reason"] = "different advisory wording"
    assert compare(old, new)["ok"]


def test_locus_swap_is_not_progress():
    old = report(); new = deepcopy(old)
    new["track_geometry"]["b"]["start_nm"][0] += 100
    assert not compare(old, new)["ok"]


def test_directional_worsening_is_not_inherited():
    old = report(); new = deepcopy(old)
    new["interactions"][0]["parallel_overlap_mm"] = 6.
    assert not compare(old, new)["ok"]


def test_multiplicity_is_preserved():
    old = report(); new = deepcopy(old)
    new["interactions"] *= 2
    assert inventory(new)["blocking_count"] == 2
    assert not compare(old, new)["ok"]
    assert compare(new, old)["ok"]


def test_targets_must_exist_and_disappear():
    old = report(); target = inventory(old)["blockers"][0]["id"]
    assert not compare(old, old, target_ids=[target])["ok"]
    assert not compare(old, old, target_ids=["fake"])["ok"]
    new = deepcopy(old); new.update(ok=True, interactions=[])
    assert compare(old, new, target_ids=[target])["ok"]


def test_missing_malformed_nonfinite_and_policy_fail_closed():
    for change in (lambda r: r.pop("complete"), lambda r: r.pop("track_geometry"),
                   lambda r: r["interactions"][0].pop("member_roles"),
                   lambda r: r["interactions"][0].update(angle_deg=float("nan")),
                   lambda r: r.update(ok=True)):
        bad = report(); change(bad)
        assert inventory(bad)["status"] == "unknown"
        assert not compare(report(), bad)["ok"]
    bad = report(); bad["minimum_parallel_mm"] = 10.
    assert not compare(report(), bad)["ok"]
    bad = report(); bad["classified_nets"].pop("SENSE")
    assert not compare(report(), bad)["ok"]


def test_advisory_counts_not_authority():
    old = report(); new = deepcopy(old)
    new.update(blocking_count=0, interaction_count=999)
    assert compare(old, new)["ok"]


def test_semantic_annotation_complete_and_bounded_targets():
    source = report()
    data = inventory(source)
    target = data["blockers"][0]["id"]
    assert source["interactions"][0]["semantic_id"] == target
    for targets in ({target}, [target, target], ["A" * 64], [target] * 33):
        result = compare(source, report(), target_ids=targets)
        assert not result["ok"] and result["complete"]
    malformed = report(); malformed.pop("complete")
    assert not compare(source, malformed)["complete"]


def test_zero_interactions_still_require_native_geometry_evidence():
    source = report(); source.update(ok=True, interactions=[])
    assert inventory(source)["status"] == "known"
    source.pop("track_geometry")
    assert inventory(source)["status"] == "unknown"


def test_reported_policy_boundaries_are_fail_closed():
    source = report()
    source["interactions"][0]["parallel_overlap_mm"] = 1.
    assert inventory(source)["status"] == "known"
    source["interactions"][0]["parallel_overlap_mm"] = .999
    assert inventory(source)["status"] == "unknown"


def test_effective_conductor_roles_override_global_without_losing_blocker():
    source = report()
    source["classified_nets"]["SENSE"] = dict(aggressor=True, victim=True)
    source["classified_nets"]["SW"] = dict(aggressor=True, victim=True)
    row = source["interactions"][0]
    # First is both globally and effectively; second's DC backbone suppresses
    # its global victim role. Only the reverse relationship is real.
    row["member_roles"] = [dict(net="SW", aggressor=True, victim=True),
                           dict(net="SENSE", aggressor=True, victim=False)]
    row.update(aggressor="SENSE", victim="SW")
    assert inventory(source)["blocking_count"] == 1
    assert compare(source, deepcopy(source))["ok"]
    wrong = deepcopy(source)
    wrong["interactions"][0].update(aggressor="SW", victim="SENSE")
    assert inventory(wrong)["status"] == "unknown"
    for invalid in (None, [], [dict(net="SW", aggressor=True, victim=True)]):
        wrong = deepcopy(source); wrong["interactions"][0]["member_roles"] = invalid
        assert inventory(wrong)["status"] == "unknown"
