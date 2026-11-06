"""Complete native current-cut contacts; explicit IDs are work, not authority.

Only the actual connected retired component touching the capacitor is used.
Each edge is re-proved at the unchanged whole-rail rating. The enclosing macro
still owns cuts, locks, transport, saved partitions and every acceptance gate.
"""
from pathlib import Path
import pcbnew


def requests(parent, child, proposal, proof, incident_plans, retired,
             composed_current_cut_uuids, deadline):
    import cec_additional_aggregate_macro as aggregate
    import cec_source_aggregate_capacitor_cell as cap
    import cec_control_gate_bias_placement as identity
    import cec_macro_cut_components as components
    need = aggregate._need
    def tick(): aggregate._left(deadline)
    declared = composed_current_cut_uuids
    need(type(declared) in (list, tuple) and 1 <= len(declared) <= 128
        and all(type(u) is str and u for u in declared)
        and len(set(declared)) == len(declared), 'bounded_unique_composed_current_cut_intent_required')
    old = {cap.force._uid(t): t for t in parent.GetTracks()}
    live = {cap.force._uid(t): t for t in child.GetTracks()}
    need(set(declared) <= old.keys() and set(declared) <= retired
        and not set(declared) & live.keys(), 'composed_current_cut_intent_must_be_actual_retired_Source_edges')
    roots = {u for p in incident_plans for u in p['retired_track_uuids']}
    need(roots and roots <= retired and roots <= old.keys() and not roots & live.keys(),
        'composed_current_cut_requires_actual_incident_roots')
    binding = cap.row._source_binding(parent)
    child_binding = cap.row._source_binding(child)
    candidates = set(declared) | roots
    # Native shape adjacency, not same-net membership or old bend endpoints.
    def touches(a, b):
        return (a.GetClass() == b.GetClass() == 'PCB_TRACK'
            and a.GetNetname() == b.GetNetname() and a.GetLayer() == b.GetLayer()
            and a.GetBoundingBox().Intersects(b.GetBoundingBox())
            and a.GetEffectiveShape(a.GetLayer()).Collide(b.GetEffectiveShape(b.GetLayer()), 0))
    selected = set(roots); pending = list(roots)
    while pending:
        tick(); edge = old[pending.pop()]
        for uid in sorted(candidates - selected):
            if touches(edge, old[uid]): selected.add(uid); pending.append(uid)
        need(len(selected) <= 8, 'bounded_composed_current_cut_cohort_required')
    plans = []
    for uid in sorted(selected):
        tick()
        plan = cap.full.plan(parent, Path(proof['source']), board_hint=proposal['board_hint'],
            retired_track_uuids=[uid], timeout_s=aggregate._left(deadline))
        need(aggregate._wire(plan['contract']) == proof['aggregate_contract']
            and plan['source_sha256'] == proof['source_sha256'],
            'wired_aggregate_same_full_current_cut_authority_required')
        plans.append(plan)
    # Component inventory deliberately omits retired metal. Prove that no
    # relevant omitted peer can vanish through that exclusion before using it.
    for uid in sorted(retired - selected):
        tick(); other = old.get(uid)
        need(other is not None, 'composed_current_retired_Source_identity_missing')
        for chosen in selected:
            edge = old[chosen]; face = edge.GetLayer()
            need(not (other.GetNetname() == edge.GetNetname() and other.IsOnLayer(face)
                and other.GetBoundingBox().Intersects(edge.GetBoundingBox())
                and other.GetEffectiveShape(face).Collide(edge.GetEffectiveShape(face), 0)),
                'composed_current_touching_retired_peer_requires_explicit_positive_owner')
    # Component builder projects actual pad positions. Validate complete
    # literal rigid footprint identity first, never a proof-supplied target.
    for fp in parent.GetFootprints():
        tick()
        contacting = any(p.GetNetname() == old[u].GetNetname() and p.IsOnLayer(old[u].GetLayer())
            and p.GetEffectiveShape(old[u].GetLayer()).Collide(old[u].GetEffectiveShape(), 0)
            for p in fp.Pads() for u in selected)
        if not contacting: continue
        expected = pcbnew.FOOTPRINT(fp); pose = proposal['poses'].get(fp.GetReference())
        if pose is not None:
            expected.SetPosition(pcbnew.VECTOR2I(*(round(v * 1e6) for v in pose[:2])))
            expected.SetOrientationDegrees(pose[2])
        actual = child.FindFootprintByReference(fp.GetReference())
        need(actual is not None and identity._footprint(child, actual) == identity._footprint(child, expected),
            'wired_aggregate_current_boundary_exact_pad_owner_pose_required')
    def project(_parent, _child, port, _transport, _retired):
        for uid in port['native_uuids']:
            tick()
            need(uid in live and identity._track(parent, old[uid]) == identity._track(child, live[uid]),
                'wired_aggregate_current_boundary_conductor_motion_needs_typed_projection')
            need(all(live[uid].IsOnLayer(face)
                and live[uid].GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*port['at_nm']), 0)
                for face in port['layers']), 'wired_aggregate_current_boundary_literal_contact_lost')
        return [port]
    extras = [dict(change=dict(uuid=p['retired_track_uuids'][0], net=p['net']),
        authority=dict(kind='unchanged_full_current_source_edge',
            native_source_uuid=p['retired_track_uuids'][0], source_plan=p)) for p in plans]
    demands, records = components.requests(parent, child, extras, retired, {},
        project_contacts=project, deadline=deadline)
    result = {}
    for index, request in enumerate(demands.values()):
        name = 'aggregate_incident_cut:' + proof['footprint_uuid'] + ':' + str(index)
        result[name] = dict(request, unchanged_full_rail_current_contract=proof['current_contract'],
            source_full_current_component_contact_proofs=records,
            complete_macro_projected_boundaries_and_partitions_still_mandatory=True)
    tick()
    need(binding == cap.row._source_binding(parent) and child_binding == cap.row._source_binding(child)
        and cap.force._hash(Path(proof['source'])) == proof['source_sha256'],
        'composed_current_cut_Source_or_candidate_changed')
    return result
