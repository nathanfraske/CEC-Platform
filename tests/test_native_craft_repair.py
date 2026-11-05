from types import SimpleNamespace
from unittest.mock import patch
import pytest
import cec_placement_geometry as geo
import cec_synth_pipeline as synth


def fault(a='DEVICE',b='BYPASS',kind='clearance'):
    return {'type':kind,'domain':'pad_copper', 'members':[
        {'ref':a,'pad':'1','net':'A'}, {'ref':b,'pad':'2','net':'B'}]}


def test_projection_preserves_native_members_and_fails_closed():
    native=fault();native['items']=native.pop('members')
    projected=geo.craft_projection({'ok':False,'source_unchanged':True,'findings':[native]})
    assert not projected['ok'] and projected['violations'][0]['members'][0]['ref']=='DEVICE'
    assert not geo.craft_projection({'ok':False,'findings':[]})['ok']
    assert geo.craft_projection({'ok':True,'source_unchanged':True,'findings':[]})['ok']


def test_fault_identity_does_not_depend_on_native_uuid_or_member_order():
    a=fault();b=fault();b['members'].reverse()
    b['members'][0]['uuid']='new normalized id'
    assert geo.craft_conflict_keys({'violations':[a]})==geo.craft_conflict_keys({'violations':[b]})
    assert geo.craft_conflict_keys({'violations':[a]})!=geo.craft_conflict_keys({'violations':[fault(kind='shorting_items')]})


def test_native_moves_keep_cells_rigid_and_fixed_hardware_immovable():
    poses={'DEVICE':(1,1,90),'BYPASS':(2,1,180),'PEER':(3,1,0)}
    moves=geo.clearance_move_specs({'violations':[fault('BYPASS','PEER')]},poses,
        owner_by_cap={'BYPASS':'DEVICE'},fixed={'PEER'},max_specs=10)
    assert len(moves)==10
    for move in moves:
        assert set(move['placements'])=={'DEVICE','BYPASS'}
        a,b=move['placements']['DEVICE'],move['placements']['BYPASS']
        assert b[0]-a[0]==pytest.approx(1) and b[1]-a[1]==pytest.approx(0)
        assert a[2]==90 and b[2]==180
    assert geo.clearance_move_specs({'violations':[fault('BYPASS','PEER')]},poses,
        owner_by_cap={'BYPASS':'DEVICE'},fixed={'PEER','DEVICE'})==[]


def test_same_footprint_fault_cannot_be_repaired_by_moving_the_footprint():
    assert not geo.clearance_move_specs({'violations':[fault('DEVICE','DEVICE')]},{'DEVICE':(0,0,0)})


def test_internal_cell_collision_reseats_member_not_the_whole_unchanged_cell():
    poses={'DEVICE':(1,1,90),'BYPASS':(2,1,180)}
    moves=geo.clearance_move_specs({'violations':[fault()]},poses,
        owner_by_cap={'BYPASS':'DEVICE'},fixed={'DEVICE'},max_specs=8)
    assert len(moves)==8 and all(set(row['placements'])=={'BYPASS'} for row in moves)


def test_native_geometry_is_a_craft_blocker_not_a_route_only_deferral():
    evidence={'ok':False,'native_geometry':{'ok':False,'violations':[fault()]}}
    assert synth.placement_craft_key(evidence)>synth.placement_craft_key({'ok':True})
    assert not synth.placement_craft_admission(evidence,allow_route_access_repair=True)['ok']
    cert=synth.placement_craft_blocker_certificate(evidence)
    assert 'native_pad_clearance' in cert['required_stages'] and cert['upstream_action_required']
    candidate=SimpleNamespace(P={'DEVICE':(0,0,0),'BYPASS':(2,0,0)})
    moves=synth._placement_craft_move_specs(candidate,evidence,optimize_clean_margin=False)
    assert any(row['kind']=='native_pad_clearance_reseat' for row in moves)


def test_trial_cannot_trade_better_decoupling_for_a_new_pad_fault():
    payload={'path':'/unused/proposal.kicad_pcb','cfg':None,'candidate':None,
             'baseline_geometry':{'ok':True,'violations':[]}}
    with patch.object(synth,'materialize'),patch.object(synth,'placement_craft_evidence',
        return_value={'ok':False,'native_geometry':{'ok':False,'violations':[fault()]}}):
        result=synth._placement_craft_trial_worker(payload)
    assert not result['ok']
    assert result['error_kind'] == 'native_geometry_regression'
    assert result['introduced_native_conflicts']


@pytest.mark.parametrize('bad', ['connected','existing_copper_unchanged','placement_unchanged','current_width','score'])
def test_filled_authority_repair_retains_input_on_any_gate_failure(tmp_path,bad):
    board=tmp_path/'board.kicad_pcb';board.write_text('input')
    proof={'POWER':{'available':True,'connected':False,'domain':{'complete':True}}}
    def route(path,*args,**kwargs):
        from pathlib import Path
        Path(path).write_text('trial')
        row={'connected':True,'existing_copper_unchanged':True,'placement_unchanged':True,'current_width':{'ok':True}}
        if bad=='current_width':row[bad]={'ok':False}
        elif bad!='score':row[bad]=False
        return row
    with patch('cec_fr.copy_project_sidecars'),patch.object(synth,'_score_priority_power_artifact_isolated'), \
         patch.object(synth,'_route_priority_current_domain_isolated',side_effect=route), \
         patch.object(synth,'_route_score_admission',return_value={'accepted':bad!='score'}):
        result=synth._repair_filled_current_authority(str(board),proof)
    assert not result['changed'] and board.read_text()=='input'


def test_filled_authority_repairs_only_exact_open_complete_domains_once(tmp_path):
    board=tmp_path/'board.kicad_pcb';board.write_text('input')
    proofs={'OPEN':{'available':True,'connected':False,'domain':{'complete':True}},
            'CLOSED':{'available':True,'connected':True,'domain':{'complete':True}},
            'UNKNOWN':{'available':False,'connected':False}}
    def route(path,net,**kwargs):
        from pathlib import Path
        assert net=='OPEN'
        Path(path).write_text('admitted')
        return {'connected':True,'existing_copper_unchanged':True,'placement_unchanged':True,'current_width':{'ok':True}}
    with patch('cec_fr.copy_project_sidecars'),patch.object(synth,'_score_priority_power_artifact_isolated'), \
         patch.object(synth,'_route_priority_current_domain_isolated',side_effect=route) as worker, \
         patch.object(synth,'_route_score_admission',return_value={'accepted':True}):
        result=synth._repair_filled_current_authority(str(board),proofs)
    assert result['changed'] and board.read_text()=='admitted' and worker.call_count==1


def test_search_projection_keeps_native_layer_attempt_status():
    from cec_probe_evidence import compact_pair_search_trace
    data={'layer_attempts':[{'layer':'In2.Cu','allow_layer_transitions':False,
          'elapsed_s':.5,'status':'deferred_budget','reason':'deadline'}]}
    row=compact_pair_search_trace(data)[0]
    assert row['layer']=='In2.Cu' and row['status']=='deferred_budget'
    assert row['allow_layer_transitions'] is False and row['elapsed_s']==.5
