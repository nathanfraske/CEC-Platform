"""A same-land seat is native geometry, not ownership or clearance by label."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_return_preservation as ground
import cec_inpad_ground_barrel_seats as seats
import cec_pose_additive_reconstruction as receiving
import cec_smd_macro_transport as macro
from test_retained_copper_passive_pose import fixture as source_fixture
from test_smd_macro_transport import inventory


def context(tmp_path,*,back=False,quarter=0,foreign=False):
    source,old_target,uid,carried=source_fixture(tmp_path,back=back,quarter=quarter,foreign=foreign)
    original,b=[pcbnew.LoadBoard(str(source)) for _ in range(2)]
    posed=pcbnew.LoadBoard(str(old_target))
    fp=next(f for f in b.GetFootprints() if force._uid(f)==uid)
    target=next(f for f in posed.GetFootprints() if force._uid(f)==uid)
    fp.SetPosition(target.GetPosition());fp.SetOrientationDegrees(target.GetOrientationDegrees())
    pad=next(p for p in fp.Pads() if p.GetNetname()=='GND')
    via=next(v for v in original.GetTracks() if v.GetClass()=='PCB_VIA' and v.GetNetname()=='GND')
    at=pad.GetPosition();request=dict(uuid=force._uid(via),owner_pad_uuid=force._uid(pad),
        position_nm=[at.x+50000,at.y-40000])
    return source,original,b,uid,request,carried


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_actual_saved_ground_seat_retains_source_current_copper_and_returns(tmp_path,back,quarter):
    source,original,b,uid,request,_=context(tmp_path,back=back,quarter=quarter)
    before=inventory(original);encoded=source.read_bytes()
    result=macro.apply(original,b,source_path=source,board_hint='synthetic',maximum_shift_mm=1.,
        retain_source_tracks=True,carry_ground_barrels_only=True,source_ground_barrel_seats=[request])
    assert result['source_ground_inpad_seats'][0]['source_and_projected_complete_native_containment']
    assert result['source_ground_inpad_seats'][0]['positive_margin_nm']==100
    proof=result['source_process_barrel_motion'][0]
    assert proof['explicitly_received_same_pad_ground_seat']
    assert not proof['original_barrel_geometry_count_and_relative_owner_seat_preserved']
    assert proof['original_barrel_geometry_and_count_preserved']
    after=inventory(b)
    assert {u for u in before if before[u]!=after[u]}=={request['uuid']}
    additive._ground_refill(b)
    target=force._copy_family(source,tmp_path/'seated');field._save_field_snapshot(b,target)
    received=receiving.receive(source,target,selected_footprint_uuids=[uid],board_hint='synthetic',
        max_shift_mm=1.,allow_source_ground_barrel_motion=True,source_ground_barrel_seats=[request])
    assert received['ok'] and received['complete'],received
    assert ground.receive(original,pcbnew.LoadBoard(str(target)))['ok']
    assert encoded==source.read_bytes() and inventory(original)==before
    assert not received['release_authority']


@pytest.mark.parametrize('fault',['foreign_barrel','wrong_pad','duplicate','outside_pad','bool_coordinate',
    'oversized_offset','extra_key','unknown_id','zero_relative_offset'])
def test_request_cannot_authorize_unowned_barrels_or_partial_lands(tmp_path,fault):
    source,original,b,uid,request,carried=context(tmp_path);rows=[copy.deepcopy(request)]
    if fault=='foreign_barrel':rows[0]['uuid']=next(force._uid(v) for v in original.GetTracks() if v.GetClass()=='PCB_VIA' and v.GetNetname()!='GND')
    elif fault=='wrong_pad':rows[0]['owner_pad_uuid']=next(force._uid(p) for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()!='GND')
    elif fault=='duplicate':rows.append(copy.deepcopy(rows[0]))
    elif fault=='outside_pad':rows[0]['position_nm'][0]+=180000
    elif fault=='bool_coordinate':rows[0]['position_nm'][0]=True
    elif fault=='oversized_offset':rows[0]['position_nm'][0]+=600000
    elif fault=='extra_key':rows[0]['skip_clearance']=True
    elif fault=='unknown_id':rows[0]['uuid']='not-a-source-id'
    else:
        pad=next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==request['owner_pad_uuid'])
        rows[0]['position_nm']=list(pad.GetPosition())
    before=inventory(b)
    with pytest.raises(ValueError):
        seats.resolve(original,b,rows,carried['source_process_barrel_motion'],maximum_shift_nm=1000000)
    assert before==inventory(b)


def test_pad_bbox_corner_is_not_native_round_land_containment(tmp_path):
    source,original,b,uid,request,carried=context(tmp_path)
    for board in (original,b):
        pad=next(p for f in board.GetFootprints() for p in f.Pads() if force._uid(p)==request['owner_pad_uuid'])
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad=next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==request['owner_pad_uuid'])
    request['position_nm']=[pad.GetPosition().x+210000,pad.GetPosition().y+210000]
    with pytest.raises(ValueError,match='native_ground_seat_containment'):
        seats.resolve(original,b,[request],carried['source_process_barrel_motion'],maximum_shift_nm=1000000)


def test_same_land_fit_cannot_waive_actual_foreign_inner_copper(tmp_path):
    source,original,b,uid,request,_=context(tmp_path,foreign=True)
    pad=next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==request['owner_pad_uuid'])
    request['position_nm']=[pad.GetPosition().x+10000,pad.GetPosition().y+20000]
    macro.apply(original,b,source_path=source,board_hint='synthetic',maximum_shift_mm=1.,
        retain_source_tracks=True,carry_ground_barrels_only=True,source_ground_barrel_seats=[request])
    additive._ground_refill(b);target=force._copy_family(source,tmp_path/'foreign');field._save_field_snapshot(b,target)
    proof=receiving.receive(source,target,selected_footprint_uuids=[uid],board_hint='synthetic',max_shift_mm=1.,
        allow_source_ground_barrel_motion=True,source_ground_barrel_seats=[request])
    assert not proof['ok'] and 'foreign_copper_collision' in proof['errors'][0],proof


@pytest.mark.parametrize('policy',[{},dict(retain_source_tracks=True)])
def test_ground_seats_require_the_explicit_ground_only_transport_tier(tmp_path,policy):
    source,original,b,uid,request,_=context(tmp_path);before=inventory(b)
    with pytest.raises(ValueError):macro.apply(original,b,source_ground_barrel_seats=[request],**policy)
    assert before==inventory(b)


def test_unexpected_saved_barrel_change_cannot_pass_without_the_literal_request(tmp_path):
    source,original,b,uid,request,_=context(tmp_path)
    macro.apply(original,b,source_path=source,board_hint='synthetic',maximum_shift_mm=1.,
        retain_source_tracks=True,carry_ground_barrels_only=True,source_ground_barrel_seats=[request])
    additive._ground_refill(b);target=force._copy_family(source,tmp_path/'unrequested');field._save_field_snapshot(b,target)
    proof=receiving.receive(source,target,selected_footprint_uuids=[uid],board_hint='synthetic',
        max_shift_mm=1.,allow_source_ground_barrel_motion=True)
    assert not proof['ok'] and proof['errors'],proof
