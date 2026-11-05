"""Fine terminal axes are search proposals, never copper/clearance authority."""
import time
from unittest import mock

import pcbnew
import pytest

import cec_fr as fr
import cec_field_coupling as field
from test_lastmile import _board


def fixture(angle=0, *, closed=False):
    b=_board([],edge=(0,0,60,60))
    for name in ('unrelated-renamed-control','unrelated-renamed-obstacles'):
        b.Add(pcbnew.NETINFO_ITEM(b,name))
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('UNRELATED_NATIVE_PIN_FENCE')
    boxes=[(0,4.0,12,4.35),(0,5.8,12,6.0),(4.3,4.0,4.6,6.0),(5.9,5.1,6.1,5.5)]
    if closed:boxes.append((6.4,4.35,6.7,5.8))
    for number,(x0,y0,x1,y1) in enumerate(boxes):
        pad=pcbnew.PAD(fp);pad.SetNumber(str(number+1));pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I(fr._nm(x1-x0),fr._nm(y1-y0)))
        pad.SetPosition(pcbnew.VECTOR2I(fr._nm((x0+x1)/2),fr._nm((y0+y1)/2)))
        pad.SetNet(b.FindNet('unrelated-renamed-obstacles'));fp.Add(pad)
    b.Add(fp)
    if angle:fp.Rotate(pcbnew.VECTOR2I_MM(30,30),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    def rotate(x,y):
        dx,dy=fr._nm(x-30),fr._nm(y-30)
        for _ in range(angle//90):dx,dy=dy,-dx
        return pcbnew.VECTOR2I(30000000+dx,30000000+dy)
    return b,rotate(5.13,5.27),rotate(40.13,5.27)


def route(b,s,t, *, detail=None,width=200000,limit=None,expired=False):
    # A finite native channel-hint menu can omit the source fence on a dense
    # long route. Removing hints does NOT remove any real native obstacle:
    # the exact _foreign_shape_indexes / capsule guards still see every pad.
    with mock.patch('cec_maze_channels.native_obstacle_boxes',return_value=[]):
        return fr._maze_lastmile_legs(b,s,t,width,pcbnew.F_Cu,200000,
            b.GetNetcodeFromNetname('unrelated-renamed-control'),
            lambda a,c,h:fr._edge_leg_clear(b,a,c,h+200000),grid_mm=1.5,margin_mm=2.,
            deadline_monotonic=time.monotonic()+(-1 if expired else 3),
            endpoint_detail_grid_mm=detail,max_length_nm=limit)


@pytest.mark.parametrize('angle',range(0,360,90))
@pytest.mark.parametrize('reverse',[False,True])
def test_native_fine_pin_escape_with_coarse_middle_and_unchanged_copper(angle,reverse):
    b,s,t=fixture(angle)
    if reverse:s,t=t,s
    before=field._field_snapshot_inventory(b)
    assert route(b,s,t) is None
    legs=route(b,s,t,detail=.2)
    assert legs and legs[0][0]==s and legs[-1][1]==t
    assert all(w==200000 for a,c,w in legs)
    for a,c,w in legs:
        dx,dy=abs(a.x-c.x),abs(a.y-c.y)
        assert not dx or not dy or dx==dy
        assert fr._tap_foreign_clear(b,a,c,w,pcbnew.F_Cu,200000,
            {b.GetNetcodeFromNetname('unrelated-renamed-control')})
    assert before==field._field_snapshot_inventory(b) and not list(b.GetTracks())


@pytest.mark.parametrize('case',['wide','closed','length','expired'])
def test_detail_does_not_override_width_native_walls_length_or_work(case):
    b,s,t=fixture(closed=case=='closed')
    before=field._field_snapshot_inventory(b)
    assert route(b,s,t,detail=.2,width=400000 if case=='wide' else 200000,
        limit=35000000 if case=='length' else None,expired=case=='expired') is None
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('detail',[True,0,.01,.6,2,float('nan'),float('inf'),'fine'])
def test_detail_requires_bounded_numeric_density(detail):
    b,s,t=fixture()
    with pytest.raises(ValueError,match='bounded_endpoint_detail_grid_and_deadline_required'):
        route(b,s,t,detail=detail)


@pytest.mark.parametrize('deadline',[None,True,float('inf'),float('nan')])
def test_detail_requires_explicit_finite_deadline(deadline):
    b,s,t=fixture()
    with pytest.raises(ValueError,match='bounded_endpoint_detail_grid_and_deadline_required'):
        fr._maze_lastmile_legs(b,s,t,200000,0,200000,1,lambda *a:True,
            endpoint_detail_grid_mm=.2,deadline_monotonic=deadline)


def invoke(*, coarse_succeeds=False, validator=None,detail=.2):
    b=_board([],edge=(0,0,60,60));net=pcbnew.NETINFO_ITEM(b,'another-renamed-source');b.Add(net)
    s,t=pcbnew.VECTOR2I_MM(5,5),pcbnew.VECTOR2I_MM(40,5)
    deadline=time.monotonic()+1;report={}
    def maze(board,start,end,width,*args,endpoint_detail_grid_mm=None,**kwargs):
        return [(start,end,width)] if coarse_succeeds or endpoint_detail_grid_mm else None
    with mock.patch.object(fr,'_canonical_45_xy_paths',return_value=[]), \
         mock.patch.object(fr,'_offset_manhattan_xy_paths',return_value=[]), \
         mock.patch('cec_maze_channels.orthogonal_channel_paths',return_value=[]), \
         mock.patch.object(fr,'_maze_lastmile_legs',side_effect=maze) as calls:
        result=fr._guarded_profiled_lastmile_legs(b,s,t,200000,0,200000,net.GetNetCode(),
            lambda *a:True,refine_maze=True,deadline_monotonic=deadline,
            endpoint_detail_grid_mm=detail,search_diagnostics=report,path_validator=validator)
    return result,calls,report,deadline


def test_detail_retry_preserves_global_grid_contract_and_shared_deadline():
    result,calls,report,deadline=invoke()
    assert result and len(calls.call_args_list)==2
    assert [q.kwargs['grid_mm'] for q in calls.call_args_list]==[1.5,1.5]
    assert [q.kwargs.get('endpoint_detail_grid_mm') for q in calls.call_args_list]==[None,.2]
    assert all(q.args[3]==200000 and q.args[5]==200000 and
        q.kwargs['deadline_monotonic']==deadline for q in calls.call_args_list)
    assert all(q['same_deadline'] and not q['no_path_proof'] for q in report['maze_tiers'])


def test_successful_coarse_route_is_unchanged_and_full_path_validator_still_required():
    result,calls,*_=invoke(coarse_succeeds=True)
    assert result and calls.call_count==1
    validator=mock.Mock(return_value=False)
    result,calls,*_=invoke(validator=validator)
    assert result is None and calls.call_count==2 and validator.call_count==1


def test_default_does_not_expand_legacy_search():
    result,calls,*_=invoke(detail=None)
    assert result is None and calls.call_count==1
