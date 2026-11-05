"""Real configured-warning DRC still rejects a completed join's new spur."""
import json
import os
from pathlib import Path

import pytest

import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_drc_runner as native
import cec_received_private_stage as stage
from test_lastmile import _board
from test_field_proposals import track


def test_completed_join_with_attached_orthogonal_spur_has_native_warning(tmp_path):
    build = os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:
        pytest.skip('cap-only native DRC reporting build not configured')
    board = _board([(5, 10, '/CONTROL'), (15, 10, '/CONTROL')], edge=(0, 0, 25, 25))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pad.SetNumber('1')
    # The parent is already completely connected. The only delta is an
    # orthogonal, full-width decorative stub attached to that real route.
    track(board, '/CONTROL', (5, 10), (10, 10), width=.22)
    track(board, '/CONTROL', (10, 10), (15, 10), width=.22)
    source = tmp_path / 'parent' / 'board.kicad_pcb'
    source.parent.mkdir()
    field._save_field_snapshot(board, source)
    # Explicit test fixture severity: WARNING, never ignored. Production
    # settings and canonical source boards are not used or changed.
    source.with_suffix('.kicad_pro').write_text(json.dumps({
        'board': {'design_settings': {'rule_severities': {'track_dangling': 'warning'}}},
        'net_settings': {'classes': [{'name': 'Default', 'track_width': .22,
                                      'clearance': .2, 'via_diameter': .6, 'via_drill': .3}]},
    }))
    child = force._copy_family(source, tmp_path / 'child')
    spur = track(board, '/CONTROL', (10, 10), (10, 12), width=.22)
    spur_uuid = force._uid(spur)
    field._save_field_snapshot(board, child)
    reports = []
    for label, path in [('parent', source), ('child', child)]:
        import pcbnew
        saved = pcbnew.LoadBoard(str(path))
        assert fr.net_connectivity_component_count(saved, saved.GetNetcodeFromNetname('/CONTROL')) == 1
        report_path = tmp_path / (label + '-native.json')
        proof = native.run(path, report_path, reporting_build=Path(build), timeout_s=10.)
        assert proof['ok'] and proof['complete'], proof
        reports.append(json.loads(report_path.read_text()))
    assert all(not report['unconnected_items'] for report in reports)
    warnings = [v for v in reports[1]['violations']
                if v['type'] == 'track_dangling' and v['severity'] == 'warning'
                and spur_uuid in {i.get('uuid') for i in v['items']}]
    assert warnings, reports[1]['violations']
    delta = stage.native_findings_delta(*reports)
    assert not delta['ok']
    assert delta['introduced_native_findings']
    assert not delta['inherited_findings_qualified']
