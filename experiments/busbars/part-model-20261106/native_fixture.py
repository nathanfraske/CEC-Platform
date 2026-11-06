"""Isolated native test: internally conductive two-foot component semantics."""
import sys,json,subprocess
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path.insert(0,str(ROOT/'scripts'))
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
import cec_force_current as force
WORK=Path(__file__).parent
def pad(fp,number,xy,net):
 p=pcbnew.PAD(fp);p.SetNumber(number);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
 p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(2,2))
 layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);layers.AddLayer(pcbnew.F_Paste);layers.AddLayer(pcbnew.F_Mask);p.SetLayerSet(layers)
 p.SetPosition(pcbnew.VECTOR2I_MM(*xy));p.SetNet(net);fp.Add(p);return p
reports=[]
for variant in('one_pin_two_feet','two_pins_same_net','separate_parts_same_net','one_pin_declared_internal_jumper'):
 directory=WORK/variant;directory.mkdir(exist_ok=True)
 board=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(board,'PWR');board.Add(net)
 for ref,xy in [('J1',(5,10)),('J2',(40.4,10))]:
  fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetPosition(pcbnew.VECTOR2I_MM(*xy));fp.SetLayer(pcbnew.F_Cu);board.Add(fp);pad(fp,'1',xy,net)
 fp=pcbnew.FOOTPRINT(board);fp.SetReference('BB1');fp.SetValue('MJP-1.0_NOMINAL');fp.SetPosition(pcbnew.VECTOR2I_MM(22.7,10));fp.SetLayer(pcbnew.F_Cu);board.Add(fp)
 if variant=='one_pin_declared_internal_jumper':fp.SetDuplicatePadNumbersAreJumpers(True)
 pad(fp,'1',(10,10),net)
 if variant=='separate_parts_same_net':
  fp=pcbnew.FOOTPRINT(board);fp.SetReference('BB2');fp.SetPosition(pcbnew.VECTOR2I_MM(35.4,10));fp.SetLayer(pcbnew.F_Cu);board.Add(fp)
 pad(fp,'2'if variant=='two_pins_same_net'else'1',(35.4,10),net)
 for a,z in[((5,10),(10,10)),((35.4,10),(40.4,10))]:
  t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z));t.SetWidth(500000);t.SetLayer(pcbnew.F_Cu);t.SetNet(net);board.Add(t)
 for a,z in[((0,0),(46,0)),((46,0),(46,20)),((46,20),(0,20)),((0,20),(0,0))]:
  e=pcbnew.PCB_SHAPE(board);e.SetShape(pcbnew.SHAPE_T_SEGMENT);e.SetStart(pcbnew.VECTOR2I_MM(*a));e.SetEnd(pcbnew.VECTOR2I_MM(*z));e.SetWidth(50000);e.SetLayer(pcbnew.Edge_Cuts);board.Add(e)
 path=directory/'board.kicad_pcb';pcbnew.SaveBoard(str(path),board)
 (directory/'board.kicad_pro').write_text('{}\n');(directory/'board.kicad_dru').write_text('(version 1)\n')
 command=['kicad-cli','pcb','drc','--format','json','--output',str(directory/'drc.json'),str(path)]
 run=subprocess.run(command,capture_output=True,text=True,timeout=10)
 assert run.returncode==0,(run.stdout,run.stderr)
 d=json.loads((directory/'drc.json').read_text())
 reports.append(dict(variant=variant,path=str(path),sha256=force._hash(path),unconnected_count=len(d['unconnected_items']),unconnected=d['unconnected_items'],violations=d['violations']))
result=dict(native_version=pcbnew.Version(),scope='synthetic native electrical semantics ONLY, no current/part/release qualification',same_net='PWR',physical_copper_gap_mm=23.4,bar_metal_not_drawn_as_PCB_copper=True,reports=reports)
(WORK/'native-fixture-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({r['variant']:r['unconnected_count']for r in reports}))
