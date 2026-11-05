import copy
import json
from types import SimpleNamespace
from unittest import mock

import pytest

import cec_materialized_candidate as materialized


@pytest.fixture
def sample(tmp_path, monkeypatch):
    source = tmp_path / 'board.kicad_pcb'
    source.write_text('retained copper')
    source.with_suffix('.railreport.json').write_text(json.dumps(dict(
        board=source.name, laid=0)))
    proposal = tmp_path / 'proposal.kicad_pcb'
    proposal.write_text('exact searched copper')
    proposal.with_suffix('.railreport.json').write_text(json.dumps(dict(
        board=proposal.name, laid=1)))
    candidate = SimpleNamespace(P={'ARBITRARY': (1., 2., 90.)}, back_refs=())
    cfg = SimpleNamespace(params={})
    monkeypatch.setattr(materialized, '_engine', lambda: 'unchanged engine')
    return source, proposal, candidate, cfg


def test_exact_proposal_survives_temporary_file_loss_and_only_identity_field_rebinds(sample):
    source, proposal, candidate, cfg = sample
    bundle, receipt = materialized.capture(proposal, source, candidate, cfg)
    assert receipt['captured'] and not receipt['cached_admission']
    proposal.unlink()
    proposal.with_suffix('.railreport.json').unlink()
    installed = materialized.install(bundle, source, candidate, cfg)
    assert installed['used'] and not installed['cached_admission']
    assert source.read_text() == 'exact searched copper'
    assert json.loads(source.with_suffix('.railreport.json').read_text()) == dict(
        board=source.name, laid=1)


@pytest.mark.parametrize('change', ['source', 'policy', 'sidecar', 'pose', 'face',
                                  'engine', 'bytes', 'foreign_path', 'quota'])
def test_stale_or_corrupted_bundle_fails_before_any_write(sample, monkeypatch, change):
    source, proposal, candidate, cfg = sample
    bundle, _ = materialized.capture(proposal, source, candidate, cfg)
    if change == 'source': source.write_text('independent edit')
    elif change == 'policy': cfg.params['clearance'] = .5
    elif change == 'sidecar': source.with_suffix('.railreport.json').write_text('{}')
    elif change == 'pose': candidate.P['ARBITRARY'] = (2., 2., 90.)
    elif change == 'face': candidate.back_refs = ('ARBITRARY',)
    elif change == 'engine': monkeypatch.setattr(materialized, '_engine', lambda: 'new engine')
    elif change == 'bytes': bundle['files'][proposal.name]['data'] = b'tampered'
    elif change == 'foreign_path': bundle['files']['../outside'] = dict(data=b'bad', sha256='bad')
    else: bundle['byte_count'] += 1
    before = source.read_bytes()
    sidecar = source.with_suffix('.railreport.json').read_bytes()
    with pytest.raises(ValueError):
        materialized.install(bundle, source, candidate, cfg)
    assert source.read_bytes() == before
    assert source.with_suffix('.railreport.json').read_bytes() == sidecar


def test_capture_is_bounded_and_external_skeleton_is_not_silently_read(sample, tmp_path):
    source, proposal, candidate, cfg = sample
    bundle, receipt = materialized.capture(proposal, source, candidate, cfg, max_bytes=1)
    assert bundle is None and receipt['reason'] == 'in_memory_byte_quota'
    external = tmp_path / 'outside.kicad_pcb'
    external.write_text('not owned by this family')
    proposal.with_suffix('.pourfirst-state.json').write_text(json.dumps(dict(skeleton=str(external))))
    bundle, receipt = materialized.capture(proposal, source, candidate, cfg)
    assert bundle is None and receipt['reason'] == 'external_skeleton_not_captured'


@pytest.mark.parametrize('regression', [False, True])
def test_coordinator_rechecks_exact_bytes_and_can_still_roll_them_back(sample, regression):
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    import cec_placement_reconstruction as reconstruction
    from test_placement_reconstruction import craft, score
    source, proposal, candidate, cfg = sample
    cfg.sch = 'declared_source.kicad_sch'
    candidate.reconstruction_artifact, _ = materialized.capture(proposal, source, candidate, cfg)
    repair = dict(changed=False, accepted_count=0, reconstruction_proposal=dict(requested=True))
    measured = [score(), dict(score(), drc=int(regression))]
    def rescore(*args):
        if len(measured) == 1:
            assert source.read_text() == 'exact searched copper'
        return measured.pop(0)
    with mock.patch.object(synth, 'placement_craft_evidence', side_effect=[craft(3), craft(2)]), \
            mock.patch.object(synth, 'materialize', side_effect=AssertionError('must not rerun search')), \
            mock.patch.object(reconstruction, 'fixed_domain', return_value='fixed'), \
            mock.patch('cec_placement_route_prefix.capture', return_value={'items': 0}), \
            mock.patch.object(pipeline, '_frozen_placement_contract', return_value={'applicable': False}), \
            mock.patch('cec_fab_repair._score_isolated', side_effect=rescore) as native, \
            mock.patch('cec_fab_repair._foreign_isolated', return_value={'foreign_status': 'pass', 'foreign_blocking': 0}), \
            mock.patch.object(synth, '_admit_materialized_power_prefix', return_value={'ok': True}), \
            mock.patch('cec_constraints.intake_gate', return_value={'ok': True}):
        result = pipeline._commit_craft_reconstruction(cfg, candidate, source, repair)
    assert native.call_count == 2
    assert result['reconstruction_commit']['accepted'] is not regression
    assert result['reconstruction_artifact']['used']
    assert source.read_text() == ('retained copper' if regression else 'exact searched copper')
