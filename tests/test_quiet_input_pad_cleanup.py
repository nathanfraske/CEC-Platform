"""Only the canonical compiler boundary is stubbed; native union/graphs are real."""
import copy
import pcbnew
import pytest
import cec_force_current as force
import cec_quiet_input_pad_cleanup as cleanup
from test_pad_contained_track_retirement import native, save
from test_smd_macro_transport import inventory


def fixture(tmp_path, monkeypatch, quarter=0, back=False, fault=None):
    board, track, _ = native(quarter, back, grouped=False)
    peer = next(p for fp in board.GetFootprints() for p in fp.Pads())
    peer.GetParentFootprint().SetReference('renamed_peer_'+str(quarter))
    fp = pcbnew.FOOTPRINT(board); fp.SetReference('renamed_consumer'); board.Add(fp)
    pad = pcbnew.PAD(fp); pad.SetNumber('unrelated_number')
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(.8,.5)); pad.SetLayerSet(peer.GetLayerSet())
    pad.SetPosition(pcbnew.VECTOR2I_MM(13,15)); pad.SetNet(peer.GetNet()); fp.Add(pad)
    if fault == 'partial': track.Move(pcbnew.VECTOR2I_MM(.4,.4))
    if fault == 'foreign':
        track.Move(pcbnew.VECTOR2I_MM(3,3)); track.SetNet(board.FindNet('/foreign'))
    if fault == 'mask': track.SetHasSolderMask(True)
    if fault == 'group':
        group=pcbnew.PCB_GROUP(board);group.SetName('unrelated');board.Add(group);group.AddItem(track)
    source=save(tmp_path,board)
    input_uid,peer_uid,uid=map(force._uid,(pad,peer,track))
    def compiler(actual, path, **kwargs):
        return dict(complete=fault!='unknown_role',peer_pad_uuid=peer_uid,
            source_request=dict(request=dict(demand=dict(net=str(peer.GetNetname()),
                pad_uuid=input_uid,target_uuid='canonical-shunt-land',
                manufacturer_source='canonical compiler fixture only'))),
            source_quiet_tree=dict(exact_direct_lineage_rederived_for_all_inputs=True,
                inward_departure=dict(ok=True),via_uuids=[],leaf_pad_uuids=[peer_uid],
                exact_shunt_pad_uuid='canonical-shunt-land',track_uuids=[uid],
                fully_land_contained_track_uuids=[uid]))
    monkeypatch.setattr(cleanup.fanout,'plan',compiler)
    args=dict(board_hint='pcie-8pin-3port',input_pad_uuid=input_uid,peer_pad_uuid=peer_uid)
    return board,track,source,args


@pytest.mark.parametrize('quarter',range(4))
def test_renamed_rotated_native_union_and_saved_partitions(tmp_path,monkeypatch,quarter):
    board,track,source,args=fixture(tmp_path,monkeypatch,quarter)
    before=inventory(board);proposal=cleanup.plan(board,source,**args)
    assert inventory(board)==before
    assert proposal['retired_track_uuids']==[force._uid(track)]
    assert proposal['retirement']['allow_owned_locked'] is True
    child=force._copy_family(source,tmp_path/'child')
    made=cleanup.construct_private(source,child,proposal)
    assert made['complete'] and made['physical_copper_union_unchanged']
    result=cleanup.receive(source,child,**args)
    assert result['ok'] and result['complete'] and result['physical_copper_union_unchanged']
    assert result['physical_receiving']['every_surviving_native_partition_preserved']
    assert not result['electrical_retirement_authority'] and not result['current_authority']
    assert inventory(pcbnew.LoadBoard(str(source)))==before


@pytest.mark.parametrize('quarter',range(4))
def test_back_face_cannot_borrow_front_only_quiet_contract(tmp_path,monkeypatch,quarter):
    board,_,source,args=fixture(tmp_path,monkeypatch,quarter,True)
    with pytest.raises(ValueError,match='ungrouped_unmasked'):
        cleanup.plan(board,source,**args)


@pytest.mark.parametrize('fault',['partial','foreign','mask','group','unknown_role'])
def test_native_partial_foreign_group_mask_and_unknown_owner_refuse(tmp_path,monkeypatch,fault):
    board,_,source,args=fixture(tmp_path,monkeypatch,fault=fault)
    before=inventory(board)
    with pytest.raises(ValueError):cleanup.plan(board,source,**args)
    assert inventory(board)==before


@pytest.mark.parametrize('fault',['cut','lock_permission','peer','union_claim','source_family'])
def test_forged_proposal_cannot_supply_retirement_authority(tmp_path,monkeypatch,fault):
    board,track,source,args=fixture(tmp_path,monkeypatch)
    q=copy.deepcopy(cleanup.plan(board,source,**args));before=inventory(board)
    if fault=='cut':q['retired_track_uuids'].append('unowned-locked-track')
    elif fault=='lock_permission':q['retirement']['allow_owned_locked']=False
    elif fault=='peer':q['peer_pad_uuid']=args['input_pad_uuid']
    elif fault=='union_claim':q['physical_copper_union_unchanged']=False
    else:q['source_family']={}
    with pytest.raises(ValueError):cleanup.materialize(board,source,q)
    assert inventory(board)==before and track.IsLocked()


def test_mutated_source_frame_and_saved_sidecar_refuse(tmp_path,monkeypatch):
    board,track,source,args=fixture(tmp_path,monkeypatch)
    q=cleanup.plan(board,source,**args)
    track.Move(pcbnew.VECTOR2I(1,0))
    with pytest.raises(ValueError,match='exact_saved'):cleanup.plan(board,source,**args)
    child=force._copy_family(source,tmp_path/'child')
    cleanup.construct_private(source,child,q)
    child.with_suffix('.kicad_pro').write_text('{}')
    assert not cleanup.receive(source,child,**args)['ok']


def test_other_locked_pad_duplicate_is_not_selected(tmp_path,monkeypatch):
    board,track,source,args=fixture(tmp_path,monkeypatch)
    other=pcbnew.PCB_TRACK(board);other.SetStart(track.GetStart());other.SetEnd(track.GetEnd())
    other.SetWidth(track.GetWidth());other.SetLayer(track.GetLayer());other.SetNet(track.GetNet())
    other.SetLocked(True);board.Add(other)
    # Update only the actual saved Source frame, not the compiler's owned set.
    source=save(tmp_path,board)
    q=cleanup.plan(board,source,**args)
    assert q['retired_track_uuids']==[force._uid(track)]
    cleanup.materialize(board,source,q)
    assert force._uid(other) in {force._uid(t)for t in board.GetTracks()}
    assert other.IsLocked()


def test_code_change_during_fresh_canonical_owner_compilation_refuses(tmp_path,monkeypatch):
    board,_,source,args=fixture(tmp_path,monkeypatch)
    original=cleanup.fanout.plan; epoch={'value':0}
    monkeypatch.setattr(cleanup.force,'_code_identity',lambda:dict(epoch))
    def changed(*a,**kw):
        result=original(*a,**kw);epoch['value']=1;return result
    monkeypatch.setattr(cleanup.fanout,'plan',changed)
    with pytest.raises(ValueError,match='source_epoch_changed'):
        cleanup.plan(board,source,**args)


def test_no_caller_cut_width_or_lock_allowlist_parameters(tmp_path,monkeypatch):
    board,_,source,args=fixture(tmp_path,monkeypatch)
    for extra in ({'allow_owned_locked':True},{'track_uuids':['forged']},{'width_nm':1}):
        with pytest.raises(TypeError):cleanup.plan(board,source,**args,**extra)
