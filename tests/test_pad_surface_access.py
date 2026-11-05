"""Native geometry-only terminal contacts, including nontrivial pad shapes."""
import json
import math
from unittest import mock

import pytest
pcbnew = pytest.importorskip("pcbnew")

import cec_pad_surface_access as access


def fixture(*, turn=0, renamed=False, back=False, pth=False, slot=False, custom=False):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    net = pcbnew.NETINFO_ITEM(board, "/renamed/arbitrary" if renamed else "/POWER")
    board.Add(net)
    footprint = pcbnew.FOOTPRINT(board)
    footprint.SetReference("UNRELATED_NAME_42" if renamed else "J_SOURCE")
    board.Add(footprint)
    pad = pcbnew.PAD(footprint)
    footprint.Add(pad)
    pad.SetNumber("arbitrary_pin" if renamed else "1")
    pad.SetNet(net)
    pad.SetPosition(pcbnew.VECTOR2I_MM(20, 30))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH if pth else pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(4, 6))
    layers = pcbnew.LSET()
    for layer in board.GetEnabledLayers().CuStack() if pth else [pcbnew.B_Cu if back else pcbnew.F_Cu]:
        layers.AddLayer(layer)
    pad.SetLayerSet(layers)
    if pth:
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(1, 3 if slot else 1))
        if slot:
            pad.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG)
    if custom:
        # A concave L-shaped copper land with its origin in a small anchor.
        pad.SetSize(pcbnew.VECTOR2I_MM(.2, .2))
        pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
        pad.SetAnchorPadShape(pcbnew.F_Cu, pcbnew.PAD_SHAPE_RECT)
        points = pcbnew.VECTOR_VECTOR2I()
        for x, y in [(-2,-2),(2,-2),(2,-1),(-1,-1),(-1,2),(-2,2)]:
            points.append(pcbnew.VECTOR2I_MM(x,y))
        pad.AddPrimitivePoly(pcbnew.F_Cu, points, 0, True)
    pad.SetOrientationDegrees(turn)
    return board, pad


@pytest.mark.parametrize("turn,renamed", [(0,False),(90,True),(37,True)])
def test_rotated_renamed_native_samples_replay_and_do_not_grant_current(turn, renamed):
    board, pad = fixture(turn=turn, renamed=renamed)
    before = (pad.GetPosition(),pad.GetSize(),pad.GetOrientationDegrees(),pad.m_Uuid.AsString())
    result = access.sample(pad, pcbnew.F_Cu)
    assert result["ok"] and result["complete"] and result["points"]
    assert result["checked"] <= 17*17+1
    assert result["points"][0] == [20_000_000,30_000_000]
    assert all(access.contact(pad,pcbnew.F_Cu,point,50_000)["ok"] for point in result["points"])
    assert result["geometry_only"] and not result["electrical_capacity_qualified"]
    assert not result["release_authority"] and not result["no_path_proof"]
    assert result["native_error_location"] == "ERROR_INSIDE"
    assert json.loads(json.dumps(result)) == result
    assert before == (pad.GetPosition(),pad.GetSize(),pad.GetOrientationDegrees(),pad.m_Uuid.AsString())


def test_custom_concavity_is_not_replaced_by_a_bounding_rectangle():
    board,pad = fixture(custom=True)
    result = access.sample(pad,pcbnew.F_Cu)
    assert result["ok"]
    assert access.contact(pad,pcbnew.F_Cu,[18_500_000,31_000_000])["ok"]
    assert not access.contact(pad,pcbnew.F_Cu,[21_000_000,31_000_000])["ok"]
    assert all(access.contact(pad,pcbnew.F_Cu,point)["ok"] for point in result["points"])
    assert not any(x>20_200_000 and y>30_200_000 for x,y in result["points"])


@pytest.mark.parametrize("slot,turn", [(False,0),(True,0),(True,90)])
def test_plated_native_hole_and_rotated_slot_are_excluded(slot, turn):
    board,pad=fixture(pth=True,slot=slot,turn=turn)
    for layer in (pcbnew.F_Cu,pcbnew.B_Cu):
        result=access.sample(pad,layer)
        assert result["ok"]
        assert not access.contact(pad,layer,[20_000_000,30_000_000])["ok"]
        hole=pad.GetEffectiveHoleShape()
        assert all(not hole.Collide(pcbnew.SHAPE_CIRCLE(pcbnew.VECTOR2I(*point),50_000),0)
                   for point in result["points"])
        assert all(access.contact(pad,layer,point)["ok"] for point in result["points"])


def test_actual_back_layer_and_disabled_copper_refuse_without_guessing():
    board,pad=fixture(back=True)
    assert access.sample(pad,pcbnew.B_Cu)["ok"]
    front=access.sample(pad,pcbnew.F_Cu)
    assert not front["points"] and front["reason"] == "pad_not_on_layer"
    disabled=access.sample(pad,pcbnew.In6_Cu)
    assert not disabled["points"] and disabled["reason"] == "layer_not_enabled_copper"


def test_npth_and_nonflashed_pads_cannot_supply_contact():
    board,pad=fixture(pth=True)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    result=access.sample(pad,pcbnew.F_Cu)
    assert not result["points"] and result["reason"] == "npth_pad_has_no_conductive_access"
    board,pad=fixture(pth=True)
    with mock.patch.object(pad,"FlashLayer",return_value=False):
        result=access.sample(pad,pcbnew.F_Cu)
    assert not result["points"] and result["reason"] == "pad_not_flashed_on_layer"


def test_native_unconnected_layer_removal_refuses_a_present_but_unflashed_pad():
    board,pad=fixture(pth=True)
    pad.SetRemoveUnconnected(True)
    board.BuildConnectivity()
    assert pad.IsOnLayer(pcbnew.In1_Cu) and not pad.FlashLayer(pcbnew.In1_Cu)
    result=access.sample(pad,pcbnew.In1_Cu)
    assert not result["points"] and result["reason"] == "pad_not_flashed_on_layer"


@pytest.mark.parametrize("point", [[22_000_000,30_000_000],[21_975_000,30_000_000],
                                  [21_950_000,30_000_000]])
def test_tangent_or_too_shallow_contact_is_not_an_interior_patch(point):
    board,pad=fixture()
    result=access.contact(pad,pcbnew.F_Cu,point)
    assert not result["ok"] and result["reason"] == "interior_contact_disk_not_contained"


def test_hole_tangent_disk_cannot_be_reported_as_annular_copper():
    board,pad=fixture(pth=True)
    result=access.contact(pad,pcbnew.F_Cu,[20_550_000,30_000_000])
    assert not result["ok"] and result["reason"] == "contact_disk_intersects_native_hole"


def test_sampler_requests_native_error_inside_explicitly():
    board,pad=fixture()
    with mock.patch.object(pad,"GetEffectivePolygon",wraps=pad.GetEffectivePolygon) as polygon:
        assert access.sample(pad,pcbnew.F_Cu)["ok"]
    polygon.assert_called_once_with(pcbnew.F_Cu,pcbnew.ERROR_INSIDE)


def test_native_polygon_failure_does_not_fall_back_to_pad_size_or_box():
    board,pad=fixture()
    with mock.patch.object(pad,"GetEffectivePolygon",side_effect=RuntimeError("unavailable")):
        result=access.sample(pad,pcbnew.F_Cu)
        proof=access.contact(pad,pcbnew.F_Cu,[20_000_000,30_000_000])
    assert not result["points"] and result["stop"] == "unsupported"
    assert not proof["ok"] and "native_geometry_unavailable" in proof["reason"]


def test_empty_native_polygon_and_hole_failure_refuse():
    board,pad=fixture()
    with mock.patch.object(pad,"GetEffectivePolygon",return_value=pcbnew.SHAPE_POLY_SET()):
        assert not access.sample(pad,pcbnew.F_Cu)["points"]
    board,pad=fixture(pth=True)
    with mock.patch.object(pad,"GetEffectiveHoleShape",return_value=None):
        result=access.sample(pad,pcbnew.F_Cu)
    assert not result["points"] and result["reason"] == "native_hole_geometry_unavailable"


def test_repeatability_bound_and_independent_geometry_replay():
    board,pad=fixture()
    first=access.sample(pad,pcbnew.F_Cu,axis_samples=33)
    assert first == access.sample(pad,pcbnew.F_Cu,axis_samples=33)
    assert first["checked"] <= 33**2+1 and len({tuple(p) for p in first["points"]}) == len(first["points"])
    old=first["points"][0]
    pad.SetPosition(pcbnew.VECTOR2I_MM(50,60))
    assert not access.contact(pad,pcbnew.F_Cu,old)["ok"]


def test_deadline_stops_before_native_geometry_and_mid_menu_without_no_path_claim():
    board,pad=fixture()
    with mock.patch.object(access.time,"monotonic",return_value=10), \
            mock.patch.object(pad,"GetEffectivePolygon") as polygon:
        result=access.sample(pad,pcbnew.F_Cu,deadline=9)
    polygon.assert_not_called()
    assert result["stop"] == "deadline" and result["checked"] == 0
    with mock.patch.object(access.time,"monotonic",side_effect=[0,0,2]):
        result=access.sample(pad,pcbnew.F_Cu,deadline=1)
    assert result["stop"] == "deadline" and result["checked"] == 1 and result["points"]
    assert not result["complete"] and not result["no_path_proof"]


@pytest.mark.parametrize("kwargs", [dict(contact_inset_nm=0),dict(contact_inset_nm=500_001),
    dict(contact_inset_nm=True),dict(contact_inset_nm=50_000.),dict(axis_samples=1),
    dict(axis_samples=34),dict(axis_samples=True),dict(deadline=math.inf),
    dict(deadline=math.nan),dict(deadline=-1),dict(deadline=True)])
def test_invalid_search_parameters_fail_before_native_sampling(kwargs):
    board,pad=fixture()
    with pytest.raises(ValueError):access.sample(pad,pcbnew.F_Cu,**kwargs)


@pytest.mark.parametrize("point", [[0],[0,0,0],[math.nan,0],[0.,0],[True,0],[2**31,0]])
def test_invalid_contact_coordinates_cannot_reach_native_integer_geometry(point):
    board,pad=fixture()
    with pytest.raises(ValueError):access.contact(pad,pcbnew.F_Cu,point)


@pytest.mark.parametrize("layer", [True,-1,128,0.0])
def test_invalid_native_layer_parameters_fail_before_geometry(layer):
    board,pad=fixture()
    with pytest.raises(ValueError):access.sample(pad,layer)
    with pytest.raises(ValueError):access.contact(pad,layer,[20_000_000,30_000_000])


@pytest.mark.parametrize("options,layer", [({},pcbnew.F_Cu),
    ({"turn":37,"renamed":True},pcbnew.F_Cu),
    ({"turn":90,"pth":True,"slot":True,"renamed":True},pcbnew.B_Cu),
    ({"custom":True},pcbnew.F_Cu)])
def test_exterior_cap_menu_retains_exact_native_interior_witnesses(options, layer):
    board,pad=fixture(**options)
    before=(pad.GetPosition(),pad.GetSize(),pad.GetOrientationDegrees(),pad.m_Uuid.AsString())
    result=access.sample_caps(pad,layer,2_500_001,axis_samples=17)
    assert result["ok"] and result["complete"] and result["checked"] <= 17**2
    assert result == access.sample_caps(pad,layer,2_500_001,axis_samples=17)
    poly=pad.GetEffectivePolygon(layer,pcbnew.ERROR_INSIDE)
    for row in result["contacts"]:
        assert row["center_nm"] != row["witness_nm"]
        assert not poly.Contains(pcbnew.VECTOR2I(*row["center_nm"]))
        assert access._cap_contains(row["center_nm"],row["witness_nm"],2_500_001,50_000)
    for row in result["contacts"][::max(1,len(result["contacts"])//12)]:
        replay=access.cap_contact(pad,layer,row["center_nm"],row["witness_nm"],2_500_001)
        assert replay["ok"] and replay["cap_contains_contact_disk"]
    assert result["geometry_only"] and not result["electrical_capacity_qualified"]
    assert not result["release_authority"] and not result["no_path_proof"]
    assert json.loads(json.dumps(result)) == result
    assert before == (pad.GetPosition(),pad.GetSize(),pad.GetOrientationDegrees(),pad.m_Uuid.AsString())


def test_cap_containment_is_strict_and_rounds_odd_integer_width_down():
    board,pad=fixture()
    witness=[20_000_000,30_000_000]
    tangent=[22_450_000,30_000_000]
    assert not access.cap_contact(pad,pcbnew.F_Cu,tangent,witness,5_000_001)["ok"]
    assert access.cap_contact(pad,pcbnew.F_Cu,[tangent[0]-1,tangent[1]],witness,5_000_001)["ok"]
    # A cap tangent to the PAD edge cannot supply any finite interior disk.
    result=access.cap_contact(pad,pcbnew.F_Cu,[22_500_000,30_000_000],
        [21_949_999,30_000_000],1_000_000)
    assert not result["ok"] and result["reason"] == "round_cap_does_not_contain_contact_disk"


def test_cap_containing_a_hole_or_stale_witness_is_not_a_pad_contact():
    board,pad=fixture(pth=True,slot=True,turn=37)
    assert not access.cap_contact(pad,pcbnew.F_Cu,[23_000_000,30_000_000],
        [20_000_000,30_000_000],8_000_000)["ok"]
    sampled=access.sample_caps(pad,pcbnew.F_Cu,2_500_000,axis_samples=9)
    row=sampled["contacts"][0]
    pad.SetPosition(pcbnew.VECTOR2I_MM(60,70))
    assert not access.cap_contact(pad,pcbnew.F_Cu,row["center_nm"],row["witness_nm"],2_500_000)["ok"]


@pytest.mark.parametrize("options,layer", [({"back":True},pcbnew.F_Cu),
    ({},pcbnew.In6_Cu),({"pth":True},pcbnew.F_Cu)])
def test_cap_sampling_keeps_layer_and_nonconductive_refusals(options,layer):
    board,pad=fixture(**options)
    if options.get("pth"):pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    result=access.sample_caps(pad,layer,2_500_000)
    assert not result["contacts"] and not result["ok"]


def test_cap_sampling_native_failure_and_deadline_never_fall_back_to_box():
    board,pad=fixture()
    with mock.patch.object(pad,"GetEffectivePolygon",side_effect=RuntimeError("unavailable")):
        assert not access.sample_caps(pad,pcbnew.F_Cu,2_500_000)["contacts"]
    with mock.patch.object(access.time,"monotonic",return_value=10), \
            mock.patch.object(pad,"GetEffectivePolygon") as polygon:
        expired=access.sample_caps(pad,pcbnew.F_Cu,2_500_000,deadline=9)
    polygon.assert_not_called()
    assert expired["stop"] == "deadline" and expired["checked"] == 0
    interior=access.sample(pad,pcbnew.F_Cu)
    with mock.patch.object(access,"sample",return_value=interior), \
            mock.patch.object(access.time,"monotonic",side_effect=[0,0,0,0,2]):
        partial=access.sample_caps(pad,pcbnew.F_Cu,2_500_000,deadline=1)
    assert partial["stop"] == "deadline" and not partial["complete"]
    assert not partial["no_path_proof"]


@pytest.mark.parametrize("kwargs", [dict(width_nm=True),dict(width_nm=2_500_000.),
    dict(width_nm=100_001),dict(width_nm=100_000_001),dict(axis_samples=1),
    dict(axis_samples=66),dict(axis_samples=True),dict(contact_axis_samples=34),
    dict(contact_inset_nm=0),dict(deadline=math.nan)])
def test_invalid_cap_search_parameters_fail_before_geometry(kwargs):
    board,pad=fixture()
    args=dict(width_nm=2_500_000,**{})
    args.update(kwargs)
    with pytest.raises(ValueError):access.sample_caps(pad,pcbnew.F_Cu,**args)
