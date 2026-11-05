"""Comparator clearance proposals must rotate the complete local bypass cell."""
from types import SimpleNamespace

import pytest

import cec_pcb
import cec_synth_pipeline as synth
from cec_placement_search_domain import rigid_cell_transform


@pytest.mark.parametrize('base_angle',[0,90,180,270])
def test_detection_grid_preserves_rigid_follower_pose(monkeypatch,base_angle):
    candidate=SimpleNamespace(P={'driver':(40.,20.,0.),
        'comparator':(10.,20.,base_angle),'bypass':(12.,21.,30.)},
        W=80,H=60,back_refs=())
    evidence={'detection_cell':{'ok':False,'violations':[
        ['comparator','driver','/renamed_detector',30.]]},
        'decoupler':{'details':[{'owner_ref':'comparator','cap_ref':'bypass','status':'assigned'}]}}
    monkeypatch.setattr(synth,'_overlap_pairs',lambda *args,**kwargs:set())
    monkeypatch.setattr(cec_pcb,'courtyard_bbox',lambda lib,x,y,angle,**kwargs:(x-.1,x+.1,y-.1,y+.1))
    moves=synth._placement_craft_move_specs(candidate,evidence,
        comps={ref:'synthetic' for ref in candidate.P},required_stages=['detection_cell_placement'])
    rotated=[m for m in moves if m['kind']=='detection_cell_macro_clearance_grid'
             and m['placements']['comparator'][2]!=base_angle]
    assert rotated
    for move in rotated:
        x,y,angle=move['placements']['comparator']
        expected=rigid_cell_transform({ref:candidate.P[ref] for ref in ('comparator','bypass')},
            'comparator',angle-base_angle,(x-10.,y-20.))
        assert move['placements']['bypass']==pytest.approx(expected['bypass'])


def test_fixed_bypass_prevents_incomplete_detector_cell_move():
    candidate=SimpleNamespace(P={'driver':(40.,20.,0.),
        'comparator':(10.,20.,0.),'bypass':(12.,21.,0.)})
    evidence={'detection_cell':{'ok':False,'violations':[
        ['comparator','driver','/renamed_detector',30.]]},
        'decoupler':{'details':[{'owner_ref':'comparator','cap_ref':'bypass','status':'assigned'}]}}
    assert synth._placement_craft_move_specs(candidate,evidence,immovable=['bypass'],
        required_stages=['detection_cell_placement'])==[]
