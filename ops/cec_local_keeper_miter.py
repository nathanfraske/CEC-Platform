"""Source-exact local full-current miters under retained native power keepers.

A trace hidden under a keeper is not a finished contour. This separate
operation owns only a bounded, branch-free local window of one actual source
keeper. It does not guess how the entire historical pour was generated or
replace that pour with a newly generated whole-board contour. Current roles,
widths, all remote windows, source objects and release gates stay unchanged.
"""
import json,math,tempfile,time,uuid
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_keeper_corner as existing
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_full_current_corner_finish as corners
import cec_full_current_planar_reflow as full
import cec_native_contour_regions as regions
import cec_native_fill_geometry as fills
import cec_ordinary_route_receiving as ordinary
import cec_owned_contour_refresh as refresh
import cec_rectilinear_copper as contours
import cec_route_corner_contacts as contacts
import cec_route_quality as quality
import cec_sensitive_scalar_path_reflow as paths
import cec_zone_fill as zone_fill
import cec_redundant_supply_branch_sweep as actual_material
from cec_native_items import discard_items

POLICY='source-exact-branch-free-local-current-keeper-miter-v1'

def require(value,message):
    if not value:raise ValueError(message)

def box_poly(bounds):
    x0,y0,x1,y1=bounds;p=pcbnew.SHAPE_POLY_SET();p.NewOutline()
    for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1)):p.Append(x,y)
    return p

def profile(board,tracks,margin,deadline):
    rows=[contours._track_row(t) for t in tracks]
    result,_=regions._profiles(board,rows,'chamfer45',1000,margin,4,deadline)
    return regions.native_poly(result)

def _items(board,proposal):
    live={force._uid(t):t for t in board.GetTracks()};old=[live[u] for u in proposal['retired_track_uuids']]
    incoming=[];token=proposal['source_sha256']+':'+str(proposal['retreat_nm'])
    for index,(a,z) in enumerate(zip(proposal['points_nm'],proposal['points_nm'][1:])):
        t=old[0].Duplicate();t.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,
            POLICY+':'+token+':'+str(proposal['retired_track_uuids'])+':'+str(index)))))
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));incoming.append(t)
    return old,incoming

def plan(source,*,board_hint,retired_track_uuids,retreat_nm=1000000,allow_locked_source=False):
    require(type(board_hint) is str and bool(board_hint) and type(allow_locked_source) is bool
        and type(retreat_nm) is int and 50000<=retreat_nm<=2000000,
        'bounded_explicit_local_keeper_miter_context_required')
    source=Path(source).resolve();b=pcbnew.LoadBoard(str(source));deadline=time.monotonic()+10.
    ids=ordinary._ids(retired_track_uuids,'local_current_keeper_tracks',2)
    require(len(ids)==2,'two_literal_local_current_source_tracks_required')
    live={force._uid(t):t for t in b.GetTracks()};require(ids<=live.keys(),'actual_local_keeper_source_tracks_required')
    old=[live[u] for u in sorted(ids)];first=old[0];face=int(first.GetLayer());width=first.GetWidth()
    grouped={force._uid(t) for g in b.Groups() for t in g.GetItems()}
    require(all(t.GetClass()=='PCB_TRACK' and not t.GetParentGroup() and force._uid(t) not in grouped
        and not t.HasSolderMask() and (not t.IsLocked() or allow_locked_source) for t in old)
        and len({(t.GetNetCode(),int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked())) for t in old})==1
        and face in (pcbnew.F_Cu,pcbnew.B_Cu), 'plain_uniform_outer_source_process_and_lock_scope_required')
    shared={tuple(first.GetStart()),tuple(first.GetEnd())}&{tuple(old[1].GetStart()),tuple(old[1].GetEnd())}
    require(len(shared)==1,'one_exact_local_source_corner_required');at=next(iter(shared))
    far=[tuple(t.GetEnd()) if tuple(t.GetStart())==at else tuple(t.GetStart()) for t in old]
    vectors=[(p[0]-at[0],p[1]-at[1]) for p in far]
    require(all((x==0)!=(y==0) for x,y in vectors) and sum(x*y for x,y in zip(*vectors))==0,
        'literal_cardinal_right_angle_required')
    require(all(math.hypot(*v)>retreat_nm+width for v in vectors)
        and 2*retreat_nm>width+math.isqrt(2*20000**2)+1,'visible_full_width_miter_and_retained_far_tails_required')
    typed=full.plan(b,source,board_hint=board_hint,retired_track_uuids=sorted(ids),
        max_source_track_mm=32.,max_source_cut_mm=48.)
    import cec_precision_route as precision
    require(first.GetNetname() not in {n for p in precision.derive_coupled_pairs(str(source),board=b)
        for n in (p['p'],p['n'])},'coupled_pair_requires_its_separate_owner')
    request=dict(net=first.GetNetname(),layer=face,at_nm=list(at),source_track_uuids=sorted(ids))
    owners=corners._retained_corner_keepers(b,request,first,deadline)
    require(len(owners)==1 and owners[0]['actual_native_fill'],'one_actual_filled_source_keeper_at_corner_required')
    zone=next(z for z in b.Zones() if force._uid(z)==owners[0]['zone_uuid']);config=refresh._configuration(zone)
    parameters=dict(required_width_nm=typed['full_current_floor_nm'],clearance_nm=config['clearance_nm'],
        min_thickness_nm=config['min_thickness_nm'],contour_style='chamfer45',contour_grid_nm=1000,
        envelope_margin_nm=1000,fill_envelope_margin_nm=4)
    refresh._settings_valid(config,parameters)
    require(not config['locked'] or allow_locked_source,'explicit_local_keeper_lock_scope_required')
    require(config['min_thickness_nm']<width,'source_keeper_minimum_feature_must_fit_full_width')
    radius=retreat_nm+width+10000
    bounds=[((at[0]-radius)//1000)*1000,((at[1]-radius)//1000)*1000,
        -((-(at[0]+radius))//1000)*1000,-((-(at[1]+radius))//1000)*1000]
    patch=box_poly(bounds)
    for i in range(zone.Outline().OutlineCount()):
        for h in range(zone.Outline().HoleCount(i)):
            ring=zone.Outline().Hole(i,h);window=pcbnew.SHAPE_POLY_SET();window.NewOutline()
            for k in range(ring.PointCount()):
                point=ring.CPoint(k);window.Append(point.x,point.y)
            window.BooleanIntersection(patch)
            require(not window.OutlineCount(),'local_keeper_window_requires_separate_explicit_ownership')
    # A local splice must not silently move a branch, terminal or another
    # source conductor. Only the two exact straight source tails may cross
    # this window. All physical holes and foreign clearances remain subject
    # to native construction/receiving; no new barrel or pad is authorized.
    peers=[*b.GetTracks(),*(p for fp in b.GetFootprints() for p in fp.Pads())]
    require(len(peers)<=16384,'local_keeper_contact_inventory_bound')
    for item in peers:
        if force._uid(item) in ids or item.GetNetCode()!=first.GetNetCode() or not item.IsOnLayer(face):continue
        p=contacts.native_contact_polygon(item,face,deadline);p.BooleanIntersection(patch)
        require(not p.OutlineCount(),'local_keeper_window_contains_another_same_net_terminal_or_branch')
    original=zone.Outline().CloneDropTriangulation();local=original.CloneDropTriangulation();local.BooleanIntersection(patch)
    require(bool(local.OutlineCount()),'positive_source_keeper_local_material_required')
    # The actual old local contour, not its name, must be wholly contained
    # by a <=4um outward, grid-bound envelope of these full-rated tracks.
    # This only bounds ownership of the old margin; it grants no neckdown,
    # capacity or clearance tolerance and never alters remote pour geometry.
    covered=local.CloneDropTriangulation();covered.BooleanSubtract(profile(b,old,4000,deadline))
    require(not covered.OutlineCount(),'local_keeper_carries_material_beyond_selected_source_path')
    inside=[(at[0]+(retreat_nm if v[0]>0 else -retreat_nm if v[0]<0 else 0),
        at[1]+(retreat_nm if v[1]>0 else -retreat_nm if v[1]<0 else 0)) for v in vectors]
    points=[list(far[0]),list(inside[0]),list(inside[1]),list(far[1])];paths._points(points)
    q=dict(policy=POLICY,source=str(source),source_sha256=force._hash(source),board_hint=board_hint,
        authority_sha256=force._hash(Path(__file__).resolve()),retired_track_uuids=sorted(ids),
        source_corner_nm=list(at),retreat_nm=retreat_nm,allow_locked_source=allow_locked_source,
        full_current_plan=typed,source_zone_configuration=config,zone_uuid=force._uid(zone),
        patch_bounds_nm=bounds,points_nm=points,full_source_current_or_width_reduced=False,
        source_generation_history_inferred=False,remote_keeper_geometry_changed=False,release_authority=False)
    old,new=_items(b,q);gap=max(config['clearance_nm'],b.GetDesignSettings().m_MinClearance)
    require(all(fr._edge_leg_clear(b,t.GetStart(),t.GetEnd(),(width+1)//2) and
        fr._tap_foreign_clear(b,t.GetStart(),t.GetEnd(),width,face,gap,{first.GetNetCode()}) for t in new),
        'native_full_width_local_miter_clearance_or_edge_refused')
    proof=contacts.preserve_contacts(b,old,[t.GetEffectiveShape(face) for t in new],layer_id=face,
        net_code=first.GetNetCode(),deadline_monotonic=deadline,max_items=16384)
    require(proof['ok'],'local_current_miter_loses_source_contact')
    generated=profile(b,new,1000,deadline);generated.BooleanIntersection(patch)
    desired=original.CloneDropTriangulation();desired.BooleanSubtract(patch);desired.BooleanAdd(generated);desired.Simplify()
    outside=desired.CloneDropTriangulation();outside.BooleanSubtract(patch)
    retained=original.CloneDropTriangulation();retained.BooleanSubtract(patch)
    a=outside.CloneDropTriangulation();a.BooleanSubtract(retained)
    z=retained.CloneDropTriangulation();z.BooleanSubtract(outside)
    require(not a.OutlineCount() and not z.OutlineCount(),'local_miter_changed_remote_keeper_material')
    # New copper IN the window must be enclosed. Outside it, the new tails
    # must be literal subsets of the old straight capsules. Do not demand
    # that a remote historical keeper window enclose an unchanged trace:
    # that would defeat exact remote-window preservation for no local reason.
    old_material=pcbnew.SHAPE_POLY_SET()
    for t in old:old_material.BooleanAdd(contours._native_capsule(t))
    for t in new:
        remaining=contours._native_capsule(t);remaining.BooleanIntersection(patch);remaining.BooleanSubtract(desired)
        require(not remaining.OutlineCount(),'new_full_width_tracks_not_enclosed_by_actual_keeper')
        remote=contours._native_capsule(t);remote.BooleanSubtract(patch);remote.BooleanSubtract(old_material)
        require(not remote.OutlineCount(),'local_miter_added_track_material_outside_owned_window')
    q['desired_zone_regions_nm']=regions.canonical_native_regions(desired)
    q['source_zone_regions_nm']=regions.canonical_native_regions(original)
    q['native_source_contacts']=proof
    require(time.monotonic()<deadline,'local_keeper_plan_deadline')
    return json.loads(json.dumps(q,allow_nan=False))

def args(q):
    return {k:q[k] for k in ('board_hint','retired_track_uuids','retreat_nm','allow_locked_source')}

def construct(proposal):
    require(plan(proposal['source'],**args(proposal))==proposal,'stale_or_forged_local_current_keeper_plan')
    b=pcbnew.LoadBoard(proposal['source']);old,new=_items(b,proposal)
    zone=next(z for z in b.Zones() if force._uid(z)==proposal['zone_uuid'])
    for t in new:b.Add(t)
    discard_items(b,old);zone.Outline().RemoveAllContours()
    zone.Outline().BooleanAdd(regions.native_poly(proposal['desired_zone_regions_nm']))
    selected=pcbnew.ZONES();selected.append(zone)
    zone_fill.compile_selected(b,selected,initialize_selected=True);additive._ground_refill(b)
    return b,dict(retired_track_uuids=proposal['retired_track_uuids'],
        added_native_uuids=sorted(force._uid(t) for t in new),modified_zone_uuids=[proposal['zone_uuid']],
        no_new_holes_or_vias=True,remote_source_keeper_material_exact=True)

def receive(source,candidate,proposal,*,board_hint):
    r=dict(ok=False,complete=False,errors=[],current_qualified=False,fab_ready=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        require(source!=candidate and board_hint==proposal['board_hint'] and str(source)==proposal['source'],
            'distinct_source_bound_local_keeper_candidate_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        expected,made=construct(proposal)
        with tempfile.TemporaryDirectory(prefix='cec-local-current-keeper-') as work:
            path=force._copy_family(source,Path(work)/'expected');field._save_field_snapshot(expected,path)
            require(syntax._freeze(additive._nodes(path)[0])==syntax._freeze(additive._nodes(candidate)[0]),
                'entire_saved_local_keeper_reconstruction_differs')
        require(force._sidecars(source)==force._sidecars(candidate),'local_keeper_changed_source_companions')
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        old={force._uid(t):t for t in parent.GetTracks()};new={force._uid(t):t for t in child.GetTracks()}
        require(full._model(parent,source,proposal['full_current_plan']['net'],board_hint)==
            full._model(child,candidate,proposal['full_current_plan']['net'],board_hint),'local_keeper_changed_current_authority')
        with force._thermal_hint(board_hint):
            guard=full.capture.Guard(parent,source,net=proposal['full_current_plan']['net'],board_hint=board_hint,timeout_s=10.)
        for uid in made['added_native_uuids']:
            t=new[uid];require(guard(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth(),int(t.GetLayer())),
                'local_keeper_original_source_current_capture_refused')
        cut=set(made['retired_track_uuids']);owned={proposal['zone_uuid']}
        boundary=pcbnew.LoadBoard(str(source));discard_items(boundary,[z for z in boundary.Zones() if force._uid(z) in owned])
        source_tracks={force._uid(t):t for t in boundary.GetTracks()}
        r['restored_original_boundaries']=ordinary._boundaries(boundary,child,[source_tracks[u] for u in cut],time.monotonic()+10.)
        before=ordinary._partition(parent,time.monotonic()+10.,retired_uuids=cut|owned)
        after=ordinary._partition(child,time.monotonic()+10.,retained_keys=set().union(*before))
        require({frozenset(p) for p in before}=={frozenset(p) for p in after},'local_keeper_changed_original_native_partitions')
        r['actual_visible_native_material_removed']=existing._visible(parent,child,
            dict(request=dict(net=proposal['full_current_plan']['net'],layer=proposal['full_current_plan']['layer_id']),
                full_current_plan=proposal['full_current_plan'],keeper_contexts=[dict(zone_uuid=proposal['zone_uuid'])]),
            made['added_native_uuids'],time.monotonic()+10.)
        # A raw land difference inside a substrate cutout or physical bore
        # is not removed copper. Reuse the independently tested, conservative
        # old-track lower bound clipped to actual substrate and ALL drills.
        r['actual_drilled_substrate_material_removed']=actual_material.removed_material(parent,child,sorted(cut))
        require(r['actual_drilled_substrate_material_removed']['positive_material_removed'] and
            r['actual_drilled_substrate_material_removed']['actual_substrate_intersection_and_global_bores_subtracted'],
            'positive_drilled_substrate_copper_removal_required')
        first=quality.analyze_board(parent,min_open_angle_deg=134.999);last=quality.analyze_board(child,min_open_angle_deg=134.999)
        require(last['issue_count']<first['issue_count'] and last['non_octilinear_count']<=first['non_octilinear_count'],
            'local_keeper_requires_real_bend_progress_without_diagonal_regression')
        require(epoch==force._code_identity() and families==[force._family(p,board_hint) for p in (source,candidate)],
            'local_keeper_source_family_or_code_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            source_current_width_and_contacts_rederived=True,whole_saved_reconstruction_exact=True,
            remote_keeper_material_exact=True,no_new_barrels=True,source_family_and_code_unchanged=True,
            removed_bend_flags=first['issue_count']-last['issue_count'],
            actual_trace_length_removed_mm=(sum(old[u].GetLength() for u in cut)-sum(new[u].GetLength() for u in made['added_native_uuids']))/1e6,
            full_current_ground_kelvin_field_DRC_and_release_receiving_still_required=True,manifest=made)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
