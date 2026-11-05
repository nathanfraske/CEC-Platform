import copy
import json
from types import SimpleNamespace

import pcbnew
import pytest

import cec_frozen_placement_domain as domain
import cec_full_pipeline as pipeline
import cec_synth_pipeline as synth
from test_frozen_consumer_ownership import native_board


def fixture(tmp_path, *, face_layer=False):
    path, state = native_board(tmp_path)
    state['placements']['LOAD'] = [10., 10., 0.]
    if face_layer:
        state['pours'][0]['layer'] = 'F.Cu'
    path.with_suffix('.pourfirst-state.json').write_text(json.dumps(state))
    candidate = SimpleNamespace(P=copy.deepcopy(state['placements']),
        W=20., H=20., back_refs=())
    candidate.frozen_placement_contract = domain.bind(path, candidate)
    return path, state, candidate


def test_loaded_domain_pins_terminals_but_not_a_proved_independent_consumer(tmp_path):
    path, state, candidate = fixture(tmp_path)
    engine = domain.Domain(candidate.frozen_placement_contract)
    assert set(engine.fixed) == {'TERM_A', 'TERM_B'}
    candidate.P['LOAD'] = [11., 10., 180.]
    before = {p: p.read_bytes() for p in (path, path.with_suffix('.pourfirst-state.json'))}
    report = engine.assess(candidate)
    assert report['ok'] and report['dry_run'] and not report['updated']
    assert engine.positions['LOAD'] == (10., 10., 0.)
    fp = engine.board.FindFootprintByReference('LOAD')
    assert fp.GetPosition() == pcbnew.VECTOR2I_MM(10, 10)
    assert fp.GetOrientationDegrees() == 0.
    assert engine.state == state
    assert all(p.read_bytes() == data for p, data in before.items())


def test_search_reservations_share_the_exact_commit_geometry(tmp_path):
    import cec_power_guard_geometry as geometry
    path, state, candidate = fixture(tmp_path, face_layer=True)
    engine = domain.Domain(candidate.frozen_placement_contract)
    regions = engine.search_regions()
    assert regions
    assert [{k:v for k,v in row.items() if k not in (
        'all_layers','exempt_refs','clearance_mm','authority')} for row in regions
        ] == geometry.placement_reservations(state)
    assert all(row['all_layers'] and row['clearance_mm']==engine.clearance for row in regions)
    assert all('LOAD' in row['exempt_refs'] for row in regions)
    # A coarse-search consumer exemption is never pad-contact admission.
    candidate.P['LOAD'] = [2.,2.,0.]
    assert not engine.assess(candidate)['ok']


@pytest.mark.parametrize('rotation',[0.,90.,180.,270.])
def test_native_pad_search_detects_contact_and_restores_pose(tmp_path,rotation):
    path, state, candidate = fixture(tmp_path,face_layer=True)
    engine = domain.Domain(candidate.frozen_placement_contract)
    before = path.read_bytes()
    poses = {'LOAD':(2.,2.,rotation)}
    hits = engine.search_pad_collisions(poses)
    assert hits and all(row['kind']=='frozen_consumer_pad' for row in hits)
    assert all(row['region_index']<0 and row['member_box'] and row['box'] for row in hits)
    assert hits == engine.search_pad_collisions(poses)
    assert engine.search_pad_collisions({'LOAD':(11.,10.,rotation)}) == []
    assert engine.positions['LOAD'] == (10.,10.,0.)
    assert engine.board.FindFootprintByReference('LOAD').GetPosition() == pcbnew.VECTOR2I_MM(10,10)
    assert engine.board.FindFootprintByReference('LOAD').GetOrientationDegrees() == 0.
    assert path.read_bytes()==before


def test_native_pad_search_allows_inner_bus_body_but_not_through_via(tmp_path):
    path,state,candidate = fixture(tmp_path)
    state['vias']=[dict(net='rail',x_mm=12.,y_mm=12.,diameter_mm=.8)]
    path.with_suffix('.pourfirst-state.json').write_text(json.dumps(state))
    engine=domain.Domain(domain.bind(path,candidate))
    assert 'LOAD' not in engine.fixed
    assert not engine.search_pad_collisions({'LOAD':(2.,2.,0.)})
    assert engine.search_pad_collisions({'LOAD':(12.,12.,0.)})


@pytest.mark.parametrize('fault', ['terminal', 'new_contact', 'face', 'population', 'outline', 'nan'])
def test_native_candidate_refusal_never_changes_source_or_loaded_pose(tmp_path, fault):
    path, _, candidate = fixture(tmp_path, face_layer=True)
    engine = domain.Domain(candidate.frozen_placement_contract)
    if fault == 'terminal': candidate.P['TERM_A'] = [1.5, 1., 0.]
    if fault == 'new_contact': candidate.P['LOAD'] = [2., 2., 0.]
    if fault == 'face': candidate.back_refs = ('LOAD',)
    if fault == 'population': candidate.P.pop('LOAD')
    if fault == 'outline': candidate.W += 1.
    if fault == 'nan': candidate.P['LOAD'] = [float('nan'), 1., 0.]
    before = path.read_bytes()
    assert not engine.assess(candidate)['ok']
    assert path.read_bytes() == before
    assert engine.board.FindFootprintByReference('LOAD').GetPosition() == pcbnew.VECTOR2I_MM(10, 10)


def test_incomplete_ownership_proof_restricts_whole_net(tmp_path):
    path, state, candidate = fixture(tmp_path)
    state.pop('reserve_report')
    path.with_suffix('.pourfirst-state.json').write_text(json.dumps(state))
    candidate.frozen_placement_contract = domain.bind(path, candidate)
    assert set(domain.Domain(candidate.frozen_placement_contract).fixed) == {'TERM_A', 'TERM_B', 'LOAD'}


@pytest.mark.parametrize('fault', ['board_bytes', 'state_bytes', 'snapshot'])
def test_stale_authority_is_not_a_search_domain(tmp_path, fault):
    path, state, candidate = fixture(tmp_path)
    if fault == 'board_bytes': path.write_text(path.read_text() + '\n')
    if fault == 'state_bytes': path.with_suffix('.pourfirst-state.json').write_text('{}')
    if fault == 'snapshot':
        state['placements']['LOAD'] = [8., 10., 0.]
        path.with_suffix('.pourfirst-state.json').write_text(json.dumps(state))
        candidate.frozen_placement_contract = domain.bind(path, candidate)
    with pytest.raises(ValueError): domain.Domain(candidate.frozen_placement_contract)


def test_worker_rejects_owned_terminal_before_materialization(tmp_path, monkeypatch):
    _, _, candidate = fixture(tmp_path)
    candidate.P['TERM_A'] = [1.5, 1., 0.]
    def forbidden(*args, **kwargs): raise AssertionError('forbidden move materialized')
    monkeypatch.setattr(synth, 'materialize', forbidden)
    result = synth._placement_craft_trial_worker(dict(candidate=candidate,
        cfg=SimpleNamespace(params={}), path=str(tmp_path/'trial.kicad_pcb')))
    assert not result['ok'] and result['error_kind'] == 'frozen_placement_dependency'
    proof = synth._placement_trial_failure_evidence([result])
    assert proof['count'] == 1
    assert proof['samples'][0]['frozen_placement_guard']['refused'][0]['ref'] == 'TERM_A'


def test_commit_and_dry_run_use_the_same_native_rule(tmp_path):
    path, state, _ = fixture(tmp_path)
    state['placements']['LOAD'] = [9., 10., 0.]
    sidecar = path.with_suffix('.pourfirst-state.json')
    sidecar.write_text(json.dumps(state))
    before = sidecar.read_bytes()
    dry = pipeline._sync_safe_postfreeze_placement_delta(path, dry_run=True)
    assert dry['ok'] and sidecar.read_bytes() == before
    actual = pipeline._sync_safe_postfreeze_placement_delta(path)
    assert actual['ok'] and actual['refs'] == dry['refs']
    assert actual['deferred_consumers'] == dry['deferred_consumers']


def test_fixed_root_and_compound_followers_do_not_consume_fair_trial_budget():
    positions = {'LOCKED': (1., 1., 0.), 'FREE': (4., 4., 0.)}
    moves = [
        {'kind': 'owner', 'ref': 'LOCKED', 'position': (2., 1., 0.)},
        {'kind': 'compound', 'ref': 'FREE', 'placements': {
            'FREE': (5., 4., 0.), 'LOCKED': (2., 1., 0.)}},
        {'kind': 'free', 'ref': 'FREE', 'position': (5., 4., 0.)},
        {'kind': 'same_pose', 'ref': 'LOCKED', 'position': (1., 1., 360.)}]
    kept, report = domain.filter_fixed_moves(moves, positions, {'LOCKED': {}})
    assert kept == moves[2:] and report['refused'] == 2
    assert synth._bounded_diverse_move_specs(kept, 1)[0] == moves[2]


def test_worker_failure_receipts_are_bounded():
    rows = [{'ok': False, 'error_kind': 'frozen_placement_dependency',
             'frozen_placement_guard': {'ok': False}}] * 20
    report = synth._placement_trial_failure_evidence(rows, limit=3)
    assert report['count'] == 20 and report['truncated'] == 17 and len(report['samples']) == 3
