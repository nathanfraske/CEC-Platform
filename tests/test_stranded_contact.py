import math
from types import SimpleNamespace

from cec_cell_packing import contact_translation_sites
import cec_synth_pipeline as synth


def test_goal_directed_contact_includes_interior_obstacle_boundary():
    sites = contact_translation_sites([(-.5,-.5,.5,.5)], bounds=(1,1,19,19),
        obstacles=[(9,9,11,11)], preferred_origin=(10,10), clearance=.1, max_sites=1)
    assert len(sites) == 1
    assert abs(math.dist(sites[0], (10,10))-1.600001) < 1e-6
    assert 1 < sites[0][0] < 19 and 1 < sites[0][1] < 19


def test_secondary_stranded_improvement_breaks_tie_without_changing_hard_priority():
    def evidence(second, violations=2):
        return {"stranded": {"details": [{"ref":"FIRST", "distance_mm":36.5},
                                         {"ref":"SECOND", "distance_mm":second}],
                            "violations":[("FIRST",36.5),("SECOND",second)][:violations]}}
    before, after = synth.placement_craft_key(evidence(29.8)), synth.placement_craft_key(evidence(25.7))
    assert before[:-1] == after[:-1]
    assert after < before
    assert synth.placement_craft_key(evidence(40,violations=1)) < after
    assert synth.placement_craft_key(evidence(29.799999)) == before


def test_contact_repair_is_geometry_driven_and_preserves_fixed_endpoint(monkeypatch):
    import cec_pcb
    monkeypatch.setattr(cec_pcb, "courtyard_bbox",
                        lambda comp,x,y,r,**kw: (x-.5,x+.5,y-.5,y+.5))
    candidate = SimpleNamespace(P={"FILTER":(2,2,0), "ADC":(35,35,0),
                                   "OBSTACLE":(34,34,0)}, W=40.,H=40.,back_refs=())
    evidence = {"stranded":{"details":[{"ref":"FILTER","nearest_ref":"ADC",
                                            "limit_mm":22.,"distance_mm":44.} ]}}
    moves = synth._placement_stranded_contact_moves(candidate,evidence,
                                                   {r:{} for r in candidate.P},immovable={"ADC"})
    assert moves and all(m["ref"] == "FILTER" for m in moves)
    first = moves[0]["position"]
    assert math.dist(first[:2],candidate.P["ADC"][:2]) < 2
    assert not synth._overlap_pairs(dict(candidate.P,FILTER=first),
                                    {r:{} for r in candidate.P})


def test_other_connected_peer_can_move_when_nearest_pair_is_fixed(monkeypatch):
    import cec_pcb
    monkeypatch.setattr(cec_pcb, 'courtyard_bbox',
                        lambda comp,x,y,r,**kw:(x-.5,x+.5,y-.5,y+.5))
    candidate=SimpleNamespace(P={'BANK_A':(5,5,0),'BANK_B':(35,5,0),
        'LINK':(38,10,90),'UNCONNECTED':(20,20,0)},W=45.,H=30.,back_refs=())
    evidence={'stranded':{'details':[dict(ref='BANK_A',nearest_ref='BANK_B',limit_mm=22.,
        connected_peers=[dict(ref='BANK_B',shared_nets=['RESERVOIR']),
                         dict(ref='LINK',shared_nets=['RESERVOIR']),
                         dict(ref='UNCONNECTED',shared_nets=[])])]}}
    moves=synth._placement_stranded_contact_moves(candidate,evidence,
        {r:{} for r in candidate.P},immovable={'BANK_A','BANK_B'})
    assert moves and {m['ref'] for m in moves}=={'LINK'}
    assert all(m['owner_ref']=='BANK_A' for m in moves)
    assert all(math.dist(m['position'][:2],candidate.P['BANK_A'][:2])<22 for m in moves)
