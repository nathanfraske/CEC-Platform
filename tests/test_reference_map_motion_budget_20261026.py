"""Explicit annotation work bounds never grant physical macro authority."""
import copy
import pcbnew
import pytest
import cec_cell_row_rebuild as row
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as macro
import cec_source_reference_group_transport as reference
import cec_source_reference_group_cardinal_batch as cardinal
import cec_force_current as force
from test_source_reference_group_cardinal import fixture


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('source_turn',[0,90,180,270])
@pytest.mark.parametrize('turn',[0,1])
def test_explicit_large_actual_macro_and_fresh_saved_replay(tmp_path,back,source_turn,turn):
    source,proof=fixture(tmp_path,back=back,source_turn=source_turn,external=True)
    original=source.read_bytes();parent=pcbnew.LoadBoard(str(source))
    poses={'X7':[22.,10.,(source_turn+turn*90)%360]}
    args=dict(reference_group_uuids=[proof['group_uuid']],allow_cardinal_rotations=True)
    with pytest.raises(ValueError,match='bounded_literal_translation'):
        row.plan(parent,poses,{},**args)
    plan=row.plan(parent,poses,{},maximum_reference_translation_mm=24.,**args)
    proposal=dict(poses=poses,row_plan=plan,board_hint='synthetic',max_shift_mm=24.,
        allow_owned_locked_escapes=True,reference_group_uuids=[proof['group_uuid']])
    actual,received=compiler._frame(parent,source,proposal)
    assert received and tuple(actual.FindFootprintByReference('X7').GetPosition())==(22000000,10000000)
    assert next(iter(actual.Groups())).IsLocked()
    candidate=tmp_path/'candidate.kicad_pcb'
    packet=dict(scope='source_typed_complete_native_macro_requests',source=str(source),
        source_sha256=force._hash(source),code_identity=force._code_identity(),source_plan=proposal)
    result=macro.save_private(actual,candidate,packet)
    assert result['literal_source_reference_save']
    delta=(12000000,0)
    if turn:
        requests=[(proof,turn,delta)]
        assert cardinal.verify(source,candidate,requests,maximum_translation_mm=24.)['ok']
        assert reference.verify_cardinal(source,candidate,proof,quarter_turns=turn,
            delta_nm=delta,maximum_translation_mm=24.)['ok']
        with pytest.raises(ValueError):cardinal.verify(source,candidate,requests)
    else:
        assert reference.verify(source,candidate,proof,delta_nm=delta,maximum_translation_mm=24.)['ok']
        with pytest.raises(ValueError):reference.verify(source,candidate,proof,delta_nm=delta)
    assert source.read_bytes()==original
    assert not result['routing_admitted'] and not result['release_authority']


@pytest.mark.parametrize('bound',[True,0,-1,64.000001,float('nan'),float('inf'),'24',None])
def test_nonfinite_or_overscope_policy_refused(tmp_path,bound):
    source,proof=fixture(tmp_path)
    with pytest.raises(ValueError):reference.transform(pcbnew.LoadBoard(str(source)),proof,
        delta_nm=(12000000,0),maximum_translation_mm=bound)
    with pytest.raises(ValueError):cardinal.expected_nodes([(proof,1,(12000000,0))],
        maximum_translation_mm=bound)


@pytest.mark.parametrize('fault',['overscope','fakeproof','fraction','booldelta','stale_source'])
@pytest.mark.parametrize('turn',[0,1])
def test_explicit_budget_cannot_weaken_independent_source_proof(tmp_path,fault,turn):
    source,proof=fixture(tmp_path)
    delta=(12000000,0)
    if fault=='overscope':delta=(24000001,0)
    elif fault=='fakeproof':proof=copy.deepcopy(proof);proof['member_uuids'].append('forged')
    elif fault=='fraction':delta=(12000000.5,0)
    elif fault=='booldelta':delta=(True,0)
    else:source.write_text(source.read_text().replace('"X7"','"X8"'))
    board=pcbnew.LoadBoard(str(source));before=reference._cardinal_identity(board)
    with pytest.raises(ValueError):
        if turn:cardinal.transform_many(board,[(proof,turn,delta)],maximum_translation_mm=24.)
        else:reference.transform(board,proof,delta_nm=delta,maximum_translation_mm=24.)
    assert reference._cardinal_identity(board)==before


def test_row_bound_is_part_of_independent_plan_replay(tmp_path):
    source,proof=fixture(tmp_path);board=pcbnew.LoadBoard(str(source))
    plan=row.plan(board,{'X7':[22.,10.,0.]},{},reference_group_uuids=[proof['group_uuid']],
        maximum_reference_translation_mm=24.)
    forged=copy.deepcopy(plan);del forged['maximum_reference_translation_mm']
    with pytest.raises(ValueError):row.apply(board,forged)
    row.apply(board,plan)
    assert reference.verify_native(source,board,[(proof,(12000000,0))],maximum_translation_mm=24.)['ok']


def test_absolute_native_annotation_cap_remains_64mm():
    assert reference._delta((64000000,-64000000),64.)==(64000000,-64000000)
    with pytest.raises(ValueError):reference._delta((64000001,0),64.)


def test_large_annotation_budget_does_not_enlarge_physical_macro_budget(tmp_path):
    source,proof=fixture(tmp_path);parent=pcbnew.LoadBoard(str(source))
    poses={'X7':[22.,10.,0.]}
    plan=row.plan(parent,poses,{},reference_group_uuids=[proof['group_uuid']],
        maximum_reference_translation_mm=24.)
    proposal=dict(poses=poses,row_plan=plan,board_hint='synthetic',max_shift_mm=10.,
        allow_owned_locked_escapes=True,reference_group_uuids=[proof['group_uuid']])
    with pytest.raises(ValueError):compiler._frame(parent,source,proposal)


@pytest.mark.parametrize('turn',[0,1])
def test_large_saved_receiver_refuses_unrelated_mutation(tmp_path,turn):
    import cec_field_coupling as field
    source,proof=fixture(tmp_path);board=pcbnew.LoadBoard(str(source));delta=(12000000,0)
    if turn:cardinal.transform_many(board,[(proof,turn,delta)],maximum_translation_mm=24.)
    else:reference.transform(board,proof,delta_nm=delta,maximum_translation_mm=24.)
    next(iter(board.GetFootprints())).SetValue('not-source')
    candidate=tmp_path/'forged.kicad_pcb';field._save_field_snapshot(board,candidate)
    with pytest.raises(ValueError):
        if turn:cardinal.verify(source,candidate,[(proof,turn,delta)],maximum_translation_mm=24.)
        else:reference.verify(source,candidate,proof,delta_nm=delta,maximum_translation_mm=24.)
