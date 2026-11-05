"""Saved, original-Source complete protector reconstruction receiving.

The private projection is a proved subtraction/rigid pose, not a Source
grade, electrical authority, or a historical intermediate. All native final
suite, parity, intake and release gates remain independently mandatory.
"""
from pathlib import Path
import json
import math
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_complete_cell_receiving as paths
import cec_current_debt as current
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_fr as fr
import cec_ground_return_preservation as returns
import cec_native_partition_pair as partitions
import cec_precision_route as precision
import cec_constraints as constraints
import cec_fab_profile as fab
import cec_native_supply_via_context as web
import cec_route_dimensions as dimensions
import cec_existing_local_pofv_pad_rule as local_rule
import cec_route_quality as craft
import cec_protector_cell as cell


def _need(value, reason):
    if not value:raise ValueError(reason)


def _ordinary_source_limits(parent):
    """Native ordinary floors plus exact saved project floors, never preferences.

    LoadBoard can inherit process-global settings. An explicit saved higher
    floor must not disappear; neither a project field nor this reader may
    lower the native floor. The bounded Source family is rechecked outside.
    """
    limits=dimensions.board_limits(parent)
    path=Path(parent.GetFileName()).with_suffix('.kicad_pro')
    if path.is_file():
        _need(path.stat().st_size<=4194304,'bounded_protector_saved_project_required')
        project=json.loads(path.read_text())
        rules=project.get('board',{}).get('design_settings',{}).get('rules',{})
        _need(type(rules) is dict,'literal_protector_saved_design_rules_required')
        for key,saved in (('via_diameter','min_via_diameter'),
                ('via_drill','min_through_hole_diameter'),('annular','min_via_annular_width')):
            if saved not in rules:continue
            value=rules[saved]
            _need(type(value) in (int,float) and math.isfinite(value) and value>=0,
                'finite_positive_protector_saved_ordinary_floor_required')
            limits[key]=max(limits[key],value)
    return limits


def _barrel_process(parent,child,q,via):
    """Ordinary process minimum, or one exact original-Source pad rule.

    Netclass via values remain preferences. This supplies no path, current,
    web, return/reference, clearance, hole or release qualification.
    """
    _need(via.GetClass()=='PCB_VIA' and via.GetViaType()==pcbnew.VIATYPE_THROUGH
        and via.TopLayer()==pcbnew.F_Cu and via.BottomLayer()==pcbnew.B_Cu
        and all(via.IsOnLayer(l) for l in parent.GetEnabledLayers().CuStack()),
        'protector_actual_full_stack_through_barrel_required')
    diameter=via.GetWidth(via.TopLayer());drill=via.GetDrillValue()
    _need(type(diameter) is int and type(drill) is int and 0<drill<diameter,
        'protector_positive_actual_barrel_geometry_required')
    limits=_ordinary_source_limits(parent)
    ordinary=dimensions.ordinary_via_geometry({},limits,requested=(diameter/1e6,drill/1e6))
    proof=dict(via_uuid=force._uid(via),diameter_nm=diameter,drill_nm=drill,
        original_ordinary_limits_mm=limits,netclass_preferred_geometry_is_not_minimum=True,
        current_capacity_inferred=False,release_authority=False)
    if tuple(round(v*1e6) for v in ordinary)==(diameter,drill):
        return dict(proof,basis='unchanged_original_ordinary_process_floors')
    # The only smaller tier belongs to the six fresh manufacturer-owned pads.
    # Never use the child as a Source for rule discovery or accept an
    # unrelated same-net land, a group label, or caller containment metadata.
    _need(all(k in q for k in ('source','owner_uuid','target_pose','owner_ref')),
        'protector_subfloor_requires_exact_source_six_pad_context')
    _rebindings(parent,child,q)
    source=Path(q['source']).resolve(strict=True)
    _need(Path(parent.GetFileName()).resolve()==source,
        'protector_local_rule_original_source_required')
    original_groups=[g for g in parent.Groups() if g.GetName()==local_rule.GROUP]
    child_groups=[g for g in child.Groups() if g.GetName()==local_rule.GROUP]
    _need(len(original_groups)==len(child_groups)==1
        and force._uid(original_groups[0])==force._uid(child_groups[0])
        and original_groups[0].IsLocked()==child_groups[0].IsLocked()
        and any(force._uid(i)==force._uid(via) for i in child_groups[0].GetItems()),
        'protector_subfloor_original_factory_group_membership_required')
    retired=set(q.get('retired_track_uuids',()))|set(q.get('retired_via_uuids',()))
    _need({force._uid(i) for i in original_groups[0].GetItems()}-retired<=
        {force._uid(i) for i in child_groups[0].GetItems()},
        'protector_subfloor_retained_source_factory_members_lost')
    projected=pcbnew.LoadBoard(str(source))
    fp=cell._owner(projected,q['owner_uuid'])[0]
    fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in q['target_pose'][:2])))
    fp.SetOrientationDegrees(q['target_pose'][2])
    local_rule.bind_projected_source_poses(projected,{q['owner_ref']:q['target_pose']})
    matches=[]
    for pad in fp.Pads():
        if pad.GetNetCode()!=via.GetNetCode():continue
        context=local_rule.inspect_contained(projected,pad,via.GetPosition(),diameter,drill,via.GetNetCode())
        if context is not None:matches.append((pad,context))
    _need(len(matches)==1,'protector_subfloor_not_one_exact_source_owned_contained_land')
    pad,context=matches[0]
    # The original saved rule remains exact on the child. The general saved
    # additive replay independently receives all group members and changes.
    child_rule=Path(child.GetFileName()).with_suffix('.kicad_dru')
    _need(child_rule.is_file() and force._hash(child_rule)==context['rule_sha256'],
        'protector_original_local_rule_changed')
    return dict(proof,basis='exact_original_local_rule_on_source_rigid_six_pad_projection',
        owner_pad_uuid=force._uid(pad),source_rule=context,
        actual_saved_factory_group_uuid=force._uid(child_groups[0]))


def _incoming(parent, child, q, *, deadline=None):
    """Fresh saved inventory, only complete pair + exact Ground/clamp domains."""
    old={force._uid(t):t for t in parent.GetTracks()}
    new={force._uid(t):t for t in child.GetTracks()}
    outgoing=set(q['retired_track_uuids'])|set(q['retired_via_uuids'])
    _need(len(old)==len(list(parent.GetTracks())) and len(new)==len(list(child.GetTracks()))
        and old.keys()-new.keys()==outgoing,'protector_exact_complete_saved_cut_required')
    incoming=set(new)-set(old)
    _need(0<len(incoming)<=1024,'bounded_complete_protector_additions_required')
    pair=q['pair_plan']['pair'];pair_nets={pair['p'],pair['n']}
    clamp=q['clamp_request']['net']
    _need(clamp not in pair_nets|{'GND'},'distinct_protector_mandatory_domains_required')
    group=[g for g in child.Groups() if g.GetName()==fr.LOCAL_PAIR_RETURN_VIA_GROUP]
    pair_returns={force._uid(t) for g in group for t in g.GetItems()}
    _need(len(group)<=1,'unique_pair_return_group_required')
    nonpair=set()
    for uid in incoming:
        if deadline is not None:cell._remaining(deadline)
        item=new[uid];net=str(item.GetNetname())
        _need(item.GetClass() in ('PCB_TRACK','PCB_VIA') and net in pair_nets|{'GND',clamp},
            'protector_incoming_outside_complete_owned_domains')
        if net in pair_nets:
            _need(item.GetClass()!='PCB_TRACK' or item.GetWidth()==round(pair['width']*1e6),
                'protector_actual_pair_width_changed')
        elif not (net=='GND' and item.GetClass()=='PCB_VIA' and uid in pair_returns):
            if item.GetClass()=='PCB_VIA':
                _barrel_process(parent,child,q,item)
            nonpair.add(uid)
        if deadline is not None:cell._remaining(deadline)
    _need(pair_nets<={str(new[u].GetNetname()) for u in incoming
        if new[u].GetClass()=='PCB_TRACK'},'protector_both_pair_members_mandatory')
    _need(any(new[u].GetNetname()==clamp for u in nonpair)
        and any(new[u].GetNetname()=='GND' for u in nonpair),
        'protector_ground_and_clamp_additions_mandatory')
    return outgoing,incoming,nonpair,new


def _rebindings(parent,child,q):
    """Only six actual, independently rigid-posed physical pads can rebind."""
    before=cell._owner(parent,q['owner_uuid'])[0]
    after=cell._owner(child,q['owner_uuid'])[0]
    old={force._uid(p):p for p in before.Pads()}
    new={force._uid(p):p for p in after.Pads()}
    _need(len(old)==len(new)==6 and old.keys()==new.keys(),
        'protector_all_six_physical_pad_identities_required')
    # Compare to a native copy of the actual Source package, not caller pads.
    expected=pcbnew.FOOTPRINT(before)
    expected.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in q['target_pose'][:2])))
    expected.SetOrientationDegrees(q['target_pose'][2])
    _need(force._uid(after)==force._uid(before)
        and tuple(after.GetPosition())==tuple(expected.GetPosition())
        and after.GetOrientationDegrees()==expected.GetOrientationDegrees()
        and after.IsFlipped()==before.IsFlipped(),'protector_exact_requested_rigid_pose_required')
    expected_pads={force._uid(p):p for p in expected.Pads()}
    def physical(p):
        return (force._item_key(p),p.GetShape(),tuple(p.GetSize()),tuple(p.GetDrillSize()),
            p.GetAttribute(),tuple(p.GetLayerSet().CuStack()),p.GetOrientationDegrees(),tuple(p.GetOffset()))
    _need(all(physical(new[u])==physical(expected_pads[u]) for u in old),
        'protector_actual_six_pad_rigid_geometry_changed')
    return {force._item_key(new[u]):force._item_key(old[u]) for u in old}


def _pair_physical(child,q,candidate):
    pair=q['pair_plan']['pair']
    native=precision._native_pair_completion(child,pair)
    with force._thermal_hint(q['board_hint']):
        summary=constraints.high_speed_pair_summary(str(candidate),board=child)
    matches=[r for r in summary.get('pairs',[]) if (r['p'],r['n'])==(pair['p'],pair['n'])]
    return dict(native=native,physical=matches[0] if len(matches)==1 else None,
        complete=bool(native.get('complete') is True and native.get('connected') is True
            and all(t.GetWidth()==round(pair['width']*1e6) for t in child.GetTracks()
                if t.GetClass()=='PCB_TRACK' and t.GetNetname() in (pair['p'],pair['n']))
            and not any(r.get('disconnected_copper_uuids') for r in native.get('nets',{}).values())
            and summary.get('applicable') is True and len(matches)==1 and not matches[0]['violations']))


def receive(source,candidate,proposal,*,timeout_s=10.):
    """Explicit bounded constituents; every success re-proves the original Source.

    Proposal contains discovery inputs, never trusted cuts, roles, dimensions,
    currents or prior proof. All outputs/negative diagnostics remain raw.
    """
    cell._deadline(timeout_s)
    stages=('source_recompile','exact_projection_and_saved_delta','original_partitions',
        'whole_pair_physical','nonpair_full_current_paths','all_ground_returns',
        'current_debt','field_and_craft','absolute_source_kelvin',
        'absolute_child_kelvin','strict_kelvin_transition','final_live_bindings')
    report=dict(schema=1,scope='saved_original_source_complete_protector_cell',ok=False,complete=False,
        errors=[],phases={},maximum_constituents=len(stages),per_constituent_limit_s=timeout_s,
        current_qualified=False,barrel_ampacity_qualified=False,placement_qualified=False,
        routing_admitted=False,fab_ready=False,release_authority=False,
        full_original_parent_suite_receiving_still_required=True)
    initial=time.monotonic();stage=stages[0];started=initial;deadline=initial+timeout_s
    def finish(data):
        cell._remaining(deadline)
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-started,**data)
    try:
        source,candidate=[Path(p).resolve(strict=True) for p in (source,candidate)]
        _need(source!=candidate and type(proposal) is dict,'distinct_saved_protector_context_required')
        _,q=cell.compile(source,owner_uuid=proposal['owner_uuid'],board_hint=proposal['board_hint'],
            pair_name=proposal['pair_plan']['pair']['name'],target_pose=proposal['target_pose'],
            max_shift_mm=proposal['max_shift_mm'],timeout_s=cell._remaining(deadline))
        _need(cell._stable(q)==cell._stable(proposal),'stale_or_forged_complete_protector_proposal')
        _need(q['pose_screen']['ok'],'saved_protector_source_pose_screen_refused')
        epoch=force._code_identity();families=[force._family(p,q['board_hint']) for p in (source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        original_binding=cell.row._source_binding(parent);child_binding=cell.row._source_binding(child)
        outgoing,incoming,nonpair,new=_incoming(parent,child,q,deadline=deadline)
        bindings=_rebindings(parent,child,q)
        _need(precision.derive_coupled_pairs(str(source),board=parent)==
            precision.derive_coupled_pairs(str(candidate),board=child),'protector_pair_contract_changed')
        finish(dict(original_source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            independently_derived_outgoing_uuids=sorted(outgoing),incoming_uuids=sorted(incoming)))

        stage=stages[1];started=time.monotonic();deadline=started+timeout_s
        with tempfile.TemporaryDirectory(prefix='cec-protector-explicit-projection-') as tmp:
            projection=force._copy_family(source,Path(tmp)/'projection')
            projected,_=cell._project(parent,q,q['target_pose'],q['max_shift_mm'])
            additive._ground_refill(projected);field._save_field_snapshot(projected,projection)
            # No unrelated serializer/field changes accompany an owned pose.
            import cec_source_literal_footprint_retention as retain
            import cec_source_retaining_ses_import as text
            text.write_raw(projection,retain.retain(text.raw_text(source),text.raw_text(projection),[q['owner_uuid']]))
            replay=additive.receive(projection,candidate,board_hint=q['board_hint'],
                allow_pair_return_via_additions=True,timeout_s=cell._remaining(deadline))
            report['phases'][stage]=dict(receiving=replay)
            _need(replay.get('ok') is True and replay.get('complete') is True,
                'protector_exact_owned_pose_cut_and_additive_saved_replay_refused')
        finish(dict(receiving=replay,projection_is_not_source_grade_or_electrical_authority=True))

        stage=stages[2];started=time.monotonic();deadline=started+timeout_s
        preserved=partitions.compare(parent,child,retired_uuids=outgoing,identity_rebindings=bindings,
            timeout_s=cell._remaining(deadline))
        report['phases'][stage]=dict(receiving=preserved)
        _need(preserved.get('preserved') is True and preserved.get('exact_positive_native_island_overlap') is True
            and preserved.get('whole_zone_uuid_connectivity_credit') is False,
            'protector_original_retained_native_island_or_contact_lost')
        finish(dict(receiving={k:v for k,v in preserved.items() if k not in ('source_parts','child_parts','demoted_parts')},
            exact_six_moved_physical_pad_rebindings=True))

        stage=stages[3];started=time.monotonic();deadline=started+timeout_s
        pair_receipt=_pair_physical(child,q,candidate)
        report['phases'][stage]=dict(receiving=pair_receipt)
        _need(pair_receipt['complete'],'protector_saved_whole_pair_native_or_physical_contract_refused')
        finish(dict(receiving=pair_receipt))

        stage=stages[4];started=time.monotonic();deadline=started+timeout_s
        fp=cell._owner(child,q['owner_uuid'])[0]
        ground=next(p for p in fp.Pads() if force._uid(p)==q['ground_pad_uuid'])
        requests=dict(clamp_reference=q['clamp_request'],functional_ground=dict(kind='ground',net='GND',
            a=cell._port(ground),reach_mm=1.5,width_nm=q['ground_leaf']['width_nm']))
        receipt=paths._receive_paths(parent,child,requests,nonpair,q['board_hint'],deadline,
            received_barrel_uuids=[u for u in nonpair if new[u].GetClass()=='PCB_VIA'])
        connected=cell.source_ports.full_width_connection(parent,child,source,q['clamp_request'],q['board_hint'],deadline)
        _need(connected is not None and connected['all_named_contacts_connected']
            and connected['zone_and_foreign_net_edges_excluded'],'protector_saved_full_current_named_clamp_join_lost')
        reference=cell._final_ground_reference(child,ground,q['source_ground_return_mm'],deadline)
        _,_,contract=cell.full._model(parent,source,q['clamp_request']['net'],q['board_hint'])
        webs=[]
        for uid in sorted(nonpair):
            if new[uid].GetClass()=='PCB_VIA' and new[uid].GetNetname()==q['clamp_request']['net']:
                proof=web.receive(child,uid,contract,timeout_s=min(2.,cell._remaining(deadline)))
                webs.append(proof)
                report['phases'][stage]=dict(paths=receipt,full_width_named_clamp=connected,
                    final_ground_reference=reference,actual_clamp_barrel_webs=webs)
                _need(proof.get('ok') is True and proof.get('complete') is True,
                    'protector_saved_clamp_actual_full_current_barrel_web_required')
        finish(dict(paths=receipt,full_width_named_clamp=connected,final_ground_reference=reference,
            actual_clamp_barrel_webs=webs))

        stage=stages[5];started=time.monotonic();deadline=started+timeout_s
        receipt=returns.receive(parent,child,timeout_s=cell._remaining(deadline))
        report['phases'][stage]=dict(receiving=receipt)
        _need(receipt.get('ok') is True and receipt.get('complete') is True,'protector_all_source_ground_returns_refused')
        finish(dict(receiving=receipt))

        stage=stages[6];started=time.monotonic();deadline=started+timeout_s
        receipt=current.receive(source,candidate,board_hint=q['board_hint'])
        report['phases'][stage]=dict(receiving=receipt)
        _need(receipt.get('ok') is True and receipt.get('complete') is True,'protector_current_debt_regressed_or_unknown')
        finish(dict(receiving=receipt))

        stage=stages[7];started=time.monotonic();deadline=started+timeout_s
        quality=craft.analyze_board(child,track_uuid_scope=incoming)
        with force._thermal_hint(q['board_hint']):
            delta=sorted(field.blocker_keys(field.field_coupling_summary(str(candidate)))-
                field.blocker_keys(field.field_coupling_summary(str(source))))
        report['phases'][stage]=dict(craft=quality,new_field_blockers=delta)
        _need(quality['craft_ok'] and not delta,'protector_new_craft_or_field_blocker')
        finish(dict(craft=quality,new_field_blockers=delta))

        evidence=[]
        for index,path in enumerate((source,candidate)):
            stage=stages[8+index];started=time.monotonic();deadline=started+timeout_s
            proof=sense.replay(path,board_hint=q['board_hint'],timeout_s=cell._remaining(deadline))
            report['phases'][stage]=dict(receiving=proof)
            _need(proof.get('complete') is True and proof.get('identity_stable') is True,
                'protector_absolute_kelvin_replay_unknown')
            evidence.append(proof);finish(dict(receiving=proof))
        stage=stages[10];started=time.monotonic();deadline=started+timeout_s
        nets=sorted({q['pair_plan']['pair']['p'],q['pair_plan']['pair']['n'],'GND',q['clamp_request']['net']})
        manifest=sense.native_copper_transform_inventory(parent,child,modified_nets=nets)
        receipt=sense.compare_contour_preservation(*evidence,modified_nets=nets,native_copper_transforms=manifest)
        report['phases'][stage]=dict(receiving=receipt)
        _need(receipt.get('comparison_complete') is True and receipt.get('same_evidence') is True,
            'protector_strict_absolute_kelvin_contact_transition_refused')
        finish(dict(receiving=receipt,native_copper_transforms=manifest))
        stage=stages[11];started=time.monotonic();deadline=started+timeout_s
        _need(epoch==force._code_identity() and families==[force._family(p,q['board_hint']) for p in (source,candidate)]
            and original_binding==cell.row._source_binding(parent) and child_binding==cell.row._source_binding(child)
            and all(force._hash(Path(p))==h for p,h in q['source_symbol']['files_sha256'].items()),
            'protector_final_source_child_hierarchy_or_code_changed')
        finish(dict(original_source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),code_identity=epoch))
        report.update(ok=True,complete=True,elapsed_s=time.monotonic()-initial,
            all_original_native_partitions_preserved=True,all_six_physical_lands_received=True,
            exact_saved_complete_domains_received=True,source_family_and_code_unchanged=True)
    except Exception as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc))
        report['phases'].setdefault(stage,{})['elapsed_s']=time.monotonic()-started
        report.update(failed_stage=stage,elapsed_s=time.monotonic()-initial)
    return report
