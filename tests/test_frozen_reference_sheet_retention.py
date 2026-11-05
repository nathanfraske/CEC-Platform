"""Literal source-reference construction is not a small-loss tolerance."""
import copy
from pathlib import Path
import pcbnew
import pytest
import cec_frozen_reference_sheet_retention as repair
import cec_force_current as force
import cec_field_coupling as field
from cec_native_items import discard_items
from test_lastmile import _board
from test_field_proposals import track


def case(tmp_path,quarter=0,retired_foreign=False):
    board=_board([(3,3,'GND'),(10,10,'POWER')],edge=(-20,-20,30,30));board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    via=None
    if retired_foreign:
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(18,18));via.SetNet(board.FindNet('POWER'))
        via.SetWidth(800000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(board);z.SetLayer(face);z.SetNet(board.FindNet('GND'));z.SetZoneName('opaque actual reference')
        for p in ((-15,-15),(25,-15),(25,25),(-15,25)):
            if not z.Outline().OutlineCount():z.Outline().NewOutline()
            z.Outline().Append(pcbnew.VECTOR2I_MM(*p))
        fill=z.Outline().CloneDropTriangulation()
        if via:
            aperture=pcbnew.SHAPE_POLY_SET();via.TransformShapeToPolygon(aperture,face,200000,1000,pcbnew.ERROR_OUTSIDE)
            fill.BooleanSubtract(aperture);fill.Fracture()
        z.SetFilledPolysList(face,fill);z.SetIsFilled(True);board.Add(z)
    for i in [*board.GetFootprints(),*board.GetTracks(),*board.Zones(),*board.GetDrawings()]:
        if quarter:i.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    incoming=force._copy_family(source,tmp_path/'incoming');board=pcbnew.LoadBoard(str(incoming))
    if via:discard_items(board,[t for t in board.GetTracks() if force._uid(t)==force._uid(via)])
    # The incoming refill loses an explicit empty-region rectangle. Its
    # positive size is not rounded away by the receiver or comparator.
    for z in board.Zones():
        face=z.GetLayer();poly=z.GetFilledPolysList(face).CloneDropTriangulation();cut=pcbnew.SHAPE_POLY_SET();cut.NewOutline()
        for xy in ((0,0),(1,0),(1,1),(0,1)):cut.Append(pcbnew.VECTOR2I_MM(*xy))
        poly.BooleanSubtract(cut);poly.Fracture();z.SetFilledPolysList(face,poly)
    track(board,'POWER',(10,10),(14,10),width=.3).SetLayer(pcbnew.B_Cu)
    field._save_field_snapshot(board,incoming)
    return source,incoming


def make(source,incoming,tmp_path,proposal):
    child=force._copy_family(incoming,tmp_path/'child');field._save_field_snapshot(repair.construct(proposal),child);return child


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('retired_foreign',[False,True])
def test_exact_original_sheets_reconstructed_without_waiving_the_comparator(tmp_path,quarter,retired_foreign):
    source,incoming=case(tmp_path,quarter,retired_foreign);held=[p.read_bytes() for p in (source,incoming)]
    proposal=repair.plan(source,incoming,board_hint='opaque');child=make(source,incoming,tmp_path,proposal)
    got=repair.receive(source,incoming,child,proposal,board_hint='opaque')
    assert got['ok'] and got['complete'],got['errors']
    assert got['every_original_reference_node_byte_exact'] and got['all_other_incoming_native_objects_exact']
    assert got['all_incoming_native_partitions_preserved'] and len(got['restored_reference_zone_uuids'])==2
    assert not got['numeric_or_area_waiver_used'] and not got['release_authority']
    assert held==[p.read_bytes() for p in (source,incoming)]


@pytest.mark.parametrize('fault',['inner_copper','new_via','pad_pose','silk','profile','zone_intent','source_unfilled','settings','ground_track'])
def test_new_reference_obstacles_or_changed_source_authority_refuse_freezing(tmp_path,fault):
    source,incoming=case(tmp_path);board=pcbnew.LoadBoard(str(source if fault=='source_unfilled' else incoming))
    if fault=='inner_copper':track(board,'POWER',(10,10),(14,10),width=.3).SetLayer(pcbnew.In1_Cu)
    elif fault=='new_via':
        v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I_MM(10,10));v.SetNet(board.FindNet('POWER'))
        v.SetWidth(800000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(v)
    elif fault=='pad_pose':next(iter(board.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='silk':next(iter(board.GetFootprints())).Reference().SetTextSize(pcbnew.VECTOR2I_MM(3,3))
    elif fault=='profile':props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_2oz';board.SetProperties(props)
    elif fault=='zone_intent':next(iter(board.Zones())).SetMinThickness(99999)
    elif fault=='source_unfilled':next(iter(board.Zones())).UnFill()
    elif fault=='settings':board.SetCopperLayerCount(4)
    elif fault=='ground_track':track(board,'GND',(3,3),(5,3),width=.3)
    field._save_field_snapshot(board,source if fault=='source_unfilled' else incoming)
    with pytest.raises(ValueError):repair.plan(source,incoming,board_hint='opaque')


@pytest.mark.parametrize('fault',['pad','track','reference_fill','sidecar','forged_plan','extra_zone'])
def test_saved_reference_receiving_has_no_collateral_mutation_permission(tmp_path,fault):
    source,incoming=case(tmp_path);proposal=repair.plan(source,incoming,board_hint='opaque');child=make(source,incoming,tmp_path,proposal)
    board=pcbnew.LoadBoard(str(child))
    if fault=='pad':next(iter(board.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='track':next(iter(board.GetTracks())).SetWidth(300001)
    elif fault=='reference_fill':next(iter(board.Zones())).SetFilledPolysList(pcbnew.In1_Cu,pcbnew.SHAPE_POLY_SET())
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='forged_plan':proposal['reference_sha256']='0'*64
    elif fault=='extra_zone':z=next(iter(board.Zones())).Duplicate(False);z.m_Uuid.Clone(pcbnew.KIID());board.Add(z)
    field._save_field_snapshot(board,child)
    got=repair.receive(source,incoming,child,proposal,board_hint='opaque')
    assert not got['ok'] and got['errors']
