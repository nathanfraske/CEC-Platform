"""Source-typed access ordering and literal existing plated endpoint faces.

This ranks construction work, not electrical importance or current capacity.
It never permits narrowing, an inferred SMD layer contact, a new barrel, or a
saved-board waiver. Native receiving still proves every complete transaction.
"""

def order(rows,priorities,*,ordinary_nets,constrained_before_ordinary=False):
    if (type(rows) not in (list,tuple) or not 1<=len(rows)<=128
            or type(priorities) not in (list,tuple) or len(priorities)>8
            or len(set(priorities))!=len(priorities)
            or any(type(n) is not str or not n or n not in ordinary_nets for n in priorities)):
        raise ValueError('bounded_positive_ordinary_access_priority_required')
    if type(constrained_before_ordinary) is not bool:
        raise ValueError('explicit_constrained_route_order_required')
    if any(type(r) is not dict or type(r.get('width')) is not int or r['width']<=0
           or type(r.get('net')) is not str or type(r.get('uid')) is not str for r in rows):
        raise ValueError('literal_native_route_schedule_rows_required')
    if len({r['uid'] for r in rows})!=len(rows):raise ValueError('unique_native_route_schedule_rows_required')
    rank={n:i for i,n in enumerate(priorities)}
    # Wide source-current conductors and GND work retain their precedence.
    # An opt-in scarce-access signal outranks only work of the same width.
    return sorted(rows,key=lambda r:(-r['width'],r['net']!='GND',
        constrained_before_ordinary and r['net'] in ordinary_nets,
        rank.get(r['net'],len(rank)),r['uid']))


def order_from_source(board,source,board_hint,rows,priorities,*,constrained_before_ordinary=False):
    """Bind scarce-face ordering to the ACTUAL positive source classifier.

    An empty optional ordinary-priority list does not disable classification
    required by constrained-first scheduling. Width/GND precedence remains
    unchanged. This is scheduling evidence, never layer/current permission.
    """
    if type(constrained_before_ordinary) is not bool:
        raise ValueError('explicit_source_constrained_order_mode_required')
    typed=bool(priorities or constrained_before_ordinary)
    eligible=None
    if typed:
        import cec_ordinary_route_receiving as ordinary
        eligible=ordinary.eligible_nets(board,source,board_hint)
    ordered=order(rows,priorities,ordinary_nets=eligible or set(),
        constrained_before_ordinary=constrained_before_ordinary)
    return ordered,eligible,dict(source_classifier_used=typed,
        constrained_faces_before_ordinary=constrained_before_ordinary,
        positive_source_ordinary_nets=sorted(eligible or ()),
        empty_optional_priority_list_does_not_disable_constrained_typing=True,
        width_ground_and_source_contracts_unchanged=True,release_authority=False)


def retained_component_pairs(board,net,start,end,layer,faces,*,ordinary_nets,deadline,limit=8,
                             allow_same_face_smd_ports=False,allow_connected_surface_smd_ports=False,
                             allow_retained_track_ports=False,
                             rank_native_departures=False,clearance_nm=None,source_width_nm=None,planar_guard=None):
    """Alternative exact plated exits of the two actual retained components."""
    import math,time
    import pcbnew
    import cec_native_component_ports as native
    import cec_native_track_ports as tracks
    import cec_force_current as force
    if (net not in ordinary_nets or type(limit) is not int or not 1<=limit<=8
            or type(allow_same_face_smd_ports) is not bool
            or type(allow_connected_surface_smd_ports) is not bool or type(rank_native_departures) is not bool
            or type(allow_retained_track_ports) is not bool
            or allow_retained_track_ports and (type(source_width_nm) is not int
                or not max(1,board.GetDesignSettings().m_TrackMinWidth)<=source_width_nm<=20000000)
            or rank_native_departures and (type(clearance_nm) is not int
                or clearance_nm<board.GetDesignSettings().m_MinClearance or clearance_nm>2000000
                or type(source_width_nm) is not int
                or not max(1,board.GetDesignSettings().m_TrackMinWidth)<=source_width_nm<=20000000)
            or type(deadline) not in (int,float) or not math.isfinite(deadline)
            or not time.monotonic()<deadline<=time.monotonic()+10.):
        raise ValueError('bounded_positive_ordinary_component_access_required')
    groups=native.boundary_components(board,net,layer,[list(start),list(end)],deadline=deadline)
    if len(groups)==1:
        return [],dict(already_connected=True,retained_components=groups,new_barrel_or_current_credit=False,
            source_boundary_receiving_still_required=True,release_authority=False)
    if len(groups)!=2:raise ValueError('two_exact_retained_ordinary_components_required')
    live={force._uid(i):i for i in [*(p for f in board.GetFootprints() for p in f.Pads()),*board.GetTracks()]}
    menus=[]
    for at,toward in ((start,end),(end,start)):
        component=next(g for g in groups if list(at) in g['source_anchors_nm'])
        base=dict(at_nm=list(at),layers=[layer],native_uuids=component['native_uuids'])
        discovered=native.endpoints(board,net,base,toward_nm=tuple(toward),max_sites=16,
            max_shift_mm=24.,deadline=deadline,prefer_native_via_access=True,diverse_native_sites=True)
        chosen=[]
        source_component=set(component['retained_component_native_uuids'])
        component_barrels=[live[u] for u in source_component if u in live
            and (live[u].GetClass()=='PCB_VIA' and live[u].GetViaType()==pcbnew.VIATYPE_THROUGH
                or live[u].GetClass()=='PAD' and live[u].GetAttribute()==pcbnew.PAD_ATTRIB_PTH and live[u].HasHole())]
        for p in discovered:
            plated=[live[u] for u in p['native_uuids'] if u in live
                and (live[u].GetClass()=='PCB_VIA' or live[u].GetClass()=='PAD'
                     and live[u].GetAttribute()==pcbnew.PAD_ATTRIB_PTH and live[u].HasHole())
                and tuple(live[u].GetPosition())==tuple(p['at_nm'])]
            same_face_smd=bool(allow_same_face_smd_ports and any(u in live
                and live[u].GetClass()=='PAD' and live[u].GetAttribute()==pcbnew.PAD_ATTRIB_SMD
                and not live[u].HasHole() and tuple(live[u].GetPosition())==tuple(p['at_nm'])
                and list(map(int,live[u].GetLayerSet().CuStack()))==[layer]
                for u in p['native_uuids']))
            surface_smd=[]
            track_contacts=[]
            if allow_retained_track_ports:
                track_contacts=[live[u] for u in p['native_uuids'] if u in source_component and u in live
                    and live[u].GetClass()=='PCB_TRACK' and live[u].GetWidth()>=source_width_nm
                    and tracks.on_centerline(live[u],p['at_nm'])]
            if allow_connected_surface_smd_ports:
                for u in p['native_uuids']:
                    if u not in source_component or u not in live:continue
                    item=live[u]
                    if (item.GetClass()!='PAD' or item.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or item.HasHole()
                            or tuple(item.GetPosition())!=tuple(p['at_nm'])):continue
                    pad_faces=list(map(int,item.GetLayerSet().CuStack()))
                    if len(pad_faces)!=1 or pad_faces[0] not in faces:continue
                    # Native membership alone does not label an SMD as
                    # plated. A different-face launch additionally owes an
                    # actual through barrel/PTH in this exact component.
                    through=[force._uid(v) for v in component_barrels
                        if v.IsOnLayer(layer) and v.IsOnLayer(pad_faces[0])]
                    if pad_faces[0]!=layer and not through:continue
                    surface_smd.append((pad_faces[0],through))
            if tuple(p['at_nm'])!=tuple(at) and not plated and not same_face_smd and not surface_smd and not track_contacts:continue
            active=[l for l in p['layers'] if l in faces]
            if not plated and track_contacts:
                # A real straight conductor grants only its actual face,
                # never the faces of a different barrel in this component.
                active=[l for l in active if any(t.IsOnLayer(l) for t in track_contacts)]
            elif not plated and surface_smd:active=[l for l in active if l in {q[0] for q in surface_smd}]
            elif same_face_smd and not plated:active=[l for l in active if l==layer]
            if not active:continue
            row=dict(p,layers=active,actual_retained_plated=bool(plated))
            if allow_retained_track_ports:row['actual_retained_track_contact']=bool(track_contacts)
            if allow_same_face_smd_ports:row['actual_same_face_smd_launch']=same_face_smd
            if allow_connected_surface_smd_ports:
                row['actual_retained_surface_smd_launch']=bool(surface_smd)
                row['actual_component_through_access_uuids']=sorted({u for _,ids in surface_smd for u in ids})
            if not any(q['at_nm']==row['at_nm'] and q['layers']==row['layers'] for q in chosen):chosen.append(row)
        if allow_connected_surface_smd_ports or rank_native_departures:
            chosen=[p for p in chosen if not p['actual_retained_plated'] or not any(
                q['actual_retained_plated'] and p['at_nm']==q['at_nm']
                and set(p['native_uuids'])==set(q['native_uuids']) and set(p['layers'])<set(q['layers'])
                for q in chosen)]
        menus.append(chosen)
    ranked=[(a,b) for a in menus[0] for b in menus[1]
        if (tuple(a['at_nm'])!=tuple(start) or tuple(b['at_nm'])!=tuple(end)
            or set(a['layers'])!={layer} or set(b['layers'])!={layer})]
    # Identical XY is not identical access. Two retained through barrels
    # may have no other component members, yet their other actual faces
    # still provide legal alternatives to a congested source face. Reject
    # only the literal original single-face request, not these real spans.
    ranked.sort(key=lambda pair:(not bool(set(pair[0]['layers'])&set(pair[1]['layers'])),
        -sum(bool(p['actual_retained_plated']) for p in pair),math.dist(pair[0]['at_nm'],pair[1]['at_nm'])))
    departure_proof=None
    if rank_native_departures and ranked:
        # Native egress samples reorder a bounded menu; they neither delete
        # negative/unexamined ports nor claim a global no-path result.
        ranked,departure_proof=native.rank_by_native_egress(board,net,ranked[:128],route_layers=faces,
            width_for_layer=lambda face:source_width_nm,
            clearance_nm=clearance_nm,deadline=deadline,planar_guard=planar_guard)
    if allow_retained_track_ports and ranked:
        ranked=native.diverse_pairs(ranked,point=lambda p:p['at_nm'],layers=lambda p:p['layers'],
            limit=min(256,len(ranked)),breadth=min(limit,len(ranked)))
    proof=dict(already_connected=False,retained_components=groups,
        exact_component_port_pairs=ranked[:limit],new_barrel_or_current_credit=False,
        source_boundary_receiving_still_required=True,release_authority=False)
    if allow_same_face_smd_ports:
        proof['same_face_smd_launches_requested']=True
        proof['smd_land_is_not_cross_layer_access']=True
    if allow_connected_surface_smd_ports:
        proof['actual_connected_surface_smd_launches_requested']=True
        proof['different_face_surface_access_requires_real_component_barrel']=True
    if rank_native_departures:proof['actual_native_departure_ranking']=departure_proof
    if allow_retained_track_ports:
        proof['retained_track_contacts_requested']=True
        proof['track_ports_require_exact_centerline_sufficient_source_width_and_actual_face']=True
    return ranked[:limit],proof


def endpoint_faces(board,at,net,faces,preferred,*,ordinary_nets):
    import pcbnew
    import cec_force_current as force
    if net not in ordinary_nets:
        raise ValueError('positive_source_ordinary_endpoint_context_required')
    if (type(faces) not in (list,tuple) or not faces or len(faces)!=len(set(faces))
            or preferred not in faces or len(at)!=2 or any(type(v) is not int for v in at)):
        raise ValueError('literal_existing_endpoint_faces_required')
    # Native exact centers and actual plated spans, never proximity, pad
    # numbers, footprint silhouettes, names or an assumed all-layer SMD.
    hits=[t for t in board.GetTracks() if t.GetClass()=='PCB_VIA'
        and str(t.GetNetname())==net and tuple(t.GetPosition())==tuple(at)
        and t.GetViaType()==pcbnew.VIATYPE_THROUGH]
    hits += [p for fp in board.GetFootprints() for p in fp.Pads()
        if p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH and p.HasHole()
        and str(p.GetNetname())==net and tuple(p.GetPosition())==tuple(at)]
    if len(hits)>1:raise ValueError('unique_actual_existing_plated_endpoint_required')
    result=[f for f in faces if hits[0].IsOnLayer(f)] if hits else [preferred]
    if not result:raise ValueError('existing_plated_endpoint_has_no_authorized_face')
    return dict(layer_ids=result,native_uuids=[force._uid(h) for h in hits],
        actual_existing_plating_only=True,new_barrel_or_current_credit=False,release_authority=False)
