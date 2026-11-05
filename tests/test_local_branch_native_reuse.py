"""Reuse one real native snapshot, never a caller verdict or a stale cache."""
import copy
import cec_swig_guard
cec_swig_guard.pin()
import wx
QUIET = wx.LogNull()
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_local_branch_access as access
import cec_placement_geometry as geometry
from test_measurement_leaf_reflow import reflow_fixture


def test_receiver_uses_exactly_two_real_native_runs_without_dropping_placement(tmp_path,monkeypatch):
    source,child,pad=reflow_fixture(tmp_path)
    before=[p.read_bytes()for p in(source,child)]
    run=access.subprocess.run;calls=[]
    def counted(command,*args,**kwargs):
        if command[:3]==['kicad-cli','pcb','drc']:
            assert '--severity-all'in command
            calls.append(command)
        return run(command,*args,**kwargs)
    actual_reuse=access._fresh_native_placement;diagnostics=[]
    def observed(actual,path,snapshot,data,**kwargs):
        ids=[m.group(3).lower()for m in fr._BOARD_UUID_RE.finditer(snapshot.read_text())]
        result=actual_reuse(actual,path,snapshot,data,**kwargs)
        a,b=force._sidecars(snapshot),force._sidecars(path)
        if result is None:diagnostics.append(dict(unique=len(ids)==len(set(ids)),
            bytes_equal=force._hash(snapshot)==force._hash(path),
            differing_companions={key:[a.get(key),b.get(key)]for key in a.keys()|b.keys()if a.get(key)!=b.get(key)},
            native_equal=field._field_snapshot_inventory(pcbnew.LoadBoard(str(snapshot)))
                ==field._field_snapshot_inventory(actual)))
        return result
    def duplicate(*args,**kwargs):raise AssertionError('third_native_DRC_not_needed_for_exact_snapshot:'+repr(diagnostics))
    monkeypatch.setattr(access.subprocess,'run',counted)
    monkeypatch.setattr(geometry,'evaluate',duplicate)
    monkeypatch.setattr(access,'_fresh_native_placement',observed)
    result=access.receive_measurement_reflow(source,child,board_hint='fixture',pad_uuid=pad)
    assert result['ok'] is True and result['complete'] is True,result['errors']
    assert len(calls)==2
    physical=result['physical_placement']
    assert physical['ok'] is True and 'physical_body'in physical
    assert physical['exact_snapshot_and_native_rule_companions_rechecked'] is True
    assert physical['reused_current_receiver_native_report'] is True
    assert not result['release_authority'] and not result['kelvin_qualified']
    assert [p.read_bytes()for p in(source,child)]==before


@pytest.mark.parametrize('fault',['duplicate_ids','case_duplicate_ids','different_copper',
    'different_courtyard','different_companion','different_opaque_companion',
    'different_existing_preferences','changed_pre_run_copy','in_memory_drift'])
def test_any_snapshot_identity_geometry_or_rule_difference_cannot_reuse(tmp_path,fault):
    _,child,_=reflow_fixture(tmp_path)
    if fault=='different_existing_preferences':child.with_suffix('.kicad_prl').write_text('{}\n')
    actual=pcbnew.LoadBoard(str(child));snapshot=force._copy_family(child,tmp_path/'native-snapshot')
    input_companions=force._sidecars(snapshot)
    if fault in('duplicate_ids','case_duplicate_ids'):
        text=snapshot.read_text();matches=list(fr._BOARD_UUID_RE.finditer(text))
        first,second=matches[:2];replacement=first.group(3)
        if fault=='case_duplicate_ids':replacement=replacement.upper()
        text=text[:second.start(3)]+replacement+text[second.end(3):]
        snapshot.write_text(text)
    elif fault=='different_companion':snapshot.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='different_opaque_companion':snapshot.with_suffix('.pourplan.json').write_text('{}\n')
    elif fault=='different_existing_preferences':snapshot.with_suffix('.kicad_prl').write_text('{"changed":true}\n')
    elif fault=='changed_pre_run_copy':input_companions=dict(input_companions,**{'.kicad_dru':'forged'})
    elif fault=='in_memory_drift':
        next(iter(actual.GetTracks())).SetWidth(333333)
    else:
        changed=pcbnew.LoadBoard(str(snapshot))
        if fault=='different_copper':next(iter(changed.GetTracks())).SetWidth(333333)
        else:
            fp=changed.FindFootprintByReference('INPUT_STAGE')
            next(item for item in fp.GraphicalItems()if item.GetLayer()==pcbnew.F_CrtYd).Move(pcbnew.VECTOR2I_MM(1,0))
        field._save_field_snapshot(changed,snapshot)
    assert access._fresh_native_placement(actual,child,snapshot,{'violations':[]},
        input_companions=input_companions) is None


def test_only_new_disposable_native_preferences_are_non_authoritative_output(tmp_path):
    _,child,_=reflow_fixture(tmp_path)
    before=force._sidecars(child)
    actual=pcbnew.LoadBoard(str(child));snapshot=force._copy_family(child,tmp_path/'native-snapshot')
    input_companions=force._sidecars(snapshot)
    snapshot.with_suffix('.kicad_prl').write_text('{"pcbnew":{"window":[]}}\n')
    proof=access._fresh_native_placement(actual,child,snapshot,{'violations':[]},
        input_companions=input_companions)
    assert proof['native_generated_local_preferences_only'] is True
    assert proof['exact_snapshot_and_native_rule_companions_rechecked'] is True
    assert force._sidecars(child)==before


def test_snapshot_classifier_keeps_raw_electrical_rows_and_body_and_structural_checks(tmp_path,monkeypatch):
    import cec_score
    import cec_physical_body
    _,child,_=reflow_fixture(tmp_path);board=pcbnew.LoadBoard(str(child))
    pad=board.FindFootprintByReference('INPUT_STAGE').FindPadByNumber('4')
    qualified=dict(type='copper_edge_clearance',severity='error',items=[dict(uuid=force._uid(pad))])
    raw={'violations':[qualified]};before=copy.deepcopy(raw)
    calls=[]
    def qualify(rows,actual):
        assert actual is board and rows==[qualified];calls.append('structural');return []
    def body(actual,**kwargs):
        assert actual is board;calls.append('body')
        return {'violations':[dict(uuid=force._uid(pad.GetParentFootprint()),ref='INPUT_STAGE')]}
    monkeypatch.setattr(cec_score,'qualify_structural_violations',qualify)
    monkeypatch.setattr(cec_physical_body,'audit',body)
    result=geometry._classify_native_snapshot(board,raw)
    assert calls==['structural','body'] and raw==before
    assert result['qualified_edge_count']==1
    assert result['ok'] is False and result['type_counts']['physical_body_envelope_missing']==1


@pytest.mark.parametrize('report',[None,{},[],{'violations':None}])
def test_missing_native_rows_are_not_a_clean_snapshot(tmp_path,report):
    _,child,_=reflow_fixture(tmp_path)
    with pytest.raises(ValueError,match='native DRC lacks'):
        geometry._classify_native_snapshot(pcbnew.LoadBoard(str(child)),report)
