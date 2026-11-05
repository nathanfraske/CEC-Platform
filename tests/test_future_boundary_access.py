"""Actual native retained-component access, not same-name island guessing."""
import math
import time

import pcbnew
import pytest

import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_future_pose_clearance as future
import cec_ordinary_route_receiving as receiving
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, angle=0, back=False, net='/RENAMED_CONTROL'):
    board=_board([(5,10,net),(15,10,net)],edge=(0,0,20,20))
    layer=pcbnew.B_Cu if back else pcbnew.F_Cu
    if back:
        for fp in board.GetFootprints():fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    cut=track(board,net,(5,10),(15,10),width=.2,layer=layer)
    for x in (5,15):
        track(board,net,(x,10),(x,8),width=.2,layer=layer)
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(x,8))
        via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(board.FindNet(net));board.Add(via)
    # The old bend is blocked on the opposite face, but actual existing
    # barrels on its retained component provide legal access elsewhere.
    board.Add(pcbnew.NETINFO_ITEM(board,'/FOREIGN'))
    track(board,'/FOREIGN',(14.5,10),(15.5,10),width=1.,
        layer=pcbnew.F_Cu if back else pcbnew.B_Cu)
    if angle:
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(10,10),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    radians=math.radians(angle)
    def at(x,y):
        return [round((10+(x-10)*math.cos(radians)+(y-10)*math.sin(radians))*1e6),
            round((10-(x-10)*math.sin(radians)+(y-10)*math.cos(radians))*1e6)]
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(board,source)
    child=pcbnew.LoadBoard(str(source))
    discard_items(child,[t for t in child.GetTracks() if force._uid(t)==force._uid(cut)])
    return source,child,force._uid(cut),net,layer,at(5,10),at(15,10)


@pytest.mark.parametrize('angle,back,net',[(0,False,'/A'),(90,False,'/other/control'),
    (180,True,'/C'),(270,True,'/Fourth')])
def test_actual_retained_barrels_restore_every_boundary(tmp_path,angle,back,net):
    source,child,uid,net,layer,start,end=fixture(tmp_path,angle,back,net)
    saved=source.read_bytes();diagnostics={}
    ops=future._native_boundary_access(child,net,start,end,layer,200000,
        deadline=time.monotonic()+5.,gap=200000,spec={},maze_margin_mm=4.,
        validate_ops=lambda operations:True,planar_guard=None,diagnostics=diagnostics)
    assert ops and diagnostics['exact_retained_component_access'],diagnostics
    # No new barrel is needed: the menu uses the two real retained barrels.
    assert not any(op[0]=='via' for op in ops)
    for _,a,b,width,route_layer in ops:
        track(child,net,[v/1e6 for v in a],[v/1e6 for v in b],width=width/1e6,layer=route_layer)
    destination=tmp_path/'received'/'board.kicad_pcb';destination.parent.mkdir()
    field._save_field_snapshot(child,destination)
    proof=receiving.receive(source,destination,retired_track_uuids=[uid],board_hint='synthetic')
    assert proof['ok'] and proof['all_prior_native_terminal_partitions_preserved'],proof
    assert source.read_bytes()==saved


def test_same_name_island_does_not_become_a_retained_boundary(tmp_path):
    source,child,uid,net,layer,start,end=fixture(tmp_path)
    # Neither cut end is on this disconnected same-name edge.
    track(child,net,(7,6),(13,6),width=.2)
    before=field._field_snapshot_inventory(child)
    with pytest.raises(ValueError,match='retained_cut_boundary_native_contact_missing'):
        future._native_boundary_access(child,net,[8000000,7000000],end,layer,200000,
            deadline=time.monotonic()+5.,gap=200000,spec={},maze_margin_mm=4.,
            validate_ops=lambda operations:True,planar_guard=None,diagnostics={})
    assert field._field_snapshot_inventory(child)==before


def test_retained_access_does_not_override_the_validation_gate(tmp_path):
    source,child,uid,net,layer,start,end=fixture(tmp_path)
    before=field._field_snapshot_inventory(child)
    ops=future._native_boundary_access(child,net,start,end,layer,200000,
        deadline=time.monotonic()+.2,gap=200000,spec={},maze_margin_mm=4.,
        validate_ops=lambda operations:False,planar_guard=None,diagnostics={})
    assert not ops and field._field_snapshot_inventory(child)==before


@pytest.mark.parametrize('angle,net',[(0,'/a'),(90,'/different'),(180,'/renamed'),(270,'/hierarchy/control')])
def test_removed_edge_middle_barrel_is_a_real_source_boundary(tmp_path,angle,net):
    source,child,uid,net,layer,start,end=fixture(tmp_path,angle,False,net)
    board=pcbnew.LoadBoard(str(source))
    middle=pcbnew.PCB_VIA(board);middle.SetPosition(pcbnew.VECTOR2I_MM(10,10))
    middle.SetWidth(600000);middle.SetDrill(300000);middle.SetViaType(pcbnew.VIATYPE_THROUGH)
    middle.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);middle.SetNet(board.FindNet(net));board.Add(middle)
    # A near but disconnected same-name island must not get any cut access.
    orphan=pcbnew.PCB_VIA(board);orphan.SetPosition(pcbnew.VECTOR2I_MM(10,12))
    orphan.SetWidth(600000);orphan.SetDrill(300000);orphan.SetViaType(pcbnew.VIATYPE_THROUGH)
    orphan.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);orphan.SetNet(board.FindNet(net))
    if angle:orphan.Rotate(pcbnew.VECTOR2I_MM(10,10),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    board.Add(orphan)
    cut=future._cut_boundaries(board,{uid},time.monotonic()+5)
    assert cut[0]['anchors_nm']==sorted([start,[10000000,10000000],end])
    assert list(orphan.GetPosition()) not in cut[0]['anchors_nm']


def test_removed_edge_middle_native_tee_survives_without_a_pad_or_barrel(tmp_path):
    source,child,uid,net,layer,start,end=fixture(tmp_path)
    parent=pcbnew.LoadBoard(str(source))
    track(parent,net,(10,10),(10,12),width=.2)
    before=field._field_snapshot_inventory(parent)
    cuts=future._cut_boundaries(parent,{uid},time.monotonic()+5)
    assert [10000000,10000000] in cuts[0]['anchors_nm']
    assert before==field._field_snapshot_inventory(parent)


@pytest.mark.parametrize('angle',range(0,360,90))
def test_actual_boundary_barrel_is_not_reinterpreted_as_one_layer(tmp_path,angle):
    source,child,uid,net,layer,start,end=fixture(tmp_path,angle)
    barrels=[t for t in child.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()==net]
    diagnostics={}
    ops=future._native_boundary_access(child,net,list(barrels[0].GetPosition()),
        list(barrels[1].GetPosition()),layer,200000,deadline=time.monotonic()+5.,
        gap=200000,spec={},maze_margin_mm=4.,validate_ops=lambda operations:True,
        planar_guard=None,diagnostics=diagnostics)
    assert ops and not any(op[0]=='via' for op in ops),diagnostics
    first=diagnostics['exact_retained_component_access'][0]
    assert pcbnew.B_Cu in first['start']['layers'] and pcbnew.B_Cu in first['destination']['layers']
