import copy
import uuid
from pathlib import Path
import pcbnew
import pytest
import cec_ink_only_variant as ink
import cec_field_coupling as field
import cec_force_current as force


def fixture(tmp_path,monkeypatch,turn=0,back=False):
    root=tmp_path/'authority';vendor=root/'lib/vendor/Fixture.pretty';vendor.mkdir(parents=True)
    monkeypatch.setattr(ink.nonpolar,'ROOT',root)
    b=pcbnew.BOARD();b.SetCopperLayerCount(6);fp=pcbnew.FOOTPRINT(b);b.Add(fp)
    fp.SetFPID(pcbnew.LIB_ID('Original','Optional_Frame'));fp.SetReference('renamed_owner');fp.SetValue('unchanged identity')
    def line(a,z,layer=pcbnew.F_SilkS,width=150000):
        g=pcbnew.PCB_SHAPE(fp);g.SetShape(pcbnew.SHAPE_T_SEGMENT);g.SetLayer(layer);g.SetWidth(width)
        g.SetStart(pcbnew.VECTOR2I_MM(*a));g.SetEnd(pcbnew.VECTOR2I_MM(*z));fp.Add(g)
    for a,z in [((-3,-2),(3,-2)),((3,-2),(3,2)),((3,2),(-3,2)),((-3,2),(-3,-2))]:line(a,z)
    line((-3.5,-2.5),(3.5,-2.5),pcbnew.F_CrtYd,50000)
    line((-2,-1),(2,-1),pcbnew.F_Fab,100000)
    for index,y in enumerate((-2,0),1):
        p=pcbnew.PAD(fp);p.SetNumber(str(index));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));p.SetPosition(pcbnew.VECTOR2I_MM(0,y));layers=pcbnew.LSET()
        for layer in(pcbnew.F_Cu,pcbnew.F_Paste,pcbnew.F_Mask):layers.AddLayer(layer)
        p.SetLayerSet(layers);fp.Add(p)
    for f in fp.GetFields():f.SetVisible(False)
    pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(str(vendor),fp);template=vendor/'Optional_Frame.kicad_mod'
    symbol=str(uuid.uuid4());path=pcbnew.KIID_PATH();path.push_back(pcbnew.KIID(symbol));fp.SetPath(path)
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    fp.SetOrientationDegrees(turn);fp.SetPosition(pcbnew.VECTOR2I_MM(15,15))
    for a,z in [((0,0),(30,0)),((30,0),(30,30)),((30,30),(0,30)),((0,30),(0,0))]:
        g=pcbnew.PCB_SHAPE(b);g.SetShape(pcbnew.SHAPE_T_SEGMENT);g.SetLayer(pcbnew.Edge_Cuts);g.SetWidth(50000)
        g.SetStart(pcbnew.VECTOR2I_MM(*a));g.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(g)
    source=tmp_path/'source/board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    sch=tmp_path/'source/root.kicad_sch';sch.write_text('(kicad_sch (version 20250114) (symbol (uuid '+symbol+') (property "Footprint" "Original:Optional_Frame" (at 1 2 0)) (property "Value" "unchanged identity")))')
    selection=dict(footprint_uuid=force._uid(fp),template_path=str(template),kind='rectangular_frame',schematic_path=str(sch),symbol_uuid=symbol)
    return source,selection,sch,template


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_independent_source_private_variant_all_faces_and_rotations(tmp_path,monkeypatch,turn,back):
    source,selection,sch,template=fixture(tmp_path,monkeypatch,turn,back)
    before=[p.read_bytes()for p in(source,sch,template)]
    q=ink.plan(source,selections=[selection],board_hint='synthetic')
    assert sum(len(x['pieces'])for x in q['records'][0]['ink'])==5
    artifact=ink.construct_private(source,q,tmp_path/'private')
    r=ink.receive(source,artifact['candidate'],q);assert r['ok']and r['complete'],r.get('first_literal_difference',r)
    assert not r['admitted']and [p.read_bytes()for p in(source,sch,template)]==before
    copied=Path(artifact['private_schematic_copies'][0]).read_text()
    assert q['records'][0]['variant_fpid']in copied and 'unchanged identity'in copied
    assert ink.plan(source,selections=[selection],board_hint='synthetic')==q


@pytest.mark.parametrize('fault',['pad','court','fab','extra_marker','locked','group','dnp','wrong_symbol','wrong_symbol_fpid','unknown_kind','outside_vendor'])
def test_positive_independent_authority_required(tmp_path,monkeypatch,fault):
    source,s,sch,template=fixture(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    if fault=='pad':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(.9,.8))
    elif fault in('court','fab'):
        layer=pcbnew.F_CrtYd if fault=='court'else pcbnew.F_Fab
        next(g for g in fp.GraphicalItems()if g.GetLayer()==layer).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='extra_marker':
        g=pcbnew.PCB_SHAPE(fp);g.SetShape(pcbnew.SHAPE_T_CIRCLE);g.SetLayer(pcbnew.F_SilkS);g.SetStart(pcbnew.VECTOR2I_MM(16,16));g.SetEnd(pcbnew.VECTOR2I_MM(16.2,16));fp.Add(g)
    elif fault=='locked':fp.SetLocked(True)
    elif fault=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(fp)
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='wrong_symbol':s['symbol_uuid']=str(uuid.uuid4())
    elif fault=='wrong_symbol_fpid':sch.write_text(sch.read_text().replace('Original:Optional_Frame','Wrong:Part'))
    elif fault=='unknown_kind':s['kind']='unknown_connector'
    elif fault=='outside_vendor':s['template_path']=str(tmp_path/'outside.kicad_mod');Path(s['template_path']).write_bytes(template.read_bytes())
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):ink.plan(source,selections=[s],board_hint='synthetic')


@pytest.mark.parametrize('fault',['pad','pose','label','sidecar','template','schematic','extra_file','fpid'])
def test_exact_private_saved_transaction_refuses_unowned_mutation(tmp_path,monkeypatch,fault):
    source,s,sch,template=fixture(tmp_path,monkeypatch);q=ink.plan(source,selections=[s],board_hint='synthetic')
    a=ink.construct_private(source,q,tmp_path/'private');child=Path(a['candidate'])
    if fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n# changed\n')
    elif fault=='template':p=Path(a['private_templates'][0]);p.write_text(p.read_text()+'\n# forged\n')
    elif fault=='schematic':p=Path(a['private_schematic_copies'][0]);p.write_text(p.read_text().replace('unchanged identity','forged identity'))
    elif fault=='extra_file':(child.parent/'unowned.txt').write_text('no')
    else:
        b=pcbnew.LoadBoard(str(child));fp=next(iter(b.GetFootprints()))
        if fault=='pad':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(1,1))
        elif fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
        elif fault=='label':fp.SetReference('OTHER')
        else:fp.SetFPID(pcbnew.LIB_ID('forged','identity'))
        field._save_field_snapshot(b,child)
    assert not ink.receive(source,child,q)['ok']


def test_forged_plan_and_changed_original_refuse(tmp_path,monkeypatch):
    source,s,sch,template=fixture(tmp_path,monkeypatch);q=ink.plan(source,selections=[s],board_hint='synthetic')
    forged=copy.deepcopy(q);forged['records'][0]['ink'][0]['width_nm']+=1
    with pytest.raises(ValueError,match='forged'):ink.construct_private(source,forged,tmp_path/'first')
    sch.write_text(sch.read_text()+'\n# changed original evidence\n')
    with pytest.raises(ValueError,match='forged'):ink.construct_private(source,q,tmp_path/'second')


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_positive_symmetric_nonpolar_independent_pattern(tmp_path,monkeypatch,turn,back):
    source,s,sch,_=fixture(tmp_path,monkeypatch)
    repo=Path(__file__).resolve().parents[1];name='R_1206_3216Metric'
    library=ink.nonpolar.ROOT/'lib/vendor/Resistor_SMD.pretty';library.mkdir()
    authority=pcbnew.FootprintLoad(str(repo/'lib/vendor/Resistor_SMD.pretty'),name)
    # Independent synthetic source/template has manufacturing-width ink.
    # Real unmodified .12mm stock artwork remains a separately refused scope.
    for g in authority.GraphicalItems():
        if g.GetLayer()==pcbnew.F_SilkS:g.SetWidth(150000)
    pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(str(library),authority)
    b=pcbnew.LoadBoard(str(source));old=next(iter(b.GetFootprints()));b.Remove(old)
    fp=pcbnew.FootprintLoad(str(library),name);b.Add(fp);fp.SetFPID(pcbnew.LIB_ID('cec-Resistor_SMD',name));fp.SetReference('N7');fp.SetValue('retained')
    path=pcbnew.KIID_PATH();path.push_back(pcbnew.KIID(s['symbol_uuid']));fp.SetPath(path)
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    fp.SetOrientationDegrees(turn);fp.SetPosition(pcbnew.VECTOR2I_MM(15,15));fp.Reference().SetVisible(True)
    fp.Reference().SetPosition(pcbnew.VECTOR2I_MM(5,5));fp.Reference().SetLayer(pcbnew.B_SilkS if back else pcbnew.F_SilkS)
    # A real separate native aperture clips one endpoint, not an invented bbox.
    line=next(g for g in fp.GraphicalItems()if g.GetLayer()==fp.Reference().GetLayer())
    other=pcbnew.FOOTPRINT(b);b.Add(other);p=pcbnew.PAD(other);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetSize(pcbnew.VECTOR2I_MM(.2,.2));p.SetPosition(line.GetStart());layers=pcbnew.LSET()
    for layer in ((pcbnew.B_Cu,pcbnew.B_Mask)if back else(pcbnew.F_Cu,pcbnew.F_Mask)):layers.AddLayer(layer)
    p.SetLayerSet(layers);other.Add(p)
    field._save_field_snapshot(b,source);sch.write_text(sch.read_text().replace('Original:Optional_Frame','cec-Resistor_SMD:'+name))
    s.update(footprint_uuid=force._uid(fp),template_path=str(library/(name+'.kicad_mod')),kind='nonpolar')
    q=ink.plan(source,selections=[s],board_hint='synthetic');a=ink.construct_private(source,q,tmp_path/'private')
    r=ink.receive(source,a['candidate'],q);assert r['ok'],r


def test_source_factory_thin_ink_never_silently_widened_or_waived(tmp_path,monkeypatch):
    source,s,sch,template=fixture(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    for g in fp.GraphicalItems():
        if g.GetLayer()==pcbnew.F_SilkS:g.SetWidth(120000)
    field._save_field_snapshot(b,source)
    library=pcbnew.FootprintLoad(str(template.parent),template.stem)
    for g in library.GraphicalItems():
        if g.GetLayer()==pcbnew.F_SilkS:g.SetWidth(120000)
    pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(str(template.parent),library)
    with pytest.raises(ValueError,match='below_factory_floor'):ink.plan(source,selections=[s],board_hint='synthetic')
