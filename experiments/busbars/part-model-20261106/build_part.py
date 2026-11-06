"""Generate one real provisional component footprint, never span PCB copper."""
import sys,json,subprocess,math
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path.insert(0,str(ROOT/'scripts'))
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
import cec_force_current as force,cec_assembly_envelope as assembly
WORK=Path(__file__).parent;PROFILE=ROOT/'experiments/busbars/mac8-mjp-1.0-nominal.json'
p=json.loads(PROFILE.read_text());name='Mac8_MJP_1p0_NOMINAL_PROTOTYPE'
library=WORK/'CEC_Busbar_Prototype.pretty';library.mkdir(exist_ok=True)
fp=pcbnew.FOOTPRINT(None);fp.SetFPID(pcbnew.LIB_ID('CEC_Busbar_Prototype',name));fp.SetValue(name);fp.SetReference('BB**')
fp.SetLayer(pcbnew.F_Cu);fp.SetAttributes(pcbnew.FP_SMD);fp.SetDuplicatePadNumbersAreJumpers(True)
fp.SetLibDescription('PROVISIONAL nominal Mac8 MJP-1.0 raised conductor. Internal component connection ONLY; no PCB span copper. No guaranteed tolerances/current/joint/Z qualification.')
for key,value in dict(Manufacturer='Mac8',MPN='MJP-1.0',Datasheet=p['drawing'],Qualification='NOMINAL_PROTOTYPE_NOT_RELEASED',Height_nominal_mm='2.3',Underside_nominal_mm='1.8',Catalog_current_A='20_NOT_APPLICATION_QUALIFIED',Source_profile_sha256=force._hash(PROFILE),Electrical_model='ONE_CONTINUOUS_CONDUCTOR_TWO_SOLDER_JOINTS').items():fp.SetField(key,value)
for x in(-p['pitch_nm']//2,p['pitch_nm']//2):
 pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
 pad.SetPosition(pcbnew.VECTOR2I(x,0));pad.SetSize(pcbnew.VECTOR2I(p['land_length_nm'],p['land_width_nm']))
 layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);layers.AddLayer(pcbnew.F_Paste);layers.AddLayer(pcbnew.F_Mask);pad.SetLayerSet(layers);fp.Add(pad)
def rectangle(bounds,layer,width):
 x0,y0,x1,y1=bounds
 for a,b in zip([(x0,y0),(x1,y0),(x1,y1),(x0,y1)],[(x1,y0),(x1,y1),(x0,y1),(x0,y0)]):
  edge=pcbnew.PCB_SHAPE(fp);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetStart(pcbnew.VECTOR2I(*a));edge.SetEnd(pcbnew.VECTOR2I(*b));edge.SetWidth(width);edge.SetLayer(layer);fp.Add(edge)
body=[-p['body_length_nm']//2,-p['body_width_nm']//2,p['body_length_nm']//2,p['body_width_nm']//2]
rectangle(body,pcbnew.F_Fab,100000)
# Engineering courtyard covers nominal body AND recommended lands +0.25mm;
# this allocation is not a vendor tolerance or guaranteed installed envelope.
half=(p['pitch_nm']+p['land_length_nm'])//2+250000
court=[-half,-1250000,half,1250000];rectangle(court,pcbnew.F_CrtYd,50000)
pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(str(library),fp)
saved=pcbnew.FootprintLoad(str(library),name);assert saved and saved.GetDuplicatePadNumbersAreJumpers()
pads=list(saved.Pads());assert len(pads)==2 and all(q.GetNumber()=='1'and q.GetAttribute()==pcbnew.PAD_ATTRIB_SMD for q in pads)
positions=sorted(tuple(q.GetPosition())for q in pads)
assert positions==[(-12700000,0),(12700000,0)]
assert all(tuple(q.GetSize())==(2000000,2000000)for q in pads)
assert all(set(q.GetLayerSet().Seq())=={pcbnew.F_Cu,pcbnew.F_Paste,pcbnew.F_Mask}for q in pads)
assert not any(g.GetLayer()in saved.GetLayerSet().CuStack()for g in saved.GraphicalItems())
saved.BuildCourtyardCaches();c=assembly.polygon_from_native(saved.GetCourtyard(pcbnew.F_Cu));assert c.is_valid
assert all(c.covers(assembly.polygon_from_native(q.GetEffectivePolygon(pcbnew.F_Cu)))for q in pads)
# Load actual generated footprint into the isolated native electrical fixture.
board=pcbnew.LoadBoard(str(WORK/'one_pin_declared_internal_jumper/board.kicad_pcb'))
old=board.FindFootprintByReference('BB1');board.Remove(old);saved.SetParent(board);saved.SetReference('BB1');board.Add(saved);saved.SetPosition(pcbnew.VECTOR2I_MM(22.7,10))
net=board.FindNet('PWR')
for q in saved.Pads():q.SetNet(net)
directory=WORK/'actual_provisional_footprint';directory.mkdir(exist_ok=True)
path=directory/'board.kicad_pcb';pcbnew.SaveBoard(str(path),board)
(directory/'board.kicad_pro').write_text('{}\n');(directory/'board.kicad_dru').write_text('(version 1)\n')
run=subprocess.run(['kicad-cli','pcb','drc','--format','json','--output',str(directory/'drc.json'),str(path)],capture_output=True,text=True,timeout=10);assert run.returncode==0,(run.stdout,run.stderr)
d=json.loads((directory/'drc.json').read_text());assert len(d['unconnected_items'])==0
errors=[v for v in d['violations']if v['severity']=='error']
result=dict(schema=1,scope='PROVISIONAL_NATIVE_COMPONENT_ONLY_NOT_CURRENT_OR_RELEASE',source_profile=dict(path=str(PROFILE),sha256=force._hash(PROFILE)),footprint=dict(path=str(library/(name+'.kicad_mod')),sha256=force._hash(library/(name+'.kicad_mod'))),pads_numbered_one=True,explicit_internal_jumper=True,land_positions_nm=positions,land_size_nm=[2000000,2000000],pitch_nm=25400000,nominal_body_bounds_nm=body,engineering_courtyard_centerline_bounds_nm=court,native_cached_courtyard_bounds_mm=list(c.bounds),nominal_height_nm=2300000,nominal_underside_nm=1800000,guaranteed_tolerances_known=False,span_PCB_copper_present=False,actual_fixture=dict(path=str(path),sha256=force._hash(path),native_opens=0,native_errors=errors),schematic_integrated=False,current_qualified=False,assembled_Z_qualified=False,release_authority=False)
(WORK/'provisional-footprint-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
