"""Exact redundant-tail cuts for a freshly source-proved moved RC shunt.

This is not ordinary-net reclassification or a critical-net waiver. Native
leaf discovery supplies hints only; saved cuts owe whole surviving partitions,
literal source replay, current and Ground-return preservation. The ORIGINAL
macro's complete receiving and native/field/intake admission remain due.
"""
import math
import time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_control_shunt_placement as shunt
import cec_ordinary_tail_discovery as tails
import cec_ordinary_route_receiving as ordinary
import cec_native_macro_tail_cleanup as hints
import cec_source_literal_retirement as literal
import cec_source_literal_additions as source_literal
import cec_source_retaining_ses_import as raw
import cec_ground_return_preservation as returns
import cec_field_coupling as field
from cec_native_items import discard_items


def _require(ok,reason):
    if not ok:raise ValueError(reason)


def _lease(timeout_s,board_hint):
    _require(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10
        and type(board_hint)is str and bool(board_hint),'bounded_typed_control_tail_context_required')
    return time.monotonic()+timeout_s


def _remaining(deadline):
    left=deadline-time.monotonic()
    _require(left>0,'source_control_tail_deadline')
    return min(10.,left)


def _singleton_cycle(board,prefix,uid,positive,width,deadline):
    """Hint only: retained contacts may join through real other-face copper."""
    _remaining(deadline)
    tracks={force._uid(t):t for t in board.GetTracks()};item=tracks.get(uid)
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    _require(item is not None and item.GetClass()=='PCB_TRACK'and item.GetNetname()in positive
        and 0<item.GetWidth()<=width and not item.IsLocked()and uid not in grouped
        and item.GetParentGroup()is None,'source_control_cycle_track_not_exactly_typed_free_copper')
    face=item.GetLayer();net=item.GetNetname()
    pads=[p for fp in board.GetFootprints()for p in fp.Pads()]
    material=[*tracks.values(),*pads]
    _require(len(material)<=6144,'source_control_cycle_native_inventory_bound')
    contacts=[]
    for other in material:
        _remaining(deadline)
        if(force._uid(other)!=uid and other.GetNetname()==net and other.IsOnLayer(face)
            and item.GetEffectiveShape(face).Collide(other.GetEffectiveShape(face),0)):
            contacts.append(force._uid(other))
    _require(len(contacts)>=2,'source_control_cycle_needs_multiple_retained_native_contacts')
    contact_items={force._uid(i):i for i in material if force._uid(i)in contacts}
    isolated=[]
    for end in(item.GetStart(),item.GetEnd()):
        point=pcbnew.SHAPE_CIRCLE(end,0)
        if not any(i.GetEffectiveShape(face).Collide(point,0)for i in contact_items.values()):isolated.append(list(end))
    _require(bool(isolated),'source_control_cycle_requires_actual_dangling_centerline_endpoint')
    probe=pcbnew.LoadBoard(str(prefix));live={force._uid(t):t for t in probe.GetTracks()}
    _require(uid in live,'source_control_cycle_saved_track_missing')
    discard_items(probe,[live[uid]])
    before=ordinary._partition(board,deadline,retired_uuids={uid});retained=set().union(*before)
    after=ordinary._partition(probe,deadline,retained_keys=retained)
    _require({frozenset(p)for p in before}=={frozenset(p)for p in after},
        'source_control_cycle_would_change_surviving_native_partition')
    # A separate actual net-only native graph independently checks the
    # precise touching conductors/lands, including through-barrel layer joins.
    conn=pcbnew.CONNECTIVITY_DATA();actual={}
    for other in[*probe.GetTracks(),*(p for fp in probe.GetFootprints()for p in fp.Pads()),
            *(z for z in probe.Zones()if not z.GetIsRuleArea())]:
        _remaining(deadline)
        if other.GetNetname()!=net:continue
        _require(conn.Add(other),'source_control_cycle_native_contact_graph_refused')
        actual[force._uid(other)]=other
    _require(set(contacts)<=actual.keys(),'source_control_cycle_retained_contact_missing')
    reached={contacts[0]}|{force._uid(i)for i in conn.GetConnectedItems(actual[contacts[0]])}
    _require(set(contacts)<=reached,'source_control_cycle_retained_contacts_not_rejoined')
    _remaining(deadline)
    return dict(track_uuid=uid,net=net,width_nm=item.GetWidth(),source_face=int(face),
        retained_direct_contact_uuids=sorted(contacts),
        source_dangling_endpoint_nm=isolated,
        full_stack_retained_contacts_joined=True,all_surviving_native_partitions_exact=True,
        routing_or_current_or_cut_admission=False)


def _compound_ports(board,prefix,tracks,positive,widths,deadline):
    """Close the native leaf topology before saving, never chase warnings."""
    tracks=set(tracks);ports=set();proofs=[]
    live={force._uid(t):t for t in board.GetTracks()}
    material=[*live.values(),*(p for fp in board.GetFootprints()for p in fp.Pads()),
        *(z for z in board.Zones()if not z.GetIsRuleArea())]
    _require(len(material)<=16384,'control_port_source_inventory_bound')
    layers=list(board.GetEnabledLayers().CuStack())
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    def contacts(via):
        rows=[]
        for other in material:
            _remaining(deadline)
            uid=force._uid(other)
            if uid==force._uid(via):continue
            faces=[]
            for face in layers:
                if not other.IsOnLayer(face):continue
                shape=via.GetEffectiveShape(face)
                if other.GetClass()=='ZONE':
                    if not other.HasFilledPolysForLayer(face):
                        _require(not other.Outline().Collide(shape,0),'control_port_source_zone_fill_unknown')
                        continue
                    hit=other.GetFilledPolysList(face).Collide(shape,0)
                else:hit=other.GetEffectiveShape(face).Collide(shape,0)
                if hit:faces.append(int(face))
            if faces:rows.append((uid,other,faces))
        return rows
    # Each successful iteration consumes a NEW actual source barrel. Five
    # iterations only detect exhaustion; the fifth is never constructed.
    for _ in range(5):
        selected=None
        for uid,via in sorted(live.items()):
            _remaining(deadline)
            if uid in ports or via.GetClass()!='PCB_VIA' or via.GetNetname()not in positive:continue
            actual=contacts(via)
            if not any(u in tracks for u,_,_ in actual):continue
            remaining=[r for r in actual if r[0]not in tracks]
            faces={l for _,_,ls in remaining for l in ls}
            if len(faces)>1:continue # Still an actual retained multilayer port.
            _require(len(ports)<4,'control_port_complete_scope_exceeds_four_barrels')
            _require(uid not in grouped and not via.IsLocked()and via.GetParentGroup()is None,
                'control_port_locked_or_grouped_source_requires_separate_authority')
            _require(all(i.GetClass()=='PCB_TRACK'and i.GetNetname()==via.GetNetname()
                and u not in grouped and not i.IsLocked()and 0<i.GetWidth()<=widths[i.GetNetname()]
                for u,i,_ in actual),'control_port_has_pad_plane_foreign_or_protected_contact')
            if remaining:
                witness=ordinary._redundant_single_face_vias(board,{uid},retired_tracks=tracks,
                    nets=positive,unlock=set(),deadline=deadline)
                probe=pcbnew.LoadBoard(str(prefix))
                discard_items(probe,[i for i in probe.GetTracks()if force._uid(i)in tracks|ports|{uid}])
                seeds=sorted(u for u,_,_ in remaining)
                walk=tails._discover_native_leaf_chains(probe,seeds,positive_nets=positive,
                    maximum_width_nm=max(widths.values()),timeout_s=_remaining(deadline))
                additions=set(walk['proposed_exact_track_uuids'])
                _require(walk['complete']and additions and all(r['proposed_track_uuids']for r in walk['attempts']),
                    'control_port_remaining_branch_not_complete_native_leaf')
            else:
                witness=ordinary._exclusive_retired_vias(board,{uid},retired_tracks=tracks,
                    nets=positive,unlock=set(),deadline=deadline)
                walk=None;additions=set()
            _require(len(tracks|additions)<=32,'control_port_complete_scope_exceeds_track_bound')
            for u in additions:
                i=live[u]
                _require(i.GetClass()=='PCB_TRACK'and i.GetNetname()in positive
                    and 0<i.GetWidth()<=widths[i.GetNetname()]and not i.IsLocked()
                    and u not in grouped and i.GetParentGroup()is None,'control_port_leaf_not_source_typed_free_track')
            selected=(uid,additions,witness,walk);break
        if selected is None:break
        uid,additions,witness,walk=selected;tracks.update(additions);ports.add(uid)
        proofs.append(dict(via_uuid=uid,original_port_geometry=witness,projected_native_leaf_discovery=walk))
    else:raise ValueError('control_port_finite_topology_bound_exhausted')
    exclusive=ordinary._exclusive_retired_vias(board,ports,retired_tracks=tracks,
        nets=positive,unlock=set(),deadline=deadline)
    return tracks,ports,dict(steps=proofs,whole_original_exclusive_port_ownership=exclusive,
        no_native_warning_chasing=True,maximum_tracks=32,maximum_vias=4)


def _scope(original,prefix,board_hint,warning_uuids,deadline):
    first=pcbnew.LoadBoard(str(original));board=pcbnew.LoadBoard(str(prefix))
    owners={force._uid(f):f for f in first.GetFootprints()};poses={}
    _require(set(owners)=={force._uid(f)for f in board.GetFootprints()},'control_tail_source_package_inventory_changed')
    for fp in board.GetFootprints():
        old=owners[force._uid(fp)]
        if(tuple(fp.GetPosition()),fp.GetOrientationDegrees(),fp.IsFlipped())!=(tuple(old.GetPosition()),old.GetOrientationDegrees(),old.IsFlipped()):
            poses[old.GetReference()]=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()]
    _require(0<len(poses)<=8,'actual_source_control_shunt_motion_required')
    selected=shunt.plan(first,poses,board_hint=board_hint,timeout_s=_remaining(deadline))
    _require(set(selected)==set(poses),'only_source_selected_control_shunts_may_move')
    live_selected=shunt.plan(board,poses,board_hint=board_hint,timeout_s=_remaining(deadline))
    # The native binding necessarily changes with the received macro prefix;
    # every typed source/part/network identity must independently rederive.
    stable=lambda rows:{ref:{k:v for k,v in item.items()if k!='source_native_binding'}for ref,item in rows.items()}
    _require(stable(live_selected)==stable(selected),'prefix_control_shunt_source_identity_changed')
    proposal=dict(poses=poses,selected_control_shunts=selected,board_hint=board_hint)
    requests=shunt.requests(first,board,proposal,timeout_s=_remaining(deadline))
    _require(len(requests)==len(selected),'complete_fresh_control_shunt_branch_requests_required')
    positive={v['net']for v in selected.values()}
    _require(positive and 'GND'not in positive,'positive_control_shunt_signal_only_required')
    authored=source_literal.incoming_copper_nets(raw.raw_text(prefix),warning_uuids)
    _require(all(net in positive for net in authored.values()),'literal_source_control_tail_net_required')
    widths={}
    for v in requests.values():
        _require(v['net']not in widths or widths[v['net']]==v['width_nm'],'unique_typed_control_net_width_required')
        widths[v['net']]=v['width_nm']
    width=max(widths.values())
    discovery=tails._discover_native_leaf_chains(board,warning_uuids,positive_nets=positive,
        maximum_width_nm=width,timeout_s=_remaining(deadline))
    retired=set(discovery['proposed_exact_track_uuids'])
    fallback=[]
    failed=[row['warning_uuid']for row in discovery['attempts']if not row['proposed_track_uuids']]
    if failed:
        _require(len(failed)<=8,'bounded_source_control_singleton_cycle_count_required')
        for uid in failed:
            row=next(r for r in discovery['attempts']if r['warning_uuid']==uid)
            _require(row.get('refusal')=='native_body_junction_or_multiple_protected_contacts',
                'source_control_leaf_refusal_is_not_a_redundant_cycle_candidate')
            fallback.append(_singleton_cycle(board,prefix,uid,positive,widths[authored[uid]],deadline));retired.add(uid)
    _require(discovery['complete']and retired and len(retired)<=32,'positive_source_control_shunt_leaf_required')
    live={force._uid(t):t for t in board.GetTracks()};groups={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    for uid in retired:
        item=live[uid]
        _require(item.GetClass()=='PCB_TRACK'and not item.IsLocked()and uid not in groups
            and item.GetParentGroup()is None and item.GetNetname()in positive
            and 0<item.GetWidth()<=widths[item.GetNetname()],
            'unlocked_ungrouped_source_control_shunt_track_only_required')
    authored=source_literal.incoming_copper_nets(raw.raw_text(prefix),retired)
    _require(all(net in positive and net==live[u].GetNetname()for u,net in authored.items()),
        'literal_source_control_tail_net_changed_by_native_normalization')
    retired,ports,compound=_compound_ports(board,prefix,retired,positive,widths,deadline)
    authored=source_literal.incoming_copper_nets(raw.raw_text(prefix),retired|ports)
    _require(all(net in positive and net==live[u].GetNetname()for u,net in authored.items()),
        'literal_compound_control_port_net_changed_by_native_normalization')
    return board,retired,dict(selected_control_shunts=selected,source_requests=requests,
        source_native_leaf_chain_discovery=discovery,source_typed_singleton_cycle_hints=fallback,
        retired_via_uuids=sorted(ports),compound_source_native_port_closure=compound)


def receive(original_source,prefix,candidate,*,board_hint,warning_uuids,timeout_s=10.):
    """Independently rederive source intent and entire exact saved cut."""
    result=dict(schema=1,scope='source_control_shunt_redundant_tail_receiving',ok=False,complete=False,
        errors=[],release_authority=False,current_authority=False,
        admitted=False,original_macro_source_receiving_still_required=True,
        whole_original_current_debt_field_native_intake_receiving_still_required=True,
        geometry_lease_s=timeout_s,separate_ground_return_lease_s=10.)
    started=time.monotonic()
    try:
        deadline=_lease(timeout_s,board_hint)
        original,prefix,child=map(lambda p:Path(p).resolve(),(original_source,prefix,candidate))
        _require(len({original,prefix,child})==3,'distinct_control_tail_source_prefix_child_required')
        paths=(original,prefix,child);families=[force._family(p,board_hint)for p in paths];code=force._code_identity()
        parent,retired,proof=_scope(original,prefix,board_hint,warning_uuids,deadline)
        ports=set(proof['retired_via_uuids']);outgoing=retired|ports
        expected=literal.subtract(raw.raw_text(prefix),outgoing)
        _require(raw.raw_text(child)==expected,'exact_control_tail_literal_subtraction_required')
        _require(force._sidecars(prefix)==force._sidecars(child),'control_tail_sidecars_changed')
        board=pcbnew.LoadBoard(str(child));live={force._uid(t):t for t in parent.GetTracks()}
        result['boundary_restoration']=ordinary._boundaries(parent,board,[live[u]for u in retired],deadline,
            exclusive_retired_via_uuids=ports)
        before=ordinary._partition(parent,deadline,retired_uuids=outgoing)
        retained=set().union(*before);after=ordinary._partition(board,deadline,retained_keys=retained)
        _require(set().union(*after)==retained and all(any(p<=q for q in after)for p in before),
            'control_tail_prior_native_terminal_or_junction_partition_lost')
        # Independently materialize native subtraction as well as literal text.
        discard_items(parent,[live[u]for u in outgoing])
        _require(field._field_snapshot_inventory(parent)==field._field_snapshot_inventory(board),
            'control_tail_literal_differs_from_native_subtraction')
        _remaining(deadline)
        result['geometry_elapsed_s']=time.monotonic()-started
        result['ground_return_preservation']=returns.receive(pcbnew.LoadBoard(str(prefix)),board,timeout_s=10.)
        _require(result['ground_return_preservation']['ok']and result['ground_return_preservation']['complete'],
            'control_tail_known_ground_return_regressed')
        _require(code==force._code_identity()and families==[force._family(p,board_hint)for p in paths],
            'control_tail_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,retired_track_uuids=sorted(retired),retired_via_uuids=sorted(ports),source_proof=proof,
            all_prior_native_terminal_partitions_preserved=True,all_surviving_native_junctions_preserved=True,
            exact_source_minus_cut_replay=True,source_and_code_unchanged=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=time.monotonic()-started
    return result


def construct(original_source,prefix,outdir,*,board_hint,original_native,proposed_native,timeout_s=10.):
    result=dict(schema=1,scope='new_source_control_shunt_macro_tail_cleanup',ok=False,complete=False,
        changed=False,candidate=None,errors=[],release_authority=False,
        admitted=False,original_macro_source_receiving_still_required=True,
        whole_original_current_debt_field_native_intake_receiving_still_required=True,
        maximum_outer_wall_s=2*timeout_s+10.)
    started=time.monotonic()
    try:
        deadline=_lease(timeout_s,board_hint);original,prefix=map(lambda p:Path(p).resolve(),(original_source,prefix))
        outdir=Path(outdir)
        _require(original!=prefix and not outdir.exists(),'fresh_control_shunt_tail_prefix_required')
        families=[force._family(p,board_hint)for p in(original,prefix)];code=force._code_identity()
        warnings=hints.new_warning_ids(original_native,proposed_native);result['new_warning_uuids']=warnings
        if not warnings:result.update(ok=True,complete=True);return result
        _,retired,proof=_scope(original,prefix,board_hint,warnings,deadline)
        child=force._copy_family(prefix,outdir)
        raw.write_raw(child,literal.subtract(raw.raw_text(prefix),retired|set(proof['retired_via_uuids'])))
        _remaining(deadline)
        receiving=receive(original,prefix,child,board_hint=board_hint,warning_uuids=warnings,
            timeout_s=timeout_s)
        result['independent_saved_receiving']=receiving
        _require(receiving['ok']and receiving['complete'],'control_shunt_tail_saved_receiving_refused:'+str(receiving['errors']))
        _require(code==force._code_identity()and families==[force._family(p,board_hint)for p in(original,prefix)],
            'control_tail_original_prefix_or_code_changed')
        _require(time.monotonic()-started<2*timeout_s+10.,'control_tail_outer_wall_bound')
        result.update(ok=True,complete=True,changed=True,candidate=str(child),candidate_sha256=force._hash(child),
            retired_track_uuids=sorted(retired),retired_via_uuids=proof['retired_via_uuids'],source_proof=proof,source_and_code_unchanged=True,
            independent_native_field_intake_and_original_macro_receiving_still_required=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=time.monotonic()-started
    return result
