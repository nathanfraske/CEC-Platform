"""Source-rooted bounded local forks for complete native cell reconstruction.

Exclusive leaf ownership must not be stretched over a real shared junction.
This separate construction scope records EVERY moving terminal and retained
native contact of a small same-face fork. It grants no routing/current/fab
admission, no barrel/zone cut, no output-mode inference and no per-load budget.
"""
import json,math,time
from pathlib import Path
import pcbnew
import cec_cell_row_rebuild as row
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_full_current_planar_reflow as full
import cec_measurement_leaf as leaf
import cec_pair_semantics as semantics
import cec_current_topology as topology
import cec_synth_pipeline as synth


def _tick(deadline):
    if time.monotonic()>=deadline:raise ValueError('source_cell_fork_deadline')


def _contact_outside_fixed(a,b,fixed,face,deadline):
    """A fixed end-port must not hide a different interior fork junction.

    Expand only literal native contact metal outside every fixed terminal or
    unowned conductor. In particular, two branches meeting inside a retained
    plated land cannot be traversed through that land into the wider mesh.
    This helper is proposal-cut ownership, not current/connection admission.
    """
    def poly(item,error):
        shape=pcbnew.SHAPE_POLY_SET()
        item.TransformShapeToPolygon(shape,face,0,1000,error)
        return shape
    contact=poly(a,pcbnew.ERROR_OUTSIDE)
    contact.BooleanIntersection(poly(b,pcbnew.ERROR_OUTSIDE))
    for item in fixed:
        _tick(deadline)
        if not item.GetBoundingBox().Intersects(a.GetBoundingBox()) or not item.GetBoundingBox().Intersects(b.GetBoundingBox()):continue
        if (a.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face),0)
                and b.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face),0)):
            # Native rounded endpoints can meet just outside a plated land
            # while both are already on that fixed port. Never walk THROUGH
            # that shared port into its other mesh arms. A different interior
            # T-branch has no such common fixed contact and stays discoverable.
            return False
        contact.BooleanSubtract(poly(item,pcbnew.ERROR_INSIDE))
        if not contact.OutlineCount():return False
    return bool(contact.OutlineCount())


def _typed_root(board,pad,kind,board_hint,*,fixed_ground_boundary=False):
    fp=pad.GetParentFootprint();model=roles.footprint_contract(fp)
    if (fp.IsLocked() or fp.IsDNP() or fp.GetParentGroup() is not None or pad.GetParentGroup() is not None
            or pad.HasHole() or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
            or cells.cec_return_escape.smd_surface_layer(pad) is None):
        raise ValueError('populated_unlocked_source_surface_fork_root_required')
    role=model['pins'].get(str(pad.GetNumber())) if model else None
    complete=False
    if model:
        try:
            roles.physical_pinmap(fp,model,board_hint=board_hint)
            complete=True
        except ValueError:
            pass
    if kind=='ground_return':
        if pad.GetNetname()!='GND':raise ValueError('literal_ground_return_fork_root_required')
        if model:
            allowed=('ground','reference','power_return','address') if fixed_ground_boundary else ('ground','reference','power_return')
            if (role not in allowed
                    or set(model['pins'].values())&{'power_output','switch','feedback'}
                    or not complete):
                raise ValueError('complete_low_power_manufacturer_ground_fork_root_required:'+fp.GetReference()+':'+pad.GetNumber()+':'+str(role))
            return dict(pad_uuid=force._uid(pad),role=role,manufacturer_source=model['source'])
        selected=leaf._bypass_supply_owner(board,pad,board_hint,ground_return=True)
        return dict(pad_uuid=force._uid(pad),role='source_selected_bypass_ground',selected_bypass=selected)
    if kind=='scalar_input':
        if (role!='signal_input' or str(pad.GetPinType()) in ('power_in','power_out')
                or not complete):
            raise ValueError('complete_manufacturer_scalar_input_fork_root_required')
        return dict(pad_uuid=force._uid(pad),role=role,manufacturer_source=model['source'])
    if model:
        if (role!='power_input' or set(model['pins'].values())&{'power_output','switch','feedback'}
                or not complete):
            raise ValueError('complete_low_power_manufacturer_supply_fork_root_required')
        return dict(pad_uuid=force._uid(pad),role=role,manufacturer_source=model['source'])
    selected=leaf._bypass_supply_owner(board,pad,board_hint)
    return dict(pad_uuid=force._uid(pad),role='source_selected_bypass_supply',selected_bypass=selected)


def plan(board,root_pad_uuids,*,moving_refs,kind,board_hint,allow_owned_locked=False,timeout_s=10.,
         retained_ground_pad_uuids=(),retained_ground_track_uuids=(),max_tracks=None,max_length_mm=None,
         allow_full_current_supply_width=False):
    """Flood only source-local ungrouped full-width strokes to real fixed ports.

    A native pad/via or an unowned conductor stops expansion; it is NEVER
    silently swallowed by the cut. An otherwise eligible edge touching that
    terminal can be cut only with an independently derived restoration port.
    Native body/round-cap contacts, not nearest points or endpoint graphs,
    determine the complete scope. Unknown or too-large scopes refuse whole.
    """
    if (type(root_pad_uuids) not in (list,tuple,set) or not 1<=len(root_pad_uuids)<=8
            or len(set(root_pad_uuids))!=len(root_pad_uuids)
            or any(type(u) is not str or not u for u in root_pad_uuids)
            or type(moving_refs) not in (list,tuple,set) or not 1<=len(moving_refs)<=8
            or len(set(moving_refs))!=len(moving_refs) or any(type(r) is not str or not r for r in moving_refs)
            or kind not in ('scalar_input','rated_supply','ground_return') or type(board_hint) is not str or not board_hint
            or type(allow_full_current_supply_width)is not bool
            or allow_full_current_supply_width and kind!='rated_supply'
            or type(allow_owned_locked) is not bool or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('bounded_explicit_source_cell_fork_context_required')
    track_bound=(16 if kind=='ground_return' else 8) if max_tracks is None else max_tracks
    length_mm=(24. if kind=='ground_return' else 16.) if max_length_mm is None else max_length_mm
    if (type(track_bound) is not int or not 1<=track_bound<=32
            or type(length_mm) not in (int,float) or not math.isfinite(length_mm) or not 0<length_mm<=32.):
        raise ValueError('bounded_explicit_source_fork_work_scope_required')
    for retained in (retained_ground_pad_uuids,retained_ground_track_uuids):
        if (type(retained) not in (list,tuple) or len(retained)>64 or len(set(retained))!=len(retained)
                or any(type(u) is not str or not u for u in retained)
                or retained and kind!='ground_return'):
            raise ValueError('bounded_retained_source_ground_contacts_required')
    source=Path(board.GetFileName())
    if not board.GetFileName() or not source.is_file():raise ValueError('actual_saved_source_cell_fork_required')
    deadline=time.monotonic()+timeout_s;binding=row._source_binding(board);digest=force._hash(source)
    if row._source_binding(pcbnew.LoadBoard(str(source)))!=binding:
        raise ValueError('literal_saved_native_source_fork_snapshot_required')
    pads={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
    tracks={force._uid(t):t for t in board.GetTracks()}
    if len(pads)+len(tracks)>16384 or not set(root_pad_uuids)<=pads.keys():
        raise ValueError('bounded_literal_native_fork_roots_required')
    roots=[pads[u] for u in sorted(root_pad_uuids)]
    if (not set(retained_ground_pad_uuids)<=pads.keys() or not set(retained_ground_track_uuids)<=tracks.keys()
            or any(pads[u].GetNetname()!='GND' for u in retained_ground_pad_uuids)
            or any(tracks[u].GetNetname()!='GND' for u in retained_ground_track_uuids)):
        raise ValueError('literal_retained_source_ground_contacts_required')
    if (any(p.GetParentFootprint().GetReference() not in moving_refs for p in roots)
            or len({str(p.GetNetname()) for p in roots})!=1
            or len({cells.cec_return_escape.smd_surface_layer(p) for p in roots})!=1):
        raise ValueError('one_net_one_surface_moving_source_fork_required')
    net=str(roots[0].GetNetname());face=cells.cec_return_escape.smd_surface_layer(roots[0])
    if (not net or (net=='GND')!=(kind=='ground_return') or face is None or roots[0].GetNetCode()<=0):
        raise ValueError('positive_non_ground_surface_fork_required')
    typed={force._uid(p):_typed_root(board,p,kind,board_hint) for p in roots}
    with force._thermal_hint(board_hint):
        domains=topology.board_current_domains(board,board_hint)
        explicit=synth.spec_net_current_contract(board_hint,net)
    protected=set(fr.coupled_pair_nets(board))|{n for q in semantics.analog_input_pairs(board) for n in (q['p'],q['n'])}
    if net in protected:raise ValueError('paired_source_fork_requires_coupled_owner')
    resolver=fr._project_netclass_resolver(str(source),board=board)
    classification=field.classify_net(net,netclass=resolver(net))
    spec=cells._netclass(board,net);floor=max(200000,int(board.GetDesignSettings().m_TrackMinWidth),int(spec['width']))
    contract=None
    if kind=='scalar_input':
        if (net in domains or explicit is not None or classification['power'] or classification['aggressor']
                or any(not z.GetIsRuleArea() and z.GetNetname()==net for z in board.Zones())):
            raise ValueError('unprotected_source_scalar_input_fork_required')
    elif kind=='rated_supply':
        model,domain,contract=full._model(board,source,net,board_hint)
        if model!='explicit_all_terminal_distributed_supply':
            raise ValueError('explicit_complete_distributed_small_supply_fork_required')
        floor=max(floor,full._source_width_floor(board,source,contract,face))
    grouped={force._uid(i) for group in board.Groups() for i in group.GetItems()}
    possible={u:t for u,t in tracks.items() if t.GetClass()=='PCB_TRACK' and t.GetNetname()==net
        and t.GetLayer()==face and u not in grouped and not t.HasSolderMask()
        and (not t.IsLocked() or allow_owned_locked) and floor<=t.GetWidth()
        and 0<t.GetLength()<=8000000 and u not in retained_ground_track_uuids
        and not any(t.GetEffectiveShape(face).Collide(pads[p].GetEffectiveShape(face),0)
            for p in retained_ground_pad_uuids if pads[p].IsOnLayer(face))}
    seed_plan=None
    if allow_full_current_supply_width:
        # This is a separate positive whole-current cut, not a higher signal
        # width ceiling. Derive its ONE actual Source width from every eligible
        # departure touching a typed moving root. Incomplete/mixed/underwidth
        # ownership refuses; neither nearest width nor a per-load guess wins.
        seeds=[]
        for uid,item in possible.items():
            _tick(deadline)
            if any(item.GetEffectiveShape(face).Collide(p.GetEffectiveShape(face),0)for p in roots):
                seeds.append(uid)
        if not seeds:raise ValueError('source_fork_has_no_owned_departures')
        seed_plan=full.plan(board,source,board_hint=board_hint,retired_track_uuids=sorted(seeds),
            timeout_s=max(.001,deadline-time.monotonic()),max_source_cut_mm=length_mm)
        eligible={u:t for u,t in possible.items()if t.GetWidth()==seed_plan['width_nm']}
    else:
        eligible={u:t for u,t in possible.items()if t.GetWidth()<=350000}
    same_pads=[p for p in pads.values() if p.GetNetname()==net and p.IsOnLayer(face)]
    moving=[p for p in same_pads if p.GetParentFootprint().GetReference() in moving_refs
        and force._uid(p) not in retained_ground_pad_uuids]
    fixed=[p for p in same_pads if p.GetParentFootprint().GetReference() not in moving_refs
        or force._uid(p) in retained_ground_pad_uuids]
    fixed += [t for t in tracks.values() if t.GetNetname()==net and t.IsOnLayer(face) and force._uid(t) not in eligible]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()==net and z.IsOnLayer(face)]
    if zones:raise ValueError('source_fork_surface_pour_requires_separate_island_owner')
    def hit(a,b):
        _tick(deadline)
        return a.GetEffectiveShape(face).Collide(b.GetEffectiveShape(face),0)
    selected={u for u,t in eligible.items() if any(hit(t,p) for p in roots)}
    if not selected:raise ValueError('source_fork_has_no_owned_departures')
    # Every old root contact must be represented, including a direct fixed
    # barrel contact. Unowned strokes may be retained, but need exact ports.
    pending=sorted(selected);seen=set();root_material={force._uid(p):p for p in roots}
    while pending:
        _tick(deadline)
        if len(selected)>track_bound:
            raise ValueError(('source_ground_fork_track_scope_exceeded:'+str(track_bound)+':'+repr(sorted(selected)))
                if kind=='ground_return' else 'source_fork_eight_track_scope_exceeded' if track_bound==8
                else 'source_fork_track_scope_exceeded:'+str(track_bound))
        uid=pending.pop()
        if uid in seen:continue
        seen.add(uid);item=eligible[uid]
        # A moving land itself is real copper between its departures. Track
        # endpoints need not meet each other at that land's centre. Expand
        # through the independently typed land, never through a fixed peer.
        new_pads={force._uid(p):p for p in moving if hit(item,p) or
            any(hit(p,other) for other in root_material.values())}
        for puid,pad in new_pads.items():
            if puid in root_material:continue
            try:contract=_typed_root(board,pad,kind,board_hint)
            except ValueError as original:
                if kind!='ground_return':raise
                # A literal existing address-to-Ground strap inside the
                # moving package is a restoration boundary, not a newly
                # inferred Ground pin or permission to start a Ground cut
                # at an address input. It is reached only from an already
                # owned manufacturer Ground/root through real source metal.
                try:contract=_typed_root(board,pad,kind,board_hint,fixed_ground_boundary=True)
                except ValueError:raise original
                if contract['role']!='address':raise original
                contract.update(existing_source_ground_address_strap_only=True,
                    new_ground_role_or_current_inferred=False)
            typed[puid]=contract;root_material[puid]=pad
            departures={u for u,t in eligible.items() if u not in selected and hit(t,pad)}
            selected|=departures;pending.extend(sorted(departures))
        if len(root_material)>8:raise ValueError('source_fork_eight_moving_land_scope_exceeded')
        if kind!='ground_return' and any(hit(item,p) for p in fixed):continue
        neighbors={u for u,t in eligible.items() if u not in selected and hit(item,t)
            and (kind!='ground_return' or _contact_outside_fixed(item,t,fixed,face,deadline))}
        selected|=neighbors;pending.extend(sorted(neighbors))
    length_bound=round(length_mm*1e6)
    if len({eligible[u].GetWidth() for u in selected})!=1 or sum(eligible[u].GetLength() for u in selected)>length_bound:
        raise ValueError('bounded_uniform_full_width_source_fork_required')
    all_material=[*same_pads,*[t for t in tracks.values() if t.GetNetname()==net and t.IsOnLayer(face)]]
    if not all(any(hit(p,eligible[u]) for u in selected) for p in root_material.values()):
        raise ValueError('every_requested_source_fork_root_must_touch_owned_copper')
    fixed_contacts={force._uid(i):i for i in all_material if force._uid(i) not in selected
        and force._uid(i) not in root_material and any(hit(i,eligible[u]) for u in selected)}
    # Direct retained contacts under a departing root remain obligations even
    # when none of the retired strokes happens to touch that native barrel.
    for item in all_material:
        _tick(deadline)
        if force._uid(item) not in selected and force._uid(item) not in root_material and any(hit(item,p) for p in root_material.values()):
            fixed_contacts[force._uid(item)]=item
    ports=[]
    fixed_ground_contracts=[]
    for uid,item in sorted(fixed_contacts.items()):
        _tick(deadline)
        if kind=='ground_return' and item.GetClass()=='PAD':
            # A small Ground return is not the ATX/PTH injection trunk.
            # Even stationary contacted lands must be positively typed
            # low-power Ground/reference/bypass terminals. Barrels and
            # other retained copper remain restoration ports, never cuts.
            fixed_ground_contracts.append(_typed_root(board,item,kind,board_hint,fixed_ground_boundary=True))
        if item.GetClass() in ('PAD','PCB_VIA'):
            point=tuple(item.GetPosition())
        elif item.GetClass()=='PCB_TRACK':
            points={tuple(p) for u in selected for p in (eligible[u].GetStart(),eligible[u].GetEnd())
                if item.GetEffectiveShape(face).Collide(p,0)}
            points|={tuple(p) for p in (item.GetStart(),item.GetEnd())
                if any(eligible[u].GetEffectiveShape(face).Collide(p,0) for u in selected)}
            if not points:raise ValueError('source_fork_off_lattice_fixed_body_contact_requires_separate_owner')
            point=min(points)
        else:raise ValueError('source_fork_unknown_fixed_native_contact')
        ports.append(dict(native_uuid=uid,native_class=item.GetClass(),at_nm=list(point),layer_id=int(face)))
    if not ports or len(ports)>16:raise ValueError('one_to_sixteen_retained_native_fork_ports_required')
    locked=sorted(u for u in selected if eligible[u].IsLocked())
    q=dict(schema=1,scope='source_typed_complete_local_multiport_fork',kind=kind,net=net,layer=int(face),
        source=str(source.resolve()),source_sha256=digest,source_native_binding=binding,
        requested_root_pad_uuids=sorted(root_pad_uuids),moving_refs=sorted(moving_refs),
        moving_source_terminal_contracts=[typed[u] for u in sorted(typed)],
        moving_source_pad_uuids=sorted(typed),track_uuids=sorted(selected),
        width_nm=int(eligible[min(selected)].GetWidth()),source_length_nm=sum(eligible[u].GetLength() for u in selected),
        retained_native_ports=ports,source_field_classification=classification,board_hint=board_hint,
        source_owned_locked_track_uuids=locked,allow_owned_locked=allow_owned_locked,
        source_work_bounds=dict(max_tracks=track_bound,max_length_mm=length_mm),
        no_per_device_current_or_output_mode_inference=True,sensitive_role_reclassification=False,
        source_vias_zones_wide_tracks_and_groups_never_retired=not any(
            eligible[u].GetWidth()>350000 for u in selected),
        every_source_partition_and_fixed_port_still_requires_reconstruction=True,
        current_authority=False,routing_admitted=False,fab_ready=False,release_authority=False)
    if kind=='rated_supply':
        _tick(deadline)
        q['full_current_source_plan']=full.plan(board,source,board_hint=board_hint,retired_track_uuids=sorted(selected),
            timeout_s=max(.001,deadline-time.monotonic()),max_source_cut_mm=length_mm)
        with force._thermal_hint(board_hint):
            q['unchanged_full_rail_current_contract']=cells._supply_current_widths(board,net)
        if not q['unchanged_full_rail_current_contract']:
            raise ValueError('complete_unchanged_full_supply_contract_required')
        if allow_full_current_supply_width:
            q.update(allow_full_current_supply_width=True,
                full_current_source_seed_plan=seed_plan,
                source_vias_zones_and_groups_never_retired=True,
                source_width_is_actual_uniform_whole_current_cut=True,
                no_wider_scalar_or_ground_fork_authority=True)
    if kind=='ground_return':
        q.update(fixed_ground_terminal_contracts=fixed_ground_contracts,
            retained_ground_pad_uuids=sorted(retained_ground_pad_uuids),
            retained_ground_track_uuids=sorted(retained_ground_track_uuids),
            source_ground_width_preserved_not_aggregate_injection_rating=True,
            no_ground_current_allocation_inferred=True,
            every_retained_ground_fragment_plane_and_original_return_still_requires_receiving=True)
    _tick(deadline)
    if row._source_binding(board)!=binding or force._hash(source)!=digest:
        raise ValueError('source_cell_fork_changed_during_inventory')
    return json.loads(json.dumps(q,allow_nan=False))


def fixed_cohorts(board,proposal,*,deadline):
    """Conservative explicit-copper components, never a whole-net name merge.

    Do not use a pre-cut cache, moving source lands or unsplit zone objects as
    connectivity credit. Omitting zones can add a restoration demand, never
    erase a real one. Independent complete native partitions still receive.
    """
    moving=set(proposal['moving_refs']);net=proposal['net'];live={}
    for fp in board.GetFootprints():
        if fp.GetReference() in moving:continue
        for pad in fp.Pads():
            if pad.GetNetname()==net:live[force._uid(pad)]=pad
    live.update({force._uid(t):t for t in board.GetTracks() if t.GetNetname()==net})
    if set(proposal['track_uuids'])&live.keys():raise ValueError('shared_source_fork_not_privately_retired')
    graph=pcbnew.CONNECTIVITY_DATA()
    for item in live.values():
        _tick(deadline)
        if not graph.Add(item):raise ValueError('fixed_fork_native_graph_item_refused')
    cohorts=[];remaining={p['native_uuid']:p for p in proposal['retained_native_ports']}
    if not remaining.keys()<=live.keys():raise ValueError('retained_native_fork_port_missing')
    for port in remaining.values():
        item=live[port['native_uuid']]
        if (item.GetNetname()!=net or not item.IsOnLayer(port['layer_id'])
                or not item.GetEffectiveShape(port['layer_id']).Collide(pcbnew.VECTOR2I(*port['at_nm']),0)):
            raise ValueError('exact_retained_native_fork_port_geometry_required')
    while remaining:
        _tick(deadline);uid=min(remaining)
        reached={uid}|{force._uid(i) for i in graph.GetConnectedItems(live[uid])}
        own=sorted(remaining.keys()&reached);cohorts.append(dict(ports=[remaining.pop(u) for u in own],
            native_component_uuids=sorted(reached&live.keys())))
    return cohorts


def supply_root_ids(values):
    """Explicit construction choices, never new fork or current authority."""
    if (type(values)not in(list,tuple)or len(values)>8
            or any(type(u)is not str or not u for u in values)or len(set(values))!=len(values)):
        raise ValueError('bounded_unique_shared_supply_root_pad_uuids_required')
    return sorted(values)


def bind_supply_roots(forks,values):
    """Every choice must already be an independently typed moving supply port."""
    values=supply_root_ids(values)
    for uid in values:
        matches=[q for q in forks if uid in q['moving_source_pad_uuids']]
        if (len(matches)!=1 or matches[0]['kind']!='rated_supply'
                or not matches[0].get('unchanged_full_rail_current_contract')):
            raise ValueError('shared_supply_root_must_belong_to_one_complete_Source_supply_fork')
        typed=[p for p in matches[0]['moving_source_terminal_contracts']if p['pad_uuid']==uid]
        if len(typed)!=1 or typed[0]['role']not in('power_input','source_selected_bypass_supply'):
            raise ValueError('shared_supply_root_must_keep_actual_Source_supply_role')
    return values


def connections(board,proposal,*,mandatory_links=(),timeout_s=10.,preferred_supply_root_pad_uuids=()):
    """A finite source-typed minimum tree, not a global route/placement proof."""
    deadline=full._budget(timeout_s);pads={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
    chosen=bind_supply_roots([proposal],preferred_supply_root_pad_uuids)
    moving=proposal['moving_source_pad_uuids'];cohorts=fixed_cohorts(board,proposal,deadline=deadline)
    if not set(moving)<=pads.keys():raise ValueError('moving_native_fork_terminal_missing')
    groups=[[dict(pad_uuid=u,at_nm=list(pads[u].GetPosition()),layers=[proposal['layer']])] for u in moving]
    groups += [[dict(at_nm=p['at_nm'],layers=[p['layer_id']],native_uuids=[p['native_uuid']]) for p in cohort['ports']] for cohort in cohorts]
    parent=list(range(len(groups)))
    def root(i):
        while parent[i]!=i:i=parent[i]
        return i
    indexes={u:i for i,u in enumerate(moving)}
    for i,cohort in enumerate(cohorts):indexes.update({u:len(moving)+i for u in cohort['native_component_uuids']})
    for a,b in mandatory_links:
        if a in indexes and b in indexes:parent[root(indexes[a])]=root(indexes[b])
    # A complete mandatory local-supply link already joins owner and bypass.
    # Its geometrically shortest member need not be the routable departure.
    # Choose ONLY a declared member of that original union; every old port
    # and mandatory link survives and retains its full Source rail width.
    initial=[root(i)for i in range(len(groups))];representatives={}
    for uid in chosen:
        index=indexes[uid];component=initial[index]
        if (sum(initial[i]==component for i in range(len(moving)))<2
                or component in representatives):
            raise ValueError('one_shared_supply_representative_per_mandatory_local_cohort_required')
        pad=pads[uid]
        if (pad.GetNetname()!=proposal['net']or not pad.IsOnLayer(proposal['layer'])
                or pad.HasHole()or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD):
            raise ValueError('actual_posed_Source_supply_representative_required')
        representatives[component]=uid
    edges=[]
    for i,left in enumerate(groups):
        for j in range(i+1,len(groups)):
            for a in left:
                for b in groups[j]:
                    if initial[i]!=initial[j]and any(
                            component in representatives and port.get('pad_uuid')!=representatives[component]
                            for component,port in((initial[i],a),(initial[j],b))):continue
                    edges.append((math.dist(a['at_nm'],b['at_nm']),i,j,a,b))
    requests=[]
    for distance,i,j,a,b in sorted(edges,key=lambda e:(e[0],e[1],e[2],repr(e[3]),repr(e[4]))):
        _tick(deadline)
        if root(i)==root(j):continue
        parent[root(i)]=root(j)
        requests.append(dict(kind='source_boundary',net=proposal['net'],a=a,b=b,width_nm=proposal['width_nm'],
            source_typed_multiport_fork=proposal,
            **({'unchanged_full_rail_current_contract':proposal['unchanged_full_rail_current_contract']}
                if proposal['kind']=='rated_supply' else {})))
        if chosen:requests[-1]['Source_shared_supply_root_choices']=chosen
    if len({root(i) for i in range(len(groups))})!=1:
        raise ValueError('complete_native_multiport_fork_tree_required')
    return requests
