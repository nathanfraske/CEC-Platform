"""Explicit shorter geometry for an independently qualified Source escape.

Only the exact existing endpoint-exception group may change. Its native UUIDs,
locks, widths, face and current/class authority survive. This constructor is
not current, clearance, Kelvin, assembly or whole-board release admission.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as row
import cec_copper_echo as syntax
import cec_current_topology as topology
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_route_corner_contacts as contacts
import cec_route_dimensions as dimensions


def apply(source, board, *, track_uuids, vertices_nm, board_hint, timeout_s=10.):
    if (type(track_uuids) not in (list,tuple) or not 1<=len(track_uuids)<=4
            or len(set(track_uuids))!=len(track_uuids)
            or any(type(u) is not str or not u for u in track_uuids)
            or type(vertices_nm) not in (list,tuple) or len(vertices_nm)!=len(track_uuids)+1
            or any(type(at) not in (list,tuple) or len(at)!=2
                or any(type(x) is not int or abs(x)>10**10 for x in at) for at in vertices_nm)
            or type(board_hint) is not str or not board_hint
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('bounded_explicit_qualified_neckdown_reflow_required')
    deadline=time.monotonic()+timeout_s;source=Path(source).resolve()
    family=force._family(source,board_hint);parent=pcbnew.LoadBoard(str(source))
    if row._source_binding(parent)!=row._source_binding(board):
        raise ValueError('qualified_neckdown_exact_saved_source_required')
    with tempfile.TemporaryDirectory(prefix='cec-neckdown-source-') as work:
        observed=force._copy_family(source,Path(work)/'source')
        field._save_field_snapshot(board,observed)
        if force._preservation_snapshot(observed)!=force._preservation_snapshot(source):
            raise ValueError('qualified_neckdown_complete_native_source_identity_required')
    old={force._uid(t):t for t in parent.GetTracks()};new={force._uid(t):t for t in board.GetTracks()}
    if not set(track_uuids)<=old.keys():raise ValueError('qualified_neckdown_source_identity_required')
    tracks=[old[u] for u in track_uuids]
    if (any(t.GetClass()!='PCB_TRACK' for t in tracks)
            or len({(str(t.GetNetname()),int(t.GetLayer()),t.GetWidth()) for t in tracks})!=1):
        raise ValueError('qualified_neckdown_uniform_actual_source_chain_required')
    groups=[g for g in parent.Groups() if any(g.ContainsItem(t) for t in tracks)]
    if (len(groups)!=1 or groups[0].GetName()!=fr.ENDPOINT_NECKDOWN_GROUP or groups[0].IsLocked()
            or not all(groups[0].ContainsItem(t) for t in tracks)):
        raise ValueError('qualified_neckdown_exact_unlocked_endpoint_group_required')
    net=str(tracks[0].GetNetname());face=int(tracks[0].GetLayer());layer=parent.GetLayerName(face)
    spec=dimensions.project_resolver(source,board=parent)(net) or {}
    with force._thermal_hint(board_hint):
        domains=topology.board_current_domains(parent,board_hint=board_hint)
        authority=topology.current_contract_for_net(net,board_hint,domains)
    rated=dimensions.current_trace_widths(authority,(layer,),fab.active_profile_name(parent,hint=board_hint))[layer] if authority else 0
    full=math.ceil(max(float(spec.get('track_width') or 0),dimensions.board_limits(parent)['track_width'],rated)*1e6)
    clearance=max(int(parent.GetDesignSettings().m_MinClearance),math.ceil(float(spec.get('clearance') or 0)*1e6))
    qualified,rejected=fr._qualified_endpoint_neckdown_tracks(parent,tracks,full,required_clearance=clearance)
    if rejected or {force._uid(t) for t in qualified}!=set(track_uuids):
        raise ValueError('qualified_neckdown_source_geometry_not_qualified')
    # A complete ordered unbranched Source chain, not unrelated short wires.
    shared=[{tuple(a.GetStart()),tuple(a.GetEnd())}&{tuple(b.GetStart()),tuple(b.GetEnd())}
        for a,b in zip(tracks,tracks[1:])]
    if any(len(points)!=1 for points in shared):raise ValueError('qualified_neckdown_ordered_source_chain_required')
    if len(tracks)==1:
        # A literal endpoint stroke is already a complete ordered chain.
        # Preserve its actual start/end order; the same Source land, strict
        # shortening, native adjacency, factory throat and replay guards below
        # still own both ports. Do not force a fake second segment just to
        # trim a cap that a moved package has exposed.
        old_vertices=[tuple(tracks[0].GetStart()),tuple(tracks[0].GetEnd())]
    else:
        first=({tuple(tracks[0].GetStart()),tuple(tracks[0].GetEnd())}-shared[0])
        last=({tuple(tracks[-1].GetStart()),tuple(tracks[-1].GetEnd())}-shared[-1])
        if len(first)!=1 or len(last)!=1:raise ValueError('qualified_neckdown_two_source_ports_required')
        old_vertices=[next(iter(first)),*[next(iter(points)) for points in shared],next(iter(last))]
    points=list(map(tuple,vertices_nm))
    def exact_stroke(a,b):
        dx,dy=abs(a[0]-b[0]),abs(a[1]-b[1])
        return bool(dx or dy) and (not dx or not dy or dx==dy)
    if (len(set(points))!=len(points) or any(not exact_stroke(a,b) for a,b in zip(points,points[1:]))
            or any(math.dist(a,b)>2e6 for a,b in zip(old_vertices,points))):
        raise ValueError('qualified_neckdown_bounded_simple_octilinear_path_required')
    for old_at,new_at in ((old_vertices[0],points[0]),(old_vertices[-1],points[-1])):
        if old_at==new_at:continue
        same=[p for fp in parent.GetFootprints() for p in fp.Pads() if p.GetNetname()==net
            and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and p.IsOnLayer(face)
            and p.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*old_at),0)
            and p.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*new_at),0)]
        if not same:raise ValueError('qualified_neckdown_changed_port_must_stay_in_same_source_land')
    before_length=sum(t.GetLength() for t in tracks)
    if sum(math.dist(a,b) for a,b in zip(points,points[1:]))>=before_length-1:
        raise ValueError('qualified_neckdown_strict_physical_shortening_required')
    old_parts=ordinary._partition(parent,deadline)
    originals={u:(pcbnew.VECTOR2I(new[u].GetStart()),pcbnew.VECTOR2I(new[u].GetEnd())) for u in track_uuids}
    accepted=False
    try:
        for uid,a,z in zip(track_uuids,points,points[1:]):
            new[uid].SetStart(pcbnew.VECTOR2I(*a));new[uid].SetEnd(pcbnew.VECTOR2I(*z))
        proposed=[new[u] for u in track_uuids]
        contact=contacts.preserve_contacts(parent,tracks,[t.GetEffectiveShape(face) for t in proposed],
            layer_id=face,net_code=tracks[0].GetNetCode(),deadline_monotonic=deadline,
            maximum_source_tracks=4,minimum_source_tracks=1)
        if not contact['ok']:raise ValueError('qualified_neckdown_old_native_adjacency_lost:'+str(contact))
        qualified,rejected=fr._qualified_endpoint_neckdown_tracks(board,proposed,full,required_clearance=clearance)
        if rejected or {force._uid(t) for t in qualified}!=set(track_uuids):
            raise ValueError('qualified_neckdown_proposed_geometry_not_qualified')
        parts=ordinary._partition(board,deadline)
        if not all(any(part<=after for after in parts) for part in old_parts):
            raise ValueError('qualified_neckdown_original_native_partition_lost')
        if force._family(source,board_hint)!=family:raise ValueError('qualified_neckdown_source_family_changed')
        accepted=True
        return dict(ok=True,complete=True,errors=[],net=net,track_uuids=list(track_uuids),
            source_length_mm=before_length/1e6,candidate_length_mm=sum(t.GetLength() for t in proposed)/1e6,
            full_width_floor_nm=full,required_clearance_nm=clearance,native_contact_preservation=contact,
            every_original_native_partition_preserved=True,locks_widths_faces_groups_and_all_other_source_exact=True,
            current_qualified=False,routing_admitted=False,release_authority=False)
    finally:
        if not accepted:
            for uid,(a,z) in originals.items():new[uid].SetStart(a);new[uid].SetEnd(z)


def receive(source,candidate,plan,*,board_hint):
    report=dict(ok=False,complete=False,errors=[],release_authority=False,routing_admitted=False)
    try:
        if type(plan) is not dict or set(plan)!={'track_uuids','vertices_nm'}:
            raise ValueError('literal_qualified_neckdown_reflow_plan_required')
        source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
        if force._sidecars(source)!=force._sidecars(candidate):raise ValueError('qualified_neckdown_sidecars_changed')
        board=pcbnew.LoadBoard(str(source));proof=apply(source,board,board_hint=board_hint,**plan)
        with tempfile.TemporaryDirectory(prefix='cec-neckdown-replay-') as work:
            expected=force._copy_family(source,Path(work)/'expected');field._save_field_snapshot(board,expected)
            if force._preservation_snapshot(expected)!=force._preservation_snapshot(candidate):
                raise ValueError('qualified_neckdown_entire_saved_replay_mismatch')
        report.update(proof,exact_saved_source_reconstruction=True)
    except Exception as exc:report['errors'].append(type(exc).__name__+':'+str(exc))
    return report
