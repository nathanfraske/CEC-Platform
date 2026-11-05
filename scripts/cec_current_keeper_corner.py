"""A full-current native miter and its exact source-owned keeper contours.

Track-only finishing cannot leave an old keeper at the discarded corner.
Reconstruct that bounded combination from the literal saved parent, retaining
every other object, floor, layer, current authority, contact and rule. This
does not qualify inherited current/thermal debt or replace final native DRC,
absolute Kelvin, coupled-pair, stack and release receiving.
"""
import copy,json,tempfile,time,uuid
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_current_debt as current
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_full_current_corner_finish as corners
import cec_full_current_planar_reflow as full
import cec_ground_return_preservation as returns
import cec_native_contour_regions as regions
import cec_native_fill_geometry as fills
import cec_ordinary_route_receiving as ordinary
import cec_owned_contour_refresh as refresh
import cec_rectilinear_copper as owner
import cec_route_quality as quality
import cec_zone_fill as zone_fill
from cec_native_items import discard_items

SCOPE='exact_original_source_current_corner_and_owned_keeper_refresh'


def _contexts(board,record,current_plan,deadline,allow_locked_source):
    result=[];zones={force._uid(z):z for z in board.Zones()}
    owners=record['retained_native_corner_owners']
    if not 1<=len(owners)<=4:raise ValueError('bounded_literal_current_corner_keepers_required')
    for item in owners:
        zone=zones[item['zone_uuid']];selected=[]
        config=refresh._configuration(zone)
        params=dict(required_width_nm=current_plan['full_current_floor_nm'],clearance_nm=config['clearance_nm'],
            min_thickness_nm=config['min_thickness_nm'],contour_style='chamfer45',contour_grid_nm=1000,
            envelope_margin_nm=1000,fill_envelope_margin_nm=4)
        refresh._settings_valid(config,params)
        if config['locked'] and not allow_locked_source:
            raise ValueError('explicit_locked_current_keeper_scope_required')
        for track in board.GetTracks():
            if time.monotonic()>=deadline:raise ValueError('current_keeper_source_context_deadline')
            if (track.GetClass()!='PCB_TRACK' or track.GetNetname()!=config['net']
                    or not track.IsOnLayer(config['layer_id'])):continue
            material=owner._native_capsule(track);material.BooleanSubtract(zone.Outline())
            if not material.OutlineCount():selected.append(force._uid(track))
        if (not 1<=len(selected)<=128 or not set(selected)&set(current_plan['retired_track_uuids'])):
            raise ValueError('current_keeper_requires_exact_bounded_contained_source_tracks')
        rows=refresh._rows(board,selected,config,params)
        if any(r['locked'] for r in rows) and not allow_locked_source:
            raise ValueError('explicit_locked_current_keeper_track_scope_required')
        derived,_=refresh._profiles(board,rows,params,deadline)
        actual=regions.canonical_native_regions(zone.Outline(),timeout_s=max(.001,deadline-time.monotonic()))
        if not refresh._same_regions(derived,actual):
            raise ValueError('current_keeper_not_exactly_reconstructed_from_source_tracks')
        result.append(dict(zone_uuid=force._uid(zone),track_uuids=sorted(selected),parameters=params,
            allow_locked_zone=allow_locked_source,allow_locked_track_uuids=sorted(selected) if allow_locked_source else []))
    return sorted(result,key=lambda q:q['zone_uuid'])


def plan(source,*,board_hint,request,allow_locked_source=False,maximum_nm=2000000,minimum_nm=50000):
    corners._settings(allow_locked_source,maximum_nm,minimum_nm)
    source=Path(source).resolve()
    if not source.is_file() or source.suffix!='.kicad_pcb' or type(board_hint) is not str or not board_hint or type(request) is not dict:
        raise ValueError('saved_explicit_current_keeper_source_and_request_required')
    b=pcbnew.LoadBoard(str(source));deadline=time.monotonic()+10.
    found=corners.discover(b,source,board_hint=board_hint,allow_locked_source=allow_locked_source,
        maximum_nm=maximum_nm,minimum_nm=minimum_nm)
    matches=[q for q in found['composed_power_contour_frontier'] if q['request']==request]
    if len(matches)!=1:raise ValueError('literal_source_current_keeper_corner_required')
    typed=full.plan(b,source,board_hint=board_hint,retired_track_uuids=request['source_track_uuids'],
        max_source_track_mm=32.,max_source_cut_mm=48.)
    contexts=_contexts(b,matches[0],typed,deadline,allow_locked_source)
    result=dict(schema=1,scope=SCOPE,source=str(source),source_sha256=force._hash(source),board_hint=board_hint,
        request=copy.deepcopy(request),full_current_plan=typed,keeper_contexts=contexts,
        allow_locked_source=allow_locked_source,maximum_nm=maximum_nm,minimum_nm=minimum_nm,
        new_capacity_credited=False,current_sharing_inferred=False,ordinary_reclassification=False,release_authority=False)
    # This is a saved-worker transaction, not a Python-object handoff. Native
    # source models legitimately contain tuples; emit the exact JSON data
    # model on BOTH sides before comparing the independently rederived plan.
    # No values, widths, domains, source identities or owner keys are omitted.
    return json.loads(json.dumps(result,allow_nan=False))


def _args(q):
    return {k:q[k] for k in ('board_hint','request','allow_locked_source','maximum_nm','minimum_nm')}


def _stroke(track):
    row=owner._track_row(track);row.pop('uuid');return json.dumps(row,sort_keys=True)


def construct(proposal,*,incoming_uuids=None):
    if plan(proposal['source'],**_args(proposal))!=proposal:
        raise ValueError('stale_or_forged_source_current_keeper_plan')
    parent,b=[pcbnew.LoadBoard(proposal['source']) for _ in range(2)]
    ids=proposal['full_current_plan']['retired_track_uuids'];index={force._uid(t):t for t in b.GetTracks()}
    before={u:(tuple(t.GetStart()),tuple(t.GetEnd())) for u,t in index.items() if t.GetClass()=='PCB_TRACK'}
    locks={u:t.IsLocked() for u,t in index.items()}
    for uid,t in index.items():
        if uid not in ids:t.SetLocked(True)
    try:
        made=fr.chamfer_unlocked_right_angles(b,max_chamfer_mm=proposal['maximum_nm']/1e6,
            min_chamfer_mm=proposal['minimum_nm']/1e6,max_width_mm=10.,allow_locked_track_uuids=ids,
            exclude_nets={t.GetNetname() for t in b.GetTracks()}-{proposal['request']['net']},
            timeout_s=10.,max_corners=8192,max_chamfers=1)
    finally:
        for t in b.GetTracks():
            if force._uid(t) in locks:t.SetLocked(locks[force._uid(t)])
    changed=sorted(force._uid(t) for t in b.GetTracks() if force._uid(t) in before
        and (tuple(t.GetStart()),tuple(t.GetEnd()))!=before[force._uid(t)])
    if made['chamfered']!=1 or changed!=ids:
        raise ValueError('exact_native_current_keeper_corner_geometry_refused')
    new=sorted((t for t in b.GetTracks() if force._uid(t) not in index),key=_stroke)
    count=len(ids)+len(new)
    if incoming_uuids is None:incoming_uuids=[str(uuid.uuid4()) for _ in range(count)]
    existing=set(__import__('re').findall(r'\(uuid\s+"?([0-9a-fA-F-]{36})',Path(proposal['source']).read_text()))
    if (type(incoming_uuids) is not list or len(incoming_uuids)!=count or len(set(incoming_uuids))!=count
            or any(type(u) is not str or str(uuid.UUID(u))!=u for u in incoming_uuids)
            or set(incoming_uuids)&existing):
        raise ValueError('fresh_exact_current_keeper_replacement_identities_required')
    for track,uid in zip(new,incoming_uuids[len(ids):]):track.m_Uuid.Clone(pcbnew.KIID(uid))
    refresh_plans=[]
    for context in proposal['keeper_contexts']:
        q=refresh.plan(parent,b,**context);refresh.materialize(b,q,source=parent);refresh_plans.append(q)
    selected=pcbnew.ZONES();zone_ids={q['zone_uuid'] for q in proposal['keeper_contexts']}
    for zone in b.Zones():
        if force._uid(zone) in zone_ids:selected.append(zone)
    zone_fill.compile_selected(b,selected,initialize_selected=True);additive._ground_refill(b)
    proofs=[refresh.receive(b,q,source=parent) for q in refresh_plans]
    if not all(q['ok'] and q['complete'] for q in proofs):
        raise ValueError('actual_native_current_keeper_contour_refresh_not_received:'+str(proofs))
    replacements=[]
    for uid,incoming in zip(ids,incoming_uuids):
        track=index[uid];duplicate=track.Duplicate();duplicate.m_Uuid.Clone(pcbnew.KIID(incoming));b.Add(duplicate)
        replacements.append(track)
    discard_items(b,replacements);additive._ground_refill(b)
    return b,dict(chamfered=1,incoming_uuids=incoming_uuids,retired_track_uuids=ids,
        modified_zone_uuids=sorted(zone_ids),refresh_plans=refresh_plans,native_miter=made,
        source_derived_keeper_geometry_receiving=proofs)


def _visible(parent,child,proposal,incoming,deadline):
    net=proposal['request']['net'];face=proposal['request']['layer']
    changed=set(proposal['full_current_plan']['retired_track_uuids'])|{q['zone_uuid'] for q in proposal['keeper_contexts']}
    def polygon(item,error):
        if item.GetClass()=='ZONE':
            if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                raise ValueError('actual_saved_current_keeper_fill_required')
            p=item.GetFilledPolysList(face).CloneDropTriangulation()
        else:
            p=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(p,face,0,1000,error)
        fills.identity(p,deadline);return p
    old=pcbnew.SHAPE_POLY_SET()
    for t in [*parent.GetTracks(),*parent.Zones()]:
        if force._uid(t) in changed:old.BooleanAdd(polygon(t,pcbnew.ERROR_INSIDE))
    for t in [*child.GetTracks(),*child.Zones()]:
        if force._uid(t) in set(incoming)|changed:old.BooleanSubtract(polygon(t,pcbnew.ERROR_OUTSIDE))
    for item in [*parent.GetTracks(),*parent.Zones(),*(p for f in parent.GetFootprints() for p in f.Pads())]:
        if time.monotonic()>=deadline:raise ValueError('current_keeper_visible_material_deadline')
        if (force._uid(item) in changed or item.GetNetname()!=net or not item.IsOnLayer(face)
                or item.GetClass()=='ZONE' and item.GetIsRuleArea()):continue
        old.BooleanSubtract(polygon(item,pcbnew.ERROR_OUTSIDE))
    if not old.OutlineCount():raise ValueError('current_keeper_miter_not_visible_in_actual_native_copper')
    digest,vertices=fills.identity(old,deadline)
    return dict(ok=True,complete=True,removed_native_polygon_sha256=digest,removed_native_vertices=vertices,
        old_inside_minus_new_and_retained_outside=True,no_area_waiver=True,release_authority=False)


def receive(source,candidate,proposal,*,board_hint):
    r=dict(ok=False,complete=False,errors=[],current_qualified=False,fab_ready=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        if str(source)!=proposal['source'] or board_hint!=proposal['board_hint'] or plan(source,**_args(proposal))!=proposal:
            raise ValueError('saved_current_keeper_plan_not_rederived_from_original_source')
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        _,old=additive._nodes(source);_,actual=additive._nodes(candidate)
        cut=set(proposal['full_current_plan']['retired_track_uuids']);incoming=set(actual)-set(old)
        if set(old)-set(actual)!=cut:raise ValueError('exact_current_keeper_source_cut_required')
        actual_tracks={force._uid(t):t for t in child.GetTracks() if force._uid(t) in incoming}
        if set(actual_tracks)!=incoming or not 1<=len(incoming)<=8:
            raise ValueError('bounded_current_keeper_incoming_tracks_only')
        # The first rebuild derives replacement geometry; only its arbitrary
        # fresh IDs are rebound to matching actual saved objects in the second.
        trial,made=construct(proposal);generated={force._uid(t):t for t in trial.GetTracks()}
        ordered=[]
        for uid in made['incoming_uuids']:
            matches=[key for key,t in actual_tracks.items() if _stroke(t)==_stroke(generated[uid])]
            if len(matches)!=1:raise ValueError('exact_unique_saved_current_keeper_replacement_required')
            ordered.append(matches[0])
        if set(ordered)!=incoming:raise ValueError('unowned_current_keeper_addition')
        expected,rebuilt=construct(proposal,incoming_uuids=ordered)
        with tempfile.TemporaryDirectory(prefix='cec-current-keeper-receiving-') as tmp:
            path=force._copy_family(source,Path(tmp)/'expected');field._save_field_snapshot(expected,path)
            if (force._preservation_snapshot(path)!=force._preservation_snapshot(candidate)
                    or force._sidecars(source)!=force._sidecars(candidate)):
                raise ValueError('entire_native_current_keeper_reconstruction_differs')
        typed=proposal['full_current_plan'];deadline=time.monotonic()+10.
        with force._thermal_hint(board_hint):
            guard=full.capture.Guard(parent,source,net=typed['net'],board_hint=board_hint,timeout_s=10.)
        for track in actual_tracks.values():
            if (track.GetClass()!='PCB_TRACK' or track.GetNetname()!=typed['net'] or track.GetLayer()!=typed['layer_id']
                    or track.GetWidth()!=typed['width_nm'] or not guard(tuple(track.GetStart()),tuple(track.GetEnd()),track.GetWidth(),track.GetLayer())):
                raise ValueError('original_full_current_floor_face_or_control_guard_refused')
        if full._model(parent,source,typed['net'],board_hint)!=full._model(child,candidate,typed['net'],board_hint):
            raise ValueError('original_current_keeper_budget_or_domain_changed')
        owned_zones={q['zone_uuid'] for q in proposal['keeper_contexts']}
        boundary_parent=pcbnew.LoadBoard(str(source))
        discard_items(boundary_parent,[z for z in boundary_parent.Zones() if force._uid(z) in owned_zones])
        tracks={force._uid(t):t for t in boundary_parent.GetTracks()}
        r['original_fixed_cut_boundaries']=ordinary._boundaries(boundary_parent,child,[tracks[u] for u in cut],time.monotonic()+10.)
        first=ordinary._partition(parent,time.monotonic()+10.,retired_uuids=cut|owned_zones)
        last=ordinary._partition(child,time.monotonic()+10.,retained_keys=set().union(*first))
        if {frozenset(q) for q in first}!={frozenset(q) for q in last}:
            raise ValueError('whole_original_native_retained_partition_changed')
        r['ground_return_nonregression']=returns.receive(parent,child)
        if not r['ground_return_nonregression']['ok'] or not r['ground_return_nonregression']['complete']:
            raise ValueError('whole_original_ground_return_regression')
        r['whole_original_current_receiving']=current.receive(source,candidate,board_hint=board_hint)
        if not r['whole_original_current_receiving']['ok'] or not r['whole_original_current_receiving']['complete']:
            raise ValueError('whole_original_current_keeper_debt_regressed')
        with force._thermal_hint(board_hint):
            r['new_field_blockers']=sorted(field.blocker_keys(field.field_coupling_summary(str(candidate)))-field.blocker_keys(field.field_coupling_summary(str(source))))
        if r['new_field_blockers']:raise ValueError('whole_original_current_keeper_field_regression')
        a,b=[quality.analyze_board(board) for board in (parent,child)]
        if (not a['power_contours']['complete'] or not b['power_contours']['complete']
                or b['power_contours']['finding_count']>a['power_contours']['finding_count']
                or b['non_octilinear_count']>a['non_octilinear_count'] or b['issue_count']>a['issue_count']):
            raise ValueError('whole_native_current_keeper_craft_or_contour_regression')
        removed=sum(t.GetLength() for t in parent.GetTracks() if force._uid(t) in cut)-sum(t.GetLength() for t in actual_tracks.values())
        if removed<=0:raise ValueError('strict_current_keeper_track_shortening_required')
        visible=_visible(parent,child,proposal,incoming,time.monotonic()+10.)
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('current_keeper_source_candidate_or_code_changed')
        r.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            code_identity=epoch,retired_track_uuids=sorted(cut),added_native_uuids=sorted(incoming),modified_zone_uuids=sorted(owned_zones),
            actual_visible_native_material_removed=visible,saved_trace_length_mm=removed/1e6,chamfered=1,
            exact_entire_original_source_reconstruction=True,source_width_face_and_current_exact=True,new_holes=0,new_vias=0,
            original_native_partitions_identical=True,ordinary_reclassification=False,
            whole_original_native_DRC_absolute_Kelvin_pairs_stack_and_release_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
