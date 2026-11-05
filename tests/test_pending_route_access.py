"""Future terminals are separate shape constraints, never material/plating."""
import time
import pcbnew
import pytest
import cec_fr as fr
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
from cec_pending_route_access import Guard
from test_lastmile import _board
from test_local_bridge_dogbones import fixture,seats


def request(layer=pcbnew.F_Cu,net='FUTURE'):
    return dict(uid='source-native-obligation',net=net,layer=layer,width=200000,
        start=(20000000,20000000),end=(30000000,20000000))


@pytest.mark.parametrize('layer',[0,2,6,8])
def test_new_barrel_checks_future_entry_on_every_enabled_face_without_materializing_it(layer):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6);before=field._field_snapshot_inventory(b)
    g=Guard(b,[request(layer)],net='OTHER',clearance_nm=200000,clearance_for=lambda n:200000)
    a=pcbnew.VECTOR2I_MM(20,20);z=pcbnew.VECTOR2I_MM(21,20)
    assert not g.planar(a,z,200000,layer)
    other=2 if layer!=2 else 0
    assert g.planar(a,z,200000,other)
    assert not g.via(a,300000,600000)
    assert g.via(pcbnew.VECTOR2I_MM(24,24),300000,600000)
    assert field._field_snapshot_inventory(b)==before
    r=g.report();assert not r['pending_disks_are_native_copper'] and not r['pending_disks_are_plating']
    assert r['via_refusals']==1 and not r['release_authority']


def test_own_future_ends_are_not_foreign_obstacles_or_new_connections():
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    g=Guard(b,[request()],net='FUTURE',clearance_nm=200000,clearance_for=lambda n:200000)
    assert g.planar(pcbnew.VECTOR2I_MM(20,20),pcbnew.VECTOR2I_MM(30,20),200000,0)
    assert g.via(pcbnew.VECTOR2I_MM(20,20),300000,600000)
    assert not list(b.GetTracks()) and not list(b.GetFootprints()) and not list(b.Zones())


def test_pending_clearance_is_the_stricter_of_both_route_contracts():
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    g=Guard(b,[request()],net='OTHER',clearance_nm=200000,clearance_for=lambda n:700000)
    a=pcbnew.VECTOR2I_MM(20.6,19);z=pcbnew.VECTOR2I_MM(20.6,21)
    assert not g.planar(a,z,200000,0)
    assert g.planar(pcbnew.VECTOR2I_MM(21,19),pcbnew.VECTOR2I_MM(21,21),200000,0)


def fill_fixture():
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    b.Add(pcbnew.NETINFO_ITEM(b,'HELD_RAIL'))
    z=pcbnew.ZONE(b);z.SetLayer(0);z.SetNet(b.FindNet('HELD_RAIL'));z.Outline().NewOutline()
    for x,y in ((10,10),(40,10),(40,40),(10,40)):z.Outline().Append(x*1000000,y*1000000)
    actual=pcbnew.SHAPE_POLY_SET();actual.NewOutline()
    for x,y in ((24,24),(26,24),(26,26),(24,26)):actual.Append(x*1000000,y*1000000)
    z.SetFilledPolysList(0,actual);z.SetIsFilled(True);b.Add(z)
    return b,z


def test_held_copper_uses_real_filled_polygons_not_large_zone_outline_or_plot_overlay():
    b,z=fill_fixture();before=field._field_snapshot_inventory(b)
    g=Guard(b,[request(net='OTHER')],net='OTHER',clearance_nm=200000,
        clearance_for=lambda n:200000,held_source=b,held_zone_uuids=[force._uid(z)])
    assert g.planar(pcbnew.VECTOR2I_MM(14,14),pcbnew.VECTOR2I_MM(16,14),200000,0)
    assert not g.planar(pcbnew.VECTOR2I_MM(24,25),pcbnew.VECTOR2I_MM(26,25),200000,0)
    assert not g.via(pcbnew.VECTOR2I_MM(25,25),300000,600000)
    assert g.planar(pcbnew.VECTOR2I_MM(24,25),pcbnew.VECTOR2I_MM(26,25),200000,2)
    assert g.report()['actual_source_filled_layer_polygons']==1
    assert field._field_snapshot_inventory(b)==before


def test_unknown_held_fill_is_not_fabricated_from_its_outline():
    b,z=fill_fixture();z.SetIsFilled(False)
    with pytest.raises(ValueError,match='actual_filled_source'):
        Guard(b,[request()],net='OTHER',clearance_nm=200000,clearance_for=lambda n:200000,
            held_source=b,held_zone_uuids=[force._uid(z)])


@pytest.mark.parametrize('key,value',[('width',True),('width',0),('layer',3),('start',[1.5,2]),
    ('start',[True,1]),('uid',[]),('net',None)])
def test_malformed_future_entries_fail_closed(key,value):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6);r=request();r[key]=value
    with pytest.raises(ValueError):Guard(b,[r],net='OTHER',clearance_nm=200000,clearance_for=lambda n:200000)


@pytest.mark.parametrize('answer',[False,1,None])
def test_additional_via_guard_is_required_by_the_multilayer_search(answer):
    b=_board([],edge=(0,0,10,10));b.Add(pcbnew.NETINFO_ITEM(b,'RENAMED'))
    calls=[]
    def gate(point,drill,diameter):calls.append((list(point),drill,diameter));return answer
    ops=fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(3,3),pcbnew.VECTOR2I_MM(6,3),
        b.GetNetcodeFromNetname('RENAMED'),[0,2],200000,lambda *a:True,width_for_layer=lambda l:200000,
        start_layers=[0],end_layers=[2],grid_mm=1.,margin_mm=1.,max_vias=1,via_guard=gate,
        deadline_monotonic=time.monotonic()+2.)
    assert ops is None and calls and not list(b.GetTracks())
    assert all((d,w)==(300000,600000) for _,d,w in calls)


def test_additional_via_guard_can_admit_native_legal_transition():
    b=_board([],edge=(0,0,10,10));b.Add(pcbnew.NETINFO_ITEM(b,'RENAMED'))
    ops=fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(3,3),pcbnew.VECTOR2I_MM(6,3),
        b.GetNetcodeFromNetname('RENAMED'),[0,2],200000,lambda *a:True,width_for_layer=lambda l:200000,
        start_layers=[0],end_layers=[2],grid_mm=1.,margin_mm=1.,max_vias=1,via_guard=lambda *a:True,
        deadline_monotonic=time.monotonic()+2.)
    assert ops and sum(op[0]=='via' for op in ops)==1 and not list(b.GetTracks())


@pytest.mark.parametrize('kind',['dogbone','inset'])
def test_local_profiled_via_helpers_cannot_bypass_additional_all_face_guard(kind):
    b,p,nc,layer=fixture(size=.8);before=field._field_snapshot_inventory(b);calls=[]
    def gate(at,drill,dia):calls.append((list(at),drill,dia));return False
    if kind=='dogbone':
        assert not seats(b,p,nc,layer,via_guard=gate,allow_face_launch=True)
    else:
        result=fr._local_pofv_inset_seats(b,p.GetPosition(),layer,200000,nc,200000,
            profile=fab.get_profile(fab.board_profile_name(b)),leg_ok=lambda *a:True,via_guard=gate)
        assert not result
    assert calls and field._field_snapshot_inventory(b)==before


def test_bridge_propagates_additional_via_guard_to_all_local_and_offset_seats():
    b,p,nc,layer=fixture();calls=[]
    def gate(at,drill,dia):calls.append((list(at),drill,dia));return False
    result=fr._lastmile_bridge(b,(30000000,40000000),{layer},(35000000,40000000),{6},200000,nc,[6],200000,
        via_guard=gate,allow_maze=False,allow_lattice=False,seat_limit=1,seat_offsets_mm=(.5,),
        seat_angles_deg=(0,),endpoint_handoffs=False,deadline_monotonic=time.monotonic()+2.)
    assert result is None and calls and not list(b.GetTracks())


@pytest.mark.parametrize('value',[False,1,'yes'])
@pytest.mark.parametrize('mode',['maze','bridge'])
def test_noncallable_additional_via_policy_is_not_silently_ignored(value,mode):
    b=_board([],edge=(0,0,10,10));b.Add(pcbnew.NETINFO_ITEM(b,'RENAMED'))
    code=b.GetNetcodeFromNetname('RENAMED')
    with pytest.raises(ValueError,match='callable_additional'):
        if mode=='maze':
            fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(3,3),pcbnew.VECTOR2I_MM(6,3),code,[0,2],
                200000,lambda *a:True,width_for_layer=lambda l:200000,via_guard=value)
        else:
            fr._lastmile_bridge(b,(3000000,3000000),{0},(6000000,3000000),{0},200000,code,[2],
                200000,via_guard=value)


def test_local_shape_constraints_do_not_enable_accumulated_parallel_field_history():
    b=_board([],edge=(0,0,10,10));b.Add(pcbnew.NETINFO_ITEM(b,'RENAMED'))
    r=request();r.update(start=(4500000,3000000),end=(4500000,6000000))
    g=Guard(b,[r],net='RENAMED',clearance_nm=200000,clearance_for=lambda n:200000);d={}
    ops=fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(3,3),pcbnew.VECTOR2I_MM(6,3),
        b.GetNetcodeFromNetname('RENAMED'),[0],200000,lambda *a:True,width_for_layer=lambda l:200000,
        start_layers=[0],end_layers=[0],grid_mm=.25,margin_mm=1.,max_vias=0,
        local_shape_guard=g.planar,allow_single_layer=True,neutral_state_dominance=True,
        field_state_dominance=True,diagnostics=d,deadline_monotonic=time.monotonic()+2.)
    assert ops and d['neutral_state_dominance_active'] and not d['field_state_memory_preserved']
    assert all(g.planar(op[1],op[2],op[3],op[4]) for op in ops)
    assert d['hop_refusals']['local_native_shape_constraint']>0


def test_local_shape_and_accumulated_field_predicates_remain_independent():
    b=_board([],edge=(0,0,10,10));b.Add(pcbnew.NETINFO_ITEM(b,'RENAMED'));d={};calls=[]
    def shape(a,z,w,l):calls.append((list(a),list(z)));return True
    ops=fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(3,3),pcbnew.VECTOR2I_MM(6,3),
        b.GetNetcodeFromNetname('RENAMED'),[0],200000,lambda *a:True,width_for_layer=lambda l:200000,
        start_layers=[0],end_layers=[0],grid_mm=.5,margin_mm=.5,max_vias=0,
        planar_guard=lambda *a:False,local_shape_guard=shape,allow_single_layer=True,
        neutral_state_dominance=True,field_state_dominance=True,diagnostics=d,
        deadline_monotonic=time.monotonic()+2.)
    assert ops is None and d['field_state_memory_preserved']
    assert d['hop_refusals']['same_layer_field_search_prediction']>0
