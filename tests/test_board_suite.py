from pathlib import Path
import json
from unittest.mock import patch
import pytest
import cec_board_suite as suite

def test_commands_keep_source_authority_and_no_admission_bypass():
    for derived in (False, True):
        row={'board':'synthetic', 'input':'/declared/input.kicad_pcb', 'derived':derived}
        cmd=suite.command(row,Path('/new/output'),trials=12,passes=8)
        assert '--review-skip-route-probes' not in cmd
        assert '--resume' not in cmd
        assert ('--allow-derived-input' in cmd) == derived
        assert ('--fresh-placement-only' in cmd) == (not derived)
        if derived:
            assert cmd[cmd.index('--input-board')+1]==row['input']

def test_unknown_boards_and_unused_overrides_fail_closed():
    with pytest.raises(ValueError): suite.inputs(['obsolete-candidate'])
    with pytest.raises(ValueError): suite.inputs([], {'unused':'x'})


def test_explicit_per_board_pool_ceiling_is_forwarded_without_admission_changes():
    row = {'board':'synthetic', 'input':'/declared/input.kicad_pcb', 'derived':False}
    old = suite.command(row, Path('/new/output'), trials=12, passes=8)
    new = suite.command(row, Path('/new/output'), trials=12, passes=8, workers_per_board=6)
    index = old.index('--workers') + 1
    assert old[index] == '2' and new[index] == '6'
    new[index] = old[index]
    assert new == old


@pytest.mark.parametrize('workers', [0, -1, 1.5, True])
def test_invalid_per_board_worker_ceiling_fails_before_launch(workers):
    with pytest.raises(ValueError, match='positive integer'):
        suite.command({}, Path('/new/output'), trials=12, passes=8, workers_per_board=workers)


def test_explicit_priority_operation_budget_is_forwarded_without_route_waivers():
    row = {'board':'synthetic', 'input':'/declared/input.kicad_pcb', 'derived':False}
    cmd = suite.command(row, Path('/new/output'), trials=12, passes=8,
                        priority_repair_timeout=1200)
    assert cmd[cmd.index('--priority-repair-timeout')+1] == '1200.0'
    assert '--review-skip-route-probes' not in cmd


@pytest.mark.parametrize('timeout', [0, -1, float('nan'), float('inf'), True])
def test_invalid_priority_budget_fails_before_launch(timeout):
    with pytest.raises(ValueError, match='finite and positive'):
        suite.command({}, Path('/new/output'), trials=12, passes=8, priority_repair_timeout=timeout)


@pytest.mark.parametrize('invalidated', [True, False])
def test_certified_interface_eco_selects_rebuild_not_fresh_or_retained(invalidated):
    row={'board':'synthetic','input':'/current/seed.kicad_pcb','derived':True}
    with patch('cec_interface_eco.read_status',return_value={'route_authority_invalidated':invalidated}):
        cmd=suite.command(row,Path('/new/output'),trials=12,passes=8)
    assert ('--replace-placement' in cmd)==invalidated
    assert '--fresh-placement-only' not in cmd


def test_mismatched_interface_eco_never_launches():
    row={'board':'synthetic','input':'/current/seed.kicad_pcb','derived':True}
    with patch('cec_interface_eco.read_status',side_effect=ValueError('changed bytes')):
        with pytest.raises(ValueError,match='changed bytes'):
            suite.command(row,Path('/new/output'),trials=12,passes=8)

def test_signature_detects_hierarchy_drift_and_deletion(tmp_path):
    path=tmp_path/'leaf.kicad_sch';path.write_text('current')
    sig={'files':[{'path':str(path),'sha256':suite.sha(path)}]}
    assert suite.signature_unchanged(sig)
    path.write_text('changed')
    assert not suite.signature_unchanged(sig)
    path.unlink()
    assert not suite.signature_unchanged(sig)


@pytest.mark.parametrize('case', ['completed', 'missing_output', 'partial', 'changed_source', 'running', 'changed_board'])
def test_continuation_is_explicit_and_requires_stable_authority(tmp_path, case):
    name = suite.manifest.WAVE_BOARDS[0]
    source = tmp_path/'source.sch'
    source.write_text('current source')
    target = tmp_path/name
    output = target/'02-placement/board.kicad_pcb'
    output.parent.mkdir(parents=True)
    output.write_text('completed placement, not routing')
    entry = {'status':'complete', 'result':{'board':str(output)},
             'artifacts':[{'path':str(output),'sha256':suite.sha(output)}]}
    row = {'status':'blocked_or_failed','source_inputs_unchanged':True,'engine_unchanged':True,
           'source_signature':{'files':[{'path':str(source),'sha256':suite.sha(source)}]}}
    if case == 'running': row['status'] = 'running'
    if case == 'changed_source': source.write_text('source drift')
    if case == 'changed_board': output.write_text('copper changed after publication')
    if case in ('partial', 'missing_output'): entry = {'status':'timed_out'}
    if case == 'missing_output': output.unlink()
    (target/'pipeline-state.json').write_text(json.dumps({'board':name,'stages':{'placement':entry}}))
    summary = tmp_path/'suite.json'
    summary.write_text(json.dumps({'boards':{name:row}}))
    if case in ('changed_source', 'running', 'changed_board'):
        with pytest.raises(ValueError): suite.continuation_inputs(summary, [name])
    else:
        overrides, lineage = suite.continuation_inputs(summary, [name])
        assert (name in overrides) == (case == 'completed')
        assert lineage[name]['mode'] == ('continue' if case == 'completed' else 'fresh')
