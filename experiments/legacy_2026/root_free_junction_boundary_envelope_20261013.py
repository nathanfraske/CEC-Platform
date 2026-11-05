"""Source-native free-junction chain expansion for PRIVATE reconstruction.

An obstructed degree-two joint is not a terminal. Reach the next clear native
anchor instead of asking a maze to start inside foreign copper. Never cross
a pad, barrel, branch, width boundary or typed current-allocation boundary.
This proposes a cut envelope, not permission to remove or publish copper.
"""
import time
import json
import pcbnew
import cec_force_current as force
import cec_fr as fr


def expand(board,rows,*,clearance_for,timeout_s=3.,max_extension_tracks=8,max_extension_mm=25.,
           provisional_reconstruction_track_uuids=(),maximum_input_edges=64):
    if (not callable(clearance_for) or not 0<timeout_s<=10 or
            type(max_extension_tracks) is not int or not 1<=max_extension_tracks<=8 or
            not 0<max_extension_mm<=25 or type(maximum_input_edges) is not int
            or not 1<=maximum_input_edges<=128 or not 1<=len(rows)<=maximum_input_edges):
        raise ValueError('bounded_free_junction_envelope_policy_required')
    deadline=time.monotonic()+timeout_s
    tracks=list(board.GetTracks());pads=[p for f in board.GetFootprints() for p in f.Pads()]
    if len(tracks)>8192 or len(pads)>4096:raise ValueError('bounded_native_junction_inventory_required')
    byid={force._uid(t):t for t in tracks};pending={r['uid'] for r in rows};used=set();result=[]
    if type(provisional_reconstruction_track_uuids) not in (list,tuple,set,frozenset):
        raise ValueError('literal_bounded_free_junction_provisional_track_scope_required')
    provisional=set(provisional_reconstruction_track_uuids)
    if (len(provisional)>256 or len(provisional)!=len(provisional_reconstruction_track_uuids) or
            not provisional<=byid.keys() or any(byid[u].GetClass()!='PCB_TRACK' for u in provisional)):
        raise ValueError('literal_bounded_free_junction_provisional_track_scope_required')
    caches={}
    def groups(t):return sorted(force._uid(g) for g in board.Groups() if g.ContainsItem(t))
    def typed(t):return any(g.ContainsItem(t) and g.GetName().startswith('CEC_LOCAL_SUPPLY_ALLOCATION_V1|')
        for g in board.Groups())
    for original in rows:
        row=dict(original);extensions=[];length=0.;gap=clearance_for(row['net'])
        key=(row['code'],row['layer'])
        if key not in caches:
            zones,copper=fr._identified_foreign_shape_indexes(board,row['layer'],{row['code']})
            if provisional:
                native_rows=copper.get('rows',()) if isinstance(copper,dict) else copper
                copper=fr._bucket_foreign_shapes([r for r in native_rows
                    if (r[2] or {}).get('uuid') not in provisional])
            caches[key]=(zones,copper)
        zones,copper=caches[key]
        for port in ('start','end'):
            at=tuple(row[port]);chain=set(row.get('pending_member_uuids',[row['uid']]));previous=byid[row['uid']]
            while fr._snapshot_foreign_blockers(pcbnew.VECTOR2I(*at),pcbnew.VECTOR2I(*at),
                    row['width'],gap,zones,copper):
                if time.monotonic()>=deadline:raise ValueError('native_free_junction_envelope_deadline')
                cap=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*at),pcbnew.VECTOR2I(*at),row['width'])
                native_pads=[force._uid(p) for p in pads if p.GetNetCode()==row['code'] and
                    p.IsOnLayer(row['layer']) and p.GetEffectiveShape(row['layer']).Collide(cap,0)]
                native_barrels=[force._uid(t) for t in tracks if t.GetClass()=='PCB_VIA' and
                    t.GetNetCode()==row['code'] and t.IsOnLayer(row['layer']) and
                    t.GetEffectiveShape(row['layer']).Collide(cap,0)]
                if native_pads or native_barrels:
                    raise ValueError(('blocked_junction_is_actual_native_pad:' if native_pads else
                        'blocked_junction_is_actual_native_barrel:')+json.dumps(dict(
                            requested_track_uuid=row['uid'],at_nm=list(at),net=row['net'],
                            layer=int(row['layer']),width_nm=row['width'],native_pad_uuids=native_pads,
                            native_barrel_uuids=native_barrels,
                            actual_foreign_blockers=fr._snapshot_foreign_blockers(pcbnew.VECTOR2I(*at),pcbnew.VECTOR2I(*at),
                                row['width'],gap,zones,copper)[:16]),sort_keys=True))
                touching=[t for t in tracks if t.GetClass()=='PCB_TRACK' and
                    t.GetNetCode()==row['code'] and t.GetLayer()==row['layer'] and
                    t.GetEffectiveShape(row['layer']).Collide(cap,0)]
                adjacent=[t for t in touching if force._uid(t) not in chain]
                if (len(adjacent)!=1 or any(force._uid(t) not in chain|{force._uid(adjacent[0])}
                       for t in touching)):
                    raise ValueError('blocked_junction_not_unambiguous_degree_two:'+json.dumps(dict(
                        requested_track_uuid=row['uid'],at_nm=list(at),net=row['net'],
                        layer=int(row['layer']),width_nm=row['width'],
                        touching_native_tracks=[dict(uuid=force._uid(t),width_nm=t.GetWidth(),
                            start_nm=list(t.GetStart()),end_nm=list(t.GetEnd())) for t in touching],
                        whole_source_owned_branch_transaction_required=True),sort_keys=True))
                other=adjacent[0];uid=force._uid(other)
                ends=[tuple(other.GetStart()),tuple(other.GetEnd())]
                if (uid in pending|used or at not in ends or other.GetWidth()!=row['width'] or
                        groups(other)!=groups(previous) or typed(other) or typed(previous)):
                    # Exact refusal context is retained with the diagnostic
                    # receipt. It cannot silently become a looser cut scope.
                    raise ValueError('free_junction_width_group_anchor_or_pending_boundary:'+json.dumps(dict(
                        requested_track_uuid=row['uid'],at_nm=list(at),
                        adjacent_track_uuid=uid,adjacent_already_pending=uid in pending,
                        adjacent_already_consumed=uid in used,exact_endpoint=at in ends,
                        source_width_nm=row['width'],adjacent_width_nm=other.GetWidth(),
                        source_group_uuids=groups(previous),adjacent_group_uuids=groups(other),
                        typed_allocation_boundary=typed(other) or typed(previous)),sort_keys=True))
                if len(extensions)>=max_extension_tracks:raise ValueError('native_free_junction_chain_count_bound')
                length+=other.GetLength()/1e6
                if length>max_extension_mm:raise ValueError('native_free_junction_chain_length_bound')
                at=ends[1] if ends[0]==at else ends[0]
                chain.add(uid);used.add(uid);extensions.append(uid);previous=other
            row[port]=at
        row['envelope_extension_uuids']=extensions
        row['envelope_extension_length_mm']=length
        result.append(row)
    return result,sorted(used)
