"""Required, Source-owned ordinary supply-departure columns.

A constructive column can justify a bounded ordinary-obstacle reconstruction
only when the complete macro is required to build that exact real barrel.
Source bypass ownership and full-rail width remain authoritative. This is
not virtual copper, new current/barrel capacity, or a fabrication waiver.
"""
import hashlib,json,math,time,uuid
from pathlib import Path
import pcbnew
import cec_cell_row_rebuild as row
import cec_decoupler_cell as cell
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_measurement_leaf as leaf
import cec_native_placement_context as native
import cec_native_component_ports as ports
import cec_route_quality as quality


def _digest(pad,deadline):
    material=native._native_stationary_land(pad,deadline)
    if material is None:raise ValueError('required_supply_native_land_unknown')
    return hashlib.sha256(repr(material[:3]+material[4:]).encode()).hexdigest()


def plan(parent,private,proposal,requests,*,timeout_s=10.):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or type(requests) not in (list,tuple) or len(requests)>4):
        raise ValueError('bounded_explicit_supply_departure_columns_required')
    if not requests:return [],[]
    deadline=time.monotonic()+timeout_s;source=Path(parent.GetFileName()).resolve()
    binding=row._source_binding(parent)
    if (not source.is_file() or proposal.get('source_native_binding')!=binding
            or row._source_binding(pcbnew.LoadBoard(str(source)))!=binding):
        raise ValueError('literal_saved_supply_departure_source_required')
    old={force._uid(p):p for f in parent.GetFootprints() for p in f.Pads()}
    live={force._uid(p):p for f in private.GetFootprints() for p in f.Pads()}
    proofs=[];columns=[];seen=set();sites=set()
    for request in requests:
        if time.monotonic()>=deadline:raise ValueError('required_supply_departure_plan_deadline')
        if (type(request) is not dict or set(request)!={'owner_pad_uuid','position_nm'}
                or type(request['owner_pad_uuid']) is not str or request['owner_pad_uuid'] in seen
                or request['owner_pad_uuid'] not in old or request['owner_pad_uuid'] not in live
                or type(request['position_nm']) not in (list,tuple) or len(request['position_nm'])!=2
                or any(type(v) is not int or abs(v)>2000000000 for v in request['position_nm'])
                or tuple(request['position_nm']) in sites):
            raise ValueError('unique_literal_supply_departure_pad_and_site_required')
        uid=request['owner_pad_uuid'];before,pad=old[uid],live[uid];ref=pad.GetParentFootprint().GetReference()
        face=cell.cec_return_escape.smd_surface_layer(pad)
        if (ref not in proposal['poses'] or face is None or pad.HasHole() or pad.GetNetname()=='GND'
                or pad.GetNetname()!=before.GetNetname() or pad.GetParentFootprint().IsLocked()
                or pad.GetParentFootprint().IsDNP()
                or math.dist(tuple(pad.GetPosition()),request['position_nm'])>6000000):
            raise ValueError('bounded_actual_surface_supply_departure_owner_required')
        authority=leaf._bypass_supply_owner(parent,before,proposal['board_hint'])
        with force._thermal_hint(proposal['board_hint']):
            contract=cell._supply_current_widths(parent,before.GetNetname())
            after_contract=cell._supply_current_widths(private,pad.GetNetname())
        if (not contract or json.loads(json.dumps(contract))!=json.loads(json.dumps(after_contract))
                or face not in contract['required_by_layer_nm']):
            raise ValueError('unchanged_positive_full_supply_contract_required')
        width=max(200000,int(parent.GetDesignSettings().m_TrackMinWidth),
            int(cell._netclass(parent,pad.GetNetname())['width']),contract['required_by_layer_nm'][face])
        from cec_cell_escape_replan import _source_current_via_geometry
        geometry=_source_current_via_geometry(private,contract,
            tuple(map(int,private.GetEnabledLayers().CuStack())),minimum_width_nm=width)
        diameter,drill=geometry['dia'],geometry['drill']
        dia,hole=round(diameter*1e6),round(drill*1e6);at=pcbnew.VECTOR2I(*request['position_nm'])
        if any(t.GetClass()=='PCB_VIA' and tuple(t.GetPosition())==tuple(at) for t in private.GetTracks()):
            raise ValueError('required_supply_departure_must_be_new_not_duplicate')
        if (not fr._edge_leg_clear(private,at,at,dia//2)
                or not cell._hole_to_hole_clear(private,at,drill)[0]):
            raise ValueError('required_supply_departure_edge_or_drill_conflict')
        column=pcbnew.PCB_VIA(private);column.SetPosition(at);column.SetNet(pad.GetNet())
        column.SetWidth(dia);column.SetDrill(hole);column.SetViaType(pcbnew.VIATYPE_THROUGH)
        column.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        name='required-source-supply:'+force._hash(source)+':'+uid+':'+repr(tuple(at))
        column.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,name))))
        proofs.append(dict(schema=1,scope='source_required_ordinary_supply_departure',source=str(source),
            source_sha256=force._hash(source),source_native_binding=binding,board_hint=proposal['board_hint'],
            pad_uuid=uid,owner=ref,target_pose=list(proposal['poses'][ref]),net=pad.GetNetname(),face=int(face),
            point_nm=list(at),diameter_nm=dia,drill_nm=hole,width_nm=width,source_supply_owner=authority,
            required_full_contact_web_nm=geometry['minimum_local_via_web_nm'],
            unchanged_full_rail_current_contract=json.loads(json.dumps(contract)),
            actual_land_sha256=_digest(pad,deadline),proposal_column_uuid=force._uid(column),
            maximum_surface_path_mm=6.,mandatory_new_saved_barrel=True,
            current_capacity_or_new_rule_or_clearance_credit=False,release_authority=False))
        columns.append(column);seen.add(uid);sites.add(tuple(at))
    if row._source_binding(parent)!=binding or time.monotonic()>=deadline:
        raise ValueError('required_supply_departure_source_changed_or_expired')
    return proofs,columns


def rederive(board,proof,*,timeout_s=10.):
    source=Path(proof['source'])
    if not source.is_file() or force._hash(source)!=proof['source_sha256']:
        raise ValueError('required_supply_departure_source_changed')
    parent=pcbnew.LoadBoard(str(source))
    fresh,_=plan(parent,board,dict(source_native_binding=row._source_binding(parent),
        board_hint=proof['board_hint'],poses={proof['owner']:proof['target_pose']}),
        [dict(owner_pad_uuid=proof['pad_uuid'],position_nm=proof['point_nm'])],timeout_s=timeout_s)
    if json.loads(json.dumps(fresh[0]))!=proof:raise ValueError('required_supply_departure_stale_or_forged')


def required_ops(proof,ops):
    vias=[op for op in ops if op[0]=='via']
    return bool(len(vias)==1 and list(vias[0][1])==proof['point_nm']
        and round(vias[0][2]*1e6)==proof['drill_nm'] and round(vias[0][3]*1e6)==proof['diameter_nm'])


def entry_ops(board,proof,*,timeout_s=10.):
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.:
        raise ValueError('bounded_required_supply_departure_offer_lease')
    deadline=time.monotonic()+timeout_s;rederive(board,proof,timeout_s=timeout_s)
    pad=next(p for f in board.GetFootprints() for p in f.Pads() if force._uid(p)==proof['pad_uuid'])
    at=pcbnew.VECTOR2I(*proof['point_nm']);gap=max(200000,int(board.GetDesignSettings().m_MinClearance),
        int(cell._netclass(board,proof['net'])['clearance']))
    detail=dict(scope='exact_required_native_supply_departure_offer',found=False,no_path_proof=False,release_authority=False)
    spot={};clear=bool(fr._edge_leg_clear(board,at,at,proof['diameter_nm']//2+gap)
        and cell._hole_to_hole_clear(board,at,proof['drill_nm']/1e6)[0]
        and fr._via_spot_clear(board,at,proof['diameter_nm'],gap,{pad.GetNetCode()},
            drill_nm=proof['drill_nm'],net_code=pad.GetNetCode(),foreign_cache={},report=spot))
    detail['actual_native_column_admission']=spot
    if not clear or time.monotonic()>=deadline:return [],detail
    legs=fr._guarded_profiled_lastmile_legs(board,pad.GetPosition(),at,proof['width_nm'],proof['face'],gap,
        pad.GetNetCode(),lambda s,t,h:fr._edge_leg_clear(board,s,t,h+gap),foreign_cache={},
        deadline_monotonic=deadline,allow_maze=True,refine_maze=True,endpoint_detail_grid_mm=.2,
        compact_phase_jogs=True,max_length_nm=round(proof['maximum_surface_path_mm']*1e6),search_diagnostics=detail)
    if (not legs or time.monotonic()>=deadline
            or sum(math.dist(tuple(s),tuple(t)) for s,t,w in legs)>proof['maximum_surface_path_mm']*1e6
            or tuple(legs[0][0])!=tuple(pad.GetPosition()) or tuple(legs[-1][1])!=tuple(at)
            or any(int(w)!=proof['width_nm'] or not quality.is_canonical_stroke(tuple(s),tuple(t),tolerance_nm=0)
                for s,t,w in legs)
            or any(tuple(first[1])!=tuple(last[0]) for first,last in zip(legs,legs[1:]))):return [],detail
    ops=[('trk',tuple(s),tuple(t),int(w),proof['face']) for s,t,w in legs]
    ops.append(('via',tuple(at),proof['drill_nm']/1e6,proof['diameter_nm']/1e6))
    if not ports.plain_endpoint_turn_guard(board,proof['net'])(ops):return [],detail
    detail['found']=True
    return ops,detail


def receive(board,proofs,incoming,*,timeout_s=10.):
    deadline=time.monotonic()+timeout_s;observed=[]
    for proof in proofs:
        if time.monotonic()>=deadline:raise ValueError('required_saved_supply_departure_deadline')
        pad=next((p for f in board.GetFootprints() for p in f.Pads() if force._uid(p)==proof['pad_uuid']),None)
        if pad is None or _digest(pad,deadline)!=proof['actual_land_sha256']:
            raise ValueError('required_saved_supply_departure_land_changed')
        matches=[t for t in board.GetTracks() if force._uid(t) in incoming and t.GetClass()=='PCB_VIA'
            and t.GetNetname()==proof['net'] and list(t.GetPosition())==proof['point_nm']
            and t.GetDrillValue()==proof['drill_nm'] and t.GetViaType()==pcbnew.VIATYPE_THROUGH
            and t.TopLayer()==pcbnew.F_Cu and t.BottomLayer()==pcbnew.B_Cu
            and all(t.GetWidth(l)==proof['diameter_nm'] for l in board.GetEnabledLayers().CuStack())]
        if len(matches)!=1:raise ValueError('required_new_saved_supply_departure_not_constructed')
        via=matches[0]
        # The fresh compiler proof sized every possible contact face before
        # native search. Recheck its full web on the literal saved column;
        # process legality alone is not a current-contact width proof.
        from cec_cell_escape_replan import _source_current_via_geometry
        geometry=_source_current_via_geometry(board,proof['unchanged_full_rail_current_contract'],
            tuple(map(int,board.GetEnabledLayers().CuStack())),minimum_width_nm=proof['width_nm'])
        if (proof.get('required_full_contact_web_nm')!=geometry['minimum_local_via_web_nm']
                or any(via.GetWidth(l)-via.GetDrillValue()<geometry['minimum_local_via_web_nm']
                    for l in board.GetEnabledLayers().CuStack())):
            raise ValueError('required_saved_supply_departure_full_contact_web_lost')
        distance=cell._shortest_track_path_mm(board,pad,via,snap_mm=.000001)
        if distance is None or distance>proof['maximum_surface_path_mm']:
            raise ValueError('required_saved_supply_departure_has_no_bounded_terminal_path')
        if tuple(round(v*1e6) for v in fab.board_legal_through_via_geometry(board,
                proof['diameter_nm']/1e6,proof['drill_nm']/1e6)[:2])!=(proof['diameter_nm'],proof['drill_nm']):
            raise ValueError('required_saved_supply_departure_ordinary_process_changed')
        observed.append(dict(pad_uuid=proof['pad_uuid'],via_uuid=force._uid(via),surface_path_mm=distance,
            exact_required_supply_column_constructed=True,current_capacity_inferred=False,release_authority=False))
    return observed
