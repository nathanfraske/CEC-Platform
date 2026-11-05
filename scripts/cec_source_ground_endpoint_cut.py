"""Positive retirement of an existing fine-pitch Ground endpoint component.

An endpoint exception is not a movable dogbone.  Re-derive its real source
geometry and manufacturer Ground owner before transport; keep the full-width
throat fixed.  This grants only a constructive restoration debt, never new
thin copper, a current rating, or permission to save an incomplete board.
"""
import math
import time

import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_device_power_roles as roles


def plan(source, posed, *, source_floor, allow_locked=False, timeout_s=10.):
    """Inventory only actual departing, source-qualified Ground neckdowns.

    ``source_floor`` is the transport compiler's exact saved-source
    class/current/layer resolver, not an external width override.  All other
    group members and every physical throat/barrel remain native source.
    """
    if (type(allow_locked) is not bool or not callable(source_floor)
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10.):
        raise ValueError('bounded_source_ground_endpoint_inventory_required')
    deadline = time.monotonic() + timeout_s

    def tick():
        if time.monotonic() >= deadline:
            raise ValueError('source_ground_endpoint_inventory_deadline')

    pads = [p for f in source.GetFootprints() for p in f.Pads()]
    target = {force._uid(p): p for f in posed.GetFootprints() for p in f.Pads()}
    tracks = list(source.GetTracks())
    if len(pads) + len(tracks) > 16384:
        raise ValueError('source_ground_endpoint_inventory_bound')
    moving = {force._uid(p): p for p in pads if force._uid(p) in target
        and (tuple(p.GetPosition()) != tuple(target[force._uid(p)].GetPosition())
            or p.GetOrientationDegrees() != target[force._uid(p)].GetOrientationDegrees())}
    result = []
    seen = set()
    for group in source.Groups():
        tick()
        if group.GetName() != fr.ENDPOINT_NECKDOWN_GROUP or group.IsLocked():
            continue
        grouped = list(group.GetItems())
        if any(t.GetClass() != 'PCB_TRACK' for t in grouped):
            continue
        for face in sorted({int(t.GetLayer()) for t in grouped if t.GetNetname() == 'GND'}):
            cohort = [t for t in grouped if t.GetNetname() == 'GND' and t.GetLayer() == face]
            departing = [p for p in moving.values() if p.GetNetname() == 'GND' and p.IsOnLayer(face)
                and any(p.HitTest(at, 0) and not target[force._uid(p)].HitTest(at, 0)
                    for t in cohort for at in (t.GetStart(), t.GetEnd()))]
            if not departing:
                continue
            full, gap = source_floor(cohort[0])
            if type(full) is not int or type(gap) is not int or full <= 0 or gap < 0:
                raise ValueError('literal_source_ground_dimensions_required')
            qualified, _ = fr._qualified_endpoint_neckdown_tracks(
                source, cohort, full, required_clearance=gap)
            allowed = {force._uid(t) for t in qualified}
            todo = {force._uid(t): t for t in cohort if force._uid(t) in allowed}
            while todo:
                tick()
                uid = min(todo)
                component = [todo.pop(uid)]
                points = {tuple(at) for at in (component[0].GetStart(), component[0].GetEnd())}
                changed = True
                while changed:
                    changed = False
                    for key, edge in list(todo.items()):
                        ends = {tuple(edge.GetStart()), tuple(edge.GetEnd())}
                        if ends & points:
                            component.append(todo.pop(key)); points |= ends; changed = True
                if (not 1 <= len(component) <= 4
                        or any(t.HasSolderMask() or not 0 < t.GetWidth() <= 350000
                            or t.IsLocked() and not allow_locked for t in component)):
                    continue
                ids = {force._uid(t) for t in component}
                # A group name is insufficient: no nested/overlapping owner.
                if any([force._uid(g) for g in source.Groups() if g.ContainsItem(t)]
                        != [force._uid(group)] for t in component):
                    continue
                roots = []
                valid = True
                for pad in pads:
                    if pad.GetNetname() != 'GND' or not pad.IsOnLayer(face):
                        continue
                    if not any(t.GetEffectiveShape(face).Collide(pad.GetEffectiveShape(face), 0)
                            for t in component):
                        continue
                    key = force._uid(pad)
                    model = roles.footprint_contract(pad.GetParentFootprint())
                    role = model['pins'].get(pad.GetNumber()) if model else None
                    if (key not in moving or pad.HasHole()
                            or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                            or not model or set(model['pins'].values()) & {'power_output', 'switch', 'feedback'}
                            or role not in ('ground', 'reference', 'power_return', 'address')
                            or role == 'address' and not any(p.GetNetname() == 'GND'
                                and model['pins'].get(p.GetNumber()) in ('ground', 'power_return')
                                for p in pad.GetParentFootprint().Pads())):
                        valid = False; break
                    contacts = sorted(at for at in points if pad.HitTest(pcbnew.VECTOR2I(*at), 0))
                    if not contacts:
                        valid = False; break
                    roots.append(dict(pad_uuid=key, role=role, manufacturer_source=model['source'],
                        source_contact_nm=[list(at) for at in contacts]))
                if not valid or not roots or not any(r['pad_uuid'] in {force._uid(p) for p in departing} for r in roots):
                    continue
                root_points = {tuple(at) for r in roots for at in r['source_contact_nm']}
                degree = {at: sum(at in (tuple(t.GetStart()), tuple(t.GetEnd())) for t in component) for at in points}
                ends = {at for at, count in degree.items() if count == 1}
                if len(ends) != 2 or len(ends & root_points) != 1:
                    continue
                throat = next(iter(ends - root_points))
                fixed = [t for t in tracks if t.GetClass() == 'PCB_TRACK' and force._uid(t) not in ids
                    and t.GetNetname() == 'GND' and t.GetLayer() == face and t.GetWidth() >= full
                    and throat in (tuple(t.GetStart()), tuple(t.GetEnd()))]
                if not fixed or any(any(p.HitTest(at, 0) for at in (t.GetStart(), t.GetEnd()))
                        for t in fixed for p in moving.values() if p.GetNetname() == 'GND' and p.IsOnLayer(face)):
                    continue
                if seen & ids:
                    raise ValueError('ambiguous_source_ground_endpoint_cut')
                seen |= ids
                if len(seen) > 16:
                    raise ValueError('bounded_source_ground_endpoint_cut_cohort_required')
                result.append(dict(kind='positive_source_ground_endpoint_restoration',
                    source_group_uuid=force._uid(group), source_group_cohort_uuids=sorted(force._uid(t) for t in cohort),
                    retired_track_uuids=sorted(ids), source_pad_roots=roots,
                    source_edges=[dict(uuid=force._uid(t), source_nm=[list(t.GetStart()), list(t.GetEnd())],
                        width_nm=int(t.GetWidth()), locked=bool(t.IsLocked())) for t in sorted(component, key=force._uid)],
                    full_width_floor_nm=full, required_clearance_nm=gap, layer_id=face,
                    retained_throat_nm=list(throat), retained_throat_track_uuids=sorted(force._uid(t) for t in fixed),
                    source_endpoint_geometry_independently_qualified=True,
                    complete_source_partitions_and_physical_ground_returns_still_due=True,
                    new_endpoint_copper_requires_fresh_qualification=True,
                    current_authority=False, saved_candidate_authorized=False))
    return result
