"""A source-defined reference return may reserve its actual owner ground.

The supply blocker retains its existing full-load contract. The new lease
never supplies arbitrary endpoints or authority to change priority copper.
"""
import pcbnew
import pytest

import cec_field_coupling as field
import cec_force_current as force
import cec_future_pose_clearance as future
import cec_ground_reference_access as ground
import cec_local_branch_access as access
import cec_rated_supply_detour as rated
from cec_native_items import discard_items
from test_field_proposals import track
from test_local_branch_access import fixture as cell_fixture
from test_rated_supply_detour import authority


def fixture(tmp_path,*,angle=0,back=False):
    source,_,_=cell_fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    discard_items(b,[t for t in b.GetTracks() if t.GetNetname()=='MEASURE_MINUS'])
    owner=b.FindFootprintByReference('U_RENAMED');owner.SetReference('MEASUREMENT_OWNER_'+str(angle))
    for name,x in [('SOURCE_OTHER',12),('SINK_OTHER',18)]:
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(name);b.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(b.FindNet('+3V3'))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(.45,.45));pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetPosition(pcbnew.VECTOR2I_MM(x,14));fp.Add(pad)
    blocker=track(b,'+3V3',(12,14),(18,14));blocker.SetLocked(True)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    if angle:
        for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    if back:
        for fp in b.GetFootprints():fp.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for item in [*b.GetTracks(),*b.GetDrawings()]:
            item.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    target=force._uid(owner.FindPadByNumber('5'));uid=force._uid(blocker)
    field._save_field_snapshot(b,source)
    return pcbnew.LoadBoard(str(source)),source,target,uid


@pytest.mark.parametrize('angle,back',[(0,False),(90,False),(180,True),(270,True)])
def test_reference_lease_and_rated_prefix_replay_on_real_native_rotated_faces(tmp_path,angle,back):
    b,source,target,uid=fixture(tmp_path,angle=angle,back=back);before=source.read_bytes()
    task=next(r for r in access.targets(b,board_hint='synthetic') if r['pad_uuid']==target)
    primary=future.plan_ground_reference_links(b,[target],source=source,board_hint='synthetic')
    proposal=future.plan_ground_reference_links(b,[target],source=source,board_hint='synthetic',owner_ground=True)
    assert primary['links'][0]['destination']['role']=='assigned_bypass_return'
    assert proposal['links'][0]['destination']['role']=='manufacturer_ground'
    assert proposal['links'][0]['points_nm'][-1]==task['verified_ground_alternatives'][0]['at_nm']
    assert proposal['links'][0]['task']['cap']==task['cap']
    assert not proposal['ok'] and proposal['blockers'][0]['uuid']==uid
    with authority('+3V3'):
        result=rated.run(source,tmp_path/'rated-prefix',{},board_hint='synthetic',source_sha256=force._hash(source),
            reference_pad_uuids=[target],owner_ground=True)
    assert result['ok'],result.get('errors',result.get('receiving',{}).get('errors'))
    assert result['proposal']['retired_track_uuids']==[uid]
    assert result['source_and_code_unchanged'] and source.read_bytes()==before
    assert result['receiving']['opens']==result['receiving']['source_opens']
    assert not result['routing_admitted'] and not result['receiving']['force_current_qualified']
    child=pcbnew.LoadBoard(result['board'])
    clear=future.plan_ground_reference_links(child,[target],source=result['board'],board_hint='synthetic',owner_ground=True)
    assert not clear['blockers'] and clear['reference_link_not_yet_constructed']
    joined=ground.run(result['board'],tmp_path/'joined-ground',board_hint='synthetic',
        source_sha256=force._hash(result['board']))
    assert joined['ok'],joined
    assert joined['opens']<joined['source_opens'] and not joined['release_authority']


@pytest.mark.parametrize('fault',['wrong_pin','wrong_ground','ambiguous_package','nonboolean'])
def test_ground_destination_is_rederived_from_source_not_a_worker_coordinate(tmp_path,fault):
    b,source,target,_=fixture(tmp_path);owner=next(f for f in b.GetFootprints() if f.GetValue()=='INA181A2IDBVR')
    if fault=='wrong_pin':target=force._uid(owner.FindPadByNumber('2'))
    elif fault=='wrong_ground':owner.FindPadByNumber('2').SetNet(b.FindNet('+3V3'))
    elif fault=='ambiguous_package':owner.SetValue('INA181');owner.SetFPID(pcbnew.LIB_ID('Unknown','unknown'))
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):
        future.plan_ground_reference_links(b,[target],source=source,board_hint='synthetic',
            owner_ground='yes' if fault=='nonboolean' else True)


def test_ground_return_lease_cannot_be_combined_with_an_arbitrary_pose_or_missing_load(tmp_path):
    b,source,target,_=fixture(tmp_path)
    with authority('+3V3'):
        with pytest.raises(ValueError,match='one_source_preclear_scope_required'):
            rated.plan(b,{'unowned':[12,12,0]},source=source,board_hint='synthetic',
                reference_pad_uuids=[target],owner_ground=True)
    with authority('ABSENT'),pytest.raises(ValueError,match='full_load_planar_supply_preclear'):
        rated.plan(b,{},source=source,board_hint='synthetic',reference_pad_uuids=[target],owner_ground=True)


def test_forged_reference_plan_endpoint_does_not_change_native_source(tmp_path):
    b,source,target,_=fixture(tmp_path)
    plan=future.plan_ground_reference_links(b,[target],source=source,board_hint='synthetic',owner_ground=True)
    before=source.read_bytes();plan['links'][0]['destination']['at_nm'][0]+=100000
    with pytest.raises(ValueError,match='future_pose_plan_identity_changed'):
        future.construct(b,plan,source=source)
    assert source.read_bytes()==before
