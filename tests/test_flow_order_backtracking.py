from types import SimpleNamespace
from unittest.mock import patch
import pytest
import cec_precision_route as route
import cec_pair_native_layer_order as native_layers


@pytest.fixture(autouse=True)
def isolate_order_units_from_native_endpoint_inventory(monkeypatch):
    # This module deliberately uses a minimal non-SWIG Board to exercise
    # transaction ordering and rollback. Native source-layer selection has
    # its own real pad/barrel/rotation/rollback integration regressions.
    # Preserve this unit's original one-layer search domain and assertions.
    monkeypatch.setattr(native_layers,'rank',lambda *a:[dict(layer='F.Cu')])

class Track:
    def __init__(self, name): self.m_Uuid=SimpleNamespace(AsString=lambda:name)

class Board:
    def __init__(self):self.tracks=[Track('protected'),Track('station-ties')]
    def GetTracks(self): return list(self.tracks)
    def Groups(self): return []
    def Delete(self,track): self.tracks.remove(track)

LEGS=[((0,0),(5,0),(0,.5),(5,.5)), ((5,2),(10,2),(5,2.5),(10,2.5))]

def test_failed_successor_retries_first_and_rolls_back_return_vias():
    board=Board();calls=[]
    legs=LEGS
    def attempt(_board,_pair,**kw):
        calls.append(kw['endpoints'])
        assert len(kw['avoid']) == (2 if len(calls) in (1,3) else 0)
        if len(calls)==2:
            board.tracks.append(Track('refused-ground-return'))
            return {'refused':'blocked by predecessor'}
        if len(calls)==3:
            assert [t.m_Uuid.AsString() for t in board.tracks]==['protected','station-ties']
        board.tracks.append(Track('signal-and-return-'+str(len(calls))))
        return {'length_mm':1,'segments':2,'coupled_len_mm':1}
    with patch.object(route,'_scheduled_flow_legs',return_value=[(0,legs[0],(2,)),(1,legs[1],(1,))]),patch.object(route,'route_coupled_pair',side_effect=attempt):
        result=route._route_flow_leg_orders(board,dict(name='PAIR',p='P',n='N'),legs,['CELL'])
    assert calls==[legs[0],legs[1],legs[1],legs[0]]
    assert result['flow_leg_order']==[2,1]
    assert len(result['flow_order_attempts'])==2
    assert result['length_mm']==2
    completed=result['flow_order_attempts'][0]['completed_leg_evidence']
    assert len(completed)==1 and completed[0]['leg']==1
    assert completed[0]['scope']=='inline-leg-only' and completed[0]['release_authority'] is False
    assert completed[0]['evidence']['segments']==2

def test_intrinsic_first_leg_failure_does_not_loop_and_cleans_all_new_copper():
    board=Board()
    def fail(*a,**kw):
        board.tracks.append(Track('ground'))
        return {'refused':'no pad escape'}
    with patch.object(route,'_scheduled_flow_legs',return_value=[(0,LEGS[0],(2,))]),patch.object(route,'route_coupled_pair',side_effect=fail) as call:
        result=route._route_flow_leg_orders(board,dict(name='PAIR',p='P',n='N'),LEGS[:1],['CELL'])
    assert call.call_count==1
    assert result['refused']
    assert [t.m_Uuid.AsString() for t in board.tracks]==['protected','station-ties']


def test_internal_future_surrogate_can_be_negotiated_only_as_complete_atomic_chain():
    board=Board();calls=[];external={'kind':'protected-power','label':'unchanged'}
    legs=[LEGS[0],((5,2),(30,2),(5,2.5),(30,2.5))]
    def attempt(_board,_pair,**kw):
        calls.append(kw)
        assert external in kw['avoid']
        if len(kw['avoid'])>1:
            board.tracks.append(Track('refused-return'))
            return {'refused':'prospective sibling launch blocks real escape'}
        if len(calls)==3:
            assert [t.m_Uuid.AsString() for t in board.tracks]==['protected','station-ties']
        board.tracks.append(Track('negotiated-'+str(len(calls))))
        return {'length_mm':1,'segments':2,'coupled_len_mm':1}
    with patch.object(route,'_scheduled_flow_legs',return_value=[(1,legs[1],(9,)),(0,legs[0],(1,))]), \
         patch.object(route,'route_coupled_pair',side_effect=attempt):
        result=route._route_flow_leg_orders(board,dict(name='PAIR',p='P',n='N'),legs,['CELL'],avoid=(external,),max_orders=3)
    assert len(calls)==4 and not result.get('refused')
    assert result['flow_leg_order']==[1,2]
    assert result['flow_order_attempts'][-1]['internal_reservation_policy']=='actual-copper-atomic'
    assert all(call['avoid']==(external,) for call in calls[2:])


def test_failed_negotiated_successor_rolls_back_entire_inline_chain():
    board=Board();calls=[]
    def attempt(_board,_pair,**kw):
        calls.append(kw);board.tracks.append(Track('new-'+str(len(calls))))
        if len(calls)!=3:return {'refused':'still blocked by real geometry'}
        return {'length_mm':1,'segments':2,'coupled_len_mm':1}
    with patch.object(route,'_scheduled_flow_legs',return_value=[(0,LEGS[0],(2,)),(1,LEGS[1],(1,))]), \
         patch.object(route,'route_coupled_pair',side_effect=attempt):
        result=route._route_flow_leg_orders(board,dict(name='PAIR',p='P',n='N'),LEGS,['CELL'],max_orders=3)
    assert len(calls)==4 and result['refused']
    assert [t.m_Uuid.AsString() for t in board.tracks]==['protected','station-ties']
