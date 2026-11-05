"""Exact native cardinal annotation transport, not physical pose admission."""
import copy
from pathlib import Path
import pcbnew
import pytest
import cec_source_reference_group_transport as op
import cec_field_coupling as field
import cec_source_retaining_ses_import as raw
from test_source_reference_group_transport import fixture as base_fixture


def fixture(tmp_path,*,back=False,source_turn=0,external=False):
    source,owner,gid=base_fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()));group=next(iter(b.Groups()))
    if back:fp.Flip(fp.GetPosition(),False)
    fp.SetOrientationDegrees(source_turn)
    # Rebuild only test annotation producer geometry for this actual native FP.
    for item in list(b.GetDrawings()):group.RemoveItem(item);b.Remove(item)
    face=pcbnew.F_SilkS if fp.IsFlipped()else pcbnew.B_SilkS
    text=pcbnew.PCB_TEXT(b);text.SetText(fp.GetReference());text.SetLayer(face)
    text.SetMirrored(face==pcbnew.B_SilkS);text.SetTextSize(pcbnew.VECTOR2I_MM(.8,.8))
    text.SetTextThickness(120000);text.SetTextPos(fp.GetPosition());text.SetKeepUpright(True)
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER);text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    b.Add(text);group.AddItem(text)
    court=fp.GetCourtyard(fp.GetLayer());chain=court.COutline(0)
    vertices=[tuple(chain.CPoint(i))for i in range(chain.PointCount())]
    for a,z in zip(vertices,vertices[1:]+vertices[:1]):
        line=pcbnew.PCB_SHAPE(b);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(face)
        line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*z));line.SetWidth(120000)
        b.Add(line);group.AddItem(line)
    if external:
        import cec_assembly_envelope as assembly
        from shapely.ops import nearest_points
        native=assembly.polygon_from_native(court)
        text.SetTextPos(pcbnew.VECTOR2I(round((native.bounds[2]+2)*1e6),fp.GetPosition().y))
        poly=pcbnew.SHAPE_POLY_SET();text.TransformShapeToPolygon(poly,face,0,1000,pcbnew.ERROR_OUTSIDE,False)
        glyph=assembly.polygon_from_native(poly)
        a,z=nearest_points(native,glyph.envelope.buffer(.262,join_style=2))
        leader=pcbnew.PCB_SHAPE(b);leader.SetShape(pcbnew.SHAPE_T_SEGMENT);leader.SetLayer(face)
        leader.SetStart(pcbnew.VECTOR2I(*(round(v*1e6)for v in a.coords[0])))
        leader.SetEnd(pcbnew.VECTOR2I(*(round(v*1e6)for v in z.coords[0])));leader.SetWidth(120000)
        b.Add(leader);group.AddItem(leader)
    group.SetLocked(True);fp.SetLocked(False);field._save_field_snapshot(b,source)
    return source,op.inspect(source,owner_uuid=owner,group_uuid=gid)


def literal_child(source,proof,path,turn,delta=(0,0)):
    nodes=op.expected_cardinal_nodes(proof,quarter_turns=turn,delta_nm=delta)
    text=source.read_text();spans=raw.inventory(text)
    for uid,node in sorted(nodes.items(),key=lambda row:spans[row[0]][0],reverse=True):
        a,z=spans[uid];text=text[:a]+op.ast._render(node)+text[z:]
    path.write_text(text)
    return path


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('source_turn',[0,90,180,270])
@pytest.mark.parametrize('turn',[0,1,2,3])
@pytest.mark.parametrize('external',[False,True])
def test_actual_native_and_literal_cardinal_replay(tmp_path,back,source_turn,turn,external):
    source,proof=fixture(tmp_path,back=back,source_turn=source_turn,external=external)
    original=source.read_bytes();b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    old_pos=tuple(fp.GetPosition());old_face=fp.IsFlipped();delta=(123457,-234569)
    before={op.force._uid(p):tuple(p.GetPosition())for p in fp.Pads()}
    old_upright=next(i for i in b.GetDrawings()if i.GetClass()=='PCB_TEXT').IsKeepUpright()
    result=op.transform_cardinal(b,proof,quarter_turns=turn,delta_nm=delta)
    assert tuple(fp.GetPosition())==(old_pos[0]+delta[0],old_pos[1]+delta[1])
    assert fp.GetOrientationDegrees()%360==(source_turn+turn*90)%360
    for p in fp.Pads():
        x,y=before[op.force._uid(p)][0]-old_pos[0],before[op.force._uid(p)][1]-old_pos[1]
        for _ in range(turn):x,y=y,-x
        assert tuple(p.GetPosition())==(old_pos[0]+x+delta[0],old_pos[1]+y+delta[1])
    assert fp.IsFlipped()==old_face and next(iter(b.Groups())).IsLocked()
    text=next(i for i in b.GetDrawings()if i.GetClass()=='PCB_TEXT')
    assert text.GetTextAngle().AsDegrees()in(0,90)and text.IsKeepUpright()==old_upright
    assert text.IsMirrored()==(text.GetLayer()==pcbnew.B_SilkS)
    child=literal_child(source,proof,tmp_path/'child.kicad_pcb',turn,delta)
    assert op.verify_cardinal(source,child,proof,quarter_turns=turn,delta_nm=delta)['ok']
    actual=pcbnew.LoadBoard(str(child));assert op._cardinal_identity(actual)==op._cardinal_identity(b)
    assert not result['pose_admitted']and not result['current_authority']and not result['release_authority']
    assert source.read_bytes()==original


@pytest.mark.parametrize('back',[False,True])
def test_four_quarter_turns_return_all_native_geometry_exactly(tmp_path,back):
    source,proof=fixture(tmp_path,back=back);initial=op._cardinal_identity(pcbnew.LoadBoard(str(source)))
    for index in range(4):
        child=literal_child(source,proof,tmp_path/('round'+str(index)+'.kicad_pcb'),1)
        assert op.verify_cardinal(source,child,proof,quarter_turns=1)['ok']
        source=child;proof=op.inspect(source,owner_uuid=proof['owner_uuid'],group_uuid=proof['group_uuid'])
    assert op._cardinal_identity(pcbnew.LoadBoard(str(source)))==initial


@pytest.mark.parametrize('fault',['angle','bool','negative','delta','pivot','member','source','ink','group','field','body','copper','flip'])
def test_no_caller_authority_or_changed_source_can_enter_transform(tmp_path,fault):
    source,proof=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));args=dict(quarter_turns=1)
    if fault=='angle':args['quarter_turns']=90
    elif fault=='bool':args['quarter_turns']=True
    elif fault=='negative':args['quarter_turns']=-1
    elif fault=='delta':args['delta_nm']=(1.,0)
    elif fault=='pivot':args['pivot_nm']=(0,0)
    elif fault=='member':proof=copy.deepcopy(proof);proof['member_uuids'].append('forged')
    elif fault=='source':source.write_text(source.read_text()+'\n')
    elif fault=='ink':next(iter(b.GetDrawings())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='group':next(iter(b.Groups())).SetLocked(False)
    elif fault=='field':next(iter(b.GetFootprints())).SetValue('changed')
    elif fault=='body':next(iter(next(iter(b.GetFootprints())).GraphicalItems())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='copper':
        t=pcbnew.PCB_TRACK(b);t.SetWidth(200000);b.Add(t)
    else:next(iter(b.GetFootprints())).Flip(pcbnew.VECTOR2I(0,0),False)
    before=op._cardinal_identity(b)
    with pytest.raises((ValueError,TypeError)):op.transform_cardinal(b,proof,**args)
    assert op._cardinal_identity(b)==before


@pytest.mark.parametrize('fault',['font','mirror','upright','ink','group','field','flip','copper'])
def test_saved_literal_and_native_mutations_refuse(tmp_path,fault):
    source,proof=fixture(tmp_path,external=True)
    child=literal_child(source,proof,tmp_path/'bad.kicad_pcb',1)
    b=pcbnew.LoadBoard(str(child));text=next(i for i in b.GetDrawings()if i.GetClass()=='PCB_TEXT')
    if fault=='font':text.SetTextThickness(130000)
    elif fault=='mirror':text.SetMirrored(not text.IsMirrored())
    elif fault=='upright':
        # Root PCB_TEXT KeepUpright is not persisted by KiCad. An authored
        # unknown directive must not be silently normalized into acceptance.
        child.write_text(child.read_text().replace('(gr_text ', '(gr_text (keep_upright yes) ',1))
        with pytest.raises(ValueError):op.verify_cardinal(source,child,proof,quarter_turns=1)
        return
    elif fault=='ink':next(i for i in b.GetDrawings()if i.GetClass()=='PCB_SHAPE').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='group':next(iter(b.Groups())).SetLocked(False)
    elif fault=='field':next(iter(b.GetFootprints())).SetValue('wrong')
    elif fault=='flip':next(iter(b.GetFootprints())).Flip(pcbnew.VECTOR2I(0,0),False)
    else:
        t=pcbnew.PCB_TRACK(b);t.SetWidth(200000);b.Add(t)
    field._save_field_snapshot(b,child)
    with pytest.raises(ValueError):op.verify_cardinal(source,child,proof,quarter_turns=1)
