import copy
from pathlib import Path
import wx
quiet=wx.LogNull()
import pcbnew
import cec_swig_guard
cec_swig_guard.pin()
import pytest
import cec_nonpolar_print_context as op
import cec_field_coupling as field
import cec_force_current as force


def fixture(tmp_path,monkeypatch,turn=0,back=False,selected_name='R_1206_3216Metric',legacy_fields=False):
    real=Path(__file__).resolve().parents[1];authority=tmp_path/'authority'
    namespace='Capacitor_SMD'if selected_name.startswith('C_')else'Resistor_SMD'
    other_name='C_0805_2012Metric'if namespace=='Capacitor_SMD'else'R_0805_2012Metric'
    library=authority/('lib/vendor/'+namespace+'.pretty');library.mkdir(parents=True)
    for name in(selected_name,other_name):
        text=(real/'lib/vendor'/(namespace+'.pretty')/(name+'.kicad_mod')).read_text()
        if legacy_fields:
            # Exact legacy field syntax, same original field text/effects;
            # no native reserialization that would modernize the fixture.
            text=text.replace('(property "Reference"','(fp_text reference',1).replace('(property "Value"','(fp_text value',1)
        (library/(name+'.kicad_mod')).write_text(text)
    monkeypatch.setattr(op.ink.nonpolar,'ROOT',authority)
    b=pcbnew.BOARD();b.SetCopperLayerCount(6);ids=[]
    for index,(name,angle,flipped)in enumerate(((selected_name,turn,back),(selected_name,(turn+90)%360,not back),(other_name,0,False))):
        f=pcbnew.FootprintLoad(str(library),name);b.Add(f);f.SetFPID(pcbnew.LIB_ID('cec-'+namespace,name));f.SetReference('UNRELATED'+str(index));f.SetValue('authored')
        if flipped:f.Flip(pcbnew.VECTOR2I(0,0),False)
        f.SetOrientationDegrees(angle);f.SetPosition(pcbnew.VECTOR2I_MM(10+index*10,20));f.Reference().SetVisible(True)
        if index<2:ids.append(force._uid(f))
    source=tmp_path/'source/board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source);source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    table=source.parent/'fp-lib-table';table.write_text('(fp_lib_table (version 7) (lib (name "cec-'+namespace+'") (type "KiCad") (uri "'+str(library)+'") (options "") (descr "source")))')
    return source,table,ids,library


def planned(source,table,ids):
    return op.plan(source,library_table=table,footprint_ids=['cec-Resistor_SMD:R_1206_3216Metric'],expected_instance_uuids=ids,board_hint='renamed')


def omit_source_body(source,uid,count=2):
    b=pcbnew.LoadBoard(str(source));f=next(f for f in b.GetFootprints()if force._uid(f)==uid)
    graphics=[g for g in f.GraphicalItems()if g.GetLayer()in(pcbnew.F_SilkS,pcbnew.B_SilkS)]
    op.ink.discard_footprint_children(b,f,graphics[:count])
    field._save_field_snapshot(b,source)


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('both',[False,True])
def test_complete_zero_line_or_mixed_source_replays_without_changing_zero_owner(tmp_path,monkeypatch,turn,back,both):
    source,table,ids,library=fixture(tmp_path,monkeypatch,turn,back)
    omit_source_body(source,ids[0])
    if both:omit_source_body(source,ids[1])
    before=source.read_text();inventory=op.raw.inventory(before)
    q=planned(source,table,ids);states={r['footprint_uuid']:r for r in q['records']}
    assert states[ids[0]]['source_optional_body_state']=='already_omitted_zero_lines'
    assert states[ids[0]]['graphic_uuids']==[]
    assert states[ids[1]]['source_optional_body_state']==('already_omitted_zero_lines'if both else'original_two_lines')
    a=op.construct_private(source,q,tmp_path/'private');r=op.receive(source,a['candidate'],q)
    assert r['ok']and r['complete'],r
    after=Path(a['candidate']).read_text();child_inventory=op.raw.inventory(after)
    for uid in(ids if both else ids[:1]):
        x,y=inventory[uid];cx,cy=child_inventory[uid];assert before[x:y]==after[cx:cy]
    assert source.read_text()==before


@pytest.mark.parametrize('fault',['partial_one','pad','court','fab','model','extra_marker','functional_text'])
def test_zero_state_cannot_hide_partial_physical_or_functional_changes(tmp_path,monkeypatch,fault):
    source,table,ids,library=fixture(tmp_path,monkeypatch)
    omit_source_body(source,ids[0],1 if fault=='partial_one'else 2)
    b=pcbnew.LoadBoard(str(source));f=next(f for f in b.GetFootprints()if force._uid(f)==ids[0])
    if fault=='pad':next(iter(f.Pads())).SetSize(pcbnew.VECTOR2I_MM(2,2))
    elif fault in('court','fab'):
        layer=pcbnew.F_CrtYd if fault=='court'else pcbnew.F_Fab
        next(g for g in f.GraphicalItems()if g.GetLayer()==layer).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='model':m=pcbnew.FP_3DMODEL();m.m_Filename='forged.step';f.Models().push_back(m)
    elif fault=='extra_marker':
        g=pcbnew.PCB_SHAPE(f);g.SetShape(pcbnew.SHAPE_T_SEGMENT);g.SetLayer(pcbnew.F_SilkS);g.SetStart(f.GetPosition());g.SetEnd(f.GetPosition()+pcbnew.VECTOR2I_MM(1,0));f.Add(g)
    elif fault=='functional_text':
        g=pcbnew.PCB_TEXT(f);g.SetLayer(pcbnew.F_SilkS);g.SetText('+');f.Add(g)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):planned(source,table,ids)


def test_forged_zero_state_plan_is_not_omission_authority(tmp_path,monkeypatch):
    source,table,ids,library=fixture(tmp_path,monkeypatch);q=planned(source,table,ids)
    q['records'][0]['source_optional_body_state']='already_omitted_zero_lines';q['records'][0]['graphic_uuids']=[]
    with pytest.raises(ValueError,match='stale_or_forged'):op.construct_private(source,q,tmp_path/'private')


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_all_same_fpid_instances_exact_original_print_context(tmp_path,monkeypatch,turn,back):
    source,table,ids,library=fixture(tmp_path,monkeypatch,turn,back);before={p:p.read_bytes()for p in(source,table,*library.glob('*'))}
    q=planned(source,table,ids);assert len(q['records'])==2
    a=op.construct_private(source,q,tmp_path/'private');r=op.receive(source,a['candidate'],q)
    assert r['ok']and r['complete'],r
    assert not r['admitted']and r['old_library_context']['references']==r['new_library_context']['references']
    assert all(p.read_bytes()==value for p,value in before.items())
    newlib=Path(a['new_library_context']['rows']['cec-Resistor_SMD']['path'])
    assert (newlib/'R_0805_2012Metric.kicad_mod').read_bytes()==(library/'R_0805_2012Metric.kicad_mod').read_bytes()
    child=pcbnew.LoadBoard(a['candidate']);selected=[f for f in child.GetFootprints()if force._uid(f)in ids]
    assert all(not[g for g in f.GraphicalItems()if g.GetLayer()in(pcbnew.F_SilkS,pcbnew.B_SilkS)]for f in selected)


@pytest.mark.parametrize('fault',['partial','unknown','pad','court','fab','model','unknown_marker','hidden','locked','group','dnp','missing_other_item','missing_template','wrong_table_alias'])
def test_source_physical_and_complete_context_fail_closed(tmp_path,monkeypatch,fault):
    source,table,ids,library=fixture(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source));f=next(f for f in b.GetFootprints()if force._uid(f)==ids[0])
    if fault=='partial':ids=ids[:1]
    elif fault=='unknown':ids=ids+[str(pcbnew.KIID())]
    elif fault=='pad':next(iter(f.Pads())).SetSize(pcbnew.VECTOR2I_MM(9,9))
    elif fault in('court','fab'):
        layer=pcbnew.F_CrtYd if fault=='court'else pcbnew.F_Fab;next(g for g in f.GraphicalItems()if g.GetLayer()==layer).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='model':
        model=pcbnew.FP_3DMODEL();model.m_Filename='unreviewed.step';f.Models().push_back(model)
    elif fault=='unknown_marker':
        g=pcbnew.PCB_SHAPE(f);g.SetShape(pcbnew.SHAPE_T_CIRCLE);g.SetLayer(pcbnew.F_SilkS);g.SetStart(pcbnew.VECTOR2I_MM(11,21));g.SetEnd(pcbnew.VECTOR2I_MM(11.2,21));f.Add(g)
    elif fault=='hidden':f.Reference().SetVisible(False)
    elif fault=='locked':f.SetLocked(True)
    elif fault=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(f)
    elif fault=='dnp':f.SetDNP(True)
    elif fault=='missing_other_item':(library/'R_0805_2012Metric.kicad_mod').unlink()
    elif fault=='missing_template':(library/'R_1206_3216Metric.kicad_mod').unlink()
    elif fault=='wrong_table_alias':table.write_text(table.read_text().replace('cec-Resistor_SMD','wrong'))
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):planned(source,table,ids)


@pytest.mark.parametrize('fault',['partial_child','court','model','fpid','other_alias_item','variant','missing_other','missing_variant','table','sidecar','new_file','nested_metadata','proposal','claimed_admission'])
def test_receiver_independently_replays_entire_source_and_context(tmp_path,monkeypatch,fault):
    source,table,ids,library=fixture(tmp_path,monkeypatch);q=planned(source,table,ids);a=op.construct_private(source,q,tmp_path/'private');child=Path(a['candidate'])
    newlib=Path(a['new_library_context']['rows']['cec-Resistor_SMD']['path'])
    if fault in('partial_child','court','model','fpid'):
        b=pcbnew.LoadBoard(str(child));f=next(f for f in b.GetFootprints()if force._uid(f)==ids[0])
        if fault=='partial_child':
            original=pcbnew.LoadBoard(str(source));old=next(fp for fp in original.GetFootprints()if force._uid(fp)==ids[0]);b.Remove(f);b.Add(pcbnew.FOOTPRINT(old))
        elif fault=='court':next(g for g in f.GraphicalItems()if g.GetLayer()==pcbnew.F_CrtYd).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='model':model=pcbnew.FP_3DMODEL();model.m_Filename='changed.step';f.Models().push_back(model)
        else:f.SetFPID(pcbnew.LIB_ID('changed','part'))
        field._save_field_snapshot(b,child)
    elif fault in('other_alias_item','variant'):
        p=newlib/(('R_0805_2012Metric'if fault=='other_alias_item'else'R_1206_3216Metric')+'.kicad_mod');p.write_text(p.read_text()+'\n# forged\n')
    elif fault in('missing_other','missing_variant'):
        (newlib/(('R_0805_2012Metric'if fault=='missing_other'else'R_1206_3216Metric')+'.kicad_mod')).unlink()
    elif fault=='table':p=child.parent/'fp-lib-table';p.write_text(p.read_text().replace('(version 7)','(version 8)'))
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n# changed\n')
    elif fault=='new_file':(child.parent/'unowned.txt').write_text('no')
    elif fault=='nested_metadata':
        folder=child.parent/'extra';folder.mkdir();(folder/'print-context.json').write_text('{}')
    elif fault=='claimed_admission':
        p=child.parent/'print-context.json';p.write_text(p.read_text().replace('"admitted": false','"admitted": true'))
    else:q=copy.deepcopy(q);q['records']=q['records'][:1]
    assert not op.receive(source,child,q)['ok']


@pytest.mark.parametrize('fault',['source','template','table','sidecar'])
def test_stale_original_authority_refuses_construction(tmp_path,monkeypatch,fault):
    source,table,ids,library=fixture(tmp_path,monkeypatch);q=planned(source,table,ids)
    p={'source':source,'template':library/'R_1206_3216Metric.kicad_mod','table':table,'sidecar':source.with_suffix('.kicad_dru')}[fault]
    p.write_text(p.read_text()+'\n# source evidence changed\n')
    with pytest.raises(ValueError):op.construct_private(source,q,tmp_path/'private')


def test_unmodeled_but_native_physical_root_setting_never_ignored(tmp_path,monkeypatch):
    source,table,ids,library=fixture(tmp_path,monkeypatch)
    text=source.read_text();a,b=op.raw.inventory(text)[ids[0]];part=text[a:b]
    assert '(duplicate_pad_numbers_are_jumpers no)'in part
    source.write_text(text[:a]+part.replace('(duplicate_pad_numbers_are_jumpers no)','(duplicate_pad_numbers_are_jumpers yes)',1)+text[b:])
    with pytest.raises(ValueError,match='additional_source_physical'):planned(source,table,ids)


def hidden_map_case(tmp_path,monkeypatch,fault=None):
    source,table,ids,library=fixture(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source));fp=next(f for f in b.GetFootprints()if force._uid(f)==ids[0])
    fp.SetReference('X0');fp.Reference().SetVisible(False);fp.BuildCourtyardCaches()
    group=pcbnew.PCB_GROUP(b);group.SetName(op.maps.PREFIX+'X0');b.Add(group);group.AddItem(fp)
    face=pcbnew.F_SilkS if fp.IsFlipped()else pcbnew.B_SilkS
    text=pcbnew.PCB_TEXT(b);text.SetText('X0');text.SetLayer(face);text.SetMirrored(face==pcbnew.B_SilkS)
    text.SetTextSize(pcbnew.VECTOR2I_MM(.8,.8));text.SetTextThickness(120000);text.SetPosition(fp.GetPosition())
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER);text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER);text.SetLocked(True);b.Add(text);group.AddItem(text)
    court=fp.GetCourtyard(fp.GetLayer());chain=court.COutline(0);points=[(chain.CPoint(i).x,chain.CPoint(i).y)for i in range(chain.PointCount())]
    for a,z in zip(points,points[1:]+points[:1]):
        g=pcbnew.PCB_SHAPE(b);g.SetLayer(face);g.SetShape(pcbnew.SHAPE_T_SEGMENT);g.SetStart(pcbnew.VECTOR2I(*a));g.SetEnd(pcbnew.VECTOR2I(*z));g.SetWidth(120000);g.SetLocked(True);b.Add(g);group.AddItem(g)
    group.SetLocked(True);fp.SetLocked(False)
    if fault=='wrong_text':text.SetText('OTHER')
    elif fault=='wrong_outline':g.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='unlocked_text':group.SetLocked(False);text.SetLocked(False)
    field._save_field_snapshot(b,source)
    return source,table,ids


@pytest.mark.parametrize('fault',[None,'wrong_text','wrong_outline','unlocked_text'])
def test_hidden_reference_requires_fresh_real_source_owned_readable_map(tmp_path,monkeypatch,fault):
    source,table,ids=hidden_map_case(tmp_path,monkeypatch,fault)
    if fault:
        with pytest.raises(ValueError):planned(source,table,ids)
    else:
        q=planned(source,table,ids);assert next(r for r in q['records']if r['footprint_uuid']==ids[0])['source_reference_map']
        a=op.construct_private(source,q,tmp_path/'private');r=op.receive(source,a['candidate'],q);assert r['ok'],r


def test_private_fresh_plan_map_frame_matches_independent_public_inspection(tmp_path,monkeypatch):
    source,table,ids=hidden_map_case(tmp_path,monkeypatch)
    native=pcbnew.LoadBoard(str(source));group=next(g for g in native.Groups()
        if any(force._uid(i)==ids[0]for i in g.GetItems()))
    expected=op.maps.inspect(source,owner_uuid=ids[0],group_uuid=force._uid(group))
    calls={'literal':0,'recognize':0};parse=op.maps.ast._nodes;recognize=op.maps._inspect_bound
    def literal(path):
        calls['literal']+=1
        return parse(path)
    def inspect(*args,**kwargs):
        calls['recognize']+=1
        assert kwargs.get('projection_geometry',op.maps.COURT_PROJECTION)==op.maps.COURT_PROJECTION
        return recognize(*args,**kwargs)
    def no_duplicate_context(*args,**kwargs):raise AssertionError('redundant_public_map_context')
    monkeypatch.setattr(op.maps,'inspect_many',no_duplicate_context)
    monkeypatch.setattr(op.maps.ast,'_nodes',literal)
    monkeypatch.setattr(op.maps,'_inspect_bound',inspect)
    first=planned(source,table,ids);first_counts=dict(calls)
    proof=next(r['source_reference_map']for r in first['records']if r['footprint_uuid']==ids[0])
    assert proof==expected and calls['recognize']==1 and calls['literal']>=1
    second=planned(source,table,ids)
    assert second==first and calls=={name:2*value for name,value in first_counts.items()}


@pytest.mark.parametrize('target',['source','family'])
def test_shared_print_map_frame_cannot_hide_midrecognition_changes(tmp_path,monkeypatch,target):
    source,table,ids=hidden_map_case(tmp_path,monkeypatch);recognize=op.maps._inspect_bound
    def changed(*args,**kwargs):
        result=recognize(*args,**kwargs)
        path=source if target=='source'else source.with_suffix('.kicad_dru')
        path.write_text(path.read_text()+'\n# epoch changed while recognizing map\n')
        return result
    monkeypatch.setattr(op.maps,'_inspect_bound',changed)
    with pytest.raises(ValueError,match='Source_or_lease_changed|context_code_or_lease_changed'):
        planned(source,table,ids)


@pytest.mark.parametrize('name',['source_board','source_nodes','source_maps','prepared_context'])
def test_public_print_plan_accepts_no_prepared_map_authority(tmp_path,monkeypatch,name):
    source,table,ids=hidden_map_case(tmp_path,monkeypatch)
    with pytest.raises(TypeError):
        op.plan(source,library_table=table,footprint_ids=['cec-Resistor_SMD:R_1206_3216Metric'],
            expected_instance_uuids=ids,board_hint='opaque',**{name:{'ok':True}})


@pytest.mark.parametrize('name',['C_0402_1005Metric','R_0402_1005Metric'])
@pytest.mark.parametrize('legacy',[False,True])
def test_actual_original_uuid_less_vendored_formats_preserve_every_field(tmp_path,monkeypatch,name,legacy):
    source,table,ids,library=fixture(tmp_path,monkeypatch,selected_name=name,legacy_fields=legacy)
    authority=library/(name+'.kicad_mod');original=authority.read_text()
    original_lines=op._template_lines(authority);assert len(original_lines)==2 and all(x.startswith('literal:')for x in original_lines)
    namespace='cec-Capacitor_SMD'if name.startswith('C_')else'cec-Resistor_SMD'
    q=op.plan(source,library_table=table,footprint_ids=[namespace+':'+name],expected_instance_uuids=ids,board_hint='actual-vendor-format')
    a=op.construct_private(source,q,tmp_path/'private');r=op.receive(source,a['candidate'],q);assert r['ok'],r
    target=Path(a['new_library_context']['rows'][namespace]['path'])/(name+'.kicad_mod')
    assert target.read_text()==op._omitted(original,original_lines)
    fields=[original[a:b]for a,b in op.raw.children(original)if op.ink._node(original[a:b])[0]in('property','fp_text')]
    assert all(field in target.read_text()for field in fields)


def test_legacy_user_silk_is_never_mistaken_for_reference_field(tmp_path,monkeypatch):
    source,table,ids,library=fixture(tmp_path,monkeypatch,selected_name='R_0402_1005Metric',legacy_fields=True)
    p=library/'R_0402_1005Metric.kicad_mod';p.write_text(p.read_text().replace('(fp_text reference','(fp_text user',1))
    with pytest.raises(ValueError,match='functional_or_unknown'):op._template_lines(p)


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_source_fab_reference_instance_angles_preserved_not_normalized(tmp_path,monkeypatch,turn,angle,back):
    source,table,ids,library=fixture(tmp_path,monkeypatch,turn,back,selected_name='R_0402_1005Metric')
    b=pcbnew.LoadBoard(str(source));fp=next(f for f in b.GetFootprints()if force._uid(f)==ids[0])
    text=next(g for g in fp.GraphicalItems()if g.GetClass()=='PCB_TEXT'and g.GetText()=='${REFERENCE}')
    text.SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T));field._save_field_snapshot(b,source)
    original=source.read_text();template_before=(library/'R_0402_1005Metric.kicad_mod').read_bytes()
    q=op.plan(source,library_table=table,footprint_ids=['cec-Resistor_SMD:R_0402_1005Metric'],expected_instance_uuids=ids,board_hint='source-fab-angle')
    a=op.construct_private(source,q,tmp_path/'private');r=op.receive(source,a['candidate'],q);assert r['ok'],r
    spans=op.raw.inventory(original);x,y=spans[ids[0]];part=original[x:y]
    node=next(part[a:b]for a,b in op.raw.children(part)if op.raw.kind(part[a:b])=='fp_text')
    assert node in Path(a['candidate']).read_text()
    assert (library/'R_0402_1005Metric.kicad_mod').read_bytes()==template_before
    variant=Path(a['new_library_context']['rows']['cec-Resistor_SMD']['path'])/'R_0402_1005Metric.kicad_mod'
    assert variant.read_text()==op._omitted(template_before.decode(),op._template_lines(library/'R_0402_1005Metric.kicad_mod'))


@pytest.mark.parametrize('fault',['position','font','stroke','text','missing','extra','ambiguous','mirror','noncardinal'])
def test_no_other_fab_attribute_becomes_instance_authority(tmp_path,monkeypatch,fault):
    source,table,ids,library=fixture(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source));fp=next(f for f in b.GetFootprints()if force._uid(f)==ids[0])
    text=next(g for g in fp.GraphicalItems()if g.GetClass()=='PCB_TEXT'and g.GetText()=='${REFERENCE}')
    if fault=='position':text.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='font':text.SetTextSize(pcbnew.VECTOR2I_MM(.9,.9))
    elif fault=='stroke':text.SetTextThickness(text.GetTextThickness()+1)
    elif fault=='text':text.SetText('FUNCTIONAL')
    elif fault=='missing':op.ink.discard_footprint_children(b,fp,[text])
    elif fault in('extra','ambiguous'):
        other=text.Duplicate();other.m_Uuid.Clone(pcbnew.KIID());fp.Add(other)
        if fault=='extra':other.SetText('FUNCTIONAL')
    elif fault=='mirror':text.SetMirrored(not text.IsMirrored())
    elif fault=='noncardinal':text.SetTextAngle(pcbnew.EDA_ANGLE(45,pcbnew.DEGREES_T))
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):planned(source,table,ids)


def test_local_inventory_and_original_defaults_rebuilt_once_per_fresh_plan(tmp_path,monkeypatch):
    source,table,ids,library=fixture(tmp_path,monkeypatch);calls={'inventory':0,'defaults':0}
    inventory=op.raw.inventory;defaults=op._original_defaults
    def counted_inventory(text):calls['inventory']+=1;return inventory(text)
    def counted_defaults(*args):calls['defaults']+=1;return defaults(*args)
    monkeypatch.setattr(op.raw,'inventory',counted_inventory);monkeypatch.setattr(op,'_original_defaults',counted_defaults)
    first=planned(source,table,ids);assert calls=={'inventory':1,'defaults':1}
    second=planned(source,table,ids);assert second==first and calls=={'inventory':2,'defaults':2}
    source.write_text(source.read_text()+'\n')
    third=planned(source,table,ids);assert third['source_sha256']!=first['source_sha256']and calls=={'inventory':3,'defaults':3}
    template=library/'R_1206_3216Metric.kicad_mod';template.write_text(template.read_text()+'\n')
    fourth=planned(source,table,ids);assert fourth['derivatives'][0]['original_sha256']!=third['derivatives'][0]['original_sha256']
    assert calls=={'inventory':4,'defaults':4}


def test_defaults_are_per_fpid_not_per_owner_or_global(tmp_path,monkeypatch):
    source,table,ids,library=fixture(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source));all_ids=sorted(force._uid(f)for f in b.GetFootprints())
    calls=[];defaults=op._original_defaults
    def counted(path,*args):calls.append(path.name);return defaults(path,*args)
    monkeypatch.setattr(op,'_original_defaults',counted)
    q=op.plan(source,library_table=table,footprint_ids=['cec-Resistor_SMD:R_1206_3216Metric','cec-Resistor_SMD:R_0805_2012Metric'],expected_instance_uuids=all_ids,board_hint='two-source-fpids')
    assert len(q['records'])==3 and sorted(calls)==['R_0805_2012Metric.kicad_mod','R_1206_3216Metric.kicad_mod']


@pytest.mark.parametrize('target',['source','template','code','dependency'])
def test_midplan_changes_refuse_despite_private_immutable_indexes(tmp_path,monkeypatch,target):
    source,table,ids,library=fixture(tmp_path,monkeypatch);owner=op._owner;first=True
    original_code=force._code_identity;original_hash=force._hash;code_changed=False;dependency_changed=False
    def code():
        value=original_code()
        return {**value,'forged_midplan_epoch':'changed'}if code_changed else value
    def filehash(path,*args,**kwargs):
        if dependency_changed and Path(path).resolve()==Path(op.ink.frame.__file__).resolve():return 'f'*64
        return original_hash(path,*args,**kwargs)
    def mutate(*args):
        nonlocal first,code_changed,dependency_changed
        value=owner(*args)
        if first:
            first=False
            if target in('source','template'):
                path=source if target=='source'else library/'R_1206_3216Metric.kicad_mod';path.write_text(path.read_text()+'\n')
            elif target=='code':code_changed=True
            else:dependency_changed=True
        return value
    monkeypatch.setattr(force,'_code_identity',code);monkeypatch.setattr(force,'_hash',filehash);monkeypatch.setattr(op,'_owner',mutate)
    with pytest.raises(ValueError,match='context_code_or_lease_changed'):planned(source,table,ids)


def test_no_public_or_cross_call_authority_cache_parameter(tmp_path,monkeypatch):
    source,table,ids,library=fixture(tmp_path,monkeypatch)
    with pytest.raises(TypeError):op.plan(source,library_table=table,footprint_ids=['cec-Resistor_SMD:R_1206_3216Metric'],expected_instance_uuids=ids,board_hint='opaque',cache={})
