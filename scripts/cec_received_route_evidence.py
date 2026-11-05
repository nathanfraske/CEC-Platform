"""Requalify additive-route contact evidence from independently replayed files.

The native source-plus-delta receiver, not a worker manifest, determines exact
added UUIDs and their net/kind counts. Changed positive copper cuts require
absolute readmission before AND after. Unknown/failing cuts remain strict.
No fabrication/current/whole-board/release authority is granted here.
"""
from collections import defaultdict
from pathlib import Path

import pcbnew
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_additive_route_receiving as receiving
import cec_current_path_receiving as current_receiving
import cec_current_topology as topology
import cec_fr as fr


def _rebind_received_package_positions(old,child,after,proof):
    """Comparison metadata only, after exact native manufacturer replay.

    Neither a pose allowlist nor a worker's chosen coordinates is accepted.
    Independently rederive the old catalog pattern and the actual new lands;
    replace ONLY matching physical-pad position metadata in a comparison copy.
    Raw saved geometry, raw cut outcomes/guards and qualified/unknown counts
    remain visible. The pattern receiver also requires exactly unchanged
    conductor partitions, so this cannot disguise an acquired/lost contact.
    """
    import copy
    import cec_manufacturer_land_pattern as patterns
    proposals=proof.get('source_manufacturer_land_pattern_replays',())
    if not proposals:return after,[]
    if (proof.get('ok') is not True or proof.get('complete') is not True
            or proof.get('strict_manufacturer_land_patterns_received') is not True
            or len(proposals)!=1):
        raise ValueError('exact_received_manufacturer_package_phase_required')
    proposal=proposals[0]
    if patterns.plan(old,proposal['footprint_uuids'])!=proposal:
        raise ValueError('manufacturer_metadata_rebinding_source_differs')
    projected=pcbnew.LoadBoard(old.GetFileName())
    patterns.materialize(projected,proposal)
    originals={force._uid(fp):fp for fp in old.GetFootprints()}
    expected={force._uid(fp):fp for fp in projected.GetFootprints()}
    targets={force._uid(fp):fp for fp in child.GetFootprints()}
    bindings={}
    for uid in proposal['footprint_uuids']:
        a={force._uid(p):p for p in originals[uid].Pads()}
        b={force._uid(p):p for p in targets[uid].Pads()}
        e={force._uid(p):p for p in expected[uid].Pads()}
        if a.keys()!=b.keys() or b.keys()!=e.keys():
            raise ValueError('manufacturer_rebinding_pad_identity_changed')
        for key,p in a.items():
            if (patterns._pad(b[key])!=patterns._pad(e[key])
                    or p.GetNetname()!=b[key].GetNetname()):
                raise ValueError('manufacturer_rebinding_actual_land_differs_from_catalog')
            bindings[key]=dict(ref=p.GetParentFootprint().GetReference(),footprint_uuid=uid,
                pad=p.GetNumber(),uuid=key,net=p.GetNetname(),
                before=force._point(p),after=force._point(b[key]))
    adjusted=copy.deepcopy(after);nodes=0;visited=set();active=set()
    def walk(value,depth=0):
        nonlocal nodes
        nodes+=1
        if nodes>262144 or depth>64:raise ValueError('manufacturer_metadata_rebinding_budget')
        container=type(value) in (dict,list,tuple)
        if container:
            if id(value) in active:raise ValueError('cyclic_manufacturer_metadata')
            if id(value) in visited:return
            active.add(id(value))
        if type(value) is dict:
            binding=bindings.get(value.get('uuid'))
            if binding and 'position_nm' in value:
                if (value['position_nm']!=binding['after']
                        or any(value.get(k)!=binding[k] for k in
                            ('ref','footprint_uuid','pad','uuid','net'))):
                    raise ValueError('manufacturer_report_pad_is_not_actual_saved_land:'+str(value))
                value['position_nm']=copy.deepcopy(binding['before'])
            for v in value.values():walk(v,depth+1)
        elif type(value) in (list,tuple):
            for v in value:walk(v,depth+1)
        if container:
            active.remove(id(value));visited.add(id(value))
    walk(adjusted)
    return adjusted,[dict(row,comparison_metadata_only=True,
        qualification_granted=False,release_authority=False) for row in bindings.values()]


def _rebind_received_measurement_paths(old, child, before, after, phases,
        manufacturer_footprint_uuids=()):
    """Refresh exact leaf UUID witnesses, never the physical cut or departure.

    Only an already independently received measurement or stationary phase supplies
    scope. Re-type both final saved native leaves, require the exact original
    owner/boundary/width/layer, both absolute whole-net cuts, and an identical
    retained witness prefix. The caller still runs the strict full physical
    comparator on this copy. Arbitrary unknown cuts, a new shunt exit, a
    changed owner, an acquired contact, and other witness changes cannot be
    normalized. A strict incomplete-authority cut stays unknown; only its
    exact independently received leaf-UUID suffix may be refreshed.
    """
    import copy
    import cec_measurement_leaf as leaf
    selected=[]
    for row in phases:
        proof=row['proof']
        if row.get('kind')=='measurement_leaf_reflow':
            if proof.get('only_exact_typed_measurement_leaf_changed') is not True:
                raise ValueError('independently_received_pure_measurement_phase_required')
            selected.append((proof,proof['source_leaf'],proof['new_leaf']))
        elif row.get('kind')=='stationary_cell':
            first,last=proof['source_leaves'],proof['new_leaves']
            if (not 1<=len(first)<=4 or len(first)!=len(last)
                    or not proof.get('gained_source_isolated_terminals')):
                raise ValueError('exact_received_stationary_leaf_cohort_required')
            selected.extend((proof,a,b) for a,b in zip(first,last))
    if len(selected)>4:raise ValueError('bounded_received_measurement_witness_scope_required')
    adjusted=copy.deepcopy(after);observations=[];seen=set()
    for proof,first,last in selected:
        if (proof.get('ok') is not True or proof.get('complete') is not True
                or proof.get('source_candidate_and_code_unchanged') is not True):
            raise ValueError('independently_received_pure_measurement_phase_required')
        pad=first['pad_uuid']
        if pad in seen:raise ValueError('measurement_witness_rebinding_repeated')
        seen.add(pad)
        original=leaf.plan(old,pad);final=leaf.plan(child,pad)
        def owner_pose(board,proposal):
            fp=board.FindFootprintByReference(proposal['owner'])
            if fp is None:raise ValueError('native_measurement_owner_missing')
            return (force._uid(fp),tuple(fp.GetPosition()),fp.GetOrientationDegrees(),fp.GetLayer(),
                tuple(sorted((force._uid(p),tuple(p.GetPosition()),tuple(p.GetSize()),
                    p.GetNetname(),p.GetAttribute(),p.GetShape(),tuple(p.GetLayerSet().CuStack()))
                    for p in fp.Pads())))
        if (owner_pose(old,original)!=owner_pose(child,final)
                and force._uid(old.FindFootprintByReference(original['owner']))
                    not in manufacturer_footprint_uuids):
            raise ValueError('received_measurement_owner_or_lands_moved')
        without_binding=lambda row:{k:v for k,v in row.items() if k!='source_native_binding'}
        if without_binding(first)!=without_binding(original) or without_binding(last)!=without_binding(final):
            raise ValueError('received_measurement_leaf_differs_from_final_saved_native_path')
        variable={'track_uuids','points_nm','source_length_mm','source_boundary_entry_nm','source_native_binding'}
        if {k:v for k,v in first.items() if k not in variable}!={k:v for k,v in last.items() if k not in variable}:
            raise ValueError('received_measurement_owner_boundary_or_dimension_changed')
        net=first['net']
        prior=sense.admit_changed_net(before,before,net);fresh=sense.admit_changed_net(before,after,net)
        absolute=(prior.get('ok') is True and fresh.get('ok') is True
                and prior.get('expected_legs') and prior['expected_legs']==fresh.get('expected_legs')
                and prior.get('checked')==fresh.get('checked'))
        inherited_unknown=False
        if not absolute:
            # An exactly owned local leaf can have a new UUID witness while
            # an unrelated force connector is STILL OPEN. Rebind only that
            # exact suffix, never its physical cut, unknown reason, guard,
            # source departure, retained prefix, or authority. The final
            # strict comparator still requires all other evidence identical.
            relevant=[[r for r in report.get('clipped_isolation',{}).get('details',())
                if r['net']==net and r.get('sense_terminal',{}).get('uuid')==pad]
                for report in (before,after)]
            inherited_unknown=all(len(rows)==1 and rows[0].get('ok') is None
                and rows[0].get('status')=='unknown'
                and rows[0].get('native',{}).get('reason')=='baseline_native_terminal_connectivity_incomplete'
                and rows[0].get('native',{}).get('complete') is False for rows in relevant)
        if not absolute and not inherited_unknown:
            raise ValueError('measurement_witness_requires_two_absolute_whole_net_cut_passes')
        rows=[]
        for report in (before,adjusted):
            found=[r for r in report['inner_departure']['details']
                if r['net']==net and r.get('sense_terminal',{}).get('uuid')==pad]
            if len(found)!=1 or found[0].get('ok') is not True:
                raise ValueError('positive_exact_measurement_terminal_departure_required')
            rows.append(found[0])
        witnesses=[]
        # Exact original boundary-contact suffixes are independently kept by
        # the leaf receiver. They remain part of the immutable witness prefix.
        common=[]
        for a,b in zip(reversed(first['track_uuids']),reversed(last['track_uuids'])):
            if a!=b:break
            common.append(a)
        for row,proposal in zip(rows,(first,last)):
            paths=[d['input_contact_paths'][pad] for d in row['native']['departures']
                if pad in d.get('input_contact_paths',{})]
            suffix=list(reversed(proposal['track_uuids']))[len(common):]+[pad]
            if (len(paths)!=1 or len(paths[0])>64 or len(paths[0])<=len(suffix)
                    or paths[0][-len(suffix):]!=suffix):
                raise ValueError('exact_received_measurement_leaf_witness_required:'+str(
                    dict(pad=pad,expected_suffix=suffix,actual_paths=paths)))
            witnesses.append((paths[0],paths[0][:-len(suffix)]))
        if witnesses[0][1]!=witnesses[1][1]:
            raise ValueError('measurement_witness_retained_departure_or_junction_changed')
        for departure in rows[1]['native']['departures']:
            if pad in departure.get('input_contact_paths',{}):
                departure['input_contact_paths'][pad]=copy.deepcopy(witnesses[0][0])
        observations.append(dict(pad_uuid=pad,net=net,
            retired_leaf_uuids=first['track_uuids'],received_leaf_uuids=last['track_uuids'],
            retained_witness_prefix=witnesses[0][1],before=prior,after=fresh,
            basis='exact_received_native_leaf_and_two_absolute_cut_passes' if absolute else
                'exact_received_native_leaf_suffix_only_strict_inherited_incomplete_authority',
            inherited_unknown_not_qualified=inherited_unknown,release_authority=False))
    return adjusted,observations


def _compare_input_repairs(before,after,repair_legs,modified_nets,transforms):
    """Refresh an entire shared input cohort only with absolute native proof.

    A new input tap can change the observed contact/witness of an already
    connected input on the same shunt land. Its old witness is not immutable,
    but neither is it eligible for a waiver. Re-admit every typed input on
    every repaired net before using the existing whole-net comparator. If
    even one input is unfinished, retain the exact newly connected leg scope
    and its strict unaffected-evidence checks instead.
    This receives physical input evidence, not a whole-board/release pass.
    """
    nets=sorted({key[2] for key in repair_legs})
    attempts=[sense.admit_changed_net(before,after,net) for net in nets]
    whole=bool(nets) and all(row.get('ok') is True and row.get('applicable') is True
        and row.get('checked')==len(row.get('expected_legs',()))
        and row.get('checked',0)>0 for row in attempts)
    result=sense.compare_repaired_preservation(before,after,repair_nets=nets,
        modified_nets=modified_nets,native_copper_transforms=transforms,
        repair_legs=None if whole else repair_legs)
    result['whole_cohort_admission_attempts']=attempts
    result['derived_input_scope']='absolutely_verified_whole_cohorts' if whole else 'newly_connected_legs_only'
    return result


def compare(source,candidate,before,after,*,timeout_s=10.,
            retired_ordinary_track_uuids=(),allow_locked_track_uuids=(),
            allow_selected_bypass_poses=False,source_cut_phases=(),source_cut_per_phase_leases=False,
            retired_force_bundle_native_uuids=(),allow_locked_force_bundle_native_uuids=()):
    result=dict(ok=False,complete=False,errors=[],release_authority=False,
                inherited_debt_qualified=False,full_kelvin_qualification=False)
    try:
        if type(source_cut_per_phase_leases) is not bool or (source_cut_per_phase_leases and not source_cut_phases):
            raise ValueError('explicit_typed_source_cut_phase_lease_required')
        if type(allow_selected_bypass_poses) is not bool:
            raise ValueError('explicit_bypass_pose_policy_required')
        if allow_selected_bypass_poses and (retired_ordinary_track_uuids or allow_locked_track_uuids):
            raise ValueError('bypass_pose_and_ordinary_retirement_scopes_cannot_mix')
        if source_cut_phases and (allow_selected_bypass_poses or retired_ordinary_track_uuids or allow_locked_track_uuids):
            raise ValueError('typed_cut_chain_and_other_retirement_scopes_cannot_mix')
        if allow_locked_force_bundle_native_uuids and not retired_force_bundle_native_uuids:
            raise ValueError('force_bundle_lock_scope_requires_exact_cut')
        if retired_force_bundle_native_uuids and (source_cut_phases or source_cut_per_phase_leases
                or allow_selected_bypass_poses or retired_ordinary_track_uuids or allow_locked_track_uuids):
            raise ValueError('force_bundle_and_other_native_retirement_scopes_cannot_mix')
        paths=[Path(source).resolve(),Path(candidate).resolve()]
        code=force._code_identity()
        if before.get('board_hint')!=after.get('board_hint') or not before.get('board_hint'):
            raise ValueError('explicit_unchanged_board_identity_required')
        for path,report in zip(paths,(before,after)):
            if (report.get('source_family_before')!=force._family(path,report.get('board_hint'))
                    or report.get('source_family_after')!=report.get('source_family_before')
                    or report.get('code_before')!=code or report.get('code_after')!=code
                    or report.get('identity_stable') is not True):
                raise ValueError('sense_replay_not_bound_to_saved_family')
        if retired_force_bundle_native_uuids:
            import cec_redundant_force_bundle as bundles
            proof=bundles.receive(*paths,board_hint=before['board_hint'],timeout_s=timeout_s,
                native_uuids=retired_force_bundle_native_uuids,
                allow_locked_native_uuids=allow_locked_force_bundle_native_uuids)
        elif source_cut_phases:
            import cec_source_cut_chain as chain
            proof=chain.receive(*paths,timeout_s=timeout_s,board_hint=before['board_hint'],phases=source_cut_phases,
                per_phase_leases=source_cut_per_phase_leases)
        elif allow_selected_bypass_poses:
            import cec_bypass_pose_receiving as bypass
            proof=bypass.receive(*paths,timeout_s=timeout_s,board_hint=before['board_hint'])
        elif retired_ordinary_track_uuids:
            import cec_ordinary_route_receiving as ordinary
            proof=ordinary.receive(*paths,timeout_s=timeout_s,
                retired_track_uuids=retired_ordinary_track_uuids,
                allow_locked_track_uuids=allow_locked_track_uuids,
                board_hint=before['board_hint'])
        else:
            if allow_locked_track_uuids:raise ValueError('locked_scope_requires_ordinary_retirements')
            proof=receiving.receive(*paths,timeout_s=timeout_s)
        result['source_delta']=proof
        if not proof.get('ok') or not proof.get('complete'):
            raise ValueError('independent_source_delta_refused')
        old=pcbnew.LoadBoard(str(paths[0]));b=pcbnew.LoadBoard(str(paths[1]))
        comparison_after,package_observations=_rebind_received_package_positions(old,b,after,proof)
        result['received_manufacturer_pad_metadata_rebound']=package_observations
        hint=before['board_hint'];resolver=fr._project_netclass_resolver(str(paths[0]))
        with force._thermal_hint(hint):
            domains=topology.board_current_domains(old,hint)
            contracts=topology.route_width_contracts(old,hint)
        result['current_joins']={net:current_receiving.compare(
            force._graph(old,net,domain,contracts[net],resolver(net) or {})[0],
            force._graph(b,net,domain,contracts[net],resolver(net) or {})[0])
            for net,domain in domains.items() if net in contracts}
        if set(result['current_joins'])!=set(domains):
            raise ValueError('incomplete_declared_current_contract_inventory')
        if any(not row['ok'] or not row['complete'] for row in result['current_joins'].values()):
            raise ValueError('new_current_authority_join_is_not_rated')
        incoming=set(proof['added_native_uuids'])
        manifests=defaultdict(lambda:dict(retired_track_uuids=[],added_zone_uuids=[],
            added_track_uuids=[],added_via_uuids=[],retired_via_uuids=[]))
        for t in b.GetTracks():
            uid=force._uid(t)
            if uid not in incoming:continue
            row=manifests[str(t.GetNetname())];row['added_track_uuids'].append(uid)
            if t.GetClass()=='PCB_VIA':row['added_via_uuids'].append(uid)
            elif t.GetClass()!='PCB_TRACK':raise ValueError('unsupported_added_contact_kind')
        # Only the exact independently compiled source-owned collector may
        # contribute a new zone count. Arbitrary pour area is not authority.
        allowed_zones=set(proof.get('exact_source_force_collector_uuids',()))
        actual_zones={force._uid(z):z for z in b.Zones() if force._uid(z) in incoming}
        if set(actual_zones)!=allowed_zones:
            raise ValueError('new_contact_zone_not_independently_source_owned')
        for uid,z in actual_zones.items():manifests[str(z.GetNetname())]['added_zone_uuids'].append(uid)
        outgoing=set(proof.get('retired_track_uuids',()))|set(proof.get('retired_via_uuids',()))
        for t in old.GetTracks():
            uid=force._uid(t)
            if uid not in outgoing:continue
            row=manifests[str(t.GetNetname())];row['retired_track_uuids'].append(uid)
            if t.GetClass()=='PCB_VIA':row['retired_via_uuids'].append(uid)
            elif t.GetClass()!='PCB_TRACK':raise ValueError('unsupported_retired_contact_kind')
        outgoing_zones=set(proof.get('retired_zone_uuids',()))
        if outgoing_zones and (not retired_force_bundle_native_uuids
                or proof.get('exact_native_source_minus_bundle_received') is not True):
            raise ValueError('retired_contact_zone_not_independently_received')
        for z in old.Zones():
            uid=force._uid(z)
            if uid in outgoing_zones:
                manifests[str(z.GetNetname())].setdefault('retired_zone_uuids',[]).append(uid)
        # Pure native capacitor motion can improve a local cell without new
        # copper. Independently proved moved pads still require actual-parent
        # physical evidence on both of their nets; no worker list is trusted.
        result['moved_bypasses']=proof.get('moved_bypasses',[])
        for row in result['moved_bypasses']:
            for net in (row['rail'],row['return_rail']):manifests[net]
        for row in proof.get('source_force_landing_replays',[]):manifests[row['net']]
        result['native_transforms']=[dict(net=net,**{k:sorted(v) for k,v in row.items()})
            for net,row in sorted(manifests.items())]
        if not manifests:raise ValueError('no_received_route_changes')
        # A proved rigid bypass pose changes no conductor inventory. Keep its
        # affected nets in the physical check, but do not manufacture an empty
        # copper-count transformation. The strict comparator rightly refuses
        # such a manifest; with no count delta it compares every count exactly.
        result['contact_count_transforms']=[row for row in result['native_transforms']
            if row['retired_track_uuids'] or row['added_zone_uuids'] or row['added_track_uuids']
                or row.get('retired_zone_uuids')]
        # Derive repair scope from independently received actual new copper
        # and exact physical demand identities. A worker cannot name an
        # unrelated net to waive its unknown or changed evidence.
        import json
        def demand_key(row):return json.dumps({k:row[k] for k in
            ('input_ref','leg','net','start','end','start_pad','end_pad')},sort_keys=True)
        prior={demand_key(r):r for r in before['same_net_connectivity']['details']}
        incoming_nets={str(t.GetNetname()) for t in b.GetTracks() if force._uid(t) in incoming}
        repair_legs=sorted({(r['input_ref'],r['leg'],r['net']) for r in comparison_after['same_net_connectivity']['details']
            if r['net'] in incoming_nets and r.get('ok') is True and demand_key(r) in prior
            and prior[demand_key(r)].get('ok') is not True})
        repair_nets=sorted({k[2] for k in repair_legs})
        result['derived_repaired_input_nets']=repair_nets
        result['derived_repaired_input_legs']=[list(k) for k in repair_legs]
        bank_nets=[]
        if incoming_nets:
            # A pure package/field pose has no new conductor and cannot close
            # a source bank. Keep that existing dispatch independent of bank
            # metadata. Actual added copper still requires both raw cut
            # inventories; missing evidence must not silently become a pass.
            old_cuts={(r['input_ref'],r['leg'],r['net']):r
                for r in before['clipped_isolation']['details']}
            bank_nets=sorted({r['net'] for r in comparison_after['clipped_isolation']['details']
                if r['net'] in incoming_nets and r.get('ok') is True
                and (r['input_ref'],r['leg'],r['net']) in old_cuts
                and old_cuts[(r['input_ref'],r['leg'],r['net'])].get('ok') is None
                and old_cuts[(r['input_ref'],r['leg'],r['net'])].get('native',{}).get('reason')
                    =='baseline_native_terminal_connectivity_incomplete'})
        comparison_after,measurement_observations=_rebind_received_measurement_paths(
            old,b,before,comparison_after,proof.get('phase_receiving',()),
            manufacturer_footprint_uuids=proof.get('manufacturer_modified_footprint_uuids',()))
        result['received_measurement_path_observations_rebound']=measurement_observations
        if retired_force_bundle_native_uuids:
            # Source locks authorize only the exact requested private cut.
            # Redundancy, real filled-copper connectivity and both absolute
            # cut packets are independently replayed above. Do not refresh
            # an internal-contact witness to hide a removed material path.
            result['independent_native_force_bundle_receiving']=proof
            preservation=sense.compare_contour_preservation(before,comparison_after,
                modified_nets=list(manifests),native_copper_transforms=result['contact_count_transforms'])
        elif repair_nets:
            preservation=_compare_input_repairs(before,comparison_after,repair_legs,
                list(manifests),result['contact_count_transforms'])
        elif bank_nets:
            # This is a different physical repair from a new monitor input.
            # The receiver independently reloads BOTH saved native families,
            # infers exact additive nets/widths, closes ALL actual authority
            # pairs, and replays absolute cuts. A candidate observation is
            # merely the trigger; no worker flag or edited BEFORE row decides.
            # Mixed rip-up phases or extra ordinary additions refuse there;
            # they must be received as separately bounded construction steps.
            import cec_force_bank_repair as banks
            received=banks.receive(*paths,board_hint=hint,timeout_s=max(10.,timeout_s))
            result['derived_force_bank_repair_nets']=bank_nets
            result['independent_native_force_bank_receiving']=received
            if (received.get('ok') is not True or received.get('complete') is not True
                    or received.get('inferred_repaired_nets')!=bank_nets):
                raise ValueError('exact_native_source_bank_repair_refused')
            preservation=received['physical_preservation']
        else:
            preservation=sense.compare_contour_preservation(before,comparison_after,modified_nets=list(manifests),
                native_copper_transforms=result['contact_count_transforms'],rebind_covered_internal_contacts=True)
        result['preservation']=preservation
        result.update(complete=preservation['comparison_complete'],
                      ok=preservation['comparison_complete'] and preservation['same_evidence'])
    except (KeyError,TypeError,ValueError) as exc:
        result['errors'].append(str(exc))
    return result
