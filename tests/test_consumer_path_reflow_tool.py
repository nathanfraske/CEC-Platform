"""Whole-path geometry never supplies or weakens consumer-current authority."""
import copy,json,runpy,time
from pathlib import Path
import pcbnew
import pytest
import cec_consumer_group_reconstruction as owner
import cec_field_coupling as field
import cec_force_current as force
import cec_native_drc_runner as native
from test_consumer_corner_miter_tool import case,BUILD
from test_field_proposals import track

TOOL=Path(__file__).resolve().parents[1]/'ops/cec_consumer_path_reflow.py'


def api():return runpy.run_path(str(TOOL))


def baseline(tmp_path,source):
    shadow=force._copy_family(source,tmp_path/'native-source');report=tmp_path/'source.drc.json'
    producer=native.run(shadow,report,reporting_build=BUILD,timeout_s=10.)
    assert producer['ok'] and producer['complete'] and not producer['native_inventory']['potentially_truncated']
    assert not json.loads(report.read_text())['unconnected_items']
    grade=tmp_path/'baseline.json';force._write(grade,dict(code_identity=force._code_identity(),
        boards=dict(candidate=dict(sha256=force._hash(source),native_producer=producer))))
    return grade


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_whole_group_zigzag_reflow_preserves_actual_tap_contacts_budget_and_process(tmp_path,monkeypatch,quarter,mirror):
    source,b,row,domain,downstream=case(tmp_path,monkeypatch,quarter=quarter,mirror=mirror)
    original=source.read_bytes();budget=copy.deepcopy((row,domain,downstream));functions=api()
    result=functions['run'](source,tmp_path/'work',board_hint='synthetic',expected_source_sha256=force._hash(source),
        grade=baseline(tmp_path,source),reporting_build=BUILD,allow_locked_source=True)
    assert result['ok'] and result['complete'] and result['changed'],result
    proof=result['independent_source_consumer_receiving']
    assert proof['ok'] and proof['complete'] and not proof['errors']
    assert proof['independently_rederived_native_contacts']
    received=proof['source_consumer_receiving']
    assert received['all_original_surviving_partitions_preserved'] and received['exact_native_ground_refill_replayed']
    assert received['source_scope']['source_budget']['current_authority']['amps']==3.0004
    assert received['source_scope']['source_budget']['aggregate_current_authority']['amps']==20.
    assert not received['source_current_reduced'] and not received['branch_sharing_assumed']
    assert result['actual_length_removed_mm']>0 and result['removed_source_strokes']>0 and result['removed_bend_flags']>0
    assert not result['attempts'][-1]['new_native_faults'] and not result['attempts'][-1]['opens']
    assert result['source_family_and_code_unchanged'] and source.read_bytes()==original and (row,domain,downstream)==budget
    assert not result['fab_ready'] and not result['release_authority']
    again=functions['receive'](source,result['candidate'],board_hint='synthetic',**result['records'][0]['plan'])
    assert again['ok'] and again['complete'] and again['independently_rederived_native_contacts']


@pytest.mark.parametrize('fault',['unknown_group','wrong_package','underwidth','masked','second_tap','lowered_allocation','inner_outer_width'])
def test_no_reclassification_or_budget_waiver_on_whole_path(tmp_path,monkeypatch,fault):
    source,b,*_=case(tmp_path,monkeypatch,fault=fault);before=source.read_bytes()
    result=api()['inventory'](b,source,board_hint='synthetic',allow_locked_source=True)
    assert not result['offers'] and source.read_bytes()==before


@pytest.mark.parametrize('options',[dict(max_source_tracks=2),dict(max_source_tracks=17),dict(max_source_tracks=True),
    dict(max_windows=0),dict(max_windows=129),dict(max_windows=True),dict(max_templates=0),dict(max_templates=129),
    dict(max_templates=True),dict(allow_locked_source='yes')])
def test_whole_path_search_has_typed_finite_bounds(tmp_path,monkeypatch,options):
    source,b,*_=case(tmp_path,monkeypatch)
    with pytest.raises(ValueError):api()['inventory'](b,source,board_hint='synthetic',**options)


def test_locked_source_needs_explicit_whole_path_permission(tmp_path,monkeypatch):
    source,b,*_=case(tmp_path,monkeypatch)
    result=api()['inventory'](b,source,board_hint='synthetic')
    assert not result['offers'] and not result['source_mutated']


def test_source_hash_is_checked_before_grade_or_output(tmp_path,monkeypatch):
    source,b,*_=case(tmp_path,monkeypatch);out=tmp_path/'must-not-exist'
    with pytest.raises(ValueError,match='source_hash'):
        api()['run'](source,out,board_hint='synthetic',expected_source_sha256='0'*64,grade=tmp_path/'not-read.json',reporting_build=BUILD)
    assert not out.exists()


def test_shortcut_cannot_discard_a_midpath_native_pad_contact(tmp_path,monkeypatch):
    source,b,*_=case(tmp_path,monkeypatch);functions=api()
    candidates,_=functions['windows'](b,allow_locked_source=True,max_source_tracks=8,max_windows=64)
    selection=max(candidates,key=lambda q:len(q['source_track_uuids']))
    # Source fixture's long detour passes (12,15); a native same-net pad
    # there is a genuine tap, not a cosmetic endpoint-only constraint.
    old=[t for t in b.GetTracks() if force._uid(t) in selection['source_track_uuids']]
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('SYNTHETIC_TAP');b.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
    pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4));pad.SetLayerSet(layers);pad.SetNet(old[0].GetNet())
    fp.Add(pad);pad.SetPosition(pcbnew.VECTOR2I_MM(12,15));field._save_field_snapshot(b,source)
    points=functions['geometry']._tangent_paths(selection['source_points_nm'])[0]
    with pytest.raises(ValueError,match='side_contact|single|tap|consumer'):
        functions['plan'](b,source,board_hint='synthetic',retired_track_uuids=selection['source_track_uuids'],points_nm=points,allow_locked_source=True)


def test_receiving_does_not_trust_claimed_replacement_points(tmp_path,monkeypatch):
    source,b,*_=case(tmp_path,monkeypatch);functions=api()
    result=functions['run'](source,tmp_path/'work',board_hint='synthetic',expected_source_sha256=force._hash(source),
        grade=baseline(tmp_path,source),reporting_build=BUILD,allow_locked_source=True)
    assert result['changed'],result
    claim=copy.deepcopy(result['records'][0]['plan']);claim['points_nm'][0][0]+=1
    refused=functions['receive'](source,result['candidate'],board_hint='synthetic',**claim)
    assert not refused['ok'] and refused['errors']
