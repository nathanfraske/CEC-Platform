"""Native/source handoff identity only: no construction or acceptance mocks."""
import copy
import time
from pathlib import Path

import pcbnew
import pytest
import cec_source_role_handoff as op
from test_programming_resistor_placement import fixture as source_fixture


def fixture(tmp_path,monkeypatch,canonical=True):
    board,owner,cap,root,tree,poses=source_fixture(tmp_path,monkeypatch)
    evidence=tmp_path/'reviewed-source.txt';evidence.write_text('reviewed fixture evidence')
    roles=dict(synthetic_role=dict(source_proof=dict(evidence_files_sha256={
        str(evidence):op.force._hash(evidence)}),current_authority=False))
    options=dict(allow_linear_power_stage_reconstruction=False)
    if not canonical:monkeypatch.setattr(op.canonical.source_nc,'_root',lambda *a:None)
    return board,owner,cap,root,poses,roles,options,evidence


def capture(board,poses,root,roles,options,**kw):
    return op.capture(board,poses,board_hint=str(root),roles=roles,options=options,
        deadline=kw.pop('deadline',time.monotonic()+9.),**kw)


def check(snapshot,board,poses,root,roles,options,**kw):
    return op.assert_same(snapshot,board,poses,board_hint=str(root),roles=roles,options=options,
        deadline=kw.pop('deadline',time.monotonic()+9.),**kw)


@pytest.mark.parametrize('canonical',[False,True])
def test_fresh_handoff_is_plain_independent_JSON_no_authority(tmp_path,monkeypatch,canonical):
    board,owner,cap,root,poses,roles,options,evidence=fixture(tmp_path,monkeypatch,canonical)
    source=Path(board.GetFileName()).read_bytes();before=op.row._source_binding(board)
    snapshot=capture(board,poses,root,roles,options)
    assert snapshot==capture(board,poses,root,roles,options)
    assert check(snapshot,board,poses,root,roles,options)
    assert snapshot['payload']['canonical_inputs']is not None if canonical else snapshot['payload']['canonical_inputs']is None
    assert snapshot['payload']['admission_authority']is False
    assert snapshot['payload']['motion_authority']is False
    assert Path(board.GetFileName()).read_bytes()==source and before==op.row._source_binding(board)


@pytest.mark.parametrize('mutation',['field','pin_type','pin_name','path','pose','reference','options',
    'roles','bool_to_int','source_bytes','project','canonical','evidence','environment','other_board'])
def test_native_and_role_input_changes_are_not_a_saved_handoff(tmp_path,monkeypatch,mutation):
    board,owner,cap,root,poses,roles,options,evidence=fixture(tmp_path,monkeypatch)
    snapshot=capture(board,poses,root,roles,options)
    if mutation=='field':owner.SetField('Manufacturer','changed manufacturer')
    elif mutation=='pin_type':owner.FindPadByNumber('11').SetPinType('passive')
    elif mutation=='pin_name':owner.FindPadByNumber('11').SetPinFunction('not SS')
    elif mutation=='path':owner.SetPath(pcbnew.KIID_PATH('/00000000-0000-0000-0000-000000000001'))
    elif mutation=='pose':poses[cap.GetReference()][0]+=.1
    elif mutation=='reference':cap.SetReference('renamed participant')
    elif mutation=='options':options['allow_linear_power_stage_reconstruction']=True
    elif mutation=='roles':roles['synthetic_role']['current_authority']=True
    elif mutation=='bool_to_int':roles['synthetic_role']['current_authority']=0
    elif mutation=='source_bytes':
        path=Path(board.GetFileName());path.write_bytes(path.read_bytes()+b'\n; changed Source\n')
    elif mutation=='project':Path(board.GetFileName()).with_suffix('.kicad_pro').write_text('{}')
    elif mutation=='canonical':root.write_text(root.read_text()+'\n; changed canonical hierarchy\n')
    elif mutation=='evidence':evidence.write_text('changed reviewed evidence')
    elif mutation=='environment':monkeypatch.setenv('CEC_TEST_HANDOFF_EPOCH','changed')
    else:board=pcbnew.LoadBoard(board.GetFileName())
    with pytest.raises(ValueError):check(snapshot,board,poses,root,roles,options)


@pytest.mark.parametrize('mutation',['code','exporter','root_project','library_table'])
def test_code_exporter_and_canonical_input_fences(tmp_path,monkeypatch,mutation):
    board,owner,cap,root,poses,roles,options,evidence=fixture(tmp_path,monkeypatch)
    snapshot=capture(board,poses,root,roles,options)
    if mutation=='code':monkeypatch.setattr(op.force,'_code_identity',lambda:dict(synthetic_changed_code=True))
    elif mutation=='exporter':
        import cec_toolchain as tc
        other=tmp_path/'other-cli';other.write_text('not observed CLI')
        monkeypatch.setattr(tc,'require_kicad_cli',lambda *a:str(other))
    elif mutation=='root_project':root.with_suffix('.kicad_pro').write_text('{}')
    else:(root.parent/'sym-lib-table').write_text('(sym_lib_table)')
    with pytest.raises(ValueError):check(snapshot,board,poses,root,roles,options)


def test_all_native_metadata_not_only_binding_is_observed(tmp_path,monkeypatch):
    board,owner,cap,root,poses,roles,options,evidence=fixture(tmp_path,monkeypatch)
    before=op.row._source_binding(board);snapshot=capture(board,poses,root,roles,options)
    owner.SetField('Manufacturer','different identity');owner.FindPadByNumber('11').SetPinType('passive')
    assert before==op.row._source_binding(board)
    with pytest.raises(ValueError,match='live_inputs_changed'):check(snapshot,board,poses,root,roles,options)


def test_nested_proof_evidence_rederived_and_forged_snapshot_refused(tmp_path,monkeypatch):
    board,owner,cap,root,poses,roles,options,evidence=fixture(tmp_path,monkeypatch)
    roles=dict(nested=[dict(deeper=dict(source_proof=dict(evidence_files_sha256={
        str(evidence):op.force._hash(evidence)})))])
    snapshot=capture(board,poses,root,roles,options)
    assert snapshot['payload']['role_evidence_files'][str(evidence)]==op.force._hash(evidence)
    forged=copy.deepcopy(snapshot);forged['payload']['admission_authority']=True
    with pytest.raises(ValueError,match='live_inputs_changed'):check(forged,board,poses,root,roles,options)


@pytest.mark.parametrize('offset',[0,-1,11,True,float('nan'),float('inf')])
def test_bounded_real_absolute_deadline(tmp_path,monkeypatch,offset):
    board,owner,cap,root,poses,roles,options,evidence=fixture(tmp_path,monkeypatch)
    deadline=offset if type(offset)is bool else time.monotonic()+offset
    with pytest.raises(ValueError,match='bounded_source_role_handoff_deadline'):
        capture(board,poses,root,roles,options,deadline=deadline)


@pytest.mark.parametrize('value',[{1:'coerced key'},dict(nonfinite=float('nan')),dict(native=object())])
def test_non_JSON_inputs_refused(tmp_path,monkeypatch,value):
    board,owner,cap,root,poses,roles,options,evidence=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='JSON'):capture(board,poses,root,value,options)
