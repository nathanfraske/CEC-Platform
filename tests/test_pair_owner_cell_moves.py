from types import SimpleNamespace
from unittest.mock import patch
import math
import cec_pcb
import cec_synth_pipeline as s

def test_rotates_owned_bypass_not_unrelated_passive_and_keeps_owner_pivot():
    c=SimpleNamespace(P={'DEVICE':(10,10,0),'BYPASS':(11,10,90),'OTHER':(20,10,0)},back_refs=())
    evidence={'critical_pair_refused':[{'refused':'no common lane order',
              'endpoint_stations':[{'physical_refs':['DEVICE']}]}]}
    with patch.object(cec_pcb,'local_pads',return_value={'1':(0,0),'2':(1,0),'3':(0,1)}):
        moves=s._route_feedback_owner_cell_moves(c,evidence,dict.fromkeys(c.P),
            {'DEVICE':('DEVICE','BYPASS')},{'BYPASS':('DEVICE','1')})
        assert len(moves)==3
        for m in moves:
            assert set(m['placements'])=={'DEVICE','BYPASS'}
            assert m['placements']['DEVICE'][:2]==(10,10)
            assert math.isclose(math.dist(m['placements']['DEVICE'][:2],m['placements']['BYPASS'][:2]),1)
        assert not s._route_feedback_owner_cell_moves(c,evidence,dict.fromkeys(c.P),
            {'DEVICE':('DEVICE','BYPASS')},{'BYPASS':('DEVICE','1')},immovable={'BYPASS'})


def test_prelegalization_is_bounded_preserves_fixed_and_carries_full_macro():
    c=SimpleNamespace(P={'DEVICE':(10,10,0),'NEIGHBOR':(11,10,0)},back_refs=())
    move={'ref':'DEVICE','placements':{'DEVICE':(11,10,90)},'kind':'rotation'}
    poses={'DEVICE':(11,10,90),'NEIGHBOR':(12,10,0)}
    with patch.object(s,'_overlap_pairs',side_effect=[set(),{('DEVICE','NEIGHBOR')}]), \
         patch.object(s,'_placement_bounded_macro_legalizations',return_value=[(poses,['NEIGHBOR'],'macro_window')]) as legalize:
        output=s._route_feedback_legalized_moves(c,[move],{}, {},max_moves=1)
        assert output[0]['placements']==poses
        assert output[0]['source_kind']=='rotation'
        assert legalize.call_args.kwargs['max_variants']==1
    with patch.object(s,'_overlap_pairs',return_value=set()), \
         patch.object(s,'_placement_bounded_macro_legalizations') as legalize:
        assert s._route_feedback_legalized_moves(c,[move],{}, {},immovable={'DEVICE'})==[]
        assert s._route_feedback_legalized_moves(c,[move],{}, {},max_moves=0)==[]
        legalize.assert_not_called()


def test_rotated_cell_translation_uses_satellite_geometry_and_preserves_pitch():
    c=SimpleNamespace(P={'DEVICE':(10,10,0),'BYPASS':(12,10,0),'OBSTACLE':(10,10,0)},
                      back_refs=(), W=30,H=30)
    move={'ref':'DEVICE','placements':{r:c.P[r] for r in ('DEVICE','BYPASS')},
          'kind':'rotation','budget_group':'orientation'}
    def bbox(comp,x,y,rot):return x-.5,x+.5,y-.5,y+.5
    with patch.object(cec_pcb,'courtyard_bbox',side_effect=bbox):
        moves=s._route_feedback_cell_translation_moves(c,[move],dict.fromkeys(c.P),radius_mm=3,sites_per_move=3)
    assert 0<len(moves)<=3
    for row in moves:
        a,b=row['placements']['DEVICE'],row['placements']['BYPASS']
        assert math.isclose(b[0]-a[0],2) and a[1]==b[1]
        assert abs(a[0]-10)<=3 and abs(a[1]-10)<=3
        assert math.dist(a[:2],(10,10))>1


def test_large_module_follower_is_local_to_pin_not_package_origin():
    c=SimpleNamespace(P={'MODULE':(10,10,0),'BYPASS':(21,10,0),'REMOTE':(29,10,0)},back_refs=())
    with patch.object(cec_pcb,'pad_global',return_value=(20,10)):
        groups=s._route_local_follower_groups(c,
            {'BYPASS':('MODULE','42'),'REMOTE':('MODULE','42')},set(),{},max_distance_mm=2)
    assert groups=={'MODULE':('MODULE','BYPASS')}
