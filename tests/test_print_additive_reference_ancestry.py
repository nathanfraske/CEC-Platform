"""A received interrupted guide survives copper additions, never map mutation."""
import copy
import pcbnew
import pytest
import cec_force_current as force
import cec_additive_pair_repair as additions
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_nonpolar_print_context as op
from test_received_guide_print_context import case


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',[0,90,180,270])
def test_fresh_map_plus_strict_additive_saved_boundary_required(tmp_path,monkeypatch,back,turn):
    ancestor,mapped,declaration,options=case(tmp_path,monkeypatch,back=back,turn=turn,with_signal=True)
    candidate=force._copy_family(mapped,tmp_path/'copper-child')
    # Literal copper delta (independent additive receiver is NOT mocked).
    b=pcbnew.LoadBoard(str(candidate));old={force._uid(t)for t in b.GetTracks()}
    prior=next(t for t in b.GetTracks()if t.GetNetname()=='/existing_channel')
    track=pcbnew.PCB_TRACK(b);track.SetNet(prior.GetNet());track.SetStart(prior.GetEnd())
    track.SetEnd(pcbnew.VECTOR2I_MM(47,30));track.SetWidth(200000);track.SetLayer(pcbnew.B_Cu);b.Add(track)
    additions.save_native_additions(candidate,b,{},old,board_hint='renamed')
    proof=additive.receive(mapped,candidate,board_hint='renamed',timeout_s=10.)
    assert proof['ok']and proof['complete'],proof
    inherited=dict(declaration,mapped_source=dict(path=str(mapped),sha256=force._hash(mapped)))
    q=op.plan(candidate,**options,reference_mapping_transition=inherited)
    received=[r['source_reference_map']for r in q['records']if r.get('source_reference_map')]
    assert len(received)==1 and received[0]['strict_opaque_Source_additive_ancestry_independently_received']
    assert received[0]['copper_addition_admission_or_current_authority']is False
    artifact=op.construct_private(candidate,q,tmp_path/'printed')
    result=op.receive(candidate,artifact['candidate'],q)
    assert result['ok']and result['complete'],result


@pytest.mark.parametrize('fault',['pad','value','guide','group','sidecar','ancestor_hash','unreceived_map'])
def test_no_alias_authority_from_modified_or_unreceived_ancestor(tmp_path,monkeypatch,fault):
    ancestor,mapped,declaration,options=case(tmp_path,monkeypatch)
    candidate=force._copy_family(mapped,tmp_path/'copper-child')
    inherited=dict(declaration,mapped_source=dict(path=str(mapped),sha256=force._hash(mapped)))
    if fault=='ancestor_hash':inherited['mapped_source']['sha256']='0'*64
    elif fault=='unreceived_map':inherited['source']=copy.deepcopy(inherited['mapped_source'])
    elif fault=='sidecar':candidate.with_suffix('.kicad_dru').write_text('(version 1)')
    else:
        b=pcbnew.LoadBoard(str(candidate));fp=next(f for f in b.GetFootprints()if f.GetReference()=='Z91')
        if fault=='pad':next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='value':fp.SetValue('unowned')
        elif fault=='guide':next(iter(b.GetDrawings())).Move(pcbnew.VECTOR2I(1,0))
        else:next(iter(b.Groups())).SetName('forged map')
        field._save_field_snapshot(b,candidate)
    with pytest.raises(ValueError):op.plan(candidate,**options,reference_mapping_transition=inherited)


def test_public_plan_does_not_accept_caller_native_board_or_prepared_proof(tmp_path,monkeypatch):
    ancestor,mapped,declaration,options=case(tmp_path,monkeypatch,with_signal=True)
    candidate=force._copy_family(mapped,tmp_path/'copper-child')
    inherited=dict(declaration,mapped_source=dict(path=str(mapped),sha256=force._hash(mapped)))
    with pytest.raises(TypeError):op.plan(candidate,**options,reference_mapping_transition=inherited,
        _source_board=pcbnew.LoadBoard(str(candidate)))


def test_internal_bound_board_avoids_duplicate_native_load_not_independent_receiving(tmp_path,monkeypatch):
    ancestor,mapped,declaration,options=case(tmp_path,monkeypatch,with_signal=True)
    candidate=force._copy_family(mapped,tmp_path/'copper-child');board=pcbnew.LoadBoard(str(candidate))
    def forbidden(*args,**kwargs):raise AssertionError('duplicate native load inside prepared private phase')
    monkeypatch.setattr(pcbnew,'LoadBoard',forbidden)
    result=op._retained_map_track_ancestry(mapped,candidate,'renamed',_source_board=board)
    assert result['ok']and result['all_original_tree_and_companions_exact']
    assert result['reference_association_only']and not result['copper_admission']
