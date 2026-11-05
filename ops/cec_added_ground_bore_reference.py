"""Reference preservation for exact additive Ground bores, not no-bore edits.

All original pair items, footprints, surviving bores, stack and zone intent
stay literal. Saved Ground fills must match an independent native additive
replay. Every real missing filled polygon is tested against the pair too.
Each additional real circular Ground drill, enlarged by the Source pair
clearance, must be disjoint from ALL actual native copper of that pair on
every face. Thus no newly drilled reference loss can reach the unchanged
pair projection. Unlike the older no-new-bore lemma, this does NOT claim
that all global physical Ground metal remains: new drill apertures are real.
This is scoped preservation, not impedance, reference or fabrication signoff.
"""
import math
import time
from pathlib import Path

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_fab_profile as fab
import cec_force_current as force
import cec_pair_local_reference_refinement as native
import cec_precision_route as precision


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _pair_copper(board, pair, deadline, clearance_nm=0):
    """Outside native copper, including real lands and barrels, not centres."""
    names={pair['p'],pair['n']};result=pcbnew.SHAPE_POLY_SET();count=0
    for face in board.GetEnabledLayers().CuStack():
        for item in [*board.GetTracks(),*[p for f in board.GetFootprints() for p in f.Pads()]]:
            if item.GetNetname() not in names or not item.IsOnLayer(face):continue
            _require(time.monotonic()<deadline,'added_bore_pair_projection_deadline')
            poly=pcbnew.SHAPE_POLY_SET()
            item.TransformShapeToPolygon(poly,face,clearance_nm,1000,pcbnew.ERROR_OUTSIDE)
            native._reference_identity(poly,deadline);result.BooleanAdd(poly);count+=1
    _require(count and result.OutlineCount(),'nonempty_actual_native_pair_copper_projection_required')
    _require(not any(not z.GetIsRuleArea() and z.GetNetname() in names for z in board.Zones()),
        'pair_zone_reference_projection_not_supported')
    return result,count


def _bore_guard(via, clearance_nm):
    # PCB_VIA's actual through drill is circular; round radius OUTWARD. The
    # additional guard is the existing Source pair clearance, not an epsilon
    # allowance or invented electrical keepout.
    radius=(int(via.GetDrillValue())+1)//2+clearance_nm
    shape=pcbnew.SHAPE_CIRCLE(via.GetPosition(),radius)
    poly=pcbnew.SHAPE_POLY_SET();shape.TransformToPolygon(poly,1,pcbnew.ERROR_OUTSIDE)
    return poly


def receive(source,candidate,*,board_hint,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],pair_or_reference_qualified=False,
        fab_ready=False,routing_admitted=False,release_authority=False)
    try:
        _require(type(board_hint) is str and bool(board_hint) and type(timeout_s) in (int,float)
            and math.isfinite(timeout_s) and 0<timeout_s<=10.,'bounded_added_ground_bore_reference_context_required')
        paths=[Path(p).resolve() for p in (source,candidate)];epoch=force._code_identity()
        tool=Path(__file__).resolve();digest=force._hash(tool)
        families=[force._family(p,board_hint) for p in paths]
        # Two explicit independent <=10-second phases, never a longer lease
        # for the frozen additive or native reference geometry receivers.
        replay=additive.receive(*paths,board_hint=board_hint,timeout_s=timeout_s)
        _require(replay['ok'] and replay['complete'] and
            replay['existing_ground_fill_matches_independent_native_replay'],
            'independent_exact_native_source_plus_ground_bore_refill_required:'+str(replay['errors']))
        deadline=time.monotonic()+timeout_s
        boards=[pcbnew.LoadBoard(str(p)) for p in paths];nodes=[additive._nodes(p)[1] for p in paths]
        _require(force._sidecars(paths[0])==force._sidecars(paths[1]) and
            force._preservation_snapshot(paths[0])[1]==force._preservation_snapshot(paths[1])[1],
            'added_bore_reference_stack_settings_outline_or_sidecars_changed')
        old,new=nodes;common=old.keys()&new.keys();incoming=new.keys()-old.keys()
        _require(not old.keys()-new.keys() and 1<=len(incoming)<=8
            and all(new[u][0]=='via' for u in incoming),'one_to_eight_pure_additive_ground_bores_required')
        _require(all(syntax._freeze(old[u])==syntax._freeze(new[u]) for u in common
            if old[u][0] not in ('zone','group')),'original_pair_parts_tracks_and_existing_bores_must_be_literal')
        live={force._uid(t):t for t in boards[1].GetTracks()};added=[live[u] for u in sorted(incoming)]
        _require(all(v.GetClass()=='PCB_VIA' and v.GetNetname()=='GND'
            and v.GetViaType()==pcbnew.VIATYPE_THROUGH and v.TopLayer()==pcbnew.F_Cu
            and v.BottomLayer()==pcbnew.B_Cu and v.GetDrillValue()>0 for v in added),
            'only_actual_new_ground_through_bores_are_in_scope')
        with force._thermal_hint(board_hint):profiles=[fab.active_profile_name(b,hint=board_hint) for b in boards]
        _require(profiles[0] and profiles[0]==profiles[1],'unchanged_positive_source_reference_stack_required')
        faces={int(boards[0].GetLayerID(n)) for n,role in zip(fab.COPPER_LAYERS,
            fab.get_profile(profiles[0])['roles']) if role=='GND'}
        _require(faces,'actual_dedicated_ground_reference_faces_required')
        zones=[{force._uid(z):z for z in b.Zones()} for b in boards]
        _require(zones[0].keys()==zones[1].keys(),'reference_zone_inventory_changed')
        sheets=[];covered=set();missing_union=pcbnew.SHAPE_POLY_SET()
        for uid,z in zones[0].items():
            other=zones[1][uid]
            if z.GetIsRuleArea() or z.GetNetname()!='GND':
                _require(syntax._freeze(old[uid])==syntax._freeze(new[uid]),'non_ground_zone_changed');continue
            _require(additive._without(old[uid],'filled_polygon')==additive._without(new[uid],'filled_polygon'),
                'source_ground_reference_zone_intent_changed')
            for face in sorted(faces):
                if not z.IsOnLayer(face):continue
                covered.add(face)
                _require(all(q.IsFilled() and q.HasFilledPolysForLayer(face) for q in (z,other)),
                    'complete_actual_saved_ground_reference_fill_required')
                polys=[q.GetFilledPolysList(face).CloneDropTriangulation() for q in (z,other)]
                identities=[native._reference_identity(q,deadline) for q in polys]
                missing=polys[0].CloneDropTriangulation();missing.BooleanSubtract(polys[1])
                missing_union.BooleanAdd(missing)
                _require(all(q.OutlineCount() for q in polys),'nonempty_source_and_candidate_ground_sheets_required')
                sheets.append(dict(uuid=uid,face=face,source_native_identity=identities[0],
                    candidate_native_identity=identities[1],missing_filled_polygon_outlines=missing.OutlineCount(),
                    missing_actual_native_identity=native._reference_identity(missing,deadline)))
        _require(covered==faces,'all_dedicated_source_ground_faces_must_be_observed')
        pairs=[precision.derive_coupled_pairs(str(p),board=b) for p,b in zip(paths,boards)]
        _require(pairs[0]==pairs[1] and pairs[0],'unchanged_nonempty_source_pair_inventory_required')
        pair_rows=[]
        for pair in pairs[0]:
            clearance=math.ceil(precision._pair_clearance(boards[0],pair)*1e6)
            projection,count=_pair_copper(boards[0],pair,deadline)
            protected,_=_pair_copper(boards[0],pair,deadline,clearance)
            fill_loss=missing_union.CloneDropTriangulation();fill_loss.BooleanIntersection(protected)
            _require(not fill_loss.OutlineCount(),'actual_missing_ground_fill_reaches_source_pair_copper_or_clearance')
            bore_rows=[]
            for via in added:
                guard=_bore_guard(via,clearance);native._reference_identity(guard,deadline)
                guard.BooleanIntersection(projection)
                _require(not guard.OutlineCount(),'new_ground_bore_reaches_source_pair_copper_or_source_clearance')
                bore_rows.append(dict(uuid=force._uid(via),drill_nm=int(via.GetDrillValue()),
                    at_nm=list(via.GetPosition()),source_pair_clearance_nm=clearance,
                    actual_native_intersection_outlines=0))
            pair_rows.append(dict(pair=pair,actual_projected_native_copper_items=count,
                projection_identity=native._reference_identity(projection,deadline),
                added_bores=bore_rows,missing_native_ground_fill_intersection_outlines=0,
                new_projected_reference_deficit_added=False))
        _require(time.monotonic()<deadline and epoch==force._code_identity() and digest==force._hash(tool)
            and families==[force._family(p,board_hint) for p in paths],
            'added_ground_bore_reference_source_code_or_lease_changed')
        r.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[1]),
            code_identity=epoch,authority_sha256=digest,actual_ground_reference_faces=sorted(faces),
            ground_filled_polygon_receiving=sheets,pairs=pair_rows,added_ground_via_uuids=sorted(incoming),
            independent_native_additive_replay=replay,
            original_pair_footprint_and_surviving_bore_geometry_exact=True,
            every_source_filled_ground_polygon_preserved=not bool(missing_union.OutlineCount()),
            source_ground_fill_changes_are_exact_native_additive_replay=True,
            missing_saved_ground_fill_source_clearance_separated_from_all_pair_copper=True,
            new_ground_bores_source_clearance_separated_from_all_pair_copper=True,
            new_reference_deficit_added=False,global_physical_ground_metal_unchanged_claimed=False,
            drilled_reference_loss_is_real_not_filled_or_hidden=True,
            original_no_new_bore_receiver_relaxed=False,profile_roles_reclassified=False,
            native_pair_capsule_outside_error_nm=1000,native_bore_guard_outside_error_nm=1,
            numeric_area_or_sampling_waiver_used=False,source_candidate_and_code_unchanged=True,
            independent_phase_lease_seconds=timeout_s,independent_lease_phases=2,
            typed_ground_owner_native_DRC_current_Kelvin_field_stack_and_fab_receiving_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
