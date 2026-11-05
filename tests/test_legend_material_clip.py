"""Silk body lines clip to real substrate; copper, labels and markers stay."""
import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_board_geometry as geometry
import cec_legend_repair as repair


def fixture(rotation,back=False):
    board=pcbnew.CreateEmptyBoard()
    vertices=[(0,0),(10,0),(10,10),(18,10),(18,0),(40,0),(40,40),(0,40)]
    for a,b in zip(vertices,vertices[1:]+vertices[:1]):
        edge=pcbnew.PCB_SHAPE(board);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetWidth(100000)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)
    hole=pcbnew.PCB_SHAPE(board);hole.SetLayer(pcbnew.Edge_Cuts)
    hole.SetShape(pcbnew.SHAPE_T_CIRCLE);hole.SetStart(pcbnew.VECTOR2I_MM(28,28))
    hole.SetEnd(pcbnew.VECTOR2I_MM(32,28));board.Add(hole)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('ANY123');board.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I_MM(5,20));fp.Reference().SetVisible(True)
    fp.Reference().SetPosition(pcbnew.VECTOR2I_MM(14,5))
    fp.Reference().SetTextSize(pcbnew.VECTOR2I_MM(1,1))
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetPosition(pcbnew.VECTOR2I_MM(5,20))
    pad.SetSize(pcbnew.VECTOR2I_MM(1,1));fp.Add(pad)
    def line(a,b,layer):
        item=pcbnew.PCB_SHAPE(fp);item.SetShape(pcbnew.SHAPE_T_SEGMENT)
        item.SetLayer(layer);item.SetWidth(200000);item.SetStart(pcbnew.VECTOR2I_MM(*a))
        item.SetEnd(pcbnew.VECTOR2I_MM(*b));fp.Add(item);return item
    layer=pcbnew.B_SilkS if back else pcbnew.F_SilkS
    crossing=[line((8,5),(22,5),layer),line((22,28),(36,28),layer)]
    marker=line((12,2),(15,2),layer)
    copper=line((8,5),(22,5),pcbnew.F_Cu)
    if rotation:
        at=pcbnew.VECTOR2I_MM(20,20);angle=pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T)
        for item in [*board.GetDrawings(),fp]:item.Rotate(at,angle)
    return board,fp,pad,crossing,marker,copper


def protected(board,fp,pad,marker,copper):
    def shape(s):return s.m_Uuid.AsString(),s.GetShape(),tuple(s.GetStart()),tuple(s.GetEnd()),s.GetLayer(),s.GetWidth()
    text=fp.Reference()
    return (sorted(shape(e) for e in board.GetDrawings()),tuple(fp.GetPosition()),fp.GetOrientationDegrees(),
        tuple(pad.GetPosition()),tuple(pad.GetSize()),text.GetText(),tuple(text.GetPosition()),
        tuple(text.GetTextSize()),text.IsVisible(),shape(marker),shape(copper))


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_notches_holes_and_both_faces_keep_entire_stroke_clear(tmp_path,rotation,back):
    b,fp,pad,crossing,marker,copper=fixture(rotation,back)
    old=protected(b,fp,pad,marker,copper)
    result=repair.clip_line_art_to_material(b,clearance_mm=.15)
    assert result['complete'] and result['applied_count']==2,result
    assert result['release_authority'] is False
    assert result['refused']==[dict(uuid=marker.m_Uuid.AsString(),reason='would_erase_entire_graphic')]
    assert old==protected(b,fp,pad,marker,copper)
    path=tmp_path/'saved.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    actual=pcbnew.LoadBoard(str(path));outline=geometry.outline_material(actual)
    boundaries=geometry.material_boundaries(outline)
    pieces=[s for f in actual.GetFootprints() for s in f.GraphicalItems()
            if s.GetLayer()==(pcbnew.B_SilkS if back else pcbnew.F_SilkS)
            and s.m_Uuid.AsString()!=marker.m_Uuid.AsString()]
    assert len(pieces)==4
    assert len({s.m_Uuid.AsString() for s in pieces})==4
    assert all(geometry.material_leg_clear(outline,boundaries,s.GetStart(),s.GetEnd(),250000) for s in pieces)
    again=repair.clip_line_art_to_material(actual,clearance_mm=.15)
    assert again['complete'] and again['applied_count']==0,again


def test_locked_or_group_owned_art_is_not_silently_changed():
    b,fp,pad,crossing,marker,copper=fixture(0)
    crossing[0].SetLocked(True)
    group=pcbnew.PCB_GROUP(b);group.AddItem(crossing[1]);b.Add(group)
    before=[(tuple(s.GetStart()),tuple(s.GetEnd())) for s in crossing]
    result=repair.clip_line_art_to_material(b,clearance_mm=.15)
    assert result['complete'] and result['applied_count']==0
    assert [r['reason'] for r in result['refused']].count('owned_or_locked_silk_graphic')==2
    assert before==[(tuple(s.GetStart()),tuple(s.GetEnd())) for s in crossing]


@pytest.mark.parametrize('options',[dict(clearance_mm=float('nan')),dict(clearance_mm=.15,timeout_s=0),
    dict(clearance_mm=.15,max_items=1),dict(clearance_mm=.15,graphic_uuid_scope=['not-a-live-uuid'])])
def test_incomplete_or_stale_plan_never_mutates(options):
    b,fp,pad,crossing,marker,copper=fixture(0)
    before=[(s.m_Uuid.AsString(),tuple(s.GetStart()),tuple(s.GetEnd())) for s in fp.GraphicalItems()]
    result=repair.clip_line_art_to_material(b,**options)
    assert not result['complete'] and result['applied_count']==0
    assert before==[(s.m_Uuid.AsString(),tuple(s.GetStart()),tuple(s.GetEnd())) for s in fp.GraphicalItems()]


def test_broken_outline_cannot_use_a_rectangle_fallback():
    b,fp,pad,crossing,marker,copper=fixture(0)
    b.Remove(next(s for s in b.GetDrawings() if s.GetShape()==pcbnew.SHAPE_T_SEGMENT))
    result=repair.clip_line_art_to_material(b,clearance_mm=.15)
    assert not result['complete'] and result['applied_count']==0


def test_substrate_sliver_is_not_erased_or_made_into_a_dot():
    b,fp,pad,crossing,marker,copper=fixture(0)
    item=crossing[0]
    item.SetStart(pcbnew.VECTOR2I_MM(9.6,5));item.SetEnd(pcbnew.VECTOR2I_MM(12,5))
    before=tuple(item.GetStart()),tuple(item.GetEnd())
    result=repair.clip_line_art_to_material(b,clearance_mm=.15)
    assert result['complete'] and result['applied_count']==1,result
    assert dict(uuid=item.m_Uuid.AsString(),reason='cannot_retain_manufacturable_native_piece') in result['refused']
    assert before==(tuple(item.GetStart()),tuple(item.GetEnd()))
