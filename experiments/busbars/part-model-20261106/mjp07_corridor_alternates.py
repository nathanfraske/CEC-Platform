"""Finite read-only MJP0.7 mechanical/contact scout, not qualification."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
pcbnew,_=_native()
import cec_assembly_envelope as assembly,cec_force_current as force,cec_fr as fr
import cec_current_topology as topology,cec_decoupler_cell as cells
from shapely.geometry import box,shape
SOURCE=ROOT/'experiments/repack/bar-corridor-20261106/c9-corrective-v4/candidate/board.kicad_pcb'
COVER=ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb'
CONTRACT=ROOT/'beta/assembly/hub-atx-stack.json'
PART=ROOT/'experiments/busbars/part-model-20261106/mjp07-source-fixture/CEC_MJP07_Prototype.pretty'
assert force._hash(SOURCE)=='b118546af6665d77b190a9ac8ce3132cde413d607cdb3d9b28ba620a3857be24'
assert force._hash(COVER)=='c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db'
TARGET='/SENSE12V_HI'
b=pcbnew.LoadBoard(str(SOURCE));cover=pcbnew.LoadBoard(str(COVER));contract=json.loads(CONTRACT.read_text())
baseline,pops=assembly.evaluate_boards(b,cover,contract)
vents=assembly.facing_vents(baseline,contract,'carrier')
local=fr._foreign_clearance_resolver(b);rows=[];held=[]
name=next(PART.glob('*.kicad_mod')).stem
poses=[(23.2,54.73,90),(22.0,54.73,90),(24.2,54.73,90),(25.5,54.73,90),
    (27.0,54.73,90),(30.9,54.73,90),(30.9,53.73,90),(30.9,55.73,90),
    (23.2,54.73,0),(27.0,54.73,0)]
for x,y,d in poses:
    fp=pcbnew.FootprintLoad(str(PART),name);fp.SetReference('SCOUT_BAR_ONLY')
    held.append(fp)
    fp.SetOrientationDegrees(d);fp.SetPosition(pcbnew.VECTOR2I_MM(x,y));b.Add(fp)
    court=assembly.polygon_from_native(fp.GetCourtyard(pcbnew.F_Cu))
    body=box(x-.9,y-9.59,x+.9,y+9.59)if d==90 else box(x-9.59,y-.9,x+9.59,y+.9)
    conflicts=[]
    for other in b.GetFootprints():
        if other==fp or other.GetLayer()!=pcbnew.F_Cu:continue
        q=other.GetCourtyard(pcbnew.F_Cu)
        if not q.OutlineCount():continue
        g=assembly.polygon_from_native(q);area=g.intersection(court).area
        if area>0:conflicts.append(dict(ref=other.GetReference(),uuid=force._uid(other),
            courtyard_overlap_mm2=area,nominal_metal_vs_existing_courtyard_XY_overlap_mm2=g.intersection(body).area,
            source_courtyard_mm=list(g.bounds)))
    feet=[]
    for pad in fp.Pads():
        face=pcbnew.F_Cu;hits=[]
        for item in[*b.GetTracks(),*(p for f in b.GetFootprints()if f!=fp for p in f.Pads())]:
            if not item.IsOnLayer(face)or item.GetNetname()==TARGET:continue
            gap=max(int(b.GetDesignSettings().m_MinClearance),int(local(item,face)),200000)
            if pad.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face),gap):
                hits.append(dict(uuid=force._uid(item),net=item.GetNetname(),kind=item.GetClass(),
                    clearance_mm=gap/1e6,at_mm=[item.GetPosition().x/1e6,item.GetPosition().y/1e6]))
        feet.append(dict(at_mm=[pad.GetPosition().x/1e6,pad.GetPosition().y/1e6],foreign_hits=hits))
    rows.append(dict(pose_mm=[x,y,d],native_courtyard_mm=list(court.bounds),nominal_body_XY_mm=list(body.bounds),
        same_face_courtyard_conflicts=conflicts,feet=feet,
        vent_intersections=[dict(ref=v['ref'],court_area_mm2=court.intersection(shape(v['xy'])).area,
            nominal_body_area_mm2=body.intersection(shape(v['xy'])).area)for v in vents]))
    b.Remove(fp)
terminals=[]
for fp in b.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNetname()==TARGET:terminals.append(dict(ref=fp.GetReference(),pin=pad.GetNumber(),uuid=force._uid(pad),
            at_mm=[pad.GetPosition().x/1e6,pad.GetPosition().y/1e6],drill_mm=[v/1e6 for v in pad.GetDrillSize()]))
with force._thermal_hint('atx-24pin-rev3'):
    domain=topology.board_current_domains(b,'atx-24pin-rev3')[TARGET]
    current=cells._supply_current_widths(b,TARGET)
result=dict(schema=1,scope='FINITE_READ_ONLY_12V_CORRIDOR_SCOUT_NOT_SYS_PORT_REASSIGNMENT',target_native_net=TARGET,
    authority=[dict(path=str(p),sha256=force._hash(p))for p in[SOURCE,COVER,CONTRACT]],
    nominal_part_definition=dict(path=str(PART/(name+'.kicad_mod')),sha256=force._hash(PART/(name+'.kicad_mod'))),
    poses=rows,actual_12V_terminals=terminals,source_current_domain=domain,source_current_contract=current,
    Kelvin_obligation='Same /SENSE12V_HI force leg J3.10/11 to RS1.1 only. Preserve RS1.2 /SENSE12V_LO to TB1 and U10 HI/LO Kelvin branch identity; no shunt bypass or repartition/current-sharing inference.',
    previous_conditional_stack_bound=dict(gain_X_mm=2,gain_Y_mm=0,baseline_declared_size_mm=[89.585,93.09],
        conditional_trim_size_mm=[87.585,93.09],new_additional_gain_proved_mm=0),
    qualification=dict(source_qualified=False,current_qualified=False,
        installed_Z_qualified=False,routed_candidate=False,outline_gain_proved=False),
    limits='Native courts and native FCu pad/track/via clearance only; no saved-fill clearance or actual assembly receiving with nominal bar. Metal XY versus existing courtyard is classification, not permission for under-bar components or court waivers.')
assert force._hash(SOURCE)=='b118546af6665d77b190a9ac8ce3132cde413d607cdb3d9b28ba620a3857be24'
(Path(__file__).parent/'mjp07-corridor-alternates.json').write_text(json.dumps(result,indent=2)+'\n')
for r in rows:print(r['pose_mm'],[(q['ref'],round(q['courtyard_overlap_mm2'],4))for q in r['same_face_courtyard_conflicts']],
    'VENT',[(v['ref'],round(v['court_area_mm2'],4))for v in r['vent_intersections']],
    'FEET',[(f['at_mm'],sorted({h['net']for h in f['foreign_hits']}))for f in r['feet']])
print('12V_TERMINALS',terminals)
