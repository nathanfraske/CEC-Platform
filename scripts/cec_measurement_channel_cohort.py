"""Read-only, source-typed two-owner measurement channel selection.

This returns a stationary search seed, not a placement, cut, current or route
permission. Consumers must freshly compile their proposed poses through the
existing complete-cell APIs and independently receive the saved result.
"""
import math
import time


def select(board, *, board_hint, owner_uuid, timeout_s=10., max_members=8,reference_group_uuids=()):
    import cec_force_current as force
    import cec_cell_row_rebuild as binding
    import cec_current_topology as topology
    import cec_sense_topology as sense
    import cec_pair_semantics as semantics
    import cec_device_power_roles as roles
    import cec_constraints as constraints
    import cec_cell_escape_replan as escape
    import pcbnew
    if (type(board_hint) is not str or not board_hint or type(owner_uuid) is not str or not owner_uuid
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(max_members) is not int or not 4<=max_members<=8):
        raise ValueError('bounded_source_measurement_channel_identity_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('measurement_channel_selection_deadline')
    before=binding._source_binding(board)
    try:
        fps=list(board.GetFootprints())
        if len(fps)>1024 or len({force._uid(f)for f in fps})!=len(fps):
            raise ValueError('bounded_unique_source_footprint_inventory_required')
        refs={f.GetReference():f for f in fps}
        if len(refs)!=len(fps):raise ValueError('unique_source_references_required')
        seeds=[f for f in fps if force._uid(f)==owner_uuid]
        if len(seeds)!=1 or semantics.footprint_input_contract(seeds[0]) is None:
            raise ValueError('positive_actual_measurement_owner_uuid_required')
        tick()
        with force._thermal_hint(board_hint):domains=topology.board_current_domains(board,board_hint)
        tick()
        authorities={r for d in domains.values()if d.get('complete')is True
            for r in d.get('authority_refs',())}
        if not authorities:raise ValueError('complete_source_current_shunt_authority_required')
        # Explicit authority refs, with NO default HI/LO spelling inference.
        lineage=sense.board_evidence(board,anchor_pairs=[],anchor_refs=sorted(authorities))
        tick()
        rows=lineage.get('details',[])
        if len(rows)>64:raise ValueError('bounded_measurement_owner_inventory_required')
        selected=[r for r in rows if r['ref']==seeds[0].GetReference()]
        if len(selected)!=1 or selected[0].get('ok')is not True:
            raise ValueError('unique_resolved_seed_shunt_lineage_required')
        def root(row):
            s=row['selected']
            return (s['anchor_ref'],s['p']['anchor_pad'],s['n']['anchor_pad'])
        target=root(selected[0]);anchor=refs.get(target[0])
        if anchor is None or any(constraints._fp_assembly_state(anchor))or target[0]not in authorities:
            raise ValueError('actual_active_source_shunt_required')
        # Any unresolved owner touching either selected input net is not an
        # orphan that can silently disappear from this channel inventory.
        seed_nets=set(selected[0]['input_nets'])
        if any(r.get('ok')is not True and seed_nets&set(r.get('input_nets',()))for r in rows):
            raise ValueError('ambiguous_or_orphan_channel_owner')
        owners=[r for r in rows if r.get('ok')is True and root(r)==target]
        if len(owners)!=2 or len({r['ref']for r in owners})!=2:
            raise ValueError('exact_two_measurement_models_on_same_ordered_shunt_required')
        models={}
        for row in owners:
            fp=refs.get(row['ref']);model=roles.footprint_contract(fp)if fp is not None else None
            if (fp is None or any(constraints._fp_assembly_state(fp)) or fp.IsLocked()
                    or model is None or semantics.footprint_input_contract(fp) is None):
                raise ValueError('active_complete_selected_measurement_model_required')
            pads=list(fp.Pads());numbers=[p.GetNumber()for p in pads]
            if (len(set(numbers))!=len(numbers)or set(numbers)!=set(model['pins'])
                    or any(p.HasHole()or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in pads)
                    or any(model['pins'].get(pin)!='measurement'for pin in row['pins'])):
                raise ValueError('complete_actual_surface_measurement_pinmap_required')
            models[row['ref']]=model
        tick()
        with force._thermal_hint(board_hint):assignment=constraints._device_bypass_assignment(board,project_max_mm=3.5)
        tick();assigned=list(assignment.get('assigned',{}).values())
        if len(assigned)>256:raise ValueError('bounded_source_bypass_assignment_required')
        chosen=[]
        for row in owners:
            own=[a for a in assigned if a['requirement']['ref']==row['ref']]
            if not own:raise ValueError('actual_assigned_owner_bypass_required')
            required={str(pin)for pin,role in models[row['ref']]['pins'].items()if role=='power_input'}
            if not required or {str(a['requirement']['pin'])for a in own}!=required:
                raise ValueError('every_actual_owner_power_input_bypass_required')
            chosen.extend(own)
        caps=[a['cap_ref']for a in chosen]
        if len(set(caps))!=len(caps):raise ValueError('ambiguous_shared_channel_bypass')
        for a in chosen:
            ref=a['cap_ref'];cap=refs.get(ref);req=a['requirement']
            if (cap is None or any(constraints._fp_assembly_state(cap)) or cap.IsLocked()
                    or sum(x['cap_ref']==ref for x in assigned)!=1
                    or (req.get('return_rail')or'GND')!='GND'
                    or len(list(cap.Pads()))!=2
                    or {p.GetNetname()for p in cap.Pads()}!={req['rail'],'GND'}):
                raise ValueError('unique_active_actual_source_bypass_required')
        members=sorted(set(models)|set(caps))
        if len(members)!=len(models)+len(caps)or not 4<=len(members)<=max_members:
            raise ValueError('bounded_distinct_channel_members_required')
        poses={ref:[refs[ref].GetPosition().x/1e6,refs[ref].GetPosition().y/1e6,
                    refs[ref].GetOrientationDegrees()]for ref in members}
        # Existing compiler independently rederives complete model/pin and
        # unique bypass identities. Stationary compilation grants NO cuts.
        prepared=escape.prepare(board,poses,board_hint=board_hint,reference_group_uuids=reference_group_uuids)
        tick()
        if prepared.get('source_native_binding')!=before or prepared.get('retired_track_uuids'):
            raise ValueError('stationary_complete_cell_source_binding_or_cut_changed')
        return dict(schema=1,scope='source_selected_measurement_channel_stationary_seed',
            source_native_binding=before,seed_owner_uuid=owner_uuid,board_hint=board_hint,
            anchor_ref=target[0],ordered_anchor_pins=list(target[1:]),
            anchor_uuid=force._uid(anchor),owners=sorted(models),bypasses=sorted(caps),
            member_uuids={ref:force._uid(refs[ref])for ref in members},poses=poses,
            lineage=owners,source_prepare_binding=prepared['source_native_binding'],
            stationary_prepare_completed=True,placement_authority=False,
            retirement_authority=False,current_authority=False,release_authority=False)
    finally:
        if binding._source_binding(board)!=before:raise ValueError('measurement_channel_selector_changed_source')
