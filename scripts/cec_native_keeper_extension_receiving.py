"""Source-retaining extension of an existing native purposeful power keeper.

An equal-priority overlapping filler is not a consolidation. Recompute the
declared keeper extension from actual unchanged source tracks and old fill,
retain its exact process/ownership contract, replay the whole saved phase,
then re-prove partitions, full current debt, fields and absolute Kelvin cuts.
No old conductor, old keeper fill, current width, source budget or clearance
may be lost. This grants no capacity, thermal, fabrication or release status.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_debt as current
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_ordinary_route_receiving as ordinary
import cec_rectilinear_copper as owner


def _seconds(value,limit):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=limit:
        raise ValueError('bounded_native_keeper_extension_work_lease_required')
    return float(value)


def _contacting_keepers(board,selected,*,deadline,allow_signed_native_keeper=False,
                        allow_source_solid_keeper=False,source_zone_uuid=None):
    """Read actual fill contact; this alone grants no construction authority."""
    import cec_native_contour_regions as signed
    names=(owner.ZONE_NAME,signed.ZONE_NAME) if allow_signed_native_keeper else (owner.ZONE_NAME,)
    net=str(selected[0].GetNetname());layer=int(selected[0].GetLayer())
    zones=list(board.Zones())
    if len(zones)>8192 or len({force._uid(z) for z in zones})!=len(zones):
        raise ValueError('bounded_unique_source_keeper_owner_inventory_required')
    candidates=[]
    for z in zones:
        if time.monotonic()>=deadline:raise ValueError('source_keeper_contact_inventory_deadline')
        if (z.GetIsRuleArea() or z.GetNetname()!=net or not z.IsOnLayer(layer)
                or set(z.GetLayerSet().CuStack())!={layer}
                or not allow_source_solid_keeper and z.GetZoneName() not in names
                or (source_zone_uuid is not None and force._uid(z)!=source_zone_uuid)
                or (source_zone_uuid is None and z.GetAssignedPriority()!=0)):continue
        if not z.IsFilled() or not z.HasFilledPolysForLayer(layer):
            if any(z.Outline().Collide(t.GetEffectiveShape(layer),0) for t in selected):
                raise ValueError('contacting_source_keeper_has_no_actual_native_fill')
            continue
        if any(z.GetFilledPolysList(layer).Collide(t.GetEffectiveShape(layer),0) for t in selected):
            candidates.append(z)
    return candidates


def contacting_keeper_uuids(board,track_uuids,*,allow_signed_native_keeper=False,timeout_s=10.):
    """Bounded read-only scheduler prescreen using the planner's native oracle.

    A positive result is only contact eligibility, never permission to change a
    keeper. The full planner and independent saved-board receiver still run.
    """
    deadline=time.monotonic()+_seconds(timeout_s,10.)
    if type(allow_signed_native_keeper) is not bool:
        raise ValueError('explicit_signed_native_keeper_class_policy_required')
    ids=ordinary._ids(track_uuids,'keeper_extension_source_tracks',64)
    live={force._uid(t):t for t in board.GetTracks()}
    if not ids or len(live)>16384 or not ids<=live.keys():
        raise ValueError('bounded_actual_source_keeper_tracks_required')
    selected=[live[u] for u in sorted(ids)]
    if (any(t.GetClass()!='PCB_TRACK' or not t.GetNetname() for t in selected)
            or len({(str(t.GetNetname()),int(t.GetLayer())) for t in selected})!=1):
        raise ValueError('one_actual_source_net_and_face_keeper_request_required')
    if str(selected[0].GetNetname()).rsplit('/',1)[-1].upper() in ('GND','AGND','PGND','DGND'):
        raise ValueError('ground_keeper_extension_not_authorized')
    return sorted(force._uid(z) for z in _contacting_keepers(board,selected,deadline=deadline,
        allow_signed_native_keeper=allow_signed_native_keeper))


def plan(board,track_uuids,*,required_width_nm,allow_locked_track_uuids=(),
         allow_grouped_track_uuids=(),allow_locked_zone_uuids=(),allow_grouped_zone_uuids=(),
         timeout_s=10.,retain_existing_keeper_lock=False,retain_existing_keeper_group=False,
         retained_native_track_material=False,allow_signed_native_keeper=False,source_diagonal_quantum_nm=0,
         envelope_margin_nm=1000,allow_source_solid_keeper=False,source_zone_uuid=None,
         contour_max_jog_nm=0):
    """Select ONE actual contacting compatible keeper, without changing it.

    This is source geometry/proposal scope only. A named keeper, empty outline,
    touching bbox or partial grouped owner is not permission. Multiple old
    same-priority owners require a different explicit consolidation operation.
    The caller still supplies exact locks, the original dimensional floor and
    full saved current/native/field/absolute-cut receiving.
    Explicit independent group retention is only for this non-retiring,
    original-fill-preserving operation; it never grants group reassignment.
    """
    deadline=time.monotonic()+_seconds(timeout_s,10.)
    if type(envelope_margin_nm) is not int or not 1<=envelope_margin_nm<=100000:
        raise ValueError('bounded_actual_keeper_construction_margin_required')
    if type(allow_signed_native_keeper) is not bool:
        raise ValueError('explicit_signed_native_keeper_class_policy_required')
    if (type(allow_source_solid_keeper) is not bool or allow_source_solid_keeper and not
            (retained_native_track_material and retain_existing_keeper_lock
             and retain_existing_keeper_group and allow_signed_native_keeper)):
        raise ValueError('source_solid_keeper_needs_exact_native_source_retention')
    if source_zone_uuid is not None and (not allow_source_solid_keeper
            or type(source_zone_uuid) is not str or not source_zone_uuid):
        raise ValueError('explicit_source_solid_keeper_identity_required')
    ids=ordinary._ids(track_uuids,'keeper_extension_source_tracks',64)
    if not ids:raise ValueError('nonempty_source_keeper_extension_track_scope_required')
    live={force._uid(t):t for t in board.GetTracks()}
    if len(live)>16384 or not ids<=live.keys():raise ValueError('bounded_actual_source_keeper_tracks_required')
    selected=[live[u] for u in sorted(ids)]
    if (any(t.GetClass()!='PCB_TRACK' or not t.GetNetname() for t in selected)
            or len({(str(t.GetNetname()),int(t.GetLayer())) for t in selected})!=1):
        raise ValueError('one_actual_source_net_and_face_keeper_request_required')
    net=str(selected[0].GetNetname());layer=int(selected[0].GetLayer())
    if net.rsplit('/',1)[-1].upper() in ('GND','AGND','PGND','DGND'):
        raise ValueError('ground_keeper_extension_not_authorized')
    candidates=_contacting_keepers(board,selected,deadline=deadline,
        allow_signed_native_keeper=allow_signed_native_keeper,
        allow_source_solid_keeper=allow_source_solid_keeper,source_zone_uuid=source_zone_uuid)
    if len(candidates)!=1:
        raise ValueError('one_actual_contacting_native_keeper_required:'+str(len(candidates)))
    keeper=candidates[0];uid=force._uid(keeper)
    if keeper.GetLocalClearance()<board.GetDesignSettings().m_MinClearance:
        raise ValueError('source_keeper_clearance_below_unchanged_board_floor')
    return owner.plan(board,sorted(ids),required_width_nm=required_width_nm,
        clearance_nm=keeper.GetLocalClearance(),min_thickness_nm=keeper.GetMinThickness(),
        allow_locked_track_uuids=allow_locked_track_uuids,allow_grouped_track_uuids=allow_grouped_track_uuids,
        allow_locked_zone_uuids=allow_locked_zone_uuids,allow_grouped_zone_uuids=allow_grouped_zone_uuids,
        retire_source_tracks=False,replace_native_zone_uuid=uid,enclosing_native_zone_uuids=[uid],
        landing_enclosure_mode='canonical_outline',contour_style='chamfer45',contour_grid_nm=1000,
        fill_envelope_margin_nm=4,fill_policy='source_preserving_regions',
        retain_existing_keeper_lock=retain_existing_keeper_lock,
        retain_existing_keeper_group=retain_existing_keeper_group,
        retained_native_track_material=retained_native_track_material,
        allow_signed_native_keeper=allow_signed_native_keeper,
        source_diagonal_quantum_nm=source_diagonal_quantum_nm,
        allow_source_solid_keeper=allow_source_solid_keeper,
        contour_max_jog_nm=contour_max_jog_nm,
        envelope_margin_nm=envelope_margin_nm,
        timeout_s=max(.001,min(10.,deadline-time.monotonic())),max_tracks=64)


def _records(records):
    if (type(records) is not list or not 1<=len(records)<=4
            or any(type(row) is not dict or set(row)!={'plan','materialized'} for row in records)):
        raise ValueError('bounded_exact_keeper_extension_records_required')
    ids=[]
    for row in records:
        plan=row['plan'];emitted=row['materialized']
        if type(plan) is not dict or type(emitted) is not dict:
            raise ValueError('literal_native_keeper_extension_objects_required')
        owner._validate_plan(plan)
        uid=(plan.get('replacement_source_zone') or {}).get('configuration',{}).get('uuid')
        if (type(uid) is not str or not uid or uid in ids or emitted.get('zone_uuid')!=uid
                or emitted.get('modified_zone_uuids')!=[uid]
                or plan.get('retire_source_tracks') is not False
                or plan.get('rebuild_keeper_from_tracks',False) is not False
                or plan.get('convex_support_cover',False) is not False
                or plan.get('fill_policy')!='source_preserving_regions'
                or plan.get('landing_enclosure_mode')!='canonical_outline'
                or not 1<=len(plan['source_tracks'])<=64):
            raise ValueError('source_fill_and_every_native_track_retained_extension_required')
        ids.append(uid)
    return ids


def _replan(board,plan,timeout_s):
    """Worker geometry/digests are never the expected-source oracle."""
    uid=plan['replacement_source_zone']['configuration']['uuid']
    rows=plan['source_tracks'];ids=[row['uuid'] for row in rows]
    return owner.plan(board,ids,clearance_nm=plan['clearance_nm'],
        min_thickness_nm=plan['min_thickness_nm'],required_width_nm=plan['required_width_nm'],
        allow_locked_track_uuids=[row['uuid'] for row in rows if row['locked']],
        allow_grouped_track_uuids=[row['uuid'] for row in rows if row['group_uuid']],
        envelope_margin_nm=plan['envelope_margin_nm'],retire_source_tracks=False,
        contour_style=plan.get('contour_style','square'),contour_grid_nm=plan.get('contour_grid_nm',1),
        fill_envelope_margin_nm=plan.get('fill_envelope_margin_nm',0),
        enclosing_native_zone_uuids=plan['enclosing_native_zone_uuids'],
        landing_enclosure_mode='canonical_outline',landing_max_jog_nm=plan.get('landing_max_jog_nm',0),
        contour_max_jog_nm=plan.get('contour_max_jog_nm',0),replace_native_zone_uuid=uid,
        allow_locked_zone_uuids=[uid],allow_grouped_zone_uuids=[uid],
        fill_policy='source_preserving_regions',timeout_s=timeout_s,max_tracks=64,
        retain_existing_keeper_lock=plan.get('retain_existing_keeper_lock',False),
        retain_existing_keeper_group=plan.get('retain_existing_keeper_group',False),
        retained_native_track_material=plan.get('retained_native_track_material',False),
        allow_signed_native_keeper=plan.get('allow_signed_native_keeper',False),
        allow_source_solid_keeper=plan.get('allow_source_solid_keeper',False),
        source_diagonal_quantum_nm=plan.get('source_diagonal_quantum_nm',0))


def receive_literal_phase(source,candidate,records,*,board_hint,timeout_s=10.):
    """Independently reconstruct an exact phase; not electrical admission."""
    r=dict(schema=1,scope='literal_original_source_retained_keeper_extension',ok=False,complete=False,
        errors=[],new_capacity_credited=False,release_authority=False,
        independent_electrical_and_uncapped_DRC_receiving_still_required=True)
    try:
        seconds=_seconds(timeout_s,10.);deadline=time.monotonic()+seconds
        ids=_records(records)
        if type(board_hint) is not str or not board_hint:raise ValueError('explicit_keeper_source_context_required')
        paths=[Path(p).resolve() for p in (source,candidate)]
        if paths[0]==paths[1]:raise ValueError('distinct_saved_keeper_extension_families_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        _,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        if (old.keys()!=new.keys() or any(u not in old or old[u][0]!='zone' or new[u][0]!='zone' for u in ids)
                or force._preservation_snapshot(paths[0])[1]!=force._preservation_snapshot(paths[1])[1]
                or force._sidecars(paths[0])!=force._sidecars(paths[1])):
            raise ValueError('exact_existing_keeper_inventory_and_source_metadata_required')
        child=pcbnew.LoadBoard(str(paths[1]));proofs=[]
        with tempfile.TemporaryDirectory(prefix='cec-keeper-extension-replay-') as tmp:
            expected=force._copy_family(paths[0],Path(tmp)/'family')
            rebuilt=pcbnew.LoadBoard(str(expected));rebuilt.SetFileName(str(expected))
            retained=[]
            for row,uid in zip(records,ids):
                remaining=deadline-time.monotonic()
                if remaining<=0:raise ValueError('keeper_extension_literal_replay_deadline')
                original=pcbnew.LoadBoard(str(expected));retained.append(original)
                actual=_replan(rebuilt,row['plan'],min(10.,remaining))
                if actual!=row['plan']:raise ValueError('keeper_extension_plan_not_derived_from_actual_source')
                tracks=[q['uuid'] for q in actual['source_tracks']]
                emitted=owner.materialize(rebuilt,actual,allow_locked_track_uuids=tracks,
                    allow_grouped_track_uuids=tracks,allow_locked_zone_uuids=[uid],allow_grouped_zone_uuids=[uid])
                if emitted!=row['materialized']:raise ValueError('keeper_extension_materialized_inventory_changed')
                owner.fill(rebuilt,actual,uid,regional_source=original,
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                proof=owner.receive(child,actual,uid,regional_source=original,
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                if (not proof['ok'] or not proof['complete']
                        or proof.get('original_native_keeper_fill_preserved') is not True):
                    raise ValueError('actual_old_fill_and_native_conductor_enclosure_required:'+str(proof.get('reason')))
                proofs.append(proof);additive._ground_refill(rebuilt)
                field._save_field_snapshot(rebuilt,expected);rebuilt=pcbnew.LoadBoard(str(expected))
            _,actual_nodes=additive._nodes(expected)
            if actual_nodes.keys()!=new.keys() or any(syntax._freeze(actual_nodes[u])!=syntax._freeze(new[u]) for u in new):
                raise ValueError('whole_original_source_keeper_and_ground_replay_differs')
        if (time.monotonic()>=deadline or epoch!=force._code_identity()
                or families!=[force._family(p,board_hint) for p in paths]):
            raise ValueError('keeper_extension_source_candidate_code_or_deadline_changed')
        r.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[1]),
            code_identity=epoch,source_candidate_and_code_unchanged=True,actual_modified_zone_uuids=ids,
            actual_modified_nets=sorted({row['plan']['net'] for row in records}),
            every_source_conductor_and_original_keeper_fill_retained=True,
            independently_received_native_extensions=proofs,
            exact_original_source_keeper_and_ground_refill_replayed=True)
    except (ValueError,TypeError,KeyError,RuntimeError,OSError,owner.Refused) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def receive(source,candidate,records,*,board_hint,timeout_s=10.,sense_timeout_s=10.):
    """Whole source-preserving geometry/current/field/absolute-cut reception."""
    r=dict(schema=1,scope='source_retained_native_keeper_extension_preservation',ok=False,complete=False,
        errors=[],new_capacity_credited=False,current_qualified=False,coupled_thermal_qualified=False,
        release_authority=False,full_native_DRC_mating_and_release_receiving_still_required=True)
    try:
        seconds=_seconds(timeout_s,10.);sense_seconds=_seconds(sense_timeout_s,60.)
        paths=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        literal=receive_literal_phase(*paths,records,board_hint=board_hint,timeout_s=seconds)
        r['independent_literal_phase']=literal
        if not literal['ok'] or not literal['complete']:raise ValueError('native_keeper_extension_literal_phase_refused')
        before,after=[pcbnew.LoadBoard(str(p)) for p in paths]
        parts=ordinary._partition(before,time.monotonic()+seconds)
        retained=set().union(*parts)
        updated=ordinary._partition(after,time.monotonic()+seconds,retained_keys=retained)
        if not all(any(part<=other for other in updated) for part in parts):
            raise ValueError('keeper_extension_surviving_native_partition_lost')
        debt=current.receive(*paths,board_hint=board_hint);r['current_debt_receiving']=debt
        if not debt['ok'] or not debt['complete']:raise ValueError('keeper_extension_full_current_debt_refused')
        with force._thermal_hint(board_hint):
            delta=sorted(field.blocker_keys(field.field_coupling_summary(str(paths[1])))-
                field.blocker_keys(field.field_coupling_summary(str(paths[0]))))
        r['new_field_blocker_keys']=delta
        if delta:raise ValueError('new_native_keeper_extension_field_blocker')
        first,last=[sense.replay(p,board_hint=board_hint,timeout_s=sense_seconds) for p in paths]
        nets=literal['actual_modified_nets']
        for evidence in (first,last):
            if any(row['net'] in nets and row.get('ok') is not True
                    for row in evidence['clipped_isolation']['details']):
                raise ValueError('changed_keeper_requires_positive_absolute_source_and_candidate_cuts')
        kelvin=sense.compare_contour_preservation(first,last,modified_nets=nets)
        r['physical_kelvin_preservation']=kelvin
        if not kelvin['comparison_complete'] or not kelvin['same_evidence']:
            raise ValueError('keeper_extension_absolute_cuts_and_unaffected_evidence_refused')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('keeper_extension_source_candidate_or_code_changed')
        r.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[1]),
            code_identity=epoch,source_candidate_and_code_unchanged=True,actual_modified_nets=nets,
            all_source_native_partitions_preserved=True,every_source_conductor_and_keeper_fill_retained=True)
    except (ValueError,TypeError,KeyError,RuntimeError,OSError,owner.Refused) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
