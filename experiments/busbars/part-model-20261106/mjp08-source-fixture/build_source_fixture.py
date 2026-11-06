"""Bounded experiment-only exact-MPN source asset and native mapping probe."""
import hashlib,json,subprocess,sys,uuid,xml.etree.ElementTree as ET
from pathlib import Path

WORK=Path(__file__).resolve().parent
ROOT=WORK.parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import cec_swig_guard
import pcbnew
cec_swig_guard.pin()

def uid(value):return str(uuid.uuid5(uuid.NAMESPACE_URL,'cec:mjp08-source-fixture:'+value))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=10)
    if result.returncode:raise RuntimeError((args,result.returncode,result.stdout,result.stderr))
    return dict(command=args,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)

run([sys.executable,str(WORK/'build_nominal_part.py')])
NAME='Mac8_MJP_0p8_NOMINAL_PROTOTYPE'
LIB='CEC_MJP08_Prototype_Source'
FP='CEC_MJP08_Prototype:'+NAME
DRAWING='https://www.mac8japan.com/uploads/entry_meta/file_value/2890/en_2022a_mjp.pdf'
SOURCE_FP=WORK/'CEC_MJP08_Prototype.pretty'/(NAME+'.kicad_mod')
SOURCE_BOARD=WORK.parent/'actual_provisional_footprint/board.kicad_pcb'
originals={str(p):sha(p)for p in(SOURCE_FP,SOURCE_BOARD)}

def prop(name,value,x=0,y=0,hidden=True):
    return f'(property {json.dumps(name)} {json.dumps(value)} (at {x} {y} 0)'+(' (hide yes)'if hidden else'')+' (effects (font (size 1.27 1.27))))'

def symbol(name,reference,value,footprint,jumper=False):
    fields={'Reference':reference,'Value':value,'Footprint':footprint,
        'Datasheet':DRAWING if jumper else'',
        'Description':'PROTOTYPE nominal real formed conductor; one logical passive pin maps two separate solder feet; NOT QUALIFIED'if jumper else'Isolated test terminal, not a product connector'}
    if jumper:fields.update(Manufacturer='Mac8',MPN='MJP-0.8',Material='PHOSPHOR_BRONZE_NOT_COPPER',Finish='TIN_OVER_NICKEL',Reel_MPN='MJP-0.8-T',Reel_quantity='700',Reel_tape_width_mm='32',Qualification='NOMINAL_PROTOTYPE_NOT_RELEASED',Catalog_current_A='20_CATALOG_ONLY_NOT_PATH_OR_JOINT_QUALIFICATION',Height_nominal_mm='2.3',Underside_nominal_mm='1.8',Source_footprint_sha256=sha(SOURCE_FP))
    content=f'(symbol "{name}" (exclude_from_sim yes) (in_bom {"yes"if jumper else"no"}) (on_board yes) (duplicate_pin_numbers_are_jumpers {"yes"if jumper else"no"})\n'
    content+='\n'.join(prop(k,v,0,5.08 if k=='Reference'else-5.08,hidden=k not in('Reference','Value'))for k,v in fields.items())
    content+=f'\n(symbol "{name}_0_1" (rectangle (start -2.54 2.54) (end 2.54 -2.54) (stroke (width 0) (type default)) (fill (type background))))'
    content+=f'\n(symbol "{name}_1_1" (pin passive line (at -5.08 0 0) (length 2.54) (name "LINK" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))))'
    return content,fields

bar,barfields=symbol(NAME,'BB','MJP-0.8',FP,True)
port,portfields=symbol('Fixture_Port','J','FIXTURE_PORT','',False)
library=WORK/(LIB+'.kicad_sym')
library.write_text('(kicad_symbol_lib (version 20251024) (generator "kicad_symbol_editor")\n'+bar+'\n'+port+'\n)\n')
(WORK/'sym-lib-table').write_text(f'(sym_lib_table (lib (name "{LIB}") (type "KiCad") (uri "${{KIPRJMOD}}/{LIB}.kicad_sym") (options "") (descr "EXPERIMENT ONLY")))\n')
(WORK/'fp-lib-table').write_text('(fp_lib_table (lib (name "CEC_MJP08_Prototype") (type "KiCad") (uri "${KIPRJMOD}/CEC_MJP08_Prototype.pretty") (options "") (descr "MJP-0.8 PHOSPHOR BRONZE NOMINAL PROTOTYPE")))\n')
rootid=uid('sheet');sch=WORK/'mjp-source.kicad_sch'
text=f'(kicad_sch (version 20250114) (generator "eeschema") (uuid "{rootid}") (paper "A4")\n'
text+='(title_block (title "MJP-0.8 PHOSPHOR BRONZE SOURCE FIXTURE — NOMINAL PROTOTYPE NOT QUALIFIED"))\n'
text+='(lib_symbols '+bar.replace(f'(symbol "{NAME}"',f'(symbol "{LIB}:{NAME}"',1)+'\n'+port.replace('(symbol "Fixture_Port"',f'(symbol "{LIB}:Fixture_Port"',1)+')\n'
instances={}
for ref,name,y,fields in [('BB1',NAME,50.8,barfields),('J1','Fixture_Port',71.12,portfields),('J2','Fixture_Port',91.44,portfields)]:
    instance=uid(ref);instances[ref]=instance
    text+=f'(wire (pts (xy 40.64 {y}) (xy 45.72 {y})) (stroke (width 0) (type default)) (uuid "{uid(ref+":wire")}"))\n'
    text+=f'(label "PWR" (at 40.64 {y} 0) (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid "{uid(ref+":label")}"))\n'
    text+=f'(symbol (lib_id "{LIB}:{name}") (at 50.8 {y} 0) (unit 1) (exclude_from_sim yes) (in_bom {"yes"if ref=="BB1"else"no"}) (on_board yes) (dnp no) (uuid "{instance}")\n'
    text+='\n'.join(prop(k,ref if k=='Reference'else v,50.8,y-5.08 if k=='Reference'else y+5.08,k not in('Reference','Value'))for k,v in fields.items())
    text+=f'\n(pin "1" (uuid "{uid(ref+":pin1")}")) (instances (project "mjp-source" (path "/{rootid}" (reference "{ref}") (unit 1)))))\n'
text+=')\n';sch.write_text(text)
(WORK/'mjp-source.kicad_pro').write_text('{}\n')
netlist=WORK/'mjp-source.net.xml'
netrun=run(['kicad-cli','sch','export','netlist','--format','kicadxml','--output',str(netlist),str(sch)])
ercrun=run(['kicad-cli','sch','erc','--format','json','--output',str(WORK/'erc.json'),str(sch)])
svgrun=run(['kicad-cli','sch','export','svg','--output',str(WORK/'schematic-svg'),str(sch)])
tree=ET.parse(netlist).getroot();members=[(n.attrib['ref'],n.attrib['pin'])for n in tree.findall("./nets/net[@name='/PWR']/node")]
assert sorted(members)==[('BB1','1'),('J1','1'),('J2','1')],members
# The CLI has no Update-PCB-from-Schematic command. Explicitly map its fresh
# exported terminal table into the isolated native fixture, not a production
# netlist importer or an assertion of GUI transfer behavior.
barfp=pcbnew.PCB_IO_KICAD_SEXPR().FootprintLoad(str(SOURCE_FP.parent),NAME)
board=pcbnew.LoadBoard(str(SOURCE_BOARD));board.Remove(board.FindFootprintByReference('BB1'))
barfp.SetParent(board);board.Add(barfp)
barfp.SetReference('BB1');barfp.SetPosition(pcbnew.VECTOR2I_MM(22.7,10))
# Retain only physical board copper to the TWO actual feet. No span metal.
for track in board.GetTracks():
    for getter,setter in((track.GetStart,track.SetStart),(track.GetEnd,track.SetEnd)):
        point=getter()
        if point.x==10000000:setter(pcbnew.VECTOR2I(12540000,point.y))
        elif point.x==35400000:setter(pcbnew.VECTOR2I(32860000,point.y))
exported_jumper=tree.find("./components/comp[@ref='BB1']/duplicate_pin_numbers_are_jumpers")
assert exported_jumper is not None and exported_jumper.text=='1'
barfp.SetDuplicatePadNumbersAreJumpers(exported_jumper.text=='1')
barfp.SetValue(tree.find("./components/comp[@ref='BB1']/value").text)
net=board.FindNet('PWR');net.SetNetname('/PWR')
for fp in board.GetFootprints():
    assert fp.GetReference()in instances
    fp.SetPath(pcbnew.KIID_PATH('/'+rootid+'/'+instances[fp.GetReference()]))
    fp.Reference().SetPosition(fp.GetPosition()+pcbnew.VECTOR2I(0,-2500000))
    fp.Value().SetLayer(pcbnew.F_Fab);fp.Value().SetVisible(False)
    for p in fp.Pads():
        assert (fp.GetReference(),p.GetNumber())in members
        p.SetNet(net)
candidate=WORK/'mjp-source.kicad_pcb';pcbnew.SaveBoard(str(candidate),board)
(WORK/'mjp-source.kicad_dru').write_text('(version 1)\n')
drcrun=run(['kicad-cli','pcb','drc','--format','json','--output',str(WORK/'drc.json'),str(candidate)])
native=pcbnew.LoadBoard(str(candidate));bb=native.FindFootprintByReference('BB1');pads=list(bb.Pads())
assert len(pads)==2 and {p.GetNumber()for p in pads}=={'1'}and bb.GetDuplicatePadNumbersAreJumpers()
tracks=list(native.GetTracks());assert len(tracks)==2
assert not list(native.Zones())and not any(g.IsOnLayer(pcbnew.F_Cu)for g in bb.GraphicalItems())
graph=pcbnew.CONNECTIVITY_DATA()
material=[*native.GetTracks(),*(p for f in native.GetFootprints()for p in f.Pads())]
for item in material:assert graph.Add(item)
remaining={i.m_Uuid.AsString():i for i in material};physical_components=[]
while remaining:
    key=min(remaining);reached={key}|{i.m_Uuid.AsString()for i in graph.GetConnectedItems(remaining[key])}
    component=sorted(set(remaining)&reached);assert component
    physical_components.append(component)
    for key in component:del remaining[key]
assert len(physical_components)==2
import cec_current_topology as topology
transport_guard=topology.unmodelled_internal_transports(native,['/PWR'])
assert transport_guard
drc=json.loads((WORK/'drc.json').read_text());erc=json.loads((WORK/'erc.json').read_text())
assert not drc['unconnected_items']
assert {str(p):sha(p)for p in(SOURCE_FP,SOURCE_BOARD)}==originals
receipt=dict(schema=1,scope='EXPERIMENT_ONLY_SOURCE_COMPONENT_NATIVE_SEMANTICS_NOT_APPLICATION_QUALIFICATION',
    kicad_version=pcbnew.Version(),source_inputs_sha256=originals,
    generated_sha256={str(p.relative_to(ROOT)):sha(p)for p in(library,sch,netlist,candidate)},
    original_footprint_sha256=sha(SOURCE_FP),single_logical_passive_pin=True,
    profile_sha256=sha(WORK/'mac8-mjp-0.8-nominal.json'),material='phosphor bronze; NOT copper',
    symbol_duplicate_pin_numbers_are_jumpers=True,footprint_duplicate_pad_numbers_are_jumpers=bb.GetDuplicatePadNumbersAreJumpers(),
    netlist_exported_jumper_value=exported_jumper.text,
    netlist_members=sorted(members),physical_pad_records=[dict(uuid=p.m_Uuid.AsString(),number=p.GetNumber(),at_nm=list(p.GetPosition()),net=p.GetNetname())for p in pads],
    source_instance_path=bb.GetPath().AsString(),native_tracks=2,span_PCB_copper_present=False,
    physical_PCB_component_count=2,physical_PCB_components=physical_components,
    unmodelled_internal_transport_guard=transport_guard,
    erc=erc,erc_counts=dict(errors=sum(v['severity']=='error'for s in erc['sheets']for v in s['violations']),warnings=sum(v['severity']=='warning'for s in erc['sheets']for v in s['violations'])),native_drc=dict(errors=[v for v in drc['violations']if v['severity']=='error'],warnings=[v for v in drc['violations']if v['severity']=='warning'],opens=len(drc['unconnected_items'])),
    commands=[netrun,ercrun,svgrun,drcrun],
    native_mapping_method='fresh CLI XML netlist exact ref/pin membership mapped explicitly into isolated native fixture; no automated GUI update claimed',
    limitations=['one schematic passive pin maps two DISTINCT physical solder-contact UUIDs',
        'native assembled connectivity is not a PCB-copper-only path or current/FEM transport model',
        'no native CLI PCB-update command available; automatic symbol-to-footprint jumper transfer not exercised',
        '20A catalog only; joints, PCB15A path/barrels, tolerances, installedZ and paste process unqualified'],
    current_qualified=False,assembled_Z_qualified=False,production_sources_changed=False,release_authority=False)
(WORK/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(dict(netlist_members=members,erc=receipt['erc_counts'],native_drc=dict(errors=len(receipt['native_drc']['errors']),warnings=len(receipt['native_drc']['warnings']),opens=receipt['native_drc']['opens']),candidate_sha256=sha(candidate)),indent=2))
