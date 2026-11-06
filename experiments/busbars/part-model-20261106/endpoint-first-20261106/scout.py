"""Six constraint-event-derived placements, not a random pose search."""
import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
p,_=_native()
import cec_force_current as force,cec_fr as fr,cec_assembly_envelope as assembly
import cec_ordinary_route_receiving as ordinary
from shapely.geometry import box,shape
from shapely.ops import unary_union
SOURCE=ROOT/'experiments/repack/bar-corridor-20261106/c9-corrective-v4/candidate/board.kicad_pcb'
COVER=ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb'
CONTRACT=ROOT/'beta/assembly/hub-atx-stack.json'
assert force._hash(SOURCE)=='b118546af6665d77b190a9ac8ce3132cde413d607cdb3d9b28ba620a3857be24'
assert force._hash(COVER)=='c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db'
b=p.LoadBoard(str(SOURCE));cover=p.LoadBoard(str(COVER));contract=json.loads(CONTRACT.read_text())
r,_=assembly.evaluate_boards(b,cover,contract);vents=assembly.facing_vents(r,contract,'carrier')
eligible=ordinary.eligible_nets(b,SOURCE,'atx-24pin-rev3');local=fr._foreign_clearance_resolver(b)
objects=[*b.GetTracks(),*(pad for fp in b.GetFootprints()for pad in fp.Pads())]
courts=[]
for fp in b.GetFootprints():
    n=fp.GetCourtyard(p.F_Cu)
    if fp.GetLayer()==p.F_Cu and n.OutlineCount():courts.append((fp.GetReference(),force._uid(fp),assembly.polygon_from_native(n)))
PARTS={
 '1.0':(ROOT/'experiments/busbars/part-model-20261106/CEC_Busbar_Prototype.pretty',26.8),
 '0.8':(ROOT/'experiments/busbars/part-model-20261106/mjp08-source-fixture/CEC_MJP08_Prototype.pretty',21.72),
 '0.7':(ROOT/'experiments/busbars/part-model-20261106/mjp07-source-fixture/CEC_MJP07_Prototype.pretty',19.18)}
poses=[('1.0',71,72.5),('1.0',71,69.3),('0.7',30.9,43.89),
    ('0.8',30.9,48.86),('1.0',24.1,64.7),('0.7',30.6,45.59)]
rows=[];held=[];width=3230592
for part,x,y in poses:
    lib,length=PARTS[part];fp=p.FootprintLoad(str(lib),next(lib.glob('*.kicad_mod')).stem);held.append(fp)
    fp.SetOrientationDegrees(90);fp.SetPosition(p.VECTOR2I_MM(x,y));b.Add(fp)
    native=assembly.polygon_from_native(fp.GetCourtyard(p.F_Cu));expanded=[native];feet=[]
    for pad in fp.Pads():
        pad.SetSize(p.VECTOR2I(width,width));pad.SetNetCode(b.GetNetcodeFromNetname('/SENSE12V_HI'))
        at=pad.GetPosition();xx,yy=at.x/1e6,at.y/1e6
        expanded.append(box(xx-width/2e6-.25,yy-width/2e6-.25,xx+width/2e6+.25,yy+width/2e6+.25))
        hits=[]
        for item in objects:
            if not item.IsOnLayer(p.F_Cu)or item.GetNetname()=='/SENSE12V_HI':continue
            gap=max(200000,int(local(item,p.F_Cu)))
            if pad.GetEffectiveShape(p.F_Cu).Collide(item.GetEffectiveShape(p.F_Cu),gap):
                hits.append(dict(uuid=force._uid(item),net=item.GetNetname(),kind=item.GetClass(),
                    ref=item.GetParentFootprint().GetReference()if item.GetClass()=='PAD'else None,
                    eligible_ordinary_route=item.GetClass()!='PAD'and item.GetNetname()in eligible))
        # Exact rule-area geometry is separately guarded by the real router.
        feet.append(dict(at_mm=[xx,yy],enlarged_square_land_mm=width/1e6,foreign_clearance_hits=hits))
    expanded=unary_union(expanded);body=box(x-.9,y-length/2,x+.9,y+length/2)
    rows.append(dict(part=part,pose_mm=[x,y,90],native_courtyard_mm=list(native.bounds),
        larger_land_courtyard_mm=list(expanded.bounds),nominal_body_mm=list(body.bounds),feet=feet,
        native_courtyard_owners=[dict(ref=ref,uuid=uid,area_mm2=native.intersection(g).area)for ref,uid,g in courts if native.intersection(g).area>0],
        larger_land_courtyard_owners=[dict(ref=ref,uuid=uid,area_mm2=expanded.intersection(g).area)for ref,uid,g in courts if expanded.intersection(g).area>0],
        vent_intersections=[dict(ref=v['ref'],area_mm2=expanded.intersection(shape(v['xy'])).area)for v in vents]))
    b.Remove(fp)
report=dict(schema=1,target_native_net='/SENSE12V_HI',amps=12,geometry_margin=1.25,width_nm=width,
    source=str(SOURCE),source_sha256=force._hash(SOURCE),cover_sha256=force._hash(COVER),
    poses=rows,scope='Six manually selected constraint-event poses; endpoint-first native FCu clearances then actual cached court plus enlarged-land margin. No board save, current/joint/assembly/route qualification.',
    no_qualified_pad_neckdown=True,larger_land_geometry_is_provisional=True)
(Path(__file__).parent/'selected-endpoints.json').write_text(json.dumps(report,indent=2)+'\n')
for q in rows:
    print(q['part'],q['pose_mm'],'NATIVEOWNERS',[c['ref']for c in q['native_courtyard_owners']],
        'LANDOWNERS',[c['ref']for c in q['larger_land_courtyard_owners']],
        'VENT',[(v['ref'],round(v['area_mm2'],3))for v in q['vent_intersections']],
        'FEET',[(f['at_mm'],len(f['foreign_clearance_hits']),sorted({h['net']for h in f['foreign_clearance_hits']if not h['eligible_ordinary_route']}))for f in q['feet']])
