"""Ephemeral whole-source power corridors during private reconstruction.

Reservations are NOT copper, capacity or routing permission. Their widths
come only from the actual current-domain contract, never from a caller's
thin hint or I/N. They must be removed before fill, save, DRC or receiving.
This prevents a locally shorter repair from consuming another required
full-current route's corridor when a whole chain is simplified.
"""
from __future__ import annotations
import math


def construct_barrels(board, requests, *, source_sha256, board_hint, blocked_net):
    """Reserve the actual transition land/drill envelope on ALL native faces.

    Outer lands come from the unchanged aggregate outer-face contract.
    Optional smaller inner lands must independently meet native/factory
    floors; they grant no inner-layer routing or barrel capacity credit.
    These obstacles create no saved copper, pin sharing or barrel rating.
    Validate the complete batch before adding anything; require_removed is
    the common mandatory cleanup check for traces and barrels alike.
    """
    import re
    import pcbnew
    import cec_current_topology as topology
    import cec_fab_profile as fab
    import cec_fr as fr
    import cec_force_current as force
    from cec_native_items import discard_items
    if (type(source_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',source_sha256)
            or type(blocked_net) is not str or not blocked_net
            or type(requests) is not list or not 1<=len(requests)<=4):
        raise ValueError('bounded_exact_source_future_current_barrels_required')
    domains=topology.board_current_domains(board,board_hint)
    contracts=topology.route_width_contracts(board,board_hint)
    plans=[];seen=set()
    for q in requests:
        required={'source_sha256','net','at_nm'}
        if type(q) is not dict or not required<=set(q) or set(q)-required-{'inner_land_diameter_nm'}:
            raise ValueError('exact_source_current_barrel_fields_required')
        net=q['net'];at=q['at_nm']
        domain=domains.get(net) if type(net) is str else None
        contract=contracts.get(net) if type(net) is str else None
        if (q['source_sha256']!=source_sha256 or type(net) is not str or not net
                or net==blocked_net or net.rsplit('/',1)[-1]=='GND'
                or board.FindNet(net) is None or board.FindNet(net).GetNetCode()<=0
                or type(at) is not list or len(at)!=2
                or any(type(v) is not int or abs(v)>2000000000 for v in at)
                or (net,tuple(at)) in seen
                or not domain or not domain.get('complete') or domain.get('missing_refs')
                or not contract or not {'F.Cu','B.Cu'}<=set(contract.get('routing_layers',()))):
            raise ValueError('positive_complete_foreign_current_barrel_source_required')
        auth=contract.get('current_authority',{})
        if (any(type(auth.get(k)) not in (int,float) or not math.isfinite(auth[k]) or auth[k]<=0
                for k in ('amps','geometry_margin'))
                or type(auth.get('margin_included')) is not bool
                or auth['margin_included'] and auth['geometry_margin']!=1.):
            raise ValueError('unchanged_positive_current_barrel_authority_required')
        floors=[contract.get('required_by_layer_mm',{}).get(n) for n in ('F.Cu','B.Cu')]
        if any(type(w) not in (int,float) or not math.isfinite(w) or w<=0 for w in floors):
            raise ValueError('complete_positive_outer_barrel_widths_required')
        full=max(math.ceil(w*1e6) for w in floors)
        dia,drill,_=fab.board_legal_through_via_geometry(board,max(.6,.3+full/1e6),.3)
        diameter,hole=round(dia*1e6),round(drill*1e6)
        if not 0<hole<diameter<=8000000 or diameter-hole<full:
            raise ValueError('bounded_full_source_future_barrel_web_required')
        inner=q.get('inner_land_diameter_nm')
        if 'inner_land_diameter_nm' in q:
            if type(inner) is not int or not hole<inner<diameter:
                raise ValueError('complete_legal_future_inner_land_diameter_required')
            legal_inner,legal_drill,_=fab.board_legal_through_via_geometry(board,inner/1e6,hole/1e6)
            if round(legal_inner*1e6)!=inner or round(legal_drill*1e6)!=hole:
                raise ValueError('every_future_inner_land_must_meet_native_and_factory_floors')
        point=pcbnew.VECTOR2I(*at)
        if not fr._edge_leg_clear(board,point,point,math.ceil(diameter/2)):
            raise ValueError('future_current_barrel_outside_actual_material')
        seen.add((net,tuple(at)));plans.append((net,at,diameter,hole,full,contract,inner))
    ghosts=[];rows=[]
    try:
        for net,at,diameter,hole,full,contract,inner in plans:
            v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I(*at))
            v.SetWidth(diameter);v.SetDrill(hole);v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNetCode(board.GetNetcodeFromNetname(net))
            if inner is not None:
                v.Padstack().SetMode(pcbnew.PADSTACK.MODE_FRONT_INNER_BACK)
                for face in board.GetEnabledLayers().CuStack():
                    v.SetWidth(face,diameter if face in (pcbnew.F_Cu,pcbnew.B_Cu) else inner)
            v.SetLocked(True);board.Add(v);ghosts.append(v)
            rows.append(dict(temporary_uuid=force._uid(v),net=net,at_nm=list(at),
                diameter_nm=diameter,drill_nm=hole,full_source_outer_web_nm=full,
                all_actual_faces_reserved=True,not_actual_saved_copper=True,
                actual_land_diameters_nm={board.GetLayerName(face):int(v.GetWidth(face))
                    for face in board.GetEnabledLayers().CuStack()},
                inner_lands_grant_no_routed_current_or_barrel_capacity=True))
    except Exception:
        discard_items(board,ghosts);raise
    return ghosts,dict(scope='ephemeral_whole_source_current_barrel_reservations',rows=rows,
        source_sha256=source_sha256,whole_source_contracts={q['net']:contracts[q['net']] for q in requests},
        saved_copper_authority=False,current_capacity_credited=False,equal_current_sharing_assumed=False,
        mandatory_removal_before_fill_save_or_receiving=True,release_authority=False)


def construct(board, requests, *, board_hint):
    import pcbnew
    import cec_current_topology as topology
    import cec_fab_profile as fab
    import cec_fr as fr
    import cec_route_quality as quality
    import cec_force_current as force
    from cec_native_items import discard_items
    if type(requests) is not list or not 1<=len(requests)<=4:
        raise ValueError('bounded_explicit_future_power_corridor_required')
    domains=topology.board_current_domains(board,board_hint)
    contracts=topology.route_width_contracts(board,board_hint)
    plans=[];count=0;seen=set()
    for q in requests:
        if type(q) is not dict or set(q)!={'net','layer','points_nm'}:
            raise ValueError('exact_future_power_corridor_fields_required')
        net=q['net'];face=q['layer'];points=q['points_nm']
        if (type(net) is not str or not net or net.rsplit('/',1)[-1]=='GND'
                or type(face) is not str or (net,face) in seen or board.FindNet(net) is None
                or board.FindNet(net).GetNetCode()<=0
                or net not in domains or not domains[net].get('complete') or domains[net].get('missing_refs')
                or net not in contracts or face not in contracts[net]['required_by_layer_mm']
                or type(points) is not list or not 2<=len(points)<=17
                or any(type(p) is not list or len(p)!=2 or any(type(v) is not int or abs(v)>2000000000 for v in p) for p in points)):
            raise ValueError('positive_complete_source_power_corridor_domain_required')
        lid=board.GetLayerID(face)
        if lid not in board.GetEnabledLayers().CuStack() or lid in {board.GetLayerID(n) for n in fr.plane_layers(board)}:
            raise ValueError('enabled_nonreference_future_power_face_required')
        raw=contracts[net]['required_by_layer_mm'][face]
        if type(raw) not in (int,float) or not math.isfinite(raw) or not 0<raw<=20:
            raise ValueError('bounded_actual_whole_source_width_required')
        width=math.ceil(raw*1e6);seen.add((net,face))
        for s,t in zip(points,points[1:]):
            count+=1
            if count>32 or not quality.is_canonical_stroke(tuple(s),tuple(t)) or s==t:
                raise ValueError('bounded_canonical_nonempty_future_power_strokes_required')
            a,b=pcbnew.VECTOR2I(*s),pcbnew.VECTOR2I(*t)
            if not fr._edge_leg_clear(board,a,b,math.ceil(width/2)):
                raise ValueError('future_power_corridor_outside_actual_board_material')
            plans.append((a,b,width,lid,net))
    ghosts=[];rows=[]
    try:
        for a,b,width,lid,net in plans:
            t=pcbnew.PCB_TRACK(board);t.SetStart(a);t.SetEnd(b);t.SetWidth(width);t.SetLayer(lid)
            t.SetNetCode(board.GetNetcodeFromNetname(net));t.SetLocked(True);board.Add(t);ghosts.append(t)
            rows.append(dict(temporary_uuid=force._uid(t),net=net,layer=board.GetLayerName(lid),width_nm=width,
                start_nm=list(a),end_nm=list(b),not_actual_saved_copper=True))
    except Exception:
        discard_items(board,ghosts);raise
    return ghosts,dict(scope='ephemeral_whole_source_power_route_reservations',rows=rows,
        whole_source_contracts={q['net']:contracts[q['net']] for q in requests},
        saved_copper_authority=False,current_capacity_credited=False,equal_current_sharing_assumed=False,
        mandatory_removal_before_fill_save_or_receiving=True,release_authority=False)


def require_removed(board, receipt):
    import cec_force_current as force
    ids={force._uid(t) for t in board.GetTracks()}
    if ids&{r['temporary_uuid'] for r in receipt['rows']}:
        raise ValueError('ephemeral_future_power_reservation_leaked_into_actual_copper')
    return dict(ok=True,temporary_reservations_absent=True,release_authority=False)
