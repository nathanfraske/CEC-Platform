"""Native metadata-only sync; synthetic export fixtures are not role proofs."""
import copy
import json
import time
from pathlib import Path
import pytest
import pcbnew
import cec_swig_guard
cec_swig_guard.pin()
import cec_component_jumper_metadata as jumper


def exported(groups='(group (pin "1") (pin "6")) (group (pin "3") (pin "4"))',implicit=''):
    return f'''(export (components (comp (ref "X72") (libsource (lib "fixture") (part "six"))
        {implicit} (jumper_pin_groups {groups})))
        (libparts (libpart (lib "fixture") (part "six") (pins
        {' '.join('(pin (num "'+str(i)+'"))' for i in range(1,7))})))
        (nets (net (code "1") (name "signal-P") (node (ref "X72") (pin "1")) (node (ref "X72") (pin "6")))
        (net (code "2") (name "signal-N") (node (ref "X72") (pin "3")) (node (ref "X72") (pin "4")))
        (net (code "3") (name "return") (node (ref "X72") (pin "2")))
        (net (code "4") (name "supply") (node (ref "X72") (pin "5")))))'''


def board_fixture(tmp_path,face='F',turn=0):
    b=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(b);fp.SetReference('X72');fp.SetValue('arbitrary')
    fp.SetFPID(pcbnew.LIB_ID('fixture','generic-package'));b.Add(fp)
    nets={}
    for name in ('signal-P','signal-N','return','supply'):
        nets[name]=pcbnew.NETINFO_ITEM(b,name);b.Add(nets[name])
    for i in range(1,7):
        p=pcbnew.PAD(fp);p.SetNumber(str(i));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I(700000,400000));layers=pcbnew.LSET()
        for layer in (pcbnew.F_Cu,pcbnew.F_Mask,pcbnew.F_Paste):layers.AddLayer(layer)
        p.SetLayerSet(layers)
        p.SetPosition(pcbnew.VECTOR2I(10000000+i*1000000,20000000))
        p.SetNet(nets['signal-P'if i in (1,6)else 'signal-N'if i in (3,4)else 'return'if i==2 else 'supply']);fp.Add(p)
    fp.SetPosition(pcbnew.VECTOR2I(17000000,21000000));fp.SetOrientationDegrees(turn)
    if face=='B':fp.Flip(fp.GetPosition(),False)
    group=pcbnew.PCB_GROUP(b);group.SetName('literal Source group');b.Add(group);group.AddItem(fp)
    mechanical=pcbnew.FOOTPRINT(b);mechanical.SetReference('H57');b.Add(mechanical)
    t=pcbnew.PCB_TRACK(b);t.SetNet(nets['return']);t.SetStart(pcbnew.VECTOR2I(30000000,30000000));t.SetEnd(pcbnew.VECTOR2I(31000000,30000000));t.SetWidth(500000);t.SetLayer(pcbnew.F_Cu);b.Add(t)
    path=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    return path


@pytest.mark.parametrize('face',['F','B'])
@pytest.mark.parametrize('turn',[0,90,180,270])
def test_exact_native_roundtrip_only_metadata(tmp_path,face,turn):
    path=board_fixture(tmp_path,face,turn);before=jumper._parse(path.read_text());contracts=jumper.from_export(exported())
    assert jumper.apply_saved(path,contracts)==['X72']
    assert jumper.read_saved(path)['X72']==(('1','6'),('3','4'))
    assert jumper.read_saved(path)['H57']==()
    assert jumper._without_metadata(before)==jumper._without_metadata(jumper._parse(path.read_text()))
    b=pcbnew.LoadBoard(str(path));fp=b.FindFootprintByReference('X72')
    assert not fp.GetDuplicatePadNumbersAreJumpers()
    saved=tmp_path/'roundtrip.kicad_pcb';pcbnew.SaveBoard(str(saved),b)
    assert jumper.read_saved(saved)==jumper.read_saved(path)
    assert jumper.apply_saved(path,contracts)==[]


@pytest.mark.parametrize('groups',[
    '(group (pin "1"))','(group (pin "1") (pin "1"))',
    '(group (pin "1") (pin "6")) (group (pin "6") (pin "3"))',
    '(group (pin "1") (pin "99"))','(group (pin "1") (pin "3"))',
    '(group (pin "1") (pin "6") (wat "3"))','(group)',
])
def test_export_refuses_unknown_crossnet_malformed_duplicate(groups):
    with pytest.raises(ValueError):jumper.from_export(exported(groups))


@pytest.mark.parametrize('implicit',['(duplicate_pin_numbers_are_jumpers 1)','(duplicate_pin_numbers_are_jumpers yes)',
 '(duplicate_pin_numbers_are_jumpers)','(duplicate_pin_numbers_are_jumpers 0) (duplicate_pin_numbers_are_jumpers 0)'])
def test_implicit_mode_not_supported(implicit):
    with pytest.raises(ValueError):jumper.from_export(exported(implicit=implicit))


@pytest.mark.parametrize('damage',['missing','wrongnet','no-net','overlap','unknown','late','input-change'])
def test_saved_refusal_is_atomic(tmp_path,monkeypatch,damage):
    path=board_fixture(tmp_path);contracts=jumper.from_export(exported())
    if damage in ('missing','wrongnet','no-net'):
        b=pcbnew.LoadBoard(str(path));fp=b.FindFootprintByReference('X72');p=fp.FindPadByNumber('6')
        if damage=='missing':p.SetNumber('66')
        elif damage=='wrongnet':p.SetNet(fp.FindPadByNumber('3').GetNet())
        else:p.SetNetCode(0)
        pcbnew.SaveBoard(str(path),b)
    if damage=='overlap':contracts['X72']['groups']=(('1','6'),('6','3'))
    if damage=='unknown':contracts['X72']['groups']=(('1','99'),)
    before=path.read_bytes()
    if damage=='late':
        times=iter([0.,11.]);monkeypatch.setattr(jumper.time,'monotonic',lambda:next(times))
    if damage=='input-change':
        original=jumper.read_saved
        def mutate(p):
            q=original(p);path.write_bytes(before+b'\n');return q
        monkeypatch.setattr(jumper,'read_saved',mutate)
    with pytest.raises(ValueError):jumper.apply_saved(path,contracts)
    assert path.read_bytes()==before+(b'\n'if damage=='input-change'else b'')


def test_source_hash_and_deadline_rechecked(tmp_path,monkeypatch):
    source=tmp_path/'source.kicad_sch';source.write_text('source')
    import hashlib
    q=dict(files={str(source):hashlib.sha256(source.read_bytes()).hexdigest()},deadline=time.monotonic()+10)
    jumper.check_observation(q);source.write_text('changed')
    with pytest.raises(ValueError,match='hierarchy_changed'):jumper.check_observation(q)
    q['files']={};q['deadline']=0
    with pytest.raises(ValueError,match='deadline'):jumper.check_observation(q)


def test_all_selected_components_validated_before_write(tmp_path):
    path=board_fixture(tmp_path);contracts=jumper.from_export(exported())
    contracts['H57']=copy.deepcopy(contracts['X72'])
    before=path.read_bytes()
    with pytest.raises(ValueError,match='missing_native_jumper_pad'):jumper.apply_saved(path,contracts)
    assert path.read_bytes()==before


def test_component_scope_not_generic_fpid_and_stale_groups_cleared(tmp_path):
    path=board_fixture(tmp_path);contracts=jumper.from_export(exported())
    assert jumper.from_export_tree(jumper._parse(exported()))==contracts
    jumper.apply_saved(path,contracts)
    # Same generic package elsewhere has no symbol ownership and stays exact.
    before=jumper._footprints(jumper._parse(path.read_text()))['H57']
    cleared=jumper.from_export(exported(groups=''))
    assert jumper.apply_saved(path,cleared)==['X72']
    assert jumper.read_saved(path)['X72']==()
    assert jumper._footprints(jumper._parse(path.read_text()))['H57']==before


def test_contract_json_roundtrip_keeps_literal_pin_strings(tmp_path):
    path=board_fixture(tmp_path);contracts=json.loads(json.dumps(jumper.from_export(exported())))
    assert jumper.apply_saved(path,contracts)==['X72']
    contracts['X72']['groups']=[[1,6]]
    before=path.read_bytes()
    with pytest.raises(ValueError,match='literal_contract'):jumper.apply_saved(path,contracts)
    assert path.read_bytes()==before


def test_real_native_roundtrip_damage_refuses(tmp_path,monkeypatch):
    path=board_fixture(tmp_path);contracts=jumper.from_export(exported());before=path.read_bytes()
    original=jumper.pcbnew.SaveBoard
    def damaged(output,b):
        if str(output).endswith('/native.kicad_pcb'):
            fp=b.FindFootprintByReference('X72');fp.SetPosition(pcbnew.VECTOR2I(19000000,24000000))
        return original(output,b)
    monkeypatch.setattr(jumper.pcbnew,'SaveBoard',damaged)
    with pytest.raises(ValueError,match='nonmetadata'):jumper.apply_saved(path,contracts)
    assert path.read_bytes()==before


def test_actual_bounded_cli_exports_explicit_groups(tmp_path):
    """Real KiCad exporter consumes embedded symbol, not fixture verdicts."""
    import uuid
    root=str(uuid.uuid4());owner=str(uuid.uuid4());pins=[];labels=[]
    for i in range(1,7):
        y=(i-1)*2.54
        pins.append(f'(pin passive line (at 0 {y} 0) (length 2.54) (name "P{i}" (effects (font (size 1.27 1.27)))) (number "{i}" (effects (font (size 1.27 1.27)))))')
        net='signal-P'if i in (1,6)else 'signal-N'if i in (3,4)else 'return'if i==2 else 'supply'
        labels.append(f'(global_label "{net}" (shape input) (at 50 {50-y} 0) (effects (font (size 1.27 1.27))) (uuid "{uuid.uuid4()}"))')
    source=tmp_path/'source.kicad_sch'
    source.write_text(f'''(kicad_sch (version 20260101) (generator "eeschema") (uuid "{root}") (paper "A4")
      (lib_symbols (symbol "test:Six" (pin_names (offset 0)) (in_bom yes) (on_board yes)
       (jumper_pin_groups ("1" "6") ("3" "4"))
       (property "Reference" "X" (at 0 0 0) (effects (font (size 1.27 1.27))))
       (property "Value" "Six" (at 0 0 0) (effects (font (size 1.27 1.27))))
       (property "Footprint" "fixture:generic-package" (at 0 0 0) (effects (font (size 1.27 1.27))))
       (symbol "Six_1_1" {' '.join(pins)})))
      {' '.join(labels)}
      (symbol (lib_id "test:Six") (at 50 50 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid "{owner}")
       (property "Reference" "X72" (at 50 50 0) (effects (font (size 1.27 1.27))))
       (property "Value" "Six" (at 50 50 0) (effects (font (size 1.27 1.27))))
       (property "Footprint" "fixture:generic-package" (at 50 50 0) (effects (font (size 1.27 1.27))))
       (instances (project "source" (path "/{root}" (reference "X72") (unit 1))))))''')
    started=time.monotonic();contracts,observation=jumper.observe(source,timeout_s=8.)
    assert time.monotonic()-started<8
    assert contracts['X72']['groups']==(('1','6'),('3','4'))
    assert contracts['X72']['pad_nets']['1']==contracts['X72']['pad_nets']['6']
    jumper.check_observation(observation)


@pytest.mark.parametrize('bounds',[0,-1,11,True,float('nan')])
def test_bounded_native_and_export_leases(tmp_path,bounds):
    with pytest.raises(ValueError):jumper.observe('not-a-source',timeout_s=bounds)
    with pytest.raises(ValueError):jumper.apply_saved(tmp_path/'absent',{},timeout_s=bounds)


@pytest.mark.parametrize('mode',['existing','added','replaced'])
def test_sync_handles_all_native_footprint_lifecycles(tmp_path,monkeypatch,mode):
    import cec_sync_pcb_from_schematic as sync
    path=board_fixture(tmp_path);contracts=jumper.from_export(exported())
    native=pcbnew.LoadBoard(str(path));template=pcbnew.Cast_to_FOOTPRINT(native.FindFootprintByReference('X72').Duplicate(False))
    if mode=='added':
        import cec_native_items
        cec_native_items.discard_items(native,[native.FindFootprintByReference('X72')]);pcbnew.SaveBoard(str(path),native)
    inventory={'X72':dict(value='arbitrary',footprint='fixture:new'if mode=='replaced'else 'fixture:generic-package',props={},dnp=False,in_bom=True,on_board=True)}
    nets={(ref,pin):name for ref,c in contracts.items()for pin,name in c['pad_nets'].items()}
    monkeypatch.setattr(sync,'_schematic_pad_nets',lambda _: (nets,{'X72'}))
    monkeypatch.setattr(sync.cec_sch_gates,'inventory',lambda _:inventory)
    monkeypatch.setattr(sync.cec_pcb_reconcile,'symbol_paths',lambda _: {'X72':'/11111111-1111-4111-8111-111111111111'})
    monkeypatch.setattr(jumper,'observe',lambda *a,**k:(contracts,dict(files={},deadline=time.monotonic()+10)))
    def load(b,ref,part):
        fp=pcbnew.Cast_to_FOOTPRINT(template.Duplicate(False));fp.SetReference(ref);fp.SetFPID(pcbnew.LIB_ID('fixture','new'));b.Add(fp);return fp
    monkeypatch.setattr(sync,'_load_missing_footprint',load)
    monkeypatch.setattr(sync,'_place_new_footprint',lambda *a,**k:[17.,21.,0.])
    report=sync.synchronize('fixture',str(path),add_missing=mode=='added',replace_mismatched_footprints=mode=='replaced',rip_all_copper=mode=='replaced')
    assert report['jumper_metadata_updated_refs']==['X72']
    assert jumper.read_saved(path)['X72']==contracts['X72']['groups']
    assert jumper.read_saved(path)['H57']==()
