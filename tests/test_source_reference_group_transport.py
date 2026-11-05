import copy
import pytest
import pcbnew
import cec_source_reference_group_transport as op
import cec_field_coupling as field
import cec_force_current as force
import cec_source_retaining_ses_import as raw
from test_lastmile import _board


def fixture(tmp_path, fault=None):
    b = _board([(10, 10, '/N')], edge=(0, 0, 30, 30))
    fp = next(iter(b.GetFootprints())); fp.SetReference('X7'); fp.Reference().SetVisible(False)
    for a, z in [((-3,-2),(3,-2)),((3,-2),(3,2)),((3,2),(-3,2)),((-3,2),(-3,-2))]:
        line = pcbnew.PCB_SHAPE(fp); line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetLayer(pcbnew.F_CrtYd); line.SetStart(pcbnew.VECTOR2I_MM(10+a[0],10+a[1])); line.SetEnd(pcbnew.VECTOR2I_MM(10+z[0],10+z[1])); fp.Add(line)
    g = pcbnew.PCB_GROUP(b); g.SetName(op.PREFIX+'X7'); b.Add(g); g.AddItem(fp)
    text = pcbnew.PCB_TEXT(b); text.SetText('X7'); text.SetLayer(pcbnew.B_SilkS)
    text.SetMirrored(True); text.SetTextSize(pcbnew.VECTOR2I_MM(.8,.8)); text.SetTextThickness(120000)
    text.SetTextPos(pcbnew.VECTOR2I_MM(10,10)); text.SetKeepUpright(True)
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER); text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    b.Add(text); g.AddItem(text)
    chain=fp.GetCourtyard(fp.GetLayer()).COutline(0)
    points=[(chain.CPoint(i).x,chain.CPoint(i).y)for i in range(chain.PointCount())]
    for a,z in zip(points,points[1:]+points[:1]):
        line=pcbnew.PCB_SHAPE(b); line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.B_SilkS)
        line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*z));line.SetWidth(120000);b.Add(line);g.AddItem(line)
    g.SetLocked(True); fp.SetLocked(False)
    if fault=='name':g.SetName('arbitrary')
    elif fault=='visible':fp.Reference().SetVisible(True)
    elif fault=='wrongtext':text.SetText('X8')
    elif fault=='hidden':text.SetVisible(False)
    elif fault=='layer':text.SetLayer(pcbnew.F_SilkS)
    elif fault=='mirror':text.SetMirrored(False)
    elif fault=='font':text.SetTextSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='lockedfp':fp.SetLocked(True)
    elif fault=='court':next(i for i in g.GetItems()if i.GetClass()=='PCB_SHAPE').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='copper':
        t=pcbnew.PCB_TRACK(b);t.SetNetCode(1);t.SetLayer(0);t.SetStart(pcbnew.VECTOR2I_MM(1,1));t.SetEnd(pcbnew.VECTOR2I_MM(2,1));t.SetWidth(200000);b.Add(t);g.AddItem(t)
    elif fault=='secondfp':
        f=pcbnew.FOOTPRINT(b);f.SetReference('X8');b.Add(f);g.AddItem(f)
    elif fault=='nested':
        h=pcbnew.PCB_GROUP(b);h.SetName('parent');b.Add(h);h.AddItem(g)
    path=tmp_path/'board.kicad_pcb';field._save_field_snapshot(b,path)
    if fault=='hidden':
        # Root PCB_TEXT visibility is not serialized by KiCad. An explicit
        # source hide must still fail closed rather than vanish on load.
        path.write_text(path.read_text().replace('(gr_text "X7"','(gr_text "X7" (hide yes)',1))
    return path,force._uid(fp),force._uid(g)


def test_native_translation_and_exact_source_ast(tmp_path):
    source, owner, group = fixture(tmp_path)
    proof=op.inspect(source,owner_uuid=owner,group_uuid=group)
    b=pcbnew.LoadBoard(str(source));op.transform(b,proof,delta_nm=(250000,-500000))
    child=tmp_path/'child.kicad_pcb';field._save_field_snapshot(b,child)
    assert op.verify(source,child,proof,delta_nm=(250000,-500000))['ok']
    assert next(iter(b.Groups())).IsLocked() and not next(iter(b.GetFootprints())).IsLocked()
    assert not proof['pose_admitted'] and not proof['release_authority']


@pytest.mark.parametrize('fault',['name','visible','wrongtext','hidden','layer','mirror','font','lockedfp','court','copper','secondfp','nested'])
def test_unrecognized_source_group_fails_closed(tmp_path,fault):
    source,owner,group=fixture(tmp_path,fault)
    with pytest.raises(ValueError):op.inspect(source,owner_uuid=owner,group_uuid=group)


def test_forged_member_and_rotation_cannot_be_transport_authority(tmp_path):
    source,owner,group=fixture(tmp_path);p=op.inspect(source,owner_uuid=owner,group_uuid=group)
    forged=copy.deepcopy(p);forged['member_uuids'].append('invented')
    with pytest.raises(ValueError):op.transform(pcbnew.LoadBoard(str(source)),forged,delta_nm=(1,0))
    with pytest.raises(ValueError):op.expected_nodes(p,delta_nm=(True,0))
    b=pcbnew.LoadBoard(str(source));op.transform(b,p,delta_nm=(250000,0));next(iter(b.GetFootprints())).Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(90,pcbnew.DEGREES_T))
    child=tmp_path/'rotated.kicad_pcb';field._save_field_snapshot(b,child)
    with pytest.raises(ValueError):op.verify(source,child,p,delta_nm=(250000,0))


@pytest.mark.parametrize('bad',['owner','group'])
def test_missing_actual_owner_or_group_identity(tmp_path,bad):
    source,owner,group=fixture(tmp_path)
    with pytest.raises(ValueError):
        op.inspect(source,owner_uuid='missing' if bad=='owner' else owner,
                   group_uuid='missing' if bad=='group' else group)


def two_maps(tmp_path):
    one=tmp_path/'one';two=tmp_path/'two';one.mkdir();two.mkdir()
    source,owner,group=fixture(one);other,owner2,group2=fixture(two)
    # Compose literal fixture nodes so every group keeps its actual native
    # member UUIDs; PCB_SHAPE copy constructors regenerate those identities.
    second=other.read_text().replace('"X7"','"X8"').replace(op.PREFIX+'X7',op.PREFIX+'X8')
    extra=[second[a:z]for a,z in raw.children(second)if raw.kind(second[a:z])in('footprint','gr_text','gr_line','group')]
    first=source.read_text();at=first.rfind(')');source.write_text(first[:at]+'\n'+'\n'.join(extra)+'\n'+first[at:])
    return source,[(owner,group),(owner2,group2)]


def test_fresh_batch_matches_standalone_and_parses_source_once(tmp_path,monkeypatch):
    source,selections=two_maps(tmp_path);before=source.read_bytes();nodes=op.ast._nodes;calls=[]
    def counted(path):calls.append(str(path));return nodes(path)
    monkeypatch.setattr(op.ast,'_nodes',counted)
    batch=op.inspect_many(source,selections);assert len(calls)==1
    assert op.inspect_many(source,selections)==batch and len(calls)==2
    assert batch==[op.inspect(source,owner_uuid=o,group_uuid=g)for o,g in selections]
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['owner','group','duplicate','empty','too_many','caller_cache'])
def test_batch_does_not_accept_poisoned_members_or_external_context(tmp_path,fault):
    source,selections=two_maps(tmp_path)
    if fault=='owner':selections[1]=('invented',selections[1][1])
    if fault=='group':selections[1]=(selections[1][0],'invented')
    if fault=='duplicate':selections.append(selections[0])
    if fault=='empty':selections=[]
    if fault=='too_many':selections=[(str(i),str(i))for i in range(129)]
    with pytest.raises((TypeError,ValueError)):
        op.inspect_many(source,selections,**({'cache':{}}if fault=='caller_cache'else{}))


@pytest.mark.parametrize('fault',['source','code','expired'])
def test_batch_rechecks_live_source_and_code_after_all_native_proofs(tmp_path,monkeypatch,fault):
    source,selections=two_maps(tmp_path);inspect=op._inspect_bound;state={'changed':False}
    code=op.force._code_identity
    def changed(*a,**kw):
        value=inspect(*a,**kw)
        if not state['changed']:
            state['changed']=True
            if fault=='source':source.write_text(source.read_text()+'\n')
        return value
    monkeypatch.setattr(op,'_inspect_bound',changed)
    if fault=='code':monkeypatch.setattr(op.force,'_code_identity',lambda:'changed'if state['changed']else code())
    if fault=='expired':
        tick=[0]
        def clock():tick[0]+=1;return 0 if tick[0]<3 else 20
        monkeypatch.setattr(op.time,'monotonic',clock)
    with pytest.raises(ValueError):op.inspect_many(source,selections)


def test_changed_font_or_source_group_lock_fails_saved_exact_replay(tmp_path):
    source,owner,group=fixture(tmp_path);p=op.inspect(source,owner_uuid=owner,group_uuid=group)
    b=pcbnew.LoadBoard(str(source));op.transform(b,p,delta_nm=(1,0))
    next(i for i in b.GetDrawings()if i.GetClass()=='PCB_TEXT').SetTextThickness(130000)
    child=tmp_path/'badfont.kicad_pcb';field._save_field_snapshot(b,child)
    with pytest.raises(ValueError):op.verify(source,child,p,delta_nm=(1,0))


def test_literal_fabricated_member_cannot_disappear_during_native_load(tmp_path):
    source,owner,group=fixture(tmp_path)
    text=source.read_text()
    text=text.replace('(members','(members "00000000-0000-4000-8000-000000000001"',1)
    source.write_text(text)
    with pytest.raises(ValueError):op.inspect(source,owner_uuid=owner,group_uuid=group)


def external_fixture(tmp_path, fault=None):
    import cec_assembly_envelope as assembly
    from shapely.ops import nearest_points
    source,owner,group=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()));g=next(iter(b.Groups()))
    text=next(i for i in g.GetItems()if i.GetClass()=='PCB_TEXT')
    text.SetTextPos(pcbnew.VECTOR2I_MM(10,6.5))
    p=pcbnew.SHAPE_POLY_SET();text.TransformShapeToPolygon(p,pcbnew.B_SilkS,0,1000,pcbnew.ERROR_OUTSIDE,False)
    glyph=assembly.polygon_from_native(p);court=assembly.polygon_from_native(fp.GetCourtyard(fp.GetLayer()))
    a,z=nearest_points(court,glyph.envelope.buffer(.2+.12/2+.002,join_style=2))
    line=pcbnew.PCB_SHAPE(b);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.B_SilkS)
    line.SetWidth(120000);line.SetStart(pcbnew.VECTOR2I(*(round(v*1e6)for v in a.coords[0])))
    line.SetEnd(pcbnew.VECTOR2I(*(round(v*1e6)for v in z.coords[0])));line.SetLocked(True);b.Add(line);g.AddItem(line)
    # This leader crosses a vertical gap. Moving horizontally slides along
    # an equally near boundary pair; it is NOT a detached/invalid leader.
    if fault=='moved':line.Move(pcbnew.VECTOR2I(0,1))
    elif fault=='tied':line.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='detached':line.SetStart(line.GetStart()+pcbnew.VECTOR2I(0,-1))
    elif fault=='extra':
        other=line.Duplicate();b.Add(other);g.AddItem(other)
    field._save_field_snapshot(b,source)
    return source,owner,group


def test_exact_external_source_leader_native_translation(tmp_path):
    source,owner,group=external_fixture(tmp_path);p=op.inspect(source,owner_uuid=owner,group_uuid=group)
    b=pcbnew.LoadBoard(str(source));op.transform(b,p,delta_nm=(100000,-250000))
    child=tmp_path/'translated.kicad_pcb';field._save_field_snapshot(b,child)
    assert op.verify(source,child,p,delta_nm=(100000,-250000))['ok']


@pytest.mark.parametrize('fault',['moved','detached','extra'])
def test_arbitrary_nearby_or_extra_leader_is_not_source_authority(tmp_path,fault):
    source,owner,group=external_fixture(tmp_path,fault)
    with pytest.raises(ValueError):op.inspect(source,owner_uuid=owner,group_uuid=group)


def test_exact_alternative_nearest_pair_is_valid_but_does_not_refresh_an_old_source_proof(tmp_path):
    source,owner,group=external_fixture(tmp_path)
    old=op.inspect(source,owner_uuid=owner,group_uuid=group)
    board=pcbnew.LoadBoard(str(source));g=next(iter(board.Groups()))
    lines=[i for i in g.GetItems()if i.GetClass()=='PCB_SHAPE']
    # The unique line outside the four courtyard edges is the external leader.
    leader=min(lines,key=lambda i:i.GetLength())
    leader.Move(pcbnew.VECTOR2I(1,0));field._save_field_snapshot(board,source)
    fresh=op.inspect(source,owner_uuid=owner,group_uuid=group)
    assert fresh['source_sha256']!=old['source_sha256']and not fresh['pose_admitted']
    with pytest.raises(ValueError):op.transform(board,old,delta_nm=(1,0))


def fab_body_fixture(tmp_path, *, back=False, source_turn=0, external=False):
    """Use the actual annotation producer's native Fab-body projection."""
    import cec_dense_reference_mapping as producer
    import cec_assembly_envelope as assembly
    from shapely.ops import nearest_points
    source,owner,gid=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    group=next(iter(board.Groups()))
    body=pcbnew.PCB_SHAPE(fp);body.SetShape(pcbnew.SHAPE_T_RECT)
    body.SetLayer(pcbnew.F_Fab);body.SetStart(pcbnew.VECTOR2I_MM(8,9))
    body.SetEnd(pcbnew.VECTOR2I_MM(12,11));body.SetWidth(100000);fp.Add(body)
    if back:fp.Flip(fp.GetPosition(),False)
    fp.SetOrientationDegrees(source_turn)
    for item in list(board.GetDrawings()):group.RemoveItem(item);board.Remove(item)
    face=pcbnew.F_SilkS if back else pcbnew.B_SilkS
    projected=producer.guide_body(fp,True)
    for line in producer.make_outline(board,projected,face,.12):
        board.Add(line);group.AddItem(line)
    text=producer.make_text(board,'X7',(10,10),face,.8,.12,0)
    board.Add(text);group.AddItem(text)
    if external:
        text.SetTextPos(pcbnew.VECTOR2I(round((projected.bounds[2]+2)*1e6),10000000))
        poly=pcbnew.SHAPE_POLY_SET();text.TransformShapeToPolygon(poly,face,0,1000,pcbnew.ERROR_OUTSIDE,False)
        glyph=assembly.polygon_from_native(poly)
        a,z=nearest_points(projected,glyph.envelope.buffer(.262,join_style=2))
        leader=pcbnew.PCB_SHAPE(board);leader.SetShape(pcbnew.SHAPE_T_SEGMENT)
        leader.SetLayer(face);leader.SetWidth(120000)
        leader.SetStart(pcbnew.VECTOR2I(*(round(v*1e6)for v in a.coords[0])))
        leader.SetEnd(pcbnew.VECTOR2I(*(round(v*1e6)for v in z.coords[0])))
        board.Add(leader);group.AddItem(leader)
    group.SetLocked(True);fp.SetLocked(False)
    field._save_field_snapshot(board,source)
    return source,owner,gid


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('source_turn',[0,90,180,270])
@pytest.mark.parametrize('turn',[0,1,2,3])
@pytest.mark.parametrize('external',[False,True])
def test_exact_source_fab_body_map_cardinal_replay(tmp_path,back,source_turn,turn,external):
    from test_source_reference_group_cardinal import literal_child
    source,owner,gid=fab_body_fixture(tmp_path,back=back,source_turn=source_turn,external=external)
    original=source.read_bytes()
    # Legacy print recognition must not borrow transport-only recognition.
    with pytest.raises(ValueError):op.inspect(source,owner_uuid=owner,group_uuid=gid)
    proof=op.inspect_native_fab_body(source,owner_uuid=owner,group_uuid=gid)
    assert proof['outline_geometry']=='exact_source_fab_body_not_manufacturing_courtyard'
    assert proof['manufacturing_courtyard_unchanged']and not proof['closed_assembly_body_authority']
    board=pcbnew.LoadBoard(str(source));delta=(123457,-234569)
    court_before=next(iter(board.GetFootprints())).GetCourtyard(next(iter(board.GetFootprints())).GetLayer()).Area()
    result=op.transform_cardinal(board,proof,quarter_turns=turn,delta_nm=delta)
    child=literal_child(source,proof,tmp_path/'child.kicad_pcb',turn,delta)
    assert op.verify_cardinal(source,child,proof,quarter_turns=turn,delta_nm=delta)['ok']
    assert op._cardinal_identity(board)==op._cardinal_identity(pcbnew.LoadBoard(str(child)))
    fp=next(iter(board.GetFootprints()))
    assert fp.GetCourtyard(fp.GetLayer()).Area()==court_before
    assert not result['pose_admitted']and not result['current_authority']and not result['release_authority']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['not_exact','partial','duplicate','extra_fab_mark',
    'filled_fab','wrong_fab_face','outside_court','noncardinal','unlocked_ink'])
def test_source_fab_projection_is_not_arbitrary_miniature_or_body_permission(tmp_path,fault):
    source,owner,gid=fab_body_fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()));group=next(iter(board.Groups()))
    lines=[item for item in group.GetItems()if item.GetClass()=='PCB_SHAPE']
    body=next(item for item in fp.GraphicalItems()if item.GetLayer()==pcbnew.F_Fab)
    if fault=='not_exact':
        for line in lines:line.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='partial':group.RemoveItem(lines[0]);board.Remove(lines[0])
    elif fault=='duplicate':
        other=lines[0].Duplicate();board.Add(other);group.AddItem(other)
    elif fault=='extra_fab_mark':
        mark=pcbnew.PCB_SHAPE(fp);mark.SetShape(pcbnew.SHAPE_T_SEGMENT);mark.SetLayer(pcbnew.F_Fab)
        mark.SetStart(pcbnew.VECTOR2I_MM(8,9));mark.SetEnd(pcbnew.VECTOR2I_MM(8.2,9.2));fp.Add(mark)
    elif fault=='filled_fab':body.SetFilled(True)
    elif fault=='wrong_fab_face':body.SetLayer(pcbnew.B_Fab)
    elif fault=='outside_court':body.SetStart(pcbnew.VECTOR2I_MM(6,9))
    elif fault=='noncardinal':fp.SetOrientationDegrees(45)
    else:
        # A locked parent still makes an individually unlocked item native-
        # locked. Remove that inherited lock in the negative fixture too.
        group.SetLocked(False);lines[0].SetLocked(False)
        assert not lines[0].IsLocked()
    field._save_field_snapshot(board,source)
    with pytest.raises(ValueError):op.inspect_native_fab_body(source,owner_uuid=owner,group_uuid=gid)


def test_source_fab_map_translation_keeps_original_literal_body_and_court(tmp_path):
    source,owner,gid=fab_body_fixture(tmp_path,external=True)
    proof=op.inspect_native_fab_body(source,owner_uuid=owner,group_uuid=gid)
    board=pcbnew.LoadBoard(str(source));op.transform(board,proof,delta_nm=(100000,-200000))
    child=tmp_path/'translated.kicad_pcb';field._save_field_snapshot(board,child)
    assert op.verify(source,child,proof,delta_nm=(100000,-200000))['ok']
