"""Inventory retained ordinary crossings of explicit native reservations.

Avoiding a future corridor only while emitting NEW traces leaves its old
crossings in place forever. This read-only planner identifies those literal
source tracks for a bounded whole-source reconstruction transaction. It does
not retire copper, alter locks, authorize current, acquire another island or
admit a saved board. Existing branch/terminal/delta receivers remain owed.
"""
import math
import time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary


def _identity(t):
    return (t.GetClass(),str(t.GetNetname()),int(t.GetNetCode()),int(t.GetLayer()),
        int(t.GetWidth()),tuple(t.GetStart()),tuple(t.GetEnd()),bool(t.IsLocked()))


def plan(parent,board,reservations,*,source_path,board_hint,clearance_for,
         already_pending_uuids=(),maximum_tracks=64,timeout_s=3.):
    if (type(reservations) not in (list,tuple) or not 1<=len(reservations)<=40
            or type(already_pending_uuids) not in (list,tuple,set,frozenset)
            or len(already_pending_uuids)>256
            or len(set(already_pending_uuids))!=len(already_pending_uuids)
            or any(type(u) is not str or not u for u in already_pending_uuids)
            or not callable(clearance_for) or type(board_hint) is not str or not board_hint
            or type(maximum_tracks) is not int or not 1<=maximum_tracks<=64
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or Path(parent.GetFileName()).resolve()!=Path(source_path).resolve()
            or Path(board.GetFileName()).resolve()!=Path(source_path).resolve()):
        raise ValueError('bounded_original_source_reserved_corridor_scope_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('reserved_corridor_track_scope_deadline')
    original={force._uid(t):t for t in parent.GetTracks()}
    items={force._uid(t):t for t in board.GetTracks()}
    if len(original)>8192 or len(items)>8192 or len(items)!=len(list(board.GetTracks())):
        raise ValueError('bounded_unique_reserved_corridor_native_inventory_required')
    ids=[force._uid(t) for t in reservations]
    if (len(set(ids))!=len(ids) or any(u in original or u not in items or items[u]!=t
            or t.GetClass() not in ('PCB_TRACK','PCB_VIA') for u,t in zip(ids,reservations))):
        raise ValueError('literal_unsaved_native_reservation_objects_required')
    eligible=set(ordinary.eligible_nets(parent,Path(source_path),board_hint))
    pending=set(already_pending_uuids);obstacles={};gaps={}
    def gap(net):
        if net not in gaps:
            value=clearance_for(net)
            if type(value) is not int or not 0<=value<=2000000:
                raise ValueError('literal_reserved_corridor_native_clearance_required')
            gaps[net]=value
        return gaps[net]
    for t in reservations:
        for layer in board.GetEnabledLayers().CuStack():
            if t.IsOnLayer(layer):
                obstacles.setdefault(int(layer),[]).append((t,t.GetEffectiveShape(layer)))
    rows=[];refusals=[];pending_contacts=[]
    for uid,t in sorted(items.items()):
        tick()
        if t.GetClass()!='PCB_TRACK' or uid in ids:continue
        hits=[];shape=None
        for reserve,obstacle in obstacles.get(int(t.GetLayer()),[]):
            if reserve.GetNetCode()==t.GetNetCode():continue
            if shape is None:shape=t.GetEffectiveShape(t.GetLayer())
            clearance=max(gap(str(t.GetNetname())),gap(str(reserve.GetNetname())))
            if shape.Collide(obstacle,clearance):
                hits.append(dict(reservation_uuid=force._uid(reserve),
                    reservation_net=str(reserve.GetNetname()),clearance_nm=clearance))
        if not hits:continue
        if uid in pending:
            pending_contacts.append(dict(uuid=uid,witnesses=hits));continue
        old=original.get(uid);reason=None
        if old is None:reason='unscheduled_non_source_provisional_copper'
        elif old.GetClass()!='PCB_TRACK' or _identity(old)!=_identity(t):
            reason='retained_original_source_geometry_or_lock_changed'
        elif str(t.GetNetname()) not in eligible:reason='not_positive_source_ordinary_track'
        elif (any(g.ContainsItem(t) for g in board.Groups())
                or any(g.ContainsItem(old) for g in parent.Groups())):
            reason='source_owned_group_not_ordinary_scope'
        elif t.GetLength()<=0 or t.GetLength()>32000000 or not 0<t.GetWidth()<=350000:
            reason='finite_positive_source_ordinary_track_work_bound'
        if reason:
            refusals.append(dict(uuid=uid,net=str(t.GetNetname()),layer=int(t.GetLayer()),
                reason=reason,witnesses=hits));continue
        if len(rows)>=maximum_tracks:raise ValueError('reserved_corridor_original_track_union_bound')
        rows.append(dict(uuid=uid,net=str(t.GetNetname()),layer=int(t.GetLayer()),
            width_nm=int(t.GetWidth()),start_nm=list(t.GetStart()),end_nm=list(t.GetEnd()),
            source_locked=bool(t.IsLocked()),witnesses=hits))
    return dict(schema=1,source_sha256=force._hash(Path(source_path)),
        additional_source_ordinary_tracks=rows,already_scheduled_contacts=pending_contacts,
        unscoped_foreign_track_obstructions=refusals,
        all_foreign_track_obstructions_scoped=not refusals,
        exact_native_reservation_uuids=ids,native_board_mutated=False,
        automatic_retirement_authorized=False,source_width_and_lock_preserved=True,
        source_native_boundaries_partitions_delta_and_saved_receiving_required=True,
        current_or_pair_or_ground_authority=False,release_authority=False)
