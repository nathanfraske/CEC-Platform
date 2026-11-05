"""Retire only an obsolete generated return beside a retained in-pad entry.

The old small barrel and its bounded surface kernel must have exactly one
capacitor ground land and one unchanged qualified in-pad root. Actual saved
plane material must already bridge both reference planes without the kernel.
This grants no ordinary stitch, mesh, component, current or release authority.
"""
from collections import deque
from pathlib import Path
import math
import time
import hashlib
import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_fab_profile as fab
import cec_device_bypass as caps
import cec_ground_plane_echo as echo
import cec_ground_dead_end_tail as tails
import cec_stale_local_ground_via as stale
import cec_kelvin_copper_cut as physical
from cec_native_items import discard_items


def _binding(board):
    # Copper-only equality cannot authorize a capacitance/technology or DNP
    # decision made from an unsaved part edit. Bind the actual component
    # metadata used by ownership as well as all of the native plane material.
    owners=sorted((force._uid(fp),fp.GetReference(),fp.GetValue(),fp.GetFPIDAsString(),
        fp.GetAttributes(),fp.IsDNP(),fp.IsLocked(),
        tuple(sorted((f.GetName(),f.GetText()) for f in fp.GetFields())))
        for fp in board.GetFootprints())
    groups=sorted((force._uid(g),g.IsLocked()) for g in board.Groups())
    return hashlib.sha256(repr((echo._binding(board),owners,groups)).encode()).hexdigest()


def plan(board, source, via_uuid, *, allow_source_locked=False, timeout_s=10.):
    deadline=tails._deadline(timeout_s)
    if type(via_uuid) is not str or not via_uuid or type(allow_source_locked) is not bool:
        raise ValueError('exact_source_redundant_local_ground_scope_required')
    source=Path(source).resolve();binding=_binding(board)
    private=pcbnew.LoadBoard(str(source))
    if binding!=_binding(private):
        raise ValueError('redundant_local_ground_requires_exact_saved_native_source')
    tracks=list(board.GetTracks());pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    if len(tracks)+len(pads)+len(list(board.Zones()))>16384:
        raise ValueError('redundant_local_ground_native_inventory_bound')
    live={force._uid(t):t for t in tracks};via=live.get(via_uuid)
    if (via is None or via.GetClass()!='PCB_VIA' or via.GetNetname()!='GND'
            or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
            or via.IsLocked() and not allow_source_locked):
        raise ValueError('explicit_generated_ground_barrel_required')
    def tick():
        if time.monotonic()>=deadline:raise ValueError('redundant_local_ground_native_deadline')
    layers=tuple(map(int,board.GetEnabledLayers().CuStack()))
    seeds=[]
    for item in [*pads,*tracks]:
        tick()
        if force._uid(item)==via_uuid:continue
        touched=[l for l in layers if item.IsOnLayer(l) and
            item.GetEffectiveShape(l).Collide(via.GetEffectiveShape(l),0)]
        if not touched:continue
        if (item.GetClass()!='PCB_TRACK' or item.GetNetname()!='GND'
                or len(touched)!=1 or touched[0] not in (pcbnew.F_Cu,pcbnew.B_Cu)):
            raise ValueError('obsolete_barrel_has_unowned_land_barrel_or_inner_departure')
        seeds.append(item)
    if not seeds or len({int(t.GetLayer()) for t in seeds})!=1:
        raise ValueError('one_bounded_outer_return_kernel_required')
    layer=int(seeds[0].GetLayer());pending=deque(force._uid(t) for t in seeds)
    retired=set();bound_pads=set();bound_vias=set();length=0.
    shapes={force._uid(t):t.GetEffectiveShape(layer) for t in [*tracks,*pads] if t.IsOnLayer(layer)}
    items={force._uid(t):t for t in [*tracks,*pads] if t.IsOnLayer(layer)}
    grouped={force._uid(t) for g in board.Groups() for t in g.GetItems()}
    surface_zones=[z for z in board.Zones() if not z.GetIsRuleArea() and z.IsOnLayer(layer)]
    while pending:
        tick();uid=pending.popleft()
        if uid in retired:continue
        item=live[uid]
        if (item.GetClass()!='PCB_TRACK' or item.GetNetname()!='GND'
                or item.GetParentGroup() is not None or uid in grouped
                or item.IsLocked() and not allow_source_locked
                or not 0<item.GetWidth()<=350000 or not item.GetLength()>0):
            raise ValueError('small_source_owned_surface_return_kernel_required')
        retired.add(uid);length+=item.GetLength()/1e6
        if len(retired)>8 or length>8.:
            raise ValueError('obsolete_return_kernel_work_bound')
        for zone in surface_zones:
            tick()
            if not zone.IsFilled() or not zone.HasFilledPolysForLayer(layer):
                if zone.Outline().Collide(shapes[uid],0):
                    raise ValueError('obsolete_return_surface_zone_material_unknown')
            elif zone.GetFilledPolysList(layer).Collide(shapes[uid],0):
                raise ValueError('obsolete_return_has_surface_zone_contact')
        for other,shape in shapes.items():
            tick()
            if other==uid or not shape.Collide(shapes[uid],0):continue
            peer=items[other]
            if peer.GetNetname()!='GND':raise ValueError('obsolete_return_has_foreign_native_contact')
            if peer.GetClass()=='PCB_TRACK':
                if other not in retired:pending.append(other)
            elif peer.GetClass()=='PAD':bound_pads.add(other)
            elif peer.GetClass()=='PCB_VIA':bound_vias.add(other)
            else:raise ValueError('obsolete_return_has_unknown_native_contact')
    if len(bound_pads)!=1 or len(bound_vias-{via_uuid})!=1:
        raise ValueError('one_retained_capacitor_land_and_one_inpad_root_required')
    pad=next(p for p in pads if force._uid(p) in bound_pads)
    owner=pad.GetParentFootprint();members=list(owner.Pads());farads=caps.capacitance_f(owner.GetValue())
    if (pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.HasHole()
            or owner.IsDNP() or len(members)!=2
            or not caps.capacitor_identity(owner.GetReference(),owner.GetFPIDAsString())
            or farads is None or not 0<farads<=1e-3
            or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole() for p in members)
            or len([p for p in members if p.GetNetname()=='GND'])!=1):
        raise ValueError('actual_two_land_local_capacitor_ground_owner_required')
    root=live[next(iter(bound_vias-{via_uuid}))]
    if (not stale._qualified_bridge(board,root)
            or not fab._pad_contains_circle(pad,root.GetPosition(),root.GetWidth(layer)//2)):
        raise ValueError('unchanged_qualified_fully_inpad_ground_entry_required')
    # Decode the real kernel union, not endpoint coincidence or a graph label.
    # Overlapping old stubs are permitted; actual loops/holes are not.
    poly=pcbnew.SHAPE_POLY_SET()
    for uid in sorted(retired):
        tick();part=pcbnew.SHAPE_POLY_SET()
        live[uid].TransformShapeToPolygon(part,layer,0,1000,pcbnew.ERROR_INSIDE)
        poly.BooleanAdd(part)
    try:actual=physical._poly(poly,physical._Work(deadline))
    except physical.Unknown as exc:
        raise ValueError('obsolete_return_kernel_actual_geometry_unknown:'+str(exc)) from exc
    if actual.geom_type!='Polygon' or actual.is_empty or len(actual.interiors):
        raise ValueError('one_hole_free_native_return_kernel_required')
    discard_items(private,[t for t in private.GetTracks() if force._uid(t) in retired])
    isolated=stale.plan(private,via_uuid,allow_source_locked=allow_source_locked,
        max_bridge_mm=3.,timeout_s=max(.001,deadline-time.monotonic()))
    if isolated['retained_root_via_uuid']!=force._uid(root):
        raise ValueError('actual_inpad_root_must_own_both_reference_plane_bridges')
    tick()
    return dict(schema=1,kind='obsolete_generated_capacitor_ground_return_kernel',
        source_sha256=force._hash(source),source_binding=binding,via_uuid=via_uuid,ground_net='GND',
        allow_source_locked=allow_source_locked,
        retired_track_uuids=sorted(retired|{via_uuid}),retired_via_uuids=[via_uuid],
        obsolete_surface_track_uuids=sorted(retired),source_kernel_length_mm=length,
        retained_root_via_uuid=force._uid(root),retained_capacitor_ground_pad_uuid=force._uid(pad),
        source_factory_owner_decision=list(fab.local_pofv_via_decision(board,via)),
        retained_inpad_factory_decision=list(fab.local_pofv_via_decision(board,root)),
        source_layer=layer,source_minus_kernel_stale_barrel_proof=isolated,
        actual_contact_plane_ids=isolated['actual_contact_plane_ids'],
        source_diameter_nm=via.GetWidth(via.TopLayer()),
        source_has_retained_fully_inpad_entry=True,
        ordinary_ground_stitch_retirement_authorized=False,current_qualified=False,release_authority=False)


def subtract(board,proposal,*,timeout_s=10.):
    fresh=plan(board,board.GetFileName(),proposal['via_uuid'],
        allow_source_locked=proposal['allow_source_locked'],timeout_s=timeout_s)
    if fresh!=proposal:raise ValueError('stale_or_forged_obsolete_ground_return_kernel')
    outgoing=set(fresh['retired_track_uuids'])
    discard_items(board,[t for t in board.GetTracks() if force._uid(t) in outgoing])


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    deadline=tails._deadline(timeout_s)
    r=tails._receive_exact_subtraction(source,candidate,proposal,board_hint=board_hint,
        subtractor=subtract,timeout_s=timeout_s)
    r.update(scope='obsolete_local_ground_return_kernel_subtraction',
        ordinary_ground_stitch_retirement_authorized=False)
    if r['ok'] and r['complete']:
        try:
            parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
            old=next(v for v in parent.GetTracks() if force._uid(v)==proposal['via_uuid'])
            retained=next(v for v in child.GetTracks() if force._uid(v)==proposal['retained_root_via_uuid'])
            if not stale._qualified_bridge(child,retained):
                raise ValueError('retained_inpad_entry_factory_context_lost')
            proofs=stale._witnesses(child,old,retained,set(proposal['actual_contact_plane_ids']),
                proposal['source_diameter_nm'],deadline)
            if {q['layer'] for q in proofs}!=set(proposal['actual_contact_plane_ids']):
                raise ValueError('obsolete_return_plane_bridge_after_refill_unproved')
            r['actual_saved_reference_plane_bridges']=proofs
        except (ValueError,StopIteration,physical.Unknown) as exc:
            r.update(ok=False,complete=False);r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def discover_from_drc(board,source,drc,*,authorize_source_locked=False,
                      include_source_factory_debt=False,timeout_s=2.):
    """Retype native errors, optionally actual generated-owner factory debt.

    A legacy exact-object DRU can hide a lost POFV owner from native DRC.
    This opt-in uses the actual source factory decision, never the existence
    of the tag alone, and still independently proves the whole capacitor
    return kernel and both real reference-plane bridges before any cut.
    """
    deadline=tails._deadline(timeout_s)
    if (type(drc) is not dict or type(authorize_source_locked) is not bool
            or type(include_source_factory_debt) is not bool):
        raise ValueError('bounded_native_ground_kernel_discovery_required')
    r=dict(complete=False,plans=[],refused=[],errors=[],release_authority=False,
        candidate_inventory_complete=False,stopped_after_first_received_scope=False)
    try:
        vias={force._uid(t) for t in board.GetTracks() if t.GetClass()=='PCB_VIA'
            and t.GetNetname()=='GND'}
        rows=drc.get('violations') or ()
        if len(rows)>16384:raise ValueError('ground_kernel_native_error_inventory_bound')
        ids={str(i.get('uuid') or '') for row in rows
            if row.get('type') in ('clearance','shorting_items','hole_clearance','via_dangling')
            for i in row.get('items') or () if str(i.get('uuid') or '') in vias}
        if include_source_factory_debt:
            generated={force._uid(t) for g in board.Groups()
                if g.GetName()==fr.LOCAL_POFV_SIGNAL_VIA_GROUP and not g.IsLocked()
                for t in g.GetItems()}
            for via in board.GetTracks():
                if time.monotonic()>=deadline:raise ValueError('ground_kernel_factory_inventory_deadline')
                if (force._uid(via) in vias&generated
                        and not fab.local_pofv_via_decision(board,via)[0]):ids.add(force._uid(via))
        ids=sorted(ids)
        if len(ids)>64:raise ValueError('ground_kernel_error_named_candidate_bound')
        for index,uid in enumerate(ids):
            if time.monotonic()>=deadline:raise ValueError('ground_kernel_discovery_deadline')
            try:
                r['plans'].append(plan(board,source,uid,allow_source_locked=authorize_source_locked,
                    timeout_s=max(.001,min(2.,deadline-time.monotonic()))))
            except ValueError as exc:r['refused'].append(dict(uuid=uid,reason=str(exc)))
            else:
                # The runtime commits ONE separately received source step.
                # Do not discard this complete scope because unrelated later
                # candidates consume the discovery lease. This is expressly
                # not a declaration that the remaining inventory is clean.
                r.update(complete=True,stopped_after_first_received_scope=True,
                    candidate_inventory_complete=index==len(ids)-1,
                    remaining_candidate_count=len(ids)-index-1)
                return r
        if time.monotonic()>=deadline:raise ValueError('ground_kernel_discovery_deadline')
        r.update(complete=True,candidate_inventory_complete=True,remaining_candidate_count=0)
    except ValueError as exc:r.update(plans=[],errors=[str(exc)])
    return r
