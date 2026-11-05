"""Fixed-port reconstruction of a source-typed necessary small GND branch.

The detached kernel must be one manufacturer-defined non-converter ground
terminal, optionally its uniquely selected bypass return, and a bounded set
of same-face full-class tracks. No barrel, plane, connector, shared device,
power-return or generic GND mesh can be cut under this contract. Every actual
surviving native conductor partition must be identical after reconstruction.
This neither changes any current budget nor qualifies current/thermal/fab.
"""
import time
from pathlib import Path
import pcbnew
import cec_constraints as constraints
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_fab_profile as fab
import cec_force_current as force
import cec_ground_strap_rebuild as straps
import cec_native_ground_span_reflow as span
import cec_ordinary_route_receiving as ordinary
import cec_native_partition_pair as partitions
import cec_native_zone_islands as islands
import cec_return_escape as surface


def _ground_parts(board,retired,deadline):
    items=[p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname()=='GND']
    items += [t for t in board.GetTracks() if t.GetNetname()=='GND']
    for z in board.Zones():
        if not z.GetIsRuleArea()and z.GetNetname()=='GND':
            items+=islands.decompose(board,z,deadline=deadline)
    if len(items)>16384:raise ValueError('necessary_ground_branch_native_inventory_bound')
    live={force._uid(i):i for i in items if force._uid(i) not in retired}
    if len(live)!=len(items)-len(retired):raise ValueError('necessary_ground_branch_exact_native_ids_required')
    graph=pcbnew.CONNECTIVITY_DATA()
    for item in live.values():
        if time.monotonic()>=deadline:raise ValueError('necessary_ground_branch_partition_deadline')
        if not graph.Add(item):raise ValueError('necessary_ground_branch_native_item_refused')
    remaining=set(live);parts=[]
    while remaining:
        if time.monotonic()>=deadline:raise ValueError('necessary_ground_branch_partition_deadline')
        uid=min(remaining)
        reached={uid}|{force._uid(i) for i in graph.GetConnectedItems(live[uid])}
        own=remaining&reached;parts.append(own);remaining-=own
    return live,parts


def _context(board,proposal,deadline):
    retired=set(proposal['retired_track_uuids']);face=proposal['source_layer']
    contacts=set(proposal['retained_contact_uuids'])
    live,parts=_ground_parts(board,retired,deadline)
    touched=[q for q in parts if q&contacts]
    if len(touched)!=2:raise ValueError('exactly_one_necessary_two_port_ground_branch_required')
    _,original=_ground_parts(board,set(),deadline)
    if not any(set.union(*touched)<=q for q in original):
        raise ValueError('necessary_ground_branch_source_ports_not_already_connected')
    profile=fab.get_profile(fab.board_profile_name(board))
    if not profile:raise ValueError('necessary_ground_branch_explicit_reference_profile_required')
    plane_faces={int(board.GetLayerID(name)) for name,role in zip(fab.COPPER_LAYERS,profile['roles']) if role=='GND'}
    assignments=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    candidates=[]
    for own in touched:
        if not 1<=len(own)<=10:continue
        objects=[live[u] for u in sorted(own)]
        pads=[i for i in objects if i.GetClass()=='PAD']
        if not 1<=len(pads)<=2:continue
        if any(i.GetClass() not in ('PAD','PCB_TRACK') for i in objects):continue
        floor=max(int(board.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(board,'GND')['width']))
        if any(i.GetClass()=='PCB_TRACK' and (int(i.GetLayer())!=face or not floor<=i.GetWidth()<=350000
                or i.GetParentGroup() or i.HasSolderMask()) for i in objects):continue
        if any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                or surface.smd_surface_layer(p)!=face for p in pads):continue
        roots=[]
        for pad in pads:
            fp=pad.GetParentFootprint();model=roles.footprint_contract(fp)
            if (not fp.IsDNP() and model and model['pins'].get(str(pad.GetNumber()))=='ground'
                    and not set(model['pins'].values())&{'power_output','switch','power_return'}):
                roots.append((pad,fp,model))
        if len(roots)!=1:continue
        root,owner,model=roots[0]
        selected=[r for r in assignments['assigned'].values() if r['requirement']['ref']==owner.GetReference()]
        if len(selected)!=1:continue
        cap=board.FindFootprintByReference(selected[0]['cap_ref'])
        cap_grounds=[p for p in cap.Pads() if p.GetNetname()=='GND'] if cap else []
        if len(cap_grounds)!=1:continue
        cap_ground=cap_grounds[0]
        manufacturer,_,requirement=straps._land_ownership(board,cap_ground,'selected_bypass')
        if (requirement['ref']!=owner.GetReference() or surface.smd_surface_layer(cap_ground)!=face
                or any(force._uid(p) not in {force._uid(root),force._uid(cap_ground)} for p in pads)):
            continue
        main=next(q for q in touched if q is not own)
        planes=[(u,layer) for u in sorted(main) if live[u].GetClass()=='ZONE'
            and live[u].IsFilled() for layer in sorted(plane_faces)
            if live[u].IsOnLayer(layer) and live[u].HasFilledPolysForLayer(layer)]
        if len({layer for u,layer in planes})<2:continue
        candidates.append(dict(owner_pad_uuid=force._uid(root),selected_cap_ground_uuid=force._uid(cap_ground),
            manufacturer_source=manufacturer,device_package=model['device_package'],selected_requirement=requirement,
            detached_kernel_uuids=sorted(own),retained_main_port_contact_uuids=sorted(main&contacts),
            retained_branch_port_contact_uuids=sorted(own&contacts),actual_main_reference_planes=planes,
            source_component_already_connected=True,source_branch_is_necessary=True,
            current_budget_modified=False,release_authority=False))
    if len(candidates)!=1:raise ValueError('one_selected_nonconverter_ground_terminal_kernel_required')
    # JSON-safe tuples are deliberately normalized before source binding.
    result=candidates[0];result['actual_main_reference_planes']=[list(q) for q in result['actual_main_reference_planes']]
    return result


def _base(proposal):
    result=dict(proposal)
    if 'necessary_branch' not in result:raise ValueError('explicit_typed_necessary_branch_plan_required')
    result.pop('necessary_branch');return result


def plan(board,track_uuids,points_nm,*,maximum_extra_nm=0,timeout_s=10.,allow_locked_track_uuids=()):
    deadline=span._deadline(timeout_s)
    if type(maximum_extra_nm) is not int or maximum_extra_nm!=0:
        raise ValueError('necessary_ground_branch_must_be_strictly_shorter')
    proposal=span.plan(board,track_uuids,points_nm,maximum_extra_nm=0,
        timeout_s=max(.001,min(10.,deadline-time.monotonic())),allow_locked_track_uuids=allow_locked_track_uuids)
    if proposal['source_length_nm']-proposal['replacement_length_nm']<=10000:
        raise ValueError('necessary_ground_branch_must_be_strictly_shorter')
    proposal['necessary_branch']=_context(board,proposal,deadline)
    if time.monotonic()>=deadline:raise ValueError('necessary_ground_branch_plan_deadline')
    return proposal


def materialize(board,proposal):
    base=_base(proposal)
    fresh=plan(board,base['retired_track_uuids'],base['replacement_points_nm'],
        allow_locked_track_uuids=base.get('allow_locked_track_uuids',()))
    if fresh!=proposal:raise ValueError('necessary_ground_branch_stale_or_forged_source_plan')
    return span.materialize(board,base)


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    try:
        deadline=span._deadline(timeout_s);base=_base(proposal)
        parent=pcbnew.LoadBoard(str(Path(source).resolve()))
        fresh=plan(parent,base['retired_track_uuids'],base['replacement_points_nm'],
            timeout_s=max(.001,min(10.,deadline-time.monotonic())),
            allow_locked_track_uuids=base.get('allow_locked_track_uuids',()))
        if fresh!=proposal:raise ValueError('necessary_ground_branch_stale_or_forged_source_plan')
        def cut_contract(parent,basis,child,received,source_parts,cut_parts,lease):
            if _context(parent,received,lease)!=proposal['necessary_branch']:
                raise ValueError('necessary_ground_branch_source_kernel_changed')
            transition=partitions.compare(parent,child,retired_uuids=set(received['retired_track_uuids']),
                timeout_s=min(10.,lease-time.monotonic()))
            if (not transition['preserved']or {frozenset(q)for q in transition['source_parts']}
                    !={frozenset(q)for q in transition['child_parts']}):
                raise ValueError('necessary_ground_branch_changed_surviving_native_partition')
            return dict(source_span_already_redundant_to_retained_native_copper=False,
                source_necessary_ground_terminal_branch=proposal['necessary_branch'],
                every_surviving_native_conductor_partition_identical=True)
        return span._receive_path(source,candidate,base,board_hint=board_hint,
            timeout_s=max(.001,min(10.,deadline-time.monotonic())),cut_contract=cut_contract)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        return dict(ok=False,complete=False,errors=[type(exc).__name__+':'+str(exc)],
            current_qualified=False,release_authority=False,
            full_current_fields_native_DRC_absolute_cuts_and_release_still_required=True)
