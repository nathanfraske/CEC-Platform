"""Native-fill-preflight multi-owner cleanup; no arbitrary-angle hull projection.

No board IDs, reference numbers or coordinates are selected here. Convex
chamfers are not defects. Every old fill record and native primitive remains
literal; additions must be local, source-anchored, region-clipped and receive
full original current/Kelvin/return/clearance/reference checks independently.
"""
import json
from pathlib import Path
import tempfile
import time
import pcbnew
import cec_force_current as force
import cec_source_retaining_boundary_pocket as single
import cec_reentrant_pocket_geometry as geometry
import cec_shallow_copper_pocket_cover as shallow
import cec_rectilinear_copper as native
import cec_regional_fill as regional
import cec_rounded_landing as landing
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_ordinary_route_receiving as ordinary
import cec_current_debt as current
import cec_ground_return_preservation as ground
import cec_force_sense_evidence as sense
import cec_native_copper_delta as delta
import cec_graphic_aware_copper_progress as graphic_progress
import cec_native_pocket_preflight as preflight

POLICY='native-fill-preflight-canonical-pocket-cohort-v2'
require=single.require
plain=single.plain

def plan(source, *, board_hint, maximum_zones=4, maximum_pockets_per_zone=4,
        maximum_guarded_offers=32, start_zone_rank=0, support_mode='local_overlap'):
    require(type(board_hint) is str and bool(board_hint),'source_batch_board_context_required')
    require(all(type(v) is int for v in (maximum_zones,maximum_pockets_per_zone,maximum_guarded_offers,start_zone_rank))
        and 1<=maximum_zones<=8 and 1<=maximum_pockets_per_zone<=8 and 1<=maximum_guarded_offers<=64
        and 0<=start_zone_rank<=128,'finite_source_pocket_batch_required')
    require(support_mode in ('local_overlap','inset_copy'),'literal_source_support_policy_required')
    source=Path(source).resolve();b=pcbnew.LoadBoard(str(source));epoch=force._code_identity()
    from cec_native_contour_regions import ZONE_NAME as signed_name
    zones={force._uid(z):z for z in b.Zones()}
    require(len(zones)<=8192,'source_batch_zone_inventory_bound')
    eligible=[];rejected=[]
    for uid,z in zones.items():
        if (z.GetZoneName() not in (native.ZONE_NAME,signed_name) or z.GetIsRuleArea()
                or len(list(z.GetLayerSet().CuStack()))!=1 or z.GetNetname().rsplit('/',1)[-1]=='GND'
                or z.Outline().OutlineCount()!=1 or z.Outline().HoleCount(0)):continue
        r=z.Outline().Outline(0);points=[[r.CPoint(i).x,r.CPoint(i).y] for i in range(r.PointCount())]
        try:offers=shallow.candidates(points)
        except ValueError as exc:
            rejected.append(dict(zone_uuid=uid,reason=str(exc)));continue
        ranked=[(i,o) for i,o in enumerate(offers[:64]) if geometry.reentrant(o)
            and o['original_vertices']-o['replacement_vertices']>=2]
        ranked.sort(key=lambda row:(-(row[1]['original_vertices']-row[1]['replacement_vertices']),row[1]['added_area_nm2'],row[0]))
        if ranked:eligible.append((uid,shallow.compact(points),ranked))
    require(len(eligible)<=128,'source_batch_registered_owner_bound')
    eligible.sort(key=lambda row:(-(row[2][0][1]['original_vertices']-row[2][0][1]['replacement_vertices']),
        row[2][0][1]['added_area_nm2'],-len(row[1]),row[0]))
    records=[];guarded=0
    for uid,points,ranked in eligible[start_zone_rank:]:
        if len(records)>=maximum_zones or guarded>=maximum_guarded_offers:break
        selected=[];profile=points;first=None;protected={}
        for index,offer in ranked:
            if len(selected)>=maximum_pockets_per_zone or guarded>=maximum_guarded_offers:break
            try:combined=geometry.merged(profile,offer['points_nm'])
            except ValueError:continue
            guarded+=1
            try:
                old_zone=zones[uid]
                envelope=geometry.visible_support_envelope(b,old_zone.GetNetname(),int(old_zone.GetFirstLayer()),offer['source_window_nm'],
                    process_halo_nm=(int(old_zone.GetMinThickness())+1)//2)
                spill=native._poly(offer['points_nm']);spill.BooleanSubtract(native._poly(points));spill.BooleanSubtract(native._poly(envelope))
                require(not spill.OutlineCount(),'nominal_pocket_would_extend_beyond_actual_source_copper_support')
            except (ValueError,native.Refused) as exc:
                rejected.append(dict(zone_uuid=uid,candidate_index=index,reason=str(exc)));continue
            try:q=single.plan(source,board_hint=board_hint,zone_uuid=uid,candidate_index=index)
            except (ValueError,native.Refused) as exc:
                rejected.append(dict(zone_uuid=uid,candidate_index=index,reason=str(exc)));continue
            trial_protected=dict(protected)
            for region in q['regional_combination_contract']['regional_fill_binding']['protected_regions']:
                key=region['native']['uuid'];require(key not in trial_protected or trial_protected[key]==region,'source_batch_region_snapshot_changed')
                trial_protected[key]=region
            chosen=dict(candidate_index=index,offer=offer,actual_source_support_envelope_nm=envelope)
            trial_contract=plain(q['regional_combination_contract'])
            trial_contract['regional_fill_binding']['protected_regions']=[trial_protected[k] for k in sorted(trial_protected)]
            trial_row=dict(zone_uuid=uid,source_keeper=q['source_keeper'],source_configuration=q['source_configuration'],
                source_points_nm=points,points_nm=combined,selected_offers=[*selected,chosen],regional_combination_contract=trial_contract)
            try:
                trial_board=preflight.emit(source,[trial_row],support_mode=support_mode,refill_ground=False)
                observed=preflight.observe(b,trial_board,trial_row)
            except (ValueError,RuntimeError,AssertionError,native.Refused) as exc:
                rejected.append(dict(zone_uuid=uid,candidate_index=index,stage='actual_native_fill_preflight',reason=str(exc)));continue
            if first is None:first=q
            protected=trial_protected
            profile=combined;chosen['native_fill_preflight']=observed;selected.append(chosen)
        if not selected:continue
        contract=first['regional_combination_contract']
        contract['regional_fill_binding']['protected_regions']=[protected[k] for k in sorted(protected)]
        records.append(dict(zone_uuid=uid,source_keeper=first['source_keeper'],source_configuration=first['source_configuration'],
            source_points_nm=points,points_nm=profile,selected_offers=selected,regional_combination_contract=contract))
    require(bool(records),'no_guarded_reentrant_source_pockets_in_bounded_portfolio')
    require(epoch==force._code_identity(),'source_batch_runtime_changed')
    return plain(dict(policy=POLICY,source_sha256=force._hash(source),code_identity=epoch,
        authority_sha256=force._hash(Path(__file__)),geometry_authority_sha256=force._hash(Path(geometry.__file__)),
        shallow_geometry_authority_sha256=force._hash(Path(shallow.__file__)),
        graphic_progress_authority_sha256=force._hash(Path(graphic_progress.__file__)),
        native_fill_preflight_authority_sha256=force._hash(Path(preflight.__file__)),
        single_owner_authority_sha256=force._hash(Path(single.__file__)),board_hint=board_hint,
        maximum_zones=maximum_zones,maximum_pockets_per_zone=maximum_pockets_per_zone,
        maximum_guarded_offers=maximum_guarded_offers,start_zone_rank=start_zone_rank,records=records,
        support_mode=support_mode,
        discovery=dict(eligible_source_owners=len(eligible),guarded_offers=guarded,refusals=rejected),
        original_native_fill_and_primitives_must_stay_literal=True,current_or_barrel_qualified=False,
        inherited_regional_intrusion_qualified=False,release_authority=False))

def args(proposal):
    return {k:proposal[k] for k in ('board_hint','maximum_zones','maximum_pockets_per_zone','maximum_guarded_offers','start_zone_rank','support_mode')}

def construct(source, proposal):
    require(plan(source,**args(proposal))==proposal,'stale_or_forged_source_pocket_batch_plan')
    child=preflight.emit(source,proposal['records'],support_mode=proposal['support_mode'])
    original=pcbnew.LoadBoard(str(source))
    for row in proposal['records']:preflight.observe(original,child,row)
    return child

def receive(source, candidate, proposal, *, board_hint):
    result=dict(ok=False,complete=False,errors=[],current_or_barrel_qualified=False,
        inherited_regional_intrusion_qualified=False,release_authority=False)
    try:
        source,candidate=[Path(q).resolve() for q in (source,candidate)]
        require(source!=candidate and board_hint==proposal['board_hint'],'actual_source_pocket_batch_child_required')
        epoch=force._code_identity();families=[force._family(q,board_hint) for q in (source,candidate)]
        replay=construct(source,proposal)
        with tempfile.TemporaryDirectory(prefix='cec-source-pocket-batch-') as work:
            expected=force._copy_family(source,Path(work)/'expected');field._save_field_snapshot(replay,expected)
            require(syntax._freeze(additive._nodes(expected)[0])==syntax._freeze(additive._nodes(candidate)[0]),
                'source_pocket_batch_changed_unowned_saved_native_evidence')
        require(force._sidecars(source)==force._sidecars(candidate)
            and force._preservation_snapshot(source)[1]==force._preservation_snapshot(candidate)[1],
            'source_pocket_batch_fields_parts_rules_or_stack_changed')
        before,after=[pcbnew.LoadBoard(str(q)) for q in (source,candidate)]
        old={force._uid(z):z for z in before.Zones()};new={force._uid(z):z for z in after.Zones()};scopes=set()
        native_preflights=[preflight.observe(before,after,row) for row in proposal['records']]
        for row in proposal['records']:
            z0,z1=old[row['zone_uuid']],new[row['zone_uuid']];c=row['source_configuration'];face=c['layers'][0]
            require(landing._configuration(z0)==landing._configuration(z1),'source_batch_keeper_process_or_owner_changed')
            require(regional.exact_source_contour_present(z1.GetFilledPolysList(face),z0.GetFilledPolysList(face),time.monotonic()+10.),
                'every_source_batch_keeper_record_must_stay_literal')
            fresh=z1.GetFilledPolysList(face).CloneDropTriangulation()
            old_count=z0.GetFilledPolysList(face).OutlineCount()
            for i in reversed(range(fresh.OutlineCount()-old_count,fresh.OutlineCount())):fresh.RemoveOutline(i)
            # Source-inset support copies are existing copper, not new area.
            # Their 1um construction inset prevents remote Boolean scraps;
            # the receiving subtraction/mask remains literal zero-spill.
            fresh.BooleanSubtract(z0.GetFilledPolysList(face))
            permitted=geometry.addition_window(row['source_points_nm'],row['points_nm'],c['min_thickness_nm'])
            spill=fresh.CloneDropTriangulation();spill.BooleanSubtract(permitted)
            require(not spill.OutlineCount(),'source_batch_added_copper_outside_derived_local_pocket_mask')
            # The nominal-outline halo above only models its unchanged fill
            # offset. Saved NEW copper itself must stay within the actual old
            # local material hull, with ZERO exterior-spur allowance.
            support=pcbnew.SHAPE_POLY_SET()
            for selected in row['selected_offers']:
                support.BooleanAdd(native._poly(geometry.visible_support_envelope(before,c['net'],face,
                    selected['offer']['source_window_nm'])))
            spur=fresh.CloneDropTriangulation();spur.BooleanSubtract(support)
            require(not spur.OutlineCount(),'source_batch_new_exterior_spur_past_actual_native_material_support')
            for region in row['regional_combination_contract']['regional_fill_binding']['protected_regions']:
                z=old[region['native']['uuid']];void=z.Outline().CloneDropTriangulation();void.BooleanSubtract(z.GetFilledPolysList(face))
                intrusion=fresh.CloneDropTriangulation();intrusion.BooleanIntersection(void)
                require(not intrusion.OutlineCount(),'source_batch_new_stronger_region_void_intrusion')
            scopes.add((c['net'],face))
        material=[]
        for net,face in sorted(scopes):
            observed=delta.compare(before,after,net=net,layer_ids=[face],timeout_s=10.)
            if not observed['ok'] and any('unsupported_footprint_copper_graphic' in error or 'unsupported_board_copper_graphic' in error for error in observed['errors']):
                original=observed
                observed=graphic_progress.compare(before,after,net=net,layer_ids=[face],timeout_s=10.)
                observed['original_global_comparator_unknown_retained']=original
                observed['original_clipped_kelvin_or_factory_gate_unchanged']=True
            require(observed['ok'] and observed['complete'],'source_batch_actual_joined_copper_delta_unproved:'+str(observed['errors']))
            require(observed['faces'][0]['definitely_added_area_mm2']>=.0025,
                'source_batch_authored_outline_only_or_insufficient_visible_native_progress')
            material.append(observed)
        parts=ordinary._partition(before,time.monotonic()+10.)
        actual=ordinary._partition(after,time.monotonic()+10.,retained_keys=set().union(*parts))
        require(all(any(part<=row for row in actual) for part in parts),'source_batch_native_partition_lost')
        debt=current.receive(source,candidate,board_hint=board_hint)
        require(debt['ok'] and debt['complete'],'source_batch_current_debt_regressed_or_unknown')
        returns=ground.receive(before,after,timeout_s=10.)
        require(returns['ok'] and returns['complete'],'source_batch_ground_return_regressed')
        with force._thermal_hint(board_hint):
            blockers=sorted(field.blocker_keys(field.field_coupling_summary(str(candidate)))-field.blocker_keys(field.field_coupling_summary(str(source))))
        require(not blockers,'source_batch_new_field_blocker')
        first,last=[sense.replay(q,board_hint=board_hint,timeout_s=40.) for q in (source,candidate)]
        nets=sorted({net for net,_ in scopes})
        for evidence in (first,last):
            require(all(row.get('ok') is True for row in evidence['clipped_isolation']['details'] if row['net'] in nets),
                'source_batch_changed_nets_require_positive_absolute_clipped_cuts')
        cuts=sense.compare_contour_preservation(first,last,modified_nets=nets)
        require(cuts['same_evidence'] and cuts['comparison_complete'],'source_batch_clipped_kelvin_or_unaffected_evidence_changed')
        require(epoch==force._code_identity() and families==[force._family(q,board_hint) for q in (source,candidate)],'source_batch_family_or_runtime_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),code_identity=epoch,
            exact_saved_native_source_reconstruction=True,every_source_filled_record_and_primitive_literal=True,
            fresh_material_is_local_and_no_new_stronger_void_intrusion=True,
            native_polygon_anchors_use_existing_source_overlap_or_inset_copies_not_new_bridges=True,
            no_new_exterior_spur_past_actual_native_material_support=True,
            actual_native_fill_preflight=native_preflights,arbitrary_angle_hull_projection_used=False,
            real_joined_copper_progress_not_only_authored_vertices=material,
            minimum_area_is_proposal_interest_not_geometry_or_manufacturing_waiver=True,
            all_native_partitions_preserved=True,source_current_receiving=debt,source_ground_return_receiving=returns,
            physical_kelvin_preservation=cuts,new_field_blockers=blockers,
            modified_zone_uuids=[r['zone_uuid'] for r in proposal['records']],modified_nets=nets,
            uncapped_native_pair_stack_and_visual_receiving_still_required=True)
    except (ValueError,RuntimeError,AssertionError,KeyError,TypeError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
