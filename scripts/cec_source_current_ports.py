"""Native Source current ports and explicit full-width connection evidence.

This is not a load model or saved-board admission. Callers independently
compile the original Source role/current/pose, preserve actual partitions
and receive every rule, current, reference, field and native DRC obligation.
Actual pads and barrels grant connectivity only, never capacity or sharing.
"""
import json
import math
from pathlib import Path
import time
import pcbnew
import cec_cell_escape_replan as escape
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_full_current_planar_reflow as full


def _left(deadline):
    left=deadline-time.monotonic()
    if left<=0:raise ValueError('source_current_port_deadline')
    return min(10.,left)


def _stable(value):return json.loads(json.dumps(value,sort_keys=True,allow_nan=False))


def port(pad):
    point=pad.GetPosition()
    faces=[int(l)for l in pad.GetLayerSet().CuStack()]
    if not faces or any(not pad.GetEffectiveShape(l).Collide(point,0)for l in faces):
        raise ValueError('exact_native_protector_port_axis_required')
    return dict(pad_uuid=force._uid(pad),at_nm=list(point),layers=faces)


def aggregate_ports(board,source,net,domain,contract,deadline):
    """Harvest exact retained full-width ports rooted in the rated Source.

    Do not force a new branch back to an inaccessible source-pad centre when
    actual rated copper on that SAME Source component is already available.
    Zones, undersized strokes and arbitrary same-net islands do not join this
    inventory. Existing through barrels are connectivity, never ampacity credit.
    """
    roots=[p for f in board.GetFootprints()for p in f.Pads()
        if f.GetReference()in set(domain['source_refs'])and p.GetNetname()==net]
    if not 1<=len(roots)<=16:raise ValueError('protector_actual_aggregate_source_ports_required')
    pads=[p for f in board.GetFootprints()for p in f.Pads()if p.GetNetname()==net]
    tracks=[];floors={}
    for item in board.GetTracks():
        _left(deadline)
        if item.GetNetname()!=net:continue
        if item.GetClass()=='PCB_VIA':
            if (item.GetViaType()==pcbnew.VIATYPE_THROUGH and item.TopLayer()==pcbnew.F_Cu
                    and item.BottomLayer()==pcbnew.B_Cu):tracks.append(item)
        elif item.GetClass()in ('PCB_TRACK','PCB_ARC'):
            face=int(item.GetLayer())
            try:floor=full._source_width_floor(board,source,contract,face)
            except ValueError:continue
            if item.GetWidth()>=floor:
                tracks.append(item);floors[force._uid(item)]=floor
    if len(pads)+len(tracks)>4096:raise ValueError('bounded_protector_aggregate_port_inventory_required')
    graph=pcbnew.CONNECTIVITY_DATA()
    for item in [*pads,*tracks]:
        _left(deadline)
        if not graph.Add(item):raise ValueError('protector_explicit_source_port_native_graph_refused')
    reached={force._uid(p)for p in roots}
    for pad in roots:reached.update(force._uid(t)for t in graph.GetConnectedItems(pad))
    ports=[port(p)for p in roots]
    strokes=[]
    for item in tracks:
        _left(deadline);uid=force._uid(item)
        if uid not in reached or item.GetClass()!='PCB_TRACK':continue
        strokes.append(dict(native_uuid=uid,start_nm=list(item.GetStart()),end_nm=list(item.GetEnd()),
            layer_id=int(item.GetLayer()),width_nm=int(item.GetWidth()),source_floor_nm=floors[uid]))
    return dict(root_pad_uuids=sorted(force._uid(p)for p in roots),root_ports=ports,
        retained_full_width_strokes=sorted(strokes,key=lambda r:r['native_uuid']),
        actual_source_component_without_zones_or_undersized_strokes=True,
        existing_barrel_capacity_qualified=False,new_current_budget=False,release_authority=False)


def stroke_port(stroke,toward):
    a,b=stroke['start_nm'],stroke['end_nm'];dx,dy=b[0]-a[0],b[1]-a[1]
    steps=math.gcd(abs(dx),abs(dy))
    if steps<=0:raise ValueError('nonzero_literal_aggregate_source_stroke_required')
    ux,uy=dx//steps,dy//steps
    along=max(0,min(steps,round(((toward[0]-a[0])*ux+(toward[1]-a[1])*uy)/(ux*ux+uy*uy))))
    at=[a[0]+along*ux,a[1]+along*uy]
    return dict(native_uuids=[stroke['native_uuid']],at_nm=at,layers=[stroke['layer_id']])


def full_width_connection(parent,child,source,request,hint,deadline):
    """A named join must not borrow an old thin branch as its missing link.

    All old AND new strokes in this proof meet the actual saved Source and
    full aggregate per-face floors. Actual pads and through barrels supply
    native connectivity only, not a new contact/barrel/thermal current rating.
    No zones, foreign shorts, inferred internal pin shorts or equal sharing.
    """
    named=escape.retained_native_boundary_connection(child,request,timeout_s=_left(deadline))
    if named is None or not named['all_named_contacts_connected']or not named['zone_and_foreign_net_edges_excluded']:
        raise ValueError('current_passive_actual_named_connection_required')
    kind,domain,contract=full._model(parent,Path(source),request['net'],hint)
    if kind!='aggregate_source_sink'or domain is None:
        raise ValueError('current_passive_existing_aggregate_named_path_required')
    with force._thermal_hint(hint):current=cells._supply_current_widths(parent,request['net'])
    if (current is None or _stable(current)!=_stable(request['unchanged_full_rail_current_contract'])
            or contract['current_authority']!=current['current_authority']):
        raise ValueError('current_passive_named_path_source_current_mismatch')
    items=[p for f in child.GetFootprints()for p in f.Pads()if p.GetNetname()==request['net']]
    floors={}
    for item in child.GetTracks():
        _left(deadline)
        if item.GetNetname()!=request['net']:continue
        if item.GetClass()=='PCB_VIA':
            if (item.GetViaType()==pcbnew.VIATYPE_THROUGH and item.TopLayer()==pcbnew.F_Cu
                    and item.BottomLayer()==pcbnew.B_Cu):items.append(item)
        elif item.GetClass()in('PCB_TRACK','PCB_ARC'):
            face=int(item.GetLayer())
            try:floor=full._source_width_floor(parent,Path(source),contract,face)
            except ValueError:continue
            floor=max(floor,int(request['width_nm']))
            if item.GetWidth()>=floor:items.append(item);floors[str(face)]=floor
    if not 1<=len(items)<=4096:raise ValueError('bounded_full_width_named_current_graph_required')
    live={force._uid(i):i for i in items}
    ends=named['source_endpoint_native_uuids'];required=set(ends[0]+ends[1])
    if not required<=live.keys():raise ValueError('current_passive_named_contact_below_source_width')
    graph=pcbnew.CONNECTIVITY_DATA()
    for item in items:
        _left(deadline)
        if not graph.Add(item):raise ValueError('full_width_named_current_graph_refused')
    reached={ends[0][0]}|{force._uid(i)for i in graph.GetConnectedItems(live[ends[0][0]])}
    if not required<=reached:raise ValueError('current_passive_named_join_relies_on_unqualified_copper')
    _left(deadline)
    return dict(all_named_contacts_connected=True,zone_and_foreign_net_edges_excluded=True,
        all_used_strokes_meet_source_and_aggregate_width=True,
        source_endpoint_native_uuids=ends,per_face_width_floor_nm=floors,
        old_thin_copper_and_all_zone_edges_excluded=True,native_graph_items=len(items),
        existing_barrel_capacity_qualified=False,thermal_qualified=False,current_qualified=False,release_authority=False)
