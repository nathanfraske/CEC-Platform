"""Saved rigid-cell input repairs without laundering another input's debt.

The public receiver owns its macro replay and both raw native sense replays.
Only actual moved manufacturer input PAD position metadata may be compared in
the Source frame. Default leaf rebinding requires two positive whole-net cuts
and the retained boundary. Explicit whole-leaf rebinding additionally derives
the complete owned replacement, positive leg cuts, identical fixed native
components and exact pickup geometry; unrelated failures remain failures.
No cut geometry, shunt/current terminal, guard, unknown result
or raw native report is moved or fabricated. A newly
connected leg needs absolute AFTER proof. Other inputs retain their actual
failure/unknown state, including a pre-existing bad departure on a shared
shunt. This is scoped preservation/repair, never whole-net Kelvin approval.
"""
import copy
from pathlib import Path
import time

import pcbnew
import cec_complete_macro_cell as macro
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense


_CATEGORIES=('same_net_connectivity','inner_departure','shunt_pad_omitted',
             'clipped_isolation')
_GEOMETRIC_CUT_FIELDS={'elapsed_s','vertices_examined','contacts_examined',
    'exact_linear_refinements','baseline_geometry','upper','lower'}


def _key(row):
    return row['input_ref'],row['leg'],row['net']


def _rows(report,category):
    rows=report[category]['details'];indexed={_key(r):r for r in rows}
    # A filtered leg has multiple same-net demands, so this helper is used
    # only for categories with exactly one physical row per leg.
    if len(indexed)!=len(rows):raise ValueError('unique_macro_input_leg_required')
    return indexed


def _moved_input_bindings(parent,child,before,after,moved_refs):
    """Only lineage-resolved manufacturer IC input pads, never shunt lands."""
    originals={f.GetReference():f for f in parent.GetFootprints()}
    actuals={f.GetReference():f for f in child.GetFootprints()}
    old={r['ref']:r for r in before['lineage']['details']}
    new={r['ref']:r for r in after['lineage']['details']}
    if old!=new:raise ValueError('macro_typed_input_lineage_changed')
    bindings={}
    for ref in sorted(set(moved_refs)&old.keys()):
        declared=old[ref]
        if declared.get('ok') is not True or len(declared['pins'])!=2:
            raise ValueError('resolved_manufacturer_input_pins_required')
        first,last=originals[ref],actuals[ref]
        if (force._uid(first)!=force._uid(last) or first.GetValue()!=last.GetValue()
                or first.GetFPIDAsString()!=last.GetFPIDAsString()):
            raise ValueError('rigid_macro_input_owner_identity_changed')
        for pin in declared['pins']:
            a=[p for p in first.Pads() if p.GetNumber()==pin]
            b=[p for p in last.Pads() if p.GetNumber()==pin]
            if len(a)!=1 or len(b)!=1:raise ValueError('unique_manufacturer_input_pad_required')
            a,b=a[0],b[0]
            if (force._uid(a)!=force._uid(b) or a.GetNetname()!=b.GetNetname()
                    or tuple(a.GetSize())!=tuple(b.GetSize())
                    or a.GetAttribute()!=b.GetAttribute() or a.GetShape()!=b.GetShape()
                    or tuple(a.GetLayerSet().CuStack())!=tuple(b.GetLayerSet().CuStack())):
                raise ValueError('rigid_macro_input_land_contract_changed')
            if force._point(a)==force._point(b):continue
            bindings[force._uid(a)]=dict(ref=ref,pad=pin,uuid=force._uid(a),
                footprint_uuid=force._uid(first),net=a.GetNetname(),
                before=force._point(a),after=force._point(b))
    if len(bindings)>32:raise ValueError('finite_moved_manufacturer_input_pad_scope_required')
    return bindings


def _position_comparison_copy(before,after,bindings):
    """Explicit terminal metadata paths; never recursively rewrite witnesses."""
    result=copy.deepcopy(after);seen=set();visited=set()
    for category in _CATEGORIES:
        fields=('start_pad','end_pad') if category=='same_net_connectivity' else ('sense_terminal',)
        for row in result[category]['details']:
            terminals=[row.get(k) for k in fields]
            if category=='clipped_isolation':terminals.append(row.get('native',{}).get('sense'))
            for terminal in terminals:
                if type(terminal) is not dict:continue
                binding=bindings.get(terminal.get('uuid'))
                if binding is None:continue
                # A live audit can share one terminal dictionary between its
                # wrapper and native proof; JSON replay has distinct copies.
                # Inspect each actual object exactly once in either form.
                if id(terminal) in visited:continue
                if (any(terminal.get(k)!=binding[k] for k in
                        ('ref','pad','uuid','footprint_uuid','net'))
                        or terminal.get('position_nm')!=binding['after']):
                    raise ValueError('macro_report_input_pad_is_not_actual_saved_land')
                terminal['position_nm']=copy.deepcopy(binding['before']);seen.add(binding['uuid'])
                visited.add(id(terminal))
    if seen!=bindings.keys():raise ValueError('moved_input_pad_missing_from_raw_native_inventory')
    # The raw Source is checked too; a position hint cannot authorize an
    # unknown old owner or a non-input physical terminal.
    for row in before['same_net_connectivity']['details']:
        for field_name in ('start_pad','end_pad'):
            terminal=row.get(field_name,{})
            binding=bindings.get(terminal.get('uuid'))
            if binding and (terminal.get('position_nm')!=binding['before']
                    or any(terminal.get(k)!=binding[k] for k in
                        ('ref','pad','uuid','footprint_uuid','net'))):
                raise ValueError('macro_source_input_pad_is_not_actual_saved_land')
    return result


def _new_input_legs(before,after,incoming):
    """Actual false-to-true native demands with new saved path material."""
    def demands(report):
        rows=report['same_net_connectivity']['details']
        def key(r):return _key(r)+(repr((r['start'],r['end'])),)
        found={key(r):r for r in rows}
        if len(found)!=len(rows):raise ValueError('unique_native_macro_demand_inventory_required')
        return found
    first,last=demands(before),demands(after)
    if first.keys()!=last.keys():raise ValueError('macro_native_input_demands_changed')
    selected={k[:3] for k in first if first[k].get('ok') is not True and last[k].get('ok') is True}
    if len(selected)>16:raise ValueError('finite_newly_completed_macro_input_scope_required')
    departures=_rows(after,'inner_departure')
    for key in selected:
        row=departures[key];terminal=row['sense_terminal']['uuid']
        paths=[d.get('input_contact_paths',{}).get(terminal,[]) for d in row['native']['departures']]
        actual={u for path in paths for u in path}
        if not actual&incoming:raise ValueError('newly_connected_input_has_no_actual_incoming_path')
        admission=sense.admit_changed_net(after,after,key[2],input_legs=[key[:2]])
        if not admission['ok'] or not admission['applicable'] or admission['checked']!=1:
            raise ValueError('absolute_raw_after_input_admission_refused:'+repr(key))
    return sorted(selected)


def _refresh_failing_peer_observations(before,after,selected,incoming):
    """An extra independent tap is not a repair of an existing bad tap.

    Retain every old exit, heading, issue, reachability, result and contract.
    Both peer geometric cuts must freshly PASS, independently of its still
    FAILED departure. Only extra non-reaching observations of an absolutely
    proved new input departure are compared in the old observation frame.
    """
    result=copy.deepcopy(after);observations=[]
    old=_rows(before,'inner_departure');actual=_rows(after,'inner_departure')
    first_cuts=_rows(before,'clipped_isolation');last_cuts=_rows(after,'clipped_isolation')
    if old.keys()!=actual.keys():raise ValueError('peer_physical_input_inventory_changed')
    proved={}
    for key in selected:
        row=actual[key]
        for departure in row['native']['departures']:
            proved[(row['source_pad']['uuid'],departure['uuid'])]=departure
    for index,row in enumerate(result['inner_departure']['details']):
        key=_key(row);prior=old[key]
        if key in selected or key[2] not in {k[2] for k in selected}:continue
        a,b=prior.get('native'),row.get('native')
        if a==b or not a or not b:continue
        # The older public comparator deliberately keeps its unchanged
        # still-open-peer contract. This separate receiver owns ONLY an
        # already connected but still failing peer with retained bad exits.
        if (prior.get('ok') is not False or row.get('ok') is not False
                or prior.get('status')!='failed' or row.get('status')!='failed'
                or not a.get('departures') or not a.get('issues')
                or a.get('unreachable_input_pad_uuids') or b.get('unreachable_input_pad_uuids')):
            continue
        mutable={'contact_count','non_sense_departures'}
        if ({k:v for k,v in prior.items() if k!='native'}!={k:v for k,v in row.items() if k!='native'}
                or {k:v for k,v in a.items() if k not in mutable}!={k:v for k,v in b.items() if k not in mutable}):
            raise ValueError('preexisting_failed_peer_exit_issue_or_policy_changed')
        def by_uuid(rows):
            found={r['uuid']:r for r in rows}
            if len(found)!=len(rows):raise ValueError('unique_native_peer_departure_observations_required')
            return found
        first,last=by_uuid(a.get('non_sense_departures',())),by_uuid(b.get('non_sense_departures',()))
        if not first.keys()<=last.keys() or any(last[u]!=v for u,v in first.items()):
            raise ValueError('old_peer_observation_changed')
        extra=last.keys()-first.keys()
        if not extra or not extra<=incoming or b['contact_count']-a['contact_count']!=len(extra):
            raise ValueError('exact_added_peer_observation_inventory_required')
        witness_fields={'reachable_input_pad_uuids','input_contact_paths'}
        for uid in extra:
            witness=proved.get((row['source_pad']['uuid'],uid))
            if (witness is None or last[uid].get('reachable_input_pad_uuids')
                    or last[uid].get('input_contact_paths')
                    or {k:v for k,v in witness.items() if k not in witness_fields}
                        !={k:v for k,v in last[uid].items() if k not in witness_fields}):
                raise ValueError('peer_observation_not_exact_proved_nonreaching_new_tap')
        x,y=first_cuts[key],last_cuts[key]
        for cut in (x,y):
            native=cut['native']
            if (cut.get('ok') is not True or cut.get('status')!='verified'
                    or native.get('ok') is not True or native.get('complete') is not True
                    or native.get('reason')!='isolated_in_upper_copper_model'
                    or native.get('tracks_clipped') is not True
                    or native.get('exact_linear_identity_verified') is not True
                    or native.get('physical_bypass_proved') is not False):
                raise ValueError('two_positive_raw_peer_geometric_cuts_required')
        if ({k:v for k,v in x.items() if k!='native'}!={k:v for k,v in y.items() if k!='native'}
                or {k:v for k,v in x['native'].items() if k not in _GEOMETRIC_CUT_FIELDS}
                    !={k:v for k,v in y['native'].items() if k not in _GEOMETRIC_CUT_FIELDS}):
            raise ValueError('peer_cut_guard_authority_or_model_changed')
        result['inner_departure']['details'][index]=copy.deepcopy(prior)
        for cut in result['clipped_isolation']['details']:
            if _key(cut)==key:cut['native']=copy.deepcopy(x['native'])
        observations.append(dict(input_ref=key[0],leg=key[1],net=key[2],
            source_pad_uuid=row['source_pad']['uuid'],new_nonreaching_tap_uuids=sorted(extra),
            raw_before_ok=prior['ok'],raw_after_ok=row['ok'],
            existing_departure_failure_retained=True,peer_qualified=False,release_authority=False))
    return result,observations


def _rebind_owned_moved_leaf_witnesses(parent,child,before,after,proof,bindings,*,excluded_pad_uuids=()):
    """A saved rigid macro owns its exact reconstructed leaf, not all paths.

    Require two positive absolute whole-net admissions, re-derive both native
    leaves, keep the actual shunt/junction prefix and physical boundary exact,
    and refresh ONLY the changed received leaf's UUID suffix in a comparison
    copy. Unknown/failing cuts and all other observations remain strict.
    """
    import cec_measurement_leaf as leaf
    packet=proof.get('source_macro_packet',{});plan=packet.get('source_plan',{})
    leaves=plan.get('measurement_leaves',())
    if not leaves or not bindings:return copy.deepcopy(after),[]
    if (proof.get('scope')!='independent_saved_source_owned_macro_cell'
            or proof.get('all_original_surviving_native_partitions_preserved')is not True
            or proof.get('all_original_physical_ground_returns',{}).get('ok')is not True
            or any(proof.get('independent_exact_source_cut_transform_and_additions',{}).get(k)is not True
                for k in('ok','complete'))):
        raise ValueError('independent_exact_rigid_macro_required_for_leaf_witness')
    if type(leaves)is not list or len(leaves)>32:
        raise ValueError('bounded_Source_macro_measurement_leaf_inventory_required')
    deadline=time.monotonic()+10.;adjusted=copy.deepcopy(after);observations=[];seen=set()
    retired=set(proof['retired_track_uuids']);incoming=set(proof['added_native_uuids'])
    old_rows=_rows(before,'inner_departure');new_rows=_rows(after,'inner_departure')
    def fixed_boundaries(board,identities):
        found={}
        for item in [*board.GetTracks(),*[p for f in board.GetFootprints()for p in f.Pads()]]:
            uid=force._uid(item)
            if uid not in identities:continue
            if uid in found:raise ValueError('unique_macro_leaf_boundary_identity_required')
            state=(item.GetClass(),item.GetNetname(),bool(item.IsLocked()))
            if item.GetClass()=='PAD':
                fp=item.GetParentFootprint()
                state+=(force._uid(fp),fp.GetValue(),fp.GetFPIDAsString(),item.GetNumber(),
                    tuple(item.GetPosition()),tuple(item.GetSize()),tuple(item.GetDrillSize()),
                    item.GetOrientationDegrees(),int(item.GetShape()),int(item.GetAttribute()),
                    tuple(item.GetLayerSet().CuStack()))
            elif item.GetClass()=='PCB_TRACK':
                state+=(tuple(item.GetStart()),tuple(item.GetEnd()),item.GetWidth(),int(item.GetLayer()))
            elif item.GetClass()=='PCB_VIA':
                state+=(tuple(item.GetPosition()),item.GetWidth(item.TopLayer()),item.GetDrillValue(),
                    int(item.GetViaType()),int(item.TopLayer()),int(item.BottomLayer()))
            else:raise ValueError('unsupported_macro_leaf_fixed_boundary_material')
            state+=(force._uid(item.GetParentGroup())if item.GetParentGroup()else None,)
            found[uid]=state
        if set(found)!=set(identities):raise ValueError('actual_macro_leaf_fixed_boundaries_required')
        return found
    for claimed in leaves:
        pad=claimed.get('pad_uuid');binding=bindings.get(pad)
        if pad in excluded_pad_uuids:continue
        if binding is None:continue
        if pad in seen:raise ValueError('repeated_Source_macro_measurement_leaf')
        seen.add(pad)
        keys=[key for key,row in old_rows.items()if row.get('sense_terminal',{}).get('uuid')==pad]
        if len(keys)!=1 or keys[0]not in new_rows:
            raise ValueError('exact_moved_macro_input_leaf_inventory_required')
        key=keys[0];a,b=old_rows[key],new_rows[key]
        # A still-open or pre-existing bad input is not eligible for witness
        # refresh. In particular, no inherited unknown acquires this scope.
        if a.get('ok')is not True or b.get('ok')is not True:continue
        net=claimed['net']
        first_cut=sense.admit_changed_net(before,before,net)
        last_cut=sense.admit_changed_net(after,after,net)
        if (not all(q.get('ok')is True and q.get('applicable')is True
                and type(q.get('checked'))is int and q['checked']>0
                and q['checked']==len(q.get('expected_legs',()))for q in(first_cut,last_cut))
                or first_cut['expected_legs']!=last_cut['expected_legs']):
            continue
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('macro_measurement_leaf_witness_deadline')
        first=leaf.plan(parent,pad,timeout_s=min(10.,remaining))
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('macro_measurement_leaf_witness_deadline')
        last=leaf.plan(child,pad,timeout_s=min(10.,remaining))
        if (first!=claimed or first['owner']!=binding['ref']or first['net']!=binding['net']
                or first['points_nm'][0]!=binding['before']or last['points_nm'][0]!=binding['after']
                or first['points_nm'][-1]!=last['points_nm'][-1]
                or not set(first['track_uuids'])<=retired
                or not set(last['track_uuids'])<=incoming|set(first['track_uuids'])):
            raise ValueError('actual_received_macro_leaf_cut_additions_or_ports_changed')
        variable={'track_uuids','points_nm','source_length_mm','source_boundary_entry_nm','source_native_binding'}
        if ({k:v for k,v in first.items()if k not in variable}
                !={k:v for k,v in last.items()if k not in variable}):
            raise ValueError('macro_measurement_leaf_owner_boundary_or_dimension_changed')
        if fixed_boundaries(parent,first['boundary_uuids'])!=fixed_boundaries(child,last['boundary_uuids']):
            raise ValueError('macro_measurement_leaf_retained_boundary_material_changed')
        common=[]
        for left,right in zip(reversed(first['track_uuids']),reversed(last['track_uuids'])):
            if left!=right:break
            common.append(left)
        witnesses=[]
        for row,proposal in((a,first),(b,last)):
            paths=[d['input_contact_paths'][pad]for d in row['native']['departures']
                if pad in d.get('input_contact_paths',{})]
            suffix=list(reversed(proposal['track_uuids']))[len(common):]+[pad]
            if (len(paths)!=1 or len(paths[0])>64 or len(paths[0])<=len(suffix)
                    or paths[0][-len(suffix):]!=suffix):
                raise ValueError('exact_received_macro_leaf_witness_suffix_required')
            witnesses.append((paths[0],paths[0][:-len(suffix)]))
        if witnesses[0][1]!=witnesses[1][1]:
            raise ValueError('macro_measurement_retained_departure_or_junction_changed')
        for row in adjusted['inner_departure']['details']:
            if _key(row)!=key:continue
            for departure in row['native']['departures']:
                if pad in departure.get('input_contact_paths',{}):
                    departure['input_contact_paths'][pad]=copy.deepcopy(witnesses[0][0])
        observations.append(dict(pad_uuid=pad,net=net,retired_leaf_uuids=first['track_uuids'],
            received_leaf_uuids=last['track_uuids'],retained_witness_prefix=witnesses[0][1],
            before=first_cut,after=last_cut,raw_native_reports_unchanged=True,
            basis='exact_received_rigid_macro_leaf_and_two_absolute_whole_net_cut_passes',
            inherited_unknown_not_qualified=True,full_kelvin_qualification=False,release_authority=False))
        if time.monotonic()>=deadline:raise ValueError('macro_measurement_leaf_witness_deadline')
    return adjusted,observations


def _compare_received(parent,child,before,after,proof,modified_nets,transforms,*,
                      whole_leaf_pad_uuids=(),deadline=None):
    """Internal comparison; the public entrypoint supplies all raw proofs."""
    if (proof.get('ok') is not True or proof.get('complete') is not True
            or proof.get('source_candidate_families_and_code_unchanged') is not True):
        raise ValueError('independently_received_saved_rigid_macro_required')
    incoming=set(proof['added_native_uuids'])
    bindings=_moved_input_bindings(parent,child,before,after,proof['moved_refs'])
    selected=_new_input_legs(before,after,incoming)
    # Default remains the legacy strict Source leaf/whole-net comparison.
    adjusted=after;whole_leaf_observations=[];processed=()
    if whole_leaf_pad_uuids:
        import cec_source_whole_leaf_comparison as whole
        processed=whole.requests(whole_leaf_pad_uuids)
        adjusted,whole_leaf_observations=whole.reconcile_received_whole_leaves(
            parent,child,before,after,proof,bindings,processed,
            deadline=time.monotonic()+10. if deadline is None else deadline)
    adjusted,leaf_witnesses=_rebind_owned_moved_leaf_witnesses(
        parent,child,before,adjusted,proof,bindings,excluded_pad_uuids=processed)
    adjusted=_position_comparison_copy(before,adjusted,bindings)
    adjusted,peers=_refresh_failing_peer_observations(before,adjusted,selected,incoming)
    if selected:
        comparison=sense.compare_repaired_preservation(before,adjusted,
            repair_nets=sorted({k[2] for k in selected}),modified_nets=modified_nets,
            native_copper_transforms=transforms,repair_legs=selected)
    else:
        comparison=sense.compare_contour_preservation(before,adjusted,
            modified_nets=modified_nets,native_copper_transforms=transforms)
    return dict(comparison,derived_completed_input_legs=selected,
        moved_input_position_metadata=[dict(b,comparison_only=True,qualification_granted=False)
            for b in bindings.values()],failed_peer_observations=peers,
        received_moved_leaf_witnesses=leaf_witnesses,
        **(dict(received_whole_leaf_observations=whole_leaf_observations)if processed else {}),
        raw_native_evidence_retained=True,full_kelvin_qualification=False,release_authority=False)


def receive(source,candidate,*,board_hint,macro_options=None,timeout_s=10.,whole_leaf_pad_uuids=()):
    """Finite macro + two native evidence replays + exact comparison stages."""
    started=time.monotonic();result=dict(ok=False,complete=False,comparison_complete=False,
        same_evidence=False,errors=[],release_authority=False,full_kelvin_qualification=False,
        scope='saved_rigid_macro_input_repair_and_strict_unaffected_preservation')
    try:
        if type(timeout_s) not in (int,float) or not 0<timeout_s<=10:
            raise ValueError('bounded_macro_evidence_constituents_required')
        import cec_source_whole_leaf_comparison as whole
        whole_leaf_pad_uuids=whole.requests(whole_leaf_pad_uuids)
        options=dict(macro_options or {})
        if options.pop('board_hint',board_hint)!=board_hint:
            raise ValueError('unchanged_macro_evidence_board_hint_required')
        if 'timeout_s' in options:raise ValueError('macro_evidence_constituent_lease_not_overridable')
        paths=[Path(p).resolve(strict=True) for p in (source,candidate)]
        families=[force._family(p,board_hint) for p in paths];code=force._code_identity()
        proof=macro.receive(*paths,board_hint=board_hint,timeout_s=timeout_s,**options)
        result['saved_macro_receiving']=proof
        if not proof.get('ok') or not proof.get('complete'):
            raise ValueError('independent_saved_macro_replay_refused')
        raw=[sense.replay(p,board_hint=board_hint,timeout_s=timeout_s) for p in paths]
        result['raw_native_evidence']=raw
        for p,family,report in zip(paths,families,raw):
            if (report.get('source')!=str(p) or report.get('board_hint')!=board_hint
                    or report.get('complete') is not True or report.get('identity_stable') is not True
                    or report.get('source_family_before')!=family or report.get('source_family_after')!=family
                    or report.get('code_before')!=code or report.get('code_after')!=code):
                raise ValueError('fresh_same_epoch_raw_macro_evidence_required')
        deadline=time.monotonic()+timeout_s
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        old,new=map(field._field_snapshot_inventory,(parent,child));nets=set()
        for key in old.keys()|new.keys():
            if old.get(key)==new.get(key):continue
            for inventory in (old,new):
                if key in inventory:nets.add(inventory[key][1 if key[0]=='track' else 0])
        if not nets or len(nets)>64 or any(type(n) is not str or not n for n in nets):
            raise ValueError('bounded_positive_actual_macro_material_net_scope_required')
        transforms=sense.native_copper_transform_inventory(parent,child,modified_nets=sorted(nets))
        comparison=_compare_received(parent,child,*raw,proof,sorted(nets),transforms,
            whole_leaf_pad_uuids=whole_leaf_pad_uuids,deadline=deadline)
        result['comparison']=comparison
        if (time.monotonic()>=deadline or families!=[force._family(p,board_hint) for p in paths]
                or code!=force._code_identity()):
            raise ValueError('macro_evidence_comparison_epoch_or_lease_changed')
        result.update(comparison_complete=comparison['comparison_complete'],
            same_evidence=comparison['same_evidence'],
            complete=comparison['comparison_complete'],ok=comparison['same_evidence'] is True,
            source_candidate_families_and_code_unchanged=True,
            actual_modified_nets=sorted(nets),native_copper_transforms=transforms)
    except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=time.monotonic()-started
    return result
