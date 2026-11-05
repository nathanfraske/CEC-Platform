"""CURRENT native chart association, independent from unrelated board history."""
import shutil
from pathlib import Path
import pcbnew,pytest
import cec_force_current as force
import cec_existing_reference_chart as charts
import cec_nonpolar_print_context as printing
import cec_field_coupling as field
from test_received_chart_print_context import case


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',[0,90,180,270])
def test_actual_chart_is_rebuilt_on_current_Source_and_saved_print_replays(tmp_path,monkeypatch,back,turn):
    old,source,oldq,qp,decl,options=case(tmp_path,monkeypatch,back=back,turn=turn)
    native=pcbnew.LoadBoard(str(source));group=next(iter(native.Groups()));gid=force._uid(group)
    before=source.read_bytes();proofs=charts.inspect_many(source,[gid]);assert len(proofs)==1
    p=next(iter(proofs.values()));assert p['complete_current_native_ink_reconstructed']
    assert all(p[key]is False for key in('pose_authority','current_authority','copper_admission','closed_assembly_body_authority','release_authority'))
    with pytest.raises(ValueError):printing.plan(source,**options)
    # The old producer files are deliberately unavailable; no cached success,
    # previous proposal, old Source hash or UUID derivation supplies authority.
    old.rename(old.with_suffix('.unavailable'));qp.rename(qp.with_suffix('.unavailable'))
    q=printing.plan(source,**options,source_chart_group_uuids=[gid])
    assert q['source_chart_group_uuids']==[gid]
    artifact=printing.construct_private(source,q,tmp_path/'current-chart-print')
    received=printing.receive(source,artifact['candidate'],q)
    assert received['ok']and received['complete'],received
    assert source.read_bytes()==before


def test_unrelated_source_motion_copper_and_ids_never_need_ancestor_relabelling(tmp_path,monkeypatch):
    old,source,q,qp,decl,options=case(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));gid=force._uid(next(iter(b.Groups())))
    unrelated=pcbnew.FOOTPRINT(b);unrelated.SetReference('other_owner');b.Add(unrelated)
    unrelated.SetPosition(pcbnew.VECTOR2I_MM(48,32))
    track=pcbnew.PCB_TRACK(b);track.SetStart(pcbnew.VECTOR2I_MM(44,30));track.SetEnd(pcbnew.VECTOR2I_MM(45,30))
    track.SetWidth(200000);b.Add(track)
    field._save_field_snapshot(b,source)
    proof=next(iter(charts.inspect_many(source,[gid]).values()))
    assert proof['source_sha256']==force._hash(source)
    assert proof['unrelated_Source_material_not_authorized_by_reference_association']
    assert not proof['copper_admission']and not proof['pose_authority']


@pytest.mark.parametrize('fault',['title','mirror','leader','owner_move','owner_ref','owner_removed','owner_lock',
    'owner_visible','group_unlock','nested','unknown_item','duplicate_text','missing_line','font','text_angle','duplicate_scope','unknown_scope'])
def test_source_geometry_membership_or_readability_changes_refuse(tmp_path,monkeypatch,fault):
    _,source,q,qp,decl,options=case(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));g=next(iter(b.Groups()));gid=force._uid(g)
    fp=next(i for i in g.GetItems()if i.GetClass()=='FOOTPRINT')
    text=next(i for i in g.GetItems()if i.GetClass()=='PCB_TEXT'and i.GetText()==fp.GetReference())
    if fault=='title':next(i for i in g.GetItems()if i.GetClass()=='PCB_TEXT'and i.GetText()=='REF MAP').SetText('wrong')
    elif fault=='mirror':text.SetMirrored(not text.IsMirrored())
    elif fault=='leader':next(i for i in g.GetItems()if i.GetClass()=='PCB_SHAPE').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='owner_move':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='owner_ref':fp.SetReference('other')
    elif fault=='owner_removed':g.RemoveItem(fp)
    elif fault=='owner_lock':fp.SetLocked(True)
    elif fault=='owner_visible':fp.Reference().SetVisible(True)
    elif fault=='group_unlock':g.SetLocked(False)
    elif fault=='nested':outer=pcbnew.PCB_GROUP(b);b.Add(outer);outer.AddItem(g)
    elif fault=='unknown_item':
        t=pcbnew.PCB_TRACK(b);t.SetWidth(200000);t.SetEnd(pcbnew.VECTOR2I_MM(1,1));b.Add(t);g.AddItem(t)
    elif fault=='duplicate_text':
        at=text.GetPosition();other=charts.producer.make_text(b,text.GetText(),(at.x/1e6,at.y/1e6),
            text.GetLayer(),text.GetTextHeight()/1e6,text.GetTextThickness()/1e6,text.GetTextAngle().AsDegrees())
        other.SetLocked(True);b.Add(other);g.AddItem(other)
    elif fault=='missing_line':g.RemoveItem(next(i for i in g.GetItems()if i.GetClass()=='PCB_SHAPE'))
    elif fault=='font':text.SetTextSize(pcbnew.VECTOR2I_MM(.1,.1))
    elif fault=='text_angle':text.SetTextAngle(pcbnew.EDA_ANGLE(45,pcbnew.DEGREES_T))
    field._save_field_snapshot(b,source)
    ids=[gid,gid]if fault=='duplicate_scope'else['missing']if fault=='unknown_scope'else[gid]
    with pytest.raises(ValueError):charts.inspect_many(source,ids)


@pytest.mark.parametrize('fault',['pad','fab'])
def test_chart_association_never_waives_independent_original_template_identity(tmp_path,monkeypatch,fault):
    _,source,q,qp,decl,options=case(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));g=next(iter(b.Groups()));gid=force._uid(g);fp=next(i for i in g.GetItems()if i.GetClass()=='FOOTPRINT')
    if fault=='pad':next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0))
    else:next(i for i in fp.GraphicalItems()if i.GetLayer()==pcbnew.F_Fab).Move(pcbnew.VECTOR2I(1,0))
    field._save_field_snapshot(b,source)
    assert charts.inspect_many(source,[gid])  # Association is not body authority.
    with pytest.raises(ValueError):printing.plan(source,**options,source_chart_group_uuids=[gid])


@pytest.mark.parametrize('back',[False,True])
def test_multi_owner_chart_requires_the_entire_shared_mapping(tmp_path,monkeypatch,back):
    import uuid
    _,source,q,qp,decl,options=case(tmp_path,monkeypatch,back=back)
    b=pcbnew.LoadBoard(str(source));old=next(iter(b.Groups()))
    first=next(i for i in old.GetItems()if i.GetClass()=='FOOTPRINT')
    for item in list(old.GetItems()):
        old.RemoveItem(item)
        if item.GetClass()!='FOOTPRINT':b.Remove(item)
    b.Remove(old)
    second=pcbnew.FOOTPRINT(first);second.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid4())))
    second.SetReference('Y7');second.Move(pcbnew.VECTOR2I_MM(4,2));b.Add(second)
    group=pcbnew.PCB_GROUP(b);group.SetName(charts.producer.GROUP);b.Add(group)
    models=[(f,charts.producer.court(f))for f in(first,second)]
    face=pcbnew.F_SilkS if back else pcbnew.B_SilkS;floors=charts.producer.floors(b,source)
    items,_,records=charts.producer.shapes(b,models,face,floors,positions=(12.,0.),scale=3.)
    decoration,_,_=charts.producer.chart_decoration(b,records,models,face,floors)
    for item in items+decoration:item.SetLocked(True);b.Add(item);group.AddItem(item)
    for f in(first,second):f.Reference().SetVisible(False);f.SetLocked(False);group.AddItem(f)
    group.SetLocked(True)
    for f in(first,second):f.SetLocked(False)
    field._save_field_snapshot(b,source)
    proofs=charts.inspect_many(source,[force._uid(group)])
    assert set(proofs)=={force._uid(first),force._uid(second)}
    assert len({p['chart_geometry_sha256']for p in proofs.values()})==1
    native=pcbnew.LoadBoard(str(source));g=next(iter(native.Groups()))
    g.RemoveItem(next(i for i in g.GetItems()if i.GetClass()=='FOOTPRINT'))
    field._save_field_snapshot(native,source)
    with pytest.raises(ValueError):charts.inspect_many(source,[force._uid(group)])
