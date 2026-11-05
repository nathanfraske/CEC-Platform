"""Exact existing courtyard representation repair, without geometric forgiveness."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pcbnew
import pytest
import cec_equivalent_courtyard_serialization as op


@pytest.fixture
def source_factory(tmp_path,monkeypatch):
    original=op.ROOT/'lib/vendor/Package_DFN_QFN.pretty/RUX0012A.kicad_mod'
    root=tmp_path/'project';vendor=root/'lib/vendor/Package.pretty';vendor.mkdir(parents=True)
    template=vendor/'Renamed.kicad_mod';template.write_text(original.read_text().replace('"RUX0012A"','"Renamed"',1))
    table=root/'fp-lib-table';table.write_text('(fp_lib_table (version 7) (lib (name "renamed") (type "KiCad") (uri "'+str(vendor)+'") (options "") (descr "")))')
    monkeypatch.setattr(op,'ROOT',root)
    monkeypatch.setattr(op.synth.Config,'load',lambda hint:SimpleNamespace(dir=root))
    def make(turn=0,back=False,asymmetric=False):
        folder=root/('source-'+str(turn)+'-'+str(back));folder.mkdir()
        source=folder/'board.kicad_pcb';b=pcbnew.BOARD();b.SetCopperLayerCount(6)
        f=pcbnew.FootprintLoad(str(vendor),'Renamed');b.Add(f)
        f.SetFPID(pcbnew.LIB_ID('renamed','Renamed'));f.SetReference('RENAMED_OWNER');f.SetValue('literal value')
        rect=next(g for g in f.GraphicalItems()if int(g.GetLayer())in op.court.COURTS)
        if asymmetric:
            rect.SetEnd(pcbnew.VECTOR2I(2000000,1900000))
            # Publish the independently expected altered synthetic vendor,
            # not a template back-copied from a candidate.
            pcbnew.FootprintSave(str(vendor),f)
            # FootprintSave uses the selected item identity.
        a,z=tuple(rect.GetStart()),tuple(rect.GetEnd());width=rect.GetWidth();f.Remove(rect)
        points=[a,(a[0],z[1]),z,(z[0],a[1])]
        for start,end in zip(points,points[1:]+points[:1]):
            g=pcbnew.PCB_SHAPE(f);g.SetShape(pcbnew.SHAPE_T_SEGMENT);g.SetLayer(pcbnew.F_CrtYd)
            g.SetStart(pcbnew.VECTOR2I(*start));g.SetEnd(pcbnew.VECTOR2I(*end));g.SetWidth(width);f.Add(g)
        f.SetOrientationDegrees(turn);f.SetPosition(pcbnew.VECTOR2I_MM(30,30))
        if back:f.Flip(f.GetPosition(),False)
        ink=pcbnew.PCB_TEXT(b);ink.SetText('functional root note');ink.SetPosition(pcbnew.VECTOR2I_MM(10,10));b.Add(ink)
        op.field._save_field_snapshot(b,source)
        source.with_suffix('.kicad_dru').write_text('(version 1)\n')
        source.with_suffix('.kicad_pro').write_text('{"opaque":true}\n')
        op.literal.write_raw(source,op.literal.raw_text(source)+'\n; opaque source comment\n')
        return source,op.force._uid(f),table,template
    return make


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_cardinal_faces_literal_and_second_native_replay(source_factory,tmp_path,turn,back):
    source,uid,table,_=source_factory(turn,back)
    before=source.read_bytes();q=op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)
    child=tmp_path/'child'/'board.kicad_pcb';assert op.write_private(source,child,q)==child
    proof=op.receive(source,child,q);assert proof['ok']and proof['complete'],proof
    assert proof['whole_native_second_save_exact']and proof['all_material_and_functional_ink_unchanged']
    assert not proof['physical_or_electrical_qualification']and not proof['release_authority']
    assert source.read_bytes()==before and '; opaque source comment' in child.read_text()
    b=pcbnew.LoadBoard(str(child));f=next(iter(b.GetFootprints()));assert len(op._courts(f))==1
    assert op._courts(f)[0].GetShape()==pcbnew.SHAPE_T_RECT


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_persisted_json_proposal_reconstructs_and_receives_independently(source_factory,tmp_path,turn,back):
    source,uid,table,_=source_factory(turn,back)
    proposal=op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)
    saved=tmp_path/'proposal.json';saved.write_text(json.dumps(proposal,sort_keys=True,allow_nan=False))
    q=json.loads(saved.read_text())
    assert q==proposal and q['epoch']['library']['references']==[['renamed','Renamed']]
    child=tmp_path/'child'/'board.kicad_pcb';op.write_private(source,child,q)
    proof=op.receive(source,child,json.loads(saved.read_text()))
    assert proof['ok']and proof['complete']and proof['all_material_and_functional_ink_unchanged'],proof


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_complete_saved_and_native_query_input_relation_keeps_debt_unknown(source_factory,tmp_path,turn,back):
    source,uid,table,_=source_factory(turn,back);before=source.read_bytes()
    q=json.loads(json.dumps(op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)))
    child=tmp_path/'child'/'board.kicad_pcb';op.write_private(source,child,q)
    proof=op.query_input_identity(source,child,q)
    assert all(proof.get(k)is True for k in('ok','complete','comparison_complete','same_material')),proof
    assert proof['fresh_exact_source_scope_reconstructed']and proof['actual_native_courtyard_geometry_equal']
    assert proof['independent_equivalent_courtyard_receiving_required']
    assert proof['mutation_authority']is proof['full_kelvin_qualification']is proof['release_authority']is False
    assert proof['inherited_electrical_debt']=='unchanged_not_evaluated'
    assert proof['unchanged_saved_ast_sha256']and proof['unchanged_native_ast_sha256']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['pose','pad','ink','court','metadata','rules'])
def test_query_relation_cannot_erase_unowned_or_unequal_court_changes(source_factory,tmp_path,fault):
    source,uid,table,_=source_factory();q=op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)
    child=tmp_path/'child'/'board.kicad_pcb';op.write_private(source,child,q)
    if fault=='metadata':op.literal.write_raw(child,op.literal.raw_text(child)+'\n; unowned new comment\n')
    elif fault=='rules':child.with_suffix('.kicad_dru').write_text('(version 2)')
    else:
        b=pcbnew.LoadBoard(str(child));f=next(iter(b.GetFootprints()))
        if fault=='pose':f.Move(pcbnew.VECTOR2I(1,0))
        elif fault=='pad':next(iter(f.Pads())).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='ink':next(iter(b.GetDrawings())).SetText('changed functional mark')
        else:op._courts(f)[0].Move(pcbnew.VECTOR2I(1,0))
        op.field._save_field_snapshot(b,child)
    proof=op.query_input_identity(source,child,q)
    assert not proof['ok']and proof['errors']and not proof['full_kelvin_qualification']


def test_query_relation_owns_fresh_receiving_and_independent_native_trees(source_factory,tmp_path,monkeypatch):
    source,uid,table,_=source_factory();q=op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)
    child=tmp_path/'child'/'board.kicad_pcb';op.write_private(source,child,q);original=op.field._save_field_snapshot
    def altered_native(board,path,*args,**kw):
        if 'cec-equivalent-court-query-'in str(path)and Path(path).name=='1.kicad_pcb':
            next(iter(board.GetFootprints())).SetValue('corrupted native observation')
        return original(board,path,*args,**kw)
    monkeypatch.setattr(op.field,'_save_field_snapshot',altered_native)
    proof=op.query_input_identity(source,child,q)
    assert not proof['ok']and any('native_query_input_changed'in e for e in proof['errors']),proof
    monkeypatch.setattr(op.field,'_save_field_snapshot',original)
    def refused_scope(*a,**k):raise ValueError('independent Source reconstruction refused')
    monkeypatch.setattr(op,'_fresh',refused_scope)
    assert not op.query_input_identity(source,child,q)['ok']


@pytest.mark.parametrize('fault',['gap','width','mixed_width','wrong_face','mixed_lock','group','rotation','extra_court','pad','model','functional_ink'])
def test_source_or_template_geometry_not_forgiven(source_factory,fault):
    source,uid,table,template=source_factory();b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()));lines=op._courts(fp)
    if fault=='gap':lines[0].SetStart(lines[0].GetStart()+pcbnew.VECTOR2I(1,0))
    elif fault=='width':
        for g in lines:g.SetWidth(g.GetWidth()+1)
    elif fault=='mixed_width':lines[0].SetWidth(lines[0].GetWidth()+1)
    elif fault=='wrong_face':lines[0].SetLayer(pcbnew.B_CrtYd)
    elif fault=='mixed_lock':lines[0].SetLocked(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.SetName('opaque group');g.AddItem(lines[0])
    elif fault=='rotation':fp.SetOrientationDegrees(45)
    elif fault=='extra_court':
        g=pcbnew.PCB_SHAPE(lines[0]);fp.Add(g)
    elif fault=='pad':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I(1050001,400000))
    elif fault=='model':
        m=pcbnew.FP_3DMODEL();m.m_Filename='not-the-vendor.step';fp.Models().push_back(m)
    else:
        g=pcbnew.PCB_TEXT(fp);g.SetText('functional unknown');g.SetLayer(pcbnew.F_SilkS);fp.Add(g)
    op.field._save_field_snapshot(b,source)
    with pytest.raises((ValueError,RuntimeError)):op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)


@pytest.mark.parametrize('fault',['pad','pose','root_ink','metadata','rules','extra_fp','court_1nm','new_ink'])
def test_saved_receiver_entire_unowned_transaction_exact(source_factory,tmp_path,fault):
    source,uid,table,_=source_factory();q=op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)
    child=tmp_path/'child'/'board.kicad_pcb';op.write_private(source,child,q)
    if fault=='rules':child.with_suffix('.kicad_dru').write_text('(version 2)');return_assert=op.receive(source,child,q);assert not return_assert['ok'];return
    if fault=='metadata':op.literal.write_raw(child,op.literal.raw_text(child).replace('opaque source comment','altered comment'))
    else:
        b=pcbnew.LoadBoard(str(child));fp=next(iter(b.GetFootprints()))
        if fault=='pad':next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
        elif fault=='root_ink':next(iter(b.GetDrawings())).SetText('renamed')
        elif fault=='extra_fp':b.Add(pcbnew.FOOTPRINT(b))
        elif fault=='court_1nm':op._courts(fp)[0].Move(pcbnew.VECTOR2I(1,0))
        else:
            g=pcbnew.PCB_TEXT(fp);g.SetText('new unauthorized ink');fp.Add(g)
        op.field._save_field_snapshot(b,child)
    proof=op.receive(source,child,q);assert not proof['ok']and proof['errors']


@pytest.mark.parametrize('fault',['source','vendor','table','proposal','code'])
def test_stale_source_vendor_context_and_proposal(source_factory,tmp_path,monkeypatch,fault):
    source,uid,table,template=source_factory();q=op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)
    child=tmp_path/'child'/'board.kicad_pcb';op.write_private(source,child,q)
    if fault=='source':op.literal.write_raw(source,op.literal.raw_text(source)+'\n')
    elif fault=='vendor':template.write_text(template.read_text()+'\n')
    elif fault=='table':table.write_text(table.read_text()+'\n')
    elif fault=='proposal':q['records'][0]['rectangle_literal']=q['records'][0]['rectangle_literal'].replace('0.05','0.051')
    else:monkeypatch.setattr(op.force,'_code_identity',lambda:{'forged':True})
    assert not op.receive(source,child,q)['ok']


def test_native_cache_and_deadline_remain_independent(source_factory,monkeypatch):
    source,uid,table,_=source_factory();old=op._cache;calls=[]
    def cache(fp,deadline):
        calls.append(fp);return old(fp,deadline)if len(calls)==1 else 'not-the-same-native-court'
    monkeypatch.setattr(op,'_cache',cache)
    with pytest.raises(ValueError,match='cached'):op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)
    monkeypatch.setattr(op,'_cache',old)
    with pytest.raises(ValueError,match='deadline'):op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table,timeout_s=1e-9)


def test_invalid_scope_and_nonproject_table(source_factory,tmp_path):
    source,uid,table,_=source_factory()
    for ids in [[],[uid,uid],['not-an-owner']]:
        with pytest.raises(ValueError):op.plan(source,board_hint='renamed',footprint_uuids=ids,library_table=table)
    other=tmp_path/'other-table';other.write_bytes(table.read_bytes())
    with pytest.raises(ValueError,match='actual_project'):op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=other)


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_asymmetric_independent_rectangle_uses_native_flip_not_layer_rename(source_factory,tmp_path,turn,back):
    source,uid,table,_=source_factory(turn,back,asymmetric=True)
    q=op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)
    child=tmp_path/'child'/'board.kicad_pcb';op.write_private(source,child,q)
    assert op.receive(source,child,q)['complete']


@pytest.mark.parametrize('where',['source_unknown','source_dash','vendor_unknown','vendor_fill'])
def test_unsupported_courtyard_attributes_are_not_discarded(source_factory,where):
    source,uid,table,vendor=source_factory()
    p=source if where.startswith('source')else vendor
    text=op.literal.raw_text(p)
    if where=='source_dash':text=text.replace('(type default)','(type dash)')
    elif where=='vendor_fill':text=text.replace('(fill no)','(fill yes)').replace('(fill none)','(fill solid)')
    else:
        target='fp_line'if where.startswith('source')else'fp_rect'
        if p==source:
            a,z=op.literal.inventory(text)[uid];part=text[a:z]
            x,y=next((x,y)for x,y in op.literal.children(part)if op.literal.kind(part[x:y])==target
                and 'CrtYd'in part[x:y]);part=part[:y-1]+' (opaque_future_rule yes)'+part[y-1:];text=text[:a]+part+text[z:]
        else:
            x,y=next((x,y)for x,y in op.literal.children(text)if op.literal.kind(text[x:y])==target and 'CrtYd'in text[x:y])
            text=text[:y-1]+' (opaque_future_rule yes)'+text[y-1:]
    op.literal.write_raw(p,text)
    with pytest.raises((ValueError,RuntimeError,OSError)):op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)


def test_all_saved_fill_metadata_and_short_receive_lease_are_exact(source_factory,tmp_path):
    source,uid,table,_=source_factory();b=pcbnew.LoadBoard(str(source))
    zone=pcbnew.ZONE(b);zone.SetLayer(pcbnew.In2_Cu);outline=zone.Outline();outline.NewOutline()
    for x,y in [(1,1),(2,1),(2,2),(1,2)]:outline.Append(x*1000000,y*1000000)
    b.Add(zone);zone.SetFilledPolysList(pcbnew.In2_Cu,outline.CloneDropTriangulation());zone.SetIsFilled(True)
    op.field._save_field_snapshot(b,source)
    q=op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)
    child=tmp_path/'child'/'board.kicad_pcb';op.write_private(source,child,q)
    assert not op.receive(source,child,q,timeout_s=1e-9)['ok']
    candidate=pcbnew.LoadBoard(str(child));next(iter(candidate.Zones())).UnFill();op.field._save_field_snapshot(candidate,child)
    assert not op.receive(source,child,q)['ok']


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('reading_angle',[0,90,180,270])
def test_only_cardinal_instance_fab_reading_angle_may_differ_from_vendor(source_factory,tmp_path,turn,back,reading_angle):
    source,uid,table,_=source_factory(turn,back)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    field=next(g for g in fp.GraphicalItems()if g.GetClass()=='PCB_TEXT'and g.GetText()=='${REFERENCE}')
    field.SetTextAngle(pcbnew.EDA_ANGLE(reading_angle,pcbnew.DEGREES_T))
    op.field._save_field_snapshot(board,source);before=source.read_bytes()
    q=json.loads(json.dumps(op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)))
    child=tmp_path/'child'/'board.kicad_pcb';op.write_private(source,child,q)
    assert op.receive(source,child,q)['ok']
    observed=pcbnew.LoadBoard(str(child))
    after=next(g for f in observed.GetFootprints()for g in f.GraphicalItems()
        if g.GetClass()=='PCB_TEXT'and g.GetText()=='${REFERENCE}')
    assert after.GetTextAngle().AsDegrees()==reading_angle
    assert source.read_bytes()==before
    # Whole-tree receiving still forbids an actual annotation-angle edit.
    board=pcbnew.LoadBoard(str(child));fp=next(iter(board.GetFootprints()))
    field=next(g for g in fp.GraphicalItems()if g.GetClass()=='PCB_TEXT'and g.GetText()=='${REFERENCE}')
    field.SetTextAngle(pcbnew.EDA_ANGLE((reading_angle+90)%360,pcbnew.DEGREES_T))
    op.field._save_field_snapshot(board,child)
    assert not op.receive(source,child,q)['ok']


@pytest.mark.parametrize('fault',['position','size','stroke','mirror','upright','layer','text','bold','italic','duplicate','noncardinal'])
def test_instance_reading_angle_projection_does_not_hide_other_fab_changes(source_factory,fault):
    source,uid,table,_=source_factory();board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    field=next(g for g in fp.GraphicalItems()if g.GetClass()=='PCB_TEXT'and g.GetText()=='${REFERENCE}')
    field.SetTextAngle(pcbnew.EDA_ANGLE(270,pcbnew.DEGREES_T))
    if fault=='position':field.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='size':field.SetTextSize(pcbnew.VECTOR2I(1000001,1000000))
    elif fault=='stroke':field.SetTextThickness(field.GetTextThickness()+1)
    elif fault=='mirror':field.SetMirrored(not field.IsMirrored())
    elif fault=='upright':field.SetKeepUpright(not field.IsKeepUpright())
    elif fault=='layer':field.SetLayer(pcbnew.B_Fab)
    elif fault=='text':field.SetText('${VALUE}')
    elif fault=='bold':field.SetBold(not field.IsBold())
    elif fault=='italic':field.SetItalic(not field.IsItalic())
    elif fault=='duplicate':fp.Add(pcbnew.PCB_TEXT(field))
    else:field.SetTextAngle(pcbnew.EDA_ANGLE(45,pcbnew.DEGREES_T))
    op.field._save_field_snapshot(board,source)
    with pytest.raises((ValueError,RuntimeError)):
        op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)


def test_new_courtyard_uuid_is_native_canonical_before_any_followon_stage(source_factory,tmp_path):
    source,uid,table,_=source_factory()
    q=op.plan(source,board_hint='renamed',footprint_uuids=[uid],library_table=table)
    row=q['records'][0]
    assert '(uuid '+json.dumps(row['rectangle_uuid'])+')'in row['rectangle_literal']
    child=tmp_path/'child'/'board.kicad_pcb';op.write_private(source,child,q)
    native=tmp_path/'followon-native.kicad_pcb'
    board=pcbnew.LoadBoard(str(child));op.field._save_field_snapshot(board,native)
    def footprint(path):
        text=op.literal.raw_text(path);a,z=op.literal.inventory(text)[uid]
        return op.syntax._parse(op.syntax._TOKEN.findall(text[a:z]))
    def rectangle(path):
        fp=footprint(path)
        return next(n for n in fp if isinstance(n,list)and n[:1]==['fp_rect']
            and any(isinstance(v,list)and v[:1]==['uuid']and v[1].strip('"')==row['rectangle_uuid']for v in n))
    assert op.syntax._freeze(rectangle(child))==op.syntax._freeze(rectangle(native))
    assert op.syntax._freeze(footprint(child))==op.syntax._freeze(footprint(native))
