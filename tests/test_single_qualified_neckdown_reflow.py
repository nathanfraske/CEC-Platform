"""One real Source endpoint needs no fabricated second segment to shorten."""
import json
import time
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_qualified_neckdown_reflow as reflow
import cec_route_corner_contacts as contacts
from test_pad_mediated_neckdown_throat import fixture
from test_smd_macro_transport import inventory


def source(tmp_path,quarter=0,back=False,fault=None):
    board,track=fixture(quarter=quarter,back=back,fault=None if fault=='side_contact_lost' else fault)
    group=pcbnew.PCB_GROUP(board);group.SetName(fr.ENDPOINT_NECKDOWN_GROUP)
    board.Add(group);group.AddItem(track);track.SetLocked(True)
    if fault=='locked_endpoint_group':group.SetLocked(True)
    start,end=map(tuple,(track.GetStart(),track.GetEnd()))
    points=[[a+(z-a)//4 for a,z in zip(start,end)],list(end)]
    if fault=='side_contact_lost':
        side=pcbnew.PCB_TRACK(board);side.SetNet(track.GetNet());side.SetLayer(pcbnew.F_Cu)
        side.SetStart(pcbnew.VECTOR2I_MM(9.45,10));side.SetEnd(pcbnew.VECTOR2I_MM(9.45,9.5))
        side.SetWidth(200000);board.Add(side);points[0]=[9700000,10000000]
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,path)
    path.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='Default',track_width=1.,clearance=.15)]))))
    return path,pcbnew.LoadBoard(str(path)),dict(track_uuids=[force._uid(track)],vertices_nm=points)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_shorter_single_endpoint_keeps_the_complete_source_contract_and_saved_replay(tmp_path,quarter,back):
    path,board,plan=source(tmp_path,quarter,back);before=inventory(board)
    proof=reflow.apply(path,board,board_hint='opaque_synthetic',**plan)
    assert proof['source_length_mm']==.2 and proof['candidate_length_mm']==.15
    assert proof['full_width_floor_nm']==1000000 and proof['every_original_native_partition_preserved']
    assert set(before)==set(inventory(board))
    track=next(t for t in board.GetTracks() if force._uid(t)==plan['track_uuids'][0])
    assert track.IsLocked() and track.GetWidth()==200000
    target=force._copy_family(path,tmp_path/'candidate');field._save_field_snapshot(board,target)
    observed=reflow.receive(path,target,plan,board_hint='opaque_synthetic')
    assert observed['ok'] and observed['complete'] and observed['exact_saved_source_reconstruction']
    assert not observed['current_qualified'] and not observed['routing_admitted']


@pytest.mark.parametrize('fault',['partial_overlap','wrong_profile','narrow_throat',
    'side_contact_lost','locked_endpoint_group','lost_land','angle','longer','empty_path','metadata'])
def test_one_track_does_not_relax_any_source_scope_or_native_guard(tmp_path,fault):
    path,board,plan=source(tmp_path,fault=fault)
    if fault=='lost_land':plan['vertices_nm'][0]=[9300000,10000000]
    elif fault=='angle':plan['vertices_nm'][0][1]+=1
    elif fault=='longer':plan['vertices_nm'][0]=[9500000,10000000]
    elif fault=='empty_path':plan['vertices_nm'][0]=list(plan['vertices_nm'][1])
    elif fault=='metadata':
        props=board.GetProperties();props['UNRELATED_SOURCE_METADATA']='changed';board.SetProperties(props)
    before=inventory(board)
    with pytest.raises(ValueError):reflow.apply(path,board,board_hint='opaque_synthetic',**plan)
    assert inventory(board)==before


def test_a_foreign_short_is_not_normalized_into_a_qualifying_source(tmp_path):
    # The authored foreign short is rejected at the exact snapshot boundary
    # on this native toolchain, before it can become apparent same-net metal.
    # Never use the normalizing convenience SaveBoard to manufacture a pass.
    with pytest.raises((field._ProposalUnknown,ValueError)):
        path,board,plan=source(tmp_path,fault='foreign_via')
        reflow.apply(path,board,board_hint='opaque_synthetic',**plan)


@pytest.mark.parametrize('fault',['width','footprint','sidecar'])
def test_saved_single_endpoint_receiver_still_requires_exact_whole_source_reconstruction(tmp_path,fault):
    path,board,plan=source(tmp_path);reflow.apply(path,board,board_hint='opaque_synthetic',**plan)
    if fault=='width':
        next(t for t in board.GetTracks() if force._uid(t)==plan['track_uuids'][0]).SetWidth(210000)
    elif fault=='footprint':next(iter(board.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    target=force._copy_family(path,tmp_path/'candidate');field._save_field_snapshot(board,target)
    if fault=='sidecar':target.with_suffix('.kicad_pro').write_text('{}')
    received=reflow.receive(path,target,plan,board_hint='opaque_synthetic')
    assert not received['ok'] and not received['complete'] and received['errors']


@pytest.mark.parametrize('minimum',[None,False,0,3,1.0])
def test_plain_corner_callers_do_not_silently_acquire_single_track_scope(tmp_path,minimum):
    path,board,plan=source(tmp_path)
    track=next(t for t in board.GetTracks() if force._uid(t)==plan['track_uuids'][0])
    options={} if minimum is None else dict(minimum_source_tracks=minimum)
    with pytest.raises(ValueError,match='bounded_native_corner_contact_scope_required'):
        contacts.preserve_contacts(board,[track],[track.GetEffectiveShape(track.GetLayer())],
            layer_id=track.GetLayer(),net_code=track.GetNetCode(),deadline_monotonic=time.monotonic()+10.,**options)
