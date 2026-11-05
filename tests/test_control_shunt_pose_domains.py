"""A source-qualified RC shunt has geometric roles without becoming power."""
import copy
import time
from pathlib import Path

import pcbnew
import pytest

import cec_native_cell_pose_domains as domains
import cec_cell_escape_replan as escape
import cec_control_shunt_placement as shunt
import cec_field_coupling as field
import cec_force_current as force
from test_control_shunt_placement import fixture


def source(tmp_path,monkeypatch,turn=0,back=False):
    b,owner,g,root,unused=fixture(tmp_path,monkeypatch,0,False)
    # This canonical RC-only fixture deliberately has no power network.
    # Independent source-control topology and all actual native geometry
    # remain real; unrelated bypass assignment is tested in its own suites.
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**k:{'assigned':{}})
    b.SetCopperLayerCount(6);cap=g.GetParentFootprint()
    cap.SetPosition(pcbnew.VECTOR2I_MM(20,10))
    cap.FindPadByNumber('1').SetPosition(pcbnew.VECTOR2I_MM(19.55,10))
    cap.FindPadByNumber('2').SetPosition(pcbnew.VECTOR2I_MM(20.45,10))
    for fp in b.GetFootprints():
        bounds=[p.GetBoundingBox()for p in fp.Pads()]
        court=pcbnew.PCB_SHAPE(fp);court.SetShape(pcbnew.SHAPE_T_RECT);court.SetLayer(pcbnew.F_CrtYd)
        court.SetWidth(50000);court.SetStart(pcbnew.VECTOR2I(min(v.GetLeft()for v in bounds)-100000,min(v.GetTop()for v in bounds)-100000))
        court.SetEnd(pcbnew.VECTOR2I(max(v.GetRight()for v in bounds)+100000,max(v.GetBottom()for v in bounds)+100000));fp.Add(court)
    if turn:
        origin=pcbnew.VECTOR2I_MM(35,15)
        for fp in b.GetFootprints():fp.Rotate(origin,pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    if back:
        for fp in b.GetFootprints():fp.Flip(pcbnew.VECTOR2I_MM(35,15),False)
    for a,c in [((-20,-30),(90,-30)),((90,-30),(90,70)),((90,70),(-20,70)),((-20,70),(-20,-30))]:
        e=pcbnew.PCB_SHAPE(b);e.SetShape(pcbnew.SHAPE_T_SEGMENT);e.SetLayer(pcbnew.Edge_Cuts)
        e.SetStart(pcbnew.VECTOR2I_MM(*a));e.SetEnd(pcbnew.VECTOR2I_MM(*c));e.SetWidth(50000);b.Add(e)
    path=Path(b.GetFileName());field._save_field_snapshot(b,path)
    monkeypatch.setattr(force,'_family',lambda p,h:dict(board=force._hash(Path(p)),source=force._hash(root)))
    pose=[cap.GetPosition().x/1e6+.3,cap.GetPosition().y/1e6,cap.GetOrientationDegrees()]
    return path,b,owner,cap,root,{cap.GetReference():pose}


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_fresh_native_control_shunt_has_bounded_nonpower_choices(tmp_path,monkeypatch,turn,back):
    path,b,owner,cap,root,poses=source(tmp_path,monkeypatch,turn,back);before=path.read_bytes()
    result=domains.propose(path,poses,board_hint=str(root),radius_mm=.75,grid_mm=.25,
        max_candidates=8,max_results=1,complete_owner_ground=False)
    assert result['domains'][cap.GetReference()],result['domain_stages']
    for choice in result['domains'][cap.GetReference()]:
        assert 'control_signal_nm'in choice and 'supply_nm'not in choice
        assert len(choice['ground_nm'])==1
    assert path.read_bytes()==before and not result['routing_admitted']


@pytest.mark.parametrize('fault',['no_mpn','different_net','dnp'])
def test_unqualified_cap_never_acquires_control_geometry_from_its_name(tmp_path,monkeypatch,fault):
    path,b,owner,cap,root,poses=source(tmp_path,monkeypatch)
    if fault=='no_mpn':owner.SetField('MPN','unknown')
    elif fault=='different_net':cap.FindPadByNumber('1').SetNetCode(0)
    else:cap.SetDNP(True)
    field._save_field_snapshot(b,path)
    with pytest.raises(ValueError):
        domains.propose(path,poses,board_hint=str(root),radius_mm=.75,grid_mm=.25,
            max_candidates=8,max_results=1,complete_owner_ground=False)


@pytest.mark.parametrize('whole_owner',[False,True])
def test_control_ground_cannot_disappear_from_early_physical_receiving(monkeypatch,whole_owner):
    seen=[]
    def screen(board,refs,**kwargs):
        seen.append((refs,kwargs));return {'ok':False,'mandatory_native_ground_refusal':True}
    monkeypatch.setattr(domains.frontier,'ground_screen',screen)
    plan=dict(selected_bypasses={},selected_control_shunts={'arbitrary_rc':{}},device_contracts={},poses={'arbitrary_rc':[1,2,0]},stationary_device_owners=[])
    proof=domains._pose_ground_screen(None,plan,board_hint='not-a-net-name',timeout_s=1.,complete_owner_ground=whole_owner)
    assert not proof['ok']and seen[0][0]==['arbitrary_rc']
    assert seen[0][1]['reach_mm']==.8


def test_exact_prepared_cell_motion_binds_the_same_saved_rule_context_as_macro(tmp_path,monkeypatch):
    path,b,owner,cap,root,poses=source(tmp_path,monkeypatch)
    proposal=escape.prepare(b,poses,board_hint=str(root))
    child=pcbnew.LoadBoard(str(path));escape.apply_private(child,proposal)
    assert child._cec_projected_saved_pad_rule_poses==poses
    assert child._cec_projected_saved_pad_rule_allow_octilinear_rotations is False
    # The context is transient and grants no saved geometry or routing proof.
    assert path.read_bytes()==Path(b.GetFileName()).read_bytes()
    assert not proposal['routing_admitted']
