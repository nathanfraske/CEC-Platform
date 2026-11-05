import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import cec_placement_evidence_identity as identity
import cec_synth_pipeline as synth


def test_paired_peer_bytes_invalidate_cached_placement(tmp_path):
    board=tmp_path/'board.kicad_pcb';board.write_text('native')
    peer=tmp_path/'peer.kicad_pcb';peer.write_text('first')
    contract=tmp_path/'contract.json';contract.write_text('{}')
    pair=tmp_path/'pair.json';pair.write_text(json.dumps(dict(cover=dict(path=str(peer),sha256='pinned'))))
    cfg=SimpleNamespace(params=dict(assembly_envelope=dict(role='carrier',contract=str(contract),pair=str(pair))))
    first=identity.capture(board,cfg)
    peer.write_text('other')
    second=identity.capture(board,cfg)
    assert first['sha256']!=second['sha256']
    assert first['files']['assembly.2']['sha256']!=second['files']['assembly.2']['sha256']


@pytest.mark.parametrize('suffix', identity.SIDECARS + ('.pourfirst-skeleton.kicad_pcb',))
def test_sidecar_creation_mutation_and_removal_invalidate(tmp_path, suffix):
    board = tmp_path / 'board.kicad_pcb'
    board.write_text('fixed native board')
    initial = synth._placement_craft_cache_key(board)
    authority = tmp_path / ('board' + suffix)
    authority.write_text('first')
    created = synth._placement_craft_cache_key(board)
    authority.write_text('other')
    changed = synth._placement_craft_cache_key(board)
    authority.unlink()
    assert len({initial, created, changed}) == 3
    assert initial == synth._placement_craft_cache_key(board)


@pytest.mark.parametrize('via_environment', [False, True])
def test_external_authority_bytes_not_only_path_are_bound(tmp_path, monkeypatch, via_environment):
    board = tmp_path / 'board.kicad_pcb'
    board.write_text('native')
    state = tmp_path / 'external-state.json'
    state.write_text('first')
    cfg = SimpleNamespace(params={})
    if via_environment:
        monkeypatch.setenv('CEC_POURFIRST_STATE', str(state))
    else:
        cfg.params['pourfirst_state'] = str(state)
    first = identity.capture(board, cfg)
    state.write_text('other')
    assert identity.capture(board, cfg)['sha256'] != first['sha256']


def test_environment_is_hashed_and_os_secrets_not_recorded(tmp_path, monkeypatch):
    board = tmp_path / 'board.kicad_pcb'
    board.write_text('native')
    monkeypatch.setenv('UNRELATED_SECRET', 'never log this')
    monkeypatch.setenv('CEC_TEST_POLICY', 'policy value')
    first = identity.capture(board)
    encoded = json.dumps(first)
    assert 'never log this' not in encoded and 'policy value' not in encoded
    monkeypatch.setenv('CEC_TEST_POLICY', 'changed')
    assert first['sha256'] != identity.capture(board)['sha256']


def test_mid_measurement_mutation_is_not_cached_or_admitted(tmp_path, monkeypatch):
    board = tmp_path / 'board.kicad_pcb'
    board.write_text('native')
    def evaluate(*args, **kwargs):
        board.with_suffix('.kicad_dru').write_text('changed rule')
        return {'ok': True}
    monkeypatch.setattr(synth, '_placement_craft_evidence_uncached', evaluate)
    synth._clear_placement_craft_cache()
    result = synth.placement_craft_evidence(board)
    assert not result['ok'] and result['input_identity_after'] != result['input_identity']
    assert synth.placement_craft_cache_stats()['stores'] == 0
    change = result['input_identity_change']
    assert not change['ok'] and not change['promotion_allowed']
    assert [row['role'] for row in change['file_changes']] == ['board.kicad_dru']
    assert change['file_changes'][0]['before']['sha256'] is None
    assert change['file_changes'][0]['after']['sha256']
    # The coordinator's existing generic projection used to lose both input
    # identities here, leaving only an untraceable error string.
    import cec_full_pipeline as pipeline
    failures = pipeline._placement_craft_failures(result)
    assert failures['input_identity_change'] == change
    assert 'errors' in failures
    failures['input_identity_change']['file_changes'].clear()
    assert result['input_identity_change']['file_changes']


def test_identity_delta_preserves_roles_without_disclosing_values(tmp_path, monkeypatch):
    board = tmp_path / 'board.kicad_pcb'; board.write_text('native')
    cfg = SimpleNamespace(params={'arbitrary_policy': 'private setting'})
    monkeypatch.setenv('CEC_TEST_POLICY', 'secret value before')
    before = identity.capture(board, cfg)
    cfg.params['arbitrary_policy'] = 'private new setting'
    monkeypatch.setenv('CEC_TEST_POLICY', 'secret value after')
    monkeypatch.setenv('CEC_ADDED_POLICY', 'also private')
    after = identity.capture(board, cfg)
    change = identity.describe_change(before, after)
    assert not change['ok'] and change['policy_changed']
    assert [row['name'] for row in change['environment_changes']] == [
        'CEC_ADDED_POLICY', 'CEC_TEST_POLICY']
    encoded = json.dumps(change)
    assert 'secret value' not in encoded and 'private setting' not in encoded
    assert 'private new setting' not in encoded and 'also private' not in encoded
    assert not change['file_changes']


def test_identical_and_repointed_file_deltas_are_deterministic(tmp_path):
    first = tmp_path/'first'; second = tmp_path/'second'
    first.write_text('same'); second.write_text('same')
    before = identity.capture(first)
    assert identity.describe_change(before, before)['ok']
    after = identity.capture(second)
    change = identity.describe_change(before, after)
    assert not change['ok'] and not change['policy_changed']
    assert identity.describe_change(before, after) == change
    file_change = next(row for row in change['file_changes'] if row['role'] == 'board')
    assert file_change['before']['sha256'] == file_change['after']['sha256']
    assert file_change['before']['path'] != file_change['after']['path']


@pytest.mark.parametrize('key', ['CEC_OPERATION_PROGRESS','CEC_OPERATION_STACKS'])
def test_declared_diagnostic_creation_and_append_do_not_invalidate_inputs(tmp_path,monkeypatch,key):
    board=tmp_path/'board.kicad_pcb';board.write_text('native')
    log=tmp_path/'runtime-output';monkeypatch.setenv(key,str(log))
    before=identity.capture(board)
    log.write_text('first supervisor output')
    assert before==identity.capture(board)
    log.write_text('new stack/progress contents')
    assert before==identity.capture(board)
    assert 'environment.'+key not in before['files']
    assert key in before['environment_sha256']


@pytest.mark.parametrize('config_alias',[False,True])
def test_diagnostic_file_referenced_as_authority_still_invalidates(tmp_path,monkeypatch,config_alias):
    board=tmp_path/'board.kicad_pcb';board.write_text('native')
    shared=tmp_path/'authority.json';shared.write_text('first')
    monkeypatch.setenv('CEC_OPERATION_STACKS',str(shared))
    cfg=SimpleNamespace(params={})
    if config_alias:cfg.params['explicit_file']=str(shared)
    else:monkeypatch.setenv('CEC_UNKNOWN_AUTHORITY',str(shared))
    before=identity.capture(board,cfg)
    shared.write_text('changed')
    change=identity.describe_change(before,identity.capture(board,cfg))
    assert not change['ok']
    assert [r['role'] for r in change['file_changes']]==[
        'config.params.explicit_file' if config_alias else 'environment.CEC_UNKNOWN_AUTHORITY']


def test_stack_sampling_during_measurement_is_not_false_input_mutation(tmp_path,monkeypatch):
    board=tmp_path/'board.kicad_pcb';board.write_text('native')
    log=tmp_path/'stacks.log';log.write_text('')
    monkeypatch.setenv('CEC_OPERATION_STACKS',str(log))
    def evaluate(*args,**kwargs):
        log.write_text('periodic stack sample')
        return {'ok':True,'errors':[]}
    monkeypatch.setattr(synth,'_placement_craft_evidence_uncached',evaluate)
    synth._clear_placement_craft_cache()
    result=synth.placement_craft_evidence(board)
    assert result['ok'] and not result['errors']
    assert 'input_identity_change' not in result
    assert synth.placement_craft_cache_stats()['stores']==1


def test_failure_retains_both_exact_artifacts_and_rule_inputs(tmp_path):
    expected_path = tmp_path / 'trial.kicad_pcb'
    actual_path = tmp_path / 'incumbent.kicad_pcb'
    expected_path.write_text('trial native')
    actual_path.write_text('certified native')
    actual_path.with_suffix('.kicad_dru').write_text('exact rules')
    expected = {'input_identity': identity.capture(expected_path), 'ok': False}
    actual = {'input_identity': identity.capture(actual_path), 'ok': False}
    path = Path(identity.retain_failure(tmp_path / 'retained', expected=expected,
        actual=actual, candidate=SimpleNamespace(P={'X': (1, 2, 90)}, back_refs=()), reason='drift'))
    expected_path.unlink()
    actual_path.unlink()
    report = json.loads(path.read_text())
    assert report['complete'] and not report['promotion_allowed']
    assert report['candidate']['positions']['X'] == [1, 2, 90]
    for row in report['files']:
        assert identity.digest(path.parent / row['retained_as']) == row['sha256']
    assert {r['evidence'] for r in report['files']} == {'expected', 'actual'}


def test_retention_quota_and_changed_files_stay_fail_closed(tmp_path):
    board = tmp_path / 'board.kicad_pcb'
    board.write_text('original')
    evidence = {'input_identity': identity.capture(board)}
    board.write_text('changed')
    args = dict(expected=evidence, actual=evidence, candidate=SimpleNamespace(),
                reason='drift', max_bundles=1)
    report = json.loads(Path(identity.retain_failure(tmp_path / 'retained', **args)).read_text())
    assert not report['complete'] and not report['promotion_allowed']
    with pytest.raises(RuntimeError, match='quota exhausted'):
        identity.retain_failure(tmp_path / 'retained', **args)


def test_retention_byte_budget_is_explicit(tmp_path):
    board = tmp_path / 'board.kicad_pcb'
    board.write_text('larger than quota')
    evidence = {'input_identity': identity.capture(board)}
    path = identity.retain_failure(tmp_path / 'retained', expected=evidence,
        actual=evidence, candidate=SimpleNamespace(), reason='drift', max_bytes=2)
    report = json.loads(Path(path).read_text())
    assert not report['complete'] and report['retained_bytes'] == 0
