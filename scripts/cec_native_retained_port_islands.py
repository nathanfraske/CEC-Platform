"""Collapse duplicate construction ports only through real retained copper.

This is a routing proposal optimization, not a current, Kelvin or retirement
certificate. Pending material is excluded as well as the exact owned cut;
same-net labels or overlapping XY on different faces do not join islands.
"""
import math
import json
import time
import pcbnew
import cec_force_current as force
import cec_native_zone_islands as zone_islands


def collapse(board, *, net_code, layer, width_nm, points_nm, retired_uuids,
             provisional_uuids=(), deadline,maximum_retired_tracks=16,maximum_ports=16):
    if (type(net_code) is not int or net_code <= 0 or type(layer) is not int
            or layer not in board.GetEnabledLayers().CuStack()
            or type(width_nm) is not int or not 0 < width_nm <= 10_000_000
            or type(maximum_retired_tracks) is not int or not 1<=maximum_retired_tracks<=32
            or type(maximum_ports) is not int or not 2<=maximum_ports<=32
            or type(points_nm) not in (list,tuple) or not 2 <= len(points_nm) <= maximum_ports
            or any(type(p) not in (list,tuple) or len(p) != 2
                or any(type(v) is not int or abs(v) > 2_000_000_000 for v in p)
                for p in points_nm)
            or type(deadline) not in (int,float) or not math.isfinite(deadline)):
        raise ValueError('bounded_actual_retained_branch_port_inventory_required')
    points=sorted(set(map(tuple,points_nm)))
    if len(points)!=len(points_nm):raise ValueError('unique_native_branch_ports_required')
    def ids(values,maximum):
        if (type(values) not in (list,tuple,set,frozenset) or len(values)>maximum
                or any(type(v) is not str or not v for v in values)
                or len(set(values))!=len(values)):
            raise ValueError('exact_retained_port_exclusion_inventory_required')
        return set(values)
    retired=ids(retired_uuids,maximum_retired_tracks);provisional=ids(provisional_uuids,256)
    if not retired:raise ValueError('exact_owned_branch_cut_required')
    def tick():
        if time.monotonic()>=deadline:raise ValueError('native_retained_port_island_deadline')
    tracks=list(board.GetTracks());pads=[p for f in board.GetFootprints() for p in f.Pads()]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea()]
    if len(tracks)+len(pads)+len(zones)>16384:
        raise ValueError('retained_port_native_material_bound')
    lookup={force._uid(t):t for t in tracks}
    if (len(lookup)!=len(tracks)or not (retired|provisional)<=lookup.keys()
            or any(lookup[u].GetClass()!='PCB_TRACK' for u in retired|provisional)):
        raise ValueError('retained_port_exclusions_must_name_actual_source_tracks')
    excluded=retired|provisional
    raw=[i for i in [*pads,*tracks,*zones]
        if i.GetNetCode()==net_code and force._uid(i) not in excluded]
    owners={}
    for item in raw:owners.setdefault(force._uid(item),[]).append(item)
    if any(len(rows)>1 and any(i.GetClass()!='PAD'for i in rows)for rows in owners.values()):
        raise ValueError('ambiguous_retained_native_material_identity')
    material=[]
    for item in raw:
        tick()
        if item.GetClass()=='ZONE':material+=zone_islands.decompose(board,item,deadline=deadline)
        else:material.append(item)
    if not 1<=len(material)<=4096:raise ValueError('bounded_retained_net_material_required')
    conn=pcbnew.CONNECTIVITY_DATA()
    for item in material:
        tick()
        if item.GetClass()=='ZONE' and (not item.IsFilled() or any(
                not item.HasFilledPolysForLayer(face) for face in item.GetLayerSet().CuStack())):
            raise ValueError('retained_port_related_zone_fill_unknown')
        if not conn.Add(item):raise ValueError('retained_port_native_item_refused')
    component={};remaining={force._item_key(i):i for i in material}
    if len(remaining)!=len(material):raise ValueError('ambiguous_retained_native_material_key')
    while remaining:
        tick();uid=min(remaining);item=remaining[uid]
        members={uid}|{force._item_key(i) for i in conn.GetConnectedItems(item)}
        members&=remaining.keys()
        for identity in members:component[identity]=uid;del remaining[identity]
    groups={};contacts=[]
    for point in points:
        tick();at=pcbnew.VECTOR2I(*point);cap=pcbnew.SHAPE_SEGMENT(at,at,width_nm)
        witnesses=[]
        for item in material:
            tick()
            if not item.IsOnLayer(layer):continue
            shape=(item.GetFilledPolysList(layer) if item.GetClass()=='ZONE'
                else item.GetEffectiveShape(layer))
            if shape.Collide(cap,0):witnesses.append(force._item_key(item))
        islands={component[u] for u in witnesses}
        if len(islands)!=1:
            raise ValueError('retained_port_has_missing_or_ambiguous_actual_material:'+json.dumps(dict(
                at_nm=list(point),actual_retained_witness_keys=sorted(witnesses),
                actual_retained_component_ids=sorted(islands),
                excluded_owned_or_pending_track_count=len(excluded),
                proposal_only=True,clearance_or_current_or_connectivity_qualified=False,
                release_authority=False),sort_keys=True))
        identity=next(iter(islands));groups.setdefault(identity,[]).append(point)
        contacts.append(dict(at_nm=list(point),retained_native_keys=sorted(witnesses),
            actual_retained_component_identity=list(identity),exact_native_zone_islands=True))
    representatives=sorted(min(group) for group in groups.values())
    if len(representatives)<2:
        raise ValueError('entire_native_branch_cut_needs_separate_redundancy_receiver:'+json.dumps(dict(
            net=str(lookup[next(iter(retired))].GetNetname()),layer=int(layer),width_nm=width_nm,
            exact_owned_cut_uuids=sorted(retired),excluded_provisional_uuids=sorted(provisional),
            contacts=contacts,distinct_actual_retained_components=len(representatives),
            cut_authorized=False,source_mutated=False,release_authority=False),sort_keys=True))
    return representatives,dict(schema=1,input_port_count=len(points),
        distinct_actual_retained_components=len(representatives),
        representative_ports_nm=[list(p) for p in representatives],contacts=contacts,
        exact_owned_cut_uuids=sorted(retired),excluded_provisional_uuids=sorted(provisional),
        same_net_labels_not_connectivity_credit=True,native_geometry_mutated=False,
        current_or_kelvin_or_retirement_qualified=False,release_authority=False)
