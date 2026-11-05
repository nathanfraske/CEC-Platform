"""Broader native reports must bind their producer, not merely its version."""
import hashlib
import math
from pathlib import Path

import pytest

import cec_native_drc_inventory as inventory
import cec_native_drc_runner as runner
from test_native_drc_inventory import report


def test_cap_only_source_changes_exactly_two_reporting_constants():
    official='before\n#define ERROR_LIMIT 199\ngeometry_check();\n#define EXTENDED_ERROR_LIMIT 499\nfinish();\n'
    expected='before\n#define ERROR_LIMIT 20000\ngeometry_check();\n#define EXTENDED_ERROR_LIMIT 20000\nfinish();\n'
    assert runner._cap_only_source(official)==expected
    assert runner._cap_only_source(official).replace('20000','199',1).replace('20000','499',1)==official


@pytest.mark.parametrize('bad',[None,True,'','#define ERROR_LIMIT 200\n#define EXTENDED_ERROR_LIMIT 499\n',
    '#define ERROR_LIMIT 199\n#define ERROR_LIMIT 199\n#define EXTENDED_ERROR_LIMIT 499\n',
    '#define ERROR_LIMIT 199\n#define EXTENDED_ERROR_LIMIT 500\n'])
def test_unverified_official_source_never_receives_a_reporting_profile(bad):
    with pytest.raises(ValueError):runner._cap_only_source(bad)


@pytest.mark.parametrize('count,opens,saturated',[(199,0,False),(499,0,False),(19999,0,False),
    (20000,0,True),(20001,0,True),(0,19999,False),(0,20000,True)])
def test_verified_higher_caps_still_report_saturation_and_never_waive_faults(count,opens,saturated):
    original=report(count=count,opens=opens)
    result=inventory._assess_verified_limits(original,20000,20000,'producer-bound-test')
    assert result['category_limits_checked'] and result['potentially_truncated'] is saturated
    assert result['reported_unconnected_count']==opens
    assert result['reported_violation_counts'].get('silk_overlap',0)==count
    assert result['faults_suppressed']==0 and result['admission_unchanged']
    assert not result['full_native_inventory_proved'] and not result['release_authority']


@pytest.mark.parametrize('timeout',[0,True,math.nan,math.inf,11])
def test_unbounded_native_deadlines_refuse_without_launching_or_writing(tmp_path,timeout):
    result=runner.run(tmp_path/'nonexistent.kicad_pcb',tmp_path/'report.json',timeout_s=timeout)
    assert not result['ok'] and result['errors'] and not result['release_authority']
    assert not (tmp_path/'report.json').exists()


def test_native_artifact_hashes_have_an_explicit_byte_bound(tmp_path):
    path=tmp_path/'small-native-artifact';path.write_bytes(b'known-native-bytes')
    assert runner._hash(path)==hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):runner._hash(path,limit=2)


@pytest.mark.parametrize('bad_output',['existing.json','source.drc.json','source.kicad_pcb','not-a-report.txt'])
def test_report_output_cannot_overwrite_or_join_the_immutable_board_family(tmp_path,bad_output):
    board=tmp_path/'source.kicad_pcb';board.write_text('(kicad_pcb)')
    existing=tmp_path/'existing.json';existing.write_text('keep')
    original=board.read_bytes()
    result=runner.run(board,tmp_path/bad_output)
    assert not result['ok'] and result['errors'] and not result['release_authority']
    assert board.read_bytes()==original and existing.read_text()=='keep'


def test_nonexistent_reporting_build_cannot_claim_higher_caps(tmp_path):
    board=tmp_path/'source.kicad_pcb';board.write_text('(kicad_pcb)')
    result=runner.run(board,tmp_path/'report.json',reporting_build=tmp_path/'unverified-build')
    assert not result['ok'] and result['errors'] and not result['release_authority']
    assert not (tmp_path/'report.json').exists()


def test_actual_stock_report_requests_all_track_errors_and_preserves_saved_source(tmp_path):
    import pcbnew
    import cec_field_coupling as field
    import cec_toolchain as toolchain
    if not toolchain.have_kicad_cli():pytest.skip('native CLI required for exact producer integration')
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    for start,end in [((0,0),(20,0)),((20,0),(20,20)),((20,20),(0,20)),((0,20),(0,0))]:
        shape=pcbnew.PCB_SHAPE(board);shape.SetShape(pcbnew.SHAPE_T_SEGMENT);shape.SetLayer(pcbnew.Edge_Cuts)
        shape.SetStart(pcbnew.VECTOR2I_MM(*start));shape.SetEnd(pcbnew.VECTOR2I_MM(*end));board.Add(shape)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source);original=source.read_bytes()
    result=runner.run(source,tmp_path/'native-report.json')
    assert result['ok'] and result['complete'],result
    assert '--all-track-errors' in result['command'] and '--severity-all' in result['command']
    assert '--save-board' not in result['command'] and '--refill-zones' not in result['command']
    assert result['source_and_producer_unchanged'] and result['report_sha256']==runner._hash(tmp_path/'native-report.json')
    assert not result['release_authority'] and not result['native_inventory']['full_native_inventory_proved']
    assert source.read_bytes()==original
