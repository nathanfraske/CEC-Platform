"""Pad material, not a pad box or a net label, owns duplicate retirement."""
import json
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_pad_contained_track_retirement as cleanup
from test_pad_mediated_neckdown_throat import fixture
from test_smd_macro_transport import inventory


def native(quarter=0,back=False,grouped=True):
    board,track=fixture();track.SetStart(pcbnew.VECTOR2I_MM(9.8,10));track.SetEnd(pcbnew.VECTOR2I_MM(10,10))
    track.SetLocked(True)
    group=None
    if grouped:
        group=pcbnew.PCB_GROUP(board);group.SetName(fr.ENDPOINT_NECKDOWN_GROUP);board.Add(group);group.AddItem(track)
    origin=pcbnew.VECTOR2I_MM(10,10);angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
    for fp in board.GetFootprints():fp.Rotate(origin,angle)
    for t in board.GetTracks():t.Rotate(origin,angle)
    if back:
        layers=pcbnew.LSET()
        for lid in (pcbnew.B_Cu,pcbnew.B_Mask,pcbnew.B_Paste):layers.AddLayer(lid)
        for fp in board.GetFootprints():
            fp.SetLayer(pcbnew.B_Cu)
            for pad in fp.Pads():pad.SetLayerSet(layers)
        for t in board.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetLayer(pcbnew.B_Cu if t.GetLayer()==pcbnew.F_Cu else pcbnew.F_Cu)
    return board,track,group


def save(tmp_path,board):
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='Default',track_width=1.,clearance=.15)]))))
    return source


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('grouped',[False,True])
def test_actual_positive_margin_pad_coverage_and_entire_source_replay(tmp_path,quarter,back,grouped):
    board,track,group=native(quarter,back,grouped);uid=force._uid(track)
    source=save(tmp_path,board);before=inventory(board)
    proposal=cleanup.plan(board,[uid],allow_owned_locked=True)
    assert before==inventory(board) and proposal['coverage_margin_nm']==10
    assert proposal['records'][0]['containing_source_pads']
    proof=cleanup.materialize(board,proposal)
    assert proof['physical_copper_union_unchanged'] and not proof['current_qualified']
    target=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(board,target)
    received=cleanup.receive(source,target,proposal)
    assert received['ok'] and received['complete'] and received['exact_entire_saved_source_reconstruction']
    assert received['every_surviving_native_partition_preserved']
    assert set(inventory(board))==set(before)-{uid}
    assert not received['new_capacity_credited'] and not received['routing_admitted']


@pytest.mark.parametrize('fault',['box_corner','partial_cap','foreign_net','other_face','custom_pad',
    'tht_pad','unknown_group','locked_group','no_lock_permission','dnp_pad','margin_zero','bad_id'])
def test_bounds_labels_partial_land_and_group_names_cannot_authorize_a_cut(fault):
    board,track,group=native();pad=next(p for fp in board.GetFootprints() for p in fp.Pads())
    options=dict(allow_owned_locked=True)
    if fault=='box_corner':
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE);track.SetStart(pcbnew.VECTOR2I_MM(9.7,9.8));track.SetEnd(pcbnew.VECTOR2I_MM(9.8,9.8))
    elif fault=='partial_cap':track.SetStart(pcbnew.VECTOR2I_MM(9.6,10))
    elif fault=='foreign_net':track.SetNet(board.FindNet('/foreign'))
    elif fault=='other_face':track.SetLayer(pcbnew.B_Cu)
    elif fault=='custom_pad':pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    elif fault=='tht_pad':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='unknown_group':group.SetName('opaque_unknown_annotation')
    elif fault=='locked_group':group.SetLocked(True)
    elif fault=='no_lock_permission':options['allow_owned_locked']=False
    elif fault=='dnp_pad':pad.GetParentFootprint().SetAttributes(pcbnew.FP_DNP)
    elif fault=='margin_zero':options['coverage_margin_nm']=0
    uid='not-source' if fault=='bad_id' else force._uid(track);before=inventory(board)
    with pytest.raises(ValueError):cleanup.plan(board,[uid],**options)
    assert inventory(board)==before


@pytest.mark.parametrize('fault',['pad','survivor','metadata','group','sidecar'])
def test_saved_child_cannot_smuggle_unrelated_source_changes(tmp_path,fault):
    board,track,group=native()
    if fault=='group':
        # A native writer drops an empty group. Keep an untouched member so
        # the attempted annotation change is an actual saved-board mutation.
        group.AddItem(next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and force._uid(t)!=force._uid(track)))
    source=save(tmp_path,board)
    proposal=cleanup.plan(board,[force._uid(track)],allow_owned_locked=True);cleanup.materialize(board,proposal)
    if fault=='pad':next(p for fp in board.GetFootprints() for p in fp.Pads()).SetSize(pcbnew.VECTOR2I_MM(1.,1.))
    elif fault=='survivor':next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(900000)
    elif fault=='metadata':
        props=board.GetProperties();props['UNRELATED_SOURCE_DATA']='changed';board.SetProperties(props)
    elif fault=='group':group.SetName('changed')
    target=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(board,target)
    if fault=='sidecar':target.with_suffix('.kicad_pro').write_text('{}')
    received=cleanup.receive(source,target,proposal)
    assert not received['ok'] and not received['complete'] and received['errors']


def test_discovery_protects_the_operation_and_uses_physical_same_face_contacts():
    board,operation,group=native();duplicate=operation.Duplicate();board.Add(duplicate)
    duplicate.SetStart(pcbnew.VECTOR2I_MM(9.9,10));duplicate.SetEnd(pcbnew.VECTOR2I_MM(10.05,10))
    before=inventory(board)
    found=cleanup.discover(board,touching_track_uuids=[force._uid(operation)],allow_owned_locked=True)
    assert found['ok'] and found['complete'] and found['plan']['track_uuids']==[force._uid(duplicate)]
    assert force._uid(operation) not in found['plan']['track_uuids'] and inventory(board)==before


def test_forged_witness_and_typed_allocation_dependency_refuse_before_mutation():
    board,track,group=native();proposal=cleanup.plan(board,[force._uid(track)],allow_owned_locked=True)
    proposal['records'][0]['containing_source_pads'][0]['pad_uuid']='forged';before=inventory(board)
    with pytest.raises(ValueError,match='stale_or_forged'):cleanup.materialize(board,proposal)
    assert inventory(board)==before
    dependency=pcbnew.PCB_GROUP(board)
    dependency.SetName('CEC_LOCAL_SUPPLY_ALLOCATION_V1|owner|portal|'+force._uid(track));board.Add(dependency)
    proposal=cleanup.plan(board,[force._uid(track)],allow_owned_locked=True);before=inventory(board)
    with pytest.raises(ValueError,match='breaks_typed_supply_annotation'):cleanup.materialize(board,proposal)
    assert inventory(board)==before
