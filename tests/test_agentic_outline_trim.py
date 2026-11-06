"""No implicit mechanical or manufacturing authority from a rectangle trim."""
from copy import deepcopy
from pathlib import Path
import shutil
import sys
import time

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pcbnew
from cec_pipeline import outlines
from cec_pipeline import groundplanes as geom


def ring(x0,y0,x1,y1):
    return [[int(x*1e6),int(y*1e6)] for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1))]


def fixture(tmp_path, side=3, *, ground=True):
    board=pcbnew.BOARD(); edges=[]; points=ring(0,0,10,10)
    for a,b in zip(points,points[1:]+points[:1]):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I(*a));edge.SetEnd(pcbnew.VECTOR2I(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetWidth(50000);edge.SetLocked(True)
        board.Add(edge);edges.append(edge)
    board.GetDesignSettings().m_CopperEdgeClearance=200000
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('OPAQUE7');board.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I(5000000,5000000));fp.SetLocked(True)
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetSize(pcbnew.VECTOR2I(1000000,1000000))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetDrillSize(pcbnew.VECTOR2I(500000,500000));pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    pad.SetPosition(pcbnew.VECTOR2I(5000000,5000000));fp.Add(pad)
    cp=ring(4,4,6,6)
    for a,b in zip(cp,cp[1:]+cp[:1]):
        g=pcbnew.PCB_SHAPE(fp);g.SetShape(pcbnew.SHAPE_T_SEGMENT)
        g.SetStart(pcbnew.VECTOR2I(*a));g.SetEnd(pcbnew.VECTOR2I(*b))
        g.SetLayer(pcbnew.F_CrtYd);g.SetWidth(50000);fp.Add(g)
    for name in ('GND','POWER'):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net)
        zone=pcbnew.ZONE(board);zone.SetNet(net);zone.SetLayer(pcbnew.F_Cu if name=='GND' else pcbnew.B_Cu)
        zone.Outline().Append(geom._poly([ring(0,0,10,10)]));board.Add(zone)
        fill=ring(.2,.2,9.8,9.8) if name=='GND' else ring(1,1,9,9)
        zone.SetFilledPolysList(zone.GetLayer(),geom._poly([fill]));zone.SetIsFilled(True)
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    board=pcbnew.LoadBoard(str(source))
    edge_uid=edges[side].m_Uuid.AsString()
    position=500000 if side in (0,3) else 9500000
    op=dict(kind='outline_trim',edge_uuid=edge_uid,position_nm=position)
    record=outlines.construct(board,source,op,board_hint=None,request={'operations':[op]})
    candidate=tmp_path/'candidate.kicad_pcb';pcbnew.SaveBoard(str(candidate),board)
    sync(source,candidate)
    return source,candidate,op,record


def sync(source,candidate):
    for suffix in ('.kicad_pro','.kicad_prl'):
        if source.with_suffix(suffix).exists():shutil.copyfile(source.with_suffix(suffix),candidate.with_suffix(suffix))


def receive(values):return outlines.receive(*values,board_hint=None)


@pytest.mark.parametrize('side',range(4))
def test_all_four_edges_trim_exactly_three_primitives(tmp_path,side):
    values=fixture(tmp_path,side)
    result=receive(values)
    assert result['ok'] and len(result['edge_updates'])==3
    assert result['removed_ground_area2_nm2']>0
    assert not result['assembly_qualified'] and not result['fabrication_qualified']
    board=pcbnew.LoadBoard(str(values[1]));assert all(e.IsLocked() for e in board.GetDrawings())


@pytest.mark.parametrize('fault',('pad','footprint','unlock','powerfill','groundadd','randomcut','edgewidth','endpoint','global'))
def test_independent_saved_tamper_refused(tmp_path,fault):
    values=fixture(tmp_path);source,candidate,op,record=values
    board=pcbnew.LoadBoard(str(candidate));fp=list(board.GetFootprints())[0]
    if fault=='pad':list(fp.Pads())[0].SetSize(pcbnew.VECTOR2I(1100000,1000000))
    elif fault=='footprint':fp.SetPosition(pcbnew.VECTOR2I(5000001,5000000))
    elif fault=='unlock':fp.SetLocked(False)
    elif fault in ('powerfill','groundadd','randomcut'):
        zone=next(z for z in board.Zones() if z.GetNetname()==('POWER' if fault=='powerfill' else 'GND'))
        points=ring(.7,.2,9.7,9.8) if fault=='randomcut' else ring(.1,.1,9.9,9.9)
        zone.SetFilledPolysList(zone.GetLayer(),geom._poly([points]))
    elif fault=='global':board.SetCopperLayerCount(4)
    else:
        edge=next(e for e in board.GetDrawings() if e.m_Uuid.AsString()==op['edge_uuid'])
        if fault=='edgewidth':edge.SetWidth(60000)
        else:edge.SetStart(pcbnew.VECTOR2I(500001,10000000))
    pcbnew.SaveBoard(str(candidate),board);sync(source,candidate)
    with pytest.raises(ValueError):receive(values)


@pytest.mark.parametrize('position',(0,-1,10000000,10000001,500000.0,True))
def test_noop_reverse_collapse_or_noninteger_refused(tmp_path,position):
    source,_,op,_=fixture(tmp_path);op=deepcopy(op);op['position_nm']=position
    with pytest.raises(ValueError):outlines._plan(pcbnew.LoadBoard(str(source)),source,op,time.monotonic()+8)


@pytest.mark.parametrize('fault',('court','pad','hole','missingcourt','nonrectangle','extraoperation','record','companion'))
def test_positive_scope_and_source_witness_required(tmp_path,fault):
    values=list(fixture(tmp_path));source,candidate,op,record=values
    if fault=='record':
        record['position_nm']+=1
        with pytest.raises(ValueError):receive(values)
        return
    if fault=='companion':
        candidate.with_suffix('.kicad_pro').write_text('{}')
        with pytest.raises(ValueError):receive(values)
        return
    board=pcbnew.LoadBoard(str(source));fp=list(board.GetFootprints())[0]
    if fault=='court':
        g=next(g for g in fp.GraphicalItems() if g.GetLayer()==pcbnew.F_CrtYd)
        g.SetStart(pcbnew.VECTOR2I(400000,4000000))
    elif fault=='pad':list(fp.Pads())[0].SetPosition(pcbnew.VECTOR2I(600000,5000000))
    elif fault=='hole':list(fp.Pads())[0].SetDrillSize(pcbnew.VECTOR2I(10000000,10000000))
    elif fault=='missingcourt':
        for g in list(fp.GraphicalItems()):fp.Remove(g)
    elif fault=='nonrectangle':
        next(iter(board.GetDrawings())).SetShape(pcbnew.SHAPE_T_ARC)
    elif fault=='extraoperation':op['unlock']=True
    with pytest.raises(ValueError):outlines._plan(board,source,op,time.monotonic()+8)


def test_ground_fill_must_actually_clear_trimmed_edge(tmp_path):
    values=fixture(tmp_path);source,candidate,op,record=values
    board=pcbnew.LoadBoard(str(candidate))
    zone=next(z for z in board.Zones() if z.GetNetname()=='GND')
    # Still a subset of source and no remote loss, but not enough edge setback.
    zone.SetFilledPolysList(pcbnew.F_Cu,geom._poly([ring(.6,.2,9.8,9.8)]))
    pcbnew.SaveBoard(str(candidate),board);sync(source,candidate)
    with pytest.raises(ValueError,match='exact_source_edge_clip'):receive(values)


def test_fixed_power_fill_cannot_be_clipped_by_trim(tmp_path):
    source,_,op,_=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));zone=next(z for z in board.Zones() if z.GetNetname()=='POWER')
    zone.SetFilledPolysList(pcbnew.B_Cu,geom._poly([ring(.6,1,9,9)]))
    with pytest.raises(ValueError,match='fixed_non_ground_fill'):
        outlines._plan(board,source,op,time.monotonic()+8)


def test_constructor_clips_original_native_filler_geometry_without_repour(tmp_path,monkeypatch):
    source,_,op,_=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));zone=next(z for z in board.Zones() if z.GetNetname()=='GND')
    list(list(board.GetFootprints())[0].Pads())[0].SetNet(board.FindNet('GND'))
    import cec_zone_fill
    selected=pcbnew.ZONES();selected.append(zone)
    cec_zone_fill.compile_selected(board,selected,timeout_s=8.,initialize_selected=True)
    pcbnew.SaveBoard(str(source),board)
    board=pcbnew.LoadBoard(str(source))
    def forbidden(*args,**kwargs):raise AssertionError('trim must not repour')
    monkeypatch.setattr(cec_zone_fill,'compile_selected',forbidden)
    record=outlines.construct(board,source,op,board_hint=None,request={'operations':[op]})
    candidate=tmp_path/'native_clip.kicad_pcb';pcbnew.SaveBoard(str(candidate),board);sync(source,candidate)
    result=outlines.receive(source,candidate,op,record,board_hint=None)
    assert result['ok'] and result['removed_ground_area2_nm2']>0


def test_even_local_extra_ground_removal_is_not_exact_clip(tmp_path):
    values=fixture(tmp_path);source,candidate,op,record=values
    board=pcbnew.LoadBoard(str(candidate));zone=next(z for z in board.Zones() if z.GetNetname()=='GND')
    # An additional notch adjacent to the new setback is not the independently
    # expected half-plane clip; no agent-selected extra copper loss.
    shape=zone.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
    # Derive the notch from actual saved material, not a presumed default
    # project clearance: KiCad builds can restore different native defaults.
    box=shape.BBox();x=int(box.GetLeft());y=int(box.GetTop())+100000
    before_area=geom._area2(shape,time.monotonic()+2.)
    shape.BooleanSubtract(geom._poly([[[x,y],[x+10000,y],
                                      [x+10000,y+100000],[x,y+100000]]]))
    assert geom._area2(shape,time.monotonic()+2.)<before_area
    zone.SetFilledPolysList(pcbnew.F_Cu,shape)
    pcbnew.SaveBoard(str(candidate),board);sync(source,candidate)
    saved=pcbnew.LoadBoard(str(candidate))
    saved_zone=next(z for z in saved.Zones() if z.GetNetname()=='GND')
    assert geom._area2(saved_zone.GetFilledPolysList(pcbnew.F_Cu),
                       time.monotonic()+2.)<before_area
    with pytest.raises(ValueError,match='exact_source_edge_clip'):receive(values)


@pytest.mark.parametrize('fault',('dangling','wrong_face','wrong_owner_face'))
def test_unresolved_or_wrong_face_courtyard_cannot_authorize_trim(tmp_path,fault):
    source,_,op,_=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));fp=list(board.GetFootprints())[0]
    assert fp.GetCourtyard(pcbnew.F_Cu).OutlineCount()==1
    assert fp.GetCourtyard(pcbnew.B_Cu).OutlineCount()==0
    if fault=='dangling':
        for graphic in list(fp.GraphicalItems()):fp.Remove(graphic)
        graphic=pcbnew.PCB_SHAPE(fp);graphic.SetShape(pcbnew.SHAPE_T_SEGMENT)
        graphic.SetStart(pcbnew.VECTOR2I(4000000,4000000))
        graphic.SetEnd(pcbnew.VECTOR2I(6000000,4000000))
        graphic.SetLayer(pcbnew.F_CrtYd);graphic.SetWidth(50000);fp.Add(graphic)
    elif fault=='wrong_face':
        for graphic in fp.GraphicalItems():graphic.SetLayer(pcbnew.B_CrtYd)
    else:fp.SetLayer(pcbnew.B_Cu)
    # Re-read native derived courtyard caches after changing source geometry.
    altered=tmp_path/'altered_source.kicad_pcb';pcbnew.SaveBoard(str(altered),board)
    board=pcbnew.LoadBoard(str(altered))
    with pytest.raises(ValueError,match='valid_closed_occupied_face_courtyard'):
        outlines._plan(board,altered,op,time.monotonic()+8)


def test_valid_back_face_courtyard_is_received_without_front_fallback(tmp_path):
    source,_,op,_=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));fp=list(board.GetFootprints())[0]
    fp.SetLayer(pcbnew.B_Cu)
    for graphic in fp.GraphicalItems():graphic.SetLayer(pcbnew.B_CrtYd)
    altered=tmp_path/'back_source.kicad_pcb';pcbnew.SaveBoard(str(altered),board)
    board=pcbnew.LoadBoard(str(altered));fp=list(board.GetFootprints())[0]
    assert fp.GetCourtyard(pcbnew.B_Cu).OutlineCount()==1
    assert fp.GetCourtyard(pcbnew.F_Cu).OutlineCount()==0
    record=outlines._plan(board,altered,op,time.monotonic()+8)
    assert not record['assembly_qualified'] and not record['fabrication_qualified']
