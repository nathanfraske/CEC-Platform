"""Copper-equivalent partition at literal, already existing track contacts.

This exposes graph ports, not new electrical connections. Every fragment has
the exact source face, width and process; its collinear interval union is the
whole original capsule. No net role, current, cut, via-motion or release rights
follow from this purely representational preparation.
"""
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
import math
import tempfile
import time
import uuid

import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_route_quality as quality
from cec_native_items import discard_items


def _parameter(a, b, p):
    dx, dy = b[0]-a[0], b[1]-a[1]
    if (p[0]-a[0])*dy != (p[1]-a[1])*dx:
        raise ValueError('exact_native_partition_centreline_required')
    return Fraction(p[0]-a[0], dx) if dx else Fraction(p[1]-a[1], dy)


def _contact(a, b, c, d):
    """Exact lattice crossings, or peer endpoints for collinear overlaps."""
    dx, dy = b[0]-a[0], b[1]-a[1]
    ex, ey = d[0]-c[0], d[1]-c[1]
    cross = dx*ey-dy*ex
    if not cross:
        try:
            return [p for p in (c, d) if 0 < _parameter(a, b, p) < 1]
        except ValueError:
            return []
    t = Fraction((c[0]-a[0])*ey-(c[1]-a[1])*ex, cross)
    u = Fraction((c[0]-a[0])*dy-(c[1]-a[1])*dx, cross)
    if not (0 < t < 1 and 0 <= u <= 1):
        return []
    p = (Fraction(a[0])+t*dx, Fraction(a[1])+t*dy)
    return [tuple(map(int, p))] if all(q.denominator == 1 for q in p) else []


def plan(board, requests, *, source_path, board_hint, timeout_s=10.):
    if (type(requests) is not list or not 1 <= len(requests) <= 32
            or type(board_hint) is not str or not board_hint
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10
            or Path(source_path).resolve() != Path(board.GetFileName()).resolve()):
        raise ValueError('bounded_literal_native_track_partition_context_required')
    deadline = time.monotonic()+timeout_s
    live = {force._uid(t): t for t in board.GetTracks()}
    if len(live) > 16384:
        raise ValueError('native_track_partition_inventory_bound')
    sites = defaultdict(set)
    for r in requests:
        if time.monotonic() >= deadline:
            raise ValueError('native_track_partition_contact_deadline')
        if (type(r) is not dict or set(r) !=
                {'track_uuid', 'peer_uuid', 'point_nm', 'locked_source_requested'}
                or type(r['locked_source_requested']) is not bool
                or type(r['track_uuid']) is not str or type(r['peer_uuid']) is not str
                or r['track_uuid'] == r['peer_uuid']
                or not {r['track_uuid'], r['peer_uuid']} <= live.keys()
                or type(r['point_nm']) is not list or len(r['point_nm']) != 2
                or any(type(n) is not int or abs(n) > 2000000000 for n in r['point_nm'])):
            raise ValueError('literal_unique_native_track_contact_required')
        track, peer = live[r['track_uuid']], live[r['peer_uuid']]
        if (any(t.GetClass() != 'PCB_TRACK' or t.GetParentGroup() or t.HasSolderMask()
                or not 0 < t.GetLength() <= 32000000 or t.GetWidth() <= 0 for t in (track, peer))
                or any(g.ContainsItem(t) for g in board.Groups() for t in (track, peer))
                or not track.GetNetname() or track.GetNetCode() != peer.GetNetCode()
                or track.GetLayer() != peer.GetLayer()
                or not pcbnew.IsCopperLayer(track.GetLayer())
                or not board.IsLayerEnabled(track.GetLayer())
                or r['locked_source_requested'] != bool(track.IsLocked())):
            raise ValueError('unchanged_ungrouped_same_net_face_native_track_contact_required')
        a, b, c, d = map(tuple, (track.GetStart(), track.GetEnd(), peer.GetStart(), peer.GetEnd()))
        if not all(quality.is_canonical_stroke(x, y, tolerance_nm=0) for x, y in ((a,b),(c,d))):
            raise ValueError('canonical_native_track_partition_required')
        p = tuple(r['point_nm'])
        if (p not in _contact(a,b,c,d)
                or not track.GetEffectiveShape(track.GetLayer()).Collide(peer.GetEffectiveShape(track.GetLayer()),0)
                or min(math.dist(p,q) for q in (a,b)) < 10000):
            raise ValueError('actual_exact_interior_lattice_track_contact_required')
        if p in sites[r['track_uuid']]:
            raise ValueError('duplicate_native_track_partition_site')
        sites[r['track_uuid']].add(p)
    if len(sites) > 8 or any(len(v) > 8 for v in sites.values()):
        raise ValueError('bounded_native_track_partition_fragment_count_required')
    digest = force._hash(Path(source_path)); _, nodes = additive._nodes(Path(source_path)); ids = set(nodes)
    rows=[]
    for uid, points in sorted(sites.items()):
        t=live[uid]; a,b=tuple(t.GetStart()),tuple(t.GetEnd())
        ordered=[a,*sorted(points,key=lambda p:_parameter(a,b,p)),b]; fragments=[]
        for left,right in zip(ordered,ordered[1:]):
            new=str(uuid.uuid5(uuid.NAMESPACE_URL, f'cec-native-track-partition:{digest}:{uid}:{left}:{right}'))
            if new in ids:raise ValueError('native_track_partition_uuid_collision')
            ids.add(new);fragments.append(dict(uuid=new,start_nm=list(left),end_nm=list(right)))
        rows.append(dict(track_uuid=uid,net=str(t.GetNetname()),layer=int(t.GetLayer()),
            width_nm=int(t.GetWidth()),locked=bool(t.IsLocked()),fragments=fragments,
            exact_equal_width_collinear_capsule_union=True))
    return dict(schema=1,source_sha256=digest,source_binding=binding._source_binding(board),
        requests=requests,rows=rows,no_physical_copper_change=True,no_new_barrels=True,
        current_qualified=False,routing_admitted=False,release_authority=False)


def materialize(board, proposal, *, source_path, board_hint):
    if plan(board,proposal['requests'],source_path=source_path,board_hint=board_hint) != proposal:
        raise ValueError('stale_or_forged_native_track_partition_plan')
    live={force._uid(t):t for t in board.GetTracks()}; added=[];retired=[]
    for row in proposal['rows']:
        original=live[row['track_uuid']]; exemplar=original.Duplicate()
        discard_items(board,[original]);retired.append(row['track_uuid'])
        for fragment in row['fragments']:
            item=exemplar.Duplicate();item.m_Uuid.Clone(pcbnew.KIID(fragment['uuid']))
            item.SetStart(pcbnew.VECTOR2I(*fragment['start_nm']))
            item.SetEnd(pcbnew.VECTOR2I(*fragment['end_nm']));board.Add(item);added.append(force._uid(item))
    return dict(retired_track_uuids=retired,added_native_uuids=added,
        no_physical_copper_change=True,release_authority=False)


def receive(source,candidate,requests,*,board_hint,timeout_s=10.):
    result=dict(ok=False,complete=False,errors=[],release_authority=False,current_qualified=False,
        full_saved_current_fields_native_DRC_absolute_cuts_and_release_still_required=True)
    try:
        source,candidate=map(Path,(source,candidate));epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        proposal=plan(parent,requests,source_path=source,board_hint=board_hint,timeout_s=timeout_s)
        with tempfile.TemporaryDirectory(prefix='cec-native-track-partition-') as tmp:
            path=force._copy_family(source,Path(tmp)/'expected');expected=pcbnew.LoadBoard(str(path))
            q=plan(expected,requests,source_path=path,board_hint=board_hint,timeout_s=timeout_s)
            delta=materialize(expected,q,source_path=path,board_hint=board_hint)
            field._save_field_snapshot(expected,path)
            want_root,want=additive._nodes(path);got_root,got=additive._nodes(candidate)
            if (syntax._freeze(want_root)!=syntax._freeze(got_root) or want.keys()!=got.keys()
                    or any(syntax._freeze(want[u])!=syntax._freeze(got[u]) for u in want)):
                raise ValueError('exact_native_track_partition_saved_replay_differs')
        if force._sidecars(source)!=force._sidecars(candidate):
            raise ValueError('native_track_partition_source_sidecars_changed')
        first=ordinary._partition(parent,time.monotonic()+10.,retired_uuids=set(delta['retired_track_uuids']))
        keys=set().union(*first);last=ordinary._partition(child,time.monotonic()+10.,retained_keys=keys)
        if any(not any(p<=q for q in last) for p in first):
            raise ValueError('native_track_partition_retained_native_connectivity_lost')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('native_track_partition_source_or_code_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            code_identity=epoch,source_family_and_code_unchanged=True,
            exact_saved_replay=True,actual_copper_geometry_unchanged=True,
            all_surviving_native_partitions_preserved=True,**delta)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
