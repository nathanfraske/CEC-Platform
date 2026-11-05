"""A saved outline broadens search, never copper or current authority."""
import time
import pcbnew
import pytest
import cec_fr as fr
import cec_field_coupling as field
from test_lastmile import _board


def fixture(angle=0, *, closed=False):
    b=_board([],edge=(0,0,30,30))
    for name in ('/different/control','/unrelated/retained_bus'):
        b.Add(pcbnew.NETINFO_ITEM(b,name))
    def rotated(x,y):
        dx,dy=fr._nm(x-15),fr._nm(y-15)
        for _ in range(angle//90):dx,dy=dy,-dx
        return pcbnew.VECTOR2I(15000000+dx,15000000+dy)
    for layer in (pcbnew.F_Cu,pcbnew.B_Cu):
        t=pcbnew.PCB_TRACK(b);t.SetStart(rotated(10,0))
        t.SetEnd(rotated(10,30 if closed else 20));t.SetLayer(layer)
        t.SetWidth(fr._nm(.4));t.SetNet(b.FindNet('/unrelated/retained_bus'));t.SetLocked(True);b.Add(t)
    return b,rotated(5,10),rotated(15,10)


def route(b,s,t,*,whole=False,**kwargs):
    d={}
    opts=dict(width_for_layer=lambda _:400000,start_layers=(pcbnew.F_Cu,),
        end_layers=(pcbnew.F_Cu,),max_vias=0,grid_mm=.75,margin_mm=2,
        deadline_monotonic=time.monotonic()+3.,diagnostics=d,
        native_board_envelope=whole,canonical_turns_only=True)
    opts.update(kwargs)
    ops=fr._multilayer_maze_lastmile_ops(b,s,t,b.GetNetcodeFromNetname('/different/control'),
        (pcbnew.F_Cu,pcbnew.B_Cu),200000,
        lambda a,c,h:fr._edge_leg_clear(b,a,c,h+200000),**opts)
    return ops,d


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('reverse',[False,True])
def test_native_outline_finds_distant_detour_without_moving_retained_copper(angle,reverse):
    b,s,t=fixture(angle)
    if reverse:s,t=t,s
    before=field._field_snapshot_inventory(b)
    old,local=route(b,s,t)
    ops,d=route(b,s,t,whole=True)
    assert old is None and local['stop']=='bounded_graph_exhausted'
    assert ops and d['stop']=='found'
    assert d['search_window_policy']=='native_saved_outline_envelope'
    bounds=b.GetBoardEdgesBoundingBox()
    assert d['native_board_envelope_nm']==[bounds.GetLeft(),bounds.GetTop(),bounds.GetRight(),bounds.GetBottom()]
    assert tuple(ops[0][1])==tuple(s) and tuple(ops[-1][2])==tuple(t)
    for kind,a,c,w,layer in ops:
        assert kind=='trk' and w==400000 and layer==pcbnew.F_Cu
        assert fr._edge_leg_clear(b,a,c,w//2+200000)
        assert fr._tap_foreign_clear(b,a,c,w,layer,200000,{b.GetNetcodeFromNetname('/different/control')})
        dx,dy=abs(a.x-c.x),abs(a.y-c.y)
        assert not dx or not dy or dx==dy
    assert before==field._field_snapshot_inventory(b)
    assert not d['release_authority'] and not d['no_path_proof']


def test_native_envelope_never_opens_a_wall_through_copper_or_outside_board():
    b,s,t=fixture(closed=True)
    ops,d=route(b,s,t,whole=True)
    assert ops is None and d['stop']=='bounded_graph_exhausted'


@pytest.mark.parametrize('bad',[None,1,'yes',{},[]])
def test_envelope_requires_literal_boolean(bad):
    b,s,t=fixture()
    with pytest.raises(ValueError,match='bounded_explicit_native_board_envelope'):
        route(b,s,t,whole=bad)


@pytest.mark.parametrize('deadline',[None,float('inf'),float('nan')])
def test_full_board_search_requires_finite_bounded_lease(deadline):
    b,s,t=fixture()
    with pytest.raises(ValueError,match='bounded_explicit_native_board_envelope'):
        route(b,s,t,whole=True,deadline_monotonic=deadline)


def test_no_outline_cannot_create_a_guessed_envelope():
    b=pcbnew.BOARD();b.Add(pcbnew.NETINFO_ITEM(b,'/different/control'))
    ops,d=route(b,pcbnew.VECTOR2I_MM(5,10),pcbnew.VECTOR2I_MM(15,10),whole=True)
    assert ops is None and d['stop']=='native_board_envelope_unavailable_or_endpoint_outside'


def test_declared_length_limit_still_prevents_long_detour():
    b,s,t=fixture()
    ops,d=route(b,s,t,whole=True,max_length_nm=fr._nm(11))
    assert ops is None and not d['no_path_proof']


def test_expired_lease_is_not_no_path_evidence():
    b,s,t=fixture()
    ops,d=route(b,s,t,whole=True,deadline_monotonic=time.monotonic()-1)
    assert ops is None and d['stop']=='deadline_exhausted' and not d['no_path_proof']


@pytest.mark.parametrize('bad',[None,1,'yes'])
def test_bridge_requires_explicit_bounded_envelope(bad):
    b,s,t=fixture()
    with pytest.raises(ValueError,match='bounded_explicit_bridge_board_envelope'):
        fr._lastmile_bridge(b,tuple(s),[pcbnew.F_Cu],tuple(t),[pcbnew.F_Cu],400000,
            b.GetNetcodeFromNetname('/different/control'),[pcbnew.F_Cu,pcbnew.B_Cu],200000,
            deadline_monotonic=time.monotonic()+1,middle_native_board_envelope=bad)


def test_lastmile_envelope_is_opt_in_and_bounded():
    b,s,t=fixture()
    for options in ({'native_board_envelope':1},{'native_board_envelope':True},
            {'native_board_envelope':True,'wall_timeout_s':float('inf')}):
        with pytest.raises(ValueError,match='bounded_explicit_lastmile_board_envelope'):
            fr.synthesize_lastmile(b,**options)


def test_bridge_forwards_the_same_native_outline_policy():
    b,s,t=fixture();d={}
    ops=fr._lastmile_bridge(b,tuple(s),[pcbnew.F_Cu,pcbnew.B_Cu],tuple(t),
        [pcbnew.F_Cu,pcbnew.B_Cu],400000,b.GetNetcodeFromNetname('/different/control'),
        [pcbnew.F_Cu,pcbnew.B_Cu],200000,
        leg_ok=lambda a,c,h:fr._edge_leg_clear(b,a,c,h+200000),
        deadline_monotonic=time.monotonic()+3.,_multilayer_only=True,
        middle_grid_mm=.75,middle_max_vias=0,middle_native_board_envelope=True,diagnostics=d)
    assert ops and d['middle_searches'][0]['search_window_policy']=='native_saved_outline_envelope'
    assert all(o[0]=='trk' and o[3]==400000 for o in ops)


def test_shared_lastmile_uses_retained_THT_layers_without_new_barrels():
    b,s,t=fixture();net=b.FindNet('/different/control')
    # This fixture exercises the distant detour, not an unobstructed inner
    # layer in the default six-layer test board.  Both retained THT pads still
    # expose every copper layer that actually exists on this board.
    b.SetCopperLayerCount(2)
    for index,at in enumerate((s,t)):
        f=pcbnew.FOOTPRINT(b);f.SetReference('UNRELATED_'+str(index))
        p=pcbnew.PAD(f);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE);p.SetSize(pcbnew.VECTOR2I_MM(2,2))
        p.SetDrillSize(pcbnew.VECTOR2I_MM(.6,.6));p.SetLayerSet(pcbnew.PAD.PTHMask())
        p.SetPosition(at);p.SetNet(net);f.Add(p);b.Add(f)
    result=fr.synthesize_lastmile(b,max_mm=30,min_w=.4,clearance=.2,
        include_nets={'/different/control'},maze_max_mm=30,prefer_bridge=True,
        native_board_envelope=True,wall_timeout_s=5,per_net_timeout_s=5,
        netclass_resolver=lambda _:dict(track_width=.4,clearance=.2))
    assert result['closed']==1
    assert not [o for o in b.GetTracks() if o.GetClass()=='PCB_VIA']
    searches=[]
    for row in result['bridge_search_diagnostics']:
        detail=row['detail']
        searches.extend(detail.get('middle_searches',[]))
        searches.extend(detail.get('early_multilayer_search',{}).get('detail',{}).get('middle_searches',[]))
    assert searches and any(r['stop']=='found' and
        r['search_window_policy']=='native_saved_outline_envelope' for r in searches)
