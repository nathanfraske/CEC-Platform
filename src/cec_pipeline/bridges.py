"""Source-bound, read-only trials of real raised SMT conductor bridges.

The agent chooses the part and each placement. This is a rejection/measurement
tool, not a router, electrical model, thermal certificate or PCB constructor.
The metal span is NEVER added to PCB copper, zone fills or connectivity.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from .geometry import point
from .identity import require
from .legacy import bootstrap
from .native import _native

bootstrap()
import cec_assembly_envelope as assembly
import cec_suite_inspection as inspection


def part_geometry(part):
    require(type(part) is dict and set(part)=={
        'schema','id','manufacturer','drawing','mount','pitch_nm','body_length_nm',
        'body_width_nm','land_length_nm','land_width_nm','height_nm','underside_nm',
        'catalog_current_a','dimensions_basis'}, 'exact_bridge_part_fields_required')
    require(type(part['schema']) is int and part['schema']==1
            and part['mount']=='raised_smt' and part['dimensions_basis']=='nominal_only',
            'nominal_raised_smt_bridge_profile_required')
    require(all(type(part[k]) is str and part[k].strip()
                for k in ('id','manufacturer','drawing')), 'evidenced_bridge_identity_required')
    require(all(type(part[k]) is int and 0<part[k]<=100_000_000
                for k in ('pitch_nm','body_length_nm','body_width_nm',
                          'land_length_nm','land_width_nm','height_nm','underside_nm')),
            'bounded_positive_integer_bridge_dimensions_required')
    require(part['land_length_nm']<part['pitch_nm']<=part['body_length_nm']
            and part['underside_nm']<part['height_nm'], 'consistent_bridge_geometry_required')
    rating=part['catalog_current_a']
    require(type(rating) in (int,float) and math.isfinite(rating) and 0<rating<=1000,
            'finite_positive_catalog_rating_required')
    return part


def placed_shapes(part, candidate):
    from shapely.geometry import Polygon
    part_geometry(part)
    require(type(candidate) is dict and set(candidate)=={'id','ends_nm','face'},
            'exact_bridge_placement_fields_required')
    require(type(candidate['id']) is str and 0<len(candidate['id'])<=80
            and candidate['face'] in ('F.Cu','B.Cu'), 'named_surface_bridge_placement_required')
    ends=candidate['ends_nm']
    require(type(ends) is list and len(ends)==2, 'two_explicit_bridge_feet_required')
    a,b=[point(p) for p in ends];dx,dy=b[0]-a[0],b[1]-a[1]
    require((dx==0) != (dy==0) and abs(dx)+abs(dy)==part['pitch_nm'],
            'exact_cardinal_manufacturer_bridge_pitch_required')
    ux,uy=dx/part['pitch_nm'],dy/part['pitch_nm']
    def rect(center,length,width):
        return Polygon([((center[0]+sx*ux*length/2-sy*uy*width/2)/1e6,
                         (center[1]+sx*uy*length/2+sy*ux*width/2)/1e6)
                        for sx,sy in ((-1,-1),(1,-1),(1,1),(-1,1))])
    body=rect([(x+y)/2 for x,y in zip(a,b)],part['body_length_nm'],part['body_width_nm'])
    lands=[rect(p,part['land_length_nm'],part['land_width_nm']) for p in (a,b)]
    return body,lands


def rating_screen(part, authority):
    """Preserve the source's conductor margin; catalog pass is not qualification."""
    part_geometry(part)
    require(type(authority) is dict and all(type(authority.get(k)) in (int,float)
            and math.isfinite(authority[k]) and authority[k]>0
            for k in ('amps','geometry_margin'))
            and authority['geometry_margin']>=1
            and type(authority.get('margin_included')) is bool
            and (not authority['margin_included'] or authority['geometry_margin']==1),
            'positive_unchanged_source_current_authority_required')
    required=authority['amps']*authority['geometry_margin']
    return dict(source_current_a=authority['amps'],source_margin=authority['geometry_margin'],
                required_conductor_current_a=required,catalog_current_a=part['catalog_current_a'],
                catalog_rating_sufficient=part['catalog_current_a']>=required,
                thermal_environment_and_joints_qualified=False,sharing_assumed=False)


def screen_native(board, part, candidate, *, net, clearance, mechanical_margin_nm, deadline):
    """Real lands/fills/holes, not track centerlines or a uniform stack gap."""
    body,lands=placed_shapes(part,candidate)
    result,data=screen_geometry(board,body,lands,candidate,net=net,clearance=clearance,
        mechanical_margin_nm=mechanical_margin_nm,deadline=deadline)
    result.update(nominal_height_mm=part['height_nm']/1e6,
                  nominal_underside_mm=part['underside_nm']/1e6)
    return result,data


def screen_geometry(board, body, lands, candidate, *, net, clearance,
                    mechanical_margin_nm, deadline):
    """Shared rejection checks for supplied real land and body polygons."""
    from shapely.geometry import box, mapping
    pcbnew,quiet=_native()
    require(1<=len(lands)<=2 and all(s.is_valid and not s.is_empty for s in [body,*lands]),
            'valid_bounded_conductor_polygons_required')
    face={'F.Cu':pcbnew.F_Cu,'B.Cu':pcbnew.B_Cu}[candidate['face']]
    require(type(mechanical_margin_nm) is int and 0<mechanical_margin_nm<=5_000_000,
            'explicit_positive_bounded_mechanical_margin_required')
    margin=mechanical_margin_nm/1e6
    fps=list(board.GetFootprints());tracks=list(board.GetTracks());zones=list(board.Zones())
    pads=[p for f in fps for p in f.Pads()]
    require(len(fps)<=4096 and len(tracks)<=16384 and len(zones)<=256 and len(pads)<=32768,
            'bounded_native_bridge_inventory_required')
    gaps={str(i.GetNetname()):clearance(str(i.GetNetname())) for i in [*pads,*tracks,*zones]}
    require(all(type(g) in (int,float) and math.isfinite(g) and 0<=g<=100_000_000
                for g in gaps.values()),'finite_bounded_source_land_clearance_required')
    gaps={n:g/1e6 for n,g in gaps.items()}
    hole_gap=max(0,board.GetDesignSettings().m_HoleClearance)/1e6
    area=body
    for land in lands:area=area.union(land)
    radius=max(margin,hole_gap,max(gaps.values(),default=0),2.0)
    left,top,right,bottom=area.bounds
    # A polygonized circular buffer is inscribed between arc vertices. Use
    # an expanded box for conservative broadphase, exact distance afterward.
    near=box(left-radius,top-radius,right+radius,bottom+radius)
    def tick(): require(time.monotonic()<deadline,'bridge_screen_time_budget_exceeded')
    def local(item):
        b=item.GetBoundingBox()
        return near.intersects(box(b.GetLeft()/1e6,b.GetTop()/1e6,
                                   b.GetRight()/1e6,b.GetBottom()/1e6))
    def polygon(item,hole=False):
        tick();poly=pcbnew.SHAPE_POLY_SET()
        if hole:item.GetEffectiveHoleShape().TransformToPolygon(poly,1,pcbnew.ERROR_OUTSIDE)
        else:item.TransformShapeToPolygon(poly,face,0,1,pcbnew.ERROR_OUTSIDE,False)
        result=assembly.polygon_from_native(poly)
        require(not result.is_empty and result.is_valid,'valid_native_bridge_obstacle_required')
        return result
    def ident(item):
        row=dict(uuid=str(item.m_Uuid.AsString()),kind=item.GetClass(),net=str(item.GetNetname()))
        if item.GetClass()=='PAD':row.update(reference=item.GetParentFootprint().GetReference(),pin=item.GetNumber())
        return row
    conflicts=[];contacts=[[] for _ in lands];holes=[];bodies=[];missing=[];copper=[];drills=[]
    def check_hole(item,protruding_lead):
        shape=polygon(item,True);gap=body.distance(shape);drills.append(shape)
        if protruding_lead and (gap<margin or body.intersects(shape)):
            holes.append(dict(**ident(item),body_gap_mm=gap,
                              nominal_body_projection_overlap=body.intersects(shape),
                              protrusion_height_known=False))
        for i,land in enumerate(lands):
            if land.intersects(shape) or land.distance(shape)<hole_gap:
                conflicts.append(dict(**ident(item),foot=i+1,kind_of_conflict='drill_under_smt_land',
                                      measured_gap_mm=land.distance(shape),required_gap_mm=hole_gap))
    def check_copper(item,shape):
        row=ident(item);copper.append((shape,row))
        gap=gaps[row['net']]
        for i,land in enumerate(lands):
            if row['net']==net:
                if land.intersection(shape).area>0:contacts[i].append(row)
            elif land.intersects(shape) or land.distance(shape)<gap:
                conflicts.append(dict(**row,foot=i+1,kind_of_conflict='other_net_land_clearance',
                                      measured_gap_mm=land.distance(shape),required_gap_mm=gap))
    for fp in fps:
        tick()
        if fp.GetLayer()==face and local(fp):
            try:shape,basis=assembly.footprint_planar_envelope(fp)
            except ValueError as exc:missing.append(dict(reference=fp.GetReference(),reason=str(exc)))
            else:
                if area.distance(shape)<margin or area.intersects(shape):
                    bodies.append(dict(reference=fp.GetReference(),basis=basis,
                                       measured_gap_mm=area.distance(shape)))
        for pad in fp.Pads():
            if not local(pad):continue
            if pad.HasHole():
                # A hole bounds a potential protruding lead, NOT its assembled
                # height or solder envelope. Same-net leads can collide too.
                check_hole(pad,True)
            if pad.IsOnLayer(face) and pad.GetAttribute()!=pcbnew.PAD_ATTRIB_NPTH:
                check_copper(pad,polygon(pad))
    for track in tracks:
        tick()
        if track.IsOnLayer(face) and local(track):
            check_copper(track,polygon(track))
            if track.GetClass()=='PCB_VIA':check_hole(track,False)
    for zone in zones:
        tick()
        if not zone.IsOnLayer(face):continue
        if zone.GetIsRuleArea():
            shape=assembly.polygon_from_native(zone.Outline())
            if zone.GetDoNotAllowFootprints() and area.intersects(shape):
                missing.append(dict(uuid=str(zone.m_Uuid.AsString()),reason='body_intersects_component_keepout'))
            elif any(land.intersects(shape) for land in lands):
                missing.append(dict(uuid=str(zone.m_Uuid.AsString()),reason='land_intersects_rule_area'))
        elif not zone.IsFilled() or not zone.HasFilledPolysForLayer(face):
            missing.append(dict(uuid=str(zone.m_Uuid.AsString()),reason='saved_fill_missing'))
        else:
            shape=assembly.polygon_from_native(zone.GetFilledPolysList(face))
            if shape.intersects(near):check_copper(zone,shape)
    # Decorative copper/text is not silently treated as a routable blank.
    for item in [*board.GetDrawings(),*(g for f in fps for g in f.GraphicalItems())]:
        tick()
        if item.GetLayer()==face and local(item):
            missing.append(dict(uuid=str(item.m_Uuid.AsString()),reason='local_copper_graphic_requires_review'))
    outline=pcbnew.SHAPE_POLY_SET()
    require(board.GetBoardPolygonOutlines(outline,False),'native_bridge_board_outline_required')
    substrate=assembly.polygon_from_native(outline)
    edge=max(0,board.GetDesignSettings().m_CopperEdgeClearance)/1e6
    inside=substrate.covers(body) and all(substrate.buffer(-edge).covers(land) for land in lands)
    tick()
    result=dict(id=candidate['id'],face=candidate['face'],
                land_conflicts=conflicts,same_net_land_contacts=contacts,
                source_copper_touches_both_feet=all(contacts),
                nearby_holes_or_leads=holes,same_face_body_reservations=bodies,unknown=missing,
                body_and_lands_inside_board=inside,
                land_clearance_screen_ok=not conflicts and not missing and inside,
                nominal_mechanical_screen_ok=not holes and not bodies and not missing and inside,
                mechanical_allocation_mm=margin,
                scope='base/netclass land-clearance and nominal mechanical rejection screen',
                custom_rule_DRC_run=False,lead_geometry_basis='native drill envelopes; solder unknown',
                mechanical_fit_qualified=False,added_assembly_height_known=False,
                current_connection_qualified=False,release_authority=False)
    if 'ends_nm' in candidate:result['ends_nm']=candidate['ends_nm']
    data=dict(body=mapping(body),lands=[mapping(s) for s in lands],
              copper=[dict(shape=mapping(s.intersection(near)),**row) for s,row in copper],
              drills=[mapping(s) for s in drills],
              bounds=list(near.bounds))
    return result,data


def preview(request):
    require(type(request) is dict and set(request)=={
        'schema','source','board_hint','part','source_track_uuid','mechanical_margin_nm','candidates'}
        and type(request['schema']) is int and request['schema']==1,'exact_bridge_preview_request_required')
    start=time.monotonic();paths=[]
    for key in ('source','part'):
        row=request[key]
        require(type(row) is dict and set(row)=={'path','sha256'},'source_bound_bridge_input_required')
        path=Path(row['path']).resolve(strict=True)
        require(path.is_file() and path.stat().st_size<=32*1024*1024
                and inspection.sha(path)==row['sha256'],'bridge_source_identity_mismatch')
        paths.append(path)
    part=part_geometry(json.loads(paths[1].read_text()))
    candidates=request['candidates']
    require(type(candidates) is list and 1<=len(candidates)<=8,'bounded_explicit_bridge_candidates_required')
    for candidate in candidates:placed_shapes(part,candidate)
    require(len({c['id'] for c in candidates})==len(candidates),'unique_bridge_candidate_ids_required')
    pcbnew,quiet=_native();board=pcbnew.LoadBoard(str(paths[0]))
    tracks={str(t.m_Uuid.AsString()):t for t in board.GetTracks()}
    require(type(request['source_track_uuid']) is str and request['source_track_uuid'] in tracks,
            'existing_current_domain_track_required')
    require(type(request['board_hint']) is str and request['board_hint'],'explicit_source_board_hint_required')
    net=str(tracks[request['source_track_uuid']].GetNetname())
    import cec_full_current_planar_reflow as authority
    import cec_force_current as force
    import cec_fr as fr
    family=force._family(paths[0],request['board_hint'])
    kind,domain,contract=authority._model(board,paths[0],net,request['board_hint'])
    rating=rating_screen(part,contract['current_authority'])
    resolver=fr._project_netclass_resolver(str(paths[0]),board=board)
    def clearance(other):
        return max(board.GetDesignSettings().m_MinClearance,
                   *[round(float((resolver(n) or {}).get('clearance') or 0)*1e6) for n in (net,other)])
    results=[];data=[]
    for candidate in candidates:
        row,view=screen_native(board,part,candidate,net=net,clearance=clearance,
                              mechanical_margin_nm=request['mechanical_margin_nm'],deadline=start+9)
        results.append(row);data.append(view)
    require(family==force._family(paths[0],request['board_hint'])
            and inspection.sha(paths[1])==request['part']['sha256'], 'bridge_inputs_changed_during_preview')
    require(time.monotonic()-start<9,'bridge_preview_time_budget_exceeded')
    result=dict(schema=1,source=request['source'],source_family=family,part=request['part'],
        part_id=part['id'],net=net,current_domain_kind=kind,source_current_contract=contract,
        rating=rating,candidates=results,source_unchanged=True,pcb_files_modified=False,
        routing_admitted=False,span_added_to_pcb_copper=False,BOM_changed=False,
        electrical_or_current_qualified=False,release_authority=False,
        outstanding=['source-owned force connections and Kelvin-safe partition',
                     'real two-terminal schematic/BOM and assembly conductor model',
                     'component tolerances, solder/lead envelopes and assembled Z',
                     'pad/joint ampacity and full thermal/current receiving',
                     'whole-board native DRC, saved fills and routed placement receiving',
                     'assembled cost, supply availability and measured footprint benefit'])
    return result,data


def plot(result,data,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch as Key
    from shapely.geometry import shape
    fig,axes=plt.subplots(1,len(data),figsize=(5*len(data),8),squeeze=False)
    for ax,row,view in zip(axes[0],result['candidates'],data):
        def draw(raw,color,alpha=1,outline=False):
            g=shape(raw)
            for p in ([g] if g.geom_type=='Polygon' else getattr(g,'geoms',[])):
                if p.geom_type!='Polygon' or p.is_empty:continue
                # Compound paths preserve saved zone and annular holes rather
                # than painting fictional copper across them.
                from matplotlib.path import Path as MplPath
                from matplotlib.patches import PathPatch
                from shapely.geometry.polygon import orient
                p=orient(p,sign=1.0);verts=[];codes=[]
                for ring in [p.exterior,*p.interiors]:
                    coords=list(ring.coords);verts.extend(coords)
                    codes.extend([MplPath.MOVETO]+[MplPath.LINETO]*(len(coords)-2)+[MplPath.CLOSEPOLY])
                ax.add_patch(PathPatch(MplPath(verts,codes),facecolor='none' if outline else color,
                                       edgecolor=color,linewidth=.8,alpha=alpha))
        ax.set_facecolor('#f7faf8')
        for item in view['copper']:draw(item['shape'],'#388167' if item['net']==result['net'] else '#bccac5',.8)
        for raw in view['drills']:draw(raw,'#f7faf8')
        draw(view['body'],'#d46a16',.75,True)
        for raw in view['lands']:draw(raw,'#d46a16',.55)
        left,top,right,bottom=view['bounds']
        ax.set_xlim(left-1,right+1);ax.set_ylim(bottom+1,top-1);ax.set_aspect('equal')
        ax.set_title(row['id']+'\n'+row['face']+' / nominal placement ONLY',fontsize=10)
        ax.set_xlabel('Native x (mm)');ax.set_ylabel('Native y (mm)')
        ax.text(.02,.02,'%d land conflicts\n%d nearby holes/leads' % (
            len(row['land_conflicts']),len(row['nearby_holes_or_leads'])),
            transform=ax.transAxes,fontsize=9,bbox=dict(facecolor='white',alpha=.9))
    fig.suptitle(result['part_id']+' — real copper retained; nominal bridge study\n'
                 +'Source '+result['source']['sha256'][:16]+' / no PCB change',fontsize=12)
    fig.legend(handles=[Key(color='#388167',label='Source power copper'),
                        Key(color='#bccac5',label='Other source copper'),
                        Key(facecolor='none',edgecolor='#d46a16',label='Proposed raised metal; NOT PCB copper')],
               loc='lower center',ncol=1)
    fig.tight_layout(rect=(0,.12,1,.95));fig.savefig(output,dpi=160);plt.close(fig)


def outputs(request_path,request,report,image=None):
    import cec_force_current as force
    protected=force._protected_paths(request['source']['path'],request['board_hint'])
    protected|={str(Path(p).resolve()) for p in (request_path,request['part']['path'])}
    targets=[Path(report).resolve()]+([] if image is None else [Path(image).resolve()])
    for path,ext in zip(targets,('.json','.png')):
        require(path.suffix==ext,'bridge_preview_output_format_required')
        force._check_output(path,protected)
        for other in [p for p in targets if p is not path]:
            require(path!=other and not(path.exists() and other.exists() and path.samefile(other)),
                    'bridge_outputs_must_not_alias_inputs_or_each_other')
    return targets


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--plot');args=parser.parse_args()
    request=json.loads(Path(args.request).read_text())
    paths=outputs(args.request,request,args.output,args.plot)
    result,data=preview(request);inspection.write_json(paths[0],result)
    if args.plot:plot(result,data,paths[1])
    print(json.dumps(dict(candidates=len(result['candidates']),rating=result['rating'],
                         source_unchanged=True,routing_admitted=False)))


if __name__=='__main__':main()
