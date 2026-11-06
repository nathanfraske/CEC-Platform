"""Read-only, source-bound paired placement previews; never a routed candidate.

The frontier model supplies every pose. This module measures that proposal;
it neither searches placements nor saves a modified PCB or selects a parent.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from .cells import normalize_poses
from .identity import require
from .legacy import bootstrap
from .native import _native

bootstrap()
import cec_assembly_envelope as assembly
import cec_suite_inspection as inspection


def _same_face(board, moved, planar):
    rows=[];missing=[];fallback=[]
    for fp in board.GetFootprints():
        try:
            shape,basis=assembly.footprint_planar_envelope(fp)
        except ValueError as exc:
            # Only a source-contract zero-height feature can omit a body.
            # Its copper, hole and edge clearances remain entirely unchecked.
            if str(fp.GetFPID().GetLibItemName()) not in planar:
                missing.append(dict(reference=fp.GetReference(),reason=str(exc)))
            continue
        if basis!='native_courtyard':fallback.append(fp.GetReference())
        rows.append((fp.GetReference(),fp.GetLayer(),shape))
    conflicts=[]
    for i,(ref,face,shape) in enumerate(rows):
        for other,other_face,other_shape in rows[i+1:]:
            if face!=other_face or not ({ref,other}&moved):continue
            if shape.intersects(other_shape):
                conflicts.append(dict(references=sorted((ref,other)),
                    overlap_area_mm2=shape.intersection(other_shape).area))
    return dict(ok=not missing and not conflicts,complete=not missing,
                conflicts=conflicts,missing=missing,fallback_references=fallback,
                scope='moved-owner planar envelope screening only')


def _edge_exits(boards,data,ports):
    """Check declared connector mouths, not just body fit or pin-row proximity.

    Numbered pads define the row's frame, so rotation preserves pinout. Mouth
    dimensions/direction require package evidence; cable/tool envelopes are
    separate obligations. Holes cannot masquerade as the external perimeter.
    """
    from shapely.geometry import Polygon, shape
    require(type(ports) is list and len(ports)<=16,'bounded_edge_port_scope_required')
    results=[];seen=set()
    fields={'side','reference','footprint','pad_pair','exit_normal',
            'mouth_offset_nm','mouth_width_nm','allowed_edges','evidence'}
    for port in ports:
        require(type(port) is dict and set(port)==fields,'exact_edge_port_fields_required')
        side,ref=port['side'],port['reference']
        require(side in ('carrier','cover') and type(ref) is str and ref,
                'edge_port_identity_required')
        require((side,ref) not in seen,'unique_edge_port_scope_required');seen.add((side,ref))
        idx=0 if side=='carrier' else 1;board=boards[idx]
        fp=board.FindFootprintByReference(ref)
        require(fp is not None and str(fp.GetFPID().GetLibItemName())==port['footprint']
                and board.GetLayerName(fp.GetLayer())=='F.Cu','declared_front_port_package_required')
        pair=port['pad_pair']
        require(type(pair) is list and len(pair)==2 and all(type(n) is str and n for n in pair)
                and pair[0]!=pair[1],'numbered_edge_port_row_required')
        pads=[]
        for number in pair:
            matches=[p for p in fp.Pads() if p.GetNumber()==number]
            require(len(matches)==1,'unique_edge_port_pad_required')
            pads.append(matches[0].GetPosition())
        dx,dy=pads[1].x-pads[0].x,pads[1].y-pads[0].y
        require((dx==0) != (dy==0),'cardinal_edge_port_row_required')
        length=math.hypot(dx,dy);row=(dx/length,dy/length)
        require(port['exit_normal'] in ('left','right'),'edge_port_normal_required')
        sign=1 if port['exit_normal']=='left' else -1
        normal=(-row[1]*sign,row[0]*sign)
        edge={(-1.,0.):'left',(1.,0.):'right',(0.,-1.):'top',(0.,1.):'bottom'}[normal]
        allowed=port['allowed_edges']
        require(type(allowed) is list and 1<=len(allowed)<=4
                and all(type(e) is str and e in ('left','right','top','bottom') for e in allowed)
                and len(set(allowed))==len(allowed),'explicit_allowed_port_edges_required')
        require(all(type(port[k]) is int and 0<port[k]<=100_000_000
                    for k in ('mouth_offset_nm','mouth_width_nm'))
                and type(port['evidence']) is str and port['evidence'],
                'evidenced_bounded_port_dimensions_required')
        center=[(pads[0].x+pads[1].x)/2e6,(pads[0].y+pads[1].y)/2e6]
        center=[v+n*port['mouth_offset_nm']/1e6 for v,n in zip(center,normal)]
        half=port['mouth_width_nm']/2e6
        ends=[[v+s*r*half for v,r in zip(center,row)] for s in (-1,1)]
        outline=shape(data[idx]['outline']);outer=Polygon(outline.exterior)
        bounds=outer.bounds;reach=math.hypot(bounds[2]-bounds[0],bounds[3]-bounds[1])*2
        far=[[v+n*reach for v,n in zip(p,normal)] for p in ends]
        corridor=Polygon([ends[0],ends[1],far[1],far[0]])
        # One native nanometre permits a mouth exactly on Edge.Cuts.
        exits=not corridor.intersects(outer.buffer(-.000001))
        results.append(dict(side=side,reference=ref,edge=edge,mouth_center_mm=center,
                            opening_line_mm=ends,outward=[*normal],allowed=edge in allowed,
                            exits_external_perimeter=exits,ok=exits and edge in allowed,
                            scope='declared mouth direction and unobstructed laminate exit only',
                            cable_and_tool_access_qualified=False))
    return results


def preview(request):
    require(type(request) is dict
            and {'schema','carrier','cover','contract'}<=set(request)
            and set(request)<={'schema','carrier','cover','contract','edge_ports'}
            and type(request['schema']) is int and request['schema']==1,
            'exact_paired_preview_request_required')
    start=time.monotonic()
    source_rows=[request['carrier'],request['cover'],request['contract']]
    paths=[];hashes=[]
    for i,row in enumerate(source_rows):
        require(type(row) is dict and set(row)==({'path','sha256','poses'} if i<2 else {'path','sha256'}),
                'exact_source_bound_preview_inputs_required')
        path=Path(row['path']).resolve(strict=True)
        require(path.is_file() and path.stat().st_size<=32*1024*1024,
                'bounded_preview_source_file_required')
        require(inspection.sha(path)==row['sha256'],'preview_source_identity_mismatch')
        paths.append(path);hashes.append(row['sha256'])
    require(paths[0]!=paths[1],'distinct_native_boards_required')
    contract=json.loads(paths[2].read_text())
    require(all(type(row['poses']) is list for row in source_rows[:2]),
            'explicit_preview_pose_lists_required')
    poses=[normalize_poses(row['poses']) if row['poses'] else {} for row in source_rows[:2]]
    require(any(poses),'explicit_preview_motion_required')
    pcbnew,quiet=_native()
    boards=[pcbnew.LoadBoard(str(p)) for p in paths[:2]]
    before,data_before=assembly.evaluate_boards(*boards,contract)
    edge_before=_edge_exits(boards,data_before,request.get('edge_ports',[]))
    prepared=[];moved=[set(),set()]
    for i,(board,targets) in enumerate(zip(boards,poses)):
        fps=list(board.GetFootprints());index={fp.GetReference():fp for fp in fps}
        require(len(index)==len(fps) and targets.keys()<=index.keys(),
                'unique_existing_preview_references_required')
        for ref,(x,y,turn) in targets.items():
            fp=index[ref];old=fp.GetPosition();old_turn=fp.GetOrientationDegrees()
            require(max(abs(x-old.x/1e6),abs(y-old.y/1e6))<=64,
                    'bounded_preview_translation_required')
            if (old.x,old.y)!=(round(x*1e6),round(y*1e6)) or (old_turn-turn)%360:
                moved[i].add(ref)
            prepared.append((i,fp,[round(x*1e6),round(y*1e6)],turn,
                             dict(reference=ref,uuid=str(fp.m_Uuid.AsString()),
                                  source_at_nm=[old.x,old.y],target_at_nm=[round(x*1e6),round(y*1e6)],
                                  source_rotation_deg=old_turn,target_rotation_deg=turn,
                                  locked=bool(fp.IsLocked()))))
    require(any(moved),'preview_requires_actual_pose_change')
    # Source files remain immutable. Only these private in-memory copies move.
    for i,fp,point,turn,_ in prepared:
        fp.SetOrientationDegrees(turn);fp.SetPosition(pcbnew.VECTOR2I(*point))
    after,data_after=assembly.evaluate_boards(*boards,contract)
    edge_after=_edge_exits(boards,data_after,request.get('edge_ports',[]))
    spec=dict(contract.get('envelopes',{}))
    for group in contract.get('envelope_groups',[]):
        for key in group['footprints']:spec[key]=group
    planar={key for key,row in spec.items() if row.get('height_max_mm')==0}
    same=[_same_face(b,refs,planar) for b,refs in zip(boards,moved)]
    require([inspection.sha(p) for p in paths]==hashes,'preview_source_changed_during_measurement')
    require(time.monotonic()-start<9.0,'paired_preview_time_budget_exceeded')
    result=dict(schema=1,source_unchanged=True,
        sources=[dict(path=str(p),sha256=h) for p,h in zip(paths,hashes)],
        moves={side:[row for i,_,_,_,row in prepared if i==idx]
               for idx,side in enumerate(('carrier','cover'))},
        before=before,after=after,same_face=same,
        edge_ports=dict(before=edge_before,after=edge_after),
        placement_screen_ok=after['ok'] and all(r['ok'] for r in same+edge_after),
        source_assembly_screen_ok=before['ok'],
        routing_admitted=False,pcb_files_modified=False,BOM_changed=False,
        native_DRC_run=False,electrical_or_current_qualified=False,release_authority=False,
        outstanding=['rated route and saved-fill reconstruction','pad and drill clearances',
                     'same-board keepouts and edge clearance','source-owned bypass and return paths',
                     'full current and Kelvin receiving','paired native DRC and opens',
                     'connector access and physical samples'])
    return result,dict(before=data_before,after=data_after,transform=contract['transform'],
                       moved=[sorted(refs) for refs in moved],
                       edge_ports=[edge_before,edge_after],
                       dimensions=[r['projected_dimensions'] for r in (before,after)])


def plot(data,output):
    """Actual declared envelope polygons; no invented copper or routed preview."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as Patch, Patch as Key
    from shapely.geometry import shape
    from shapely import affinity
    fig,axes=plt.subplots(1,2,figsize=(12,7.5),sharex=True,sharey=True)
    colors=['#2869ae','#d68c23']
    all_bounds=[]
    for ax,title,boards,dimensions,ports in zip(axes,['Source placement','Proposed placement — NOT routed'],
                               [data['before'],data['after']],data['dimensions'],data['edge_ports']):
        for side,board in enumerate(boards):
            def posed(raw):
                g=shape(raw)
                return affinity.affine_transform(g,data['transform']) if side else g
            outline=posed(board['outline'])
            all_bounds.append(outline.bounds)
            ax.plot(*outline.exterior.xy,color=colors[side],linewidth=1.5,linestyle='--')
            for row in board['bodies']:
                if not row['height_max_mm']:continue
                g=posed(row['xy']);polys=[g] if g.geom_type=='Polygon' else list(g.geoms)
                all_bounds.append(g.bounds)
                moved=row['ref'] in data['moved'][side]
                for poly in polys:
                    ax.add_patch(Patch(list(poly.exterior.coords),facecolor=colors[side],
                                      edgecolor=colors[side],alpha=.55 if moved else .12,
                                      linewidth=1.2 if moved else .5))
                if (moved and g.area>8) or g.area>150:
                    c=g.centroid;ax.text(c.x,c.y,('C:' if side==0 else 'V:')+row['ref'],
                                        ha='center',va='center',fontsize=6)
        from shapely.geometry import Point
        for port in ports:
            start=Point(port['mouth_center_mm'])
            end=Point([v+4*n for v,n in zip(port['mouth_center_mm'],port['outward'])])
            if port['side']=='cover':
                start=affinity.affine_transform(start,data['transform'])
                end=affinity.affine_transform(end,data['transform'])
            ax.annotate('',xy=(end.x,end.y),xytext=(start.x,start.y),
                        arrowprops=dict(arrowstyle='->',color='#167b50' if port['ok'] else '#b44332',lw=2))
        dims=dimensions['declared_body_plus_laminate']
        size='Body envelope unknown' if dims is None else 'XY envelope: %.2f × %.2f mm' % tuple(dims['size_mm'])
        ax.set_aspect('equal');ax.set_title(title+'\n'+size);ax.set_xlabel('Carrier-frame x (mm)')
        ax.grid(alpha=.12)
    left=min(b[0] for b in all_bounds);top=min(b[1] for b in all_bounds)
    right=max(b[2] for b in all_bounds);bottom=max(b[3] for b in all_bounds)
    pad=max(right-left,bottom-top)*.04
    axes[0].set_xlim(left-pad,right+pad);axes[0].set_ylim(bottom+pad,top-pad)
    axes[0].set_ylabel('Carrier-frame y (mm)')
    fig.legend(handles=[Key(color=c,alpha=.4,label=l) for c,l in zip(colors,['Carrier bodies (C)','Transformed cover bodies (V)'])],
               loc='lower center',ncol=2,bbox_to_anchor=(.5,.045))
    fig.suptitle('Matched-stack XY study — declared body/courtyard envelopes',fontsize=13)
    fig.text(.5,.012,'Placement preview only. Copper, routing and pad/drill clearances are NOT qualified.',
             ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.13,1,.96));fig.savefig(output,dpi=160);plt.close(fig)


def _outputs(request_path,request,output,plot_path=None):
    """Refuse input/source-family aliases before any report or image is written."""
    protected=[Path(request_path).resolve()]
    for side in ('carrier','cover','contract'):
        path=Path(request[side]['path']).resolve(strict=True)
        protected.append(path)
        if side!='contract':
            protected.extend(path.with_suffix(ext) for ext in
                             ('.kicad_pro','.kicad_dru','.kicad_sch','.kicad_prl'))
    targets=[Path(output).resolve()]
    if plot_path is not None:targets.append(Path(plot_path).resolve())
    for path,suffix in zip(targets,('.json','.png')):
        require(path.suffix==suffix,'preview_output_format_required')
        for source in protected:
            require(path!=source and not (path.exists() and source.exists() and path.samefile(source)),
                    'preview_output_must_not_replace_source')
    require(len(targets)==len(set(targets)),'distinct_preview_outputs_required')
    if len(targets)==2:
        require(not (all(p.exists() for p in targets) and targets[0].samefile(targets[1])),
                'distinct_preview_output_files_required')
    return targets


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--plot')
    args=parser.parse_args()
    request=json.loads(Path(args.request).read_text())
    targets=_outputs(args.request,request,args.output,args.plot)
    result,data=preview(request)
    inspection.write_json(targets[0],result)
    if args.plot:plot(data,targets[1])
    print(json.dumps({k:result[k] for k in ('placement_screen_ok','source_unchanged','routing_admitted','BOM_changed')}))


if __name__=='__main__':main()
