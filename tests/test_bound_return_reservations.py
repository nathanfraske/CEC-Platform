"""Complete power geometry for proposals must match the measured authority."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
import cec_local_return_feedback as feedback
import cec_power_guard_geometry as geometry
import cec_synth_pipeline as synth
from test_local_return_feedback import fixture


def state_fixture(tmp_path):
    state = dict(placement_scope='complete', frozen_nets=['POWER'],
        corridors=[dict(net='POWER',layer='B.Cu',x0=8.,y0=8.,x1=12.,y1=10.2)],
        pours=[dict(net='POWER',layer='In2.Cu',polygon=[[8,10.2],[12,10.2],[12,16],[8,16]])])
    path = tmp_path / 'authority.json'
    encoded = json.dumps(state).encode()
    path.write_bytes(encoded)
    identity = dict(path=str(path),sha256=hashlib.sha256(encoded).hexdigest())
    positions,evidence,row,proof = fixture()
    proof['pad_center']['copper_admission']['blockers'][0]['rect_mm'] = [8,8,12,10.2]
    evidence['input_identity'] = dict(files={'config.params.pourfirst_state':identity})
    params = dict(pourfirst_state=str(path))
    return positions,evidence,params,state,path


def test_complete_projection_is_exactly_the_native_guard_projection(tmp_path):
    positions,evidence,params,state,path = state_fixture(tmp_path)
    result = feedback.bound_reservations(evidence,params)
    assert result['ok'] and result['rows'] == geometry.reservations(state)
    assert result['scope'] == 'proposal_geometry_only'
    original = copy.deepcopy((positions,evidence,params,state))
    sampled = feedback.move_specs(positions,evidence['decoupler']['details'])
    complete = feedback.move_specs(positions,evidence['decoupler']['details'],reservation_context=result)
    assert min(m['dy_mm'] for m in sampled if m['dy_mm'] > 0) < 1
    assert min(m['dy_mm'] for m in complete if m['dy_mm'] > 0) > 6
    assert {m['exit_basis'] for m in complete} == {'bound_reservation_union'}
    assert all(m['reservation_state_sha256']==result['state_sha256'] for m in complete)
    assert all(m['requires_native_requalification'] for m in complete)
    assert (positions,evidence,params,state) == original


@pytest.mark.parametrize('case', ['changed','missing','path','identity','unstable','incomplete','invalid'])
def test_stale_missing_or_incomplete_authority_never_claims_complete_coverage(tmp_path,case):
    positions,evidence,params,state,path = state_fixture(tmp_path)
    if case == 'changed': path.write_bytes(path.read_bytes()+b' ')
    elif case == 'missing': path.unlink()
    elif case == 'path': params['pourfirst_state'] = str(tmp_path/'other.json')
    elif case == 'identity': evidence.pop('input_identity')
    elif case == 'unstable': evidence['input_identity_after'] = {'sha256':'changed'}
    else:
        state['placement_scope'] = 'anchor-only' if case=='incomplete' else 'complete'
        if case=='invalid': state['pours'][0]['polygon'] = []
        encoded=json.dumps(state).encode();path.write_bytes(encoded)
        evidence['input_identity']['files']['config.params.pourfirst_state']['sha256']=hashlib.sha256(encoded).hexdigest()
    result=feedback.bound_reservations(evidence,params)
    assert not result['ok'] and not result['rows']
    assert feedback.move_specs(positions,evidence['decoupler']['details'],reservation_context=result) == feedback.move_specs(positions,evidence['decoupler']['details'])


def test_same_return_net_is_not_an_obstacle_but_other_layers_are(tmp_path):
    p,e,params,state,path=state_fixture(tmp_path)
    context=feedback.bound_reservations(e,params)
    baseline=feedback.move_specs(p,e['decoupler']['details'],reservation_context=context)
    context['rows'].append(dict(net='GND',layer='In1.Cu',x0=-100,y0=-100,x1=100,y1=100))
    assert feedback.move_specs(p,e['decoupler']['details'],reservation_context=context)==baseline
    context['rows'][-1]['net']='FOREIGN'
    assert not feedback.move_specs(p,e['decoupler']['details'],reservation_context=context)


def test_production_generator_dispatches_identity_bound_complete_set(tmp_path):
    p,e,params,state,path=state_fixture(tmp_path)
    moves=synth._placement_craft_move_specs(SimpleNamespace(P=p),e,
        required_stages=['return_path_placement'],policy_params=params)
    returns=[m for m in moves if m['kind']=='decoupler_ground_territory_reseat']
    assert returns and all(m['exit_basis']=='bound_reservation_union' for m in returns)


def test_no_failed_cells_do_not_read_power_files(monkeypatch):
    p,e,params=({'Q':(0,0,0)}, {'decoupler':{'details':[]}}, {'pourfirst_state':'absent'})
    monkeypatch.setattr(feedback,'bound_reservations',lambda *a:pytest.fail('unneeded IO'))
    synth._placement_craft_move_specs(SimpleNamespace(P=p),e,policy_params=params)


def test_complete_label_with_no_conductor_is_not_complete_guard_authority(tmp_path):
    p,e,params,state,path=state_fixture(tmp_path)
    state.update(frozen_nets=[],corridors=[],pours=[],vias=[])
    encoded=json.dumps(state).encode();path.write_bytes(encoded)
    e['input_identity']['files']['config.params.pourfirst_state']['sha256']=hashlib.sha256(encoded).hexdigest()
    result=feedback.bound_reservations(e,params)
    assert result['ok'] is False and result['reason']=='invalid_power_authority'
    assert 'complete frozen power authority is empty' in result['error']
    assert feedback.move_specs(p,e['decoupler']['details'],reservation_context=result)==feedback.move_specs(
        p,e['decoupler']['details'])
