"""Retire only straight Source copper wholly duplicated by an unchanged pad.

An outward-expanded entire track capsule must fit inside one same-net native
SMD pad with positive margin. No proximity, centreline, pad box, same-net
label, zone clipping, width reduction or new current budget proves coverage.
Exact Source reconstruction keeps every survivor and all unrelated board,
group and sidecar state. Whole-board native/current/Kelvin/return/stack gates
remain separate and mandatory; this is physical-equivalence authority only.
"""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items


def _deadline(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=10:
        raise ValueError('bounded_pad_material_retirement_lease_required')
    return time.monotonic()+seconds


def plan(board,track_uuids,*,allow_owned_locked=False,coverage_margin_nm=10,timeout_s=10.):
    deadline=_deadline(timeout_s)
    if (type(track_uuids) not in (list,tuple) or not 1<=len(track_uuids)<=16
            or len(set(track_uuids))!=len(track_uuids)
            or any(type(u) is not str or not u for u in track_uuids)
            or type(allow_owned_locked) is not bool or type(coverage_margin_nm) is not int
            or not 1<=coverage_margin_nm<=1000):
        raise ValueError('literal_bounded_source_pad_retirement_scope_required')
    tracks={force._uid(t):t for t in board.GetTracks()}
    pads=[p for f in board.GetFootprints() for p in f.Pads()]
    if len(tracks)+len(pads)>32768:raise ValueError('source_pad_retirement_inventory_bound')
    if not set(track_uuids)<=tracks.keys():raise ValueError('original_pad_contained_track_identity_required')
    binding=row._source_binding(board);records=[]
    for uid in sorted(track_uuids):
        if time.monotonic()>=deadline:raise ValueError('source_pad_retirement_deadline')
        t=tracks[uid];face=int(t.GetLayer())
        groups=[g for g in board.Groups() if g.ContainsItem(t)]
        if (t.GetClass()!='PCB_TRACK' or t.GetNetCode()<=0 or not t.GetNetname()
                or face not in (pcbnew.F_Cu,pcbnew.B_Cu) or t.HasSolderMask()
                or t.GetWidth()<=0 or t.GetLength()<=0 or t.IsLocked() and not allow_owned_locked
                or len(groups)>1 or any(g.IsLocked() or g.GetParentGroup() is not None
                    or g.GetName()!=fr.ENDPOINT_NECKDOWN_GROUP for g in groups)):
            raise ValueError('plain_or_exact_factory_endpoint_source_track_required')
        outer=pcbnew.SHAPE_POLY_SET()
        t.TransformShapeToPolygon(outer,face,coverage_margin_nm,1,pcbnew.ERROR_OUTSIDE,False)
        witnesses=[]
        for pad in pads:
            if time.monotonic()>=deadline:raise ValueError('source_pad_retirement_deadline')
            if (pad.GetNetCode()!=t.GetNetCode() or not pad.IsOnLayer(face)
                    or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.HasHole()
                    or pad.GetParentFootprint().IsDNP()
                    or pad.GetShape() not in (pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,
                        pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL)):
                continue
            inner=pad.GetEffectivePolygon(face,pcbnew.ERROR_INSIDE)
            if inner.OutlineCount()!=1 or inner.HoleCount(0):continue
            missing=pcbnew.SHAPE_POLY_SET(outer);missing.BooleanSubtract(inner)
            if not missing.OutlineCount():
                witnesses.append(dict(pad_uuid=force._uid(pad),footprint_uuid=force._uid(pad.GetParentFootprint()),
                    pad_number=pad.GetNumber(),pad_polygon_sha256=hashlib.sha256(inner.Format().encode()).hexdigest()))
        if not witnesses:raise ValueError('entire_source_capsule_not_inside_one_unchanged_native_smd_land')
        records.append(dict(track_uuid=uid,net=str(t.GetNetname()),layer=face,
            source_track_polygon_sha256=hashlib.sha256(outer.Format().encode()).hexdigest(),
            containing_source_pads=sorted(witnesses,key=lambda q:q['pad_uuid']),
            source_group_uuid=force._uid(groups[0]) if groups else None,
            source_track_lock_retained_until_explicit_retirement=bool(t.IsLocked())))
    if binding!=row._source_binding(board):raise ValueError('source_changed_during_pad_material_observation')
    return dict(schema=1,scope='strict_native_smd_pad_duplicated_track_material',
        source_native_binding=binding,track_uuids=sorted(track_uuids),allow_owned_locked=allow_owned_locked,
        coverage_margin_nm=coverage_margin_nm,records=records,
        physical_copper_union_unchanged=True,current_qualified=False,release_authority=False)


def materialize(board,proposal,*,timeout_s=10.):
    fresh=plan(board,proposal['track_uuids'],allow_owned_locked=proposal['allow_owned_locked'],
        coverage_margin_nm=proposal['coverage_margin_nm'],timeout_s=timeout_s)
    if fresh!=proposal:raise ValueError('stale_or_forged_native_pad_material_retirement')
    live={force._uid(t):t for t in board.GetTracks()}
    # The shared deletion primitive also refuses dependencies encoded in
    # typed supply-allocation annotations, before touching any native object.
    discarded=discard_items(board,[live[uid] for uid in fresh['track_uuids']])
    return dict(ok=True,complete=True,errors=[],retired_track_uuids=fresh['track_uuids'],
        retired_objects=discarded,physical_copper_union_unchanged=True,
        new_capacity_credited=False,current_qualified=False,routing_admitted=False,release_authority=False)


def discover(board,*,touching_track_uuids=(),excluded_track_uuids=(),allow_owned_locked=False,
             max_tracks=8,timeout_s=10.):
    """Find actual duplicated material, optionally next to a selected operation.

    Physical contact, net and face select local work; distance and board/refdes
    rules do not. The named operation's tracks are always protected. A finite
    empty menu proves no global impossibility and grants no removal authority.
    """
    deadline=_deadline(timeout_s)
    if (type(max_tracks) is not int or not 1<=max_tracks<=16
            or type(touching_track_uuids) not in (tuple,list)
            or type(excluded_track_uuids) not in (tuple,list)
            or len(touching_track_uuids)>16 or len(excluded_track_uuids)>64
            or any(type(u) is not str or not u for u in [*touching_track_uuids,*excluded_track_uuids])):
        raise ValueError('bounded_native_pad_material_discovery_required')
    live={force._uid(t):t for t in board.GetTracks()};protected=set(touching_track_uuids)|set(excluded_track_uuids)
    if not protected<=live.keys():raise ValueError('actual_source_pad_discovery_context_required')
    if any(live[u].GetClass()!='PCB_TRACK' for u in touching_track_uuids):
        raise ValueError('straight_source_operation_context_required')
    selected=[];refusals=[];examined=0
    for uid,t in sorted(live.items()):
        if time.monotonic()>=deadline:raise ValueError('source_pad_material_discovery_deadline')
        if uid in protected or t.GetClass()!='PCB_TRACK':continue
        if touching_track_uuids and not any(t.GetNetCode()==live[u].GetNetCode()
                and t.GetLayer()==live[u].GetLayer()
                and t.GetEffectiveShape(t.GetLayer()).Collide(live[u].GetEffectiveShape(t.GetLayer()),0)
                for u in touching_track_uuids):continue
        examined+=1
        try:
            plan(board,[uid],allow_owned_locked=allow_owned_locked,
                timeout_s=max(.001,deadline-time.monotonic()))
            selected.append(uid)
        except ValueError as exc:refusals.append(dict(track_uuid=uid,reason=str(exc)))
        if len(selected)>=max_tracks:break
    proposal=plan(board,selected,allow_owned_locked=allow_owned_locked,
        timeout_s=max(.001,deadline-time.monotonic())) if selected else None
    return dict(ok=True,complete=True,examined=examined,plan=proposal,refusals=refusals,
        operation_tracks_retained=sorted(touching_track_uuids),
        exhaustive_global_inventory_claimed=False,routing_admitted=False,release_authority=False)


def receive(source,candidate,proposal,*,timeout_s=10.):
    deadline=_deadline(timeout_s)
    result=dict(ok=False,complete=False,errors=[],physical_copper_union_unchanged=False,
        new_capacity_credited=False,current_qualified=False,routing_admitted=False,release_authority=False)
    try:
        source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
        if source==candidate:raise ValueError('distinct_pad_material_source_and_child_required')
        epoch=force._code_identity();families=[force._family(path) for path in (source,candidate)]
        if force._sidecars(source)!=force._sidecars(candidate):raise ValueError('pad_material_sidecars_changed')
        board=pcbnew.LoadBoard(str(source));proof=materialize(board,proposal,timeout_s=max(.001,deadline-time.monotonic()))
        with tempfile.TemporaryDirectory(prefix='cec-pad-material-replay-') as work:
            expected=force._copy_family(source,Path(work)/'expected');field._save_field_snapshot(board,expected)
            if force._preservation_snapshot(expected)!=force._preservation_snapshot(candidate):
                raise ValueError('pad_material_entire_native_source_reconstruction_differs')
        parent,child=[pcbnew.LoadBoard(str(path)) for path in (source,candidate)]
        parts=ordinary._partition(parent,deadline,retired_uuids=set(proof['retired_track_uuids']))
        keys=set().union(*parts) if parts else set()
        after=ordinary._partition(child,deadline,retained_keys=keys)
        if not all(any(part<=other for other in after) for part in parts):
            raise ValueError('pad_material_retirement_lost_surviving_native_partition')
        if (time.monotonic()>=deadline or epoch!=force._code_identity()
                or families!=[force._family(path) for path in (source,candidate)]):
            raise ValueError('pad_material_source_epoch_or_lease_changed')
        result.update(proof,exact_entire_saved_source_reconstruction=True,
            every_surviving_native_partition_preserved=True,source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate))
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
