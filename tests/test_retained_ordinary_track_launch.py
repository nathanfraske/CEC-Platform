"""An existing ordinary conductor is a usable exit, not a guessed barrel."""
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_native_route_schedule as schedule
import cec_native_track_ports as tracks
from test_lastmile import _board
from test_field_proposals import track


def fixture(turn=0,back=False,width=.2):
    b=_board([(5,5,'/RENAMED'),(25,5,'/RENAMED'),(5,25,'/RENAMED')])
    b.SetCopperLayerCount(6)
    left=track(b,'/RENAMED',(5,5),(5,12),width=width)
    right=track(b,'/RENAMED',(25,5),(25,12))
    separate=track(b,'/RENAMED',(5,25),(25,25))
    origin=pcbnew.VECTOR2I(0,0)
    for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:
        if back:item.Flip(origin,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        item.Rotate(origin,pcbnew.EDA_ANGLE(turn*90,pcbnew.DEGREES_T))
    return b,left,right,separate


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_same_component_track_ports_are_single_face_and_read_only(turn,back):
    b,left,right,separate=fixture(turn,back);before=field._field_snapshot_inventory(b)
    start,end=tuple(left.GetStart()),tuple(right.GetStart());face=int(left.GetLayer())
    legacy,_=schedule.retained_component_pairs(b,'/RENAMED',start,end,face,[0,2,6,8],
        ordinary_nets={'/RENAMED'},deadline=time.monotonic()+3.)
    assert not any(p.get('actual_retained_track_contact') for q in legacy for p in q)
    pairs,proof=schedule.retained_component_pairs(b,'/RENAMED',start,end,face,[0,2,6,8],
        ordinary_nets={'/RENAMED'},deadline=time.monotonic()+3.,
        allow_retained_track_ports=True,source_width_nm=200000)
    ports=[p for q in pairs for p in q if p['actual_retained_track_contact']]
    assert ports and proof['retained_track_contacts_requested']
    live={force._uid(t):t for t in b.GetTracks()}
    for p in ports:
        assert not p['actual_retained_plated'] and p['layers']==[face]
        assert any(u in live and tracks.on_centerline(live[u],p['at_nm']) for u in p['native_uuids'])
        assert force._uid(separate) not in p['native_uuids']
    assert field._field_snapshot_inventory(b)==before
    assert not proof['release_authority'] and not proof['new_barrel_or_current_credit']


def test_narrow_retained_track_does_not_grant_a_wider_attachment():
    b,left,right,_=fixture(width=.15)
    pairs,_=schedule.retained_component_pairs(b,'/RENAMED',tuple(left.GetStart()),tuple(right.GetStart()),0,[0,2,6,8],
        ordinary_nets={'/RENAMED'},deadline=time.monotonic()+3.,
        allow_retained_track_ports=True,source_width_nm=200000)
    assert all(force._uid(left) not in p['native_uuids'] for q in pairs for p in q
        if p['actual_retained_track_contact'])


@pytest.mark.parametrize('fault',[None,True,0,199999.5])
def test_track_launch_cannot_guess_or_forge_source_width(fault):
    b,left,right,_=fixture()
    with pytest.raises(ValueError):schedule.retained_component_pairs(b,'/RENAMED',
        tuple(left.GetStart()),tuple(right.GetStart()),0,[0,2,6,8],ordinary_nets={'/RENAMED'},
        deadline=time.monotonic()+3.,allow_retained_track_ports=True,source_width_nm=fault)


def test_positive_ordinary_authority_still_required():
    b,left,right,_=fixture()
    with pytest.raises(ValueError):schedule.retained_component_pairs(b,'/RENAMED',
        tuple(left.GetStart()),tuple(right.GetStart()),0,[0,2,6,8],ordinary_nets=set(),
        deadline=time.monotonic()+3.,allow_retained_track_ports=True,source_width_nm=200000)
