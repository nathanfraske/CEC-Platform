"""Read-only coverage of unequal-width power joins, not a signal-90 waiver.

Both complete native junction caps must be inside literal canonical authored
zone outlines AND actual saved same-net fill on the actual face. A positive
existing current role selects the power observer; it does not qualify the
source widths, source current debt, a barrel or a board for manufacture.
"""
import math,time
import pcbnew
import cec_force_current as force
import cec_full_current_planar_reflow as current
import cec_native_contour_regions as regions
import cec_native_fill_geometry as fills


def require(value,message):
    if not value:raise ValueError(message)


def observe(board,source,track_uuids,at_nm,*,board_hint,timeout_s=2.):
    result=dict(ok=False,complete=False,errors=[],source_mutated=False,
        exposed_hard90_not_present_by_positive_native_material_evidence=False,
        mutation_or_necessity_authority=False,electrical_or_current_or_fabrication_qualified=False,
        current_debt_waived=False,release_authority=False)
    try:
        require(type(timeout_s) in (int,float) and math.isfinite(timeout_s) and 0<timeout_s<=10,
            'bounded_unequal_power_observation_deadline_required')
        deadline=time.monotonic()+timeout_s
        def tick():require(time.monotonic()<deadline,'unequal_power_material_deadline')
        require(type(track_uuids) in (list,tuple) and len(track_uuids)==len(set(track_uuids))==2
            and all(type(u) is str and u for u in track_uuids) and type(at_nm) in (list,tuple)
            and len(at_nm)==2 and all(type(v) is int for v in at_nm),
            'two_literal_source_tracks_and_integer_junction_required')
        tracks=list(board.GetTracks());zones=list(board.Zones());tick()
        require(len(tracks)+len(zones)<=16384,'bounded_unequal_power_native_inventory_required')
        live={force._uid(t):t for t in tracks};old=[live[u] for u in track_uuids]
        require(all(t.GetClass()=='PCB_TRACK' and t.GetNetCode()>0 and not t.HasSolderMask() for t in old)
            and len({(t.GetNetname(),int(t.GetLayer())) for t in old})==1,
            'literal_same_net_face_plain_power_tracks_required')
        widths=sorted(t.GetWidth() for t in old)
        require(0<widths[0]<widths[1] and 500000<=widths[1]<=100000000
            and 2*widths[1]>=3*widths[0],'actual_unequal_wide_power_join_required')
        vectors=[]
        for t in old:
            ends=[tuple(t.GetStart()),tuple(t.GetEnd())]
            require(tuple(at_nm) in ends,'literal_unequal_power_joint_endpoint_required')
            far=ends[1] if ends[0]==tuple(at_nm) else ends[0]
            vectors.append([far[i]-at_nm[i] for i in (0,1)])
        require(all(any(v) and v[0]*v[1]==0 for v in vectors)
            and sum(a*b for a,b in zip(*vectors))==0,'literal_axis_power_right_angle_required')
        net=old[0].GetNetname();face=int(old[0].GetLayer())
        kind,domain,contract=current._model(board,source,net,board_hint);tick()
        require(contract['net']==net,'positive_existing_power_role_required')
        actual=pcbnew.SHAPE_POLY_SET();owners=[]
        for z in zones:
            tick()
            if z.GetIsRuleArea() or z.GetNetname()!=net or not z.IsOnLayer(face):continue
            if not z.IsFilled() or not z.HasFilledPolysForLayer(face):continue
            try:regions.canonical_native_regions(z.Outline(),timeout_s=min(2.,max(.001,deadline-time.monotonic())))
            except (ValueError,RuntimeError):continue
            shape=z.GetFilledPolysList(face);fills.identity(shape,deadline,max_vertices=200000)
            actual.BooleanAdd(shape);owners.append(z)
        require(owners,'actual_canonical_same_face_saved_power_fill_required')
        caps=[]
        for t in old:
            tick();ghost=t.Duplicate();ghost.SetStart(pcbnew.VECTOR2I(*at_nm));ghost.SetEnd(pcbnew.VECTOR2I(*at_nm))
            cap=pcbnew.SHAPE_POLY_SET();ghost.TransformShapeToPolygon(cap,face,0,1,pcbnew.ERROR_OUTSIDE,False)
            body=pcbnew.SHAPE_POLY_SET();t.TransformShapeToPolygon(body,face,0,1,pcbnew.ERROR_OUTSIDE,False)
            cap.BooleanIntersection(body);require(cap.OutlineCount()>0,'positive_native_power_terminal_cap_required')
            covered=[]
            for z in owners:
                tick();missing=cap.CloneDropTriangulation();missing.BooleanSubtract(z.Outline())
                if not missing.OutlineCount():covered.append(force._uid(z))
            require(covered,'whole_native_joint_cap_not_inside_canonical_authored_power_region')
            missing=cap.CloneDropTriangulation();missing.BooleanSubtract(actual);tick()
            require(not missing.OutlineCount(),'whole_native_joint_cap_not_inside_actual_saved_power_fill')
            digest,vertices=fills.identity(cap,deadline,max_vertices=200000)
            caps.append(dict(track_uuid=force._uid(t),width_nm=t.GetWidth(),cap_sha256=digest,
                cap_vertices=vertices,canonical_owner_zone_uuids=sorted(covered)))
        result.update(ok=True,complete=True,net=net,layer_id=face,track_uuids=list(track_uuids),
            source_corner_nm=list(at_nm),current_role_kind=kind,unchanged_current_authority=contract['current_authority'],
            entire_unequal_power_join_inside_canonical_saved_fill=True,power_join_not_signal_corner=True,
            exposed_hard90_not_present_by_positive_native_material_evidence=True,native_caps=caps,
            actual_saved_fill_not_bbox_or_outline_only=True,pre_drill_full_cap_bound_without_filling_any_bore=True,
            local_join_observation_not_whole_track_coverage_or_capacity=True,numeric_or_area_waiver_used=False)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
