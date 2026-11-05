"""Typed actual-source manufacturer transformation, never old/new aliases."""
import json
from pathlib import Path
import time
import uuid

import pcbnew
import pytest
import cec_constraints as constraints
import cec_field_coupling as field
import cec_force_current as force
import cec_manufacturer_footprint_parity as parity
import cec_manufacturer_land_pattern as patterns
import cec_source_ground_leaf as source
import test_manufacturer_shunt_land_pattern as shunt


def fixture(tmp_path,*,quarter=0,back=False,name='RENAMED_LOAD_PART'):
    native,uid=shunt.fixture(tmp_path,angle=quarter*90,back=back,name=name)
    board=pcbnew.LoadBoard(str(native));fp=next(iter(board.GetFootprints()))
    fp.SetField('Manufacturer','Bourns')
    root_uid=str(uuid.uuid4());symbol_uid=str(uuid.uuid4())
    def effects():return '(effects (font (size 1.27 1.27)))'
    props=dict(Reference=name,Value='0.5mΩ',Footprint='cec-Resistor_SMD:R_2512_6332Metric',
        MPN='CSS2H-2512R-L500F',Manufacturer='Bourns')
    def properties():
        return ' '.join('(property '+json.dumps(k)+' '+json.dumps(v,ensure_ascii=False)+
            ' (at 20 15 0) '+effects()+')'for k,v in props.items())
    pins=' '.join('(pin passive line (at '+str(x)+' 0 '+str(angle)+') (length 2.54) '
        '(name "P'+number+'" '+effects()+') (number "'+number+'" '+effects()+'))'
        for number,x,angle in(('1',-2.54,0),('2',2.54,180)))
    schematic=tmp_path/'fixture.kicad_sch'
    schematic.write_text('(kicad_sch (version 20250114) (generator "eeschema") (uuid "'+root_uid+'") '
        '(paper "A4") (lib_symbols (symbol "fixture:Part" (in_bom yes) (on_board yes) '+properties()+
        ' (symbol "Part_1_1" '+pins+'))) '
        '(symbol\n(lib_id "fixture:Part") (at 20 20 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) '
        '(uuid "'+symbol_uid+'") '+properties()+
        ' (pin "1" (uuid "'+str(uuid.uuid4())+'")) (pin "2" (uuid "'+str(uuid.uuid4())+'")) '
        '(instances (project "fixture" (path "/'+root_uid+'" (reference '+json.dumps(name)+') (unit 1))))) '
        '(label "FEED_ONE" (at 17.46 20 0) '+effects()+' (uuid "'+str(uuid.uuid4())+'")) '
        '(label "FEED_TWO" (at 22.54 20 0) '+effects()+' (uuid "'+str(uuid.uuid4())+'")))')
    # This fixture uses the REAL installed CLI, not a mocked positive export.
    tree,exporter=source._export(schematic.resolve(),time.monotonic()+9.1)
    comps,nets,node_nets=source._tables(tree)
    for pad in fp.Pads():
        net=pcbnew.NETINFO_ITEM(board,node_nets[name,pad.GetNumber()]);board.Add(net);pad.SetNet(net)
    proposal=patterns.plan(board,[uid]);patterns.materialize(board,proposal)
    field._save_field_snapshot(board,native)
    return board,fp,native,schematic


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('name',['RENAMED_LOAD_PART','OTHER_SCOPE_781'])
def test_real_export_source_and_exact_native_recipe_prove_only_the_derived_footprint(
        tmp_path,quarter,back,name):
    board,fp,native,schematic=fixture(tmp_path,quarter=quarter,back=back,name=name)
    saved=[p.read_bytes()for p in(native,schematic)]
    proof=parity.assess(board,schematic,[name])
    assert proof['ok']and proof['complete'],proof
    assert proof['proofs'][name]['complete_native_land_courtyard_and_manufacturing_overrides_received']
    assert not proof['current_qualified']and not proof['factory_qualified']and not proof['canonical_source_converged']
    ctx={'sch':str(schematic)};verdict,message=constraints._chk_sch_pcb_sync(board,str(native),ctx)
    assert verdict is True,message
    assert 'freshly proved manufacturer transformations'in message
    assert ctx['_manufacturer_footprint_parity']['proofs'][name]['selected_mpn']=='CSS2H-2512R-L500F'
    assert saved==[p.read_bytes()for p in(native,schematic)]


@pytest.mark.parametrize('fault',['size','center','shape','offset','mask','paste','clearance',
    'drill','layer','extra_pad','missing_pin','court','mpn','maker','value','fpid','dnp','pin_net','copper_art'])
def test_filename_or_selected_part_alone_cannot_exempt_wrong_native_material(tmp_path,fault):
    board,fp,native,schematic=fixture(tmp_path);pad=fp.FindPadByNumber('1')
    if fault=='size':pad.SetSize(pad.GetSize()+pcbnew.VECTOR2I(1,0))
    elif fault=='center':pad.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I(1,0))
    elif fault=='shape':pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
    elif fault=='offset':pad.SetOffset(pcbnew.VECTOR2I(1,0))
    elif fault=='mask':pad.SetLocalSolderMaskMargin(1)
    elif fault=='paste':pad.SetLocalSolderPasteMargin(1)
    elif fault=='clearance':pad.SetLocalClearance(1)
    elif fault=='drill':pad.SetDrillSize(pcbnew.VECTOR2I(100000,100000))
    elif fault=='layer':pad.SetLayerSet(pcbnew.PAD.PTHMask())
    elif fault=='extra_pad':
        extra=pcbnew.PAD(fp);extra.SetNumber('1');fp.Add(extra)
    elif fault=='missing_pin':pad.SetNumber('99')
    elif fault=='court':patterns._courts(fp)[0].SetWidth(60000)
    elif fault=='mpn':fp.SetField('MPN','CSS2H-2512R-L300F')
    elif fault=='maker':fp.SetField('Manufacturer','OTHER')
    elif fault=='value':fp.SetValue('1mΩ')
    elif fault=='fpid':fp.SetFPIDAsString('unknown:R_Bourns_CSS2H-2512R_L500')
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='pin_net':pad.SetNet(fp.FindPadByNumber('2').GetNet())
    else:
        art=pcbnew.PCB_SHAPE(fp);art.SetLayer(pcbnew.F_Cu);art.SetShape(pcbnew.SHAPE_T_SEGMENT)
        art.SetStart(fp.GetPosition());art.SetEnd(fp.GetPosition()+pcbnew.VECTOR2I(100000,0));art.SetWidth(100000);fp.Add(art)
    proof=parity.assess(board,schematic,[fp.GetReference()])
    assert not proof['ok']and not proof['proofs'],proof
    assert constraints._chk_sch_pcb_sync(board,str(native),{'sch':str(schematic)})[0]is False


@pytest.mark.parametrize('fault',['mpn','manufacturer','value','predecessor','uuid','duplicate'])
def test_canonical_or_exported_mismatch_is_not_a_native_part_alias(tmp_path,fault):
    board,fp,native,schematic=fixture(tmp_path);text=schematic.read_text()
    if fault=='mpn':text=text.replace('CSS2H-2512R-L500F','CSS2H-2512R-L300F')
    elif fault=='manufacturer':text=text.replace('"Bourns"','"OTHER"');fp.SetField('Manufacturer','OTHER')
    elif fault=='value':text=text.replace('0.5mΩ','1mΩ')
    elif fault=='predecessor':text=text.replace('R_2512_6332Metric','R_UNKNOWN')
    elif fault=='uuid':
        # Native instance path contradicts the actual fresh Source symbol.
        path=pcbnew.KIID_PATH();path.push_back(pcbnew.KIID(str(uuid.uuid4())));fp.SetPath(path)
    else:
        actual=next(iter(board.GetFootprints()));copy=actual.Duplicate(False);copy.SetParent(board);board.Add(copy)
    schematic.write_text(text)
    proof=parity.assess(board,schematic,[fp.GetReference()])
    assert not proof['ok']and not proof['proofs'],proof


@pytest.mark.parametrize('fault',['source','asset','code','native','mask','paste','clearance','maker','court','art','jumper','expired'])
def test_enclosing_checker_must_revalidate_the_whole_typed_epoch(tmp_path,monkeypatch,fault):
    board,fp,native,schematic=fixture(tmp_path);proof=parity.assess(board,schematic,[fp.GetReference()])
    assert proof['ok'],proof
    if fault=='source':schematic.write_text(schematic.read_text()+'\n')
    elif fault=='asset':
        old=patterns.library_identity();monkeypatch.setattr(patterns,'library_identity',lambda:dict(old,extra='changed'))
    elif fault=='code':
        old=force._code_identity();monkeypatch.setattr(force,'_code_identity',lambda:dict(old,extra='changed'))
    elif fault=='native':fp.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I(1800001,3400000))
    elif fault=='mask':fp.FindPadByNumber('1').SetLocalSolderMaskMargin(1)
    elif fault=='paste':fp.SetLocalSolderPasteMargin(1)
    elif fault=='clearance':fp.SetLocalClearance(1)
    elif fault=='maker':fp.SetField('Manufacturer','OTHER')
    elif fault=='court':patterns._courts(fp)[0].SetWidth(60000)
    elif fault=='art':fp.SetField('UNOWNED_MANUFACTURER_METADATA','changed')
    elif fault=='jumper':fp.SetDuplicatePadNumbersAreJumpers(True)
    else:monkeypatch.setattr(parity.time,'monotonic',lambda:proof['deadline']+1)
    assert not parity.still_current(proof,board)


@pytest.mark.parametrize('fault',['jumper','mask','manufacturer'])
def test_initial_jumper_reader_cannot_mutate_native_material_before_manufacturer_proof(tmp_path,monkeypatch,fault):
    board,fp,native,schematic=fixture(tmp_path)
    import cec_component_jumper_metadata as jumper
    actual=jumper.read_native
    def changed(*args,**kwargs):
        result=actual(*args,**kwargs)
        if fault=='jumper':fp.SetDuplicatePadNumbersAreJumpers(True)
        elif fault=='mask':fp.FindPadByNumber('1').SetLocalSolderMaskMargin(1)
        else:fp.SetField('Manufacturer','OTHER')
        return result
    monkeypatch.setattr(jumper,'read_native',changed)
    assert constraints._chk_sch_pcb_sync(board,str(native),{'sch':str(schematic)})[0]is False
