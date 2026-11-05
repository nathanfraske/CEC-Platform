"""A real saved pad bank is not permission for an arbitrary new power zone."""
import copy,json
from pathlib import Path

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_pad_bank_collector as bank
import cec_source_literal_additions as literal
import cec_source_pad_bank_stage as stage
import cec_source_retaining_ses_import as raw
import cec_zone_fill
import root_receive_local_transaction_20261022 as transaction
from test_pad_bank_collector import fixture as native_fixture


def fixture(tmp_path,quarter=0,back=False,mirror=False):
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    board,pads,tracks=native_fixture(quarter*90,mirror,face)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    proposal=bank.plan(board,[force._uid(p)for p in pads],layer_id=face,
        clearance_nm=200000,min_thickness_nm=200000)
    child=force._copy_family(source,tmp_path/'child')
    made=bank.materialize(board,proposal);uid=made['zone_uuid']
    zone=next(z for z in board.Zones()if force._uid(z)==uid)
    selected=pcbnew.ZONES();selected.append(zone)
    cec_zone_fill.compile_selected(board,selected,initialize_selected=True)
    additive._ground_refill(board)
    native=tmp_path/'native-projection.kicad_pcb';field._save_field_snapshot(board,native)
    node=literal._inventory(raw.raw_text(native))[0][uid][2]
    original=raw.raw_text(source);end=literal._root(original)[1]
    raw.write_raw(child,original[:end]+'\n'+node+'\n'+original[end:])
    return source,child,proposal,uid


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('mirror',[False,True])
def test_fresh_native_saved_bank_reconstructs_exact_source_and_all_partitions(tmp_path,quarter,back,mirror):
    source,child,proposal,uid=fixture(tmp_path,quarter,back,mirror)
    before=source.read_bytes();q=copy.deepcopy(proposal)
    received=stage.receive(source,child,proposal,zone_uuid=uid,board_hint='synthetic')
    assert received['ok']and received['complete'],received
    assert received['only_one_native_collector_added']and received['original_objects_and_companions_preserved']
    assert received['independent_native_ground_and_bank_refill_equal']
    assert received['native_partition_preservation']['preserved']
    assert not received['new_capacity_credited']and not received['current_qualified']
    assert received['all_whole_board_gates_still_required']and not received['release_authority']
    assert source.read_bytes()==before and proposal==q


@pytest.mark.parametrize('fault',['track','part','lock','outline','thermal_relief','unfilled',
    'extra_zone','extra_track','companion','root_setting','proposal','missing_original','wrong_zone',
    'wrong_face','clearance','deadline'])
def test_saved_bank_cannot_hide_another_edit_or_supply_caller_zone_authority(tmp_path,fault):
    source,child,q,uid=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(child));zone=next(z for z in board.Zones()if force._uid(z)==uid)
    kwargs={}
    if fault=='track':next(iter(board.GetTracks())).SetWidth(3399999)
    elif fault=='part':next(iter(board.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='lock':next(iter(board.GetTracks())).SetLocked(False)
    elif fault=='outline':zone.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='thermal_relief':zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    elif fault=='unfilled':zone.UnFill()
    elif fault=='extra_zone':
        other=pcbnew.ZONE(board);other.SetNet(board.FindNet(q['net']));other.SetLayer(pcbnew.F_Cu)
        other.Outline().NewOutline()
        for x,y in ((70,70),(71,70),(71,71),(70,71)):other.Outline().Append(pcbnew.VECTOR2I_MM(x,y))
        board.Add(other)
    elif fault=='extra_track':
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(60,60));t.SetEnd(pcbnew.VECTOR2I_MM(61,60))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);board.Add(t)
    elif fault=='companion':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='root_setting':
        text=raw.raw_text(child)
        assert '(thickness 1.6)'in text
        raw.write_raw(child,text.replace('(thickness 1.6)','(thickness 1.5)',1))
    elif fault=='proposal':q['polygon_nm'][0][0]+=1
    elif fault=='missing_original':
        from cec_native_items import discard_items
        discard_items(board,[next(iter(board.GetTracks()))])
    elif fault=='wrong_zone':uid='00000000-0000-0000-0000-000000000001'
    elif fault=='wrong_face':zone.SetLayer(pcbnew.B_Cu)
    elif fault=='clearance':zone.SetLocalClearance(199999)
    elif fault=='deadline':kwargs['timeout_s']=float('inf')
    if fault not in('companion','proposal','wrong_zone','deadline','root_setting'):field._save_field_snapshot(board,child)
    before=source.read_bytes()
    result=stage.receive(source,child,q,zone_uuid=uid,board_hint='synthetic',**kwargs)
    assert not result['ok']and not result['complete']and result['errors'],result
    assert source.read_bytes()==before


def test_local_transaction_rederives_saved_bank_without_worker_success_or_waivers(tmp_path):
    source,child,q,uid=fixture(tmp_path)
    proposal=tmp_path/'proposal.json';proposal.write_text(json.dumps(q))
    row=dict(kind='source_pad_bank',candidate=str(child),candidate_sha256=force._hash(child),
        proposal=str(proposal),zone_uuid=uid)
    assert transaction.validate_phases([row])==['source_pad_bank']
    saved,proof=transaction.receive_phase(source,source,row,'synthetic')
    assert saved==child and proof['ok']and proof['complete']
    for key in('external_success','allow_new_power_zones','timeout_s','net','current_amps'):
        with pytest.raises(ValueError):transaction.validate_phases([dict(row,**{key:True})])
    with pytest.raises(ValueError):transaction.validate_phases([row,row])
