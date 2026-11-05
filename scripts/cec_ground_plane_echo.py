"""Retire an inner-layer GND echo already covered by two real ground planes.

This owns only an unlocked, ungrouped, uniform, short via-to-via stitch on a
nonplane inner layer. Both real through barrels and all plane copper remain
exact. Complete capsule coverage by TWO independent saved GND-plane layers,
direct barrel contact, all surviving partitions and every proved immediate
ground return are mandatory. No surface shielding, ampacity, thermal, Kelvin,
inherited-debt or release qualification follows from this topological proof.
"""
import math
import hashlib
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items


def _deadline(timeout_s):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10):
        raise ValueError('bounded_native_ground_echo_required')
    return time.monotonic()+timeout_s


def _tick(deadline):
    if time.monotonic()>=deadline:raise ValueError('native_ground_echo_deadline')


def _poly(item, layer):
    result=pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(result,int(layer),0,1,pcbnew.ERROR_OUTSIDE)
    return result


def _binding(board):
    # The field inventory binds actual filled/outline copper. Plane priority,
    # fabrication clearances and protected groups are process authority too.
    zones=sorted((force._uid(z),z.GetZoneName(),z.GetAssignedPriority(),
        z.GetLocalClearance(),z.GetMinThickness(),z.GetPadConnection()) for z in board.Zones())
    groups=sorted((force._uid(g),g.GetName(),sorted(force._uid(i) for i in g.GetItems()))
        for g in board.Groups())
    return hashlib.sha256(repr((field._field_snapshot_inventory(board),zones,groups)).encode()).hexdigest()


def plan(board,track_uuid,*,timeout_s=10.):
    deadline=_deadline(timeout_s)
    tracks={force._uid(t):t for t in board.GetTracks()}
    seed=tracks.get(track_uuid)
    if seed is None or seed.GetClass()!='PCB_TRACK' or seed.GetNetname()!='GND':
        raise ValueError('exact_native_ground_stitch_required')
    layer=int(seed.GetLayer());width=int(seed.GetWidth())
    planes={int(board.GetLayerID(name)) for name in fr.plane_layers(board)}
    enabled=set(map(int,board.GetEnabledLayers().CuStack()))
    if layer not in enabled-{int(pcbnew.F_Cu),int(pcbnew.B_Cu)}-planes:
        raise ValueError('nonplane_inner_stitch_only_no_surface_shielding_retirement')
    if not 0<width<=350000:raise ValueError('thin_uniform_ground_echo_required')
    grouped={force._uid(i) for group in board.Groups() for i in group.GetItems()}
    chosen={};roots={};pending=[seed]
    while pending:
        _tick(deadline);edge=pending.pop();uid=force._uid(edge)
        if uid in chosen:continue
        if (edge.GetClass()!='PCB_TRACK' or edge.GetNetname()!='GND'
                or int(edge.GetLayer())!=layer or edge.GetWidth()!=width
                or edge.IsLocked() or uid in grouped or edge.GetLength()<=0):
            raise ValueError('unlocked_ungrouped_uniform_ground_echo_required')
        chosen[uid]=edge
        if len(chosen)>8 or sum(t.GetLength() for t in chosen.values())>12000000:
            raise ValueError('bounded_ground_echo_chain_required')
        # Copy temporary SWIG vectors immediately; never retain proxies.
        ends=(tuple(edge.GetStart()),tuple(edge.GetEnd()))
        for at in ends:
            _tick(deadline)
            vias=[t for t in tracks.values() if t.GetClass()=='PCB_VIA'
                and t.GetNetCode()==seed.GetNetCode() and tuple(t.GetPosition())==at]
            if vias:
                if (len(vias)!=1 or vias[0].GetViaType()!=pcbnew.VIATYPE_THROUGH
                        or not {int(pcbnew.F_Cu),int(pcbnew.B_Cu)}<=set(map(int,vias[0].GetLayerSet().CuStack()))):
                    raise ValueError('two_real_ground_through_barrels_required')
                roots[force._uid(vias[0])]=vias[0];continue
            peers=[t for t in tracks.values() if force._uid(t)!=uid
                and t.GetClass()=='PCB_TRACK' and t.GetNetCode()==seed.GetNetCode()
                and int(t.GetLayer())==layer and at in (tuple(t.GetStart()),tuple(t.GetEnd()))]
            if len(peers)!=1:raise ValueError('endpoint_linear_via_to_via_echo_required')
            if force._uid(peers[0]) not in chosen:pending.append(peers[0])
    if len(roots)!=2:raise ValueError('two_distinct_retained_ground_barrels_required')
    body=pcbnew.SHAPE_POLY_SET();apertures=pcbnew.SHAPE_POLY_SET()
    for edge in chosen.values():body.BooleanAdd(_poly(edge,layer))
    for via in roots.values():apertures.BooleanAdd(_poly(via,layer))
    # A contact elsewhere on the stitch is not owned by a ground-plane echo.
    # Test the whole polygon intersection, not merely endpoint hit tests that
    # could hide an additional interior tee on one long neighbouring track.
    for item in [*(p for fp in board.GetFootprints() for p in fp.Pads()),
            *tracks.values(),*[z for z in board.Zones() if not z.GetIsRuleArea()]]:
        _tick(deadline);uid=force._uid(item)
        if uid in chosen or uid in roots or item.GetNetCode()!=seed.GetNetCode() or not item.IsOnLayer(layer):continue
        if item.GetClass()=='ZONE':
            if not item.IsFilled():raise ValueError('ground_echo_contact_material_unknown')
            overlap=pcbnew.SHAPE_POLY_SET(item.GetFilledPolysList(layer))
        else:overlap=_poly(item,layer)
        overlap.BooleanIntersection(body);overlap.BooleanSubtract(apertures)
        if overlap.OutlineCount():raise ValueError('ground_echo_has_unowned_interior_contact:'+uid)
    witnesses=[]
    for zone in board.Zones():
        _tick(deadline)
        if zone.GetIsRuleArea() or zone.GetNetname()!='GND' or not zone.IsFilled():continue
        for face in sorted(planes&enabled):
            if not zone.IsOnLayer(face) or not zone.HasFilledPolysForLayer(face):continue
            copper=zone.GetFilledPolysList(face)
            missing=pcbnew.SHAPE_POLY_SET(body);missing.BooleanSubtract(copper)
            if missing.OutlineCount():continue
            if not all(via.IsOnLayer(face) and copper.Collide(via.GetEffectiveShape(face),0)
                    for via in roots.values()):continue
            witnesses.append(dict(zone_uuid=force._uid(zone),layer=face,
                layer_name=board.GetLayerName(face),full_capsule_coverage=True,
                retained_native_barrel_contacts=sorted(roots)))
    if len({q['layer'] for q in witnesses})<2:
        raise ValueError('two_independent_continuous_saved_ground_plane_covers_required')
    _tick(deadline)
    return dict(schema=1,track_uuid=track_uuid,retired_track_uuids=sorted(chosen),
        retained_via_uuids=sorted(roots),retired_via_uuids=[],source_width_nm=width,
        source_layer=layer,source_path_mm=sum(t.GetLength() for t in chosen.values())/1e6,
        saved_plane_witnesses=witnesses,source_binding=_binding(board),
        current_authority=False,release_authority=False,inductive_return_qualified=False)


def subtract(board,proposal):
    if _binding(board)!=proposal['source_binding']:
        raise ValueError('ground_echo_source_binding_changed')
    if plan(board,proposal['track_uuid'])!=proposal:
        raise ValueError('ground_echo_source_geometry_or_plane_coverage_changed')
    ids=set(proposal['retired_track_uuids'])
    discard_items(board,[t for t in board.GetTracks() if force._uid(t) in ids])


def receive(source,candidate,*,track_uuid,board_hint,timeout_s=10.):
    started=time.monotonic();result=dict(schema=1,ok=False,complete=False,errors=[],
        scope='two_saved_plane_inner_ground_echo_subtraction',release_authority=False,
        current_authority=False,inductive_return_qualified=False,inherited_debt_qualified=False,
        full_saved_board_receiving_still_required=True)
    try:
        deadline=_deadline(timeout_s);source,candidate=[Path(p).resolve() for p in (source,candidate)]
        if source==candidate:raise ValueError('distinct_saved_ground_echo_candidates_required')
        families=[force._family(p,board_hint) for p in (source,candidate)];epoch=force._code_identity()
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        proposal=plan(parent,track_uuid,timeout_s=max(.001,deadline-time.monotonic()))
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        retired=set(proposal['retired_track_uuids'])
        if (old.keys()-new.keys()!=retired or new.keys()-old.keys()
                or any(sexpr._freeze(old[u])!=sexpr._freeze(new[u]) for u in new)):
            raise ValueError('ground_echo_may_only_subtract_exact_proved_inner_stitch')
        before=ordinary._partition(parent,deadline,retired_uuids=retired)
        after=ordinary._partition(child,deadline,retained_keys=set().union(*before))
        if any(not any(p<=q for q in after) for p in before):
            raise ValueError('ground_echo_lost_surviving_native_partition')
        pads={force._uid(p):p for fp in parent.GetFootprints() for p in fp.Pads() if p.GetNetname()=='GND'}
        actual={force._uid(p):p for fp in child.GetFootprints() for p in fp.Pads() if p.GetNetname()=='GND'}
        if pads.keys()!=actual.keys():raise ValueError('ground_echo_ground_land_population_changed')
        known=[];unknown=[]
        for uid,pad in pads.items():
            _tick(deadline);first=cells._existing_return(parent,pad,3.5)
            if first is None:unknown.append(uid);continue
            last=cells._existing_return(child,actual[uid],3.5)
            if last is None or last[0]>first[0]+1e-6:
                raise ValueError('ground_echo_proved_short_return_worsened:'+uid)
            known.append(dict(pad_uuid=uid,before_mm=first[0],after_mm=last[0]))
        with tempfile.TemporaryDirectory(prefix='cec-ground-echo-replay-') as directory:
            basis=force._copy_family(source,Path(directory)/'projected')
            replay=pcbnew.LoadBoard(str(basis));subtract(replay,proposal)
            field._save_field_snapshot(replay,basis)
            proof=additive.receive(basis,candidate,timeout_s=max(.001,deadline-time.monotonic()))
            result['independent_exact_subtraction_replay']=proof
            if proof.get('ok') is not True or proof.get('complete') is not True:
                raise ValueError('ground_echo_independent_saved_replay_refused')
        _tick(deadline)
        if families!=[force._family(p,board_hint) for p in (source,candidate)] or epoch!=force._code_identity():
            raise ValueError('ground_echo_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,source_candidate_and_code_unchanged=True,
            retired_track_uuids=sorted(retired),retired_via_uuids=[],added_native_uuids=[],
            proved_short_ground_returns=known,unqualified_ground_return_pad_uuids=sorted(unknown),
            all_surviving_native_partitions_and_short_returns_preserved=True,
            all_native_barrels_and_plane_copper_exact=True,
            source_proposal={k:v for k,v in proposal.items() if k!='source_binding'})
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=round(time.monotonic()-started,6)
    return result
