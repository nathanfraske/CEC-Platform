"""Four explicit front-side bridge positions; saved-source RAM geometry only."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
from cec_pipeline.native import _native
from cec_pipeline import bridges
import cec_assembly_envelope as assembly
import cec_force_current as force
import cec_fr as fr
from shapely.geometry import box, mapping

parser = argparse.ArgumentParser()
parser.add_argument('--case', type=int, required=True, choices=range(4))
parser.add_argument('--local-conflict-counterfactual', action='store_true')
parser.add_argument('--outer-corridor', action='store_true')
args = parser.parse_args()
p, _ = _native()
source = ROOT / 'experiments/busbars/part-model-20261106/endpoint-first-20261106/vbus-shortcut-v6/candidate/board.kicad_pcb'
sha = '4b7457bd28a1a798b6c851b354a2807d02472b8c85b6f583ec48833dce616310'
assert force._hash(source) == sha
b = p.LoadBoard(str(source))
removed=[]
held=[]
if args.local_conflict_counterfactual:
    assert args.case == 0
    # Diagnostic only: distinguish immediate landing occupancy from a second
    # retained-power obstruction. No displaced routing/placement is accepted.
    original=json.loads((Path(__file__).parent/'front-0.json').read_text())
    assert original['source_sha256']==sha
    rows=original['geometry']['land_conflicts']
    assert all(q['kind'] in ('PAD','PCB_TRACK') for q in rows)
    pad_rows=[q for q in rows if q['kind']=='PAD']
    assert {q['reference'] for q in pad_rows}=={'C16'}
    ids={q['uuid'] for q in rows if q['kind']=='PCB_TRACK'}
    held=list(b.GetTracks())+list(b.GetFootprints())
    caps=[fp for fp in held if fp.GetClass()=='FOOTPRINT' and fp.GetReference()=='C16']
    assert len(caps)==1
    for item in held:
        if force._uid(item) in ids:
            assert item.GetClass()=='PCB_TRACK' and item.GetWidth()<=250000
            assert item.GetNetname() in ('GND','+3V3','/I2C_SDA','/I2C_SCL')
            removed.append(dict(uuid=force._uid(item),kind=item.GetClass(),net=item.GetNetname()))
            b.Remove(item)
    assert len(removed)==len(ids)
    removed.append(dict(uuid=force._uid(caps[0]),kind='FOOTPRINT',ref='C16'))
    b.Remove(caps[0])
net = '/SENSE12V_HI'
width = 3230592
a, z = [((46,39.5),(56.7,39.5)), ((46,40),(56.7,40)),
        ((45.5,39.5),(56.2,39.5)), ((46,40.5),(56.7,40.5))][args.case]
cx, cy = (a[0]+z[0])/2, a[1]
body = box(cx-6.15,cy-1.15,cx+6.15,cy+1.15)
lands = [box(x-1.3,y-1.75,x+1.3,y+1.75) for x,y in (a,z)]
candidate = dict(id='front-short-bridge-'+str(args.case),face='F.Cu')
geometry, _ = bridges.screen_geometry(b,body,lands,candidate,net=net,
    clearance=lambda _:500000,mechanical_margin_nm=500000,
    deadline=time.monotonic()+5)
# Land-rule check remains separate from the conservative polygon screen.
holder=p.FOOTPRINT(b)
pad=p.PAD(holder)
holder.Add(pad)
pad.SetShape(p.PAD_SHAPE_RECT)
pad.SetSize(p.VECTOR2I_MM(2.6,3.5))
layers=p.LSET()
layers.AddLayer(p.F_Cu)
pad.SetLayerSet(layers)
rule_hits=[]
for xy in (a,z):
    pad.SetPosition(p.VECTOR2I_MM(*xy))
    rule_hits.append(force._native_track_rule_hits(b,pad.GetEffectiveShape(p.F_Cu),p.F_Cu))
links=[]
requests=[('source',(47.4,38.3582),a),('header',z,(18.349999,77.4))]
if args.outer_corridor:
    assert args.local_conflict_counterfactual and args.case==0
    requests=[('source',(47.4,38.3582),a),('to_right',z,(71,36)),
              ('right_corridor',(71,36),(71,82)),('to_header',(71,82),(18.349999,77.4))]
for label,left,right in requests:
    cache={}
    diag={}
    started=time.monotonic()
    def guard(u,v,half):
        return fr._edge_leg_clear(b,u,v,half) and not force._native_track_rule_hits(
            b,p.SHAPE_SEGMENT(u,v,width),p.F_Cu,cache=cache)
    legs=fr._guarded_profiled_lastmile_legs(b,p.VECTOR2I_MM(*left),p.VECTOR2I_MM(*right),
        width,p.F_Cu,200000,b.GetNetcodeFromNetname(net),guard,
        allow_maze=True,maze_margin_mm=6,foreign_cache=cache,
        deadline_monotonic=time.monotonic()+2,max_length_nm=160000000,
        refine_maze=True,refinement_grids_mm=(.5,.25),search_diagnostics=diag)
    links.append(dict(name=label,found=bool(legs),elapsed_s=time.monotonic()-started,
        legs=[dict(start_mm=[u.x/1e6,u.y/1e6],end_mm=[v.x/1e6,v.y/1e6],width_nm=w)
              for u,v,w in legs or []],diagnostics=diag))
assert force._hash(source)==sha
report=dict(schema=1,source=str(source.relative_to(ROOT)),source_sha256=sha,
    case=args.case,land_centers_mm=[a,z],body_xy=mapping(body),lands_xy=[mapping(l)for l in lands],
    nominal_part='Keystone5104TR',geometry=geometry,land_rule_hits=rule_hits,links=links,
    source_copper_retained=not removed,ram_only_counterfactual_removed=removed,
    removed_items_reconstruction_demonstrated=False,added_vias=0,board_saved=False,
    scope='Finite nominal geometry and guarded PCB link screen only; no mounted part, current, thermal, paired-stack or native DRC admission',
    current_qualified=False,assembled_Z_qualified=False,release_authority=False)
suffix='-local-counterfactual' if removed else ''
if args.outer_corridor:
    suffix+='-outer-corridor'
target=Path(__file__).parent/('front-'+str(args.case)+suffix+'.json')
target.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(case=args.case,land_conflicts=len(geometry['land_conflicts']),
    bodies=geometry['same_face_body_reservations'],holes=geometry['nearby_holes_or_leads'],
    unknown=geometry['unknown'],links=[(q['name'],q['found'])for q in links]),indent=2))
