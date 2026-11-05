"""Receive one Source-typed reference-divider Ground span, never arbitrary GND.

The Source must freshly compile as a closed selected two-resistor divider
feeding an actual manufacturer monitor pin. Its lower resistor already has
a literal in-pad, process-received reference entry. Only the full-class
straight surface span between that resistor's fixed lead and the monitor's
fixed Ground terminal can be replaced. All old live contact *material*, not
merely graph adjacency, remains covered. This distinct contract does not
relax the public small-span width limit or invent a Ground current budget.

Opaque Source-minus-cut replay, native partition/return/clearance/craft/field
guards are necessary, not current, native-DRC, Kelvin, fab or release admission.
No producer roles, stored netlists, part references or coordinate allowlists
grant ownership. Every invocation rederives actual Source and child objects.
"""
import math
from pathlib import Path
import tempfile
import time
import subprocess

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
cec_swig_guard.pin()
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_preservation as returns
import cec_ground_return_shortcut as shortcut
import cec_native_capsule_contact as capsule
import cec_native_ground_span_reflow as span
import cec_native_partition_pair as partitions
import cec_resistive_monitor_branch as resistors
import cec_route_corner_contacts as contacts
import cec_route_quality as quality
import cec_source_ground_leaf as fresh
import cec_source_literal_retirement as literal
import cec_source_literal_additions as opaque
import cec_source_no_connect as source_nc
import cec_source_retaining_ses_import as raw
import cec_synth_pipeline as synth
from cec_native_items import discard_items


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('divider_ground_span_deadline')


def _remaining(deadline):
    _tick(deadline)
    return min(10., deadline-time.monotonic())


def _pins(identity):
    """Actual selected embedded physical pins, including names lint omits."""
    fp, path, sf, symbol = identity
    libraries=[b for tag,b in sf.children if tag=='lib_symbols']
    if len(libraries)!=1:raise ValueError('divider_selected_symbol_library_required')
    tree=synth.parse_sexpr(libraries[0])
    selected=[n for n in synth._kids(tree,'symbol') if len(n)>1 and n[1]==symbol['lib_id']]
    if len(selected)!=1 or synth._first(selected[0],'extends') is not None:
        raise ValueError('divider_unique_complete_selected_symbol_required')
    stack=[selected[0]]; found={}; count=0
    while stack:
        node=stack.pop(); count+=1
        if count>8192:raise ValueError('divider_selected_symbol_bound')
        if not isinstance(node,list) or not node:continue
        if node[0]=='pin':
            number=synth._val(node,'number','')
            if not number or number in found or len(node)<2:
                raise ValueError('divider_unique_selected_pin_numbers_required')
            found[number]=(node[1],synth._val(node,'name',''))
        stack.extend(n for n in node if isinstance(n,list))
    numbers=[str(p.GetNumber()) for p in fp.Pads()]
    if len(numbers)!=len(set(numbers)) or set(found)!=set(numbers):
        raise ValueError('divider_complete_source_native_pin_map_required')
    return found


def _native_owner(board, ground_pad_uuid, deadline):
    """Positive selected topology only; no inferred Ground current demand."""
    pads=[p for f in board.GetFootprints() for p in f.Pads()]
    if len(pads)>16384:raise ValueError('divider_native_inventory_bound')
    targets=[p for p in pads if force._uid(p)==ground_pad_uuid]
    if len(targets)!=1:raise ValueError('divider_unique_actual_ground_land_required')
    ground=targets[0]; lower=ground.GetParentFootprint()
    if (not resistors.resistor_contract(lower) or ground.GetNetname()!='GND'
            or ground.GetNetCode()<=0):
        raise ValueError('divider_selected_lower_passive_ground_resistor_required')
    nodepad=next(p for p in lower.Pads() if force._uid(p)!=ground_pad_uuid)
    if nodepad.GetNetCode()<=0 or nodepad.GetNetCode()==ground.GetNetCode():
        raise ValueError('divider_distinct_positive_monitor_node_required')
    members=[p for p in pads if p.GetNetCode()==nodepad.GetNetCode()]
    if len(members)!=3:raise ValueError('divider_closed_three_land_monitor_node_required')
    monitors=[]; uppers=[]
    for p in members:
        _tick(deadline)
        if force._uid(p)==force._uid(nodepad):continue
        fp=p.GetParentFootprint(); monitor=roles.resistive_voltage_monitor_contract(fp,p.GetNumber())
        if monitor:
            supply=fp.FindPadByNumber(monitor['associated_power_pin'])
            if supply is None or supply.GetNetCode()<=0 or supply.GetNetCode() in (ground.GetNetCode(),nodepad.GetNetCode()):
                raise ValueError('divider_actual_distinct_associated_supply_required')
            monitors.append((p,monitor,supply))
        elif resistors.resistor_contract(fp):
            other=next(q for q in fp.Pads() if force._uid(q)!=force._uid(p))
            uppers.append((p,other))
        else:raise ValueError('divider_unknown_or_load_bearing_monitor_node')
    if len(monitors)!=1 or len(uppers)!=1:
        raise ValueError('divider_unique_selected_upper_and_manufacturer_monitor_required')
    monitor, contract, supply=monitors[0]; uppernode,upperpower=uppers[0]
    if upperpower.GetNetCode()!=supply.GetNetCode():
        raise ValueError('divider_upper_rail_must_equal_actual_associated_supply')
    return ground,nodepad,uppernode,upperpower,monitor,supply,contract


def _owner(board, board_hint, ground_pad_uuid, deadline):
    selected=_native_owner(board,ground_pad_uuid,deadline)
    ground,nodepad,uppernode,upperpower,monitor,supply,contract=selected
    root=source_nc._root(board,board_hint).resolve()
    files,hashes,instances=fresh._hierarchy(root,deadline)
    tree,export=fresh._export(root,deadline); comps,nets,node_net=fresh._tables(tree)
    exporter=Path(export['exporter']).resolve()
    if not exporter.is_file() or force._hash(exporter)!=export['exporter_sha256']:
        raise ValueError('divider_fresh_exporter_actual_path_and_hash_required')
    owners={force._uid(p.GetParentFootprint()):p.GetParentFootprint()
        for p in (ground,uppernode,monitor)}
    identities={}; pinmaps={}
    for uid,fp in owners.items():
        identity=fresh._identity(board,fp.GetReference(),comps,instances,deadline)
        identities[uid]=identity; pinmaps[uid]=_pins(identity)
        for pad in fp.Pads():
            pin=str(pad.GetNumber())
            physical=[p for p in identity[3]['pins'] if p['num']==pin]
            if len(physical)!=1:raise ValueError('divider_complete_unique_source_pin_map_required')
            actual=physical[0]
            if actual['type']!=pinmaps[uid][pin][0]:
                raise ValueError('divider_actual_source_pin_type_disagrees')
            for metadata,expected in ((str(pad.GetPinType()),pinmaps[uid][pin][0]),
                    (str(pad.GetPinFunction()),pinmaps[uid][pin][1])):
                if metadata and metadata!=expected:
                    raise ValueError('divider_native_pin_metadata_contradicts_actual_source')
            if node_net.get((fp.GetReference(),pin))!=str(pad.GetNetname()):
                raise ValueError('divider_complete_actual_source_membership_mismatch')
    monitorfp=monitor.GetParentFootprint(); model=roles.footprint_contract(monitorfp)
    monitorpins=pinmaps[force._uid(monitorfp)]
    if (not model or set(model['pins'])!=set(monitorpins)
            or monitorpins[str(monitor.GetNumber())]!=('input',contract['function'])
            or monitorpins[str(supply.GetNumber())]!=('power_in',
                {'7':'IN1','2':'IN2'}.get(str(supply.GetNumber())))):
        raise ValueError('divider_actual_named_manufacturer_monitor_and_supply_required')
    for fp in (ground.GetParentFootprint(),uppernode.GetParentFootprint()):
        if any(p[0]!='passive' for p in pinmaps[force._uid(fp)].values()):
            raise ValueError('divider_actual_source_resistor_pins_must_be_passive')
    for pad in selected[:6]:
        fresh._pin(identities[force._uid(pad.GetParentFootprint())],str(pad.GetNumber()))
    native={(p.GetParentFootprint().GetReference(),str(p.GetNumber()))
        for p in (nodepad,uppernode,monitor)}
    if nets.get(str(nodepad.GetNetname()))!=native:
        raise ValueError('divider_fresh_complete_closed_source_node_required')
    groundpins=[]
    for pin,role in model['pins'].items():
        p=monitorfp.FindPadByNumber(pin)
        if role=='ground' and p is not None and p.GetNetCode()==ground.GetNetCode():
            if monitorpins[pin]!=('power_in','GND'):
                raise ValueError('divider_actual_named_manufacturer_ground_pin_required')
            groundpins.append(p)
    if not groundpins:raise ValueError('divider_actual_manufacturer_ground_terminal_required')
    # The Source entry must already exist. This receiver cannot create/move a
    # drill or infer a process waiver merely from the fabrication profile.
    via=[]
    for v in board.GetTracks():
        _tick(deadline)
        if (v.GetClass()=='PCB_VIA' and v.GetNetCode()==ground.GetNetCode()
                and tuple(v.GetPosition())==tuple(ground.GetPosition())
                and v.IsLocked() and v.GetParentGroup()
                and fab.local_pofv_via_decision(board,v)[0]):
            refs=shortcut._reference_contacts(board,v)
            if len({row[1] for row in refs})>=2:via.append((v,refs))
    if len(via)!=1:raise ValueError('divider_one_existing_received_in_pad_two_plane_ground_entry_required')
    witness=cells._existing_return(board,ground,16.,allow_native_track_body=True)
    if witness is None or witness[0]!=0 or force._uid(witness[1])!=force._uid(via[0][0]):
        raise ValueError('divider_literal_zero_length_existing_ground_entry_required')
    if (hashes!={str(p):force._hash(p) for p in files}
            or force._hash(exporter)!=export['exporter_sha256']):
        raise ValueError('divider_fresh_hierarchy_changed')
    metadata=dict(kind='fresh_source_closed_reference_divider_ground_span',
        canonical_root=str(root),source_files_sha256=hashes,fresh_export=export,
        lower_resistor_uuid=force._uid(ground.GetParentFootprint()),
        upper_resistor_uuid=force._uid(uppernode.GetParentFootprint()),
        monitor_footprint_uuid=force._uid(monitorfp),monitor_pad_uuid=force._uid(monitor),
        associated_supply_pad_uuid=force._uid(supply),ground_pad_uuid=ground_pad_uuid,
        closed_node_members=sorted([list(v) for v in native]),manufacturer_monitor=contract,
        source_entry_via_uuid=force._uid(via[0][0]),source_reference_contacts=via[0][1],
        inferred_ground_current_budget=False,current_qualified=False,release_authority=False)
    return metadata,ground,groundpins


def _plan(board, retired_track_uuids, points_nm, ground, device_ground, deadline):
    if (type(retired_track_uuids) is not list or not 1<=len(retired_track_uuids)<=8
            or any(type(u) is not str or not u for u in retired_track_uuids)
            or len(set(retired_track_uuids))!=len(retired_track_uuids)
            or type(points_nm) is not list or not 2<=len(points_nm)<=16
            or any(type(p) not in (list,tuple) or len(p)!=2 or any(type(v) is not int
                or abs(v)>2000000000 for v in p) for p in points_nm)):
        raise ValueError('bounded_explicit_divider_ground_span_required')
    tracks=list(board.GetTracks()); live={force._uid(t):t for t in tracks}
    if len(live)!=len(tracks) or not set(retired_track_uuids)<=live.keys():
        raise ValueError('divider_exact_actual_source_track_scope_required')
    old=[live[u] for u in retired_track_uuids]; face=int(old[0].GetLayer()); width=old[0].GetWidth()
    floor=max(int(board.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(board,'GND')['width']))
    if (not 0<width==floor or face not in (pcbnew.F_Cu,pcbnew.B_Cu)
            or cells.cec_return_escape.smd_surface_layer(ground)!=face
            or any(t.GetClass()!='PCB_TRACK' or t.GetNetCode()!=ground.GetNetCode()
                or t.GetWidth()!=width or int(t.GetLayer())!=face or t.IsLocked()
                or t.GetParentGroup() or t.HasSolderMask() or t.GetLength()<=0
                or any(abs(v)+(width+1)//2>2000000000 for p in (t.GetStart(),t.GetEnd()) for v in p) for t in old)
            or any(g.ContainsItem(t) for g in board.Groups() for t in old)):
        raise ValueError('divider_unlocked_ungrouped_exact_full_class_surface_chain_required')
    prior=span._chain(old); points=[tuple(p) for p in points_nm]
    if [points[0],points[-1]]!=[prior[0],prior[-1]]:
        raise ValueError('divider_exact_fixed_boundary_ports_required')
    if any(a==b or not quality.is_canonical_stroke(a,b,tolerance_nm=0) for a,b in zip(points,points[1:])):
        raise ValueError('divider_exact_octilinear_nonzero_strokes_required')
    for a,b,c in zip(points,points[1:],points[2:]):
        u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1])
        dot=sum(x*y for x,y in zip(u,v));cross=u[0]*v[1]-u[1]*v[0]
        if dot<=0 or abs(cross)>dot:raise ValueError('divider_turns_at_most_45_degrees_required')
    span._simple_reuse_path(points)
    before=sum(t.GetLength() for t in old);after=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
    if before>25000000 or after>before+1000000 or points==prior:
        raise ValueError('divider_existing_one_mm_extra_span_bound_required')
    # Narrow physical ownership: one fixed boundary at this divider's literal
    # retained lead, the other at this same monitor's actual Ground land.
    caps=[pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*p),pcbnew.VECTOR2I(*p),width) for p in (prior[0],prior[-1])]
    lower=[]; monitor=[]
    for i,cap in enumerate(caps):
        if any(cap.Collide(p.GetEffectiveShape(face),0) for p in device_ground if p.IsOnLayer(face)):
            monitor.append(i)
        for t in tracks:
            _tick(deadline)
            if (force._uid(t) in retired_track_uuids or t.GetClass()!='PCB_TRACK'
                    or t.GetNetCode()!=ground.GetNetCode() or int(t.GetLayer())!=face
                    or t.GetWidth()!=width or t.GetLength()>1500000):continue
            ends=[tuple(t.GetStart()),tuple(t.GetEnd())]
            if (prior[i*(len(prior)-1)] in ends and t.GetEffectiveShape(face).Collide(ground.GetEffectiveShape(face),0)
                    and ground.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*ends[1-ends.index(prior[i*(len(prior)-1)])]),0)):
                lower.append((i,force._uid(t)))
    attachments=[(l,m,u) for l,u in lower for m in monitor if l!=m]
    if len(attachments)!=1:
        raise ValueError('divider_fixed_lower_resistor_lead_and_same_device_ground_ports_required')
    return dict(retired_track_uuids=sorted(retired_track_uuids),source_layer=face,source_width_nm=width,
        source_points_nm=[list(p) for p in prior],replacement_points_nm=[list(p) for p in points],
        source_length_nm=before,replacement_length_nm=after,maximum_extra_nm=1000000,
        fixed_lower_lead_uuid=attachments[0][2]),old


def _process(node):
    return sorted((syntax._freeze(q) for q in node[1:] if not
        (isinstance(q,list) and q and q[0] in ('uuid','start','end'))),key=repr)


def _opaque_preservation(source,candidate,retired,ground_ids):
    """Exact opaque nodes/root records, permitting ONLY received Ground fills."""
    texts=[raw.raw_text(p) for p in (source,candidate)]
    inventories=[opaque._inventory(t) for t in texts]
    old,new=[row[0] for row in inventories]
    for uid,(_,_,node) in old.items():
        if uid in retired:continue
        if uid not in new:raise ValueError('divider_opaque_source_object_missing')
        expected=raw.replace_fills(node,new[uid][2]) if uid in ground_ids else node
        if expected!=new[uid][2]:raise ValueError('divider_opaque_source_node_changed:'+uid)
    records=[]
    for text,(nodes,_,spans,_) in zip(texts,inventories):
        records.append([text[a:b] for a,b in spans if opaque._uuid(text[a:b]) is None])
    if records[0]!=records[1]:raise ValueError('divider_opaque_root_metadata_changed')
    return dict(all_retained_source_nodes_and_root_records_opaque_exact=True,
        only_existing_ground_fill_children_may_change=True)


def _contact_kernels(parent, child, old, rows, retired, face, deadline):
    """No area tolerances. Each old track/peer kernel is checked separately."""
    # Ground refill is independently received, but a same-face Ground zone is
    # NOT a fixed peer. This narrow owner deliberately refuses that domain:
    # a Source-zone kernel cannot be credited merely because the new track
    # covers it while the child's refilled peer has removed its own material.
    for board in (parent,child):
        zones=list(board.Zones())
        if len(zones)>16384:raise ValueError('divider_native_contact_inventory_bound')
        for zone in zones:
            _tick(deadline)
            if zone.GetIsRuleArea() or zone.GetNetname()!='GND' or not zone.IsOnLayer(face):continue
            if not zone.IsFilled() or not zone.HasFilledPolysForLayer(face):
                if any(zone.GetBoundingBox().Intersects(t.GetBoundingBox()) for t in [*old,*rows]):
                    raise ValueError('divider_contact_zone_fill_unknown')
                continue
            shape=zone.GetFilledPolysList(face)
            if any(shape.Collide(t.GetEffectiveShape(face),0) for t in [*old,*rows]):
                raise ValueError('divider_touched_same_face_ground_fill_is_not_a_fixed_contact_peer')
    replacement=pcbnew.SHAPE_POLY_SET()
    for t in rows:replacement.BooleanAdd(contacts.native_contact_polygon(t,face,deadline))
    source_polys={force._uid(t):contacts.native_contact_polygon(t,face,deadline) for t in old}
    proofs=[]; actual=set(); allowed=set(); incoming=[force._uid(t) for t in rows]
    items=[*parent.GetTracks(),*(p for f in parent.GetFootprints() for p in f.Pads()),*parent.Zones()]
    if len(items)>16384:raise ValueError('divider_native_contact_inventory_bound')
    for item in items:
        _tick(deadline); uid=force._uid(item)
        if uid in retired or not item.IsOnLayer(face):continue
        if item.GetClass()=='ZONE' and item.GetIsRuleArea():continue
        if item.GetClass()=='ZONE':
            if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                if any(item.GetBoundingBox().Intersects(t.GetBoundingBox()) for t in [*old,*rows]):
                    raise ValueError('divider_contact_zone_fill_unknown')
                continue
            shape=item.GetFilledPolysList(face)
        else:shape=item.GetEffectiveShape(face)
        touched=[t for t in old if shape.Collide(t.GetEffectiveShape(face),0)]
        new_touch=any(shape.Collide(t.GetEffectiveShape(face),0) for t in rows)
        if touched:allowed.add(uid)
        if new_touch:actual.add(uid)
        if not touched and not new_touch:continue
        if item.GetNetCode()!=old[0].GetNetCode():raise ValueError('divider_source_or_candidate_foreign_contact')
        peer=contacts.native_contact_polygon(item,face,deadline)
        for t in touched:
            kernel=source_polys[force._uid(t)].CloneDropTriangulation();kernel.BooleanIntersection(peer)
            if not kernel.OutlineCount():raise ValueError('divider_unknown_empty_native_contact_kernel')
            missing=kernel.CloneDropTriangulation();missing.BooleanSubtract(replacement)
            proof=dict(source_track_uuid=force._uid(t),retained_peer_uuid=uid,
                method='full_native_contact_polygon_containment_1nm_no_area_tolerance')
            if missing.OutlineCount():
                exact=capsule.prove(parent,force._uid(t),uid,child,incoming)
                if not exact.get('ok') or not exact.get('complete'):
                    raise ValueError('divider_full_source_contact_kernel_not_covered:'+force._uid(t)+':'+uid)
                proof.update(method='exact_integer_retained_straight_track_capsule',capsule=exact)
            proofs.append(proof)
    if actual!=allowed:raise ValueError('divider_retained_contact_identity_changed')
    return dict(all_old_native_contact_kernels_fully_covered=True,retained_contact_uuids=sorted(allowed),proofs=proofs)


def receive(source,candidate,board_hint,ground_pad_uuid,retired_track_uuids,points_nm,timeout_s=10.):
    """Independently receive a saved Source-qualified divider Ground-only child."""
    r=dict(schema=1,scope='fresh_source_reference_divider_ground_span',ok=False,complete=False,
        errors=[],current_qualified=False,routing_admitted=False,release_authority=False,
        no_ground_current_budget_or_public_small_span_width_waiver=True,
        full_native_current_field_kelvin_fabrication_and_release_receiving_still_required=True)
    try:
        deadline=span._deadline(timeout_s)
        if type(board_hint) is not str or not board_hint or type(ground_pad_uuid) is not str or not ground_pad_uuid:
            raise ValueError('divider_explicit_source_design_and_ground_land_required')
        paths=[Path(p).resolve() for p in (source,candidate)]
        if paths[0]==paths[1]:raise ValueError('divider_distinct_saved_source_and_child_required')
        epoch=force._code_identity(); families=[force._family(p,board_hint) for p in paths]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        owner,ground,device_ground=_owner(parent,board_hint,ground_pad_uuid,deadline);r['source_owner']=owner
        plan,oldtracks=_plan(parent,retired_track_uuids,points_nm,ground,device_ground,deadline);r['source_plan']=plan
        retired=set(retired_track_uuids);_,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        incoming=new.keys()-old.keys();live={force._uid(t):t for t in child.GetTracks()}
        if old.keys()-new.keys()!=retired or not 1<=len(incoming)<=15 or not incoming<=live.keys():
            raise ValueError('divider_exact_retirement_and_track_only_additions_required')
        rows=[live[u] for u in incoming];signature=_process(old[retired_track_uuids[0]])
        ground_ids={force._uid(z) for z in parent.Zones() if z.GetNetname()=='GND' and not z.GetIsRuleArea()}
        r['opaque_source_preservation']=_opaque_preservation(paths[0],paths[1],retired,ground_ids)
        if any(_process(nodes[u])!=signature for nodes,ids in ((old,retired),(new,incoming)) for u in ids):
            raise ValueError('divider_exact_source_width_face_net_lock_and_all_process_fields_required')
        if any(t.GetClass()!='PCB_TRACK' or t.GetParentGroup() or t.IsLocked() or t.HasSolderMask() for t in rows):
            raise ValueError('divider_unchanged_ungrouped_surface_track_process_required')
        if [list(p) for p in span._chain(rows)]!=plan['replacement_points_nm']:
            raise ValueError('divider_saved_path_differs_from_requested_geometry')
        r['contact_kernels']=_contact_kernels(parent,child,oldtracks,rows,retired,plan['source_layer'],deadline)
        with tempfile.TemporaryDirectory(prefix='cec-source-divider-ground-') as tmp:
            projected=force._copy_family(paths[0],Path(tmp)/'source-minus-span')
            basis=pcbnew.LoadBoard(str(projected));discard_items(basis,[t for t in basis.GetTracks() if force._uid(t) in retired])
            cut=partitions.compare(parent,basis,retired_uuids=retired,timeout_s=_remaining(deadline))
            if not cut.get('available') or not cut.get('preserved'):
                raise ValueError('divider_source_cut_not_already_native_plane_redundant')
            r['source_cut_partition_preservation']=dict(preserved=True,source_component_count=cut['source_component_count'])
            gap=max(int(basis.GetDesignSettings().m_MinClearance),int(cells._netclass(basis,'GND')['clearance']));cache={}
            for t in rows:
                _tick(deadline)
                if (not fr._edge_leg_clear(basis,t.GetStart(),t.GetEnd(),(t.GetWidth()+1)//2)
                        or not fr._tap_foreign_clear(basis,t.GetStart(),t.GetEnd(),t.GetWidth(),t.GetLayer(),gap,
                            {t.GetNetCode()},foreign_cache=cache)):
                    raise ValueError('divider_native_foreign_power_collector_or_edge_guard')
            r['literal_source_cut_projection']=literal.write_native_projection(paths[0],projected,retired,basis)
            exact=additive.receive(projected,paths[1],board_hint=board_hint,timeout_s=_remaining(deadline))
            r['independent_additive_receiving']=exact
            if not exact.get('ok') or not exact.get('complete'):
                raise ValueError('divider_strict_saved_source_minus_span_additions_and_ground_refill_refused')
        paired=partitions.compare(parent,child,retired_uuids=retired,timeout_s=_remaining(deadline))
        if not paired.get('available') or not paired.get('preserved'):
            raise ValueError('divider_source_retained_native_partition_lost')
        r['every_source_native_partition_preserved']=True
        entry=live.get(owner['source_entry_via_uuid'])
        if entry is None or shortcut._reference_contacts(child,entry)!=owner['source_reference_contacts']:
            raise ValueError('divider_existing_entry_lost_saved_ground_reference_contact')
        r['same_source_entry_contacts_to_each_saved_ground_reference_preserved']=True
        preserved=returns.receive(parent,child,timeout_s=_remaining(deadline));r['all_source_known_returns']=preserved
        if not preserved.get('ok') or not preserved.get('complete'):
            raise ValueError('divider_source_known_ground_return_worsened')
        craft=[quality.analyze_board(b) for b in (parent,child)]
        if any(craft[1][k]>craft[0][k] for k in ('issue_count','non_octilinear_count')):
            raise ValueError('divider_whole_native_craft_regression')
        incomingcraft=quality.analyze_board(child,track_uuid_scope=incoming)
        if incomingcraft['issue_count'] or incomingcraft['non_octilinear_count']:
            raise ValueError('divider_incoming_native_craft_fault')
        r['craft']=dict(source_issues=craft[0]['issue_count'],candidate_issues=craft[1]['issue_count'],incoming_issues=0)
        reports=[field.field_coupling_summary(str(p),board=b,board_hint=board_hint,
            _work=field._ProposalWork(deadline,16384,1000000,1000000,16384)) for p,b in zip(paths,(parent,child))]
        newblockers=field.blocker_keys(reports[1])-field.blocker_keys(reports[0])
        r['native_field_delta']=dict(no_new_blockers=not newblockers,source_blocking_count=reports[0]['blocking_count'],
            candidate_blocking_count=reports[1]['blocking_count'])
        if newblockers:raise ValueError('divider_new_native_field_blocker')
        _tick(deadline)
        if (epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]
                or owner['source_files_sha256']!={p:force._hash(Path(p)) for p in owner['source_files_sha256']}
                or force._hash(Path(owner['fresh_export']['exporter']).resolve())!=owner['fresh_export']['exporter_sha256']):
            raise ValueError('divider_source_candidate_hierarchy_or_code_changed')
        r.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[1]),
            code_identity=epoch,source_candidate_hierarchy_and_code_unchanged=True,
            retired_track_uuids=sorted(retired),added_native_uuids=sorted(incoming),modified_nets=['GND'],
            no_new_holes_or_part_pose_group_rule_or_power_copper_changes=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,AttributeError,subprocess.SubprocessError) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
