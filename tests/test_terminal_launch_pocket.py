"""A continuous lower-obstacle enclosure, never a failed sampling grid."""
import json
import math
import time
from unittest import mock

import pcbnew
import pytest

import cec_terminal_launch_pocket as pocket


def fixture(*, turn=0, renamed=False, back=False, opened=False, rounded=False):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    own = pcbnew.NETINFO_ITEM(board, "/alternate/rated" if renamed else "/POWER")
    foreign = pcbnew.NETINFO_ITEM(board, "/obstacle")
    board.Add(own); board.Add(foreign)
    layer = pcbnew.B_Cu if back else pcbnew.F_Cu
    pads = []
    # KiCad positive pad angles rotate upward in the board's down-positive Y.
    angle = -math.radians(turn)

    def transform(x, y):
        return pcbnew.VECTOR2I_MM(30+x*math.cos(angle)-y*math.sin(angle),
                                  35+x*math.sin(angle)+y*math.cos(angle))

    def add(ref, at, size, net):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(("renamed_"+str(len(pads))) if renamed else ref)
        board.Add(fp)
        pad = pcbnew.PAD(fp)
        fp.Add(pad)
        pad.SetNumber("unusual-pin" if renamed else "1")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT if rounded else pcbnew.PAD_SHAPE_RECT)
        if rounded:
            pad.SetRoundRectRadiusRatio(.2)
        pad.SetSize(pcbnew.VECTOR2I_MM(*size))
        pad.SetOrientationDegrees(turn)
        pad.SetPosition(transform(*at))
        layers = pcbnew.LSET(); layers.AddLayer(layer)
        pad.SetLayerSet(layers); pad.SetNet(net)
        pads.append(pad)
        return pad

    source = add("TERMINAL", (0, 0), (.8, .8), own)
    add("LEFT", (-4, 0), (1, 7), foreign)
    add("RIGHT", (12 if opened else 4, 0), (1, 7), foreign)
    add("TOP", (0, -4), (7, 1), foreign)
    add("BOTTOM", (0, 4), (7, 1), foreign)
    return board, source, pads, layer


def audit(board, pad, layer, **kwargs):
    return pocket.audit(board, pad, layer, width_nm=kwargs.pop("width_nm", 4_000_001),
                        clearance_nm=200_000, **kwargs)


@pytest.mark.parametrize("turn,renamed,back,rounded", [
    (0, False, False, False), (90, True, False, False),
    (37, True, True, True), (180, False, True, True),
])
def test_continuous_enclosure_is_transformed_and_renamed_not_grid_based(turn, renamed, back, rounded):
    board, pad, pads, layer = fixture(turn=turn, renamed=renamed, back=back, rounded=rounded)
    before = [p.GetPosition() for p in pads]
    result = audit(board, pad, layer)
    assert result["certified"] is True, result
    assert result["status"] == "enclosed"
    assert len(result["possible_launch_components"]) == 1
    row = result["possible_launch_components"][0]
    assert row["enclosed"] and len(row["obstacle_indices"]) == 4
    assert result["geometry_identity_verified"]
    assert result["placement_prerequisite"]["required_for_planar_exit"]
    assert result["placement_prerequisite"]["complete_domain_placement_infeasible"] is None
    assert not result["physical_no_path_proof"]
    assert not result["electrical_capacity_qualified"]
    assert result["recipe"]["samples_are_not_proof"]
    assert result["width_nm"] == 4_000_001
    assert before == [p.GetPosition() for p in pads]
    assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize("turn,back", [(0,False),(37,True),(90,True)])
def test_actual_opening_to_bounding_region_never_certifies_pocket(turn, back):
    board, pad, _pads, layer = fixture(turn=turn, back=back, opened=True)
    result = audit(board, pad, layer)
    assert result["certified"] is False, result
    assert result["status"] == "not_enclosed"
    assert result["placement_prerequisite"] is None
    assert not result["physical_no_path_proof"]


def test_grid_contact_sample_only_witness_cannot_make_an_open_region_closed():
    board, pad, _pads, layer = fixture(opened=True)
    with mock.patch("cec_pad_surface_access.sample", return_value={"points": [[30_000_000,35_000_000]]}):
        result = audit(board, pad, layer)
    assert result["certified"] is False


def test_foreign_obstacles_on_other_face_are_not_blockers():
    board, pad, pads, layer = fixture()
    back = pcbnew.LSET(); back.AddLayer(pcbnew.B_Cu)
    for other in pads[1:]:
        other.SetLayerSet(back)
    result = audit(board, pad, layer)
    assert result["certified"] is False, result
    assert result["counts"]["used_obstacles"] == 0


def test_same_net_pads_cannot_supply_foreign_enclosure():
    board, pad, pads, layer = fixture()
    for other in pads[1:]:
        other.SetNetCode(pad.GetNetCode())
    result = audit(board, pad, layer)
    assert result["certified"] is False


@pytest.mark.parametrize("case", ["pth", "hole", "offset", "custom", "zero"])
def test_unsupported_terminal_geometry_is_unknown(case):
    board, pad, _pads, layer = fixture()
    if case == "pth":
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif case == "hole":
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    elif case == "offset":
        pad.SetOffset(pcbnew.VECTOR2I_MM(.1,0))
    elif case == "custom":
        pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    else:
        pad.SetSize(pcbnew.VECTOR2I(0,0))
    result = audit(board, pad, layer)
    assert result["certified"] is None, result
    assert result["status"] == "unknown"
    assert result["placement_prerequisite"] is None


def test_nonplanar_source_cannot_inherit_planar_obstruction_claim():
    board, pad, _pads, layer = fixture()
    layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); layers.AddLayer(pcbnew.B_Cu)
    pad.SetLayerSet(layers)
    result = audit(board, pad, layer)
    assert result["certified"] is None
    assert result["reason"] == "single_enabled_planar_terminal_required"


@pytest.mark.parametrize("kwargs,reason", [
    ({"deadline":0}, "launch_pocket_deadline_exhausted"),
    ({"max_obstacles":1}, "launch_pocket_obstacle_bound"),
    ({"max_vertices":16}, "launch_pocket_vertex_bound"),
])
def test_deadline_and_inventory_bounds_cannot_certify(kwargs, reason):
    board, pad, _pads, layer = fixture()
    result = audit(board, pad, layer, **kwargs)
    assert result["certified"] is None, result
    assert result["reason"] == reason


@pytest.mark.parametrize("kwargs", [
    {"width_nm":True}, {"width_nm":100_000}, {"width_nm":100_000_001},
    {"contact_inset_nm":0}, {"deadline":float("nan")},
    {"max_obstacles":257}, {"max_vertices":65537},
])
def test_parameter_hard_bounds(kwargs):
    board, pad, _pads, layer = fixture()
    with pytest.raises(ValueError):
        audit(board, pad, layer, **kwargs)


def test_geometry_changed_between_native_envelopes_and_final_replay_is_unknown():
    board, pad, pads, layer = fixture()
    original = pocket._connected_groups
    def move_before_replay(parts, work):
        pads[1].SetPosition(pcbnew.VECTOR2I_MM(0,0))
        return original(parts, work)
    with mock.patch.object(pocket, "_connected_groups", side_effect=move_before_replay):
        result = audit(board, pad, layer)
    assert result["certified"] is None, result
    assert result["reason"] == "launch_pocket_geometry_identity_changed"


@pytest.mark.parametrize("change", ["pad_layers","enabled_stack"])
def test_planar_layer_premise_is_epoch_bound(change):
    board,pad,_pads,layer=fixture()
    original=pocket._connected_groups
    def change_before_replay(parts,work):
        if change=="pad_layers":
            layers=pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); layers.AddLayer(pcbnew.B_Cu)
            pad.SetLayerSet(layers)
        else:
            board.SetCopperLayerCount(6)
        return original(parts,work)
    with mock.patch.object(pocket,"_connected_groups",side_effect=change_before_replay):
        result=audit(board,pad,layer)
    assert result["certified"] is None, result
    assert result["reason"] == "launch_pocket_geometry_identity_changed"


def test_native_api_failure_is_unknown_not_bbox_fallback():
    board, pad, _pads, layer = fixture()
    with mock.patch.object(pocket, "_native_polygon", side_effect=RuntimeError("native gap")):
        result = audit(board, pad, layer)
    assert result["certified"] is None
    assert result["reason"] == "native_geometry_unavailable"


def test_geos_uncertainty_is_unknown():
    from shapely.errors import GEOSException
    board, pad, _pads, layer = fixture()
    with mock.patch.object(pocket, "_buffer", side_effect=GEOSException("uncertain")):
        result = audit(board, pad, layer)
    assert result["certified"] is None
    assert result["reason"] == "geos_geometry_uncertain"


def test_point_touching_free_components_are_merged_not_hidden_exits():
    from shapely.geometry import box
    work = pocket._Work(time.monotonic()+3, pocket.MAX_OBSTACLES, pocket.MAX_VERTICES)
    groups = pocket._connected_groups([box(0,0,10,10),box(10,10,20,20),box(30,30,40,40)],work)
    assert sorted(map(sorted,groups)) == [[0,1],[2]]


def test_repeatability_without_source_mutation():
    board, pad, _pads, layer = fixture(rounded=True)
    assert audit(board,pad,layer) == audit(board,pad,layer)


def test_one_enclosed_contact_component_does_not_hide_another_possible_exit():
    board, pad, _pads, layer = fixture()
    # The endpoint territory now reaches both sides of the obstacle ring.
    # Certifying just the nearest/first free component would be a false pass.
    pad.SetSize(pcbnew.VECTOR2I_MM(18,.8))
    result = audit(board,pad,layer)
    assert result["certified"] is False, result
    assert len(result["possible_launch_components"]) >= 2
    assert any(row["enclosed"] for row in result["possible_launch_components"])
    assert any(not row["enclosed"] for row in result["possible_launch_components"])


def test_same_pocket_demand_does_not_imply_complete_domain_infeasible():
    board,pad,pads,layer=fixture()
    result=audit(board,pad,layer)
    assert result["certified"] is True
    prerequisite=result["placement_prerequisite"]
    assert prerequisite["condition"] == "authoritative_rated_path_must_exit_this_launch_component"
    assert prerequisite["complete_domain_placement_infeasible"] is None
    assert prerequisite["nonplanar_or_variable_width_feasibility"] == "not_assessed"


def test_saved_board_and_original_geometry_are_immutable(tmp_path):
    board,pad,pads,layer=fixture(rounded=True,back=True)
    path=tmp_path/'original.kicad_pcb'
    pcbnew.SaveBoard(str(path),board)
    before=path.read_bytes()
    result=audit(board,pad,layer)
    assert result["certified"] is True
    assert path.read_bytes()==before


@pytest.mark.parametrize("turn", [0,17,37,90])
def test_upper_contact_offset_contains_exact_circle_support_at_every_edge(turn):
    from shapely.affinity import rotate
    from shapely.geometry import Polygon
    # An oblique convex polygon catches GEOS per-corner arc-count rounding.
    source=rotate(Polygon([(0,0),(1_030_003,101_007),(703_017,801_023),(-13_001,509_019)]),turn)
    radius=3_217_761
    upper=pocket._buffer(source,radius,upper=True)
    vertices=list(source.exterior.coords)[:-1]
    ring=list(upper.exterior.coords)
    for a,b in zip(ring,ring[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        nx,ny=dy/math.hypot(dx,dy),-dx/math.hypot(dx,dy)
        # Orient the supporting normal away from the polygon interior.
        if (upper.centroid.x-a[0])*nx+(upper.centroid.y-a[1])*ny>0:
            nx,ny=-nx,-ny
        edge_support=a[0]*nx+a[1]*ny
        exact_circle_support=max(x*nx+y*ny for x,y in vertices)+radius
        assert edge_support-exact_circle_support>=1.9
