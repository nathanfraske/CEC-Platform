"""Only independently reconstructed selected-bypass rotations are received."""
from pathlib import Path

import pcbnew
import pytest

import cec_additive_route_receiving as receiving
import cec_constraints as constraints
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import test_decoupler_cell as fixtures


def fixture(tmp_path,monkeypatch,*,angle=90,back=False):
    board,assignment=fixtures.DecouplerCellTests()._board()
    cap=board.FindFootprintByReference('C1')
    cap.SetPosition(pcbnew.VECTOR2I_MM(11,10.5));cap.SetValue('100nF')
    if back:cap.Flip(cap.GetPosition(),False)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    # Synthetic selected device ownership, with real loaded native terminals.
    def selected(board,**_kwargs):
        owner=board.FindFootprintByReference('U1')
        return dict(assigned={'U1.2':dict(cap_ref='C1',requirement=dict(
            ref='U1',pin='2',rail='+3V3',return_rail='GND',pad=owner.FindPadByNumber('2')))})
    monkeypatch.setattr(constraints,'_device_bypass_assignment',selected)
    target=force._copy_family(source,tmp_path/'trial')
    b=pcbnew.LoadBoard(str(target));cap=b.FindFootprintByReference('C1')
    supply=cap.FindPadByNumber('1');pivot=supply.GetPosition()
    cap.Rotate(pivot,pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    ground=cap.FindPadByNumber('2')
    via=pcbnew.PCB_VIA(b);via.SetPosition(ground.GetPosition())
    via.SetWidth(pcbnew.FromMM(.35));via.SetDrill(pcbnew.FromMM(.25))
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNetCode(ground.GetNetCode());b.Add(via)
    assert fr.group_local_single_return_vias(b,[via])
    field._save_field_snapshot(b,target)
    final=receiving.finalize_private(source,target,tmp_path/'final')
    return source,Path(final['board'])


@pytest.mark.parametrize('angle',[90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_actual_native_cap_transform_keeps_supply_anchor_and_has_qualified_return(tmp_path,monkeypatch,angle,back):
    source,target=fixture(tmp_path,monkeypatch,angle=angle,back=back)
    original=source.read_bytes()
    assert not receiving.receive(source,target)['ok']
    receipt=receiving.receive(source,target,allow_fixed_supply_rotations=True)
    assert receipt['ok'] and receipt['complete'],receipt['errors']
    assert not receipt['original_power_and_terminal_geometry_exact']
    assert receipt['original_power_copper_and_supply_anchors_exact']
    proof=receipt['fixed_supply_rotations'][0]
    assert proof['rotation_delta_deg']==angle and proof['ground_topology']=='immediate_entry'
    assert not receipt['release_authority'] and source.read_bytes()==original


@pytest.mark.parametrize('fault',['supply_translation','cap_value','cap_ref','pad_net','cap_flip',
                                 'owner_move','no_return','bad_annulus','non_quarter','unassigned'])
def test_pose_scope_cannot_hide_unrelated_edits_or_unqualified_ground(tmp_path,monkeypatch,fault):
    source,target=fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(target));cap=board.FindFootprintByReference('C1')
    if fault=='supply_translation':cap.Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='cap_value':cap.SetValue('invented')
    elif fault=='cap_ref':cap.SetReference('another')
    elif fault=='pad_net':cap.FindPadByNumber('1').SetNetCode(board.GetNetcodeFromNetname('GND'))
    elif fault=='cap_flip':cap.Flip(cap.GetPosition(),False)
    elif fault=='owner_move':board.FindFootprintByReference('U1').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='no_return':board.Remove(next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA'))
    elif fault=='bad_annulus':next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA').SetWidth(pcbnew.FromMM(.25))
    elif fault=='non_quarter':cap.Rotate(cap.FindPadByNumber('1').GetPosition(),pcbnew.EDA_ANGLE(13,pcbnew.DEGREES_T))
    else:monkeypatch.setattr(constraints,'_device_bypass_assignment',lambda *a,**k:dict(assigned={}))
    field._save_field_snapshot(board,target)
    receipt=receiving.receive(source,target,allow_fixed_supply_rotations=True)
    assert not receipt['ok'] and not receipt['complete'] and receipt['errors'],receipt
