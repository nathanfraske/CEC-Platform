"""Bounded native completion of declared same-net analog package straps.

Auxiliary bus-voltage pins do not become force-current terminals or ordinary
GPIO. Only known device pin roles and identical live schematic nets authorize
a local strap. No placement, net definition, via, pour, rating or release gate
is changed. Native DRC, exact saved receiving and Kelvin isolation still follow.
"""
import math
import time

import pcbnew


def native_contact_graph(board,net,*,deadline,max_items=4096):
    """Read-only transitive native copper contact, never Kelvin qualification."""
    if (not net or type(max_items) is not int or not 1<=max_items<=4096
            or not math.isfinite(deadline)):
        raise ValueError('bounded_native_contact_graph_required')
    if time.monotonic()>=deadline:raise ValueError('native_contact_deadline')
    pads=[p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname()==net]
    tracks=[t for t in board.GetTracks() if t.GetNetname()==net]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()==net]
    items=[*pads,*tracks,*zones]
    if len(items)>max_items:raise ValueError('native_contact_inventory_bound')
    if any(not z.IsFilled() for z in zones):raise ValueError('native_contact_fill_unknown')
    if len({i.m_Uuid.AsString() for i in items})!=len(items):
        raise ValueError('native_contact_identity_ambiguous')
    conn=pcbnew.CONNECTIVITY_DATA()
    for item in items:
        if time.monotonic()>=deadline:raise ValueError('native_contact_deadline')
        if not conn.Add(item):raise ValueError('native_contact_item_refused')
    if time.monotonic()>=deadline:raise ValueError('native_contact_deadline')
    return conn


def reached(graph,pad,other,*,deadline):
    if time.monotonic()>=deadline:raise ValueError('native_contact_deadline')
    if pad.GetNetCode()<=0 or other.GetNetCode()!=pad.GetNetCode():return False
    uid=other.m_Uuid.AsString()
    return uid==pad.m_Uuid.AsString() or any(i.m_Uuid.AsString()==uid
        for i in graph.GetConnectedItems(pad))


def _isolated_source_scope(board,fp,a,b,graph,*,deadline):
    """Positive producer scope for the saved receiver's isolated input tier.

    This is not receiving: it rejects ineligible Source work before emitting
    copper. Independent literal isolation and all full saved-board gates
    still receive every generated item against the ORIGINAL parent.
    """
    import cec_pair_semantics as semantics
    import cec_device_power_roles as roles
    import cec_measurement_terminal_access as access
    import cec_force_current as force
    if time.monotonic()>=deadline:raise ValueError('source_auxiliary_scope_deadline')
    paired=semantics.footprint_input_contract(fp)
    declared=semantics.current_auxiliary_input_contract(paired[0])if paired else None
    model=roles.footprint_contract(fp)
    if (not paired or not declared or not model or fp.IsDNP()or fp.IsLocked()
            or len(list(fp.Pads()))!=len(model['pins'])
            or {p.GetNumber()for p in fp.Pads()}!=set(model['pins'])
            or b.GetNumber()not in paired[1]
            or not any(q[:2]==(a.GetNumber(),b.GetNumber())for q in declared[1])
            or any(g.ContainsItem(item)for g in board.Groups()for item in (fp,a,b))):
        raise ValueError('complete_ungrouped_manufacturer_source_auxiliary_package_required')
    if (not a.GetNetname()or a.GetNetname()!=b.GetNetname()
            or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole()
                or len(list(p.GetLayerSet().CuStack()))!=1
                or model['pins'].get(p.GetNumber())!='measurement'for p in (a,b))
            or list(a.GetLayerSet().CuStack())!=list(b.GetLayerSet().CuStack())):
        raise ValueError('same_net_surface_source_measurement_pair_required')
    islands=[]
    for p in (a,b):
        connected=list({force._uid(i):i for i in [p,*graph.GetConnectedItems(p)]}.values())
        island=access._input_island(p,connected,model,deadline=deadline)
        if island is None:raise ValueError('source_auxiliary_ends_not_stranded_measurement_islands')
        islands.append(island)
    return dict(eligible=True,owner_uuid=force._uid(fp),pad_uuids=[force._uid(a),force._uid(b)],
        source_island_uuids=islands,net=str(a.GetNetname()),manufacturer_source=model['source'],
        independent_saved_receiving_still_required=True,release_authority=False)


def construct(board,*,board_path='',width_mm=.25,max_span_mm=2.,timeout_s=3.,avoid=(),
              require_source_isolated=False):
    """Guarded 0/45/90 local straps on a caller-owned private board only."""
    import cec_pair_semantics as semantics
    import cec_fr as fr
    import cec_decoupler_cell as cell
    import cec_force_current as force
    import cec_native_items as native
    if (any(type(v) not in (int,float) or not math.isfinite(v) for v in
            (width_mm,max_span_mm,timeout_s)) or not .1<=width_mm<=.4
            or not 0<max_span_mm<=4 or not 0<timeout_s<=10
            or type(require_source_isolated)is not bool):
        raise ValueError('bounded_auxiliary_sense_strap_policy_required')
    deadline=time.monotonic()+timeout_s
    rows=[];generated=[];before={force._uid(t) for t in board.GetTracks()}
    selected=sorted((fp for fp in board.GetFootprints()
                     if semantics.current_auxiliary_input_contract(fp.GetValue())),
                    key=lambda f:f.GetReference())
    if len(selected)>64:raise ValueError('auxiliary_device_inventory_bound')
    # Inventory on the unchanged Source epoch, BEFORE constructing any strap.
    # A later package cannot inherit scope from this invocation's new copper.
    source_scopes={};source_graphs={}
    if require_source_isolated:
        for fp in selected:
            for a_pin,b_pin,*_ in semantics.current_auxiliary_input_contract(fp.GetValue())[1]:
                aa=[p for p in fp.Pads()if p.GetNumber()==a_pin]
                bb=[p for p in fp.Pads()if p.GetNumber()==b_pin]
                key=(force._uid(fp),a_pin,b_pin)
                try:
                    if len(aa)!=1 or len(bb)!=1:raise ValueError('source_auxiliary_pin_identity_ambiguous')
                    a,b=aa[0],bb[0];net=a.GetNetname()
                    if not net or net!=b.GetNetname():continue
                    if net not in source_graphs:
                        source_graphs[net]=native_contact_graph(board,net,deadline=deadline)
                    graph=source_graphs[net]
                    if reached(graph,a,b,deadline=deadline):continue
                    source_scopes[key]=_isolated_source_scope(board,fp,a,b,graph,deadline=deadline)
                except ValueError as exc:
                    if time.monotonic()>=deadline:raise
                    source_scopes[key]=dict(eligible=False,reason=str(exc),release_authority=False)
    for fp in selected:
        device,pairs=semantics.current_auxiliary_input_contract(fp.GetValue())
        for a_pin,b_pin,a_function,b_function in pairs:
            row=dict(ref=fp.GetReference(),device=device,pins=[a_pin,b_pin],
                roles=[a_function,b_function],status='refused',release_authority=False,
                current_capacity_qualified=False,kelvin_isolation_qualified=False)
            rows.append(row);new=[]
            try:
                aa=[p for p in fp.Pads() if p.GetNumber()==a_pin]
                bb=[p for p in fp.Pads() if p.GetNumber()==b_pin]
                if len(aa)!=1 or len(bb)!=1:raise ValueError('auxiliary_pin_identity_ambiguous')
                a,b=aa[0],bb[0]
                row.update(net=a.GetNetname(),pad_uuids=[force._uid(a),force._uid(b)])
                if not a.GetNetname() or a.GetNetname()!=b.GetNetname():
                    row.update(status='not_applicable',reason='live_schematic_nets_not_tied');continue
                graph=native_contact_graph(board,a.GetNetname(),deadline=deadline)
                if reached(graph,a,b,deadline=deadline):
                    row.update(status='covered',native_package_contact=True);continue
                if require_source_isolated:
                    scope=source_scopes.get((force._uid(fp),a_pin,b_pin))
                    if not scope or scope.get('eligible')is not True:
                        row.update(status='deferred',reason=(scope or {}).get('reason',
                            'positive_original_source_auxiliary_scope_required'),
                            source_scope=scope);continue
                    row['source_scope']=scope
                layers=set(a.GetLayerSet().CuStack())&set(b.GetLayerSet().CuStack())
                layers&=set(board.GetEnabledLayers().CuStack())
                if (len(layers)!=1 or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in (a,b))):
                    raise ValueError('auxiliary_strap_requires_one_surface_smd_layer')
                layer=next(iter(layers));start,end=a.GetPosition(),b.GetPosition()
                distance=math.hypot(end.x-start.x,end.y-start.y)/1e6
                if distance>max_span_mm:raise ValueError('auxiliary_package_span_exceeded')
                gap=max(int(board.GetDesignSettings().m_MinClearance),
                        int(cell._netclass(board,a.GetNetname())['clearance']))
                width=max(round(width_mm*1e6),int(board.GetDesignSettings().m_TrackMinWidth))
                if width>400000:raise ValueError('auxiliary_measurement_width_policy_exceeded')
                if require_source_isolated and width>350000:
                    raise ValueError('source_isolated_literal_measurement_width_exceeded')
                def leg_ok(left,right,half):
                    return (fr._edge_leg_clear(board,left,right,math.ceil(width/2))
                            and not fr._tap_reservation_hits([left,right],avoid,
                                net=a.GetNetname(),layer=board.GetLayerName(layer),
                                width_nm=width,clearance_nm=gap)
                            and not force._native_track_rule_hits(board,
                                pcbnew.SHAPE_SEGMENT(left,right,width),layer,cache={}))
                legs=fr._guarded_lastmile_legs(board,start,end,width,layer,gap,a.GetNetCode(),leg_ok,
                    allow_maze=False,deadline_monotonic=deadline,max_length_nm=round(max_span_mm*1e6))
                if not legs:raise ValueError('native_auxiliary_package_strap_blocked')
                if require_source_isolated and (len(legs)!=1 or
                        {tuple(p)for p in legs[0]}!={tuple(start),tuple(end)}):
                    raise ValueError('isolated_source_tier_requires_one_literal_package_strap')
                for left,right in legs:
                    t=pcbnew.PCB_TRACK(board);t.SetStart(left);t.SetEnd(right);t.SetWidth(width)
                    t.SetLayer(layer);t.SetNetCode(a.GetNetCode());t.SetLocked(True);board.Add(t);new.append(t)
                graph=native_contact_graph(board,a.GetNetname(),deadline=deadline)
                if not reached(graph,a,b,deadline=deadline):raise ValueError('generated_auxiliary_strap_not_connected')
                items=[dict(uuid=force._uid(t),net=t.GetNetname(),kind=t.GetClass(),
                    width_nm=t.GetWidth(),layer_id=t.GetLayer(),start_nm=list(t.GetStart()),end_nm=list(t.GetEnd())) for t in new]
                row.update(status='constructed',native_package_contact=True,generated_items=items)
                generated.extend(items)
            except Exception as exc:
                native.discard_items(board,new)
                row.update(reason=type(exc).__name__+':'+str(exc),generated_items=[])
    live={force._uid(t) for t in board.GetTracks()}
    if live-before!={r['uuid'] for r in generated}:raise ValueError('auxiliary_delta_inventory_mismatch')
    refused=[r for r in rows if r['status']=='refused']
    deferred=[r for r in rows if r['status']=='deferred']
    return dict(schema=1,operation='typed_same_net_auxiliary_sense_package_straps',
        ok=not refused,complete=not refused and not deferred,
        source_isolated_only=require_source_isolated,terminals=rows,refused=refused,
        deferred=deferred,generated_items=generated,
        joins=sum(r['status']=='constructed' for r in rows),generated_item_count=len(generated),
        release_authority=False,power_authority=False,kelvin_isolation_qualified=False,
        requires_independent_saved_native_drc_and_kelvin_receiving=True)
