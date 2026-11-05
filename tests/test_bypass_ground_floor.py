"""Source-derived bypass floors retain every other authored native object."""
import math
import time
from unittest import mock

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_bypass_ground_floor as floor
import cec_copper_echo as sexpr
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
from test_assigned_ground_access import fixture as ground_fixture


def fixture(tmp_path,*,turn=0,layer=pcbnew.F_Cu,names=('UNRELATED_CHIP','C_OTHER_LOCAL'),generated=False):
    source,board,owner,cap,stub,via=ground_fixture(tmp_path,turn=turn,layer=layer,names=names)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    via.SetWidth(350000);via.SetDrill(250000)
    if generated:
        group=pcbnew.PCB_GROUP(board);group.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP);board.Add(group)
        group.AddItem(via);via.SetLocked(True)
    field._save_field_snapshot(board,source)
    additive.bind_local_via_rule(board,source)
    # The SAVED source, not unsaved test settings, is the receiving authority.
    board=pcbnew.LoadBoard(str(source));owner=board.FindFootprintByReference(names[0]);cap=board.FindFootprintByReference(names[1])
    via=next(item for item in board.GetTracks() if item.GetClass()=='PCB_VIA')
    return source,board,owner,cap,via


@pytest.mark.parametrize('turn,layer,generated,names',[
    (0,pcbnew.F_Cu,False,('UNRELATED_CHIP','C_OTHER_LOCAL')),
    (1,pcbnew.B_Cu,False,('DEVICE_ALIAS','C_ALTERNATE')),
    (2,pcbnew.F_Cu,True,('RENUMBERED_OWNER','C_RENAMED_RETURN')),
    (3,pcbnew.B_Cu,True,('SOME_DEVICE','C_ANY_LOCAL'))])
def test_private_ground_dimensions_recompile_without_moving_or_unlocking_source(tmp_path,turn,layer,generated,names):
    source,board,_,cap,via=fixture(tmp_path,turn=turn,layer=layer,generated=generated,names=names)
    original=source.read_bytes();before=field._field_snapshot_inventory(board)
    result=floor.construct(board,board_hint='unrelated-board',cap_refs=[names[1]])
    assert result['changed'] and result['complete'],result
    assert len(result['plans'])==1 and result['plans'][0]['cap']==names[1]
    assert via.GetWidth(via.TopLayer())>=500000 and via.GetDrillValue()>=250000
    assert via.IsLocked() is generated
    after=field._field_snapshot_inventory(board)
    assert before.keys()==after.keys()
    assert all(before[key]==after[key] for key in before if key!=('track',force._uid(via)))
    additive._ground_refill(board);candidate=tmp_path/'candidate.kicad_pcb';field._save_field_snapshot(board,candidate)
    additive.bind_local_via_rule(board,candidate)
    receiving=floor.receive(source,candidate,board_hint='unrelated-board')
    assert receiving['ok'] and receiving['complete'],receiving
    assert receiving['all_original_native_components_preserved']
    assert not receiving['release_authority'] and not receiving['current_qualification']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['author_lock','other_group','unknown_process','unknown_device',
    'shared_pad','foreign_track','foreign_hole','non_through','supply_return'])
def test_ownership_process_holes_and_foreign_copper_refuse_before_mutation(tmp_path,fault):
    _,board,owner,cap,via=fixture(tmp_path,generated=fault=='unknown_process')
    if fault=='author_lock':via.SetLocked(True)
    elif fault=='other_group':
        group=pcbnew.PCB_GROUP(board);group.SetName('UNRELATED_AUTHORED_CELL');board.Add(group);group.AddItem(via)
    elif fault=='unknown_process':
        props=board.GetProperties();props['CEC_FAB_PROFILE']='';board.SetProperties(props)
    elif fault=='unknown_device':owner.SetValue('UNQUALIFIED_DEVICE')
    elif fault=='shared_pad':
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('UNRELATED_GROUND_OWNER');board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(board.FindNet('GND'));pad.SetPosition(via.GetPosition())
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetSize(pcbnew.VECTOR2I_MM(.3,.5));pad.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(pad)
    elif fault=='foreign_track':
        track=pcbnew.PCB_TRACK(board);track.SetNet(board.FindNet('/RENAMED_DEVICE_RAIL'));track.SetLayer(pcbnew.In1_Cu)
        track.SetWidth(200000);track.SetStart(via.GetPosition()-pcbnew.VECTOR2I_MM(1,0));track.SetEnd(via.GetPosition()+pcbnew.VECTOR2I_MM(1,0));board.Add(track)
    elif fault=='foreign_hole':
        other=pcbnew.PCB_VIA(board);other.SetNet(board.FindNet('/RENAMED_DEVICE_RAIL'))
        other.SetPosition(via.GetPosition()+pcbnew.VECTOR2I_MM(.35,0));other.SetWidth(500000);other.SetDrill(300000)
        other.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(other)
    elif fault=='non_through':via.SetViaType(pcbnew.VIATYPE_BLIND);via.SetLayerPair(pcbnew.F_Cu,pcbnew.In1_Cu)
    else:cap.FindPadByNumber('2').SetNet(board.FindNet('/RENAMED_DEVICE_RAIL'))
    before=field._field_snapshot_inventory(board)
    result=floor.construct(board,board_hint='unrelated-board')
    assert not result['changed'],result
    assert before==field._field_snapshot_inventory(board)
    assert not result['release_authority']


@pytest.mark.parametrize('fault',['oversize','undersize','drill','move_via','net','unlock','remove_group',
    'move_owner','cap_value','track_width','added_track'])
def test_saved_ground_floor_receiving_rejects_every_unowned_native_change(tmp_path,fault):
    source,board,owner,cap,via=fixture(tmp_path,generated=True)
    result=floor.construct(board,board_hint='unrelated-board');assert result['changed'],result
    if fault=='oversize':via.SetWidth(via.GetWidth(via.TopLayer())+100000)
    elif fault=='undersize':via.SetWidth(350000)
    elif fault=='drill':via.SetDrill(via.GetDrillValue()+50000)
    elif fault=='move_via':via.Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='net':via.SetNet(board.FindNet('/RENAMED_DEVICE_RAIL'))
    elif fault=='unlock':via.SetLocked(False)
    elif fault=='remove_group':next(group for group in board.Groups()).RemoveItem(via)
    elif fault=='move_owner':owner.Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='cap_value':cap.SetValue('220nF')
    elif fault=='track_width':next(track for track in board.GetTracks() if track.GetClass()=='PCB_TRACK').SetWidth(300000)
    else:
        track=pcbnew.PCB_TRACK(board);track.SetNet(board.FindNet('GND'));track.SetLayer(pcbnew.F_Cu)
        track.SetWidth(200000);track.SetStart(pcbnew.VECTOR2I_MM(7,7));track.SetEnd(pcbnew.VECTOR2I_MM(8,7));board.Add(track)
    candidate=tmp_path/'bad-candidate.kicad_pcb'
    if fault=='net':pcbnew.SaveBoard(str(candidate),board)
    else:field._save_field_snapshot(board,candidate)
    if fault!='remove_group':additive.bind_local_via_rule(board,candidate)
    receiving=floor.receive(source,candidate,board_hint='unrelated-board')
    assert not receiving['ok'] and receiving['errors'],receiving
    assert not receiving['release_authority'] and not receiving['inherited_debt_qualified']


@pytest.mark.parametrize('options',[{'timeout_s':0},{'timeout_s':True},{'timeout_s':math.nan},{'timeout_s':11},
    {'limit':0},{'limit':True},{'limit':17},{'cap_refs':[]},{'cap_refs':['C_OTHER_LOCAL']*2},
    {'cap_refs':[True]},{'board_hint':''}])
def test_search_and_scope_are_finite_before_mutation(tmp_path,options):
    source,board,*_=fixture(tmp_path)
    before=field._field_snapshot_inventory(board)
    arguments=dict(board_hint='unrelated-board');arguments.update(options)
    with pytest.raises(ValueError):floor.construct(board,**arguments)
    assert before==field._field_snapshot_inventory(board)


def test_no_change_is_not_presented_as_ground_floor_progress(tmp_path):
    source,board,*_=fixture(tmp_path)
    result=floor.receive(source,source,board_hint='unrelated-board')
    assert not result['ok'] and result['errors']
    with pytest.raises(ValueError):floor.construct(board,board_hint='unrelated-board',cap_refs=['C_NOT_PRESENT'])


def test_existing_authored_stronger_rule_cannot_be_lowered_by_group_rebinding(tmp_path):
    source,board,*_=fixture(tmp_path,generated=True)
    rule=source.with_suffix('.kicad_dru')
    rule.write_text(rule.read_text().replace('(min 0.350mm)','(min 0.600mm)'))
    source_rule=rule.read_bytes()
    result=floor.construct(board,board_hint='unrelated-board');assert result['changed']
    candidate=tmp_path/'candidate.kicad_pcb';field._save_field_snapshot(board,candidate)
    additive.bind_local_via_rule(board,candidate)
    receiving=floor.receive(source,candidate,board_hint='unrelated-board')
    assert not receiving['ok'] and 'source_rule_not_exact_owner_replay' in str(receiving['errors'])
    assert rule.read_bytes()==source_rule


def test_final_hole_conflict_restores_all_original_native_dimensions(tmp_path):
    _,board,*_=fixture(tmp_path)
    plans,refused,deferred=floor._plans(board,'unrelated-board',None,16,time.monotonic()+10)
    assert plans
    before=field._field_snapshot_inventory(board)
    with mock.patch.object(floor,'_plans',return_value=(plans,refused,deferred)),mock.patch.object(
            floor.cells,'_hole_to_hole_clear',return_value=(False,[{'reason':'joint_final_holes'}])):
        with pytest.raises(ValueError):floor.construct(board,board_hint='unrelated-board')
    assert before==field._field_snapshot_inventory(board)
