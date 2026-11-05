"""Explicit frontier selection is identity validation, never routing admission."""
import json
from types import SimpleNamespace

import pytest
import cec_board_suite as suite


@pytest.fixture
def frontier(tmp_path, monkeypatch):
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    monkeypatch.setattr(suite, 'ROOT', tmp_path)
    entries = {name: dict(board=name, pcb='board.kicad_pcb', wave=wave)
               for name, wave in [('renamed-main', True), ('renamed-control', False)]}
    monkeypatch.setattr(suite.manifest, 'BY_BOARD', entries)
    monkeypatch.setattr(suite.manifest, 'WAVE_BOARDS', ('renamed-main',))
    monkeypatch.setattr(synth.Config, 'load', lambda name: SimpleNamespace(board=name))
    monkeypatch.setattr(pipeline, '_source_files', lambda cfg, board: [board])
    def signature(paths):
        return {'files': [dict(path=str(p), sha256=suite.sha(p)) for p in sorted(map(__import__('pathlib').Path, paths))]}
    monkeypatch.setattr(pipeline, '_files_signature', signature)
    paths = []
    for name in entries:
        path = tmp_path / (name + '.kicad_pcb')
        path.write_text('immutable ' + name)
        paths.append(path)
    lineage = tmp_path/'lineage.json'; lineage.write_text('{}')
    records = [dict(board=name, path=str(path), sha256=suite.sha(path), expected_opens=opens)
               for name, path, opens in zip(entries, paths, [3, 0])]
    records[0].update(lineage=str(lineage), lineage_sha256=suite.sha(lineage))
    plan = tmp_path/'explicit-plan.json'
    def save():
        plan.write_text(json.dumps({'boards': records}))
        return suite.sha(plan)
    return SimpleNamespace(plan=plan, records=records, paths=paths, lineage=lineage, save=save)


def test_renamed_two_board_plan_retains_exact_inputs_and_read_only_control(frontier):
    rows = suite.frontier_inputs(frontier.plan, frontier.save())
    assert [r['input'] for r in rows] == list(map(str, frontier.paths))
    assert [r['frontier_control_read_only'] for r in rows] == [False, True]
    cmd = suite.command(rows[0], '/private/out', trials=1, passes=1)
    assert cmd[cmd.index('--input-board')+1] == str(frontier.paths[0])
    assert '--allow-derived-input' in cmd
    assert '--replace-placement' not in cmd and '--fresh-placement-only' not in cmd
    with pytest.raises(ValueError, match='read-only'):
        suite.command(rows[1], '/private/out', trials=1, passes=1)


@pytest.mark.parametrize('artifact', ['plan', 'pcb', 'lineage'])
def test_stale_artifact_refuses_without_fallback(frontier, artifact):
    digest = frontier.save()
    path = {'plan': frontier.plan, 'pcb': frontier.paths[0], 'lineage': frontier.lineage}[artifact]
    path.write_text(path.read_text()+' ')
    with pytest.raises(ValueError, match='hash changed'):
        suite.frontier_inputs(frontier.plan, digest)


@pytest.mark.parametrize('bad', ['duplicate', 'unsupported', 'missing', 'boolean', 'partial-lineage', 'nonwave-positive'])
def test_invalid_inventory_refuses(frontier, bad):
    selected = None
    if bad == 'duplicate': frontier.records.append(dict(frontier.records[0]))
    if bad == 'unsupported': frontier.records[0]['board'] = 'not-manifest'
    if bad == 'missing': selected = ['missing-board']
    if bad == 'boolean': frontier.records[0]['expected_opens'] = True
    if bad == 'partial-lineage': del frontier.records[0]['lineage']
    if bad == 'nonwave-positive': frontier.records[1]['expected_opens'] = 1
    with pytest.raises(ValueError): suite.frontier_inputs(frontier.plan, frontier.save(), selected)


@pytest.mark.parametrize('description', ['Source manifest; fresh review required.', '/missing/unhashed/receipt.json'])
def test_unhashed_lineage_is_descriptive_not_verified(frontier, description):
    frontier.records[0]['lineage'] = description
    del frontier.records[0]['lineage_sha256']
    row = suite.frontier_inputs(frontier.plan, frontier.save())[0]
    assert row['continuation']['lineage'] == description
    assert row['continuation']['lineage_artifact_verified'] is False
    assert row['continuation']['lineage_sha256'] is None
    assert description not in [x['path'] for x in row['source_signature']['files']]


@pytest.mark.parametrize('failure', ['stale', 'missing-path', 'missing-hash'])
def test_declared_parent_requires_exact_complete_binding(frontier, failure):
    record = frontier.records[0]
    record.update(parent_path=str(frontier.lineage), parent_sha256=suite.sha(frontier.lineage))
    if failure == 'missing-path': del record['parent_path']
    if failure == 'missing-hash': del record['parent_sha256']
    digest = frontier.save()
    if failure == 'stale': frontier.lineage.write_text('changed')
    with pytest.raises(ValueError): suite.frontier_inputs(frontier.plan, digest)


def test_dispatch_revalidates_peer_record_not_just_selected_board(frontier):
    row = suite.frontier_inputs(frontier.plan, frontier.save(), ['renamed-main'])[0]
    frontier.paths[1].write_text('changed peer')
    with pytest.raises(ValueError): suite.command(row, '/out', trials=1, passes=1)


def test_assembly_selected_member_and_peer_are_bound_but_dispatch_unsupported(frontier):
    contract = frontier.plan.parent/'contract.json'; contract.write_text('{}')
    def file(path): return dict(path=str(path), sha256=suite.sha(path))
    instance = dict(schema=1, role='carrier', contract=file(contract),
                    members=dict(carrier=file(frontier.paths[0]), cover=file(frontier.paths[1])))
    frontier.records[0]['assembly_instance'] = instance
    row = suite.frontier_inputs(frontier.plan, frontier.save(), ['renamed-main'])[0]
    with pytest.raises(ValueError, match='context threading'):
        suite.command(row, '/out', trials=1, passes=1)
    instance['role'] = 'cover'
    with pytest.raises(ValueError, match='selected assembly member'):
        suite.frontier_inputs(frontier.plan, frontier.save())


def test_invalidated_frontier_never_silently_rebases(frontier, monkeypatch):
    import cec_interface_eco
    row = suite.frontier_inputs(frontier.plan, frontier.save(), ['renamed-main'])[0]
    monkeypatch.setattr(cec_interface_eco, 'read_status', lambda _: {'route_authority_invalidated': True})
    with pytest.raises(ValueError, match='explicit rebase'):
        suite.command(row, '/out', trials=1, passes=1)


def test_actual_coordinator_controls_never_launch_or_dispatch(frontier, monkeypatch):
    import cec_pass_review
    digest = frontier.save()
    monkeypatch.setattr(suite.manifest, 'validate', lambda _: [])
    monkeypatch.setattr(suite.manifest, 'PROJECTS', list(suite.manifest.BY_BOARD.values()))
    monkeypatch.setattr(cec_pass_review, 'gallery', lambda *a, **k: None)
    def forbidden(*a, **k): raise AssertionError('control attempted worker or geometry dispatch')
    monkeypatch.setattr(suite.subprocess, 'Popen', forbidden)
    monkeypatch.setattr(suite, 'geometry_dispatch_refusal', forbidden)
    out = frontier.plan.parent/'campaign'
    suite.main(['--out', str(out), '--frontier-plan', str(frontier.plan),
                '--expected-frontier-plan-sha256', digest, '--boards', 'renamed-control'])
    result = json.loads((out/'suite.json').read_text())['boards']['renamed-control']
    assert result['status'] == 'read_only_control'
    assert result['worker_launched'] is False and result['qualification_valid'] is False
    assert result['source_inputs_unchanged'] and result['source_board_unchanged']


@pytest.mark.parametrize('extra', [[], ['--input', 'x=y'], ['--continue-suite', 'old.json']])
def test_frontier_cli_conflicts_fail_before_manifest_or_output(tmp_path, extra):
    args = ['--out', str(tmp_path/'out'), '--frontier-plan', 'plan.json']
    if extra: args += ['--expected-frontier-plan-sha256', '0'*64] + extra
    with pytest.raises(SystemExit): suite.main(args)
    assert not (tmp_path/'out').exists()
