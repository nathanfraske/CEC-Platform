"""Source-named pickup direction must survive canonical and maze routing."""
import copy
import time

import pcbnew
import pytest

import cec_force_current as force
import cec_kelvin_departure as departure
import cec_measurement_terminal_route as route
from test_measurement_terminal_access import get
from test_measurement_terminal_route import fixture


def transform(board,points,quarter,back):
    pivot=pcbnew.VECTOR2I_MM(30,30)
    angle=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
    # Use native transformations for the independent authored path as well
    # as native lands; no test repeats the generator's direction formula.
    probes=[]
    for a,b in zip(points,points[1:]):
        t=pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b));probes.append(t)
    for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings(),*probes]:
        item.Rotate(pivot,angle)
        if back:item.Flip(pivot,True)
    return [tuple(probes[0].GetStart()),*[tuple(t.GetEnd()) for t in probes]]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_diagonal_contact_on_inner_half_is_refused_by_native_exit_heading(quarter,back):
    board,demand,root,pickup=fixture()
    points=transform(board,[(10000000,10000000),(11000000,9000000),
        (19000000,9000000),(20000000,10000000)],quarter,back)
    demand=next(d for d in get(board)['requests'] if d['pad_uuid']==force._uid(root))
    guard=route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+5)
    # Same-net isolation permits this path: the real failure is directional,
    # not a foreign-clearance or whole-net-pickup excuse.
    assert all(guard['planar'](a,b,200000,guard['layer']) for a,b in zip(points,points[1:]))
    assert not guard['clear'](points)
    assert not guard['operations']([['trk',a,b,200000,guard['layer']]
        for a,b in zip(points,points[1:])])
    assert guard['unchanged']()


@pytest.mark.parametrize('quarter',range(4))
def test_every_generated_direct_route_has_an_actual_perpendicular_inward_exit(quarter):
    board,demand,root,pickup=fixture(quarter)
    menu=route.menus(board,demand,width_nm=200000,timeout_s=3,max_choices=4)
    assert menu['ops'],menu
    peer=next(p for p in pickup.GetParentFootprint().Pads() if force._uid(p)!=force._uid(pickup))
    for ops in menu['ops']:
        tracks=[]
        for op in ops:
            t=pcbnew.PCB_TRACK(board);t.SetNet(root.GetNet());t.SetLayer(op[4])
            t.SetStart(pcbnew.VECTOR2I(*op[1]));t.SetEnd(pcbnew.VECTOR2I(*op[2]))
            t.SetWidth(op[3]);tracks.append(t)
        proof=departure.audit_pad_departures(pickup,peer.GetPosition(),tracks,
            inner_min_mm=.1,target_pads=[root],connectivity_pads=[root])
        assert proof['ok'],proof
        assert proof['departures'] and all(r['transverse_error_nm']<=1000 for r in proof['departures'])
    assert not menu['current_authority'] and not menu['release_authority']


@pytest.mark.parametrize('fault',['opposite_net','opposite_ref','pickup_pin','series','third_land'])
def test_missing_or_forged_direct_source_pair_never_gets_an_inward_aperture(fault):
    board,demand,root,pickup=fixture();demand=copy.deepcopy(demand)
    if fault=='opposite_net':demand['source_topology']['n']['anchor_net']='worker_guess'
    elif fault=='opposite_ref':demand['source_topology']['n']['anchor_ref']='worker_guess'
    elif fault=='pickup_pin':demand['source_topology']['p']['anchor_pad']='worker_guess'
    elif fault=='series':demand['source_topology']['p']['series']=[{'unproved':'filter'}]
    else:
        p=pcbnew.PAD(pickup.GetParentFootprint());p.SetNumber('unowned')
        pickup.GetParentFootprint().Add(p)
    with pytest.raises(ValueError,match='exact_source_two_land_direct_shunt_direction_required'):
        route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+5)


@pytest.mark.parametrize('quarter',range(4))
def test_retained_sibling_takeoff_uses_another_perpendicular_land_port(quarter):
    board,demand,root,pickup=fixture()
    sibling=pcbnew.PCB_TRACK(board);sibling.SetNet(root.GetNet());sibling.SetLayer(pcbnew.F_Cu)
    sibling.SetWidth(250000);sibling.SetStart(pcbnew.VECTOR2I_MM(19.85,10))
    sibling.SetEnd(pcbnew.VECTOR2I_MM(19.35,10.5));board.Add(sibling)
    transform(board,[(10000000,10000000),(20000000,10000000)],quarter,False)
    demand=next(d for d in get(board)['requests'] if d['pad_uuid']==force._uid(root))
    before=force._item_key(sibling)
    menu=route.menus(board,demand,width_nm=200000,timeout_s=3,max_choices=4)
    assert menu['ops'],menu
    guard=route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+5)
    assert all(guard['operations'](ops) for ops in menu['ops'])
    assert force._item_key(sibling)==before and guard['unchanged']()


@pytest.mark.parametrize('angle',[45,135,225,315])
@pytest.mark.parametrize('sibling_present',[False,True])
def test_diagonal_package_preserves_native_inward_takeoff_and_transverse_ports(angle,sibling_present):
    board,demand,root,pickup=fixture()
    if sibling_present:
        sibling=pcbnew.PCB_TRACK(board);sibling.SetNet(root.GetNet());sibling.SetLayer(pcbnew.F_Cu)
        sibling.SetWidth(250000);sibling.SetStart(pcbnew.VECTOR2I_MM(19.85,10))
        sibling.SetEnd(pcbnew.VECTOR2I_MM(19.35,10.5));board.Add(sibling)
    pivot=pcbnew.VECTOR2I_MM(30,30);rotation=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
    for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:item.Rotate(pivot,rotation)
    demand=next(d for d in get(board)['requests'] if d['pad_uuid']==force._uid(root))
    menu=route.menus(board,demand,width_nm=200000,timeout_s=3,max_choices=4)
    assert menu['ops'],menu
    guard=route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+5)
    assert all(guard['operations'](ops) for ops in menu['ops'])
    assert all(a[0]==b[0] or a[1]==b[1] or abs(a[0]-b[0])==abs(a[1]-b[1])
        for ops in menu['ops'] for _,a,b,_,_ in ops)
    assert guard['unchanged']() and not menu['current_authority']
