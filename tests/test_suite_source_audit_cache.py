from unittest import mock
from types import SimpleNamespace
import pytest
from cec_suite_source_audit_cache import SuiteSourceAuditCache


def test_session_reuses_only_same_mode_and_returns_defensive_copies(tmp_path):
    session = SuiteSourceAuditCache(tmp_path)
    producer = mock.Mock(return_value={'findings': [{'severity': 'BLOCKER'}]})
    with mock.patch.object(session, '_signature', return_value='epoch'):
        first = session.get('electrical-current-beta', producer)
        first['findings'].clear()
        second = session.get('electrical-current-beta', producer)
        assert second == {'findings': [{'severity': 'BLOCKER'}]}
        session.get('generalization', producer)
    assert producer.call_count == 2
    assert (session.hits, session.misses) == (1, 2)


def test_changed_epoch_never_reuses_or_recomputes_old_loaded_code(tmp_path):
    session = SuiteSourceAuditCache(tmp_path)
    producer = mock.Mock(return_value={'ok': True})
    with mock.patch.object(session, '_signature', side_effect=['a', 'a', 'b']):
        session.get('generalization', producer)
        with pytest.raises(ValueError, match='epoch changed'):
            session.get('generalization', producer)
    assert producer.call_count == 1


def test_mutation_during_producer_is_fail_closed(tmp_path):
    session = SuiteSourceAuditCache(tmp_path)
    with mock.patch.object(session, '_signature', side_effect=['a', 'b']):
        with pytest.raises(ValueError, match='changed during'):
            session.get('generalization', lambda: {'ok': True})
    assert session._entries == {}


def test_sessions_never_share_results_and_unknown_modes_refused(tmp_path):
    producer = mock.Mock(return_value={'ok': False})
    for _ in range(2):
        session = SuiteSourceAuditCache(tmp_path)
        with mock.patch.object(session, '_signature', return_value='same'):
            session.get('generalization', producer)
        with pytest.raises(ValueError, match='unsupported'):
            session.get('native-drc', producer)
    assert producer.call_count == 2


def test_real_signature_binds_hierarchy_code_inventory_registry_and_environment(tmp_path, monkeypatch):
    import cec_beta_electrical_audit as electrical
    import cec_sch_gates
    import cec_toolchain
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    scripts = tmp_path / 'scripts'; scripts.mkdir()
    library = tmp_path / 'lib'; library.mkdir()
    source = tmp_path / 'source.kicad_sch'; source.write_text('source-a')
    tool = tmp_path / 'cli'; tool.write_text('tool-a')
    policy = tmp_path / 'pipeline-policy.json'; policy.write_text('{}')
    cfg = SimpleNamespace(dir=str(tmp_path), sch=str(source), pcb=str(source),
                          params={'mode': 'qualified'}, is_draft=False)
    session = SuiteSourceAuditCache(tmp_path)
    with mock.patch.object(electrical, 'discover_projects', return_value=[('product', str(tmp_path), str(source))]), \
            mock.patch.object(electrical, '_source_digest', return_value=('unused', ['source.kicad_sch'])), \
            mock.patch.object(cec_sch_gates, 'inventory', return_value={}), \
            mock.patch.object(cec_toolchain, 'require_kicad_cli', return_value=str(tool)), \
            mock.patch.object(synth.Config, 'load', return_value=cfg), \
            mock.patch.object(pipeline, '_source_files', return_value=[source, policy]):
        previous = session._signature('generalization')
        for target, text in [(source, 'source-b'), (scripts / 'added.py', 'code'),
                             (library / 'registry.json', '{}'), (tool, 'tool-b'),
                             (policy, '{"changed": true}')]:
            target.write_text(text)
            current = session._signature('generalization')
            assert current != previous
            previous = current
        nested = scripts / 'nested'; nested.mkdir()
        (nested / 'runtime.py').write_text('new runtime')
        current = session._signature('generalization')
        assert current != previous
        previous = current
        cfg.params['mode'] = 'changed'
        current = session._signature('generalization')
        assert current != previous
        previous = current
        monkeypatch.setenv('CEC_SUITE_TEST_MODE', 'different')
        assert session._signature('generalization') != previous


def test_finalization_rechecks_epoch_after_last_cache_access(tmp_path):
    session = SuiteSourceAuditCache(tmp_path)
    with mock.patch.object(session, '_signature', side_effect=['a', 'a', 'b']):
        session.get('generalization', lambda: {'ok': True})
        with pytest.raises(ValueError, match='before finalization'):
            session.evidence()


def test_pipeline_cache_never_skips_live_board_intake(tmp_path):
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    cfg = synth.Config.load('hub-standard-rev2')
    session = SuiteSourceAuditCache(pipeline.ROOT)
    with mock.patch.object(session, '_signature', return_value='same-source-code'), \
            mock.patch('cec_constraints.intake_gate', side_effect=[{'ok': True}, {'ok': False}]) as live, \
            mock.patch('cec_generalization_gate.audit', return_value={'ok': True}) as general, \
            mock.patch('cec_beta_electrical_audit.audit', return_value={'findings': []}) as electrical, \
            mock.patch.object(pipeline, '_project_rule_authority_delta', return_value={'ok': True}):
        first = pipeline._source_intake(cfg, cfg.pcb, tmp_path / 'first.json', suite_audit_cache=session)
        second = pipeline._source_intake(cfg, cfg.pcb, tmp_path / 'second.json', suite_audit_cache=session)
    assert first['ok'] and not second['ok']
    assert live.call_count == 2
    assert general.call_count == electrical.call_count == 1
