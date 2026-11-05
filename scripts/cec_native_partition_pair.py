"""Paired physical native partitions across exact saved-zone fill changes.

A zone UUID is never a conductor connecting all of its polygons. Comparison
tokens co-refine literal old/child fill islands by positive native overlap.
This is connectivity evidence only, not delta/pose/current/routing admission.
"""
import math
import time

import pcbnew
import cec_force_current as force
import cec_native_fill_geometry as fill
import cec_native_zone_islands as islands


def _tick(deadline):
    if time.monotonic()>=deadline:raise ValueError('paired_native_partition_deadline')


def _area2(shape,deadline):
    """Exact integer signed-ring arithmetic; holes are not solid material."""
    total=0
    for polygon in fill.snapshot(shape,deadline):
        for index,ring in enumerate(polygon):
            area=abs(sum(a[0]*b[1]-b[0]*a[1]for a,b in zip(ring,ring[1:]+ring[:1])))
            total+=area if index==0 else -area
    if total<0:raise ValueError('ambiguous_native_intersection_hole_area')
    return total


def _positive_overlap(a,b,deadline):
    _tick(deadline)
    if not a.BBox().Intersects(b.BBox()):return False
    overlap=a.CloneDropTriangulation();overlap.BooleanIntersection(b)
    _tick(deadline)
    return bool(overlap.OutlineCount() and _area2(overlap,deadline)>0)


def _inventory(board,deadline,bounds):
    material=[p for fp in board.GetFootprints()for p in fp.Pads()if p.GetNetCode()>0]
    material+=list(board.GetTracks())
    zones=[z for z in board.Zones()if not z.GetIsRuleArea()]
    if len(material)+len(zones)>bounds['items']:raise ValueError('paired_native_item_bound')
    owners={}
    for item in [*material,*zones]:owners.setdefault(force._uid(item),[]).append(item)
    # Historical cloned footprint children may share a UUID. Their actual
    # ref/pin/position composite keys remain distinct; copper owner aliases
    # and cross-class aliases cannot be resolved this way.
    if any(len(rows)>1 and any(i.GetClass()!='PAD'for i in rows)for rows in owners.values()):
        raise ValueError('ambiguous_native_parent_identity')
    live={force._item_key(i):i for i in material};zone_rows={};objects=list(material)
    if len(live)!=len(material):raise ValueError('ambiguous_native_source_key')
    vertices=0;polygons=0
    for zone in zones:
        _tick(deadline)
        if zone.GetNetCode()<=0 or not zone.GetNetname():raise ValueError('unknown_native_zone_net')
        # Read-only counterfactual views may filter tracks while retaining
        # the actual Source zones. Proxy ownership must use their real BOARD,
        # never reinterpret a Python inventory view as a native board.
        proxies=islands.decompose(zone.GetBoard(),zone,deadline=deadline)
        for proxy in proxies:
            face=int(proxy.GetLayer());shape=proxy.GetFilledPolysList(face)
            digest,count=fill.identity(shape,deadline);vertices+=count;polygons+=1
            if vertices>bounds['vertices'] or polygons>bounds['polygons']:
                raise ValueError('paired_native_fill_complexity_bound')
            key=(force._uid(zone),str(zone.GetNetname()),face)
            zone_rows.setdefault(key,[]).append(dict(item=proxy,shape=shape,digest=digest))
            objects.append(proxy)
    if len(objects)>bounds['items']:raise ValueError('paired_native_proxy_item_bound')
    # Only authored-net native graphs; a foreign short is not a legitimate
    # bridge and no board BuildConnectivity/net propagation is performed.
    nets={};lookup={}
    for item in objects:
        _tick(deadline)
        if item.GetNetCode()<=0 or not item.GetNetname():raise ValueError('unknown_native_conductor_net')
        name=str(item.GetNetname());nets.setdefault(name,[]).append(item)
        key=force._item_key(item)
        if key in lookup:raise ValueError('ambiguous_native_proxy_identity')
        lookup[key]=item
    components=[];component_of={}
    for name,rows in sorted(nets.items()):
        graph=pcbnew.CONNECTIVITY_DATA()
        for item in rows:
            _tick(deadline)
            if not graph.Add(item):raise ValueError('paired_native_graph_item_refused')
        remaining={force._item_key(i):i for i in rows}
        while remaining:
            _tick(deadline);key=min(remaining);item=remaining[key]
            reached={key}|{force._item_key(i)for i in graph.GetConnectedItems(item)}
            if not reached<=lookup.keys():raise ValueError('paired_native_graph_unknown_item')
            part=set(remaining)&reached
            if not part:raise ValueError('paired_native_empty_component')
            index=len(components);components.append(part)
            for member in part:component_of[member]=index;del remaining[member]
    return dict(live=live,zones=zone_rows,components=components,component_of=component_of,
        objects=objects,vertices=vertices,polygons=polygons)


def compare(parent,child,*,timeout_s=10.,retired_uuids=(),retained_keys=None,
            identity_rebindings=None,max_items=16384,max_polygons=4096,max_vertices=200000):
    """Compare retained Source components; exceptions mean unknown, not pass.

    Rebindings are exact independently authorized moved-PAD keys, never a
    grant of pose authority. Retired source tracks remain in the OLD graph,
    but are excluded from comparison keys. New child material can connect
    retained keys without acquiring Source identity or current capacity.
    """
    if (type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10
            or type(max_items)is not int or not 1<=max_items<=16384
            or type(max_polygons)is not int or not 1<=max_polygons<=4096
            or type(max_vertices)is not int or not 32<=max_vertices<=200000):
        raise ValueError('bounded_paired_native_partition_required')
    deadline=time.monotonic()+timeout_s
    bounds=dict(items=max_items,polygons=max_polygons,vertices=max_vertices)
    old=_inventory(parent,deadline,bounds);new=_inventory(child,deadline,bounds)
    if old['vertices']+new['vertices']>max_vertices or old['polygons']+new['polygons']>max_polygons:
        raise ValueError('paired_total_fill_complexity_bound')
    if type(retired_uuids)not in(list,tuple,set,frozenset)or any(type(u)is not str or not u for u in retired_uuids):
        raise ValueError('exact_retired_native_identity_required')
    retired=set(retired_uuids)
    by_uid={force._uid(i):i for i in old['live'].values()if i.GetClass()!='PAD'}
    if not retired<=by_uid.keys():
        raise ValueError('retired_identity_must_be_actual_source_copper')
    bindings={}if identity_rebindings is None else identity_rebindings
    if type(bindings)is not dict or len(set(bindings.values()))!=len(bindings):
        raise ValueError('unique_exact_moved_pad_rebindings_required')
    for actual,source in bindings.items():
        if actual not in new['live']or source not in old['live']:
            raise ValueError('moved_pad_rebinding_not_actual_source_child')
        a,b=new['live'][actual],old['live'][source]
        if (a.GetClass()!='PAD'or b.GetClass()!='PAD'or force._uid(a)!=force._uid(b)
                or a.GetNumber()!=b.GetNumber()or a.GetNetname()!=b.GetNetname()
                or force._uid(a.GetParentFootprint())!=force._uid(b.GetParentFootprint())
                or a.GetParentFootprint().GetReference()!=b.GetParentFootprint().GetReference()
                or tuple(a.GetSize())!=tuple(b.GetSize())or a.GetShape()!=b.GetShape()
                or tuple(a.GetLayerSet().CuStack())!=tuple(b.GetLayerSet().CuStack())):
            raise ValueError('moved_pad_rebinding_identity_changed')
    child_keys={bindings.get(k,k):k for k in new['live']}
    if len(child_keys)!=len(new['live']):raise ValueError('ambiguous_rebound_child_source_key')
    source_keys={k for k,v in old['live'].items()if force._uid(v)not in retired}
    if retained_keys is not None:
        if type(retained_keys)not in(set,frozenset)or not retained_keys<=source_keys:
            raise ValueError('retained_keys_must_name_actual_nonzone_source_material')
        source_keys=set(retained_keys)
    if not source_keys<=child_keys.keys():raise ValueError('surviving_source_conductor_missing')
    left=[set()for _ in old['components']];right=[set()for _ in new['components']]
    for key in source_keys:
        _tick(deadline)
        if old['live'][key].GetNetname()!=new['live'][child_keys[key]].GetNetname():
            raise ValueError('surviving_source_conductor_net_changed')
        left[old['component_of'][key]].add(key)
        right[new['component_of'][child_keys[key]]].add(key)
    tokens=[];pairs=0
    for zone_key,source_rows in sorted(old['zones'].items()):
        target_rows=new['zones'].get(zone_key)
        if not target_rows:raise ValueError('source_zone_identity_net_or_face_missing')
        for a in source_rows:
            matches=[]
            for b in target_rows:
                _tick(deadline);pairs+=1
                if pairs>65536:raise ValueError('paired_island_intersection_work_bound')
                if not _positive_overlap(a['shape'],b['shape'],deadline):continue
                token=('zone_overlap',*zone_key,a['digest'],b['digest'])
                li=old['component_of'][force._item_key(a['item'])]
                ri=new['component_of'][force._item_key(b['item'])]
                left[li].add(token);right[ri].add(token);tokens.append(token);matches.append(ri)
            if not matches:raise ValueError('source_island_has_no_positive_surviving_overlap')
    left=[p for p in left if p];right=[p for p in right if p]
    demoted=[p for p in left if not any(p<=q for q in right)]
    _tick(deadline)
    return dict(available=True,preserved=not demoted,source_parts=left,child_parts=right,
        demoted_parts=demoted,source_component_count=len(left),child_component_count=len(right),
        native_source_component_count=len(old['components']),native_child_component_count=len(new['components']),
        reported_parts_contain_comparison_keys_only=True,
        overlap_token_count=len(tokens),intersection_pairs=pairs,
        exact_positive_native_island_overlap=True,whole_zone_uuid_connectivity_credit=False,
        current_capacity_qualified=False,routing_admitted=False,release_authority=False,
        independent_delta_pose_current_receiving_still_required=True)
