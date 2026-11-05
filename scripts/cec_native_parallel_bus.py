"""Inspect saved split-bus geometry before resistance-interval planning.

The existing parallel-current screen accepts explicit two-node data. This
adapter binds its dimensions and endpoint identities to actual native tracks
and plated pads, and refuses duplicated/shared conductors. It does not certify
equipotential ports, contact bounds, terminal/barrel capacity, coupled thermal
behaviour or release. No board, net, reference or coordinate special cases.
"""
from __future__ import annotations

import math
import time

MAX_BRANCHES=8
MAX_TRACKS=256


def _uid(item):
    return str(item.m_Uuid.AsString())


def inspect(board, net, terminals, branches, *, timeout_s=10.):
    """Read-only literal native path/endpoints audit, never routing admission.

    Branches contain exactly ``id`` and ordered ``track_uuids``. Track order
    may run in either endpoint direction. Complete native finite-cap contacts
    are replayed; bounding boxes and centre-to-centre airwires are not contacts.
    Shared copper on one face is refused outside the actual endpoint pads.
    Other existing same-net copper is reported, not silently idealised into a
    zero-resistance node or silently included as an additional branch.
    """
    import pcbnew
    import cec_pad_surface_access as surface
    import cec_route_quality as quality
    import cec_kelvin_copper_cut as cut
    import shapely
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('native_parallel_bus_bounded_deadline_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('native_parallel_bus_deadline')
    if (type(net) is not str or not net or board.GetNetcodeFromNetname(net)<=0
            or not isinstance(terminals,(list,tuple)) or len(terminals)!=2
            or any(type(u) is not str or not u for u in terminals)
            or terminals[0]==terminals[1]):
        raise ValueError('native_parallel_bus_two_actual_terminal_identities_required')
    if not isinstance(branches,(list,tuple)) or not 2<=len(branches)<=MAX_BRANCHES:
        raise ValueError('native_parallel_bus_branch_budget')
    pads={_uid(p):p for f in board.GetFootprints() for p in f.Pads()}
    tracks={_uid(t):t for t in board.GetTracks()}
    selected=[pads.get(u) for u in terminals]
    if any(p is None or p.GetNetname()!=net
           or p.GetAttribute()!=pcbnew.PAD_ATTRIB_PTH for p in selected):
        raise ValueError('native_parallel_bus_same_net_plated_pad_nodes_required')
    result=dict(schema=1,scope='saved_native_parallel_bus_geometry_and_conditional_screen',
        net=net,terminals=list(terminals),branches=[],finite_native_common_contacts_verified=False,
        equipotential_nodes_qualified=False,contact_resistance_bounds_qualified=False,
        terminal_or_barrel_capacity_qualified=False,coupled_thermal_qualified=False,
        source_current_reduced=False,routing_admitted=False,release_authority=False,
        additional_same_net_contacts=[])
    used=set(); branch_ids=set(); shapes=[]; count=0
    for branch in branches:
        tick()
        if (type(branch) is not dict or set(branch)!={'id','track_uuids'}
                or type(branch['id']) is not str or not branch['id'] or branch['id'] in branch_ids
                or not isinstance(branch['track_uuids'],(list,tuple))
                or not branch['track_uuids']):
            raise ValueError('native_parallel_bus_explicit_unique_ordered_branch_required')
        branch_ids.add(branch['id']); items=[]; points=[]; polys=[]; rows=[]; lid=None
        for uid in branch['track_uuids']:
            tick();count+=1
            if (count>MAX_TRACKS or type(uid) is not str or not uid or uid in used):
                raise ValueError('native_parallel_bus_duplicate_or_unbounded_conductor')
            item=tracks.get(uid)
            if (item is None or item.GetClass()!='PCB_TRACK' or item.GetNetname()!=net
                    or item.GetLayer() not in board.GetEnabledLayers().CuStack()):
                raise ValueError('native_parallel_bus_exact_same_net_straight_track_required')
            if lid is None:lid=item.GetLayer()
            if lid!=item.GetLayer():raise ValueError('native_parallel_bus_no_hidden_layer_transition')
            a,b=tuple(item.GetStart()),tuple(item.GetEnd())
            if not quality.is_canonical_stroke(a,b) or item.GetWidth()<=0:
                raise ValueError('native_parallel_bus_noncanonical_or_empty_stroke')
            if not points:
                if len(branch['track_uuids'])>1:
                    nxt=tracks.get(branch['track_uuids'][1])
                    if nxt is None:raise ValueError('native_parallel_bus_stale_next_stroke')
                    common={a,b}&{tuple(nxt.GetStart()),tuple(nxt.GetEnd())}
                    if len(common)!=1:raise ValueError('native_parallel_bus_ambiguous_or_disconnected_chain')
                    shared=next(iter(common));points=[b,a] if shared==a else [a,b]
                else:points=[a,b]
            elif points[-1]==a:points.append(b)
            elif points[-1]==b:points.append(a)
            else:raise ValueError('native_parallel_bus_disconnected_ordered_chain')
            used.add(uid);items.append(item)
            poly=pcbnew.SHAPE_POLY_SET()
            item.TransformShapeToPolygon(poly,lid,0,1000,pcbnew.ERROR_OUTSIDE)
            polys.append(cut._poly(poly,cut._Work(deadline)))
            length=math.dist(a,b)/1e6;width=item.GetWidth()/1e6
            rows.append(dict(uuid=uid,layer=board.GetLayerName(lid),layer_id=lid,
                length_mm=[length,length],width_mm=[width,width]))
        endpoint_proofs=[]
        for order in (selected,list(reversed(selected))):
            matched=[]
            for p,at,item in zip(order,(points[0],points[-1]),(items[0],items[-1])):
                tick()
                if not p.IsOnLayer(lid) or not p.FlashLayer(lid):break
                sample=surface.sample(p,lid,axis_samples=9,deadline=deadline)
                contacts=[surface.cap_contact(p,lid,list(at),w,item.GetWidth())
                          for w in sample['points']]
                good=[q for q in contacts if q['ok']]
                if not good:break
                matched.append(good[0])
            if len(matched)==2:
                endpoint_proofs=matched;break
        if len(endpoint_proofs)!=2:
            raise ValueError('native_parallel_bus_missing_finite_endpoint_copper')
        body=shapely.union_all(polys)
        pad_polys=[cut._poly(p.GetEffectivePolygon(lid,pcbnew.ERROR_OUTSIDE),cut._Work(deadline))
                   for p in selected]
        outside=body.difference(shapely.union_all(pad_polys))
        for other in shapes:
            tick()
            if other['layer_id']==lid and outside.intersection(other['outside']).area>0:
                raise ValueError('native_parallel_bus_shared_copper_cannot_be_counted_twice')
        shapes.append(dict(id=branch['id'],layer_id=lid,outside=outside,body=body))
        result['branches'].append(dict(id=branch['id'],track_uuids=list(branch['track_uuids']),
            terminals=[q['pad']['uuid'] for q in endpoint_proofs],segments=rows,
            endpoint_proofs=endpoint_proofs,layer_id=lid))
    # Inventory third copper contacts. Pure two-node sizing must not conceal
    # extra injection points, intermediate loads or branch cross-links.
    for item in board.GetTracks():
        tick()
        if _uid(item) in used or item.GetNetname()!=net:continue
        for branch in shapes:
            lid=branch['layer_id']
            if not item.IsOnLayer(lid):continue
            poly=pcbnew.SHAPE_POLY_SET()
            item.TransformShapeToPolygon(poly,lid,0,1000,pcbnew.ERROR_OUTSIDE)
            actual=cut._poly(poly,cut._Work(deadline))
            if branch['outside'].intersects(actual):
                result['additional_same_net_contacts'].append(dict(branch=branch['id'],
                    uuid=_uid(item),kind=item.GetClass(),layer_id=lid))
    for zone in board.Zones():
        tick()
        if zone.GetIsRuleArea() or zone.GetNetname()!=net:continue
        for branch in shapes:
            lid=branch['layer_id']
            if not zone.IsOnLayer(lid) or not zone.HasFilledPolysForLayer(lid):continue
            actual=cut._poly(zone.GetFilledPolysList(lid),cut._Work(deadline))
            if branch['outside'].intersects(actual):
                result['additional_same_net_contacts'].append(dict(branch=branch['id'],
                    uuid=_uid(zone),kind='ZONE',layer_id=lid))
    for uid,pad in pads.items():
        tick()
        if uid in terminals or pad.GetNetname()!=net:continue
        for branch in shapes:
            lid=branch['layer_id']
            if not pad.IsOnLayer(lid) or not pad.FlashLayer(lid):continue
            actual=cut._poly(pad.GetEffectivePolygon(lid,pcbnew.ERROR_OUTSIDE),cut._Work(deadline))
            if branch['outside'].intersects(actual):
                result['additional_same_net_contacts'].append(dict(branch=branch['id'],
                    uuid=uid,kind='PAD',layer_id=lid))
    result.update(finite_native_common_contacts_verified=True,complete=True,
        no_shared_branch_body_copper=True,actual_branch_track_count=count,
        native_board_unchanged=True,
        additional_source_port_network_receiving_required=bool(result['additional_same_net_contacts']))
    return result


def conditional_screen(native, current, bounds, *, permitted_layers, rise_c=30.):
    """Bind supplied sensitivity intervals to native lengths/widths.

    A passing result is explicitly conditional. Caller intervals cannot
    become material, contact, terminal or temperature qualification by assertion.
    Exactly every native branch needs a bound; omitted bounds are not zero R.
    """
    import cec_parallel_current as parallel
    import cec_fab_profile as fab
    if (type(native) is not dict or native.get('complete') is not True
            or native.get('finite_native_common_contacts_verified') is not True
            or type(bounds) is not dict
            or set(bounds)!={q['id'] for q in native['branches']}):
        raise ValueError('native_parallel_bus_complete_native_inventory_and_bounds_required')
    rows=[]
    for branch in native['branches']:
        b=bounds[branch['id']]
        if type(b) is not dict or set(b)!={'copper_mm','series_ohm','temperature_c'}:
            raise ValueError('native_parallel_bus_explicit_contact_copper_temperature_bounds_required')
        rows.append(dict(id=branch['id'],terminals=branch['terminals'],
            series_ohm=b['series_ohm'],temperature_c=b['temperature_c'],segments=[dict(
                layer=fab.COPPER_LAYER_IDS[q['layer_id']],length_mm=q['length_mm'],
                width_mm=q['width_mm'],copper_mm=b['copper_mm']) for q in branch['segments']]))
    screen=parallel.screen_bundle(current,rows,terminals=native['terminals'],
        permitted_layers=permitted_layers,rise_c=rise_c)
    screen.update(native_finite_contacts_verified=True,
        native_no_shared_branch_body_copper=True,
        supplied_bounds_are_conditions_not_qualification=True,
        additional_source_port_network_receiving_required=native.get(
            'additional_source_port_network_receiving_required',False))
    return screen
