from pathlib import Path
import pytest
import cec_prefreeze_local_pi as early


def admitted(**changes):
    return dict(dict(ok=True, priority_complete=True, rolled_back=False,
                     applicable=True, generated_items=[{'uuid': 'owned-item'}],
                     required_via_uuids=['owned-return']), **changes)


def test_constructor_uses_existing_policy_and_never_rips_up_source(tmp_path, monkeypatch):
    import cec_decoupler_cell
    source = tmp_path / 'arbitrary.kicad_pcb'
    source.write_bytes(b'immutable')
    seen = []
    def construct(src, dst, **kw):
        seen.append(kw)
        Path(dst).write_bytes(b'local cells')
        return admitted()
    monkeypatch.setattr(cec_decoupler_cell, 'synthesize_pre_route', construct)
    path, report = early.prepare(source, {'decoupler_ground_reach_mm': 1.2,
                                         'decoupler_ground_pin_max_mm': 2.1})
    assert source.read_bytes() == b'immutable'
    assert Path(path).read_bytes() == b'local cells'
    assert seen == [dict(ground_reach_mm=1.2, ground_pin_max_mm=2.1,
                         repair_existing_copper=False)]
    assert early.identities(report) == {'owned-item'}


@pytest.mark.parametrize('change', [dict(ok=False), dict(priority_complete=False),
    dict(rolled_back=True), dict(ok=None)])
def test_unadmitted_local_geometry_cannot_reach_power_planner(tmp_path, monkeypatch, change):
    import cec_decoupler_cell
    monkeypatch.setattr(cec_decoupler_cell, 'synthesize_pre_route',
                        lambda *a, **kw: admitted(**change))
    with pytest.raises(early.LocalCellsRefused) as error:
        early.prepare(tmp_path / 'source.kicad_pcb', {})
    assert error.value.report['applicable']


def test_disabled_policy_does_no_native_work(monkeypatch):
    import cec_decoupler_cell
    monkeypatch.setattr(cec_decoupler_cell, 'synthesize_pre_route',
                        lambda *a, **kw: pytest.fail('disabled constructor ran'))
    path, report = early.prepare('unchanged.kicad_pcb', {'pourfirst_local_pi': False})
    assert path == 'unchanged.kicad_pcb' and not report['applicable']


@pytest.mark.parametrize('plane_ok', [True, False])
def test_exact_replay_requires_these_return_identities_on_filled_planes(monkeypatch, plane_ok):
    import cec_ground_plane
    calls = []
    def fill(board, **kw):
        calls.append(kw)
        return dict(ok=plane_ok, reasons=[] if plane_ok else ['missing owned return'])
    monkeypatch.setattr(cec_ground_plane, 'fill_board', fill)
    if plane_ok:
        assert early.finish_reference_planes(object(), 'proof.kicad_pcb', admitted())['ok']
    else:
        with pytest.raises(RuntimeError, match='return-plane proof refused'):
            early.finish_reference_planes(object(), 'proof.kicad_pcb', admitted())
    assert calls == [dict(board_path='proof.kicad_pcb', required_via_uuids=('owned-return',))]


def test_legacy_state_without_new_cells_retains_old_behavior(monkeypatch):
    import cec_ground_plane
    monkeypatch.setattr(cec_ground_plane, 'fill_board',
                        lambda *a, **kw: pytest.fail('legacy state generated new planes'))
    assert not early.finish_reference_planes(object(), 'legacy', {})['applicable']
    assert not early.finish_reference_planes(object(), 'empty',
               admitted(required_via_uuids=[]))['applicable']


def test_missing_local_admission_cannot_be_hidden_by_plane_pass():
    with pytest.raises(early.LocalCellsRefused):
        early.finish_reference_planes(object(), 'unused', admitted(ok=False))


@pytest.mark.parametrize('defect', [None, 'pcb_changed', 'unadmitted', 'incomplete', 'legacy'])
def test_measurement_replays_only_the_byte_bound_admitted_composition(tmp_path, monkeypatch, defect):
    import hashlib
    import json
    import cec_power_local_replay
    source = tmp_path / 'board.kicad_pcb'
    source.write_bytes(b'measured placement')
    state = dict(placement_scope='complete', pre_freeze_local_pi=admitted(),
        exact_admission={'passed': True}, local_copper_contract={'sha256': 'owned'},
        exact_admission_context={'board_sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    if defect == 'pcb_changed': source.write_bytes(b'different pose or copper')
    elif defect == 'unadmitted': state['exact_admission']['passed'] = False
    elif defect == 'incomplete': state['placement_scope'] = 'anchors_only'
    elif defect == 'legacy': state.pop('pre_freeze_local_pi')
    path = tmp_path / 'authority.json'
    path.write_text(json.dumps(state))
    calls = []
    def replay(board, contract):
        calls.append(contract)
        return dict(ok=True, added=7)
    monkeypatch.setattr(cec_power_local_replay, 'replay', replay)
    report = early.replay_for_measurement(object(), source, {'pourfirst_state': str(path)})
    assert report['applicable'] == (defect is None)
    assert bool(calls) == (defect is None)
    assert source.read_bytes() == (b'different pose or copper' if defect == 'pcb_changed' else b'measured placement')
