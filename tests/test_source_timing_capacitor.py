"""Native/source SS role regressions; exporter/current fixtures are synthetic."""
import copy
from pathlib import Path

import pcbnew
import pytest
import cec_field_coupling as field
import cec_source_timing_capacitor as op
from test_programming_resistor_placement import fixture as base_fixture
from test_source_linear_power_stage import literal_erc_convention


def fixture(tmp_path,monkeypatch,turn=0,back=False):
    board,owner,cap,root,tree,poses=base_fixture(tmp_path,monkeypatch,turn,back)
    oldref=cap.GetReference();ref='C_timing'
    changes={oldref:ref,'100kΩ':'2.2uF','0402WGF1003TCE':'TIMING-CERAMIC',
        'UNI-ROYAL':'Fixture Ceramic',
        'R_0402_1005Metric':'C_0402_1005Metric','R_Small':'C_Small'}
    text=root.read_text()
    for old,new in changes.items():text=text.replace(old,new)
    text=text.replace('"fixture:R"','"fixture:C"')
    root.write_text(text)
    def rewrite(item):
        for i,value in enumerate(item):
            if isinstance(value,list):rewrite(value)
            elif isinstance(value,str):
                for old,new in changes.items():value=value.replace(old,new)
                item[i]=value
    rewrite(tree)
    cap.SetReference(ref);cap.SetValue('2.2uF');cap.SetField('MPN','TIMING-CERAMIC')
    cap.SetField('Manufacturer','Fixture Ceramic');cap.SetFPID(pcbnew.LIB_ID('fixture','C_0402_1005Metric'))
    signal=cap.FindPadByNumber('1');oldcode=signal.GetNetCode()
    signal.SetNet(owner.FindPadByNumber('11').GetNet())
    for track in board.GetTracks():
        if track.GetNetCode()==oldcode:track.SetNetCode(signal.GetNetCode())
    nets=op.synth._first(tree,'nets')
    oldnet=next(n for n in op.synth._kids(nets,'net')if op.synth._val(n,'name','')=='renamed-program')
    node=next(n for n in op.synth._kids(oldnet,'node')if op.synth._val(n,'ref','')==ref)
    oldnet.remove(node)
    soft=next(n for n in op.synth._kids(nets,'net')if op.synth._val(n,'name','')=='soft-start')
    soft.append(node)
    literal_erc_convention(board,owner,root,tree,{'11':'bidirectional'})
    poses={ref:poses[oldref]}
    return board,owner,cap,root,tree,poses


def plan(board,root,poses,**kw):
    return op.plan(board,poses,board_hint=str(root),**kw)


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_distinct_literal_SS_role_and_both_contacts(tmp_path,monkeypatch,turn,back):
    board,owner,cap,root,tree,poses=fixture(tmp_path,monkeypatch,turn,back)
    before=Path(board.GetFileName()).read_bytes()
    selected=plan(board,root,poses);item=selected[cap.GetReference()]
    assert op.participant_refs(selected)=={cap.GetReference()}
    assert item['control_pin']=='11'and item['role']==op.ROLE
    assert len(item['source_proof']['selected_components'][owner.GetReference()]['pins'])==12
    assert all(item['source_terminal_contacts'].values())
    assert all(item[k]is False for k in('bypass_owner','timing_qualified','current_authority',
        'source_trace_retirement_authority','new_barrel_authority','release_authority'))
    assert 'program_pin'not in item['source_proof']['manufacturer']
    label=op.ground_root(item,pad_uuid=item['ground_pad_uuid'],reference=cap.GetReference())
    assert op.ground_root_label(label)
    forged=copy.deepcopy(label);forged['source_timing_capacitor']['control_pin']='10'
    assert not op.ground_root_label(forged)
    assert Path(board.GetFileName()).read_bytes()==before


@pytest.mark.parametrize('flag',[0,1,None,'true',[],{}])
def test_strict_owner_optin(tmp_path,monkeypatch,flag):
    board,owner,cap,root,tree,poses=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='explicit_timing_owner'):
        plan(board,root,poses,allow_linear_power_stage_reconstruction=flag)


def test_owner_motion_default_refused(tmp_path,monkeypatch):
    board,owner,cap,root,tree,poses=fixture(tmp_path,monkeypatch)
    poses[owner.GetReference()]=[32.5,12,0]
    with pytest.raises(ValueError):plan(board,root,poses)


@pytest.mark.parametrize('kind',['input','passive','no_connect'])
def test_wrong_SS_source_electrical_type_refused(tmp_path,monkeypatch,kind):
    board,owner,cap,root,tree,poses=fixture(tmp_path,monkeypatch)
    literal_erc_convention(board,owner,root,tree,{'11':kind})
    with pytest.raises(ValueError):plan(board,root,poses)


def test_extra_native_SS_terminal_refused(tmp_path,monkeypatch):
    board,owner,cap,root,tree,poses=fixture(tmp_path,monkeypatch)
    extra=pcbnew.FOOTPRINT(board);extra.SetReference('unrelated');board.Add(extra)
    pad=pcbnew.PAD(extra);pad.SetNumber('1');pad.SetNet(owner.FindPadByNumber('11').GetNet());extra.Add(pad)
    field._save_field_snapshot(board,Path(board.GetFileName()))
    with pytest.raises(ValueError,match='complete_unique_canonical_SS'):plan(board,root,poses)


def test_capacitor_symbol_not_resistor_alias(tmp_path,monkeypatch):
    board,owner,cap,root,tree,poses=fixture(tmp_path,monkeypatch)
    comp=next(c for c in op.synth._kids(op.synth._first(tree,'components'),'comp')
        if op.synth._val(c,'ref','')==cap.GetReference())
    op.synth._first(op.synth._first(comp,'libsource'),'part')[1]='R_Small'
    with pytest.raises(ValueError,match='canonical_passive_timing_capacitor'):plan(board,root,poses)


def test_requests_fresh_replay_and_exact_independent_cap_pose(tmp_path,monkeypatch):
    board,owner,cap,root,tree,poses=fixture(tmp_path,monkeypatch)
    selected=plan(board,root,poses)
    child=pcbnew.LoadBoard(board.GetFileName());live=child.FindFootprintByReference(cap.GetReference())
    pose=poses[cap.GetReference()];live.SetPosition(pcbnew.VECTOR2I_MM(*pose[:2]));live.SetOrientationDegrees(pose[2])
    proposal=dict(poses=poses,board_hint=str(root),selected_timing_capacitors=selected)
    requests=op.requests(board,child,proposal)
    assert len(requests)==2
    request=next(v for v in requests.values()if v['kind']=='source_boundary')
    assert request['role']=='manufacturer_SS_timing_control'
    assert request['every_original_contact_and_immediate_Ground_return_still_required']is True
    ground=next(v for v in requests.values()if v['kind']=='ground')
    assert ground['reach_mm']==.8 and ground['width_nm']==250000
    proposal['selected_timing_capacitors']=copy.deepcopy(selected)
    proposal['selected_timing_capacitors'][cap.GetReference()]['source_value']='1uF'
    with pytest.raises(ValueError,match='fresh_Source_timing'):op.requests(board,child,proposal)


def moving_fixture(tmp_path,monkeypatch):
    """Only exporter, load model and selected-bypass inventory are synthetic."""
    board,owner,cap,root,tree,poses=fixture(tmp_path,monkeypatch)
    import cec_source_linear_power_stage as stage
    calls=[]
    def synthetic_current(board,source,net,hint):
        assert Path(source)==Path(board.GetFileName())and hint==str(root)
        assert net in('input-a','input-b','out');calls.append(net)
        return ('synthetic_test_only',dict(complete=True,net=net),
            dict(net=net,synthetic_test_only=True,amps=.125,geometry_margin=1.25))
    monkeypatch.setattr(stage.full,'_model',synthetic_current)
    monkeypatch.setattr(op.wired.cap.constraints,'_device_bypass_assignment',
        lambda *a,**k:dict(assigned={},missing=[]))
    poses[owner.GetReference()]=[owner.GetPosition().x/1e6+1,owner.GetPosition().y/1e6,90]
    return board,owner,cap,root,tree,poses,calls


def test_moving_owner_replays_complete_existing_three_domain_stage(tmp_path,monkeypatch):
    board,owner,cap,root,tree,poses,calls=moving_fixture(tmp_path,monkeypatch)
    selected=plan(board,root,poses,allow_linear_power_stage_reconstruction=True)
    item=selected[cap.GetReference()]
    assert 'source_stationary_owner_identity'not in item
    assert 'coherent_owner_motion'in item
    assert sorted(calls)==['input-a','input-b','out']
    child=pcbnew.LoadBoard(board.GetFileName())
    for ref,pose in poses.items():
        fp=child.FindFootprintByReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(*pose[:2]));fp.SetOrientationDegrees(pose[2])
    proposal=dict(poses=poses,board_hint=str(root),selected_timing_capacitors=selected,
        allow_linear_power_stage_reconstruction=True)
    assert op.requests(board,child,proposal)
    assert len(calls)==6
    # Removing explicit permission cannot be inferred from the stored proof.
    del proposal['allow_linear_power_stage_reconstruction']
    with pytest.raises(ValueError):op.requests(board,child,proposal)


@pytest.mark.parametrize('missing',[False,True])
def test_moving_owner_requires_complete_selected_followers(tmp_path,monkeypatch,missing):
    board,owner,cap,root,tree,poses,calls=moving_fixture(tmp_path,monkeypatch)
    inventory=dict(assigned={},missing=[dict(ref=owner.GetReference())])if missing else dict(
        assigned={'synthetic_bypass':dict(cap_ref='required_selected_bypass',
            requirement=dict(ref=owner.GetReference()))},missing=[])
    monkeypatch.setattr(op.wired.cap.constraints,'_device_bypass_assignment',lambda *a,**k:inventory)
    with pytest.raises(ValueError,match='complete_selected_owner_bypasses'):
        plan(board,root,poses,allow_linear_power_stage_reconstruction=True)


def test_changed_selected_part_field_refused(tmp_path,monkeypatch):
    board,owner,cap,root,tree,poses=fixture(tmp_path,monkeypatch)
    cap.SetField('MPN','different-part')
    field._save_field_snapshot(board,Path(board.GetFileName()))
    with pytest.raises(ValueError,match='identity_mismatch'):plan(board,root,poses)


def test_native_copper_artwork_contact_refused(tmp_path,monkeypatch):
    board,owner,cap,root,tree,poses=fixture(tmp_path,monkeypatch)
    shape=pcbnew.PCB_SHAPE(board);shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    p=cap.FindPadByNumber('1');shape.SetStart(p.GetPosition());shape.SetEnd(p.GetPosition()+pcbnew.VECTOR2I_MM(.5,0))
    shape.SetWidth(100000);shape.SetLayer(p.GetLayer());board.Add(shape)
    field._save_field_snapshot(board,Path(board.GetFileName()))
    with pytest.raises(ValueError,match='artwork'):plan(board,root,poses)


def test_unfilled_zone_is_not_absent_contact_evidence(tmp_path,monkeypatch):
    board,owner,cap,root,tree,poses=fixture(tmp_path,monkeypatch)
    zone=pcbnew.ZONE(board);zone.SetLayer(pcbnew.F_Cu)
    zone.SetNetCode(cap.FindPadByNumber('2').GetNetCode())
    outline=zone.Outline();outline.NewOutline()
    for x,y in((1,1),(2,1),(2,2),(1,2)):outline.Append(x*1000000,y*1000000)
    board.Add(zone);field._save_field_snapshot(board,Path(board.GetFileName()))
    with pytest.raises(ValueError,match='filled_zone_contacts'):plan(board,root,poses)


@pytest.mark.parametrize('pose',[[True,0,0],[0,float('nan'),0],[0,0,float('inf')]])
def test_nonliteral_pose_refused(tmp_path,monkeypatch,pose):
    board,owner,cap,root,tree,poses=fixture(tmp_path,monkeypatch)
    poses[cap.GetReference()]=pose
    with pytest.raises(ValueError,match='literal_finite'):plan(board,root,poses)
