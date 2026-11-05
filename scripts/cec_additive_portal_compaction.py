"""Remove only provably unused NEW ordinary portal copper before saving.

An all-layer endpoint menu can offer a barrel and a pad-side stub even when
the selected continuation uses the same face. Do not manufacture that stub
or barrel solely because it appeared in the menu. Retained source copper,
groups, power/pair roles and component definitions are never edited here.
Native connectivity must prove every surviving old AND new partition intact.
Independent saved DRC/current/field/physical receiving remains mandatory.
"""
import math
import time
import pcbnew
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items


def _covered_by_source(track, retained):
    """Exact capsule containment, not approximate overlap or proximity."""
    a,b=tuple(track.GetStart()),tuple(track.GetEnd())
    for old in retained:
        if (old.GetClass()!='PCB_TRACK' or old.GetNetCode()!=track.GetNetCode()
                or old.GetLayer()!=track.GetLayer() or old.GetWidth()<track.GetWidth()):continue
        p,q=tuple(old.GetStart()),tuple(old.GetEnd());v=(q[0]-p[0],q[1]-p[1])
        square=v[0]**2+v[1]**2
        if not square:continue
        # Integer cross products preserve 1-nm distinctions. An offset or
        # slightly diagonal trace is not a covered source-centreline capsule.
        if all(v[0]*(r[1]-p[1])==v[1]*(r[0]-p[0])
                and 0<=(r[0]-p[0])*v[0]+(r[1]-p[1])*v[1]<=square for r in (a,b)):
            return force._uid(old)
    return None


def covered_by_collinear_union(track, retained):
    """Exact capsule cover by existing same-net/face sufficient-width tracks.

    This is constructive reuse only: no retained item is cut, moved, merged,
    narrowed or reclassified.  Integer projected intervals must cover the
    WHOLE proposed centreline without a gap.  Off-axis capsules, proximity,
    different faces/nets and insufficient widths never supply that proof.
    The enclosing caller still owns every current and terminal-path check.
    """
    if track.GetClass()!='PCB_TRACK':return None
    items=list(retained)
    if len(items)>16384:raise ValueError('bounded_existing_collinear_material_required')
    a,b=tuple(track.GetStart()),tuple(track.GetEnd());v=(b[0]-a[0],b[1]-a[1])
    square=v[0]**2+v[1]**2
    if not square:return None
    intervals=[]
    for old in items:
        if (old.GetClass()!='PCB_TRACK' or old.GetNetCode()!=track.GetNetCode()
                or old.GetLayer()!=track.GetLayer() or old.GetWidth()<track.GetWidth()):continue
        points=(tuple(old.GetStart()),tuple(old.GetEnd()))
        if any(v[0]*(p[1]-a[1])!=v[1]*(p[0]-a[0]) for p in points):continue
        lo,hi=sorted((p[0]-a[0])*v[0]+(p[1]-a[1])*v[1] for p in points)
        if hi<0 or lo>square:continue
        intervals.append((max(0,lo),min(square,hi),force._uid(old)))
    reach=0;witnesses=[]
    for lo,hi,uid in sorted(intervals):
        if lo>reach:break
        if hi<=reach:continue
        reach=hi;witnesses.append(uid)
        if reach>=square:return witnesses
    return None


def uncovered_collinear_segments(track,retained,*,max_parts=32):
    """Propose only missing centreline intervals; never change old metal.

    Exact integer collinearity, same net/face and sufficient width are
    mandatory. Unlike a proximity/overlap clip, every removed interval has
    an actual existing centreline witness. One-nanometre gaps remain gaps.
    This supplies no load, process, saved-connectivity or release authority.
    """
    if (track.GetClass()!='PCB_TRACK'or type(max_parts)is not int
            or not 1<=max_parts<=32 or track.GetWidth()<=0):
        raise ValueError('bounded_actual_collinear_track_projection_required')
    items=list(retained)
    if len(items)>16384:raise ValueError('bounded_existing_collinear_material_required')
    a,b=tuple(track.GetStart()),tuple(track.GetEnd());v=(b[0]-a[0],b[1]-a[1])
    if a==b or v[0]and v[1]and abs(v[0])!=abs(v[1]):
        raise ValueError('exact_octilinear_collinear_projection_required')
    axis=0 if v[0]else 1;length=abs(v[axis]);direction=1 if v[axis]>0 else -1
    intervals=[]
    for old in items:
        if (old.GetClass()!='PCB_TRACK'or old.GetNetCode()!=track.GetNetCode()
                or old.GetLayer()!=track.GetLayer()or old.GetWidth()<track.GetWidth()):continue
        p,q=tuple(old.GetStart()),tuple(old.GetEnd())
        if p==q or any(v[0]*(pnt[1]-a[1])!=v[1]*(pnt[0]-a[0])for pnt in(p,q)):continue
        lo,hi=sorted(direction*(pnt[axis]-a[axis])for pnt in(p,q))
        if hi<=0 or lo>=length:continue
        intervals.append((max(0,lo),min(length,hi),force._uid(old)))
    missing=[];reach=0;witnesses=[]
    for lo,hi,uid in sorted(intervals):
        if lo>reach:missing.append((reach,lo))
        if hi>reach:reach=hi;witnesses.append(uid)
    if reach<length:missing.append((reach,length))
    if len(missing)>max_parts:raise ValueError('bounded_missing_collinear_fragment_inventory_required')
    def at(distance):
        # Octilinear geometry makes every reconstructed coordinate integral;
        # do not round a non-native interception into a nearby contact.
        values=[a[k]+v[k]*distance//length for k in(0,1)]
        if any(v[k]*distance%length for k in(0,1)):
            raise ValueError('exact_integer_collinear_interval_endpoint_required')
        return values
    return dict(segments_nm=[[at(lo),at(hi)]for lo,hi in missing],
        covered_source_track_uuids=sorted(set(witnesses)),
        original_conductors_edited=False,current_authority=False,release_authority=False)


def _parts(items, retained, deadline):
    graph=pcbnew.CONNECTIVITY_DATA()
    live={force._uid(i):i for i in items}
    if len(live)!=len(items):raise ValueError('ambiguous_portal_material_identity')
    for item in items:
        if time.monotonic()>=deadline:raise ValueError('portal_compaction_deadline')
        if not graph.Add(item):raise ValueError('native_portal_material_unknown')
    pending=set(retained);result=[]
    while pending:
        if time.monotonic()>=deadline:raise ValueError('portal_compaction_deadline')
        uid=min(pending)
        reached={uid}|{force._uid(i) for i in graph.GetConnectedItems(live[uid])}
        part=pending&reached
        result.append(part);pending-=part
    return result


def compact(board, original_track_uuids, *, board_path, board_hint=None,
            timeout_s=2., max_new_items=128):
    """Private constructor-only cleanup; caller owns all non-source items.

    Ownership comes from the constructor's actual original UUID inventory,
    never DRC descriptions or a worker-authored removal list. Refusals leave
    the entire board unchanged. Same-net zones must have native filled copper;
    any other barrel contact or multiple contacted layers retains the via.
    """
    report=dict(schema=1,scope='native_new_ordinary_portal_compaction',removed=[],
        covered_tracks=[],unused_vias=[],board_mutated=False,
        all_surviving_native_partitions_preserved=False,release_authority=False,
        saved_board_receiving_still_required=True)
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(max_new_items) is not int or not 1<=max_new_items<=256
            or type(original_track_uuids) not in (set,list,tuple)
            or any(type(u) is not str or not u for u in original_track_uuids)):
        raise ValueError('bounded_constructor_portal_inventory_required')
    deadline=time.monotonic()+timeout_s
    original=set(original_track_uuids);material=list(board.GetTracks())
    ids={force._uid(i) for i in material}
    if len(ids)!=len(material) or not original<=ids:
        raise ValueError('exact_original_portal_material_inventory_required')
    incoming=[i for i in material if force._uid(i) not in original]
    if len(incoming)>max_new_items:
        report['reason']='new_portal_inventory_bound';return report
    eligible=ordinary.eligible_nets(board,board_path,board_hint or str(board_path))
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    retained=[i for i in material if force._uid(i) in original]
    candidates=[];covered=[];vias=[]
    try:
        for item in incoming:
            if time.monotonic()>=deadline:raise ValueError('portal_compaction_deadline')
            if (item.GetNetname() not in eligible or force._uid(item) in grouped
                    or item.GetClass()!='PCB_TRACK'):continue
            witness=_covered_by_source(item,retained)
            if witness:
                candidates.append(item);covered.append(dict(uuid=force._uid(item),
                    net=str(item.GetNetname()),exact_retained_capsule_uuid=witness))
        cut={force._uid(i) for i in candidates}
        pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
        zones=[z for z in board.Zones() if not z.GetIsRuleArea()]
        for item in incoming:
            if (item.GetClass()!='PCB_VIA' or force._uid(item) in grouped
                    or item.GetNetname() not in eligible):continue
            if time.monotonic()>=deadline:raise ValueError('portal_compaction_deadline')
            contacts=set();other_barrel=False
            for peer in [*material,*pads,*zones]:
                if time.monotonic()>=deadline:raise ValueError('portal_compaction_deadline')
                if (force._uid(peer)==force._uid(item) or force._uid(peer) in cut
                        or peer.GetNetCode()!=item.GetNetCode()):continue
                for layer in board.GetEnabledLayers().CuStack():
                    if not item.IsOnLayer(layer) or not peer.IsOnLayer(layer):continue
                    if peer.GetClass()=='ZONE':
                        if not peer.IsFilled() or not peer.HasFilledPolysForLayer(layer):
                            raise ValueError('same_net_portal_fill_unknown')
                        hit=peer.GetFilledPolysList(layer).Collide(item.GetEffectiveShape(layer),0)
                    else:hit=peer.GetEffectiveShape(layer).Collide(item.GetEffectiveShape(layer),0)
                    if hit:
                        contacts.add(int(layer));other_barrel|=peer.GetClass()=='PCB_VIA'
            if len(contacts)<=1 and not other_barrel:
                candidates.append(item);vias.append(dict(uuid=force._uid(item),
                    net=str(item.GetNetname()),contacted_layers=sorted(contacts)))
        if not candidates:
            report['reason']='no_proved_unused_new_portal';return report
        cuts={force._uid(i) for i in candidates};nets={i.GetNetCode() for i in candidates}
        relevant=[i for i in [*material,*pads,*zones] if i.GetNetCode() in nets]
        if len(relevant)>4096:raise ValueError('native_portal_partition_inventory_bound')
        survivors={force._uid(i) for i in relevant}-cuts
        old=_parts(relevant,survivors,deadline)
        new=_parts([i for i in relevant if force._uid(i) not in cuts],survivors,deadline)
        if any(not any(part<=q for q in new) for part in old):
            raise ValueError('unused_portal_claim_would_break_native_partition')
        if time.monotonic()>=deadline:raise ValueError('portal_compaction_deadline')
        discard_items(board,candidates)
        report.update(removed=sorted(cuts),covered_tracks=covered,unused_vias=vias,
            board_mutated=True,all_surviving_native_partitions_preserved=True,
            original_conductors_edited=False,reason='proved_new_portal_compacted')
    except ValueError as exc:report['reason']=str(exc)
    return report
