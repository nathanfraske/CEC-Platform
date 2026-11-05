"""The ideal reference must obey the same hard return-distance contract."""
import math
from types import SimpleNamespace
import pytest
import cec_synth_pipeline as synth
from cec_placement_search_domain import rotate_board_point


def solve(monkeypatch, *, turn=0, limit=2.0):
    def transform(p):
        x,y=rotate_board_point(p,(0,0),turn);return (x+37,y+22)
    class Item:
        def __init__(self,point,rotation=0):self.xy=transform(point);self.rotation=rotation+turn
        def GetPosition(self):return SimpleNamespace(x=round(self.xy[0]*1e6),y=round(self.xy[1]*1e6))
        def GetOrientationDegrees(self):return self.rotation
    owner=Item((0,0));cap=Item((-4,0),90)
    supply=Item((-.95,1.15));ground=Item((0,-1.15))
    cap_supply=Item((-4,.775));cap_ground=Item((-4,-.775))
    def box(points):
        p=[transform(point) for point in points]
        return (min(v[0] for v in p),max(v[0] for v in p),min(v[1] for v in p),max(v[1] for v in p))
    owner_box=box([(-1.5,-1.5),(1.5,1.5)])
    cap_box=box([(-4.65,-1.3),(-3.35,1.3)])
    monkeypatch.setattr(synth,'_footprint_courtyard_box',lambda item:owner_box if item is owner else cap_box)
    result=synth._decoupler_tangent_target(owner,cap,supply,cap_supply,[ground],cap_ground,
        ground_max_mm=limit)
    return result


@pytest.mark.parametrize('turn',[0,90,180,270])
def test_infeasible_reference_replaced_with_return_feasible_tangent(monkeypatch,turn):
    target=solve(monkeypatch,turn=turn)
    assert target['return_constrained'] and target['reference_feasible']
    assert target['unconstrained_best_loop']['ground_mm']>2.0
    assert target['best_loop']['ground_mm']<=2.0+1e-9
    assert all(row['ground_mm']<=2.0+1e-9 for row in target['candidates'])
    pose=target['best_supply']
    proximity=synth._decoupler_proximity_gate('GND',pose['supply_mm'],pose['ground_mm'],target,{})
    assert not proximity['bad']
    assert not synth._decoupler_return_gate('GND',pose['supply_mm'],pose['ground_mm'],target,ground_max_mm=2.0)['bad']
    assert synth._decoupler_return_gate('GND',pose['supply_mm'],2.00001,target,ground_max_mm=2.0)['bad']
    assert synth._decoupler_proximity_gate('GND',pose['supply_mm']+.25001,pose['ground_mm'],target,{})['bad']
    assert target['proximity_supply_mm']==pose['supply_mm']


def test_already_feasible_reference_is_bit_for_bit_unchanged(monkeypatch):
    old=solve(monkeypatch,limit=None)
    assert solve(monkeypatch,limit=20)==old


def test_no_feasible_reference_does_not_turn_into_pass(monkeypatch):
    target=solve(monkeypatch,limit=.001)
    assert target['return_constrained'] and not target['reference_feasible']
    assert target['best_loop'] is None and target['candidates']==[]
    assert synth._decoupler_proximity_gate('GND',1,.001,target,{})['bad']


def test_shorter_ground_loop_cannot_waive_independent_supply_distance():
    target=dict(return_constrained=True,proximity_supply_mm=.8,
                best_supply=dict(supply_mm=.8,ground_mm=2.4),
                best_loop=dict(supply_mm=2.5,ground_mm=.3,loop_proxy_mm=2.8))
    gate=synth._decoupler_proximity_gate('GND',2.5,.3,target,{})
    assert gate['bad'] and gate['ideal_supply_mm']==.8


@pytest.mark.parametrize('limit',[0,-1,float('nan'),float('inf')])
def test_invalid_contract_refused(monkeypatch,limit):
    with pytest.raises(ValueError):solve(monkeypatch,limit=limit)
