"""Read-only integer/rational diagnostic of the source vent/fill boundary."""
import sys,json,time
from pathlib import Path
from fractions import Fraction
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts')]
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
import cec_native_fill_geometry as fill
import cec_assembly_envelope as assembly
import cec_force_current as force
SOURCE=ROOT/'experiments/repack/j3-inward-20261105/typed-v10/carrier/board.kicad_pcb'
assert force._hash(SOURCE)=='27db3ea6947ce467587f454b3b719d123306b43397cd74c9ad985fc320d9dfa4'
b=pcbnew.LoadBoard(str(SOURCE));zones={str(z.m_Uuid.AsString()):z for z in b.Zones()}
guard=zones['cdb78967-3235-44b9-962b-6ce7aa574142'].Outline()
copper=zones['4298863e-593a-4614-93d4-b005e5fa434e'].GetFilledPolysList(pcbnew.F_Cu)
deadline=time.monotonic()+10
snapshot=lambda p:fill.snapshot(p,deadline,max_polygons=4096)
intersection=pcbnew.SHAPE_POLY_SET(copper);intersection.BooleanIntersection(guard)
reverse=pcbnew.SHAPE_POLY_SET(guard);reverse.BooleanIntersection(copper)
exact_area2=lambda ring:abs(sum(a[0]*z[1]-z[0]*a[1] for a,z in zip(ring,ring[1:]+ring[:1])))
rows=snapshot(intersection)
grows,crows=snapshot(guard),snapshot(copper)
from shapely.geometry import Polygon
from shapely.ops import unary_union
def integer_geometry(polys):return unary_union([Polygon(p[0],p[1:])for p in polys])
g,c=integer_geometry(grows),integer_geometry(crows)
floating=c.intersection(g)
result=dict(native_collide_copper_guard=bool(copper.Collide(guard,0)),native_collide_guard_copper=bool(guard.Collide(copper,0)),native_intersection_area_nm2=intersection.Area(),native_reverse_intersection_area_nm2=reverse.Area(),intersection_rings_nm=rows,integer_shoelace_area2_nm2=sum(exact_area2(p[0])-sum(exact_area2(h)for h in p[1:])for p in rows),shapely_integer_coordinate_intersection_area_nm2=floating.area,shapely_mm_intersection_area_mm2=assembly.polygon_from_native(copper).intersection(assembly.polygon_from_native(guard)).area,shapely_integer_valid=[c.is_valid,g.is_valid])
# Find the source boundary segments local to each native intersection point.
def dist2(point,a,z):
 dx,dy=z[0]-a[0],z[1]-a[1];px,py=point[0]-a[0],point[1]-a[1]
 t=max(Fraction(0),min(Fraction(1),Fraction(px*dx+py*dy,dx*dx+dy*dy)))
 return (Fraction(px)-t*dx)**2+(Fraction(py)-t*dy)**2
edges=lambda polys:[(a,z)for p in polys for r in p for a,z in zip(r,r[1:]+r[:1])if a!=z]
ge,ce=edges(grows),edges(crows)
witness=[]
for polygon in rows:
 for ring in polygon:
  for p in ring:
   near=lambda es:sorted(((dist2(p,*e),e)for e in es),key=lambda r:r[0])[:2]
   witness.append(dict(point_nm=p,guard_edges=[dict(distance_squared_nm2=str(d),edge_nm=e)for d,e in near(ge)],copper_edges=[dict(distance_squared_nm2=str(d),edge_nm=e)for d,e in near(ce)]))
result['witnesses']=witness
def cross(u,v):return u[0]*v[1]-u[1]*v[0]
sub=lambda p,q:(p[0]-q[0],p[1]-q[1])
A=(16881673,68261089);B=(17155304,68131671);C=(17084715,68165056);Q=(17055906,68183982)
t=Fraction(cross(sub(A,Q),sub(B,A)),cross(sub(C,Q),sub(B,A)))
I=tuple(Fraction(Q[j])+t*(C[j]-Q[j]) for j in (0,1));centroid=tuple((Fraction(B[j])+C[j]+I[j])/3 for j in (0,1))
def ring_class(r,p):
 inside=False
 for a,z in zip(r,r[1:]+r[:1]):
  if cross(sub(z,a),sub(p,a))==0 and min(a[0],z[0])<=p[0]<=max(a[0],z[0]) and min(a[1],z[1])<=p[1]<=max(a[1],z[1]):return 'boundary'
  if (a[1]>p[1])!=(z[1]>p[1]):
   xi=Fraction(a[0])+(p[1]-a[1])*Fraction(z[0]-a[0],z[1]-a[1])
   if xi>p[0]:inside=not inside
 return 'inside' if inside else 'outside'
def material_class(polys,p):
 for poly in polys:
  outer=ring_class(poly[0],p)
  if outer=='boundary':return 'boundary'
  if outer=='outside':continue
  holes=[ring_class(r,p) for r in poly[1:]]
  if 'boundary'in holes:return 'boundary'
  if 'inside'not in holes:return 'inside'
 return 'outside'
area2=abs(cross(sub(B,I),sub(C,I)))
result['exact_rational_witness']=dict(guard_edge_nm=[A,B],copper_boundary_vertices_nm=[Q,C,B],source_copper_vertex_guard_class=material_class(grows,C),source_copper_vertex_penetration_squared_nm2=str(dist2(C,A,B)),exact_crossing_point_nm=[str(v)for v in I],source_copper_edge_parameter=str(t),triangle_area_nm2=str(area2/2),triangle_area_nm2_decimal=float(area2/2),strict_common_interior_point_nm=[str(v)for v in centroid],guard_exact_winding_class=material_class(grows,centroid),copper_exact_winding_class=material_class(crows,centroid),interpretation='A positive-area rational triangle exists in both saved native polygons. Native clipping rounds intersection coordinates and reports a different sliver area; the collision is not merely floating overlay noise.')
out=ROOT/'experiments/repack/c37-vent-refresh-20261105/geometry-audit.json';out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='witnesses'},indent=2))
