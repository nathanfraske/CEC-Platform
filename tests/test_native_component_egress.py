"""Scheduling must prefer real exits without granting routing authority."""
import time

import pcbnew
import pytest

import cec_force_current as force
import cec_measurement_leaf as leaf
import cec_native_component_ports as ports
from test_measurement_leaf import fixture


def boundary(item, layers=None):
    return dict(at_nm=list(item.GetPosition()), native_uuids=[force._uid(item)],
        layers=list(layers or [int(item.GetLayer())]))


def menu(name='renamed', quarter=0):
    board, free, boxed, _, xy = fixture(name, quarter)
    foreign = pcbnew.NETINFO_ITEM(board, 'independent_foreign'); board.Add(foreign)
    for a,b in [((18,9.5),(22,9.5)), ((18,10.5),(22,10.5))]:
        track = pcbnew.PCB_TRACK(board); track.SetStart(xy(a)); track.SetEnd(xy(b))
        track.SetWidth(200000); track.SetLayer(pcbnew.F_Cu); track.SetNet(foreign)
        board.Add(track)
    fp=pcbnew.FOOTPRINT(board); fp.SetReference('OTHER_ISLAND'); board.Add(fp)
    target=pcbnew.PAD(fp); target.SetNumber('1'); target.SetShape(pcbnew.PAD_SHAPE_RECT)
    target.SetAttribute(pcbnew.PAD_ATTRIB_SMD); target.SetLayerSet(pcbnew.PAD.SMDMask())
    target.SetSize(pcbnew.VECTOR2I_MM(.5,.5)); target.SetPosition(xy((25,20)))
    target.SetNetCode(free.GetNetCode()); fp.Add(target)
    return board, [(boundary(boxed),boundary(target)), (boundary(free),boundary(target))]


def rank(board, rows, name='renamed', **kwargs):
    options=dict(route_layers=(int(pcbnew.F_Cu),), width_for_layer=lambda _:1000000,
        clearance_nm=200000,deadline=time.monotonic()+2.)
    options.update(kwargs)
    return ports.rank_by_native_egress(board,name,rows,**options)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('name',['renamed','/unrelated/positive_bus'])
def test_same_native_component_free_exit_outranks_closest_boxed_port(quarter,name):
    board, rows=menu(name,quarter); before=leaf._binding(board)
    ordered, proof=rank(board,rows,name)
    assert ordered == [rows[1],rows[0]]
    assert proof['complete'] and proof['ordered_original_indices']==[1,0]
    assert proof['all_pairs_retained'] and not proof['no_path_proof']
    assert not proof['release_authority'] and not proof['routing_admitted']
    assert proof['width_by_layer_nm']=={int(pcbnew.F_Cu):1000000}
    assert proof['clearance_nm']==200000
    boxed=next(p for p in proof['endpoints'] if p['native_endpoint']==rows[0][0])
    assert boxed['clear_faces']==[] and boxed['complete']
    assert before==leaf._binding(board) and not proof['board_mutated']


def test_expired_lease_retains_every_pair_as_unknown_not_no_path():
    board,rows=menu(); before=leaf._binding(board)
    ordered,proof=rank(board,rows,deadline=time.monotonic()-1.)
    assert ordered==rows and proof['examined_rays']==0
    assert not proof['complete'] and all(not p['complete'] for p in proof['endpoints'])
    assert proof['all_pairs_retained'] and not proof['no_path_proof']
    assert before==leaf._binding(board)


def test_failed_samples_are_not_deleted_or_treated_as_complete_route(monkeypatch):
    board,rows=menu(); before=leaf._binding(board)
    monkeypatch.setattr(ports.fr,'_tap_foreign_clear',lambda *a,**kw:False)
    ordered,proof=rank(board,rows)
    assert ordered==rows and proof['complete']
    assert all(p['clear_faces']==[] for p in proof['endpoints'])
    assert not proof['no_path_proof'] and not proof['routing_admitted']
    assert before==leaf._binding(board)


def test_big_land_interior_does_not_count_as_real_egress():
    board,rows=menu()
    target_uid=rows[0][1]['native_uuids'][0]
    target=next(p for fp in board.GetFootprints() for p in fp.Pads()
        if force._uid(p)==target_uid)
    target.SetSize(pcbnew.VECTOR2I_MM(6.,6.))
    ordered,proof=rank(board,rows,reach_nm=200000)
    node=next(p for p in proof['endpoints'] if p['native_endpoint']==rows[0][1])
    assert node['complete'] and node['clear_faces']==[]
    assert proof['all_pairs_retained'] and not proof['no_path_proof']


@pytest.mark.parametrize('fault',['back_face','missing_seed','wrong_net','off_seed','float_xy'])
def test_forged_port_geometry_and_layer_access_are_rejected(fault):
    board,rows=menu(); before=leaf._binding(board)
    endpoint=rows[0][0]
    if fault=='back_face': endpoint['layers'].append(int(pcbnew.B_Cu))
    elif fault=='missing_seed': endpoint['native_uuids']=['not-native']
    elif fault=='wrong_net': endpoint['native_uuids']=[]
    elif fault=='off_seed': endpoint['at_nm'][1]+=8000000
    else: endpoint['at_nm'][0]=float(endpoint['at_nm'][0])
    with pytest.raises(ValueError,match='native_egress'):
        rank(board,rows)
    assert before==leaf._binding(board)


def test_real_through_barrel_preserves_only_actual_faces_and_face_current_widths():
    board,pad,_,_,xy=fixture('native_barrel')
    via=pcbnew.PCB_VIA(board); via.SetPosition(xy((15,10)))
    via.SetWidth(600000); via.SetDrill(300000); via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu); via.SetNetCode(pad.GetNetCode()); board.Add(via)
    faces=[int(l) for l in board.GetEnabledLayers().CuStack()]
    rows=[(boundary(via,faces),boundary(pad))]; before=leaf._binding(board)
    widths={int(pcbnew.F_Cu):200000,int(pcbnew.B_Cu):1000000}
    ordered,proof=rank(board,rows,'native_barrel',route_layers=tuple(widths),
        width_for_layer=lambda l:widths[l])
    node=proof['endpoints'][0]
    assert set(node['clear_faces'])==set(widths)
    assert {s['layer']:s['width_nm'] for s in node['native_departures']}==widths
    assert ordered==rows and before==leaf._binding(board)
    assert not proof['routing_admitted'] and not proof['release_authority']


def test_caller_capture_or_interference_guard_is_applied_at_exact_width():
    board,rows=menu(); before=leaf._binding(board); calls=[]
    def guard(a,b,w,l):
        calls.append((tuple(a),tuple(b),w,l)); return False
    ordered,proof=rank(board,rows,planar_guard=guard)
    assert calls and {c[2] for c in calls}=={1000000}
    assert ordered==rows and all(not p['clear_faces'] for p in proof['endpoints'])
    assert not proof['no_path_proof'] and before==leaf._binding(board)


@pytest.mark.parametrize('options',[
    {'reach_nm':True},{'reach_nm':99999},{'reach_nm':4000001},
    {'clearance_nm':True},{'clearance_nm':-1},
    {'deadline':float('nan')},{'deadline':float('inf')},
    {'deadline':'too_far'}, {'route_layers':(999,)},
    {'route_layers':(int(pcbnew.F_Cu),int(pcbnew.F_Cu))},
    {'width_for_layer':lambda _:0},{'width_for_layer':lambda _:100000.5},
    {'width_for_layer':lambda _:True},{'planar_guard':True},
])
def test_invalid_or_unbounded_egress_policy_fails_closed(options):
    board,rows=menu(); before=leaf._binding(board)
    if options.get('deadline')=='too_far':
        options=dict(options,deadline=time.monotonic()+100.)
    with pytest.raises(ValueError): rank(board,rows,**options)
    assert before==leaf._binding(board)


@pytest.mark.parametrize('floor',['width','clearance'])
def test_native_absolute_floors_are_not_waived(floor):
    board,rows=menu(); before=None
    if floor=='width': board.GetDesignSettings().m_TrackMinWidth=1100000
    else: board.GetDesignSettings().m_MinClearance=250000
    before=leaf._binding(board)
    with pytest.raises(ValueError): rank(board,rows)
    assert before==leaf._binding(board)


def test_exact_one_nanometre_alias_is_retained_not_merged():
    board,pad,anchor,tracks,_=fixture()
    at=list(anchor.GetPosition()); alias=dict(at_nm=[at[0]-1,at[1]],
        layers=[int(pcbnew.F_Cu)],native_uuids=[force._uid(tracks[-1])])
    rows=[(boundary(anchor),boundary(pad)),(alias,boundary(pad))]
    ordered,proof=rank(board,rows,'ordinary_name',width_for_layer=lambda _:200000)
    assert len(proof['endpoints'])==3 and len(ordered)==2
    assert {id(p) for p in ordered}=={id(p) for p in rows}
    assert proof['all_pairs_retained']
