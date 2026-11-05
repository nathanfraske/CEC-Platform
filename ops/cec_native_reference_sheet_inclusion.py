"""Exact native reference-metal inclusion, not a pair/reference qualification.

Unchanged pair copper does not lose its source reference when *every* actual
dedicated Ground sheet retains all old metal. This read-only proof permits
additional Ground after obsolete-hole retirement without pretending the fill
bytes are identical. New/moved drills, changed zone intent/profile or missing
metal refuse the proof. No area threshold, sampling, healing or epsilon is used.
"""
import math,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_fab_profile as fab
import cec_force_current as force
import cec_pair_local_reference_refinement as reference


def require(value,message):
    if not value:raise ValueError(message)


def receive(source,candidate,*,board_hint,timeout_s=10.):
    result=dict(ok=False,complete=False,errors=[],pair_or_reference_qualified=False,release_authority=False)
    try:
        require(type(board_hint) is str and bool(board_hint) and type(timeout_s) in (int,float)
            and math.isfinite(timeout_s) and 0<timeout_s<=10,'bounded_native_sheet_receiving_context_required')
        paths=[Path(p).resolve() for p in (source,candidate)];epoch=force._code_identity()
        digest=force._hash(Path(__file__).resolve());families=[force._family(p,board_hint) for p in paths]
        deadline=time.monotonic()+timeout_s;boards=[pcbnew.LoadBoard(str(p)) for p in paths]
        nodes=[additive._nodes(p)[1] for p in paths]
        require(force._sidecars(paths[0])==force._sidecars(paths[1])
            and force._preservation_snapshot(paths[0])[1]==force._preservation_snapshot(paths[1])[1],
            'reference_sheet_outline_settings_stack_or_sidecars_changed')
        with force._thermal_hint(board_hint):profiles=[fab.active_profile_name(b,hint=board_hint) for b in boards]
        require(profiles[0] and profiles[0]==profiles[1],'same_positive_reference_sheet_fab_profile_required')
        names=fab.COPPER_LAYERS;roles=fab.get_profile(profiles[0])['roles']
        faces={int(boards[0].GetLayerID(n)) for n,r in zip(names,roles) if r=='GND'}
        require(faces and all(b.GetEnabledLayers().Contains(l) for b in boards for l in faces),
            'enabled_actual_dedicated_ground_reference_faces_required')
        fp=[{u:n for u,n in row.items() if n[0]=='footprint'} for row in nodes]
        require(fp[0].keys()==fp[1].keys() and all(syntax._freeze(n)==syntax._freeze(fp[1][u]) for u,n in fp[0].items()),
            'reference_sheet_all_actual_drilled_footprint_geometry_must_stay_exact')
        vias=[{u:n for u,n in row.items() if n[0]=='via'} for row in nodes]
        require(vias[1].keys()<=vias[0].keys() and all(syntax._freeze(n)==syntax._freeze(vias[0][u]) for u,n in vias[1].items()),
            'reference_sheet_no_new_or_moved_bores_allowed')
        zones=[{force._uid(z):z for z in b.Zones() if not z.GetIsRuleArea()
            and z.GetNetname()=='GND' and any(z.IsOnLayer(l) for l in faces)} for b in boards]
        require(zones[0] and zones[0].keys()==zones[1].keys(),'same_actual_dedicated_ground_zone_inventory_required')
        rows=[];covered=set()
        for uid,old in zones[0].items():
            new=zones[1][uid]
            require(additive._without(nodes[0][uid],'filled_polygon')==additive._without(nodes[1][uid],'filled_polygon'),
                'ground_reference_outline_or_fill_settings_changed')
            for face in sorted(faces):
                require(old.IsOnLayer(face)==new.IsOnLayer(face),'native_reference_zone_face_changed')
                if not old.IsOnLayer(face):continue
                covered.add(face)
                require(all(z.IsFilled() and z.HasFilledPolysForLayer(face) for z in (old,new)),
                    'complete_saved_native_reference_fill_required')
                polygons=[z.GetFilledPolysList(face).CloneDropTriangulation() for z in (old,new)]
                identities=[reference._reference_identity(p,deadline) for p in polygons]
                require(polygons[0].OutlineCount()>0 and polygons[1].OutlineCount()>0,'nonempty_actual_native_reference_sheets_required')
                missing=polygons[0].CloneDropTriangulation();missing.BooleanSubtract(polygons[1])
                require(time.monotonic()<deadline and not missing.OutlineCount(),
                    'actual_source_reference_metal_was_removed_or_deadline_exhausted')
                extra=polygons[1].CloneDropTriangulation();extra.BooleanSubtract(polygons[0])
                rows.append(dict(uuid=uid,face=int(face),source_native_identity=identities[0],candidate_native_identity=identities[1],
                    missing_native_outlines=0,additional_native_outlines=extra.OutlineCount(),
                    exact_native_metal_subset=True))
        require(covered==faces,'every_actual_dedicated_ground_reference_face_required')
        require(epoch==force._code_identity() and digest==force._hash(Path(__file__).resolve())
            and families==[force._family(p,board_hint) for p in paths] and time.monotonic()<deadline,
            'native_reference_sheet_epoch_or_deadline_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[1]),
            code_identity=epoch,authority_sha256=digest,rows=rows,actual_ground_reference_faces=sorted(faces),
            every_source_ground_reference_sheet_subset_of_candidate=True,source_zone_intent_unchanged=True,
            source_drilled_footprints_and_surviving_vias_exact=True,source_holes_only_retired_no_new_bores=True,
            retired_source_via_uuids=sorted(vias[0].keys()-vias[1].keys()),
            exact_integer_native_polygon_difference=True,numeric_or_area_waiver_used=False,
            source_candidate_and_code_unchanged=True,typed_conductor_drc_fields_and_release_receiving_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
