"""Retire a quiet SMD Ground collection span backed by real retained copper.

This is not general Ground-mesh thinning. Each actual touched quiet-device
land and track contact needs a full source-class-width retained surface path
to the SAME unchanged, source-qualified reference barrel. Both saved Ground
references, all fills, actual bores, every other native node and every known
local return stay owned. No new current, shielding, thermal or fab rating.
"""
import json,math,tempfile,time
from pathlib import Path
import pcbnew
import cec_additive_portal_compaction as portal
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_preservation as returns
import cec_ground_return_shortcut as reference
import cec_native_fill_geometry as fills
import cec_native_ground_span_reflow as span
import cec_native_track_partition as partition
import cec_native_track_ports as ports
import cec_ordinary_route_receiving as ordinary
import cec_return_escape as surface
import cec_route_corner_contacts as copper
import cec_route_quality as quality
import cec_stale_local_ground_via as stale
from cec_native_items import discard_items


def _tick(deadline):
    if time.monotonic()>=deadline:raise ValueError('reference_backed_ground_cut_deadline')


def _settings(ids,locks,hint,timeout_s):
    if (type(ids) not in (list,tuple) or not 1<=len(ids)<=8 or len(set(ids))!=len(ids)
            or any(type(u) is not str or not u for u in ids)
            or type(locks) not in (list,tuple) or len(set(locks))!=len(locks)
            or any(type(u) is not str or not u for u in locks) or not set(locks)<=set(ids)
            or type(hint) is not str or not hint or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('explicit_bounded_reference_backed_ground_cut_required')


def _zone_identity(board,deadline):
    result={}
    for z in board.Zones():
        _tick(deadline)
        if z.GetIsRuleArea():continue
        for face in board.GetEnabledLayers().CuStack():
            if z.IsOnLayer(face) and z.HasFilledPolysForLayer(face):
                result[force._uid(z),int(face)]=fills.identity(z.GetFilledPolysList(face),deadline)
    return result


def _track_sites(a,b):
    first,last=tuple(a.GetStart()),tuple(a.GetEnd());left,right=tuple(b.GetStart()),tuple(b.GetEnd())
    sites={p for p in (first,last,left,right) if ports.on_centerline(a,p) and ports.on_centerline(b,p)}
    sites.update(partition._contact(first,last,left,right));sites.update(partition._contact(left,right,first,last))
    return sorted(sites)


def _references(board,root,deadline):
    records=[]
    for uid,face in reference._reference_contacts(board,root):
        _tick(deadline)
        zone=next(z for z in board.Zones() if force._uid(z)==uid)
        annulus=copper.native_contact_polygon(root,face,deadline)
        hole=pcbnew.SHAPE_POLY_SET();root.GetEffectiveHoleShape().TransformToPolygon(hole,1,pcbnew.ERROR_OUTSIDE)
        annulus.BooleanSubtract(hole);annulus.BooleanIntersection(zone.GetFilledPolysList(face))
        if not annulus.OutlineCount():raise ValueError('positive_actual_annular_reference_contact_required')
        digest,vertices=fills.identity(annulus,deadline)
        records.append(dict(zone_uuid=uid,layer_id=face,annular_contact_sha256=digest,annular_contact_vertices=vertices))
    if len({q['layer_id'] for q in records})<2:raise ValueError('two_declared_actual_ground_references_required')
    return records


def _sheet(board,retired,face,root,anchors,width,deadline):
    points=[*anchors,tuple(root.GetPosition())];margin=width+100000
    xs,ys=zip(*points);box=pcbnew.BOX2I(pcbnew.VECTOR2I(min(xs)-margin,min(ys)-margin),
        pcbnew.VECTOR2I(max(xs)-min(xs)+2*margin,max(ys)-min(ys)+2*margin))
    window=pcbnew.SHAPE_POLY_SET();window.NewOutline()
    for x,y in ((box.GetLeft(),box.GetTop()),(box.GetRight(),box.GetTop()),
                (box.GetRight(),box.GetBottom()),(box.GetLeft(),box.GetBottom())):window.Append(x,y)
    sheet=pcbnew.SHAPE_POLY_SET();owners=[];zone_count=0;retained_tracks=[]
    items=[*board.GetTracks(),*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.Zones()]
    for item in items:
        _tick(deadline);uid=force._uid(item)
        if uid in retired or item.GetNetname()!='GND' or not item.IsOnLayer(face):continue
        if not item.GetBoundingBox().Intersects(box):continue
        if item.GetClass()=='ZONE':
            if item.GetIsRuleArea():continue
            if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                raise ValueError('actual_saved_surface_ground_fill_required')
            zone_count+=1
        elif item.GetClass()=='PCB_TRACK':retained_tracks.append(item)
        poly=copper.native_contact_polygon(item,face,deadline).CloneDropTriangulation()
        poly.BooleanIntersection(window);sheet.BooleanAdd(poly);owners.append(uid)
    if not zone_count and not retained_tracks:
        raise ValueError('actual_retained_surface_route_or_fill_required')
    # The one unchanged qualified terminal barrel is credited as its outer
    # landing before the common bore. Every OTHER real bore remains a void.
    # This is a surface-width witness, never barrel ampacity qualification.
    bores=[];voids=pcbnew.SHAPE_POLY_SET()
    for item in items:
        _tick(deadline)
        if (force._uid(item)==force._uid(root) or not item.IsOnLayer(face)
                or not item.GetBoundingBox().Intersects(box)):continue
        drilled=item.GetClass()=='PCB_VIA' or item.GetClass()=='PAD' and item.HasHole()
        if drilled:
            hole=pcbnew.SHAPE_POLY_SET();item.GetEffectiveHoleShape().TransformToPolygon(hole,1,pcbnew.ERROR_OUTSIDE)
            sheet.BooleanSubtract(hole);voids.BooleanAdd(hole);bores.append(force._uid(item))
    digest,vertices=fills.identity(sheet,deadline)
    return sheet,voids,retained_tracks,dict(native_retained_surface_sha256=digest,vertices=vertices,
        retained_native_uuids=sorted(owners),other_actual_bores_subtracted=sorted(bores),
        actual_saved_surface_fills=zone_count,actual_retained_surface_tracks=len(retained_tracks),
        unchanged_qualified_root_outer_landing_uuid=force._uid(root),polygon_error_nm=1)


def _paths(board,sheet,voids,retained_tracks,anchors,root,face,width,maximum_length_nm,deadline):
    target=tuple(root.GetPosition());proofs=[]
    for anchor in sorted(anchors):
        _tick(deadline)
        if anchor==target:continue
        choices=fr._canonical_45_xy_paths(anchor,target)
        for points in choices:
            if any(not quality.is_canonical_stroke(a,b,tolerance_nm=0) for a,b in zip(points,points[1:])):continue
            if sum(math.dist(a,b) for a,b in zip(points,points[1:]))>maximum_length_nm:continue
            route=pcbnew.SHAPE_POLY_SET();all_capsules=pcbnew.SHAPE_POLY_SET();exact=[]
            for a,b in zip(points,points[1:]):
                _tick(deadline)
                edge=pcbnew.PCB_TRACK(board);edge.SetNet(board.FindNet('GND'));edge.SetLayer(face);edge.SetWidth(width)
                edge.SetStart(pcbnew.VECTOR2I(*a));edge.SetEnd(pcbnew.VECTOR2I(*b))
                # Exact source-aligned capsule containment avoids inventing
                # a 1-nm width waiver at tessellated round caps. Split only at
                # literal retained stroke endpoints ON the canonical line.
                sites={a,b}|{tuple(p) for t in retained_tracks for p in (t.GetStart(),t.GetEnd())
                    if ports.on_centerline(edge,tuple(p))}
                sites=sorted(sites,key=lambda p:(p[0]-a[0])**2+(p[1]-a[1])**2)
                for left,right in zip(sites,sites[1:]):
                    _tick(deadline);edge.SetStart(pcbnew.VECTOR2I(*left));edge.SetEnd(pcbnew.VECTOR2I(*right))
                    poly=pcbnew.SHAPE_POLY_SET();edge.TransformShapeToPolygon(poly,face,0,1,pcbnew.ERROR_OUTSIDE)
                    all_capsules.BooleanAdd(poly)
                    owned=portal._covered_by_source(edge,retained_tracks)
                    if owned:exact.append(dict(points_nm=[list(left),list(right)],native_retained_track_uuid=owned))
                    else:route.BooleanAdd(poly)
            route.BooleanSubtract(sheet)
            all_capsules.BooleanIntersection(voids)
            if not route.OutlineCount() and not all_capsules.OutlineCount():
                proofs.append(dict(anchor_nm=list(anchor),points_nm=[list(p) for p in points],
                    full_source_class_width_nm=width,exact_retained_native_capsules=exact,
                    remaining_outside_capsules_in_actual_retained_inside_copper=True,
                    every_other_actual_bore_excluded=True));break
        else:raise ValueError('full_width_retained_surface_path_to_same_reference_barrel_unproved')
    return proofs


def _prepare(source,*,board_hint,retired_track_uuids,allow_locked_track_uuids=(),timeout_s=10.):
    _settings(retired_track_uuids,allow_locked_track_uuids,board_hint,timeout_s)
    deadline=time.monotonic()+timeout_s;source=Path(source).resolve()
    epoch=force._code_identity();family=force._family(source,board_hint)
    before=pcbnew.LoadBoard(str(source));tracks=list(before.GetTracks());pads=[p for fp in before.GetFootprints() for p in fp.Pads()]
    if len(tracks)+len(pads)+len(list(before.Zones()))>16384:raise ValueError('reference_ground_native_inventory_bound')
    live={force._uid(t):t for t in tracks};cut=set(retired_track_uuids);locks=set(allow_locked_track_uuids)
    if not cut<=live.keys():raise ValueError('literal_reference_ground_cut_missing')
    selected=[live[u] for u in sorted(cut)];face=int(selected[0].GetLayer());width=int(selected[0].GetWidth())
    floor=max(200000,int(before.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(before,'GND')['width']))
    grouped={force._uid(i) for g in before.Groups() for i in g.GetItems()}
    _,nodes=additive._nodes(source)
    grouped.update(u for n in nodes.values() if n[0]=='group' for u in additive._members(n))
    if (face not in (pcbnew.F_Cu,pcbnew.B_Cu) or not floor<=width<=350000
            or locks!={force._uid(t) for t in selected if t.IsLocked()}
            or any(t.GetClass()!='PCB_TRACK' or t.GetNetname()!='GND' or int(t.GetLayer())!=face
                or t.GetWidth()!=width or t.HasSolderMask() or force._uid(t) in grouped
                or t.GetParentGroup() or not 0<t.GetLength()<=12000000 for t in selected)
            or sum(t.GetLength() for t in selected)>12000000):
        raise ValueError('explicit_ungrouped_full_class_quiet_ground_surface_span_required')
    source_points=span._chain(selected);anchors=set();contacts=[];roots=[];land_count=0
    for item in [*tracks,*pads]:
        _tick(deadline);uid=force._uid(item)
        if uid in cut or not item.IsOnLayer(face):continue
        if not any(t.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face),0) for t in selected):continue
        if item.GetNetname()!='GND':raise ValueError('reference_ground_cut_has_foreign_contact')
        if item.GetClass()=='PAD':
            owner=item.GetParentFootprint();model=roles.footprint_contract(owner)
            if (owner.IsDNP() or item.HasHole() or surface.smd_surface_layer(item)!=face or not model
                    or model['pins'].get(str(item.GetNumber())) not in {'ground','power_return'}
                    or 'power_input' not in model['pins'].values()
                    or set(model['pins'].values())&{'switch','power_output'}):
                raise ValueError('actual_manufacturer_quiet_smd_ground_contacts_only')
            # A negative supply tied to literal GND may be a quiet return;
            # its name alone is not switching-current authority. Existing
            # branch owners keep their stricter pin-role guards. This owner
            # needs retained full-class copper and the SAME reference barrel
            # for every actual terminal, including interior contacts.
            anchors.add(tuple(item.GetPosition()));land_count+=1
            contacts.append(dict(uuid=uid,kind='manufacturer_quiet_ground',at_nm=list(item.GetPosition()),manufacturer_contract=model))
        elif item.GetClass()=='PCB_VIA':roots.append(item)
        elif item.GetClass()=='PCB_TRACK':
            if item.GetWidth()<width:raise ValueError('retained_ground_contact_below_source_class_width')
            sites=set(p for t in selected for p in _track_sites(t,item))
            if not sites:raise ValueError('actual_exact_retained_ground_track_contact_site_required')
            anchors.update(sites);contacts.append(dict(uuid=uid,kind='retained_ground_track',sites_nm=[list(p) for p in sorted(sites)]))
        else:raise ValueError('unsupported_reference_ground_contact')
    if not 1<=land_count<=4 or len(roots)!=1 or len(anchors)>16:
        raise ValueError('bounded_quiet_ground_lands_and_one_unchanged_reference_barrel_required')
    root=roots[0];root_uid=force._uid(root)
    if not stale._qualified_bridge(before,root):raise ValueError('source_qualified_reference_ground_barrel_required')
    source_refs=_references(before,root,deadline)
    after=pcbnew.LoadBoard(str(source));discard_items(after,[t for t in after.GetTracks() if force._uid(t) in cut])
    additive._ground_refill(after)
    if _zone_identity(before,deadline)!=_zone_identity(after,deadline):
        raise ValueError('reference_ground_cut_must_not_change_any_saved_fill')
    child_root=next(t for t in after.GetTracks() if force._uid(t)==root_uid)
    if not stale._qualified_bridge(after,child_root) or _references(after,child_root,deadline)!=source_refs:
        raise ValueError('unchanged_reference_barrel_process_or_actual_annular_contacts_lost')
    sheet,voids,retained_tracks,sheet_proof=_sheet(after,cut,face,child_root,anchors,width,deadline)
    paths=_paths(after,sheet,voids,retained_tracks,anchors,child_root,face,width,
        sum(t.GetLength() for t in selected),deadline)
    _tick(deadline)
    if epoch!=force._code_identity() or family!=force._family(source,board_hint):
        raise ValueError('reference_ground_cut_source_or_runtime_changed')
    proposal=json.loads(json.dumps(dict(schema=1,scope='quiet_smd_ground_span_in_retained_full_width_reference_copper',
        source=str(source),source_sha256=force._hash(source),source_family=family,code_identity=epoch,
        board_hint=board_hint,timeout_s=timeout_s,retired_track_uuids=sorted(cut),allow_locked_track_uuids=sorted(locks),
        source_points_nm=source_points,source_width_nm=width,source_layer=face,
        source_length_mm=sum(t.GetLength() for t in selected)/1e6,retained_root_via_uuid=root_uid,
        touched_source_contacts=contacts,saved_reference_plane_contacts=source_refs,
        retained_full_width_surface=sheet_proof,retained_full_width_contact_paths=paths,
        all_native_fills_and_original_reference_barrel_exact=True,
        no_new_current_thermal_shielding_barrel_or_release_qualification=True,
        release_authority=False),allow_nan=False))
    return after,proposal


def plan(source,**params):return _prepare(source,**params)[1]


def construct(source,proposal):
    params={k:proposal[k] for k in ('board_hint','retired_track_uuids','allow_locked_track_uuids','timeout_s')}
    board,fresh=_prepare(source,**params)
    if fresh!=proposal:raise ValueError('stale_or_forged_reference_ground_cut_plan')
    return board


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],current_qualified=False,release_authority=False)
    try:
        source,candidate=(Path(p).resolve() for p in (source,candidate));deadline=time.monotonic()+timeout_s
        _settings(proposal['retired_track_uuids'],proposal['allow_locked_track_uuids'],board_hint,timeout_s)
        if source==candidate or proposal['board_hint']!=board_hint:raise ValueError('distinct_literal_reference_ground_cut_families_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        literal,nodes=additive._nodes(source);actual,_=additive._nodes(candidate)
        cut_nodes=[nodes[u] for u in proposal['retired_track_uuids']]
        if any(n[0]!='segment' for n in cut_nodes):raise ValueError('literal_source_stroke_subtraction_required')
        remaining_literal=[n for n in literal if not any(n is selected for selected in cut_nodes)]
        if syntax._freeze(remaining_literal)!=syntax._freeze(actual):
            raise ValueError('literal_source_minus_only_selected_strokes_differs')
        expected=construct(source,proposal)
        with tempfile.TemporaryDirectory(prefix='cec-reference-ground-cut-') as work:
            path=Path(work)/'exact-source-cut.kicad_pcb';field._save_field_snapshot(expected,path)
            first,_=additive._nodes(path);last,_=additive._nodes(candidate)
            if syntax._freeze(first)!=syntax._freeze(last):raise ValueError('exact_independent_reference_ground_cut_reconstruction_differs')
        if force._sidecars(source)!=force._sidecars(candidate):raise ValueError('reference_ground_cut_sidecars_changed')
        before,after=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        parts=ordinary._partition(before,deadline,retired_uuids=set(proposal['retired_track_uuids']))
        remaining=set().union(*parts);actual=ordinary._partition(after,deadline,retained_keys=remaining)
        if {frozenset(p) for p in parts}!={frozenset(p) for p in actual}:
            raise ValueError('reference_ground_cut_changed_surviving_native_partition')
        local=returns.receive(before,after,timeout_s=max(.001,min(10.,deadline-time.monotonic())))
        if not local['ok'] or not local['complete']:raise ValueError('reference_ground_cut_worsened_known_local_return')
        _tick(deadline)
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('reference_ground_cut_receiving_epoch_changed')
        r.update(ok=True,complete=True,changed=True,code_identity=epoch,source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate),retired_track_uuids=proposal['retired_track_uuids'],added_native_uuids=[],
            retained_root_via_uuid=proposal['retained_root_via_uuid'],removed_ground_trace_mm=proposal['source_length_mm'],
            all_known_ground_returns=local,source_family_and_code_unchanged=True,
            independent_complete_native_source_replay_matched=True,all_surviving_native_partitions_identical=True,
            literal_source_minus_only_selected_strokes_matched=True,
            all_retained_source_tracks_barrels_pads_fills_fields_rules_and_poses_exact=True,
            full_native_current_field_clipped_Kelvin_pair_stack_and_release_receiving_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
