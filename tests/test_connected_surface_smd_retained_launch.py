"""A real retained barrel can connect a cut on one face to an SMD on another."""
import time
import pcbnew
import pytest
import cec_native_route_schedule as schedule
import cec_native_component_ports as native
import cec_field_coupling as field
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track


def fixture(turn=0,back=False,mode=None):
    b=_board([(5,5,'RENAMED'),(17,5,'RENAMED'),(25,25,'RENAMED')]);b.SetCopperLayerCount(6)
    via_ids=[]
    for x in (5,15):
        if mode=='no_bridge' and x==15:continue
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(x,5));v.SetWidth(600000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(0,2);v.SetNet(b.FindNet('RENAMED'));b.Add(v)
        via_ids.append(force._uid(v))
    t=track(b,'RENAMED',(14,5),(15,5));t.SetLayer(6)
    track(b,'RENAMED',(15,5),(17,5))
    target=next(p for f in b.GetFootprints() for p in f.Pads() if tuple(p.GetPosition())==(17000000,5000000))
    if mode=='multi_surface':target.SetLayerSet(pcbnew.LSET.AllCuMask())
    if mode=='npth':target.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    origin=pcbnew.VECTOR2I(0,0)
    for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:
        if back:item.Flip(origin,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        item.Rotate(origin,pcbnew.EDA_ANGLE(turn*90,pcbnew.DEGREES_T))
    first=next(v for v in b.GetTracks() if force._uid(v)==via_ids[0])
    return b,target,tuple(first.GetPosition()),tuple(t.GetStart()),int(t.GetLayer())


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_same_component_crossface_smd_is_kept_single_surface(turn,back):
    b,target,start,end,face=fixture(turn,back);before=field._field_snapshot_inventory(b)
    old,_=schedule.retained_component_pairs(b,'RENAMED',start,end,face,[0,2,6,8],
        ordinary_nets={'RENAMED'},deadline=time.monotonic()+3.,allow_same_face_smd_ports=True)
    assert all(force._uid(target) not in p['native_uuids'] for q in old for p in q)
    pairs,proof=schedule.retained_component_pairs(b,'RENAMED',start,end,face,[0,2,6,8],
        ordinary_nets={'RENAMED'},deadline=time.monotonic()+3.,allow_connected_surface_smd_ports=True)
    ports=[p for q in pairs for p in q if force._uid(target) in p['native_uuids']]
    assert ports and proof['different_face_surface_access_requires_real_component_barrel']
    surface=list(map(int,target.GetLayerSet().CuStack()));assert len(surface)==1
    assert all(p['layers']==surface and not p['actual_retained_plated']
        and p['actual_retained_surface_smd_launch'] and p['actual_component_through_access_uuids'] for p in ports)
    assert field._field_snapshot_inventory(b)==before
    assert not proof['new_barrel_or_current_credit'] and not proof['release_authority']


@pytest.mark.parametrize('mode',['no_bridge','multi_surface','npth'])
def test_surface_or_coordinate_labels_without_native_plated_connection_are_not_access(mode):
    b,target,start,end,face=fixture(mode=mode)
    pairs,_=schedule.retained_component_pairs(b,'RENAMED',start,end,face,[0,2,6,8],
        ordinary_nets={'RENAMED'},deadline=time.monotonic()+3.,allow_connected_surface_smd_ports=True)
    assert all(force._uid(target) not in p['native_uuids'] for q in pairs for p in q)


def test_native_departure_ranking_receives_the_actual_width_clearance_and_local_shape_predicate(monkeypatch):
    b,target,start,end,face=fixture();calls=[];guard=lambda *a:True
    def rank(board,net,rows,**kw):
        calls.append(kw);return list(reversed(rows)),dict(dispatch_test_only=True)
    monkeypatch.setattr(native,'rank_by_native_egress',rank)
    pairs,proof=schedule.retained_component_pairs(b,'RENAMED',start,end,face,[0,2,6,8],
        ordinary_nets={'RENAMED'},deadline=time.monotonic()+3.,allow_connected_surface_smd_ports=True,
        rank_native_departures=True,clearance_nm=250000,source_width_nm=210000,planar_guard=guard)
    assert pairs and len(calls)==1 and calls[0]['clearance_nm']==250000
    assert calls[0]['width_for_layer'](face)==210000 and calls[0]['planar_guard'] is guard
    assert proof['actual_native_departure_ranking']['dispatch_test_only']


@pytest.mark.parametrize('flag',[1,None,'yes'])
@pytest.mark.parametrize('name',['allow_connected_surface_smd_ports','rank_native_departures'])
def test_access_modes_are_explicit_booleans(name,flag):
    b,target,start,end,face=fixture()
    with pytest.raises(ValueError):schedule.retained_component_pairs(b,'RENAMED',start,end,face,[0,2,6,8],
        ordinary_nets={'RENAMED'},deadline=time.monotonic()+3.,**{name:flag})


def test_departure_ranking_cannot_guess_a_width_from_another_track():
    b,target,start,end,face=fixture()
    with pytest.raises(ValueError):schedule.retained_component_pairs(b,'RENAMED',start,end,face,[0,2,6,8],
        ordinary_nets={'RENAMED'},deadline=time.monotonic()+3.,rank_native_departures=True,clearance_nm=200000)
