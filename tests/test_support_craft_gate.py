"""Route-time placement must obey the final electrical craft authorities."""
from copy import deepcopy
import pytest
import cec_support_craft_gate as craft


@pytest.mark.parametrize('cap,owner', [('C1', 'U1'), ('BYPASS_OTHER', 'OWNER_OTHER')])
def test_early_return_distance_uses_declared_native_limit(cap, owner):
    row = dict(cap_ref=cap, owner_ref=owner, owner_pin='7', rail='/RENAMED',
        return_gate_mode='absolute_ground_distance', ground_distance_mm=2.622,
        return_limit_mm=2.5)
    assert len(craft.geometry_faults([row])) == 1
    row['return_limit_mm'] = 2.7
    assert craft.geometry_faults([row]) == {}
    row.update(return_gate_mode='rail_to_rail_loop', return_limit_mm=2.5)
    assert craft.geometry_faults([row]) == {}


@pytest.mark.parametrize('gate', ['decouple_ok', 'decoupler_cell_ok', 'netclass_geometry_ok'])
def test_every_final_gate_is_preserved(gate):
    before = dict(ok=True, gates={gate: True}, faults={})
    after = dict(ok=True, gates={gate: False}, faults={})
    result = craft.compare(before, after)
    assert not result['accepted'] and result['gate_regressions'] == [gate]


@pytest.mark.parametrize('kind', ['return_geometry', 'decouple_ok', 'decoupler_cell_ok', 'netclass_geometry_ok'])
def test_equal_counts_cannot_trade_fault_identity(kind):
    before = dict(ok=True, gates={}, faults={kind: {'original': 3}})
    after = dict(ok=True, gates={}, faults={kind: {'new': 1}})
    assert not craft.compare(before, after)['accepted']
    assert craft.compare(before, dict(ok=True, gates={}, faults={kind: {'original': 2}}))['accepted']
    assert not craft.compare(before, dict(ok=True, gates={}, faults={kind: {'original': 4}}))['accepted']


def test_preflight_ignores_intentionally_removed_supply_copper():
    before = dict(ok=True, gates={}, faults={'return_geometry': {}, 'decoupler_cell_ok': {}})
    after = dict(ok=True, phase='geometry', gates={}, faults={'return_geometry': {}})
    assert craft.compare(before, after)['accepted']


def test_unknown_measurement_remains_retryable_not_a_measured_bad_pose():
    report = craft.compare(dict(ok=True), dict(ok=False, error='native timeout'))
    assert not report['accepted'] and report['decision'].endswith('worker_error')


def test_native_authorities_receive_same_policy_and_full_violation_list(monkeypatch):
    import pcbnew
    import cec_decoupler_cell as cell
    import cec_synth_pipeline as synth
    violations = [['CAP%d'%i, 'OWNER.GND[/RAIL]', 3.] for i in range(20)]
    params = dict(decoupler_ground_reach_mm=.9, decoupler_ground_pin_max_mm=1.8)
    called = {}
    def adjacency(path, cfg, *, phase):
        called['params'] = cfg.params
        called['phase'] = phase
        return dict(ok=False, details=[], violations=violations[:12], all_violations=violations)
    def cells(board, **kwargs):
        called['cells'] = kwargs
        return dict(ok=True, refused=[])
    monkeypatch.setattr(synth, '_oracle_decoupler_adjacency', adjacency)
    monkeypatch.setattr(synth, '_oracle_netclass_geometry', lambda path: dict(ok=True, violations=[]))
    monkeypatch.setattr(pcbnew, 'LoadBoard', lambda path: object())
    monkeypatch.setattr(cell, 'audit_board', cells)
    result = craft.measure('candidate.kicad_pcb', {'params': params})
    assert called['params'] == params
    assert called['phase'] == 'routed'
    assert called['cells']['ground_reach_mm'] == .9
    assert called['cells']['ground_pin_max_mm'] == 1.8
    assert len(result['faults']['decouple_ok']) == 20


def test_comparison_never_mutates_evidence():
    before = dict(ok=True, gates={'decouple_ok': True}, faults={'return_geometry': {}})
    after = dict(ok=True, gates={'decouple_ok': True}, faults={'return_geometry': {}})
    original = deepcopy((before, after))
    assert craft.compare(before, after)['accepted']
    assert (before, after) == original
