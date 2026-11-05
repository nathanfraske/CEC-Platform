"""Concave native power envelopes keep placement space and rated copper."""
import copy

import pcbnew
import pytest
from shapely.geometry import Point, Polygon

import cec_power_contours as contours
import cec_rectilinear_copper as owner
from cec_local_copper_cell import copper_inventory
from test_rectilinear_copper import fixture


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("layer", [pcbnew.F_Cu, pcbnew.B_Cu])
def test_equal_width_elbow_is_detected_without_refdes_net_or_side_special_case(angle, mirror, layer):
    b, tracks = fixture(angle=angle, mirror=mirror, layer=layer)
    before = copper_inventory(b)
    report = contours.audit_board(b)
    assert report["complete"] and report["types"] == {"wide_round_elbow": 1}
    assert report["findings"][0]["track_uuids"] == sorted(t.m_Uuid.AsString() for t in tracks)
    assert not report["replacement_authorized"] and copper_inventory(b) == before
    assert contours.audit_board(b, track_uuid_scope=[]) ["finding_count"] == 0


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("layer", [pcbnew.F_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize("style", ["square", "chamfer45"])
def test_saved_concave_fill_preserves_capsules_without_a_convex_hull_across_empty_space(
        tmp_path, angle, mirror, layer, style):
    b, tracks = fixture(angle=angle, mirror=mirror, layer=layer)
    rows = [owner._track_row(t) for t in tracks]
    plan = owner.plan(b, [r["uuid"] for r in rows], clearance_nm=200000,
        min_thickness_nm=100000, required_width_nm=1500000, contour_style=style,
        contour_grid_nm=1000, fill_envelope_margin_nm=4, retire_source_tracks=False)
    profile = Polygon(plan["polygon_nm"])
    domain = Polygon(plan["actual_fill_envelope_nm"])
    assert not profile.equals(profile.convex_hull)
    assert not domain.equals(domain.convex_hull)
    # A real point in the empty concavity stays available to placement.
    empty = profile.convex_hull.difference(profile).representative_point()
    assert not domain.covers(empty)
    emitted = owner.materialize(b, plan); b.BuildConnectivity()
    assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path = tmp_path / "native-concave.kicad_pcb"; pcbnew.SaveBoard(str(path), b)
    saved = pcbnew.LoadBoard(str(path))
    received = owner.receive(saved, plan, emitted["zone_uuid"])
    assert received["complete"] and received["ok"], received
    assert [owner._track_row(next(t for t in saved.GetTracks() if t.m_Uuid.AsString() == r["uuid"]))
            for r in rows] == rows
    audit = contours.audit_board(saved)
    assert audit["complete"] and audit["finding_count"] == 0
    assert len(audit["purposeful_native_covers"]) == 2
    assert not received["new_capacity_credited"] and not received["release_authority"]


@pytest.mark.parametrize("fault", ["rehashed_domain", "one_nm_loss", "undeclared_spill"])
def test_concave_domain_does_not_waive_rehashed_spill_or_any_native_copper_loss(fault):
    b, tracks = fixture()
    plan = owner.plan(b, [t.m_Uuid.AsString() for t in tracks], clearance_nm=200000,
        min_thickness_nm=100000, required_width_nm=1500000, contour_style="chamfer45",
        fill_envelope_margin_nm=4, retire_source_tracks=False)
    if fault == "rehashed_domain":
        changed = copy.deepcopy(plan); changed["actual_fill_envelope_nm"][0][0] -= 1
        changed.pop("plan_sha256"); changed["plan_sha256"] = owner._digest(changed)
        before = copper_inventory(b)
        with pytest.raises(owner.Refused, match="derived"):
            owner.materialize(b, changed)
        assert copper_inventory(b) == before
        return
    emitted = owner.materialize(b, plan)
    z = next(z for z in b.Zones() if z.m_Uuid.AsString() == emitted["zone_uuid"])
    fill = owner._poly(plan["actual_fill_envelope_nm"])
    if fault == "one_nm_loss":
        at = plan["source_tracks"][0]["start_nm"]
        fill.BooleanSubtract(owner._poly([(at[0], at[1]), (at[0]+1, at[1]),
            (at[0]+1, at[1]+1), (at[0], at[1]+1)]))
    else:
        fill.BooleanAdd(owner._poly([(29000000, 29000000), (29001000, 29000000),
            (29001000, 29001000), (29000000, 29001000)]))
    z.SetFilledPolysList(pcbnew.F_Cu, fill); z.SetIsFilled(True)
    result = owner.receive(b, plan, emitted["zone_uuid"])
    assert not result["ok"]
    if fault == "one_nm_loss":
        assert result["complete"] and result["missing_source_tracks"]


def test_foreign_component_in_empty_corner_is_not_enclosed_by_hull_or_filler():
    b, tracks = fixture()
    net = pcbnew.NETINFO_ITEM(b, "/RENAMED_FOREIGN"); b.Add(net)
    fp = pcbnew.FOOTPRINT(b); b.Add(fp); pad = pcbnew.PAD(fp); fp.Add(pad)
    pad.SetNet(net); pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetSize(pcbnew.VECTOR2I_MM(1, 1)); pad.SetPosition(pcbnew.VECTOR2I_MM(33, 35))
    layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); pad.SetLayerSet(layers)
    ids = [t.m_Uuid.AsString() for t in tracks]
    plan = owner.plan(b, ids, clearance_nm=200000, min_thickness_nm=100000,
        required_width_nm=1500000, contour_style="chamfer45", fill_envelope_margin_nm=4)
    assert not Polygon(plan["actual_fill_envelope_nm"]).covers(Point(33000000, 35000000))
    pad.SetPosition(pcbnew.VECTOR2I_MM(38, 30))
    with pytest.raises(owner.Refused, match="foreign_native"):
        owner.plan(b, ids, clearance_nm=200000, min_thickness_nm=100000,
            required_width_nm=1500000, contour_style="chamfer45", fill_envelope_margin_nm=4)


def test_collinear_wide_segments_are_not_misreported_as_an_elbow():
    b, tracks = fixture(); tracks[1].SetEnd(pcbnew.VECTOR2I_MM(46, 30))
    assert contours.audit_board(b)["finding_count"] == 0


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("layer", [pcbnew.F_Cu, pcbnew.B_Cu])
def test_repair_request_owns_the_complete_native_contact_run_not_one_bulb(angle, mirror, layer):
    b, tracks = fixture(angle=angle, mirror=mirror, layer=layer, locked=True, grouped=True)
    before = copper_inventory(b)
    report = contours.component_requests(b, layer_ids=[int(layer)])
    assert report["complete"] and len(report["requests"]) == 1
    request = report["requests"][0]
    assert request["finding_types"] == ["wide_round_elbow"]
    assert request["locked_track_uuids"] == sorted(t.m_Uuid.AsString() for t in tracks)
    assert {r["uuid"] for r in request["source_tracks"]} == {t.m_Uuid.AsString() for t in tracks}
    assert request["requires_existing_dimensional_authority"]
    assert not report["replacement_authorized"] and not report["source_mutated"]
    assert copper_inventory(b) == before


@pytest.mark.parametrize("fault", ["deadline", "track_bound", "component_bound"])
def test_incomplete_component_scan_does_not_return_a_clean_or_partial_portfolio(fault):
    b, tracks = fixture(); before = copper_inventory(b)
    report = contours.component_requests(b, **{
        "deadline": {"timeout_s": 0}, "track_bound": {"max_tracks": 1},
        "component_bound": {"max_component_tracks": 1}}[fault])
    assert not report["complete"] and not report["requests"]
    assert copper_inventory(b) == before


def test_layer_and_net_scopes_are_selection_not_cross_layer_contact_or_ownership_authority():
    b, tracks = fixture()
    report = contours.component_requests(b, layer_ids=[int(pcbnew.B_Cu)])
    assert report["complete"] and not report["requests"]
    report = contours.component_requests(b, net_scope=["/A_DIFFERENT_DESIGN"])
    assert report["complete"] and not report["requests"]
    with pytest.raises(ValueError): contours.component_requests(b, layer_ids=[True])
    with pytest.raises(ValueError): contours.component_requests(b, net_scope=[None])


def test_rated_resident_portfolio_does_not_widen_a_neighboring_narrow_launch_or_invent_a_floor():
    b, tracks = fixture()
    narrow = pcbnew.PCB_TRACK(b); narrow.SetNet(tracks[0].GetNet())
    narrow.SetLayer(pcbnew.F_Cu); narrow.SetWidth(1000000)
    narrow.SetStart(tracks[1].GetEnd()); narrow.SetEnd(pcbnew.VECTOR2I_MM(45, 38)); b.Add(narrow)
    before = copper_inventory(b)
    floors = {(tracks[0].GetNetname(), int(pcbnew.F_Cu)): 1500000}
    report = contours.component_requests(b, layer_ids=[int(pcbnew.F_Cu)], resident_width_floors_nm=floors)
    assert report["complete"] and len(report["requests"]) == 1
    assert report["excluded_nonresident_track_uuids"] == [narrow.m_Uuid.AsString()]
    assert {r["uuid"] for r in report["requests"][0]["source_tracks"]} == {t.m_Uuid.AsString() for t in tracks}
    assert copper_inventory(b) == before
    empty = contours.component_requests(b, resident_width_floors_nm={})
    assert empty["complete"] and not empty["requests"]
    with pytest.raises(ValueError): contours.component_requests(b, resident_width_floors_nm={
        (tracks[0].GetNetname(), True): 1500000})
