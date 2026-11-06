"""Source-bound two-stage left-bus topology inventory; RAM only."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
p,_=_native()
import cec_force_current as f,cec_fr as fr,cec_assembly_envelope as assembly
from shapely.geometry import box
S=ROOT/'experiments/busbars/part-model-20261106/endpoint-first-20261106/vbus-shortcut-v6/candidate/board.kicad_pcb'
assert f._hash(S)=='4b7457bd28a1a798b6c851b354a2807d02472b8c85b6f583ec48833dce616310'
b=p.LoadBoard(str(S));gap=fr._foreign_clearance_resolver(b);net='/SENSE12V_HI';width=3230592
objects=[*b.GetTracks(),*(pad for fp in b.GetFootprints()for pad in fp.Pads())]
endpoints=[(4,32.1),(4,57.5),(4,60),(4,80.32),(4,85.4),(8,34.6),(8,60),(5,60),(5,85.4),(20,34.6),(20,60),(24,60),(24,85.4)]
holder=p.FOOTPRINT(b);probe=p.PAD(holder);holder.Add(probe);probe.SetShape(p.PAD_SHAPE_RECT);probe.SetSize(p.VECTOR2I(width,width))
layers=p.LSET();layers.AddLayer(p.B_Cu);probe.SetLayerSet(layers);probe.SetAttribute(p.PAD_ATTRIB_SMD)
zones=[(z,assembly.polygon_from_native(z.GetFilledPolysList(p.B_Cu)))for z in b.Zones()if not z.GetIsRuleArea()and z.IsOnLayer(p.B_Cu)and z.GetNetname()!=net and z.GetFilledPolysList(p.B_Cu).OutlineCount()]
rows=[]
for x,y in endpoints:
 t=probe;t.SetPosition(p.VECTOR2I_MM(x,y))
 hits=[]
 for o in objects:
  if not o.IsOnLayer(p.B_Cu)or o.GetNetname()==net:continue
  if o.GetEffectiveShape(p.B_Cu).Collide(t.GetEffectiveShape(p.B_Cu),max(200000,int(gap(o,p.B_Cu)))):
   row=dict(uuid=f._uid(o),kind=o.GetClass(),net=o.GetNetname())
   if o.GetClass()=='PAD':row.update(ref=o.GetParentFootprint().GetReference(),pad=o.GetNumber())
   else:row.update(at_mm=[o.GetPosition().x/1e6,o.GetPosition().y/1e6])
   hits.append(row)
 rect=box(x-width/2e6,y-width/2e6,x+width/2e6,y+width/2e6).buffer(.2)
 zone_hits=[dict(uuid=f._uid(z),net=z.GetNetname(),area_mm2=rect.intersection(g).area)for z,g in zones if rect.intersects(g)]
 rows.append(dict(at_mm=[x,y],face='B.Cu',square_land_mm=width/1e6,foreign_native_contacts=hits,saved_fill_clearance_hits=zone_hits,
  rule_hits=f._native_track_rule_hits(b,t.GetEffectiveShape(p.B_Cu),p.B_Cu)))
trunks=[]
for o in b.GetTracks():
 if o.GetClass()=='PCB_TRACK'and o.GetWidth()>=3000000:
  a,z=o.GetStart(),o.GetEnd()
  if min(a.x,z.x)-o.GetWidth()/2<2500000 or max(a.y,z.y)+o.GetWidth()/2>85000000:
   trunks.append(dict(uuid=f._uid(o),net=o.GetNetname(),layer=b.GetLayerName(o.GetLayer()),width_mm=o.GetWidth()/1e6,start_mm=[a.x/1e6,a.y/1e6],end_mm=[z.x/1e6,z.y/1e6]))
out=dict(source=str(S),source_sha256=f._hash(S),endpoint_screen=rows,outline_adjacent_wide_tracks=trunks,
 scope='Finite native BCu endpoint contact screen only; source saved fills/body/paired/tail/current transport require separate proofs. No native save.')
(Path(__file__).parent/'native-inventory.json').write_text(json.dumps(out,indent=2)+'\n')
for r in rows:print(r['at_mm'],[(h.get('ref'),h['net'],h['uuid'])for h in r['foreign_native_contacts']],r['rule_hits'])
print('TRUNKS',json.dumps(trunks))
