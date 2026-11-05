"""Explicit cell authority transports readable maps without weakening groups.

Included by the active model-directed CI test inventory.
"""
import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_complete_cell_receiving as receiving
import cec_field_coupling as field
import cec_source_reference_group_transport as annotations
from cec_pipeline import cells, protocol
from test_source_reference_group_transport import external_fixture


def operation(group):
    return dict(kind='place_cell', poses=[dict(reference='X7', at_nm=[10250000,10000000],
        rotation_deg=90)],routes=[],allow_locked_footprint_uuids=[],
        allow_locked_track_uuids=[],reference_group_uuids=[group])


def test_pipeline_plan_forwards_only_explicit_annotation_authority(tmp_path,monkeypatch):
    source,owner,group=external_fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));seen=[]
    def prepare(board,poses,**options):
        seen.append((poses,options));return dict(retired_track_uuids=[])
    monkeypatch.setattr(escape,'prepare',prepare)
    _,moved=cells.plan(board,operation(group),'opaque')
    assert moved=={'X7'}
    assert seen[0][1]['reference_group_uuids']==[group]
    assert seen[0][0]['X7']==[10.25,10.,90]
    plain=operation(group);plain.pop('reference_group_uuids')
    cells.plan(board,plain,'opaque')
    assert seen[1][1]['reference_group_uuids']==[]
    assert next(iter(board.Groups())).IsLocked()
    assert not next(iter(board.GetFootprints())).IsLocked()


@pytest.mark.parametrize('scope',[True,[True],[''],['same','same'],['x']*9])
def test_pipeline_plan_rejects_invalid_annotation_scope_before_prepare(tmp_path,monkeypatch,scope):
    source,_,group=external_fixture(tmp_path);op=operation(group)
    op['reference_group_uuids']=scope
    monkeypatch.setattr(escape,'prepare',lambda *a,**k:pytest.fail('invalid scope reached compiler'))
    with pytest.raises(ValueError,match='explicit_source_reference_group_uuid_scope'):
        cells.plan(pcbnew.LoadBoard(str(source)),op,'opaque')


def test_annotation_scope_is_exposed_in_both_cell_schemas():
    cell=next(o for o in protocol._OPERATIONS if o['properties']['kind']['const']=='place_cell')
    for schema in [cell['properties']['reference_group_uuids'],
            protocol.TOOL_PARAMETERS['plan_cell']['reference_group_uuids']]:
        assert schema['maxItems']==8 and schema['uniqueItems']
        assert schema['items']['minLength']==1


def test_stationary_grouped_context_never_grants_group_motion(tmp_path):
    source,_,_=external_fixture(tmp_path);board=pcbnew.LoadBoard(str(source))
    proposal=row.plan(board,{'X7':[10.,10.,0.]},{})
    before=row._source_binding(board)
    assert not proposal.get('source_reference_group_transports')
    row.apply(board,proposal)
    assert row._source_binding(board)==before
    for pose in [[10.000001,10.,0.],[10.,10.,90.]]:
        with pytest.raises(ValueError,match='unlocked_translation_only'):
            row.plan(board,{'X7':pose},{},allow_cardinal_rotations=True)


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('fault',['text_drift','group_unlock','owner_lock'])
def test_saved_receiver_rederives_cardinal_map_and_rejects_annotation_drift(tmp_path,turn,fault):
    source,owner,group=external_fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source))
    proof=annotations.inspect(source,owner_uuid=owner,group_uuid=group)
    proposal=row.plan(board,{'X7':[10.25,10.,90.*turn]},{},
        reference_group_uuids=[group],allow_cardinal_rotations=True)
    row.apply(board,proposal)
    target=tmp_path/'candidate.kicad_pcb';field._save_field_snapshot(board,target)
    if turn:
        import cec_complete_macro_cell as complete
        complete._save_cardinal_reference_nodes(target,[(proof,turn,(250000,0))])
    plan=dict(row_plan=proposal,max_shift_mm=6.)
    receiving._receive_reference_transports(target,plan)
    changed=pcbnew.LoadBoard(str(target))
    if fault=='text_drift':
        text=next(i for i in changed.GetDrawings() if i.GetClass()=='PCB_TEXT')
        text.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='group_unlock':next(iter(changed.Groups())).SetLocked(False)
    else:next(iter(changed.GetFootprints())).SetLocked(True)
    field._save_field_snapshot(changed,target)
    with pytest.raises(ValueError,match='cardinal_transport_differs'):
        receiving._receive_reference_transports(target,plan)


def test_saved_annotation_receiver_cannot_truncate_noncardinal_turn(tmp_path):
    source,owner,group=external_fixture(tmp_path)
    proof=annotations.inspect(source,owner_uuid=owner,group_uuid=group)
    plan=dict(row_plan=dict(source_reference_group_transports={'X7':proof},
        source_poses={'X7':[10.,10.,0.]},target_poses={'X7':[10.,10.,45.]}),max_shift_mm=6.)
    with pytest.raises(ValueError,match='cardinal_rotation_required'):
        receiving._receive_reference_transports(source,plan)


@pytest.mark.parametrize('turn',range(4))
def test_connected_constructor_retains_exact_annotation_ast_and_unowned_groups(tmp_path,monkeypatch,turn):
    """Exercise the real native-save/AST-retention boundary, not a mock writer."""
    import cec_additive_route_receiving as syntax
    import cec_copper_echo as echo
    import cec_force_current as force
    from cec_pipeline import construction

    source,owner,group=external_fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source))
    other=pcbnew.PCB_GROUP(board);other.SetName('unowned_context');board.Add(other)
    text=pcbnew.PCB_TEXT(board);text.SetText('UNCHANGED CONTEXT')
    text.SetLayer(pcbnew.B_SilkS);text.SetTextPos(pcbnew.VECTOR2I_MM(24.,24.))
    board.Add(text);other.AddItem(text);other.SetLocked(True)
    other_ids={force._uid(other),force._uid(text)}
    field._save_field_snapshot(board,source)
    original=source.read_bytes()
    original_nodes=syntax._nodes(source)[1]
    poses={'X7':[10.25,10.,90.*turn]}
    captured=[]

    def construct_cell(native,operation,**kwargs):
        proposal=row.plan(native,poses,{},reference_group_uuids=[group],
            allow_cardinal_rotations=True)
        row.apply(native,proposal)
        source_plan=dict(row_plan=proposal,poses=poses,max_shift_mm=6.,
            reference_group_uuids=[group])
        captured.append(source_plan)
        return dict(kind='place_cell',affected_footprint_uuids=[owner],
            retired_track_uuids=[],added_track_uuids=[],source_plan=source_plan)

    monkeypatch.setattr(cells,'construct',construct_cell)
    candidate=force._copy_family(source,tmp_path/'private')
    result=construction._construct_connected(source,candidate,
        dict(operations=[operation(group)]),'opaque')
    receiving._receive_reference_transports(candidate,captured[0])
    final_nodes=syntax._nodes(candidate)[1]
    proof=captured[0]['row_plan']['source_reference_group_transports']['X7']
    expected_ids=set(proof['member_uuids'])|{group}
    assert expected_ids<=set(result['affected_native_uuids'])
    assert not other_ids.intersection(result['affected_native_uuids'])
    assert all(echo._freeze(final_nodes[uid])==echo._freeze(original_nodes[uid])
        for uid in original_nodes.keys()-expected_ids)
    assert source.read_bytes()==original
    assert result['private_unadmitted'] and not result['release_authority']


def test_plan_cell_api_preserves_explicit_annotation_scope(tmp_path):
    from cec_pipeline.workbench import Workbench

    workbench=object.__new__(Workbench);workbench.workspace=tmp_path
    captured=[]
    def make_job(board,request):
        captured.append((board,request));return 'a'*24
    workbench._make_job=make_job
    workbench._run=lambda *args:dict(complete=True,result={})
    workbench.plan_cell('opaque',[],reference_group_uuids=['source-group'])
    workbench.plan_cell('opaque',[])
    assert captured[0][1]['operation']['reference_group_uuids']==['source-group']
    assert captured[1][1]['operation']['reference_group_uuids']==[]
