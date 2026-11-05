"""Export full native-population clearance envelopes to a CadQuery STEP assembly.

Consumes cec_assembly_envelope JSON, without KiCad imports or board identities.
Run in the separate CAD environment; never replace vendor tolerance evidence
with the appearance of these explicitly labeled clearance solids.
"""
import argparse,hashlib,json,math
from pathlib import Path
import cadquery as cq


def polygons(geometry):
    if geometry['type']=='Polygon':return [geometry['coordinates']]
    if geometry['type']=='MultiPolygon':return geometry['coordinates']
    raise ValueError('polygon geometry required')


def prism(geometry,z,height):
    solids=[]
    for rings in polygons(geometry):
        outer=cq.Wire.makePolygon([cq.Vector(x,y,z) for x,y in rings[0][:-1]],close=True)
        inner=[cq.Wire.makePolygon([cq.Vector(x,y,z) for x,y in r[:-1]],close=True) for r in rings[1:]]
        solids.append(cq.Solid.extrudeLinear(outer,inner,cq.Vector(0,0,height)))
    return solids[0] if len(solids)==1 else cq.Compound.makeCompound(solids)


def drill_solid(row,thickness):
    x,y=row['xy'];sx,sy=row.get('size_mm',[row['diameter_mm']]*2)
    if abs(sx-sy)<1e-7:
        return cq.Solid.makeCylinder(sx/2,thickness+.02,cq.Vector(x,y,-thickness-.01))
    angle=-row.get('angle_degrees',0)+(90 if sy>sx else 0)
    return (cq.Workplane('XY').slot2D(max(sx,sy),min(sx,sy),angle)
            .extrude(thickness+.02).val().translate((x,y,-thickness-.01)))


def build(data):
    assembly=cq.Assembly(name='paired_clearance_envelopes')
    solids=[];contract=data['contract'];gap=sum(contract['gap_mm'])/2
    matrix=contract['transform']
    # Current interchange supports facing parallel boards with a Y-axis flip.
    # Refuse an unsupported transform instead of silently rotating it wrongly.
    if matrix[:4]!=[-1,0,0,1]:raise ValueError('CAD exporter requires the declared Y-axis face flip')
    def pose(s,side):
        return s if side==0 else s.rotate((0,0,0),(0,1,0),180).translate((matrix[4],matrix[5],gap))
    def add(s,name,side,color,kind):
        if not s.isValid():raise ValueError('invalid CAD solid: '+name)
        s=pose(s,side);name=name.replace('/','_')
        assembly.add(s,name=name,color=cq.Color(*color))
        solids.append(dict(shape=s,name=name,side=side,color=color,kind=kind))
    for side,board in enumerate(data['boards']):
        tag='carrier' if side==0 else 'cover'
        t=board['thickness_mm']
        laminate=prism(board['outline'],-t,t)
        cutters=[drill_solid(r,t) for r in board['holes']]
        if cutters:laminate=laminate.cut(cq.Compound.makeCompound(cutters))
        add(laminate,tag+'_PCB',side,(.09,.36,.25), 'laminate')
        for r in board['bodies']:
            if not r['height_max_mm']:continue
            height=r['height_max_mm'];z=0 if r['inward'] else -t-height
            body=prism(r['xy'],z,height)
            kind=r.get('kind','component')
            color=(.37,.43,.50)
            if kind=='reservoir':color=(.76,.60,.22)
            elif kind=='mating_header':color=(.84,.64,.24)
            elif kind=='mating_socket':
                color=(.14,.17,.21)
                # Open receiving channels so intentional mating interpenetration
                # is visible as pin insertion, not a solid-solid clash.
                cuts=[cq.Solid.makeBox(.9,.9,6.35,cq.Vector(x-.45,y-.45,height-6.35))
                      for x,y in r.get('drill_centres_mm',[])]
                if cuts:body=body.cut(cq.Compound.makeCompound(cuts))
            elif kind=='header_housing':color=(.14,.17,.21)
            add(body,tag+'_'+r['ref'],side,color,kind)
            if kind=='mating_socket':
                for n,(x,y) in enumerate(r.get('drill_centres_mm',[])):
                    tail=cq.Solid.makeBox(.635,.635,2.64,cq.Vector(x-.3175,y-.3175,-2.64))
                    add(tail,tag+'_'+r['ref']+'_tail_'+str(n),side,(.73,.73,.70),'tail')
    for index,h in enumerate(data['result'].get('hardware',[])):
        x,y=h['xy'];af=h['af_nominal_mm'];radius=af/math.sqrt(3)
        points=[(x+radius*math.cos(math.radians(30+60*i)),y+radius*math.sin(math.radians(30+60*i))) for i in range(6)]
        spacer=cq.Workplane('XY').polyline(points).close().extrude(gap).val()
        for z in (0,gap-5):spacer=spacer.cut(cq.Solid.makeCylinder(1,5,cq.Vector(x,y,z)))
        add(spacer,'support_'+str(index),0,(.72,.73,.76),'hardware')
        for side,z in ((0,-data['boards'][0]['thickness_mm']), (1,gap+data['boards'][1]['thickness_mm'])):
            hgt=h['head_height_mm'];start=z-hgt if side==0 else z
            head=cq.Solid.makeCylinder(h['head_diameter_mm']/2,hgt,cq.Vector(x,y,start))
            # World coordinates already applied to shared hardware.
            assembly.add(head,name=f'screw_head_{index}_{side}',color=cq.Color(.72,.73,.76))
            solids.append(dict(shape=head,name=f'screw_head_{index}_{side}',side=side,color=(.72,.73,.76),kind='hardware'))
    return assembly,solids


def render(solids,path,*,explode=0,side_view=False):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from matplotlib.patches import Patch
    fig=plt.figure(figsize=(13,9),facecolor='#f5f6f8');ax=fig.add_subplot(111,projection='3d')
    ax.set_facecolor('#f5f6f8')
    extents=[]
    for r in solids:
        bound=r['shape'].BoundingBox();lift=explode if r['side']==1 else 0
        extents.append((bound.xmin,bound.xmax,bound.ymin,bound.ymax,bound.zmin+lift,bound.zmax+lift))
        vertices,triangles=r['shape'].tessellate(.18,.3)
        points=[(v.x,v.y,v.z+(explode if r['side']==1 else 0)) for v in vertices]
        mesh=Poly3DCollection([[points[i] for i in tri] for tri in triangles],
            facecolors=r['color'],linewidths=0,alpha=.66 if r['kind']=='laminate' else 1,shade=True,lightsource=matplotlib.colors.LightSource(azdeg=300,altdeg=50))
        ax.add_collection3d(mesh)
    limits=[]
    for i in (0,2,4):
        lo=min(b[i] for b in extents);hi=max(b[i+1] for b in extents)
        margin=max((hi-lo)*.05,1);limits.append((lo-margin,hi+margin))
    ax.set(xlim=limits[0],ylim=limits[1],zlim=limits[2],xlabel='Assembly X (mm)',ylabel='Assembly Y (mm)',zlabel='Z (mm)')
    ax.set_box_aspect([hi-lo for lo,hi in limits]);ax.view_init(elev=5 if side_view else 24,azim=-105 if side_view else -58)
    ax.set_title('MATED STACK — declared face gap' if not explode else 'EXPLODED STACK — cover flipped about Y',pad=15,fontsize=17,fontweight='bold')
    fig.text(.08,.05,'Actual KiCad contours, holes and placements. Clearance envelopes, not detailed supplier models.\nGold: reservoirs / contacts • Grey: component envelopes • Green: laminate. Unrouted placement study.',fontsize=10,color='#364153')
    fig.subplots_adjust(left=0,right=1,bottom=.10,top=.92)
    fig.savefig(path,dpi=150,facecolor=fig.get_facecolor());plt.close(fig)


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    data=json.loads(Path(args.input).read_text());assembly,solids=build(data)
    assembly.save(str(out/'stack-envelopes.step'))
    render(solids,out/'stack-mated.png',side_view=True)
    render(solids,out/'stack-exploded.png',explode=28)
    summary=dict(cadquery_version=cq.__version__,valid_solids=len(solids),
        input_sha256=hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
        bodies_per_board=[len(b['bodies']) for b in data['boards']],
        source_boards=data['result']['sources'],physical_release=False,
        model_kind='complete native-population clearance envelopes, not detailed supplier solids')
    (out/'cad-model-receipt.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
