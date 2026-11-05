"""Centered source-barrel landings in an existing native power keeper.

Every old barrel, track, pad, keeper process and filled source record stays
exact. Only a minimal symmetric 8-support cover of the actual source barrel
is joined to ONE actual keeper. New material is real, bounded, anchored KiCad
fill, not a renderer mask or invented FEM copper. No new capacity, barrel
ampacity, thermal, current or release qualification is granted.
"""
import argparse,json,math,tempfile,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_copper_echo as syntax
import cec_current_debt as current
import cec_field_coupling as field
import cec_fab_profile as fab
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_full_current_planar_reflow as authority
import cec_multi_keeper_contour as multi
import cec_native_contour_regions as signed
import cec_native_fill_geometry as geometry
import cec_native_drc_runner as native
import cec_ordinary_route_receiving as ordinary
import cec_rectilinear_copper as owner
import cec_rounded_landing as landing
import cec_route_quality as quality
import cec_stage_admission as admission
import cec_zone_fill

SCOPE='source_barrel_centered_existing_keeper_landing'


def _deadline(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=10:
        raise ValueError('bounded_native_barrel_landing_lease_required')
    return time.monotonic()+seconds


def _outer(via,face):
    result=pcbnew.SHAPE_POLY_SET()
    via.GetEffectiveShape(face).TransformToPolygon(result,1000,pcbnew.ERROR_OUTSIDE)
    if result.OutlineCount()!=1 or result.HoleCount(0):raise ValueError('one_actual_native_barrel_outer_shape_required')
    return result


def centered_cover(via,face,*,margin_nm=1000,grid_nm=1000):
    """Exact centered support planes measured from every native source vertex."""
    if (type(margin_nm) is not int or not 1<=margin_nm<=10000
            or type(grid_nm) is not int or not 1<=grid_nm<=10000):
        raise ValueError('bounded_actual_barrel_landing_support_policy_required')
    at=tuple(via.GetPosition());shape=_outer(via,face);ring=shape.Outline(0)
    points=[(int(ring.CPoint(i).x)-at[0],int(ring.CPoint(i).y)-at[1]) for i in range(ring.PointCount())]
    up=lambda n:-(-n//grid_nm)*grid_nm
    half=up(max(abs(v) for p in points for v in p)+margin_nm)
    diagonal=up(max(max(abs(x+y),abs(x-y)) for x,y in points)+2*margin_nm)
    cut=diagonal-half
    if not 0<cut<half:raise ValueError('proper_source_barrel_chamfer_support_required')
    offsets=[(-cut,-half),(cut,-half),(half,-cut),(half,cut),
             (cut,half),(-cut,half),(-half,cut),(-half,-cut)]
    polygon=[[at[0]+x,at[1]+y] for x,y in offsets]
    missing=shape.CloneDropTriangulation();missing.BooleanSubtract(owner._poly(polygon))
    if missing.OutlineCount():raise ValueError('centered_landing_loses_native_barrel_outer_shape')
    return polygon


def _keepers(board,via,face):
    return [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()==via.GetNetname()
        and set(z.GetLayerSet().CuStack())=={face} and z.GetAssignedPriority()==0
        and z.GetZoneName() in (owner.ZONE_NAME,signed.ZONE_NAME)
        and z.IsFilled() and z.HasFilledPolysForLayer(face)
        and z.GetFilledPolysList(face).Collide(via.GetEffectiveShape(face),0)]


def covered(board,via,face,zone):
    """Visual native outer-shape cover only; this is not plated-hole contact credit."""
    if not zone.IsFilled() or not zone.HasFilledPolysForLayer(face):return False
    outer=_outer(via,face);missing=outer.CloneDropTriangulation();missing.BooleanSubtract(zone.Outline())
    if missing.OutlineCount():return False
    actual=pcbnew.SHAPE_POLY_SET()
    for z in board.Zones():
        if not z.GetIsRuleArea() and z.GetNetname()==via.GetNetname() and z.IsOnLayer(face) and z.IsFilled() and z.HasFilledPolysForLayer(face):
            actual.BooleanAdd(z.GetFilledPolysList(face))
    outer.BooleanSubtract(actual)
    return not outer.OutlineCount()


def plan(board,source,via_uuid,face,*,board_hint,allow_locked_source=False,timeout_s=10.):
    deadline=_deadline(timeout_s)
    if (type(via_uuid) is not str or not via_uuid or type(face) is not int
            or type(board_hint) is not str or not board_hint or type(allow_locked_source) is not bool):
        raise ValueError('explicit_native_barrel_landing_source_context_required')
    tracks=list(board.GetTracks());zones=list(board.Zones())
    if len(tracks)>16384 or len(zones)>8192:raise ValueError('native_barrel_landing_inventory_bound')
    vias=[v for v in tracks if force._uid(v)==via_uuid and v.GetClass()=='PCB_VIA']
    if len(vias)!=1:raise ValueError('one_actual_source_barrel_required')
    via=vias[0];net=via.GetNetname()
    if (via.GetViaType()!=pcbnew.VIATYPE_THROUGH or not net or net.rsplit('/',1)[-1].upper() in ('GND','AGND','PGND','DGND')
            or face not in board.GetEnabledLayers().CuStack() or not via.IsOnLayer(face)
            or not 500000<=via.GetWidth(face)<=10000000 or via.GetDrillValue()<=0):
        raise ValueError('bounded_retained_native_power_barrel_required')
    profile=fab.get_profile(fab.board_profile_name(board));canonical=fab.COPPER_LAYER_IDS.get(face)
    if not profile or canonical not in fab.COPPER_LAYERS or profile['roles'][fab.COPPER_LAYERS.index(canonical)]=='GND':
        raise ValueError('source_barrel_landing_cannot_extend_on_a_reference_plane')
    kind,domain,contract=authority._model(board,Path(source),net,board_hint)
    # A saved plan is the receiving boundary, not an in-memory Python object.
    # Preserve every source-authority field in the one strict JSON form used
    # on disk, including nested tuple-valued layer/ref inventories. This is
    # not a relaxed comparison: rederive and compare the entire same payload.
    contract=json.loads(json.dumps(contract,sort_keys=True,allow_nan=False))
    candidates=_keepers(board,via,face)
    if len(candidates)!=1:raise ValueError('one_actual_contacting_barrel_keeper_required:'+str(len(candidates)))
    keeper=candidates[0];config=landing._configuration(keeper)
    if (config['group_uuid'] is not None or config['locked'] and not allow_locked_source
            or config['smoothing']!=0 or config['connection']!=int(pcbnew.ZONE_CONNECTION_FULL)
            or config['clearance_nm']<board.GetDesignSettings().m_MinClearance or config['min_thickness_nm']<=0):
        raise ValueError('unchanged_explicit_solid_barrel_keeper_process_required')
    if covered(board,via,face,keeper):raise ValueError('source_barrel_already_has_actual_purposeful_cover')
    cover=centered_cover(via,face);patch=owner._poly(cover)
    owner._require_unoccupied_outline(board,patch,net,face,deadline,clearance_nm=config['clearance_nm'])
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    old=signed._shape(signed.canonical_native_regions(keeper.Outline(),timeout_s=max(.001,min(10.,deadline-time.monotonic()))),'chamfer45')
    merged=unary_union([old,Polygon(cover)])
    if merged.geom_type!='Polygon' or not merged.is_valid:raise ValueError('one_connected_source_barrel_keeper_union_required')
    regions=signed._serialize(merged,'chamfer45')
    if keeper.GetZoneName()==owner.ZONE_NAME and regions[0]['holes_nm']:
        raise ValueError('regular_barrel_keeper_cannot_gain_authored_holes')
    profile=signed.native_poly(regions)
    owner._require_same_net_priority_available(board,profile,net,face,deadline,own_zone_uuid=force._uid(keeper))
    snapshot=multi._snapshot(keeper,deadline,include_islands=True);protected=[]
    for z in zones:
        if (z.GetIsRuleArea() or z.GetNetname()!=net or not z.IsOnLayer(face)
                or z.GetAssignedPriority()<=config['priority']):continue
        overlap=z.Outline().CloneDropTriangulation();overlap.BooleanIntersection(profile)
        if not overlap.OutlineCount():continue
        protected.append(multi._snapshot(z,deadline,include_islands=True))
        if len(protected)>64:raise ValueError('native_barrel_landing_protected_region_bound')
    return dict(schema=1,scope=SCOPE,source_binding=binding._source_binding(board),source_sha256=force._hash(Path(source)),
        board_hint=board_hint,via_uuid=via_uuid,layer_id=face,net=net,
        source_barrel=dict(at_nm=list(via.GetPosition()),diameter_nm=via.GetWidth(face),drill_nm=via.GetDrillValue(),
            top_layer=int(via.TopLayer()),bottom_layer=int(via.BottomLayer()),locked=bool(via.IsLocked())),
        keeper_uuid=force._uid(keeper),source_zones=[snapshot],profile=geometry.snapshot(profile,deadline),
        centered_cover_nm=cover,margin_nm=1000,grid_nm=1000,protected_source_regions=protected,
        allow_locked_source=allow_locked_source,source_current_kind=kind,source_current_contract=contract,
        clip_native_additions=True,native_addition_inset_nm=4,
        no_barrel_pad_track_rule_or_source_fill_retired=True,new_capacity_credited=False,release_authority=False)


def construct(board,source,proposal,*,timeout_s=10.):
    deadline=_deadline(timeout_s)
    fresh=plan(board,source,proposal['via_uuid'],proposal['layer_id'],board_hint=proposal['board_hint'],
        allow_locked_source=proposal['allow_locked_source'],timeout_s=max(.001,deadline-time.monotonic()))
    if fresh!=proposal:raise ValueError('barrel_landing_plan_not_derived_from_actual_source')
    parent=pcbnew.LoadBoard(str(source));zone=next(z for z in board.Zones() if force._uid(z)==proposal['keeper_uuid'])
    zone.UnFill();zone.Outline().RemoveAllContours();zone.Outline().Append(geometry.reconstruct(proposal['profile'],deadline))
    selected=pcbnew.ZONES();selected.append(zone);board.BuildConnectivity()
    cec_zone_fill.compile_selected(board,selected,timeout_s=max(.001,deadline-time.monotonic()))
    made=multi._preserve_source_regions(parent,zone,proposal,deadline)
    additive._ground_refill(board)
    return dict(zone_uuid=force._uid(zone),source_preserving_native_fill=made)


def receive_literal_phase(source,candidate,records,*,board_hint,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],new_capacity_credited=False,release_authority=False)
    try:
        deadline=_deadline(timeout_s)
        if (type(records) is not list or not 1<=len(records)<=8
                or any(type(q) is not dict or set(q)!={'plan','materialized'} for q in records)):
            raise ValueError('bounded_exact_source_barrel_landing_phase_required')
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        if (force._preservation_snapshot(source)[1]!=force._preservation_snapshot(candidate)[1]
                or force._sidecars(source)!=force._sidecars(candidate)):
            raise ValueError('barrel_landing_source_metadata_or_sidecars_changed')
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        if old.keys()!=new.keys():raise ValueError('barrel_landing_cannot_add_retire_native_items')
        for uid,node in old.items():
            if node[0]!='zone' and syntax._freeze(node)!=syntax._freeze(new[uid]):
                raise ValueError('barrel_landing_changed_pad_track_barrel_or_other_native_object')
        received=[];seen=set()
        with tempfile.TemporaryDirectory(prefix='cec-source-barrel-landing-') as tmp:
            expected=force._copy_family(source,Path(tmp)/'family');rebuilt=pcbnew.LoadBoard(str(expected))
            for row in records:
                declared=row['plan'];key=(declared['via_uuid'],declared['layer_id'])
                if key in seen:raise ValueError('duplicate_source_barrel_face_in_batch')
                seen.add(key)
                fresh=plan(rebuilt,source,declared['via_uuid'],declared['layer_id'],board_hint=board_hint,
                    allow_locked_source=declared['allow_locked_source'],timeout_s=max(.001,deadline-time.monotonic()))
                if fresh!=declared:raise ValueError('barrel_landing_source_plan_changed')
                made=construct(rebuilt,source,fresh,timeout_s=max(.001,deadline-time.monotonic()))
                if made!=row['materialized']:raise ValueError('barrel_landing_materialized_record_changed')
                field._save_field_snapshot(rebuilt,expected);rebuilt=pcbnew.LoadBoard(str(expected))
                zone=next(z for z in child.Zones() if force._uid(z)==fresh['keeper_uuid'])
                if landing._configuration(zone)!=fresh['source_zones'][0]['configuration']:
                    raise ValueError('barrel_landing_keeper_process_or_ownership_changed')
                via=next(t for t in child.GetTracks() if force._uid(t)==fresh['via_uuid'])
                if not covered(child,via,fresh['layer_id'],zone):raise ValueError('saved_barrel_outer_shape_still_exposed')
                received.append(fresh)
            _,actual=additive._nodes(expected)
            if actual.keys()!=new.keys() or any(syntax._freeze(actual[u])!=syntax._freeze(new[u]) for u in new):
                raise ValueError('whole_source_barrel_landing_and_native_ground_refill_replay_differs')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('barrel_landing_source_candidate_or_code_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            source_candidate_and_code_unchanged=True,actual_modified_nets=sorted({q['net'] for q in received}),
            actual_modified_zone_uuids=sorted({q['keeper_uuid'] for q in received}),received_barrel_faces=sorted(seen),
            every_source_barrel_track_pad_pose_rule_process_and_fill_retained=True,
            centered_native_outer_cover_received=True,plated_hole_or_current_qualification=False)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError,owner.Refused) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def receive(source,candidate,records,*,board_hint,sense_timeout_s=40.):
    r=dict(ok=False,complete=False,errors=[],current_qualified=False,coupled_thermal_qualified=False,
        new_capacity_credited=False,release_authority=False,fresh_native_DRC_and_release_still_required=True)
    try:
        if type(sense_timeout_s) not in (int,float) or not math.isfinite(sense_timeout_s) or not 0<sense_timeout_s<=60:
            raise ValueError('bounded_source_barrel_absolute_cut_lease_required')
        source,candidate=[Path(p).resolve() for p in (source,candidate)];epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)]
        literal=receive_literal_phase(source,candidate,records,board_hint=board_hint);r['independent_saved_phase']=literal
        if not literal['ok'] or not literal['complete']:raise ValueError('source_barrel_landing_literal_phase_refused:'+str(literal['errors']))
        before,after=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        parts=ordinary._partition(before,time.monotonic()+10.)
        new=ordinary._partition(after,time.monotonic()+10.,retained_keys=set().union(*parts))
        if not all(any(p<=q for q in new) for p in parts):raise ValueError('barrel_landing_retained_native_partition_lost')
        debt=current.receive(source,candidate,board_hint=board_hint);r['whole_source_current_receiving']=debt
        if not debt['ok'] or not debt['complete']:raise ValueError('barrel_landing_whole_source_current_refused')
        with force._thermal_hint(board_hint):
            delta=sorted(field.blocker_keys(field.field_coupling_summary(str(candidate)))-field.blocker_keys(field.field_coupling_summary(str(source))))
        r['new_field_blockers']=delta
        if delta:raise ValueError('barrel_landing_new_field_blocker')
        first,last=[sense.replay(p,board_hint=board_hint,timeout_s=sense_timeout_s) for p in (source,candidate)]
        nets=sorted(set(literal['actual_modified_nets'])|{'GND'})
        cuts=sense.compare_contour_preservation(first,last,modified_nets=nets,
            native_copper_transforms=sense.native_copper_transform_inventory(before,after,modified_nets=nets))
        r['physical_kelvin_preservation']=cuts
        if not cuts['comparison_complete'] or not cuts['same_evidence']:raise ValueError('barrel_landing_absolute_cuts_and_unaffected_evidence_refused')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('barrel_landing_sources_or_code_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            source_candidate_and_code_unchanged=True,all_source_native_partitions_preserved=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError,owner.Refused) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def discover(board,source,*,board_hint,timeout_s=10.,max_requests=32):
    """Source-derived large visible barrel overhangs, never an all-copper grade."""
    deadline=_deadline(timeout_s)
    if type(max_requests) is not int or not 1<=max_requests<=64:
        raise ValueError('bounded_source_barrel_landing_request_inventory_required')
    tracks=list(board.GetTracks())
    if len(tracks)>16384:raise ValueError('source_barrel_landing_inventory_bound')
    rows=[];authority_cache={}
    profile=fab.get_profile(fab.board_profile_name(board))
    if not profile:raise ValueError('actual_source_fabrication_profile_required')
    for via in tracks:
        owner._check_deadline(deadline)
        if (via.GetClass()!='PCB_VIA' or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or not via.GetNetname() or via.GetNetname().rsplit('/',1)[-1].upper() in ('GND','AGND','PGND','DGND')):continue
        for face in sorted(map(int,board.GetEnabledLayers().CuStack())):
            if not via.IsOnLayer(face) or not 1000000<=via.GetWidth(face)<=10000000:continue
            canonical=fab.COPPER_LAYER_IDS.get(face)
            if canonical not in fab.COPPER_LAYERS or profile['roles'][fab.COPPER_LAYERS.index(canonical)]=='GND':continue
            keepers=_keepers(board,via,face)
            if len(keepers)!=1:continue
            shape=_outer(via,face);shape.BooleanSubtract(keepers[0].Outline())
            # Visual allocation floor only: do not spend a real-board solve
            # on a sub-pixel native tessellation sliver. It grants no width,
            # current, clearance or all-board contour-completion exception.
            if not shape.OutlineCount() or shape.Area()<5000000000:continue
            net=via.GetNetname()
            if net not in authority_cache:
                try:authority._model(board,Path(source),net,board_hint);authority_cache[net]=True
                except (ValueError,RuntimeError,KeyError):authority_cache[net]=False
            if not authority_cache[net] or covered(board,via,face,keepers[0]):continue
            rows.append(dict(via_uuid=force._uid(via),layer_id=face,net=net,
                keeper_uuid=force._uid(keepers[0]),diameter_nm=via.GetWidth(face),
                exposed_outer_area_nm2=shape.Area()))
    rows.sort(key=lambda q:(-q['exposed_outer_area_nm2'],q['via_uuid'],q['layer_id']))
    return dict(ok=True,complete=True,requests=rows[:max_requests],all_matching_requests=len(rows),
        request_budget_truncated=len(rows)>max_requests,visual_diameter_work_floor_nm=1000000,
        visual_exposed_area_work_floor_nm2=5000000000,all_ugly_copper_qualified_absent=False)


def _priority_requests(requests,via_uuids):
    if (type(via_uuids) not in (list,tuple) or len(via_uuids)>4
            or any(type(u) is not str or not u for u in via_uuids) or len(set(via_uuids))!=len(via_uuids)
            or not set(via_uuids)<={q['via_uuid'] for q in requests}):
        raise ValueError('priority_hints_must_name_actual_source_barrel_requests')
    return sorted(requests,key=lambda q:q['via_uuid'] not in set(via_uuids))


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,
        allow_locked_source=False,max_trials=16,max_changes=4,priority_via_uuids=()):
    """Finite native-screened batch; expensive whole-source cut proof runs once."""
    if (type(board_hint) is not str or not board_hint or type(expected_source_sha256) is not str
            or len(expected_source_sha256)!=64 or reporting_build is None
            or type(allow_locked_source) is not bool or type(max_trials) is not int or not 1<=max_trials<=64
            or type(max_changes) is not int or not 1<=max_changes<=8):
        raise ValueError('bounded_explicit_source_barrel_landing_stage_required')
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if outdir.exists() or force._hash(source)!=expected_source_sha256:
        raise ValueError('exact_source_and_fresh_barrel_landing_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    r=dict(ok=False,complete=False,changed=False,errors=[],source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,attempts=[],records=[],
        source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False,new_capacity_credited=False)
    def observe(path,label):
        shadow=force._copy_family(path,outdir/(label+'-native-input'));dest=outdir/(label+'.drc.json')
        producer=native.run(shadow,dest,reporting_build=reporting_build,timeout_s=10.)
        r.setdefault('native_producers',{})[label]=producer
        if not producer['ok'] or not producer['complete'] or producer['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_barrel_landing_native_inventory_required')
        return json.loads(dest.read_text())
    try:
        board=pcbnew.LoadBoard(str(source));discovery=discover(board,source,board_hint=board_hint,max_requests=64)
        requests=_priority_requests(discovery['requests'],priority_via_uuids)
        r.update(source_derived_discovery=discovery,priority_hints=list(priority_via_uuids),max_changes=max_changes,
            hints_grant_no_mutation_or_receiving_authority=True)
        baseline=None;before_quality=quality.analyze_board(board);active=source;records=[]
        for index,request in enumerate(requests[:max_trials]):
            if len(records)>=max_changes:break
            row=dict(request=request,accepted=False);r['attempts'].append(row)
            try:
                child_board=pcbnew.LoadBoard(str(active))
                proposal=plan(child_board,source,request['via_uuid'],request['layer_id'],board_hint=board_hint,
                    allow_locked_source=allow_locked_source)
                made=construct(child_board,source,proposal)
                child=force._copy_family(active,outdir/('UNADMITTED-barrel-landing-'+str(index)))
                field._save_field_snapshot(child_board,child)
                record=dict(plan=proposal,materialized=made)
                if baseline is None:
                    baseline=observe(source,'source')
                    if baseline['unconnected_items']:raise ValueError('zero_open_source_precedes_optional_barrel_landing')
                last=observe(child,'candidate-'+str(index))
                faults=sorted({admission._canonical_identity(v) for v in last['violations']}-
                    {admission._canonical_identity(v) for v in baseline['violations']})
                row.update(new_native_fault_ids=faults,native_opens=len(last['unconnected_items']))
                if faults or last['unconnected_items']:raise ValueError('barrel_landing_new_native_fault_or_open')
                after=quality.analyze_board(pcbnew.LoadBoard(str(child)))
                if any(after[k]>before_quality[k] for k in ('issue_count','non_octilinear_count')):
                    raise ValueError('barrel_landing_cannot_regress_route_craft')
                row.update(geometry_screened=True,candidate=str(child),candidate_sha256=force._hash(child))
                records.append(record);active=child
            except (ValueError,RuntimeError,TypeError,KeyError,OSError,owner.Refused) as exc:
                row['refusal']=type(exc).__name__+':'+str(exc)
            print(json.dumps(dict(via=request['via_uuid'],face=request['layer_id'],geometry_screened=row.get('geometry_screened',False),
                whole_batch_not_yet_received=True,refusal=row.get('refusal'))),flush=True)
        if records:
            # Exercise exactly the persisted receipt schema before a success
            # can be reported. Native replay of worker-only Python records is
            # insufficient, even when the copper itself is unchanged.
            records=json.loads(json.dumps(records,sort_keys=True,allow_nan=False))
            proof=receive(source,active,records,board_hint=board_hint);r['independent_whole_source_receiving']=proof
            if not proof['ok'] or not proof['complete']:
                raise ValueError('source_barrel_landing_whole_batch_refused:'+str(proof['errors']))
            r.update(changed=True,candidate=str(active),candidate_sha256=force._hash(active),records=records)
            for row in r['attempts']:row['accepted']=row.get('geometry_screened',False)
        r.update(ok=True,complete=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,owner.Refused) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    r['source_family_and_code_unchanged']=epoch==force._code_identity() and family==force._family(source,board_hint)
    if not r['source_family_and_code_unchanged']:
        r.update(ok=False,complete=False,changed=False,candidate=str(source),candidate_sha256=expected_source_sha256)
        r['errors'].append('barrel_landing_source_or_code_changed')
    force._write(outdir/'stage.json',r);return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--max-trials',type=int,default=16);p.add_argument('--max-changes',type=int,default=4)
    p.add_argument('--priority-via-uuid',action='append',default=[]);p.add_argument('--allow-locked-source',action='store_true')
    a=p.parse_args();import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,max_trials=a.max_trials,
        max_changes=a.max_changes,priority_via_uuids=a.priority_via_uuid)
    print(json.dumps({k:r[k] for k in ('ok','complete','changed','candidate','candidate_sha256','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
