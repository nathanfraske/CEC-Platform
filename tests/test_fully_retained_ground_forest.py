"""Empty Source cuts retain actual old paths; they are not guessed Ground."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_field_coupling as field
import cec_force_current as force
import cec_fully_retained_ground_forest as extended
import cec_stationary_ground_forest as original
from test_stationary_ground_forest import fixture as partial_fixture
from test_ground_return_fork import plan


def full_fixture(tmp_path,quarter=0,back=False):
    b,posed,source,q,owner,fixed,via,edges,tail=partial_fixture(tmp_path,quarter,back,split=False)
    delta=owner.FindPadByNumber('2').GetPosition()-fixed.FindPadByNumber('2').GetPosition()
    fixed.Move(delta);b.Remove(edges[1]);field._save_field_snapshot(b,source)
    owner_ref=owner.GetReference();b=pcbnew.LoadBoard(str(source));owner=b.FindFootprintByReference(owner_ref)
    fork=plan(b,owner)
    assert len(fork['track_uuids'])==1
    q=dict(scope='source_typed_complete_cell_escape_proposal',source_native_binding=binding._source_binding(b),
        board_hint='opaque_design',row_plan=dict(retired_track_uuids=[]),retired_track_uuids=list(fork['track_uuids']),
        source_owned_shared_ground_return_forks=[fork])
    posed=pcbnew.LoadBoard(str(source));posed.FindFootprintByReference(owner_ref).Move(pcbnew.VECTOR2I_MM(.5,.5))
    return b,posed,source,q


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_all_required_fixed_paths_can_produce_a_literal_empty_cut(tmp_path,quarter,back):
    b,posed,source,q=full_fixture(tmp_path,quarter,back);raw=source.read_bytes()
    before=[binding._source_binding(v) for v in (b,posed)];old_q=copy.deepcopy(q)
    old=original.refine(b,posed,q);assert old['retired_track_uuids']==q['retired_track_uuids']
    new=extended.refine(b,posed,q)
    assert new['retired_track_uuids']==[] and new['source_owned_shared_ground_return_forks']==[]
    record=new['fully_retained_stationary_ground_forks'][0]
    assert set(record['kept_source_track_uuids'])==set(q['retired_track_uuids'])
    assert record['no_new_connection_hole_process_or_current_authority']
    assert not record['release_authority'] and len(record['paths'])==1
    assert [binding._source_binding(v) for v in (b,posed)]==before and source.read_bytes()==raw and q==old_q


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_existing_partial_forest_result_is_not_redefined(tmp_path,quarter,back):
    b,posed,source,q,*_=partial_fixture(tmp_path,quarter,back)
    assert extended.refine(b,posed,q)==original.refine(b,posed,q)


@pytest.mark.parametrize('fault',['moved_root','drill','moved_fixed','lost_plane','other_owner','missing_track','changed_held_width'])
def test_unknown_or_changed_reference_paths_never_become_retention_credit(tmp_path,fault):
    b,posed,source,q=full_fixture(tmp_path)
    fork=q['source_owned_shared_ground_return_forks'][0]
    root_uid=next(p['native_uuid'] for p in fork['retained_native_ports'] if p['native_class']=='PCB_VIA')
    root=next(t for t in posed.GetTracks() if force._uid(t)==root_uid)
    edge=next(t for t in posed.GetTracks() if force._uid(t)==q['retired_track_uuids'][0])
    if fault=='moved_root':root.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='drill':root.SetDrill(root.GetDrillValue()+1)
    elif fault=='moved_fixed':
        uid=fork['fixed_ground_terminal_contracts'][0]['pad_uuid']
        next(p for f in posed.GetFootprints() for p in f.Pads() if force._uid(p)==uid).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='lost_plane':
        for z in posed.Zones():z.UnFill()
    elif fault=='other_owner':q['row_plan']['retired_track_uuids']=list(q['retired_track_uuids'])
    elif fault=='missing_track':posed.Remove(edge)
    else:edge.SetWidth(edge.GetWidth()+1)
    r=extended.refine(b,posed,q)
    assert 'fully_retained_stationary_ground_forks' not in r
    assert r['retired_track_uuids']==q['retired_track_uuids']


@pytest.mark.parametrize('back',[False,True])
def test_only_source_proved_retained_transport_legs_are_restored_to_original_geometry(tmp_path,back):
    b,posed,source,q=full_fixture(tmp_path,back=back);raw=source.read_bytes()
    edge=next(t for t in posed.GetTracks() if force._uid(t)==q['retired_track_uuids'][0])
    edge.SetStart(edge.GetStart()+pcbnew.VECTOR2I(1000,0))
    refused=extended.refine(b,posed,q);assert 'fully_retained_stationary_ground_forks' not in refused
    r=extended.propose_and_restore(b,posed,q)
    assert r['retired_track_uuids']==[] and r['literal_stationary_source_ground_track_restorations']==q['retired_track_uuids']
    expected=next(t for t in b.GetTracks() if force._uid(t)==force._uid(edge))
    assert tuple(edge.GetStart())==tuple(expected.GetStart()) and tuple(edge.GetEnd())==tuple(expected.GetEnd())
    assert source.read_bytes()==raw


@pytest.mark.parametrize('fault',['tracks','root','role','source'])
def test_forged_fork_or_source_never_changes_private_or_source_on_refusal(tmp_path,fault):
    b,posed,source,q=full_fixture(tmp_path);fork=q['source_owned_shared_ground_return_forks'][0]
    if fault=='tracks':fork['track_uuids']=[]
    elif fault=='root':fork['requested_root_pad_uuids']=['forged']
    elif fault=='role':fork['fixed_ground_terminal_contracts'][0]['role']='forged'
    else:fork['source_sha256']='forged'
    before=[binding._source_binding(v) for v in (b,posed)]
    with pytest.raises((ValueError,KeyError)):extended.propose_and_restore(b,posed,q)
    assert before==[binding._source_binding(v) for v in (b,posed)]


@pytest.mark.parametrize('timeout',[True,0,float('nan'),10.001])
def test_ten_second_native_owner_bound_is_not_raised(tmp_path,timeout):
    b,posed,source,q=full_fixture(tmp_path)
    with pytest.raises(ValueError):extended.propose_and_restore(b,posed,q,timeout_s=timeout)


def test_private_macro_namespaces_never_patch_the_global_frozen_modules():
    import cec_cell_macro_requests as old_compiler
    import cec_cell_escape_replan as old_escape
    import cec_complete_macro_cell as old_macro
    identities=old_compiler.compile,old_escape.complete_connection_screen,old_macro.receive
    import cec_retained_forest_macro as private
    assert (old_compiler.compile,old_escape.complete_connection_screen,old_macro.receive)==identities
    assert private.compiler is not old_compiler and private.escape is not old_escape and private.macro is not old_macro
