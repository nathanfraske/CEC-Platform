"""No echo route for an already connected, Source-owned Ground cut.

This is a material-relation observer, NOT a remote SMD return, current or
cut authority. Only compiler-owned small Ground boundaries between literal
retained tracks/barrels can use it. A Source-owned process-qualified barrel
must actually contact every declared reference face. Every saved filled
island stays separate in the native graph; a whole zone UUID grants nothing.
All local returns, Source partitions and full saved receivers remain due.
"""
import math
import time
import pcbnew
import cec_force_current as force
import cec_fab_profile as fab
import cec_native_partition_pair as partitions
import cec_ground_return_shortcut as reference


def _scope(request):
    if (type(request)is not dict or request.get('kind')!='source_boundary'
            or request.get('net')!='GND'
            or request.get('every_surviving_source_component_port_mandatory')is not True):return None
    authorities=request.get('exact_additional_macro_component_source_ownership')
    if type(authorities)is not list or not 1<=len(authorities)<=64:return None
    literal_widths=[];class_widths=[];roots=set()
    for source in authorities:
        if (type(source)is not dict or source.get('kind')!='positive_existing_low_power_ground_boundary'
                or type(source.get('native_source_uuid'))is not str or not source['native_source_uuid']
                or source.get('source_width_preserved_not_aggregate_ground_injection_rating')is not True
                or source.get('every_source_partition_and_physical_return_still_requires_receiving')is not True
                or source.get('current_authority')is not False):return None
        values=[source.get(k)for k in('source_width_nm','source_full_class_width_nm')]
        if any(type(v)is not int or not 0<v<=20000000 for v in values):return None
        literal_widths.append(values[0]);class_widths.append(values[1])
        barrels=source.get('source_owned_barrel_roots')
        if type(barrels)is not list or len(barrels)>64:return None
        for barrel in barrels:
            if (type(barrel)is not dict or type(barrel.get('via_uuid'))is not str
                    or not barrel['via_uuid']or type(barrel.get('source_terminal_owners'))is not list
                    or not 1<=len(barrel['source_terminal_owners'])<=64):return None
            roots.add(barrel['via_uuid'])
    # A cut-component request records its literal old width; a full-class
    # demand may name the exact stricter floor. Reusing already connected
    # metal adds NOTHING and cannot cure inherited subfloor copper. Accept
    # only these two exact Source dimensions, never an arbitrary range.
    source_width=max(literal_widths);full_width=max(source_width,*class_widths)
    if (not roots or type(request.get('width_nm'))is not int
            or request['width_nm']not in(source_width,full_width)):return None
    return roots


def observe(board,request,*,timeout_s=10.):
    """Fresh exact native material observation; return None for unknown."""
    if type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10:
        raise ValueError('bounded_retained_ground_component_observation_required')
    started=time.monotonic();deadline=started+timeout_s;owned=_scope(request)
    if owned is None:return None
    import cec_cell_row_rebuild as row
    binding=row._source_binding(board);live={force._uid(t):t for t in board.GetTracks()}
    enabled=set(map(int,board.GetEnabledLayers().CuStack()));ports=[]
    for name in('a','b'):
        port=request.get(name,{})
        ids=port.get('native_uuids');point=port.get('at_nm');faces=port.get('layers')
        if (port.get('pad_uuid')is not None or type(ids)is not list or not 1<=len(ids)<=16
                or any(type(u)is not str or u not in live for u in ids)or len(set(ids))!=len(ids)
                or type(point)is not list or len(point)!=2 or any(type(n)is not int for n in point)
                or type(faces)is not list or not faces or len(set(faces))!=len(faces)
                or any(type(n)is not int or n not in enabled for n in faces)):return None
        for uid in ids:
            item=live[uid]
            if (item.GetClass()not in('PCB_TRACK','PCB_VIA')or item.GetNetname()!='GND'
                    or item.GetNetCode()<=0 or any(not item.IsOnLayer(face)
                        or not item.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*point),0)
                        for face in faces)):return None
        ports.append(ids)
    # A literal factory pickup track may name the exact barrel AXIS rather
    # than the barrel itself. Resolve only Source-owned, coaxial metal that
    # completely covers that pickup; never a nearest same-net hole.
    entries=[]
    for uid in sorted(owned&live.keys()):
        via=live[uid]
        if (via.GetClass()!='PCB_VIA'or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu):continue
        coaxial=[name for name in('a','b')if request[name]['at_nm']==list(via.GetPosition())
            and all(via.IsOnLayer(face)and all(live[u].GetClass()=='PCB_VIA'and u==uid
                or live[u].GetClass()=='PCB_TRACK'and live[u].GetWidth()<=via.GetWidth(face)
                for u in request[name]['native_uuids'])for face in request[name]['layers'])]
        if not coaxial:continue
        diameter,drill=via.GetWidth(via.TopLayer())/1e6,via.GetDrillValue()/1e6
        if (fab.board_legal_through_via_geometry(board,diameter,drill)[:2]!=(diameter,drill)
                and not fab.local_pofv_via_decision(board,via,allow_source_track_body=True)[0]):continue
        try:contacts=reference._reference_contacts(board,via)
        except ValueError:continue
        entries.append(dict(uuid=uid,literal_coaxial_endpoint_names=coaxial,
            actual_filled_reference_contacts=contacts))
    if not entries:return None
    if time.monotonic()>=deadline:raise ValueError('retained_ground_component_deadline')
    # Reuse the independently tested exact filled-island native inventory.
    # It adds ONLY unattached per-island proxies, never board material.
    inventory=partitions._inventory(board,deadline,dict(items=16384,polygons=4096,vertices=200000))
    keys=[force._item_key(live[u])for u in ports[0]+ports[1]+[v['uuid']for v in entries]]
    components={inventory['component_of'][key]for key in keys}
    if len(components)!=1:return None
    if time.monotonic()>=deadline:raise ValueError('retained_ground_component_deadline')
    if binding!=row._source_binding(board):raise ValueError('retained_ground_component_observer_changed_board')
    return dict(scope='exact_retained_ground_track_barrel_reference_component',
        source_endpoint_native_uuids=ports,entries=entries,all_named_contacts_connected=True,
        actual_native_retained_connectivity_proved=True,whole_zone_uuid_connectivity_credit=False,
        foreign_net_edges_excluded=True,remote_smd_return_not_inferred=True,new_copper=0,new_holes=0,
        original_physical_returns_and_saved_partitions_still_required=True,
        inherited_source_width_debt_present=any(
            a['source_width_nm']<a['source_full_class_width_nm']
            for a in request['exact_additional_macro_component_source_ownership']),
        inherited_source_width_not_qualified=True,
        current_qualified=False,routing_admitted=False,release_authority=False)
