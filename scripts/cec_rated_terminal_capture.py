"""Read-only reservation of actual full-source SMD launch cross sections.

Pad DRC alone does not reserve the wider native launch that its existing
current contract needs. This checker rederives current and class floors and
permits only existing manufacturer-typed, bounded class-only supply prefixes.
It promises neither a complete route nor terminal/barrel ampacity.
"""
import math,time
import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_fab_profile as fab
import cec_decoupler_cell as cells
import cec_full_current_supply_prefix as prefix
import cec_pad_surface_access as surface
import cec_native_current_capture as control
import cec_field_coupling as field
from cec_native_bus_column import _authority


def receive(board,source,*,board_hint,pad_uuids,timeout_s=2.):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or not isinstance(pad_uuids,(list,tuple)) or not 1<=len(pad_uuids)<=8
            or any(type(u) is not str or not u for u in pad_uuids)
            or len(set(pad_uuids))!=len(pad_uuids)):
        raise ValueError('bounded_exact_rated_terminal_capture_required')
    deadline=time.monotonic()+timeout_s
    before=field._field_snapshot_inventory(board)
    r=dict(schema=1,ok=False,complete=False,terminals=[],errors=[],release_authority=False,
        no_path_proof=False,full_route_proved=False,terminal_ampacity_qualified=False)
    try:
        lookup={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
        with force._thermal_hint(board_hint):
            for uid in pad_uuids:
                if time.monotonic()>=deadline:raise ValueError('rated_terminal_capture_deadline')
                p=lookup.get(uid)
                if (p is None or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole()
                        or p.GetNetCode()<=0 or p.GetParentFootprint().IsDNP()):
                    raise ValueError('actual_populated_native_smd_source_terminal_required')
                net=str(p.GetNetname());authority=_authority(board,net)
                if authority is None:raise ValueError('positive_existing_source_current_required')
                spec=cells._netclass(board,net)
                g=control.Guard(board,source,net=net,board_hint=board_hint,
                    timeout_s=max(.001,min(2.,deadline-time.monotonic())))
                if not g.allows_endpoint({'native_uuids':[uid]}):
                    raise ValueError('source_terminal_control_role_unqualified')
                gap=max(200000,spec['clearance'],board.GetDesignSettings().m_MinClearance)
                faces=[]
                for layer in p.GetLayerSet().CuStack():
                    if layer in {board.GetLayerID(n) for n in fr.plane_layers(board)}:continue
                    width=max(spec['width'],authority['required_by_layer_nm'][layer],
                        board.GetDesignSettings().m_TrackMinWidth)
                    class_width=width;role=prefix.supply_terminal_role(p);bounded=None
                    if role is not None:
                        raw=fr._pad_local_escape(p,width,gap,board.GetDesignSettings().m_TrackMinWidth)
                        if raw is not None:
                            width=max(raw[0],authority['required_by_layer_nm'][layer],
                                board.GetDesignSettings().m_TrackMinWidth)
                            if width<class_width:bounded=dict(width_nm=width,
                                budget_nm=min(raw[1],1000000),terminal_role=role,
                                saved_prefix_and_full_class_throat_receiving_required=True)
                    pos=p.GetPosition();native=surface.contact(p,layer,list(pos))
                    clear=(native['ok'] is True and g(tuple(pos),tuple(pos),width,int(layer))
                        and fr._edge_leg_clear(board,pos,pos,math.ceil(width/2))
                        and fr._tap_foreign_clear(board,pos,pos,width,int(layer),gap,
                            {p.GetNetCode()},foreign_cache={}))
                    faces.append(dict(layer=fab.COPPER_LAYER_IDS[int(layer)],clear=bool(clear),
                        actual_source_width_nm=width,preferred_class_width_nm=class_width,
                        class_only_prefix=bounded,unchanged_current_authority=authority['current_authority']))
                if not faces:raise ValueError('actual_source_terminal_face_required')
                r['terminals'].append(dict(pad_uuid=uid,net=net,at_nm=list(p.GetPosition()),
                    faces=faces,ok=all(f['clear'] for f in faces)))
        if before!=field._field_snapshot_inventory(board):
            raise ValueError('rated_terminal_capture_mutated_source')
        if time.monotonic()>=deadline:raise ValueError('rated_terminal_capture_deadline')
        r.update(complete=True,ok=all(t['ok'] for t in r['terminals']))
    except Exception as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
