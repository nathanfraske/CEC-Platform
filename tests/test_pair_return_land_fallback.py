"""Native, transformed reference-return land fallback; never drill reduction.

The native aperture tests exercise copper/hole guards on loaded boards. Their
explicit reference callbacks test filter propagation, not full-board plane or
current qualification. The transaction tests isolate rollback and deadlines.
"""
import math
from unittest.mock import patch

import pcbnew
import pytest

import cec_fab_profile as fab
import cec_precision_route as route
from test_joint_pair_return_search import board_fixture, ids, pose


@pytest.mark.parametrize("minimum,drill,ring,requested_shape,expected", (
    (.5,.3,.1,(.6,.3),((.6,.3),(.5,.3))),
    (.5,.3,.125,(.6,.3),((.6,.3),(.55,.3))),
    (.7,.4,.15,(.6,.3),((.7,.4),)),
    (.4,.25,.1,(.6,.35),((.6,.35),(.55,.35))),
    (.6,.3,.1,(.6,.3),((.6,.3),)),
    (.5,.3,.1,(.45,.25),((.5,.3),)),
))
def test_menu_obeys_absolute_board_floors_without_smaller_drill(
        minimum,drill,ring,requested_shape,expected):
    board=board_fixture();settings=board.GetDesignSettings()
    settings.m_ViasMinSize=round(minimum*1e6)
    settings.m_MinThroughDrill=round(drill*1e6)
    settings.m_ViasMinAnnularWidth=round(ring*1e6)
    menu=fab.pair_return_via_geometry_candidates(board,*requested_shape)
    actual=tuple((g['diameter_mm'],g['drill_mm']) for g in menu)
    assert actual==expected
    assert len({g[1] for g in actual})==1
    assert all(round(d*1e6)>=round(h*1e6)+2*round(ring*1e6) for d,h in actual)
    assert len(menu)<=2 and menu[0]['selection']=='preferred'


@pytest.mark.parametrize("requested_shape", ((math.nan,.3),(.6,math.inf),
    (0,.3),(.6,0),(-.5,.3),(.6,-.3)))
def test_invalid_request_is_not_an_authority_to_shrink(requested_shape):
    with pytest.raises(ValueError):
        fab.pair_return_via_geometry_candidates(board_fixture(),*requested_shape)


def add_via(board, point, diameter=.6, drill=.3, net='GND'):
    via=pcbnew.PCB_VIA(board);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetPosition(pcbnew.VECTOR2I_MM(*point));via.SetWidth(round(diameter*1e6))
    via.SetDrill(round(drill*1e6));via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNet(board.FindNet(net));board.Add(via)
    return via


@pytest.mark.parametrize("quarter",range(4))
@pytest.mark.parametrize("mirror",(False,True))
def test_loaded_native_aperture_accepts_floor_only_with_same_guards(tmp_path,quarter,mirror):
    board=board_fixture()
    # 0.91 mm aperture: .5 land + .2 clearance on each side fits, .6 cannot.
    walls=((0,0,8.445,20),(9.355,0,20,20),
           (8.445,0,9.355,8.85),(8.445,10.15,9.355,20))
    for index,(x0,y0,x1,y1) in enumerate(walls):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('ARBITRARY_'+str(index));board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('q');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(x1-x0,y1-y0));pad.SetNet(board.FindNet('OTHER'))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*pose(((x0+x1)/2,(y0+y1)/2),quarter,mirror,shift=(0,0))))
        pad.SetOrientationDegrees(90*quarter);fp.Add(pad)
    for edge in board.GetDrawings():
        for get,setter in ((edge.GetStart,edge.SetStart),(edge.GetEnd,edge.SetEnd)):
            at=get();setter(pcbnew.VECTOR2I_MM(*pose((at.x/1e6,at.y/1e6),quarter,mirror,shift=(0,0))))
    # Keep GND through native loading without a barrel through the foreign
    # front-face walls (which would be a real short and can infer OTHER).
    ground_fp=pcbnew.FOOTPRINT(board);ground_fp.SetReference('RETURN_OWNER');board.Add(ground_fp)
    ground_pad=pcbnew.PAD(ground_fp);ground_pad.SetNumber('g')
    ground_pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);ground_pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    ground_pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
    ground_layers=pcbnew.LSET();ground_layers.AddLayer(pcbnew.B_Cu)
    ground_pad.SetLayerSet(ground_layers)
    ground_pad.SetPosition(pcbnew.VECTOR2I_MM(*pose((1,1),quarter,mirror,shift=(0,0))))
    ground_pad.SetNet(board.FindNet('GND'));ground_fp.Add(ground_pad)
    source=tmp_path/'renamed.kicad_pcb';pcbnew.SaveBoard(str(source),board,True)
    original=source.read_bytes();board=pcbnew.LoadBoard(str(source))
    settings=board.GetDesignSettings();settings.m_ViasMinSize=500000
    settings.m_MinThroughDrill=300000;settings.m_ViasMinAnnularWidth=100000
    parent=ids(board)
    points=tuple(pose(at,quarter,mirror,shift=(0,0)) for at in ((10,9.75),(10,10.25)))
    center=pose((10,10),quarter,mirror,shift=(0,0))
    vector=tuple(points[1][i]-points[0][i] for i in (0,1));seen=[];diagnostics={}
    def reference(at,diameter):
        seen.append(diameter);return True
    made,status=route._add_pair_transition_returns_with_land_fallback(
        board,center,vector,signal_points=points,refine=True,
        reference_contact=reference,diagnostics=diagnostics)
    assert status=='added' and len(made)==1,diagnostics
    assert [row['geometry']['diameter_mm'] for row in diagnostics['geometry_attempts']]==[.6,.5]
    assert diagnostics['selected_geometry']['selection']=='board-minimum-land-same-drill'
    assert made[0].GetWidth()==500000 and made[0].GetDrillValue()==300000
    at=tuple(made[0].GetPosition()[i]/1e6 for i in (0,1))
    assert all(math.dist(at,q)<=1.5+1e-9 for q in points)
    assert set(seen)=={.6,.5} and source.read_bytes()==original
    route._discard_items(board,made)
    refused,status=route._add_pair_transition_returns_with_land_fallback(
        board,center,vector,signal_points=points,refine=True,reference_contact=lambda *a:False)
    assert not refused and status not in ('added','covered') and ids(board)==parent
    refused,status=route._add_pair_transition_returns_with_land_fallback(
        board,center,vector,signal_points=points,refine=True,
        return_reach_mm=.2,reference_contact=lambda *a:True)
    assert not refused and status not in ('added','covered') and ids(board)==parent
    hole_fp=pcbnew.FOOTPRINT(board);hole_fp.SetReference('UNRELATED_MECHANICAL_HOLE');board.Add(hole_fp)
    hole=pcbnew.PAD(hole_fp);hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE);hole.SetLayerSet(pcbnew.LSET.AllCuMask())
    hole.SetSize(pcbnew.VECTOR2I_MM(.6,.6));hole.SetDrillSize(pcbnew.VECTOR2I_MM(.6,.6))
    hole.SetPosition(pcbnew.VECTOR2I_MM(*pose((8.9,9.5),quarter,mirror,shift=(0,0))));hole_fp.Add(hole)
    refused,status=route._add_pair_transition_returns_with_land_fallback(
        board,center,vector,signal_points=points,refine=True,reference_contact=lambda *a:True)
    assert not refused and status not in ('added','covered') and ids(board)==parent


@pytest.mark.parametrize("failure",('partial','exception','deadline'))
def test_attempts_release_partial_fields_and_preserve_source(failure):
    board=board_fixture();settings=board.GetDesignSettings()
    settings.m_ViasMinSize=500000;settings.m_MinThroughDrill=300000
    settings.m_ViasMinAnnularWidth=100000
    inherited=add_via(board,(1,1));inherited.SetLocked(True);parent=ids(board);calls=[]
    deadline=123.0
    def construct(board,*args,via_diameter_mm,via_drill_mm,deadline,**kwargs):
        assert ids(board)==parent
        calls.append((via_diameter_mm,via_drill_mm,deadline))
        via=add_via(board,(10,10),via_diameter_mm,via_drill_mm)
        if failure=='exception':
            raise RuntimeError('native-field-fault')
        return [via],'native field refused'
    with patch.object(route,'_add_pair_transition_returns',side_effect=construct), \
         patch.object(route,'_deadline_expired',side_effect=lambda d:failure=='deadline' and bool(calls)):
        if failure=='exception':
            with pytest.raises(RuntimeError,match='native-field-fault'):
                route._add_pair_transition_returns_with_land_fallback(board,(10,10),(1,0),deadline=deadline)
        else:
            made,status=route._add_pair_transition_returns_with_land_fallback(board,(10,10),(1,0),deadline=deadline)
            assert not made and status not in ('added','covered')
    assert len(calls)==(2 if failure=='partial' else 1)
    assert all(h==.3 and d==deadline for _,h,d in calls)
    assert ids(board)==parent and inherited.IsLocked()


def test_preferred_success_does_not_probe_smaller_land():
    board=board_fixture();diagnostics={}
    with patch.object(route,'_add_pair_transition_returns',return_value=([],'covered')) as construct:
        made,status=route._add_pair_transition_returns_with_land_fallback(
            board,(10,10),(1,0),diagnostics=diagnostics)
    assert not made and status=='covered' and construct.call_count==1
    assert diagnostics['selected_geometry'] is None
    assert not diagnostics['current_capacity_qualification']
