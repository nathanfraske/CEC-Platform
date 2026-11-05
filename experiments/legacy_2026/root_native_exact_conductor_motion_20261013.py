"""Bounded literal source-conductor motion for PRIVATE multi-cohort trials.

Widths, drills, faces, identities and ownership do not change. Different
cohorts may need different travel to preserve a collector corridor. This is
not permission to select a board or to tolerate a new DRC/current fault.
"""
import math
import pcbnew
import cec_force_current as force
import cec_route_quality as quality


def apply(source, candidate, requests, *, maximum_items=32, allow_transient_rebuild_uuids=()):
    if type(maximum_items) is not int or not 1<=maximum_items<=64:
        raise ValueError('bounded_explicit_conductor_cohort_budget_required')
    if type(requests) is not list or not 1 <= len(requests) <= maximum_items:
        raise ValueError('bounded_literal_conductor_motion_required')
    transient=set(allow_transient_rebuild_uuids)
    if (type(allow_transient_rebuild_uuids) not in (list,tuple) or len(transient)!=len(allow_transient_rebuild_uuids)
            or len(transient)>maximum_items or any(type(u) is not str for u in transient)
            or not transient<={q.get('uuid') for q in requests if type(q) is dict}):
        raise ValueError('exact_bounded_transient_reconstruction_scope_required')
    old = {force._uid(t): t for t in source.GetTracks()}
    new = {force._uid(t): t for t in candidate.GetTracks()}
    if old.keys() != new.keys():
        raise ValueError('unchanged_native_conductor_population_required')
    seen = set(); proposals = []
    for q in requests:
        if type(q) is not dict or set(q) != {'uuid', 'endpoint_offsets_nm', 'locked_source_requested'}:
            raise ValueError('exact_source_conductor_motion_fields_required')
        uid = q['uuid']
        if type(uid) is not str or uid not in old or uid in seen:
            raise ValueError('unique_existing_source_conductor_required')
        seen.add(uid); before = old[uid]; after = new[uid]
        if before.GetParentGroup() is not None or before.GetClass() not in ('PCB_TRACK', 'PCB_VIA'):
            raise ValueError('unowned_native_linear_conductor_required')
        if type(q['locked_source_requested']) is not bool or q['locked_source_requested'] != before.IsLocked():
            raise ValueError('exact_locked_source_motion_request_required')
        def dimensions(t):
            if t.GetClass() == 'PCB_TRACK':
                return (t.GetClass(),t.GetNetname(),t.GetLayer(),t.GetWidth(),t.IsLocked())
            return (t.GetClass(),t.GetNetname(),t.TopLayer(),t.BottomLayer(),
                t.GetWidth(t.TopLayer()),t.GetDrillValue(),t.GetViaType(),t.IsLocked())
        if dimensions(before) != dimensions(after):
            raise ValueError('literal_source_conductor_dimensions_changed')
        count = 2 if before.GetClass() == 'PCB_TRACK' else 1
        offsets = q['endpoint_offsets_nm']
        if (type(offsets) is not list or len(offsets) != count or any(
                type(v) is not list or len(v) != 2 or any(type(n) is not int for n in v)
                or math.hypot(*v) > 3000000 for v in offsets)):
            raise ValueError('bounded_literal_endpoint_motion_required')
        points = [tuple(before.GetStart()), tuple(before.GetEnd())] if count == 2 else [tuple(before.GetPosition())]
        targets = [tuple(n+d for n, d in zip(at, delta)) for at, delta in zip(points, offsets)]
        canonical=count!=2 or quality.is_canonical_stroke(*targets)
        if count == 2 and (targets[0] == targets[1] or not canonical and uid not in transient):
            raise ValueError('nonempty_canonical_source_motion_required')
        proposals.append((after, targets, dict(uuid=uid, source_nm=points,
            candidate_nm=targets, net=before.GetNetname(), literal_source_dimensions_retained=True,
            temporary_noncanonical_reconstruction_required=not canonical)))
    # Validate the whole finite request before changing any native item.
    for item, targets, receipt in proposals:
        if item.GetClass() == 'PCB_TRACK':
            item.SetStart(pcbnew.VECTOR2I(*targets[0])); item.SetEnd(pcbnew.VECTOR2I(*targets[1]))
        else: item.SetPosition(pcbnew.VECTOR2I(*targets[0]))
    return dict(changes=[r for _, _, r in proposals], maximum_items=maximum_items,
        transient_rebuild_required_uuids=sorted(r['uuid'] for _,_,r in proposals if r['temporary_noncanonical_reconstruction_required']),routing_admitted=False,
        current_qualified=False, native_contact_reconstruction_required=True,
        independent_saved_native_receiving_required=True, release_authority=False)
