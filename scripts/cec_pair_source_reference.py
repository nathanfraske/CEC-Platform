"""Source-owned return context for bounded fixed-port pair shortening.

Retained SAME-NET native copper is not a new reference deficit. A historical
plated signal-terminal void may be re-entered only when an independent native
refill attributes that bounded void to the SAME unchanged endpoint barrel,
the route stays inside its original centreline hull, and exact source-plane
centreline loss does not increase. No ground fill is added to the candidate.

This corresponds to the own-net pad/via-void distinction of return-path DRC,
not a blanket plane-gap exclusion. It grants no EM, via-current or release
qualification. Existing strict local-deficit receiving is left intact.
"""
import math,time,json,copy,tempfile
from collections import Counter
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_exact_polygon_cover as exact
import cec_exact_reference_length as lengths
import cec_fab_profile as fab
import cec_force_current as force
import cec_pair_local_reference_refinement as owner


def _counterfactual_ground(source,source_root,endpoint,reference,deadline):
    """Compile a serialized private shadow, never detach a borrowed pad.

    This also keeps the long-lived native session out of the FOOTPRINT.Remove
    ownership path. Exactly one declared endpoint node may be absent; every
    other source node and project sidecar is copied unchanged.
    """
    root=copy.deepcopy(source_root);uid=force._uid(endpoint)
    def identity(node):
        return next((str(row[1]).strip('"') for row in node[1:]
            if isinstance(row,list) and len(row)==2 and row[0]=='uuid'),None)
    removed=0
    if endpoint.GetClass()=='PCB_VIA':
        rows=[]
        for node in root[1:]:
            if isinstance(node,list) and node and node[0]=='via' and identity(node)==uid:removed+=1
            else:rows.append(node)
        root=[root[0],*rows]
    else:
        parent=force._uid(endpoint.GetParentFootprint())
        for node in root[1:]:
            if not isinstance(node,list) or not node or node[0]!='footprint' or identity(node)!=parent:continue
            rows=[]
            for child in node[1:]:
                if isinstance(child,list) and child and child[0]=='pad' and identity(child)==uid:removed+=1
                else:rows.append(child)
            node[:]=[node[0],*rows]
    if removed!=1:raise ValueError('one_literal_counterfactual_source_endpoint_required')
    exact._check(deadline)
    with tempfile.TemporaryDirectory(prefix='cec-source-endpoint-void-') as tmp:
        shadow=force._copy_family(source,Path(tmp)/'family')
        shadow.write_text(additive._render(root)+'\n',encoding='utf-8')
        private=pcbnew.LoadBoard(str(shadow));additive._ground_refill(private)
        return _ground(private,reference,deadline)[0]


def _hull(points):
    points=sorted(set(map(tuple,points)))
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lower=[];upper=[]
    for p in points:
        while len(lower)>=2 and cross(lower[-2],lower[-1],p)<=0:lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper)>=2 and cross(upper[-2],upper[-1],p)<=0:upper.pop()
        upper.append(p)
    return lower[:-1]+upper[:-1]


def _hull_contains(hull,p):
    if len(hull)<3:return False
    return all((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])>=0
        for a,b in zip(hull,hull[1:]+hull[:1]))


def _shape(item,face,deadline):
    poly=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,face,0,1000,pcbnew.ERROR_OUTSIDE)
    identity=owner._literal_native_contact_polygon_identity(poly,deadline)
    return poly,identity


def _ground(board,face,deadline):
    poly=pcbnew.SHAPE_POLY_SET();witnesses={}
    for z in board.Zones():
        exact._check(deadline)
        if z.GetIsRuleArea() or z.GetNetname()!='GND' or not z.IsOnLayer(face):continue
        if not z.IsFilled() or not z.HasFilledPolysForLayer(face):raise ValueError('actual_source_reference_fill_required')
        fill=z.GetFilledPolysList(face);witnesses[force._uid(z)]=owner._reference_identity(fill,deadline)
        poly.BooleanAdd(fill)
    if not witnesses or not poly.OutlineCount():raise ValueError('positive_source_ground_reference_required')
    return poly,witnesses


def _endpoint_scope(board,item,face,reference,ports,width,deadline):
    floor=board.GetDesignSettings();layers=list(map(int,board.GetEnabledLayers().CuStack()))
    if item.GetClass()=='PAD':
        if (item.GetAttribute()!=pcbnew.PAD_ATTRIB_PTH or not item.HasHole()
                or not item.IsOnLayer(face) or not item.IsOnLayer(reference)
                or min(item.GetDrillSize().x,item.GetDrillSize().y)<=0):return False
        land=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(land,face,0,1000,pcbnew.ERROR_INSIDE)
        owner._literal_native_contact_polygon_identity(land,deadline)
        for p in ports:
            disk=pcbnew.PCB_TRACK(board);disk.SetStart(pcbnew.VECTOR2I(*p));disk.SetEnd(pcbnew.VECTOR2I(*p));disk.SetWidth(width)
            poly=pcbnew.SHAPE_POLY_SET();disk.TransformShapeToPolygon(poly,face,0,1000,pcbnew.ERROR_OUTSIDE)
            poly.BooleanSubtract(land)
            if not poly.OutlineCount():return True
        return False
    if (item.GetClass()!='PCB_VIA' or item.GetViaType()!=pcbnew.VIATYPE_THROUGH
            or item.TopLayer()!=pcbnew.F_Cu or item.BottomLayer()!=pcbnew.B_Cu or not item.IsOnLayer(face)
            or item.GetDrillValue()<floor.m_MinThroughDrill
            or any(item.GetWidth(l)<floor.m_ViasMinSize
                or item.GetWidth(l)-item.GetDrillValue()<2*floor.m_ViasMinAnnularWidth for l in layers)):
        return False
    radius=item.GetWidth(face)-width
    return radius>=0 and any(4*sum((p[i]-item.GetPosition()[i])**2 for i in (0,1))<=radius*radius for p in ports)


def reference_deficit(source,candidate,parent,child,old_tracks,new_tracks,kernels,*,board_hint,deadline):
    """Independent positive source-context proof, never inferred from a flag."""
    source,candidate=map(Path,(source,candidate));face=int(old_tracks[0].GetLayer());name=fab.COPPER_LAYER_IDS[face]
    with force._thermal_hint(board_hint):
        profile=fab.active_profile_name(parent,hint=board_hint);roles=fab.get_profile(profile)['roles'] if profile else None
    names=fab.COPPER_LAYERS
    if not roles or 'SIG' not in roles[names.index(name)]:raise ValueError('source_context_requires_existing_signal_face')
    refs=[n for i,n in enumerate(names) if abs(i-names.index(name))==1 and roles[i]=='GND']
    if len(refs)!=1:raise ValueError('unique_existing_source_ground_reference_required')
    ref=int(parent.GetLayerID(refs[0]));ground,zone_ids=_ground(parent,ref,deadline)
    if zone_ids!=_ground(child,ref,deadline)[1]:raise ValueError('source_context_reference_planes_changed')
    source_root,old_nodes=additive._nodes(source);_,new_nodes=additive._nodes(candidate)
    retired=old_nodes.keys()-new_nodes.keys();items=[*parent.GetTracks(),*(p for f in parent.GetFootprints() for p in f.Pads())]
    if len(items)>16384:raise ValueError('source_context_native_inventory_bound')
    # Only the same native compiler, original ground sheets and literal
    # endpoint vias own the diagnostic aperture. A stale fill cannot be
    # 'repaired' as a side effect of this comparison.
    baseline=None;recovery_cache={};records=[];clearance_reader=owner.fr._foreign_clearance_resolver(parent)
    ground_polygons=exact.native_polygons(ground)
    for old_rows,fresh in kernels:
        if int(old_rows[0].GetLayer())!=face:continue
        exact._check(deadline);net=old_rows[0].GetNetname()
        if (any(t.GetNetname()!=net or int(t.GetLayer())!=face for t in old_rows+fresh)
                or {t.GetWidth() for t in old_rows+fresh}!={old_rows[0].GetWidth()}):
            raise ValueError('same_width_native_source_kernel_context_required')
        points=owner._chain(old_rows);new_points=owner._chain(fresh)
        own_old=[t for t in old_tracks if t.GetNetname()==net]
        support=ground_polygons+exact.native_polygons(owner._capsules(own_old,face,deadline))
        contacts=[];endpoints=[]
        for item in items:
            exact._check(deadline);uid=force._uid(item)
            if uid in retired or item.GetNetname()!=net or not item.IsOnLayer(face):continue
            if not any(t.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face),0) for t in fresh):continue
            node=force._uid(item.GetParentFootprint()) if item.GetClass()=='PAD' else uid
            if node not in old_nodes or node not in new_nodes or syntax._freeze(old_nodes[node])!=syntax._freeze(new_nodes[node]):
                raise ValueError('literal_unchanged_source_contact_copper_required')
            poly,identity=_shape(item,face,deadline);support+=exact.native_polygons(poly)
            contacts.append(dict(uuid=uid,kind=item.GetClass(),native_polygon=identity))
            if _endpoint_scope(parent,item,face,ref,[points[0],points[-1]],old_rows[0].GetWidth(),deadline):endpoints.append(item)
        subject=exact.native_polygons(owner._capsules(fresh,face,deadline))
        direct=exact.cover(subject,support,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        record=dict(net=net,layer=face,source_track_uuids=sorted(force._uid(t) for t in old_rows),
            incoming_track_uuids=sorted(force._uid(t) for t in fresh),retained_same_net_native_copper=contacts,
            exact_retained_context_cover=direct,existing_endpoint_voids=[])
        if direct['ok'] and direct['complete']:
            record['method']='exact_unchanged_source_copper_and_reference_cover';records.append(record);continue
        if direct['errors']:raise ValueError('exact_source_context_cover_unknown:'+str(direct['errors']))
        if not 1<=len(endpoints)<=2:raise ValueError('bounded_actual_same_net_source_endpoint_barrel_required')
        hull=_hull(points)
        if not all(_hull_contains(hull,p) for p in new_points):raise ValueError('endpoint_void_shortening_must_not_expand_source_centerline_hull')
        if baseline is None:
            baseline=pcbnew.LoadBoard(str(source));additive._ground_refill(baseline)
            if zone_ids!=_ground(baseline,ref,deadline)[1]:raise ValueError('source_reference_is_not_exact_native_compiler_fill')
        for endpoint in endpoints:
            uid=force._uid(endpoint);key=(uid,ref)
            if key not in recovery_cache:
                recovered=_counterfactual_ground(source,source_root,endpoint,ref,deadline);recovered.BooleanSubtract(ground)
                if not recovered.OutlineCount():raise ValueError('source_endpoint_via_has_no_attributable_reference_void')
                zones=[z for z in parent.Zones() if force._uid(z) in zone_ids]
                clearance=max(int(parent.GetDesignSettings().m_MinClearance),clearance_reader(endpoint,ref),
                    *[clearance_reader(z,ref) for z in zones])
                # Native min-thickness cleanup and tessellation are ONLY a
                # finite attribution bound; actual recovered polygons, not
                # this circle, must cover every disputed new point.
                inflation=clearance+max(int(z.GetMinThickness()) for z in zones)+1000
                origin=tuple(endpoint.GetPosition())
                if endpoint.GetClass()=='PCB_VIA':body_radius=(int(endpoint.GetWidth(ref))+1)//2;limit=1000000
                else:
                    box=endpoint.GetEffectiveShape(ref).BBox()
                    distances=[sum((p[i]-origin[i])**2 for i in (0,1)) for p in
                        ((box.GetX(),box.GetY()),(box.GetX(),box.GetBottom()),(box.GetRight(),box.GetY()),(box.GetRight(),box.GetBottom()))]
                    body_radius=math.isqrt(max(distances))+1;limit=2000000
                radius=body_radius+inflation
                if radius>limit:raise ValueError('source_endpoint_void_attribution_reach_bound')
                complete_recovery=owner._reference_identity(recovered,deadline)
                # Refilling after removing a void can also change distant
                # island cleanup or fracture representation. NONE of that
                # distant material is admitted. Intersect the diagnostic
                # recovery with a conservative, source-sized local envelope;
                # the recovery, not the envelope alone, must support the cut.
                local=pcbnew.SHAPE_POLY_SET()
                endpoint.TransformShapeToPolygon(local,ref,inflation,1000,pcbnew.ERROR_INSIDE)
                owner._literal_native_contact_polygon_identity(local,deadline)
                recovered.BooleanIntersection(local)
                if not recovered.OutlineCount():raise ValueError('no_local_source_endpoint_void_attribution')
                for polygon in exact.native_polygons(recovered):
                    if any(sum((p[i]-origin[i])**2 for i in (0,1))>radius*radius for ring in polygon for p in ring):
                        raise ValueError('native_refill_recovers_nonlocal_reference_material')
                recovery_cache[key]=(exact.native_polygons(recovered),dict(endpoint_uuid=uid,endpoint_kind=endpoint.GetClass(),source_position_nm=list(origin),
                    reference_face=refs[0],native_compiler_recovered_void=owner._reference_identity(recovered,deadline),
                    complete_diagnostic_recovery_identity=complete_recovery,
                    bounded_attribution_radius_nm=radius,distant_diagnostic_recovery_not_authorized=True,
                    no_area_threshold_or_numeric_waiver_used=True,diagnostic_only_not_candidate_ground_fill=True))
            poly,witness=recovery_cache[key];support+=poly;record['existing_endpoint_voids'].append(witness)
        result=exact.cover(subject,support,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if not result['ok'] or not result['complete']:
            raise ValueError('new_reference_deficit_outside_unchanged_source_endpoint_void:'+name+':'+net+':'+
                json.dumps(dict(witness=result.get('uncovered_witness'),errors=result['errors']),sort_keys=True))
        def strokes(rows):return [dict(start_nm=list(t.GetStart()),end_nm=list(t.GetEnd())) for t in rows]
        before=lengths.measure(strokes(old_rows),ground_polygons,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        after=lengths.measure(strokes(fresh),ground_polygons,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        comparison=lengths.nonincreasing(before,after)
        if not comparison['ok']:raise ValueError('source_endpoint_void_unreferenced_centerline_not_proved_nonincreasing')
        record.update(method='actual_unchanged_source_endpoint_via_void_shortening',exact_context_and_endpoint_void_cover=result,
            source_centerline_hull=[list(p) for p in hull],reference_length_before_after=[before,after],
            exact_reference_length_comparison=comparison)
        records.append(record)
    exact._check(deadline)
    return dict(ok=True,complete=True,method='exact_saved_same_net_copper_and_attributable_unchanged_endpoint_voids',
        signal_face=name,reference_face=refs[0],exact_source_reference_zone_identities=zone_ids,kernels=records,
        native_candidate_reference_fill_unchanged=True,new_plane_holes=0,new_vias=0,
        new_unattributed_reference_deficit=False,existing_own_via_voids_disclosed_not_filled=True,
        diagnostic_refills_never_saved_to_candidate=True,numeric_tolerance_nm=0,area_omission_threshold=0,
        existing_vertical_via_return_current_and_EM_debt_not_qualified=True,
        pair_qualified=False,release_authority=False)
