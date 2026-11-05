"""Neutral seat geometry, real native guards, and bounded transaction lifetime.

The joint-controller tests substitute the downstream ribbon search to isolate
rollback/deadline policy. They are not full-board electrical admission proofs.
"""
import math
import time
from unittest.mock import patch

import pcbnew
import pytest

import cec_pair_return_field as field
import cec_precision_route as route

_held = []


def pose(point, quarter, mirror, shift=(17.3, 25.7)):
    x, y = point
    if mirror:
        x = -x
    for _ in range(quarter):
        x, y = -y, x
    return x + shift[0], y + shift[1]


@pytest.mark.parametrize("quarter", range(4))
@pytest.mark.parametrize("mirror", (False, True))
def test_refined_domain_is_local_transform_invariant(quarter, mirror):
    points = ((0, -.25), (0, .25))
    base = field.refined_seats((0, 0), (0, .5), points, reach_mm=1.5)
    center = pose((0, 0), quarter, mirror)
    moved = tuple(pose(p, quarter, mirror) for p in points)
    vector = tuple(moved[1][i] - moved[0][i] for i in range(2))
    result = field.refined_seats(center, vector, moved, reach_mm=1.5)
    def key(p):
        return tuple(round(v * 1e6) for v in p)
    expected = {key(pose(row["at_mm"], quarter, mirror)) for row in base["sites"]}
    assert {key(row["at_mm"]) for row in result["sites"]} == expected
    assert result["sampled_only"] and result["sampled_domain_complete"]
    assert len(result["sites"]) <= 2048
    assert all(any(math.dist(row["at_mm"], p) <= 1.5+1e-9 for p in moved)
               for row in result["sites"])


@pytest.mark.parametrize("reach", (.01, 1.5, 1000))
def test_enumeration_itself_remains_bounded(reach):
    result = field.refined_seats((0, 0), (0, 0), ((0, 0),), reach_mm=reach)
    assert len(result["sites"]) <= 2048
    assert result["sampled_domain_complete"]


@pytest.mark.parametrize("kwargs", (dict(reach_mm=math.nan),dict(reach_mm=0),
    dict(reach_mm=math.inf),dict(reach_mm=1.5,pitch_mm=-1),
    dict(reach_mm=1.5,site_limit=2)))
def test_invalid_field_policy_fails_closed(kwargs):
    with pytest.raises(ValueError):
        field.refined_seats((0,0),(0,.5),((0,-.25),(0,.25)),**kwargs)


def test_simultaneous_selection_does_not_strand_partner():
    p = dict(at_mm=(0,0),hits=(0,))
    p_alt = dict(at_mm=(2,0),hits=(0,))
    n = dict(at_mm=(.3,0),hits=(1,))
    result = field.covering_seats([p,p_alt,n],2,minimum_spacing_mm=.55)
    assert result["selected"] == [p_alt,n]
    assert not result["search_inconclusive"]
    both = dict(at_mm=(1,1),hits=(0,1))
    assert field.covering_seats([p,p_alt,n,both],2,
        minimum_spacing_mm=.55)["selected"] == [both]


def test_interrupted_cover_search_is_not_an_infeasibility_proof():
    rows = [dict(at_mm=(0,0),hits=(0,)),dict(at_mm=(.1,0),hits=(0,)),
            dict(at_mm=(.2,0),hits=(1,))]
    result = field.covering_seats(rows,2,minimum_spacing_mm=1,pair_limit=1)
    assert result["search_inconclusive"] and not result["selected"]


def board_fixture():
    board = pcbnew.CreateEmptyBoard(); _held.append(board)
    board.SetCopperLayerCount(6)
    for name in ("GND","OTHER","SIGNAL_P","SIGNAL_N"):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    for a,b in (((0,0),(20,0)),((20,0),(20,20)),((20,20),(0,20)),((0,20),(0,0))):
        edge = pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    return board


def native_pocket(board, quarter, mirror):
    # Native foreign lands leave a 10 um centre-coordinate aperture. The
    # finite radial proposals miss it; the pair-local fine proposals reach it.
    walls = ((0,0,8.395,20),(9.405,0,20,20),
             (8.395,0,9.405,8.85),(8.395,10.15,9.405,20))
    for index,(x0,y0,x1,y1) in enumerate(walls):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference("RENAMED_WALL_"+str(index));board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber("arbitrary");pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(x1-x0,y1-y0));pad.SetNet(board.FindNet("OTHER"))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*pose(((x0+x1)/2,(y0+y1)/2),quarter,mirror,shift=(0,0))))
        pad.SetOrientationDegrees(90*quarter);fp.Add(pad)
    # Rotate/mirror the outline as well as the native obstacle field.
    for shape in board.GetDrawings():
        a,b=shape.GetStart(),shape.GetEnd()
        shape.SetStart(pcbnew.VECTOR2I_MM(*pose((a.x/1e6,a.y/1e6),quarter,mirror,shift=(0,0))))
        shape.SetEnd(pcbnew.VECTOR2I_MM(*pose((b.x/1e6,b.y/1e6),quarter,mirror,shift=(0,0))))


@pytest.mark.parametrize("quarter", range(4))
@pytest.mark.parametrize("mirror", (False,True))
def test_loaded_native_pocket_uses_same_clearance_and_reference_guard(tmp_path,quarter,mirror):
    board=board_fixture();native_pocket(board,quarter,mirror)
    # Retain GND through save, remote from the sampled return field.
    fp=pcbnew.FOOTPRINT(board);fp.SetReference("GROUND_OWNER");board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber("g");pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2));pad.SetLayerSet(pcbnew.PAD.SMDMask())
    pad.SetPosition(pcbnew.VECTOR2I_MM(*pose((1,1),quarter,mirror,shift=(0,0))))
    pad.SetNet(board.FindNet("GND"));fp.Add(pad)
    source=tmp_path/"loaded.kicad_pcb";pcbnew.SaveBoard(str(source),board,True)
    original=source.read_bytes();board=pcbnew.LoadBoard(str(source));_held.append(board)
    p,n=(pose(point,quarter,mirror,shift=(0,0)) for point in ((10,9.75),(10,10.25)))
    center=pose((10,10),quarter,mirror,shift=(0,0))
    vector=(n[0]-p[0],n[1]-p[1])
    old,reason=route._add_pair_transition_returns(board,center,vector,signal_points=(p,n))
    assert not old and reason not in ("covered","added")
    diagnostics={}
    added,reason=route._add_pair_transition_returns(board,center,vector,
        signal_points=(p,n),refine=True,reference_contact=lambda *a:True,diagnostics=diagnostics)
    assert reason=="added" and len(added)==1,diagnostics
    via=added[0];at=(via.GetPosition().x/1e6,via.GetPosition().y/1e6)
    assert all(math.dist(at,point)<=1.5+1e-9 for point in (p,n))
    assert via.GetWidth()==pcbnew.FromMM(.6) and via.GetDrillValue()==pcbnew.FromMM(.3)
    assert diagnostics["refinement"]["legal_seats"]>0 and source.read_bytes()==original
    route._discard_items(board,added)
    refused,status=route._add_pair_transition_returns(board,center,vector,
        signal_points=(p,n),refine=True,reference_contact=lambda *a:False)
    assert not refused and status not in ("covered","added")
    assert not list(board.GetTracks())


def ids(board):
    return {t.m_Uuid.AsString() for t in board.GetTracks()}


@pytest.mark.parametrize("failure", (None,"seed","route","recheck","deadline"))
def test_joint_retry_is_bounded_and_preserves_endpoint_parent(failure):
    board=board_fixture()
    parent=pcbnew.PCB_TRACK(board);parent.SetNet(board.FindNet("OTHER"))
    parent.SetStart(pcbnew.VECTOR2I_MM(2,2));parent.SetEnd(pcbnew.VECTOR2I_MM(3,2))
    parent.SetWidth(pcbnew.FromMM(.2));parent.SetLayer(pcbnew.F_Cu);parent.SetLocked(True)
    board.Add(parent);group=pcbnew.PCB_GROUP(board);group.SetName("retained");board.Add(group);group.AddItem(parent)
    before=ids(board);calls=[];seeded=[]
    pair=dict(name="RENAMED_PAIR",p="SIGNAL_P",n="SIGNAL_N",width=.2,gap=.3)
    deadline=time.monotonic()+30
    def emit(board,pair,**kwargs):
        calls.append(kwargs)
        if len(calls)==2:
            assert ids(board)==before|set(seeded)
        child=pcbnew.PCB_TRACK(board);child.SetNet(board.FindNet(pair["p"]))
        child.SetStart(pcbnew.VECTOR2I_MM(10,10));child.SetEnd(pcbnew.VECTOR2I_MM(12,10))
        child.SetWidth(pcbnew.FromMM(.2));child.SetLayer(pcbnew.In2_Cu);board.Add(child)
        return (dict(refused="downstream native refusal") if failure=="route" and len(calls)==2 else
                dict(route_mode="test-only",segments=1))
    def returns(board,*a,refine=False,**kwargs):
        if not seeded and not refine:
            return [],"initial field refused"
        if refine:
            if failure=="seed":
                return [],"seed field refused"
            via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet("GND"))
            via.SetPosition(pcbnew.VECTOR2I_MM(11,11));via.SetWidth(pcbnew.FromMM(.6))
            via.SetDrill(pcbnew.FromMM(.3));via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
            seeded.append(via.m_Uuid.AsString());return [via],"added"
        return ([],"live field refused") if failure=="recheck" else ([],"covered")
    request=dict(center=(11,10),pair_vector=(0,.5),axis=(1,0),all_points=((11,9.75),(11,10.25)),
        side="start",signal_at_mm=[[11,9.75],[11,10.25]],return_diameter=.6,return_drill=.3)
    with patch.object(route,"route_coupled_pair",side_effect=emit), \
         patch.object(route,"_add_pair_transition_returns",side_effect=returns), \
         patch.object(route,"_deadline_expired",return_value=failure=="deadline"):
        result,transitions=route._route_with_required_pair_returns(board,pair,[request],
            route_options=dict(clearance=.2,deadline=deadline),parent_ids=before)
    assert len(calls)<=2 and all(row["deadline"]==deadline for row in calls)
    assert parent.IsLocked() and group.ContainsItem(parent)
    if failure:
        assert result.get("refused") and ids(board)==before and not transitions
    else:
        assert not result.get("refused") and before<=ids(board)
        assert result["return_route_backtrack"]["outcome"]=="joint_route_and_returns_qualified"
        assert len(transitions)==1 and len(calls)==2


def test_nonspanning_existing_ground_via_does_not_count_as_return():
    board=board_fixture()
    via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet("GND"))
    via.SetPosition(pcbnew.VECTOR2I_MM(10,11));via.SetWidth(pcbnew.FromMM(.6))
    via.SetDrill(pcbnew.FromMM(.3));via.SetViaType(pcbnew.VIATYPE_BLIND)
    via.SetLayerPair(pcbnew.In1_Cu,pcbnew.In2_Cu);board.Add(via)
    added,status=route._add_pair_transition_returns(board,(10,10),(1,0),signal_points=((10,10),))
    assert status=="added" and added
