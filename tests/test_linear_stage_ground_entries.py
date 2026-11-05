"""Independent power-stage Ground demands, not low-power portal authority.

Native saved packages, canonical Source and actual bypass assignment are real;
only the existing current/export fixture is explicitly synthetic test evidence.
"""
import copy
import json
from pathlib import Path
import uuid

import pcbnew
import pytest
import cec_field_coupling as field
import cec_linear_stage_ground_entries as op
from test_source_linear_power_stage import fixture as stage_fixture


def fixture(tmp_path, monkeypatch, turn=0, back=False):
    parent, owner, root, tree, poses, calls = stage_fixture(tmp_path, monkeypatch, turn, back)
    poses = {owner.GetReference(): [owner.GetPosition().x/1e6+.5,
        owner.GetPosition().y/1e6, owner.GetOrientationDegrees()]}
    for index, pin in enumerate(('7', '2', '1')):
        supply = owner.FindPadByNumber(pin)
        fp = pcbnew.FOOTPRINT(parent); fp.SetReference('C_min_'+str(index)); fp.SetValue('10uF')
        fp.SetFPID(pcbnew.LIB_ID('Capacitor_SMD', 'C_0805_2012Metric')); parent.Add(fp)
        fp.SetField('MPN', 'CL21A106KAYNNNE'); fp.SetField('Manufacturer', 'Samsung')
        fp.SetPosition(supply.GetPosition()+pcbnew.VECTOR2I(0,1000000))
        if back: fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for number, net, offset in [('1', supply.GetNet(), 0),
                ('2', owner.FindPadByNumber('12').GetNet(), 1000000)]:
            pad=pcbnew.PAD(fp); fp.Add(pad); pad.SetNumber(number)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I(500000,500000)); pad.SetNet(net)
            mask=pcbnew.LSET(); mask.AddLayer(pcbnew.B_Cu if back else pcbnew.F_Cu); pad.SetLayerSet(mask)
            pad.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I(0,offset)); pad.SetPinType('passive')
            netnode=next(n for n in op.stage.synth._kids(op.stage.synth._first(tree,'nets'),'net')
                if op.stage.synth._val(n,'name','')==net.GetNetname())
            netnode.append(['node',['ref',fp.GetReference()],['pin',number],['pinfunction','~'],['pintype','passive']])
        sid=str(uuid.uuid4()); ref=fp.GetReference()
        # Literal fixture component declarations, not a renamed unexported pad.
        text=root.read_text(); lib='fixture:C_'+str(index)
        declaration='(symbol "'+lib+'" (symbol "c_1_1" '+''.join(
            '(pin passive line (at '+str(i)+' 0 0) (length 1) (name "~") (number "'+str(i+1)+'"))'
            for i in range(2))+'))'
        text=text.replace('(lib_symbols ', '(lib_symbols '+declaration+' ',1)
        text=text[:-1]+'(symbol (lib_id "'+lib+'") (at '+str(300+index*10)+' 20 0) (unit 1) (uuid "'+sid+'") '+\
            '(property "Reference" "'+ref+'") (property "Value" "10uF") '+\
            '(property "Footprint" "'+fp.GetFPIDAsString()+'") '+\
            '(property "MPN" "CL21A106KAYNNNE") (property "Manufacturer" "Samsung")))'
        root.write_text(text)
        op.stage.synth._first(tree,'components').append(['comp',['ref',ref],['value','10uF'],
            ['footprint',fp.GetFPIDAsString()],['libsource',['lib','fixture'],['part','C']],['tstamps',sid]])
        poses[ref]=[fp.GetPosition().x/1e6+.5, fp.GetPosition().y/1e6, fp.GetOrientationDegrees()]
    field._save_field_snapshot(parent,Path(parent.GetFileName()))
    proof=op.stage.collect(parent,poses,board_hint=str(root),enabled=True)
    with op.force._thermal_hint(str(root)):
        assignment=op.constraints._device_bypass_assignment(parent,project_max_mm=3.5)
    selected={q['cap_ref']:dict(owner=q['requirement']['ref'],pin=str(q['requirement']['pin']),rail=q['requirement']['rail'])
        for q in assignment['assigned'].values() if q['requirement']['ref']==owner.GetReference()}
    assert len(selected)==3
    proposal=dict(poses=poses, source_linear_power_stages=proof, selected_bypasses=selected,
        allow_linear_power_stage_reconstruction=True, reference_group_uuids=[])
    posed=pcbnew.LoadBoard(parent.GetFileName())
    for ref,target in poses.items():
        fp=posed.FindFootprintByReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
        fp.SetOrientationDegrees(target[2])
    return parent,posed,proposal,str(root),owner.GetReference(),calls


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_positive_actual_Source_keeps_each_ground_independent(tmp_path,monkeypatch,turn,back):
    parent,posed,q,hint,owner,calls=fixture(tmp_path,monkeypatch,turn,back)
    before=(op.row._source_binding(parent),op.row._source_binding(posed),Path(parent.GetFileName()).read_bytes())
    result=op.entries(parent,posed,q,board_hint=hint)
    assert result['selected_bypasses']==q['selected_bypasses']
    demands=result['independent_ground_requests']
    root=posed.FindFootprintByReference(owner).FindPadByNumber('12')
    assert len(demands)==4 and 'ground:'+op.force._uid(root) in demands
    for demand in demands.values():
        assert demand['kind']=='ground' and demand['net']=='GND' and demand['reach_mm']==.8
        assert demand['same_package_ground_link_proposal_allowed'] is False
        assert demand['independent_linear_stage_ground_demand'] is True
        assert not any(k in demand for k in ('selected_bypass_entry','root_portal_pad_uuid','portal_pad_uuid'))
        assert demand['current_authority'] is False and demand['new_barrel_authority'] is False
    assert op.requests(parent,posed,q,board_hint=hint)==demands
    assert len(calls)==9  # Three independent current-net replays per Source collection.
    assert result['source_linear_power_stages']==q['source_linear_power_stages']
    assert json.loads(json.dumps(result))==result
    assert before==(op.row._source_binding(parent),op.row._source_binding(posed),Path(parent.GetFileName()).read_bytes())


@pytest.mark.parametrize('fault',['proof','option','missing_role','scope','pose','cap_pose','cap_value','cap_pad',
    'cap_net','cap_face','cap_dnp','cap_missing','owner_missing_pin','owner_value','selected_pin',
    'selected_missing','selected_foreign','follower_pose_missing','Source_missing_current'])
def test_forged_or_partial_scope_cannot_bypass_low_power_policy(tmp_path,monkeypatch,fault):
    parent,posed,q,hint,owner,calls=fixture(tmp_path,monkeypatch)
    cap=next(iter(q['selected_bypasses'])); fp=posed.FindFootprintByReference(cap)
    if fault=='proof': q['source_linear_power_stages'][owner]['current_authority']=True
    elif fault=='option': q['allow_linear_power_stage_reconstruction']=False
    elif fault=='missing_role': q.pop('source_linear_power_stages')
    elif fault=='scope': q['source_linear_power_stages']={}
    elif fault=='pose': q['poses'][owner][0]+=.01
    elif fault=='cap_pose': fp.Move(pcbnew.VECTOR2I(1000,0))
    elif fault=='cap_value': fp.SetValue('1nF')
    elif fault=='cap_pad': fp.FindPadByNumber('2').SetSize(pcbnew.VECTOR2I(900000,900000))
    elif fault=='cap_net': fp.FindPadByNumber('2').SetNet(fp.FindPadByNumber('1').GetNet())
    elif fault=='cap_face': fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    elif fault=='cap_dnp': fp.SetDNP(True)
    elif fault=='cap_missing': posed.Remove(fp)
    elif fault=='owner_missing_pin': posed.FindFootprintByReference(owner).Remove(posed.FindFootprintByReference(owner).FindPadByNumber('12'))
    elif fault=='owner_value': posed.FindFootprintByReference(owner).SetValue('unreviewed')
    elif fault=='selected_pin': q['selected_bypasses'][cap]['pin']='8'
    elif fault=='selected_missing': q['selected_bypasses'].pop(cap)
    elif fault=='selected_foreign': q['selected_bypasses'][cap]['owner']='not-the-stage'
    elif fault=='follower_pose_missing': q['poses'].pop(cap)
    elif fault=='Source_missing_current':
        def missing(*a,**k): raise ValueError('synthetic_missing_current')
        monkeypatch.setattr(op.stage.full,'_model',missing)
    with pytest.raises(ValueError): op.entries(parent,posed,q,board_hint=hint)


def test_original_selected_minimum_cannot_swap_to_another_same_rail_cap(tmp_path,monkeypatch):
    parent,posed,q,hint,owner,calls=fixture(tmp_path,monkeypatch)
    actual=op.constraints._device_bypass_assignment
    def changed(board,**kwargs):
        result=actual(board,**kwargs)
        if board is posed:
            result=copy.copy(result); result['assigned']=dict(result['assigned'])
            key=next(iter(result['assigned'])); result['assigned'][key]=dict(result['assigned'][key],cap_ref='unselected-cap')
        return result
    monkeypatch.setattr(op.constraints,'_device_bypass_assignment',changed)
    with pytest.raises(ValueError,match='selected_minima'): op.entries(parent,posed,q,board_hint=hint)


@pytest.mark.parametrize('timeout',[0,-1,10.001,float('nan'),True])
def test_timeout_is_bounded_before_Source_work(timeout):
    with pytest.raises(ValueError,match='bounded_linear_stage_ground'):
        op.entries(None,None,{},board_hint='unused',timeout_s=timeout)


def test_disabled_empty_scope_is_noop_without_invented_authority():
    assert op.entries(None,None,{},board_hint='unused')=={}
    assert op.requests(None,None,{},board_hint='unused')=={}


def test_ordinary_bypass_cannot_be_excluded_by_an_extra_proposal_row(tmp_path,monkeypatch):
    parent,posed,q,hint,owner,calls=fixture(tmp_path,monkeypatch)
    q['selected_bypasses']['unrelated_cap']=dict(owner='some_low_power_IC',pin='5',rail='input-a')
    result=op.entries(parent,posed,q,board_hint=hint)
    assert 'unrelated_cap' not in result['selected_bypasses']
    assert len(result['independent_ground_requests'])==4
