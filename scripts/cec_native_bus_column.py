"""Bounded full-current outer-face taps to actual retained native supply trunks.

An alternate surface can already carry the supply beneath a stranded bypass.
Reserve no phantom copper, infer no shared load, and never downgrade a class
or source-current floor. New through barrels must clear the complete enabled
stack and touch a positively sized retained trunk on the opposite face.
Only explicit rail-completion callers use this tier. It is not a local bypass
loop, plated-barrel ampacity, thermal, native-DRC or release qualification.
"""
import math
import time

import pcbnew
import cec_decoupler_cell as cells
import cec_device_bypass as bypass
import cec_device_power_roles as roles
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_field_coupling as field
import cec_native_current_capture as capture
import cec_native_supply_via_context as web
import cec_search_budget as budgets
from cec_native_items import discard_items


def _authority(board, net):
    authority=cells._supply_current_widths(board,net)
    if not authority:return None
    raw=authority['current_authority']
    if raw.get('source') not in ('board_design_basis','component_power_budget'):
        from cec_series_current_domain import validate_existing_domain_authority
        if not validate_existing_domain_authority(board, net, raw):
            raise ValueError('positive_existing_source_bus_current_required')
    from cec_route_dimensions import current_trace_widths
    # Physics tables use canonical copper identities, not display aliases
    # such as GND, SIG2 or PWR1 on the same real KiCad copper layers.
    layers=tuple(fab.enabled_copper_layers(board))
    profile=fab.active_profile_name(board)
    if profile!=authority['profile']:raise ValueError('actual_source_bus_profile_required')
    widths=current_trace_widths(raw,layers,profile,rise_c=30.)
    expected={board.GetLayerID(n):math.ceil(w*1e6) for n,w in widths.items()}
    if expected!=authority['required_by_layer_nm']:
        raise ValueError('complete_unchanged_source_bus_current_floors_required')
    return authority


def plan(board, owner_pad, supply_pad, *, source, board_hint,
         timeout_s=2., max_sites=32, max_feed_mm=1.5):
    """Read-only native proposal. Caller data never owns current or a trunk."""
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(max_sites) is not int or not 1<=max_sites<=64
            or type(max_feed_mm) not in (int,float) or not math.isfinite(max_feed_mm)
            or not 0<max_feed_mm<=1.5 or not source or not board_hint):
        raise ValueError('bounded_source_native_bus_column_required')
    deadline=time.monotonic()+timeout_s
    cap=supply_pad.GetParentFootprint();owner=owner_pad.GetParentFootprint()
    model=roles.footprint_contract(owner)
    if (not model or model['pins'].get(owner_pad.GetNumber()) not in ('power_input','power_output')
            or owner.IsDNP() or cap.IsDNP() or len(list(cap.Pads()))!=2
            or not bypass.capacitor_identity(cap.GetReference(),cap.GetFPIDAsString())
            or not bypass.local_bypass_technology(cap.GetValue(),cap.GetFPIDAsString())
            or bypass.capacitance_f(cap.GetValue()) is None
            or supply_pad.GetNetCode()<=0 or supply_pad.GetNetCode()!=owner_pad.GetNetCode()
            or {p.GetNetname() for p in cap.Pads()}!={'GND',supply_pad.GetNetname()}
            or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in cap.Pads())):
        return None
    # PAD.GetLayer() can retain F.Cu after a native flip while its actual
    # copper layer set is B.Cu. Electrical access comes from that layer set.
    faces=tuple(map(int,supply_pad.GetLayerSet().CuStack()))
    if len(faces)!=1:return None
    face=faces[0];opposite=pcbnew.B_Cu if face==pcbnew.F_Cu else pcbnew.F_Cu
    if face not in (pcbnew.F_Cu,pcbnew.B_Cu) or opposite not in board.GetEnabledLayers().CuStack():return None
    net=str(supply_pad.GetNetname());authority=_authority(board,net)
    if authority is None:return None
    planes={board.GetLayerID(n) for n in fr.plane_layers(board)}
    if face in planes or opposite in planes:return None
    spec=cells._netclass(board,net);floor=authority['required_by_layer_nm']
    width=max(spec['width'],floor[face],board.GetDesignSettings().m_TrackMinWidth)
    opposite_width=max(spec['width'],floor[opposite],board.GetDesignSettings().m_TrackMinWidth)
    trunks=[t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'
        and t.GetNetCode()==supply_pad.GetNetCode() and int(t.GetLayer())==opposite
        and t.GetWidth()>=opposite_width]
    if not trunks:return None
    guard=capture.Guard(board,source,net=net,board_hint=board_hint,
        timeout_s=max(.001,min(10.,deadline-time.monotonic())))
    if not guard.allows_endpoint({'native_uuids':[force._uid(supply_pad)]}):return None
    gap=max(spec['clearance'],board.GetDesignSettings().m_MinClearance,200000)
    diameter,drill,_=cells._board_legal_through_via_geometry(board,spec['via_dia'],spec['via_drill'])
    drill_nm=pcbnew.FromMM(drill)
    diameter_nm=max(pcbnew.FromMM(diameter),drill_nm+max(width,opposite_width))
    position=supply_pad.GetPosition()
    land_shape=supply_pad.GetEffectiveShape(face)
    box=land_shape.BBox()
    hx=max(position.x-box.GetX(),box.GetRight()-position.x)
    hy=max(position.y-box.GetY(),box.GetBottom()-position.y)
    # Native land extents plus the actual barrel radius give an off-land seat.
    # A 2 um outward reserve is not an assembly/foreign-clearance waiver.
    rx=math.ceil(hx+diameter_nm/2)+2000;ry=math.ceil(hy+diameter_nm/2)+2000
    offsets=[]
    for scale in (1.,1.25,1.5):
        for dx,dy in ((rx,0),(-rx,0),(0,ry),(0,-ry),
                (rx,ry),(-rx,ry),(rx,-ry),(-rx,-ry)):
            v=(round(dx*scale),round(dy*scale))
            if math.hypot(*v)<=max_feed_mm*1e6 and v not in offsets:offsets.append(v)
    binding=field._field_snapshot_inventory(board)
    for dx,dy in offsets[:max_sites]:
        if budgets.exhausted(deadline):return None
        point=pcbnew.VECTOR2I(position.x+dx,position.y+dy)
        probe=pcbnew.PCB_VIA(board);probe.SetPosition(point);probe.SetWidth(diameter_nm)
        probe.SetDrill(drill_nm);probe.SetViaType(pcbnew.VIATYPE_THROUGH)
        probe.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);probe.SetNetCode(supply_pad.GetNetCode())
        touched=[t for t in trunks if probe.GetEffectiveShape(opposite).Collide(t.GetEffectiveShape(opposite),0)
            and guard.allows_endpoint({'native_uuids':[force._uid(t)]})]
        if not touched:continue
        if (not fr._via_spot_clear(board,point,diameter_nm,gap,{supply_pad.GetNetCode()},
                drill_nm=drill_nm,net_code=supply_pad.GetNetCode())
                or not fr._edge_leg_clear(board,point,point,math.ceil(diameter_nm/2))
                or not all(guard(tuple(point),tuple(point),diameter_nm,int(l))
                    for l in board.GetEnabledLayers().CuStack())):continue
        legs=fr._guarded_profiled_lastmile_legs(board,position,point,width,face,gap,
            supply_pad.GetNetCode(),lambda a,b,h:fr._edge_leg_clear(board,a,b,h),
            foreign_cache={},allow_maze=False,deadline_monotonic=deadline,
            max_length_nm=round(max_feed_mm*1e6),
            run_guard=lambda a,b,w:guard(tuple(a),tuple(b),w,face))
        if not legs or any(w<width for a,b,w in legs):continue
        contract=dict(net=net,current_authority=authority['current_authority'],
            required_by_layer_mm={fab.COPPER_LAYER_IDS[int(l)]:w/1e6 for l,w in floor.items()},
            routing_layers=[fab.COPPER_LAYER_IDS[int(l)] for l in board.GetEnabledLayers().CuStack() if int(l) not in planes])
        if binding!=field._field_snapshot_inventory(board):raise ValueError('native_bus_column_plan_mutated_source')
        return dict(schema=1,source_binding=binding,source_current_contract=contract,
            source_profile=authority['profile'],supply_pad_uuid=force._uid(supply_pad),
            owner_pad_uuid=force._uid(owner_pad),retained_bus_track_uuids=sorted(force._uid(t) for t in touched),
            via_at_nm=list(point),via_diameter_nm=diameter_nm,via_drill_nm=drill_nm,
            legs=[dict(start_nm=list(a),end_nm=list(b),width_nm=w,layer=face) for a,b,w in legs],
            source_current_and_class_preserved=True,source_power_copper_retired=False,
            board_mutated=False,local_bypass_loop_qualified=False,
            plated_barrel_ampacity_qualified=False,release_authority=False)
    return None


def construct(board, owner_pad, supply_pad, *, source, board_hint,
              timeout_s=2., max_sites=32, max_feed_mm=1.5):
    """All-or-nothing PRIVATE additions; saved independent receiving required."""
    proposal=plan(board,owner_pad,supply_pad,source=source,board_hint=board_hint,
        timeout_s=timeout_s,max_sites=max_sites,max_feed_mm=max_feed_mm)
    if proposal is None:return None
    items=[]
    try:
        if field._field_snapshot_inventory(board)!=proposal['source_binding']:
            raise ValueError('native_bus_column_source_changed')
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I(*proposal['via_at_nm']))
        via.SetWidth(proposal['via_diameter_nm']);via.SetDrill(proposal['via_drill_nm'])
        via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetNetCode(supply_pad.GetNetCode());via.SetLocked(True);board.Add(via);items.append(via)
        for row in proposal['legs']:
            t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I(*row['start_nm']))
            t.SetEnd(pcbnew.VECTOR2I(*row['end_nm']));t.SetWidth(row['width_nm']);t.SetLayer(row['layer'])
            t.SetNetCode(supply_pad.GetNetCode());t.SetLocked(True);board.Add(t);items.append(t)
        native=web.receive(board,force._uid(via),proposal['source_current_contract'])
        if not native['ok'] or not native['complete']:raise ValueError('actual_native_bus_column_contact_floor_refused')
        return dict(status='linked-source-native-bus-column',items=items,vias=1,
            route_context='rail-island',proposal={k:v for k,v in proposal.items() if k!='source_binding'},
            actual_native_supply_contacts=native,local_bypass_loop_qualified=False,
            full_saved_native_receiving_required=True,plated_barrel_ampacity_qualified=False,
            release_authority=False)
    except Exception:
        discard_items(board,items)
        raise
