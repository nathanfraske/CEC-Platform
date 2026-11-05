"""Source-typed endpoint-chain proposals, never automatic retirement authority.

Avoid ending a cooperative rebuild at an arbitrary raster/trace vertex inside
the same obstruction. Walk only actual native same-width, same-face endpoints
from one explicitly selected, already full-load-rated small supply edge. Real
pads, barrels, fills, tees, groups and width changes stop extension. Every
proposed edge is independently retyped by the existing source receiver; that
receiver also owns all interior contacts and original conductor partitions.
No board, reference, coordinate, current split or load assumption appears here.
"""
import math,time
import pcbnew
import cec_force_current as force
import cec_rated_branch_repair as rated
import cec_field_coupling as field


def propose(board, source, *, board_hint, seed_track_uuid,
            max_source_track_mm=8.,max_source_width_mm=.35,
            max_retired_tracks=8,timeout_s=10.):
    if (type(seed_track_uuid) is not str or not seed_track_uuid
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10.):
        raise ValueError('bounded_source_typed_chain_scope_required')
    deadline=time.monotonic()+timeout_s
    before=field._field_snapshot_inventory(board)
    scope=dict(max_source_track_mm=max_source_track_mm,
        max_source_width_mm=max_source_width_mm,max_retired_tracks=max_retired_tracks)
    initial=rated.plan(board,source,board_hint=board_hint,
        retired_track_uuids=[seed_track_uuid],timeout_s=timeout_s,**scope)
    material=[*board.GetTracks(),*(p for f in board.GetFootprints() for p in f.Pads()),
        *[z for z in board.Zones() if not z.GetIsRuleArea()]]
    if len(material)>32768:raise ValueError('source_chain_native_inventory_bound')
    index={force._uid(i):i for i in material}
    seed=index[seed_track_uuid];net=str(seed.GetNetname());layer=int(seed.GetLayer())
    width=int(seed.GetWidth());seen={seed_track_uuid};stops=[]
    def tick():
        if time.monotonic()>=deadline:raise ValueError('source_chain_scope_deadline')
    def contacts(at,skip):
        rows=[]
        for item in material:
            tick();uid=force._uid(item)
            if uid in skip or item.GetNetname()!=net or not item.IsOnLayer(layer):continue
            if item.GetClass()=='PAD' and item.GetAttribute()==pcbnew.PAD_ATTRIB_NPTH:continue
            if item.GetClass()=='ZONE':
                if not item.IsFilled() or not item.HasFilledPolysForLayer(layer):
                    raise ValueError('source_chain_native_fill_unknown')
                shape=item.GetFilledPolysList(layer)
            else:shape=item.GetEffectiveShape(layer)
            if shape.Collide(pcbnew.SHAPE_SEGMENT(at,at,1),0):rows.append(item)
        return rows
    def interior_contacts(edge):
        # Endpoint degree alone misses a T-junction midway along a conductor.
        # Detect actual native material, never bbox adjacency, before offering
        # that edge as part of a simple linear scope. Saved partition receiving
        # remains independent even after this conservative proposal stop.
        hits=[];uid=force._uid(edge);shape=edge.GetEffectiveShape(layer)
        probes=[pcbnew.SHAPE_SEGMENT(at,at,1) for at in (edge.GetStart(),edge.GetEnd())]
        for item in material:
            tick();other=force._uid(item)
            if other==uid or item.GetNetname()!=net or not item.IsOnLayer(layer):continue
            if item.GetClass()=='PAD' and item.GetAttribute()==pcbnew.PAD_ATTRIB_NPTH:continue
            if item.GetClass()=='ZONE':
                if not item.IsFilled() or not item.HasFilledPolysForLayer(layer):
                    raise ValueError('source_chain_native_fill_unknown')
                actual=item.GetFilledPolysList(layer)
            else:actual=item.GetEffectiveShape(layer)
            if actual.Collide(shape,0) and not any(actual.Collide(p,0) for p in probes):hits.append(other)
        return sorted(hits)
    if interior_contacts(seed):raise ValueError('source_chain_seed_has_retained_interior_contact')
    for origin in (seed.GetStart(),seed.GetEnd()):
        at=origin;edge=seed
        while True:
            tick();neighbors=contacts(at,{force._uid(edge)})
            if len(neighbors)!=1:
                stops.append(dict(at_nm=list(at),reason='native_endpoint_contact_count',
                    native_uuids=sorted(force._uid(i) for i in neighbors)));break
            item=neighbors[0];uid=force._uid(item)
            if uid in seen:raise ValueError('source_chain_cycle_or_revisit')
            if (item.GetClass()!='PCB_TRACK' or item.GetParentGroup() is not None
                    or item.GetWidth()!=width or item.GetLayer()!=layer
                    or tuple(at) not in (tuple(item.GetStart()),tuple(item.GetEnd()))):
                stops.append(dict(at_nm=list(at),reason='retained_native_contact_or_width_boundary',
                    native_uuids=[uid]));break
            if len(seen)>=max_retired_tracks:
                raise ValueError('source_chain_scope_incomplete_at_explicit_work_bound')
            if not 0<item.GetLength()<=max_source_track_mm*1e6:
                stops.append(dict(at_nm=list(at),reason='retained_native_source_span_boundary',
                    native_uuids=[uid]));break
            hidden=interior_contacts(item)
            if hidden:
                stops.append(dict(at_nm=list(at),reason='retained_native_interior_contact',
                    native_uuids=hidden,retained_track_uuid=uid));break
            seen.add(uid);far=item.GetEnd() if item.GetStart()==at else item.GetStart()
            edge=item;at=far
    remaining=deadline-time.monotonic()
    if remaining<=0:raise ValueError('source_chain_scope_deadline')
    proof=rated.plan(board,source,board_hint=board_hint,retired_track_uuids=sorted(seen),
        timeout_s=min(10.,remaining),**scope)
    if (proof['contracts']!=initial['contracts']
            or proof['source_sha256']!=initial['source_sha256']):
        raise ValueError('source_chain_scope_source_or_load_contract_changed')
    if before!=field._field_snapshot_inventory(board):
        raise ValueError('source_chain_scope_native_board_changed')
    return dict(schema=1,scope='source_typed_endpoint_chain_proposal',seed_track_uuid=seed_track_uuid,
        source_sha256=force._hash(source),retired_track_uuids=sorted(seen),source_plan=proof,
        native_extension_stops=stops,native_endpoint_walk_complete=True,
        interior_contacts_owned_by_independent_receiving=True,source_mutated=False,
        source_current_reduced=False,automatic_retirement_authorized=False,
        routing_admitted=False,release_authority=False)
