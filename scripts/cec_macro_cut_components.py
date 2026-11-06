"""Reconstruct typed cut components between surviving literal native ports.

An internal bend retired together with both incident edges is not a surviving
terminal. Group only independently owned additional Source edges by actual
native same-net/same-face contact; reconnect every surviving native contact.
No Source pad/barrel is retired, no coordinate becomes a fictitious anchor,
and no current, native-partition, field or fabrication gate is waived.
"""
import copy
from fractions import Fraction
import math
import time

import pcbnew
import cec_force_current as force


def _contact_site(edge,item,face):
    """Finite real integer points, each checked on BOTH actual shapes."""
    first=[tuple(edge.GetStart()),tuple(edge.GetEnd())]
    last=[tuple(item.GetStart()),tuple(item.GetEnd())]
    candidates=set(first+last)
    for a in first:
        for b in last:candidates.add(tuple(round(Fraction(x+y,2)) for x,y in zip(a,b)))
    def weighted(a,b):
        # A midpoint misses overlap between unequal-width round track caps.
        # Radius-weighted closest-centreline witnesses use exact rationals;
        # the final native BOTH-shapes test remains the only acceptance.
        wa,wb=int(edge.GetWidth()),int(item.GetWidth())
        if wa<=0 or wb<=0:raise ValueError('positive_native_cut_contact_widths_required')
        q=[(Fraction(x)*wb+Fraction(y)*wa)/(wa+wb) for x,y in zip(a,b)]
        xs={math.floor(q[0]),math.ceil(q[0])};ys={math.floor(q[1]),math.ceil(q[1])}
        candidates.update((x,y)for x in xs for y in ys)
    for a in first:
        for b in last:weighted(a,b)
    # Endpoint projections supplement exact crossing and capsule contact.
    for a,b,reverse in ((first,last,False),(last,first,True)):
        x,y=b[0];dx,dy=b[1][0]-x,b[1][1]-y;den=dx*dx+dy*dy
        if not den:continue
        for px,py in a:
            u=max(Fraction(0),min(Fraction(1),Fraction((px-x)*dx+(py-y)*dy,den)))
            projected=(x+u*dx,y+u*dy)
            candidates.add(tuple(round(v)for v in projected))
            weighted(projected,(px,py)) if reverse else weighted((px,py),projected)
    ax,ay=first[0];bx,by=last[0]
    dx,dy=first[1][0]-ax,first[1][1]-ay;ex,ey=last[1][0]-bx,last[1][1]-by
    cross=dx*ey-dy*ex
    if cross:
        u=Fraction((bx-ax)*ey-(by-ay)*ex,cross)
        v=Fraction((bx-ax)*dy-(by-ay)*dx,cross)
        if 0<=u<=1 and 0<=v<=1:candidates.add((round(ax+u*dx),round(ay+u*dy)))
    a,b=edge.GetEffectiveShape(face),item.GetEffectiveShape(face)
    valid=[q for q in candidates if a.Collide(pcbnew.VECTOR2I(*q),0)
        and b.Collide(pcbnew.VECTOR2I(*q),0)]
    if not valid:raise ValueError('cut_component_has_no_exact_integer_native_contact_site')
    return min(valid,key=lambda p:(min(math.dist(p,q) for q in first),p))


def requests(parent,private,extras,retired,transport,*,project_contacts,deadline):
    """Fresh source-owned components and star demands, not routing admission."""
    if (type(extras) is not list or not 1<=len(extras)<=64
            or type(retired) not in (set,frozenset) or len(retired)>128
            or type(deadline) not in (int,float) or not math.isfinite(deadline)
            or not time.monotonic()<deadline<=time.monotonic()+10.):
        raise ValueError('bounded_literal_macro_cut_component_scope_required')
    def tick():
        if time.monotonic()>=deadline:raise ValueError('macro_cut_component_deadline')
    source={force._uid(t):t for t in parent.GetTracks()}
    by_id={r['change']['uuid']:r for r in extras}
    if len(by_id)!=len(extras) or not by_id.keys()<=retired or not by_id.keys()<=source.keys():
        raise ValueError('unique_positively_owned_additional_cut_edges_required')
    import cec_source_ground_continuation as continuation
    import cec_linear_stage_ground_boundary as linear_boundary
    ground_kinds={'positive_existing_low_power_ground_boundary',continuation.KIND,linear_boundary.KIND}
    accepted={'positive_source_ordinary','unchanged_full_current_source_edge'}|ground_kinds
    graph=pcbnew.CONNECTIVITY_DATA()
    for uid,row in by_id.items():
        tick();edge=source[uid];authority=row['authority']
        if authority.get('kind')==linear_boundary.KIND:
            if (not linear_boundary.authority_label(authority)
                    or not linear_boundary.transport_matches(authority,transport)):
                raise ValueError('independent_linear_stage_boundary_transport_required')
            proof=authority['source_linear_stage_ground_boundary']
            cohort=proof['explicit_selected_source_edge_uuids']
            for peer in cohort:
                other=by_id.get(peer,{}).get('authority',{})
                peer_proof=other.get('source_linear_stage_ground_boundary',{})
                if (other.get('kind')!=linear_boundary.KIND
                        or peer_proof.get('explicit_selected_source_edge_uuids')!=cohort
                        or peer_proof.get('source_proposal_sha256')!=proof['source_proposal_sha256']
                        or peer_proof.get('independent_native_transport')!=proof['independent_native_transport']):
                    raise ValueError('complete_same_Source_stage_ground_cut_cohort_required')
        continuation_roots=(continuation.ground_root_authorities(authority)
            if authority.get('kind')==continuation.KIND else None)
        if authority.get('kind')==continuation.KIND:
            proof=authority.get('source_ground_continuation',{})
            required=set(proof.get('required_existing_ground_cut_uuids',[]))
            if (continuation_roots is None or not required<=by_id.keys()
                    or any(by_id[u].get('authority')!=root
                        for root in continuation_roots for u in [root['native_source_uuid']])):
                raise ValueError('continuation_requires_same_complete_original_ground_cut_roots')
        ground_class_leg=(authority.get('kind')in ground_kinds
            and edge.GetNetname()=='GND' and authority.get('source_width_nm')==edge.GetWidth()
            and type(authority.get('source_full_class_width_nm')) is int
            and 0<edge.GetWidth()<=authority['source_full_class_width_nm'])
        rated=authority.get('source_plan',{})
        rated_class_leg=(authority.get('kind')=='unchanged_full_current_source_edge'
            and type(rated)is dict and rated.get('scope')=='exact_bounded_whole_current_planar_reflow'
            and rated.get('retired_track_uuids')==[uid] and rated.get('net')==edge.GetNetname()
            and rated.get('layer_id')==int(edge.GetLayer()) and rated.get('width_nm')==edge.GetWidth()
            and type(rated.get('full_current_floor_nm'))is int
            and 0<rated['full_current_floor_nm']<=edge.GetWidth()<=10000000)
        if (edge.GetClass()!='PCB_TRACK' or edge.HasSolderMask() or edge.GetParentGroup() is not None
                or authority['kind'] not in accepted or authority['native_source_uuid']!=uid
                or row['change']['net']!=edge.GetNetname()
                or not (0<edge.GetWidth()<=350000 or ground_class_leg or rated_class_leg)
                or not graph.Add(edge)):
            raise ValueError('additional_cut_component_source_ownership_changed')
    remaining=set(by_id);groups=[]
    while remaining:
        tick();root=min(remaining)
        connected={root}|{force._uid(i) for i in graph.GetConnectedItems(source[root])}
        members=remaining&connected
        if not members:raise ValueError('native_additional_cut_component_empty')
        remaining-=members;groups.append(sorted(members))
    pads=[p for fp in parent.GetFootprints() for p in fp.Pads()]
    targets={force._uid(p):p for fp in private.GetFootprints() for p in fp.Pads()}
    retained=[*pads,*(t for uid,t in source.items() if uid not in retired)]
    if len(retained)>16384:raise ValueError('macro_cut_component_native_inventory_bound')
    result={};records=[]
    for ids in groups:
        tick();edges=[source[u] for u in ids];net=edges[0].GetNetname();face=int(edges[0].GetLayer())
        kinds={by_id[u]['authority']['kind'] for u in ids}
        if ((len(kinds)!=1 and not kinds<=ground_kinds)
                or any(t.GetNetname()!=net or t.GetLayer()!=face for t in edges)):
            raise ValueError('one_exact_net_face_and_authority_per_cut_component_required')
        if (net=='GND')!=(bool(kinds)and kinds<=ground_kinds):
            raise ValueError('ground_and_ordinary_or_rated_cut_ownership_not_interchangeable')
        for uid in ids:
            authority=by_id[uid]['authority']
            if authority.get('kind')==continuation.KIND:
                required=set(authority['source_ground_continuation']['required_existing_ground_cut_uuids'])
                if not required<=set(ids):
                    raise ValueError('continuation_roots_must_share_same_actual_native_cut_component')
        ports=[];contacts=[]
        for item in retained:
            tick()
            if item.GetNetname()!=net or not item.IsOnLayer(face):continue
            box=item.GetBoundingBox()
            touching=[t for t in edges if t.GetBoundingBox().Intersects(box)
                and t.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face),0)]
            if not touching:continue
            uid=force._uid(item)
            if item.GetClass()=='PAD':
                if uid not in targets:raise ValueError('literal_surviving_component_pad_missing')
                p=targets[uid]
                projected=[dict(pad_uuid=uid,at_nm=list(p.GetPosition()),
                    layers=[int(l) for l in p.GetLayerSet().CuStack()
                        if private.IsLayerEnabled(l)])]
                original=dict(pad_uuid=uid,at_nm=list(item.GetPosition()),layers=[face])
            else:
                at=(tuple(item.GetPosition()) if item.GetClass()=='PCB_VIA' else
                    _contact_site(touching[0],item,face))
                original=dict(native_uuids=[uid],at_nm=list(at),layers=[face])
                projected=project_contacts(parent,private,original,transport,retired)
            contacts.append(dict(source_item_uuid=uid,source_class=item.GetClass(),
                source_contact=original,contacting_owned_edge_uuids=sorted(force._uid(t) for t in touching),
                projected_literal_ports=copy.deepcopy(projected)))
            ports+=projected
        if not 2<=len(ports)<=16:
            raise ValueError('cut_component_needs_two_to_sixteen_actual_surviving_ports:'+str(len(ports)))
        def signature(p):return (p.get('pad_uuid',''),tuple(p.get('native_uuids',())),tuple(p['at_nm']),tuple(p['layers']))
        if len({signature(p) for p in ports})!=len(ports):raise ValueError('ambiguous_duplicate_cut_component_port')
        # This is just a finite topology proposal. Native obstacle-aware
        # routing still chooses the actual paths, and saved receiving must
        # independently preserve EVERY old terminal/copper partition.
        anchor=min(ports,key=lambda p:(sum(math.dist(p['at_nm'],q['at_nm']) for q in ports),signature(p)))
        key='macro_boundary:'+ids[0];keys=[];width=max(t.GetWidth() for t in edges)
        for target in sorted(ports,key=signature):
            if target is anchor:continue
            if target['at_nm']==anchor['at_nm'] and set(target['layers'])&set(anchor['layers']):continue
            name=key+('' if not keys else ':component_port:'+str(len(keys)))
            result[name]=dict(kind='source_boundary',net=str(net),a=copy.deepcopy(anchor),b=copy.deepcopy(target),
                width_nm=width,exact_additional_macro_component_source_ownership=[by_id[u]['authority'] for u in ids],
                every_surviving_source_component_port_mandatory=True)
            keys.append(name)
        records.append(dict(source_extra_edge_uuids=ids,net=str(net),layer_id=face,
            original_authorities=[by_id[u]['authority'] for u in ids],surviving_contacts=contacts,
            request_ids=keys,retired_internal_bends_are_not_anchors=True,
            all_coincident_ports_need_native_partition_receiving=not keys,
            new_current_or_routing_or_fabrication_authority=False))
    tick()
    return result,records
