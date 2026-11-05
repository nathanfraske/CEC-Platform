"""Native pad-boundary proof for Kelvin departures, independent of generators.

Only actual copper contact counts; layers join solely through real plated
barrels. A near-pad endpoint or an inner
coordinate followed by an outward segment is not a valid inner-face departure.
This module never changes geometry or infers a shunt from a reference name.
"""
from __future__ import annotations
import math
import time


def _removed_source_via_face(pad,via,layer,deadline):
    """Prove an empty Source-face vertex, never clip or qualify a barrel.

    Only a genuine bore-enclosing through land wholly covered by the
    certified LOWER native SMD cut is removable. The UPPER land includes
    approximation guards; bounds, nominal centres and caller claims cannot
    supply containment. All other faces remain real connectivity vertices.
    """
    import pcbnew
    import cec_kelvin_copper_cut as cut
    if (pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.HasHole()
            or pad.GetBoard()!=via.GetBoard() or not pad.IsOnLayer(layer)
            or not pad.FlashLayer(layer) or not via.IsOnLayer(layer)
            or not via.FlashLayer(layer) or via.GetDrillValue()<=0):
        raise cut.Unknown('actual_flashed_smd_source_and_barrel_face_required')
    work=cut._Work(deadline)
    source=cut._source_cut(pad,layer,False,work)
    lower=cut._shape(via,layer,False,work)
    upper=cut._shape(via,layer,True,work)
    bore=cut._hole(via,True,work)
    if not lower.covers(bore):
        raise cut.Unknown('plated_bore_not_enclosed_by_native_land')
    removed=source.covers(upper) and upper.difference(source).is_empty
    cut._validate_linear_epochs(work);work.tick()
    if not removed:return None
    return dict(uuid=via.m_Uuid.AsString(),source_pad_uuid=pad.m_Uuid.AsString(),
        layer=int(layer),upper_land_removed_by_certified_lower_source_cut=True,
        true_polygon_and_bore_enclosure_verified=True,
        other_faces_and_plated_connectivity_retained=True,
        isolation_current_or_fabrication_qualified=False)


def audit_pad_departures(pad, other_position, tracks, *, inner_min_mm=.1,
                         heading_tolerance_nm=1000, target_pads=None,
                         connectivity_pads=(),connectivity_vias=()):
    """Qualify thin source contacts supplied by an electrical-topology caller.

    Native standard pads are convex. Their overlap interval with the track's
    round centreline probe is therefore contiguous; bounded bisection locates
    the final contact to one database unit. Endpoint-edge contacts remain valid
    even when only the trace's round cap overlaps the pad. Custom/non-convex pads
    fail closed when touched instead of assuming a bounding-box model.

    When input pads are supplied, cut the source pad and track portions inside
    it from the connectivity graph before identifying sense departures. A
    separate voltage-only branch at the same force terminal is not a Kelvin
    input branch. Rejoining that branch outside the source pad still counts.
    Other physical pads can bridge track pieces, but never the removed source.
    """
    import pcbnew
    if (not math.isfinite(inner_min_mm) or inner_min_mm<0
            or type(heading_tolerance_nm) is not int or heading_tolerance_nm<0):
        raise ValueError('invalid Kelvin departure tolerance')
    cut_deadline=time.monotonic()+10.
    centre=pad.GetPosition();dx=other_position.x-centre.x;dy=other_position.y-centre.y
    span=math.hypot(dx,dy)
    if span<=0:raise ValueError('Kelvin source terminals must be distinct')
    ux,uy=dx/span,dy/span
    convex={getattr(pcbnew,name) for name in ('PAD_SHAPE_RECT','PAD_SHAPE_CIRCLE',
        'PAD_SHAPE_OVAL','PAD_SHAPE_TRAPEZOID','PAD_SHAPE_ROUNDRECT',
        'PAD_SHAPE_CHAMFERED_RECT') if hasattr(pcbnew,name)}
    contacts=[];issues=[];departures=[];internal=[];cut_shapes={};layers={}
    offset=pad.GetOffset()
    for track in tracks:
        if track.GetNetCode()!=pad.GetNetCode():continue
        layer=track.GetLayer();shape=pad.GetEffectiveShape(layer)
        uid=track.m_Uuid.AsString();layers[uid]=layer
        track_shape=track.GetEffectiveShape(layer)
        if not pad.IsOnLayer(layer):
            # Retain actual downstream copper, without inventing a source
            # contact on a layer absent from the physical shunt land.
            cut_shapes[uid]=track_shape
            continue
        if not shape.Collide(track_shape,0):
            cut_shapes[uid]=track_shape
            continue
        row=dict(uuid=track.m_Uuid.AsString(),net=track.GetNetname(),
            layer=pcbnew.LayerName(layer),source_pad=str(pad.GetNumber()))
        contacts.append(row)
        if (track.GetClass()!='PCB_TRACK' or pad.GetShape() not in convex
                or offset.x or offset.y):
            issues.append(dict(row,reason='unsupported_native_departure_shape'))
            cut_shapes[uid]=track_shape
            continue
        a,b=track.GetStart(),track.GetEnd();width=track.GetWidth()
        def touching(point):
            # KiCad has no point-only SHAPE_SEGMENT overload. One nm is below
            # the existing heading tolerance and uses its actual native capsule.
            probe=pcbnew.SHAPE_SEGMENT(point,pcbnew.VECTOR2I(point.x+1,point.y),width)
            return bool(shape.Collide(probe,0))
        ac,bc=touching(a),touching(b)
        if ac and bc:
            internal.append(row)
            continue
        if not ac and not bc:
            issues.append(dict(row,reason='thin_track_crosses_source_pad_without_terminal'))
            cut_shapes[uid]=track_shape
            continue
        if bc:a,b=b,a
        vx,vy=b.x-a.x,b.y-a.y;length=math.hypot(vx,vy)
        if length<=0:
            issues.append(dict(row,reason='degenerate_departure'));continue
        lo,hi=0.,1.
        for _ in range(64):
            if (hi-lo)*length<=1.:break
            t=(lo+hi)/2
            q=pcbnew.VECTOR2I(round(a.x+t*vx),round(a.y+t*vy))
            if touching(q):lo=t
            else:hi=t
        exit_point=(a.x+lo*vx,a.y+lo*vy)
        outside=pcbnew.VECTOR2I(round(a.x+hi*vx),round(a.y+hi*vy))
        cut_shapes[uid]=pcbnew.SHAPE_SEGMENT(outside,b,width)
        projection=((exit_point[0]-centre.x)*ux+(exit_point[1]-centre.y)*uy)/1e6
        along=vx*ux+vy*uy;transverse=abs(vx*uy-vy*ux)
        witness=dict(row,contact_exit_mm=[round(v/1e6,6) for v in exit_point],
            inner_projection_mm=round(projection,6),
            inward_direction=[round(ux,9),round(uy,9)],
            departure_start_mm=[a.x/1e6,a.y/1e6],departure_end_mm=[b.x/1e6,b.y/1e6],
            transverse_error_nm=round(transverse,3))
        departures.append(witness)
        if projection+1e-6<inner_min_mm:
            issues.append(dict(witness,reason='departure_not_on_inner_face'))
        elif along<=0 or transverse>heading_tolerance_nm:
            issues.append(dict(witness,reason='departure_not_perpendicular_inward'))
    non_sense=[];reachable=set();source_face_barrel_cuts=[]
    target_ids=None
    if target_pads is not None:
        targets=list(target_pads)
        target_ids={p.m_Uuid.AsString() for p in targets}
        nodes=[(uid,layers[uid],shape) for uid,shape in cut_shapes.items()]
        source_id=pad.m_Uuid.AsString()
        seen=set();plated=set()
        for other in [*targets,*connectivity_pads]:
            other_id=other.m_Uuid.AsString()
            if other_id in seen or other_id==source_id or other.GetNetCode()!=pad.GetNetCode():continue
            seen.add(other_id)
            for layer in set(layers.values()):
                if not other.IsOnLayer(layer):continue
                shape=other.GetEffectiveShape(layer)
                if shape.Collide(pad.GetEffectiveShape(layer),0):
                    # A second pad overlapping the cut would reintroduce the
                    # force node. Do not silently claim that scope is proven.
                    issues.append(dict(uuid=other_id,
                        reason='connectivity_pad_overlaps_source_cut'))
                    continue
                nodes.append((other_id,layer,shape))
            if other.HasHole() and other.GetAttribute()==pcbnew.PAD_ATTRIB_PTH:
                plated.add(other_id)
        for via in connectivity_vias:
            if via.GetClass()!='PCB_VIA' or via.GetNetCode()!=pad.GetNetCode():continue
            uid=via.m_Uuid.AsString()
            if uid in seen or uid in cut_shapes:
                issues.append(dict(uuid=uid,reason='ambiguous_connectivity_barrel_identity'));continue
            seen.add(uid)
            if (int(via.GetViaType())!=int(pcbnew.VIATYPE_THROUGH)
                    or int(via.TopLayer())!=int(pcbnew.F_Cu) or int(via.BottomLayer())!=int(pcbnew.B_Cu)):
                issues.append(dict(uuid=uid,reason='unsupported_connectivity_barrel'));continue
            via_layers=set(layers.values()).intersection(map(int,via.GetLayerSet().CuStack()))
            plated.add(uid)
            for layer in sorted(via_layers):
                if pad.IsOnLayer(layer) and via.GetEffectiveShape(layer).Collide(pad.GetEffectiveShape(layer),0):
                    try:proof=_removed_source_via_face(pad,via,layer,cut_deadline)
                    except Exception as exc:
                        proof=None
                        issues.append(dict(uuid=uid,reason='connectivity_barrel_overlaps_source_cut',
                            source_face_cut_refusal=type(exc).__name__+':'+str(exc)))
                    else:
                        if proof is None:issues.append(dict(uuid=uid,
                            reason='connectivity_barrel_overlaps_source_cut'))
                    if proof is not None:source_face_barrel_cuts.append(proof)
                    # Never reintroduce the force cut. A partial/unknown face
                    # still fails above; other real faces remain available.
                    continue
                nodes.append((uid,layer,via.GetEffectiveShape(layer)))
        parent=list(range(len(nodes)));adj=[[] for _ in nodes]
        def root(i):
            while parent[i]!=i:
                parent[i]=parent[parent[i]];i=parent[i]
            return i
        for i,(_,layer,shape) in enumerate(nodes):
            for j in range(i):
                if (nodes[i][0]==nodes[j][0] and nodes[i][0] in plated
                        or nodes[j][1]==layer and shape.Collide(nodes[j][2],0)):
                    parent[root(i)]=root(j)
                    adj[i].append(j);adj[j].append(i)
        inputs={}
        for i,(uid,_,_) in enumerate(nodes):
            if uid in target_ids:inputs.setdefault(root(i),set()).add(uid)
        reach_by_uid={uid:inputs.get(root(i),set()) for i,(uid,_,_) in enumerate(nodes)
                      if uid in cut_shapes}
        index_by_uid={uid:i for i,(uid,_,_) in enumerate(nodes) if uid in cut_shapes}
        relevant=set()
        for row in departures:
            reach=reach_by_uid.get(row['uuid'],set())
            row['reachable_input_pad_uuids']=sorted(reach)
            if reach:
                from collections import deque
                start=index_by_uid[row['uuid']];queue=deque([start]);previous={start:None}
                paths={}
                while queue and len(paths)<len(reach):
                    current=queue.popleft();uid=nodes[current][0]
                    if uid in reach:
                        path=[];cursor=current
                        while cursor is not None:
                            path.append(nodes[cursor][0]);cursor=previous[cursor]
                        paths[uid]=list(reversed(path))
                    for neighbor in adj[current]:
                        if neighbor not in previous:
                            previous[neighbor]=current;queue.append(neighbor)
                row['input_contact_paths']=paths
            if reach:relevant.add(row['uuid']);reachable.update(reach)
            else:non_sense.append(row)
        departures=[r for r in departures if r['uuid'] in relevant]
        # Only directional issues can be exempted by proven branch scope.
        # Unsupported/ambiguous contacts must remain fail-closed.
        directional={'departure_not_on_inner_face','departure_not_perpendicular_inward'}
        issues=[r for r in issues if r['reason'] not in directional or r['uuid'] in relevant]
    missing=sorted(target_ids-reachable) if target_ids is not None else []
    return dict(applicable=bool(contacts),ok=bool(departures) and not issues and not missing,
        contact_count=len(contacts),departure_count=len(departures),
        internal_count=len(internal),departures=departures,issues=issues,
        non_sense_departures=non_sense,
        **({'source_face_barrel_cuts':source_face_barrel_cuts}if source_face_barrel_cuts else{}),
        unreachable_input_pad_uuids=missing,
        reason=('no_native_pad_contact' if not contacts else
                'input_not_reached_from_source' if missing else
                'no_departure_from_source_pad' if not departures and not issues else None))
