"""Native local antipads for already Source-owned, carried Ground barrels.

Construction only. The complete saved macro receiver must independently
recompile ownership, motion, cuts and every terminal before replaying this
operation. A caller selects only existing barrel identities, never a zone,
polygon, role, clearance, dimension or current allowance. Authored pours and
all other native objects remain exact; current/field/Kelvin/DRC are still due.
"""
from contextlib import contextmanager
import math
import time
import uuid

import pcbnew
import cec_copper_echo as syntax
import cec_force_current as force
import cec_fr as fr
import cec_ground_via_clearance_window as geometry
import cec_native_fill_geometry as fills
import cec_native_frozen_zone_access as frozen
import cec_native_construction_frame as frame
import cec_signal_via_clearance_window as native
import cec_zone_fill as fill


def ids(value):
    if (type(value) not in (list, tuple) or len(value)>4
            or any(type(v) is not str for v in value) or len(set(value))!=len(value)):
        raise ValueError('bounded_unique_Source_Ground_barrel_window_identities_required')
    for v in value:
        try: valid=str(uuid.UUID(v))==v
        except (ValueError, AttributeError): valid=False
        if not valid:raise ValueError('literal_Source_Ground_barrel_UUID_required')
    return tuple(sorted(value))


def _deadline(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=10.:
        raise ValueError('bounded_Source_Ground_barrel_window_required')
    return time.monotonic()+seconds


def _tick(deadline):
    if time.monotonic()>=deadline:raise ValueError('Source_Ground_barrel_window_deadline')


def _snapshot(board,deadline):
    return frame.nodes(board,deadline)


def _authored(node):
    return syntax._freeze([v for v in node if not
        (isinstance(v,list) and v and v[0] in ('filled_polygon','fill_segments'))])


def _outside_faces(node,names):
    def selected(row):
        if not isinstance(row,list) or not row or row[0]!='filled_polygon':return False
        layers=[r[1].strip('"') for r in row[1:] if isinstance(r,list)
            and len(r)==2 and r[0]=='layer']
        if len(layers)!=1:raise ValueError('literal_Ground_window_fill_face_identity_required')
        return layers[0] in names
    return syntax._freeze([r for r in node if not selected(r)])


def _header(root):
    return syntax._freeze([n for n in root if not isinstance(n,list)
        or not any(isinstance(v,list)and v and v[0]=='uuid'for v in n)])


def _prepare_ground(board,deadline):
    """Only internally regenerate ordinary nonreserved Ground, before fill.

    Old Ground covering a moved signal via must not be used for native net
    propagation. The Source-zone entry fence precedes this step. All other
    native definitions and every authored net remain literal and unchanged.
    """
    before_root,before=_snapshot(board,deadline);chosen=pcbnew.ZONES();allowed=set()
    for zone in board.Zones():
        _tick(deadline)
        if (not zone.GetIsRuleArea()and zone.GetNetname()=='GND'
                and not any(fr._zone_is_route_reservation(board,zone,l)for l in zone.GetLayerSet().CuStack())):
            allowed.add(force._uid(zone));zone.UnFill();chosen.append(zone)
    result=fill.compile_selected(board,chosen,timeout_s=max(.001,deadline-time.monotonic()),initialize_selected=True)
    after_root,after=_snapshot(board,deadline)
    if before.keys()!=after.keys()or _header(before_root)!=_header(after_root):
        raise ValueError('Ground_window_preparation_changed_native_population_or_settings')
    for uid,node in before.items():
        same=(_authored(node)==_authored(after[uid])if uid in allowed else
            syntax._freeze(node)==syntax._freeze(after[uid]))
        if not same:raise ValueError('Ground_window_preparation_changed_non_Ground_or_authored_definition')
    return dict(complete=True,ordinary_nonreserved_Ground_uuids=sorted(allowed),native_fill=result,
        all_authored_nets_and_all_other_native_definitions_unchanged=True,
        saved_Ground_partitions_and_current_still_required=True,release_authority=False)


def _restore_source_fills(parent,board,deadline):
    """Reset generated zones on a private CUT replay, never on actual input.

    This takes no retirement IDs, and does not cut, own or qualify tracks.
    The enclosing saved receiver freshly compiles the CUT frame from Source;
    standalone preview use still grants no cut or saved admission authority.
    """
    _,source=_snapshot(parent,deadline);_,actual=_snapshot(board,deadline)
    old={force._uid(z):z for z in parent.Zones()};new={force._uid(z):z for z in board.Zones()}
    if old.keys()!=new.keys():raise ValueError('window_replay_Source_zone_population_changed')
    for uid,z in old.items():
        _tick(deadline);q=new[uid]
        if _authored(source[uid])!=_authored(actual[uid]):
            raise ValueError('window_replay_Source_zone_authorship_changed')
        q.UnFill()
        for layer in z.GetLayerSet().CuStack():
            if not z.HasFilledPolysForLayer(layer):continue
            shape=z.GetFilledPolysList(layer).CloneDropTriangulation()
            q.SetFilledPolysList(layer,shape)
            for index in range(shape.OutlineCount()):
                if z.IsIsland(layer,index):q.SetIsIsland(layer,index)
        q.SetIsFilled(z.IsFilled())
    _,restored=_snapshot(board,deadline)
    if any(syntax._freeze(source[u])!=syntax._freeze(restored[u])for u in old):
        raise ValueError('window_replay_cannot_reinstall_exact_Source_generated_records')


def _barrels(parent,board,transport,selected,deadline):
    if (type(transport) is not dict or transport.get('scope')!=
            'provisional_source_owned_smd_cohort_endpoint_transport'):
        raise ValueError('complete_typed_Source_Ground_barrel_transport_required')
    rows=transport.get('source_process_barrel_motion')
    if type(rows) is not list or len(rows)>64:
        raise ValueError('bounded_Source_process_barrel_inventory_required')
    owned={q['uuid']:q for q in rows}
    if len(owned)!=len(rows) or not set(selected)<=owned.keys():
        raise ValueError('window_must_name_an_actual_Source_owned_carried_barrel')
    before={force._uid(t):t for t in parent.GetTracks()}
    after={force._uid(t):t for t in board.GetTracks()}
    pads={force._uid(p):p for f in parent.GetFootprints() for p in f.Pads()}
    layers=tuple(map(int,parent.GetEnabledLayers().CuStack()))
    if layers!=tuple(map(int,board.GetEnabledLayers().CuStack())):
        raise ValueError('Source_Ground_window_stack_changed')
    result=[]
    for uid in selected:
        _tick(deadline)
        a,b=before.get(uid),after.get(uid);q=owned[uid]
        owners=q.get('source_owner_pad_uuids')
        if (a is None or b is None or a.GetClass()!='PCB_VIA' or b.GetClass()!='PCB_VIA'
                or a.GetNetname()!='GND' or b.GetNetname()!='GND'
                or type(owners) is not list or len(owners)!=1 or owners[0] not in pads
                or pads[owners[0]].GetNetname()!='GND'
                or pads[owners[0]].GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                or pads[owners[0]].HasHole()
                or tuple(a.GetPosition())==tuple(b.GetPosition())
                or not a.IsLocked() or not b.IsLocked()
                or a.GetViaType()!=pcbnew.VIATYPE_THROUGH or b.GetViaType()!=a.GetViaType()
                or int(a.TopLayer())!=int(pcbnew.F_Cu) or int(a.BottomLayer())!=int(pcbnew.B_Cu)
                or (a.TopLayer(),a.BottomLayer())!=(b.TopLayer(),b.BottomLayer())
                or a.GetDrillValue()!=b.GetDrillValue()
                or tuple(a.GetWidth(l) for l in layers)!=tuple(b.GetWidth(l) for l in layers)
                or a.Padstack().Mode()!=pcbnew.PADSTACK.MODE_NORMAL
                or b.Padstack().Mode()!=pcbnew.PADSTACK.MODE_NORMAL
                or len({a.GetWidth(l) for l in layers})!=1
                or not 0<a.GetDrillValue()<a.GetWidth(a.TopLayer())<=1000000):
            raise ValueError('same_actual_full_stack_Source_Ground_barrel_and_owner_required')
        old_groups=sorted((force._uid(g),g.GetName(),g.IsLocked()) for g in parent.Groups() if g.ContainsItem(a))
        new_groups=sorted((force._uid(g),g.GetName(),g.IsLocked()) for g in board.Groups() if g.ContainsItem(b))
        if old_groups!=new_groups:
            raise ValueError('Source_Ground_window_barrel_group_changed')
        if (not native.fab.local_pofv_via_decision(parent,a)[0]
                or not native.fab.local_pofv_via_decision(board,b)[0]):
            raise ValueError('Source_Ground_window_existing_actual_process_refused')
        result.append(b)
    return result


def _scope(parent,board,transport,selected,deadline):
    barrels=_barrels(parent,board,transport,selected,deadline)
    old={force._uid(z):z for z in parent.Zones()};new={force._uid(z):z for z in board.Zones()}
    if old.keys()!=new.keys() or len(old)>256:
        raise ValueError('Source_Ground_window_zone_population_changed')
    resolve=fr._foreign_clearance_resolver(board);records=[]
    for uid,z in sorted(old.items()):
        _tick(deadline)
        q=new[uid]
        if z.GetIsRuleArea() or z.GetNetname()=='GND':continue
        if (not z.IsFilled() or not q.IsFilled()
                or tuple(z.GetLayerSet().CuStack())!=tuple(q.GetLayerSet().CuStack())):
            raise ValueError('Source_Ground_window_actual_saved_foreign_fills_required')
        faces=[]
        for layer in z.GetLayerSet().CuStack():
            if not z.HasFilledPolysForLayer(layer):
                raise ValueError('Source_Ground_window_foreign_face_unknown')
            region=None;via_rows=[]
            for via in barrels:
                if not via.IsOnLayer(layer):continue
                gap=max(200000,int(board.GetDesignSettings().m_MinClearance),
                    int(resolve(z,layer)),int(z.GetLocalClearance()),
                    int(native.cells._netclass(board,'GND')['clearance']))
                diameter=via.GetWidth(layer)
                if not z.GetFilledPolysList(layer).Collide(pcbnew.SHAPE_CIRCLE(via.GetPosition(),diameter//2),gap):
                    continue
                if z.GetFillMode()!=pcbnew.ZONE_FILL_MODE_POLYGONS:
                    raise ValueError('Source_Ground_window_solid_native_fill_required')
                window,radius=geometry._window(z,via.GetPosition(),diameter,gap,parent)
                if region is None:region=window
                else:region.BooleanAdd(window)
                via_rows.append(dict(uuid=force._uid(via),at_nm=list(via.GetPosition()),
                    diameter_nm=diameter,gap_nm=gap,envelope_radius_nm=radius))
            if region is not None:faces.append((int(layer),region,via_rows))
        if faces:records.append((uid,z,q,faces))
    covered={v['uuid'] for _,_,_,fs in records for _,_,vs in fs for v in vs}
    if not 1<=len(records)<=8 or covered!=set(selected):
        raise ValueError('every_selected_Ground_barrel_requires_an_actual_bounded_foreign_antipad')
    return records


def _via_only(board,scope,deadline):
    """An antipad must not cure any pad or trace's Source-fill clearance.

    This uses the actual unmodified Source foreign fills before compilation.
    It cannot authorize even a short track corridor, or a small in-pad cap's
    larger pad-shaped clearance merely because that shape fits in the box.
    """
    resolve=fr._foreign_clearance_resolver(board)
    items=[*(p for fp in board.GetFootprints() for p in fp.Pads()),
        *(t for t in board.GetTracks()if t.GetClass()!='PCB_VIA')]
    for _,source,_,faces in scope:
        for layer,region,_ in faces:
            copper=source.GetFilledPolysList(layer)
            for item in items:
                _tick(deadline)
                if not item.IsOnLayer(layer) or item.GetNetname()==source.GetNetname():continue
                gap=max(200000,int(board.GetDesignSettings().m_MinClearance),
                    int(source.GetLocalClearance()),int(resolve(source,layer)),int(resolve(item,layer)))
                shape=item.GetEffectiveShape(layer)
                if region.Collide(shape,gap) and copper.Collide(shape,gap):
                    raise ValueError('only_via_antipad_not_pad_or_track_clearance:'+force._uid(item))


@contextmanager
def search_geometry(parent,board,transport,barrel_uuids,*,timeout_s=10.):
    """Only this Source-derived window-zone subset may expose actual fill."""
    selected=ids(barrel_uuids);deadline=_deadline(timeout_s)
    if not selected:
        yield None;return
    scope=_scope(parent,board,transport,selected,deadline)
    _via_only(board,scope,deadline)
    with frame.zone_snapshot(board,deadline)as path:
        with frozen.frozen(board,path,timeout_s=max(.001,deadline-time.monotonic()),
                zone_uuids=[r[0] for r in scope]) as proof:
            yield proof
    _tick(deadline)


def _compile_antipads(parent,board,transport,selected,deadline):
    """Private exact fill construction, deliberately not a clearance verdict.

    The independent priority UNCUT frame retains old positively owned edges;
    those are NOT a geometric routing frame. Only the actual CUT frame may
    receive the complete new-seat all-face guard in public apply below.
    """
    if not selected:raise ValueError('explicit_nonempty_Source_Ground_barrel_window_required')
    _,entry=_snapshot(board,deadline);_,source_nodes=_snapshot(parent,deadline)
    scope=_scope(parent,board,transport,selected,deadline)
    _via_only(board,scope,deadline)
    for node_uid,node in entry.items():
        if node[0]=='zone' and syntax._freeze(node)!=syntax._freeze(source_nodes.get(node_uid)):
            raise ValueError('carried_Ground_windows_require_original_Source_foreign_and_Ground_fills')
    # Ground is prepared on the actual CUT frame, not on UNCUT (whose
    # positively owned obsolete edges may intentionally cross a new seat).
    preparation=_prepare_ground(board,deadline)
    before_root,before=_snapshot(board,deadline)
    # Clone actual pre-fill native zones, retaining physical island markers.
    original=frame.clone(board,deadline)
    originals={force._uid(z):z for z in original.Zones()}
    chosen=pcbnew.ZONES()
    for uid,_,zone,_ in scope:zone.UnFill();chosen.append(zone)
    compiled=fill.compile_selected(board,chosen,timeout_s=max(.001,deadline-time.monotonic()),initialize_selected=True)
    proofs=[]
    for uid,_,zone,faces in scope:
        source=originals[uid];replacements={}
        allowed={layer for layer,_,_ in faces}
        for layer in source.GetLayerSet().CuStack():
            if int(layer) not in allowed and fills.identity(source.GetFilledPolysList(layer),deadline)!=fills.identity(zone.GetFilledPolysList(layer),deadline):
                raise ValueError('Ground_barrel_window_changed_an_unselected_foreign_face')
        for layer,region,via_rows in faces:
            constrained,proof=native._source_clipped_native_fill(source.GetFilledPolysList(layer),
                zone.GetFilledPolysList(layer),region,deadline)
            replacements[layer]=constrained
            proofs.append(dict(uuid=uid,net=str(source.GetNetname()),layer=layer,
                via_envelopes=via_rows,**proof))
        native._reinstall_native_faces(zone,replacements,deadline,source_zone=source)
    after_root,after=_snapshot(board,deadline)
    affected={r[0]:{pcbnew.LayerName(layer)for layer,_,_ in r[3]}for r in scope}
    if before.keys()!=after.keys():raise ValueError('Ground_barrel_window_native_population_changed')
    for uid,node in before.items():
        if uid in affected:
            if _outside_faces(node,affected[uid])!=_outside_faces(after[uid],affected[uid]):
                raise ValueError('Ground_barrel_window_changed_authored_zone_or_unselected_face')
        elif syntax._freeze(node)!=syntax._freeze(after[uid]):
            raise ValueError('Ground_barrel_window_changed_unowned_native_item')
    if _header(before_root)!=_header(after_root):raise ValueError('Ground_barrel_window_changed_native_board_settings')
    _tick(deadline)
    return dict(complete=True,scope='construction_only_Source_carried_Ground_barrel_native_antipads',
        barrel_uuids=list(selected),foreign_zone_faces=proofs,native_fill=compiled,
        internal_ordinary_Ground_preparation=preparation,
        authored_pours_and_all_other_native_items_unchanged=True,
        all_actual_barrel_faces_and_holes_checked=False,current_capacity_qualified=False,
        original_partitions_Ground_current_field_Kelvin_and_DRC_still_required=True,
        routing_admitted=False,release_authority=False)


def apply(parent,board,transport,barrel_uuids,*,timeout_s=10.):
    """Construct on one fresh CUT frame; no standalone role/admission grant."""
    selected=ids(barrel_uuids);deadline=_deadline(timeout_s)
    proof=_compile_antipads(parent,board,transport,selected,deadline)
    with search_geometry(parent,board,transport,selected,timeout_s=max(.001,deadline-time.monotonic())):
        live={force._uid(t):t for t in board.GetTracks()}
        for uid in selected:
            via=live[uid];diagnostics={}
            # _barrels accepts only actual uniform NORMAL padstacks. No
            # per-face land is silently projected to a smaller top land.
            if not fr._via_spot_clear(board,via.GetPosition(),via.GetWidth(via.TopLayer()),
                    max(200000,int(board.GetDesignSettings().m_MinClearance)),{via.GetNetCode()},
                    drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),existing_via_uuid=uid,
                    report=diagnostics):
                raise ValueError('Source_carried_Ground_window_actual_all_face_guard_refused:'+repr(diagnostics))
    _tick(deadline)
    proof['all_actual_barrel_faces_and_holes_checked']=True
    return proof


def priority_expected(parent,uncut,transport,barrel_uuids,actual,*,timeout_s=10.):
    """Fresh replay, not an earlier proof or caller-provided polygon waiver."""
    selected=ids(barrel_uuids);deadline=_deadline(timeout_s)
    if not selected or actual is None:
        raise ValueError('actual_macro_window_board_and_exact_barrels_required')
    # `actual` is the freshly Source-compiled CUT construction in the saved
    # receiver, never its incoming saved child. Do not fill UNCUT: old owned
    # edges are still there solely for full-population/priority comparison.
    # Regenerate from exact original Source zones, not caller window fills.
    # This is independent zone compilation, NOT a new cut-ownership proof.
    expected=frame.clone(actual,deadline)
    _restore_source_fills(parent,expected,deadline)
    proof=_compile_antipads(parent,expected,transport,selected,deadline)
    _,expected_nodes=_snapshot(expected,deadline);_,actual_nodes=_snapshot(actual,deadline)
    source_zones={force._uid(z):z for z in parent.Zones()}
    actual_zones={force._uid(z):z for z in actual.Zones()}
    if source_zones.keys()!=actual_zones.keys():
        raise ValueError('actual_macro_window_zone_population_changed')
    for uid,z in source_zones.items():
        same=(_authored(expected_nodes[uid])==_authored(actual_nodes[uid])
            if not z.GetIsRuleArea() and z.GetNetname()=='GND' else
            syntax._freeze(expected_nodes[uid])==syntax._freeze(actual_nodes[uid]))
        if not same:
            raise ValueError('actual_macro_foreign_fills_differ_from_independent_carried_Ground_windows')
    _tick(deadline)
    return expected,proof
