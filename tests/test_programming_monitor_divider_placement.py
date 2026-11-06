"""Closed three-terminal monitor placement is not a two-terminal ILIM alias."""
import json
from pathlib import Path
import pcbnew
import pytest
import cec_field_coupling as field
import cec_programming_resistor_placement as op
from test_programming_resistor_placement import fixture,exported_pin


@pytest.mark.parametrize('pin',['4','5','6'])
@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_selected_closed_monitor_lower_retains_all_three_Source_peers(tmp_path,monkeypatch,pin,turn,back):
    board,owner,lower,root,tree,poses=fixture(tmp_path,monkeypatch,turn,back,monitor_pin=pin)
    before=op.row._source_binding(board);saved=Path(board.GetFileName()).read_bytes()
    selected=op.plan(board,poses,board_hint=str(root));item=selected[lower.GetReference()]
    model=item['source_proof']['manufacturer'];divider=item['source_monitor_divider']
    assert model['role']=='grounded_voltage_monitor_divider_lower'and item['control_pin']==pin
    assert model['manufacturer_monitor']['function']==op.PIN_NAMES[pin]
    assert divider['every_closed_node_member_mandatory']is True and len(divider['closed_node_members'])==3
    assert set(item['source_proof']['selected_components'])=={owner.GetReference(),lower.GetReference(),'R_upper'}
    label=op.ground_root(item,pad_uuid=item['ground_pad_uuid'],reference=lower.GetReference())
    assert op.ground_root_label(label)
    assert not any(item[k]for k in('bypass_owner','current_authority','programmed_current_qualified',
        'source_trace_retirement_authority','new_barrel_authority','release_authority'))
    assert not divider['voltage_transfer_or_operating_qualified']and not model['voltage_transfer_or_operating_qualified']
    child=pcbnew.LoadBoard(board.GetFileName());fp=child.FindFootprintByReference(lower.GetReference())
    target=poses[lower.GetReference()];fp.SetPosition(pcbnew.VECTOR2I_MM(*target[:2]));fp.SetOrientationDegrees(target[2])
    proposal=dict(poses=poses,board_hint=str(root),selected_programming_resistors=json.loads(json.dumps(selected)))
    requests=op.requests(board,child,proposal)
    assert len(requests)==2 and all(q['width_nm']>=board.GetDesignSettings().m_TrackMinWidth for q in requests.values())
    assert {q['b']['pad_uuid']for q in requests.values()}=={item['control_pad_uuid'],divider['upper_node_pad_uuid']}
    assert before==op.row._source_binding(board)and saved==Path(board.GetFileName()).read_bytes()


@pytest.mark.parametrize('fault',['upper_missing','upper_dnp','upper_wrong_value','upper_wrong_mpn','wrong_rail',
    'extra_peer','lower_changed','monitor_native_function','monitor_export_type','monitor_Source_name',
    'upper_Source_value','upper_export_missing','upper_noncardinal','manufacturer','monitor_package'])
def test_partial_or_contradictory_three_node_Source_has_no_placement_authority(tmp_path,monkeypatch,fault):
    board,owner,lower,root,tree,poses=fixture(tmp_path,monkeypatch,monitor_pin='6')
    upper=board.FindFootprintByReference('R_upper')
    if fault=='upper_missing':board.Remove(upper)
    elif fault=='upper_dnp':upper.SetDNP(True)
    elif fault=='upper_wrong_value':upper.SetValue('1kΩ')
    elif fault=='upper_wrong_mpn':upper.SetField('MPN','unverified')
    elif fault=='wrong_rail':upper.FindPadByNumber('1').SetNet(owner.FindPadByNumber('2').GetNet())
    elif fault=='extra_peer':
        extra=pcbnew.FOOTPRINT(board);extra.SetReference('unknown');board.Add(extra)
        p=pcbnew.PAD(extra);p.SetNumber('1');p.SetNet(owner.FindPadByNumber('6').GetNet());extra.Add(p)
    elif fault=='lower_changed':lower.SetValue('1kΩ')
    elif fault=='monitor_native_function':owner.FindPadByNumber('6').SetPinFunction('ILIM')
    elif fault=='monitor_export_type':op.synth._first(exported_pin(tree,owner.GetReference(),'6'),'pintype')[1]='output'
    elif fault=='monitor_Source_name':root.write_text(root.read_text().replace('(name "PR1")','(name "ILM")'))
    elif fault=='upper_Source_value':
        text=root.read_text();start=text.index('(property "Reference" "R_upper")')
        root.write_text(text[:start]+text[start:].replace('100kΩ','1kΩ',1))
    elif fault=='upper_export_missing':
        node=exported_pin(tree,'R_upper','2');op.synth._first(node,'ref')[1]='missing'
    elif fault=='upper_noncardinal':poses['R_upper']=[1.,2.,45.]
    elif fault=='manufacturer':owner.SetField('Manufacturer','unverified')
    else:owner.SetFPID(pcbnew.LIB_ID('fixture','other'))
    field._save_field_snapshot(board,Path(board.GetFileName()))
    before=Path(board.GetFileName()).read_bytes()
    try:result=op.plan(board,poses,board_hint=str(root))
    except ValueError:result={}
    assert not result and before==Path(board.GetFileName()).read_bytes()


@pytest.mark.parametrize('fault',['upper','upper_pad','lower','monitor','forged_third','forged_catalog','missing_mandatory'])
def test_actual_saved_replay_rejects_third_terminal_or_catalog_mutations(tmp_path,monkeypatch,fault):
    board,owner,lower,root,tree,poses=fixture(tmp_path,monkeypatch,monitor_pin='6')
    selected=op.plan(board,poses,board_hint=str(root));item=selected[lower.GetReference()]
    child=pcbnew.LoadBoard(board.GetFileName());fp=child.FindFootprintByReference(lower.GetReference())
    target=poses[lower.GetReference()];fp.SetPosition(pcbnew.VECTOR2I_MM(*target[:2]));fp.SetOrientationDegrees(target[2])
    if fault=='upper':child.FindFootprintByReference('R_upper').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='upper_pad':child.FindFootprintByReference('R_upper').FindPadByNumber('2').SetNetCode(0)
    elif fault=='lower':fp.SetValue('1kΩ')
    elif fault=='monitor':child.FindFootprintByReference(owner.GetReference()).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='forged_third':item['source_monitor_divider']['upper_node_pad_uuid']=item['signal_pad_uuid']
    elif fault=='forged_catalog':item['source_proof']['manufacturer']['role']='output_current_limit_programming'
    else:item['source_monitor_divider']['every_closed_node_member_mandatory']=False
    with pytest.raises(ValueError):op.requests(board,child,dict(poses=poses,board_hint=str(root),selected_programming_resistors=selected))


@pytest.mark.parametrize('fault',['ILIM_alias','pin','duplicate_peer','third_not_required','qualified','current'])
def test_ground_label_cannot_reclassify_monitor_into_current_or_two_terminal_role(tmp_path,monkeypatch,fault):
    board,owner,lower,root,tree,poses=fixture(tmp_path,monkeypatch,monitor_pin='6')
    item=op.plan(board,poses,board_hint=str(root))[lower.GetReference()]
    label=op.ground_root(item,pad_uuid=item['ground_pad_uuid'],reference=lower.GetReference())
    if fault=='ILIM_alias':item['source_proof']['manufacturer']['role']='output_current_limit_programming'
    elif fault=='pin':item['control_pin']='10'
    elif fault=='duplicate_peer':item['source_monitor_divider']['closed_node_members'][1]=item['source_monitor_divider']['closed_node_members'][0]
    elif fault=='third_not_required':item['source_monitor_divider']['every_closed_node_member_mandatory']=False
    elif fault=='qualified':item['source_monitor_divider']['voltage_transfer_or_operating_qualified']=True
    else:item['current_authority']=True
    assert not op.ground_root_label(label)


def moving_pair(tmp_path,monkeypatch,turn=0,back=False,pin='6'):
    import cec_decoupler_cell as cells
    board,owner,lower,root,tree,poses=fixture(tmp_path,monkeypatch,turn,back,monitor_pin=pin)
    upper=board.FindFootprintByReference('R_upper')
    poses['R_upper']=[upper.GetPosition().x/1e6+.5,upper.GetPosition().y/1e6+.5,
        (upper.GetOrientationDegrees()+90)%360]
    rail=dict(required_by_layer_nm={int(face):800000 if face in (0,2)else 1600000
        for face in board.GetEnabledLayers().CuStack()},current_authority={'fixture':'existing aggregate'})
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *args:rail)
    child=pcbnew.LoadBoard(board.GetFileName())
    for ref,target in poses.items():
        fp=child.FindFootprintByReference(ref);fp.SetPosition(pcbnew.VECTOR2I_MM(*target[:2]));fp.SetOrientationDegrees(target[2])
    return board,child,owner,lower,upper,root,poses,rail


@pytest.mark.parametrize('pin',['4','5','6'])
@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_complete_pair_can_move_with_source_owner_rail_and_all_contacts_retained(tmp_path,monkeypatch,pin,turn,back):
    board,child,owner,lower,upper,root,poses,rail=moving_pair(tmp_path,monkeypatch,turn,back,pin)
    before=Path(board.GetFileName()).read_bytes()
    selected=op.plan(board,poses,board_hint=str(root))
    assert op.participant_refs(selected)==set(poses)
    item=selected[lower.GetReference()];divider=item['source_monitor_divider']
    assert divider['upper_motion']is True
    assert set(divider['source_terminal_contacts'])=={op.force._uid(p)for p in upper.Pads()}
    assert 'source_stationary_upper_identity'not in divider
    assert not any(divider[k]for k in('current_authority','source_trace_retirement_authority','new_barrel_authority'))
    requests=op.requests(board,child,dict(poses=poses,board_hint=str(root),selected_programming_resistors=selected))
    assert len(requests)==3
    supply=next(q for q in requests.values()if q['role']=='manufacturer_monitor_divider_supply')
    assert supply['unchanged_full_rail_current_contract']==rail and supply['width_nm']==800000
    assert supply['b']['pad_uuid']==divider['associated_supply_pad_uuid']
    assert supply['a']['pad_uuid']==divider['upper_power_pad_uuid']
    assert before==Path(board.GetFileName()).read_bytes()


@pytest.mark.parametrize('fault',['owner_motion','upper_net','upper_value','upper_pose','upper_locked','upper_dnp',
    'upper_group','upper_pad','current_missing','current_partial','forged_contacts','forged_current','forged_motion'])
def test_complete_pair_replay_rejects_changed_parts_contacts_or_missing_rail(tmp_path,monkeypatch,fault):
    import cec_decoupler_cell as cells
    board,child,owner,lower,upper,root,poses,rail=moving_pair(tmp_path,monkeypatch)
    selected=op.plan(board,poses,board_hint=str(root));live=child.FindFootprintByReference('R_upper')
    divider=selected[lower.GetReference()]['source_monitor_divider']
    if fault=='owner_motion':child.FindFootprintByReference(owner.GetReference()).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='upper_net':live.FindPadByNumber('1').SetNetCode(0)
    elif fault=='upper_value':live.SetValue('1k')
    elif fault=='upper_pose':live.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='upper_locked':live.SetLocked(True)
    elif fault=='upper_dnp':live.SetDNP(True)
    elif fault=='upper_group':
        group=pcbnew.PCB_GROUP(child);child.Add(group);group.AddItem(live)
    elif fault=='upper_pad':live.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(1,1))
    elif fault=='current_missing':monkeypatch.setattr(cells,'_supply_current_widths',lambda *args:None)
    elif fault=='current_partial':rail['required_by_layer_nm'].pop(next(iter(rail['required_by_layer_nm'])))
    elif fault=='forged_contacts':divider['source_terminal_contacts']={}
    elif fault=='forged_current':divider['current_authority']=True
    else:divider['upper_motion']=False
    with pytest.raises(ValueError):op.requests(board,child,dict(poses=poses,board_hint=str(root),selected_programming_resistors=selected))


def test_pair_dispatch_and_independent_actual_pose_receiver_include_upper(tmp_path,monkeypatch):
    import cec_cell_escape_replan as escape
    import cec_complete_cell_receiving as saved
    board,child,owner,lower,upper,root,poses,rail=moving_pair(tmp_path,monkeypatch)
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**k:dict(assigned={}))
    proposal=escape.prepare(board,poses,board_hint=str(root))
    assert op.participant_refs(proposal['selected_programming_resistors'])==set(poses)
    assert not proposal['device_contracts']and not proposal['selected_bypasses']
    monkeypatch.setattr(saved,'_assignments',lambda *a:{})
    actual,moved=saved._poses(board,child,str(root))
    assert actual==poses and moved==set(poses)
