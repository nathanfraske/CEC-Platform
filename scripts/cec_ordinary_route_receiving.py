"""Independently receive a bounded ordinary-signal route replacement.

An additive receiver cannot certify rip-up and repair. This receiver derives
electrical ownership from the immutable parent, reconstructs the exact retired
scope, proves every old terminal partition and removed segment boundary, and
then delegates exact new copper/ground/rule replay to the additive receiver.
It does NOT replace native DRC, field, pair, current, or release admission.
"""
from pathlib import Path
import math
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_current_topology as topology
import cec_field_coupling as field
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_synth_pipeline as synth
from cec_native_items import discard_items


def _ids(values, name, maximum):
    if (type(values) not in (list, tuple, set) or len(values) > maximum
            or any(type(v) is not str or not v for v in values)
            or len(set(values)) != len(values)):
        raise ValueError('invalid_' + name)
    return set(values)


def eligible_nets(board, source, board_hint):
    """No supply, ground, pair, analog-pair, clock, sense, or pour-owned net."""
    resolver = fr._project_netclass_resolver(str(source))
    with force._thermal_hint(board_hint):
        nets = set(fr._ordinary_final_completion_nets(board, resolver))
        nets -= set(topology.board_current_domains(board, board_hint))
        nets = {n for n in nets if synth.spec_net_current_contract(board_hint, n) is None}
    nets -= {str(z.GetNetname()) for z in board.Zones() if not z.GetIsRuleArea()}
    nets -= {str(p.GetNetname()) for fp in board.GetFootprints() for p in fp.Pads()
             if str(p.GetPinType()) in ('power_in','power_out')}
    specialized = {'power','gnd','ground','sense','kelvin','can','usb',
                   'differential','clock','rf','highspeed'}
    from cec_pair_semantics import split_termination_midpoints
    midpoints = split_termination_midpoints(board)
    nets = {n for n in nets if str((resolver(n) or {}).get('name','')).casefold() not in specialized
        or n in midpoints and str((resolver(n) or {}).get('name','')).casefold() == 'can'}
    return nets


def _partition(board, deadline, *, retired_uuids=(), retained_keys=None,
               _identity_rebindings=None):
    """Private native partitions of every surviving source conductor/land.

    Tracking pads alone loses a retained copper-only tee when its parent edge
    is detoured. The old graph includes retired edges, but its comparison
    vertices are all surviving native conductors and lands. New material is
    available for reachability without becoming a source identity.
    """
    # A separately proved native pose receiver may map ONLY its exact moved
    # pad identities back to source coordinates. Ordinary routing has no such
    # map; physical positions still distinguish cloned footprint children.
    def key(item):
        native=force._item_key(item)
        return (_identity_rebindings or {}).get(native,native)
    pads = [p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetCode() > 0]
    copper = list(board.GetTracks()) + [z for z in board.Zones() if not z.GetIsRuleArea()]
    if len(pads) > 16384 or len(copper) > 16384:
        raise ValueError('native_partition_inventory_bound')
    # Use the same exact per-island/per-face native inventory as the paired
    # receiver. A whole zone owner must NEVER connect disjoint polygons,
    # holes, other faces, or foreign nets. Stable proxy keys bind literal fill
    # geometry, not just the owner's UUID. This single-board API intentionally
    # requires exact retained fill keys: callers changing fill must use the
    # paired overlap-token receiver, not borrow another island's identity.
    import cec_native_partition_pair as paired
    inventory = paired._inventory(board,min(deadline,time.monotonic()+10.),
        dict(items=16384,polygons=4096,vertices=200000))
    objects = {force._item_key(i):i for i in inventory['objects']}
    # Retirement is named by actual authored native owners, never by a
    # derived filled-island UUID. Keep retired material IN the old graph:
    # it still defines the original connectivity obligations of survivors.
    # Only the comparison markers of explicitly retired owners are omitted.
    actual_retired_keys = {force._item_key(item) for item in [*pads, *copper]
        if force._uid(item) in retired_uuids}
    retired_zone_owners = {force._uid(zone) for zone in board.Zones()
        if not zone.GetIsRuleArea() and force._uid(zone) in retired_uuids}
    zone_proxy_owners = {force._item_key(row['item']): owner[0]
        for owner, rows in inventory['zones'].items() for row in rows}
    surviving = {native:key(item) for native,item in objects.items()
        if native not in actual_retired_keys
        and zone_proxy_owners.get(native) not in retired_zone_owners}
    if len(set(surviving.values())) != len(surviving):
        raise ValueError('ambiguous_native_conductor_identity')
    remaining = set(surviving.values())
    if retained_keys is not None:
        if not retained_keys <= remaining: raise ValueError('surviving_source_conductor_missing')
        remaining &= retained_keys
    parts=[]
    for component in inventory['components']:
        if time.monotonic() >= deadline: raise ValueError('ordinary_receiving_deadline')
        own={surviving[native] for native in component if native in surviving} & remaining
        if own:parts.append(own)
    return parts


def _retained_ordinary_pofv_contacts(parent, board, *, source, board_hint, deadline):
    """Continuity through unchanged, independently qualified SIGNAL barrels.

    This is not a width/current waiver or permission for new small vias.
    Both native inspections must prove the factory-profile SMD ownership;
    every source via property used for contact must remain exactly unchanged.
    Rated/specialized nets are excluded independently of the caller's claim.
    Saved subtract/add replay subsequently checks the complete native nodes.
    """
    nets = eligible_nets(parent, source, board_hint)
    def inventory(b):
        rows = {}
        layers = tuple(map(int, b.GetEnabledLayers().CuStack()))
        for via in b.GetTracks():
            if time.monotonic() >= deadline: raise ValueError('ordinary_receiving_deadline')
            if via.GetClass() != 'PCB_VIA' or str(via.GetNetname()) not in nets: continue
            uid = force._uid(via)
            if uid in rows: raise ValueError('ambiguous_retained_via_identity')
            signature = (str(via.GetNetname()), tuple(via.GetPosition()),
                tuple((layer, int(via.GetWidth(layer))) for layer in layers),
                int(via.GetDrillValue()), int(via.GetViaType()),
                int(via.TopLayer()), int(via.BottomLayer()), bool(via.IsLocked()))
            rows[uid] = (via, signature)
        return rows
    old, live = inventory(parent), inventory(board)
    result = set(); old_cache = {}; live_cache = {}
    for uid, (via, signature) in old.items():
        if time.monotonic() >= deadline: raise ValueError('ordinary_receiving_deadline')
        current = live.get(uid)
        if current is None or current[1] != signature: continue
        if (fab.local_pofv_via_decision(parent, via, cache=old_cache)[0]
                and fab.local_pofv_via_decision(board, current[0], cache=live_cache)[0]):
            result.add(uid)
    return result


def _incoming_ordinary_pofv_contacts(parent, board, incoming, *, source,
                                     board_hint, deadline):
    """Re-prove exact new ordinary local barrels, never rated via capacity.

    The parent supplies electrical eligibility. Only newly saved UUIDs in
    the generated local-via group qualify; proximity, dimensions, group name
    alone, or a changed source barrel do not. The subsequent subtract/add
    replay still proves unchanged pads/settings, exact rule scope and every
    native addition. This function grants continuity only, not ampacity.
    """
    incoming=_ids(incoming,'incoming_ordinary_via_contacts',256)
    if not incoming:return set()
    nets=eligible_nets(parent,source,board_hint)
    source_ids={force._uid(t) for t in parent.GetTracks()}
    if incoming & source_ids:
        raise ValueError('incoming_contact_is_not_new_native_material')
    if fab.board_profile_name(parent)!=fab.board_profile_name(board):
        raise ValueError('incoming_contact_changed_factory_profile')
    owned={force._uid(i) for g in board.Groups()
        if g.GetName()==fr.LOCAL_POFV_SIGNAL_VIA_GROUP for i in g.GetItems()}
    result=set();cache={}
    for via in board.GetTracks():
        if time.monotonic()>=deadline:raise ValueError('ordinary_receiving_deadline')
        uid=force._uid(via)
        if uid not in incoming:continue
        if (via.GetClass()=='PCB_VIA' and str(via.GetNetname()) in nets
                and uid in owned and via.IsLocked()
                and fab.local_pofv_via_decision(board,via,cache=cache,allow_source_track_body=True)[0]):
            result.add(uid)
    return result


def _exclusive_retired_vias(parent, requested, *, retired_tracks, nets, unlock, deadline):
    """Retire only obsolete ordinary barrels wholly owned by the exact cut.

    This never grants via-in-pad, power, pair, plane, or grouped-via deletion.
    Every actual source contact on every copper layer must be one of the
    independently typed retired tracks. Surviving native partitions and cut
    boundaries still have to be restored by the complete replacement.
    """
    inventory = {force._uid(t): t for t in parent.GetTracks()}
    grouped = {force._uid(i) for g in parent.Groups() for i in g.GetItems()}
    layers = tuple(parent.GetEnabledLayers().CuStack())
    items = [*(p for fp in parent.GetFootprints() for p in fp.Pads()),
             *parent.GetTracks()]
    if len(items) > 16384:
        raise ValueError('exclusive_via_source_inventory_bound')
    proofs = []
    for uid in sorted(requested):
        via = inventory.get(uid)
        if (via is None or via.GetClass() != 'PCB_VIA' or uid in grouped
                or str(via.GetNetname()) not in nets
                or via.IsLocked() and uid not in unlock
                or via.GetViaType() != pcbnew.VIATYPE_THROUGH
                or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu):
            raise ValueError('retired_via_not_exclusive_ordinary_through:' + uid)
        dia, drill, _ = fab.board_legal_through_via_geometry(parent,
            via.GetWidth(via.TopLayer()) / 1e6, via.GetDrillValue() / 1e6)
        if (via.GetWidth(via.TopLayer()) < round(dia * 1e6)
                or via.GetDrillValue() < round(drill * 1e6)):
            raise ValueError('exclusive_retired_via_factory_geometry_unknown:' + uid)
        contacts = set(); contact_layers = set()
        for item in items:
            if time.monotonic() >= deadline:
                raise ValueError('ordinary_receiving_deadline')
            other = force._uid(item)
            if other == uid:
                continue
            touched = [int(layer) for layer in layers if item.IsOnLayer(layer)
                and item.GetEffectiveShape(layer).Collide(via.GetEffectiveShape(layer), 0)]
            if not touched:
                continue
            if (other not in retired_tracks or item.GetClass() != 'PCB_TRACK'
                    or item.GetNetCode() != via.GetNetCode()):
                raise ValueError('exclusive_retired_via_has_surviving_or_unowned_contact:' + uid)
            contacts.add(other); contact_layers.update(touched)
        if not 2 <= len(contacts) <= 8 or len(contact_layers) < 2:
            raise ValueError('exclusive_retired_via_requires_exact_multilayer_departures:' + uid)
        proofs.append(dict(via_uuid=uid, net=str(via.GetNetname()),
            source_contact_track_uuids=sorted(contacts), contact_layers=sorted(contact_layers),
            no_surviving_land_barrel_or_track_contact=True,
            all_departures_in_exact_typed_retirement=True, release_authority=False))
    return proofs


def _redundant_single_face_vias(parent, requested, *, retired_tracks, nets, unlock, deadline):
    """Prove unused ordinary barrels after the separately typed track cut.

    A through via may be obsolete after native-component reattachment. Its
    remaining actual contacts must occupy exactly ONE enabled copper face.
    Any surviving pad, zone, foreign item, grouped contact or second face
    refuses this scope. Whole surviving native partitions still decide the
    final deletion; this grants no power/POFV or general barrel authority.
    """
    inventory={force._uid(t):t for t in parent.GetTracks()}
    grouped={force._uid(i) for g in parent.Groups() for i in g.GetItems()}
    layers=tuple(parent.GetEnabledLayers().CuStack())
    items=[*(p for fp in parent.GetFootprints() for p in fp.Pads()),
        *parent.GetTracks(),*(z for z in parent.Zones() if not z.GetIsRuleArea())]
    if len(items)>16384:raise ValueError('redundant_via_source_inventory_bound')
    proofs=[]
    for uid in sorted(requested):
        via=inventory.get(uid)
        if (via is None or via.GetClass()!='PCB_VIA' or uid in grouped
                or str(via.GetNetname()) not in nets or via.IsLocked() and uid not in unlock
                or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu):
            raise ValueError('redundant_via_not_source_ordinary_through:'+uid)
        dia,drill,_=fab.board_legal_through_via_geometry(parent,
            via.GetWidth(via.TopLayer())/1e6,via.GetDrillValue()/1e6)
        if (via.GetWidth(via.TopLayer())<round(dia*1e6)
                or via.GetDrillValue()<round(drill*1e6)):
            raise ValueError('redundant_via_factory_geometry_unknown:'+uid)
        contacts=set();faces=set()
        for item in items:
            if time.monotonic()>=deadline:raise ValueError('ordinary_receiving_deadline')
            other=force._uid(item)
            if other==uid or other in retired_tracks:continue
            touched=[]
            for face in layers:
                if not item.IsOnLayer(face):continue
                if item.GetClass()=='ZONE':
                    if not item.HasFilledPolysForLayer(face):
                        if item.Outline().Collide(via.GetEffectiveShape(face),0):
                            raise ValueError('redundant_via_native_zone_fill_unavailable:'+uid)
                        continue
                    if item.GetFilledPolysList(face).Collide(via.GetEffectiveShape(face),0):
                        touched.append(int(face))
                elif item.GetEffectiveShape(face).Collide(via.GetEffectiveShape(face),0):
                    touched.append(int(face))
            if not touched:continue
            if (item.GetClass()!='PCB_TRACK' or item.GetNetCode()!=via.GetNetCode()
                    or other in grouped or not 0<item.GetWidth()<500000):
                raise ValueError('redundant_via_has_surviving_land_or_unowned_contact:'+uid)
            contacts.add(other);faces.update(touched)
        if not 1<=len(contacts)<=8 or len(faces)!=1:
            raise ValueError('redundant_via_requires_one_actual_retained_copper_face:'+uid)
        proofs.append(dict(via_uuid=uid,net=str(via.GetNetname()),
            retained_contact_track_uuids=sorted(contacts),retained_contact_layers=sorted(faces),
            no_surviving_second_face_pad_zone_or_foreign_contact=True,
            final_native_partition_receiving_required=True,release_authority=False))
    return proofs


def _boundaries(parent, board, retired, deadline, *, ordinary_source=None, board_hint=None,
                incoming_ordinary_via_uuids=(), exclusive_retired_via_uuids=()):
    """Restore external cut boundaries, not obsolete internal bend coordinates.

    Zero-length 1 nm probes do not bridge a routing gap. The private native
    graph includes only this net's lands and conductors at least as wide as
    the displaced edge. Every probe needs contact with real saved copper, and
    all external ends of each connected removed branch must be in one
    component. Corners joined ONLY to other retired edges can disappear;
    retaining them would defeat rerouting. Complete surviving-copper
    partitions separately protect tees that touch the middle of an edge.
    Old narrow track neckdowns and larger net-level component counts cannot
    stand in for restored external boundaries. Explicit ordinary reception
    can include unchanged, source-qualified local signal POFV contacts and
    independently re-proved exact incoming ordinary local barrels; their
    annular web is not a trace-width test. Default/rated callers stay strict.
    This is ordinary continuity;
    it grants no barrel, current, or high-frequency capacity certificate.
    """
    proofs = []
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    tracks = list(board.GetTracks())
    retained_contacts = (_retained_ordinary_pofv_contacts(parent, board,
        source=ordinary_source, board_hint=board_hint, deadline=deadline)
        if ordinary_source is not None and board_hint is not None else set())
    if incoming_ordinary_via_uuids and (ordinary_source is None or board_hint is None):
        raise ValueError('incoming_contact_requires_source_ordinary_receiving')
    incoming_contacts=(_incoming_ordinary_pofv_contacts(parent,board,
        incoming_ordinary_via_uuids,source=ordinary_source,board_hint=board_hint,
        deadline=deadline) if incoming_ordinary_via_uuids else set())
    removed = {force._uid(t) for t in retired} | set(exclusive_retired_via_uuids)
    source_pads = [p for fp in parent.GetFootprints() for p in fp.Pads()]
    source_retained = [t for t in parent.GetTracks() if force._uid(t) not in removed]
    pending = {force._uid(t):t for t in retired}
    groups = []
    while pending:
        seed = pending.pop(min(pending)); group = [seed]; queue = [seed]
        while queue:
            a = queue.pop()
            for uid, b in list(pending.items()):
                if time.monotonic() >= deadline: raise ValueError('ordinary_receiving_deadline')
                if (a.GetNetname() == b.GetNetname() and a.GetLayer() == b.GetLayer()
                        and a.GetEffectiveShape(a.GetLayer()).Collide(b.GetEffectiveShape(b.GetLayer()),0)):
                    group.append(b); queue.append(b); del pending[uid]
        groups.append(group)
    for group in groups:
        if time.monotonic() >= deadline: raise ValueError('ordinary_receiving_deadline')
        old = group[0]
        net = str(old.GetNetname()); code = board.GetNetcodeFromNetname(net)
        if code <= 0: raise ValueError('retired_net_identity_missing')
        width = max(int(t.GetWidth()) for t in group); layer = int(old.GetLayer())
        anchors = set()
        for edge in group:
            for point in (edge.GetStart(), edge.GetEnd()):
                marker = pcbnew.SHAPE_SEGMENT(point,point,1)
                if any(str(i.GetNetname()) == net and i.IsOnLayer(layer)
                       and i.GetEffectiveShape(layer).Collide(marker,0)
                       for i in [*source_pads,*source_retained]):
                    anchors.add((int(point.x),int(point.y)))
        if not anchors:
            proofs.append(dict(net=net, retired_uuids=sorted(force._uid(t) for t in group),
                external_boundary_count=0, restored=True,
                basis='no_external_endpoint_contacts_surviving_junction_partitions_still_required'))
            continue
        items = [p for p in pads if str(p.GetNetname()) == net]
        items += [t for t in tracks if str(t.GetNetname()) == net and
                  ((t.GetClass() == 'PCB_TRACK' and t.GetWidth() >= width)
                   or (t.GetClass() == 'PCB_VIA' and
                       (t.GetWidth(t.TopLayer()) - t.GetDrillValue() >= width
                        or force._uid(t) in retained_contacts | incoming_contacts)))]
        if len(items) > 4096: raise ValueError('boundary_inventory_bound')
        probes = []
        for point in sorted(anchors):
            point = pcbnew.VECTOR2I(*point)
            p = pcbnew.PCB_TRACK(board); p.SetStart(point); p.SetEnd(point)
            p.SetWidth(1); p.SetLayer(layer); p.SetNetCode(code); probes.append(p)
        conn = pcbnew.CONNECTIVITY_DATA()
        for item in [*items, *probes]:
            if time.monotonic() >= deadline: raise ValueError('ordinary_receiving_deadline')
            if not conn.Add(item): raise ValueError('native_boundary_item_refused')
        reached = [list(conn.GetConnectedItems(p)) for p in probes]
        real = {force._item_key(i) for i in items}
        if any(not ({force._item_key(i) for i in rows} & real) for rows in reached):
            raise ValueError('retired_endpoint_has_no_saved_conductor:' + force._uid(old))
        connected = {force._item_key(i) for i in reached[0]} | {force._item_key(probes[0])}
        if any(force._item_key(p) not in connected for p in probes):
            raise ValueError('retired_endpoint_pair_not_restored:' + force._uid(old))
        proofs.append(dict(retired_uuids=sorted(force._uid(t) for t in group), net=net,
            layer=board.GetLayerName(layer), width_nm=width,
            retained_qualified_signal_via_contacts=sorted(force._uid(i) for i in items
                if i.GetClass() == 'PCB_VIA' and force._uid(i) in retained_contacts),
            incoming_qualified_signal_via_contacts=sorted(force._uid(i) for i in items
                if i.GetClass() == 'PCB_VIA' and force._uid(i) in incoming_contacts),
            external_boundary_count=len(anchors), anchors_nm=[list(p) for p in sorted(anchors)],restored=True))
    return proofs


def receive(source, candidate, *, retired_track_uuids, board_hint,
            allow_locked_track_uuids=(), retired_via_uuids=(),
            allow_locked_via_uuids=(), redundant_single_face_via_uuids=(),
            allow_redundant_cut_only=False, timeout_s=10.0,max_retired_tracks=32):
    """Receive an exact ordinary replacement, or an explicit redundant cut.

    A cut-only proposal still has to restore every external boundary and
    every original surviving native partition, re-prove exclusive barrels,
    and replay an exact source-minus-cut delta. It cannot delete power/pair/
    ground copper or import a pose, rule, fill or sidecar change. Defaults
    retain the historical nonempty incoming replacement requirement.
    """
    report = dict(schema=1, scope='bounded_ordinary_source_delta_receiving',
        ok=False, complete=False, errors=[], release_authority=False,
        inherited_debt_qualified=False, power_authority=False)
    started = time.monotonic()
    try:
        if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 30 or type(board_hint) is not str or not board_hint
                or type(allow_redundant_cut_only) is not bool
                or type(max_retired_tracks) is not int or not 1<=max_retired_tracks<=128):
            raise ValueError('invalid_ordinary_receiving_budget_or_identity')
        deadline = started + timeout_s
        requested = _ids(retired_track_uuids, 'retired_track_inventory', max_retired_tracks)
        unlock = _ids(allow_locked_track_uuids, 'locked_track_scope', max_retired_tracks)
        report['max_retired_tracks']=max_retired_tracks
        exclusive_ids = _ids(retired_via_uuids, 'exclusive_retired_via_inventory', 4)
        redundant_ids = _ids(redundant_single_face_via_uuids, 'redundant_single_face_via_inventory', 4)
        via_ids=exclusive_ids|redundant_ids
        via_unlock = _ids(allow_locked_via_uuids, 'exclusive_locked_via_scope', 4)
        if (not requested and not (allow_redundant_cut_only and redundant_ids)
                or not unlock <= requested or not via_unlock <= via_ids
                or requested & via_ids or exclusive_ids & redundant_ids or len(via_ids)>4):
            raise ValueError('explicit_nonempty_exact_retirement_scope_required')
        outgoing = requested | via_ids
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        families = [force._family(p, board_hint) for p in (source, candidate)]
        code = force._code_identity()
        _, first = additive._nodes(source); _, last = additive._nodes(candidate)
        if first.keys() - last.keys() != outgoing:
            raise ValueError('saved_retirement_differs_from_exact_scope')
        incoming = last.keys() - first.keys()
        if (len(incoming) > 256 or not incoming and not allow_redundant_cut_only
                or incoming and allow_redundant_cut_only):
            raise ValueError('incoming_ordinary_delta_bound')
        report['exact_redundant_ordinary_cut_only']=allow_redundant_cut_only
        parent = pcbnew.LoadBoard(str(source)); child = pcbnew.LoadBoard(str(candidate))
        tracks = {force._uid(t): t for t in parent.GetTracks()}
        nets = eligible_nets(parent, source, board_hint)
        grouped = {force._uid(i) for g in parent.Groups() for i in g.GetItems()}
        retired = []
        for uid in sorted(requested):
            t = tracks.get(uid)
            if (t is None or t.GetClass() != 'PCB_TRACK' or uid in grouped
                    or str(t.GetNetname()) not in nets or not 0 < t.GetWidth() < 500000
                    or (t.IsLocked() and uid not in unlock)):
                raise ValueError('retired_copper_not_scoped_ordinary_track:' + uid)
            retired.append(t)
        report['exclusive_retired_via_ownership'] = _exclusive_retired_vias(parent, exclusive_ids,
            retired_tracks=requested, nets=nets, unlock=via_unlock, deadline=deadline)
        report['redundant_single_face_via_ownership']=_redundant_single_face_vias(parent,redundant_ids,
            retired_tracks=requested,nets=nets,unlock=via_unlock,deadline=deadline)
        for t in child.GetTracks():
            if force._uid(t) in incoming and str(t.GetNetname()) not in nets:
                raise ValueError('incoming_copper_not_ordinary_owned')
        report['boundary_restoration'] = _boundaries(parent, child, retired, deadline,
            ordinary_source=source, board_hint=board_hint,
            exclusive_retired_via_uuids=via_ids,
            incoming_ordinary_via_uuids={force._uid(t) for t in child.GetTracks()
                if t.GetClass()=='PCB_VIA' and force._uid(t) in incoming})
        import cec_native_partition_pair as paired_partitions
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('ordinary_receiving_deadline')
        paired=paired_partitions.compare(parent,child,timeout_s=min(10.,remaining),
            retired_uuids=outgoing)
        report['paired_native_partition_preservation']={k:v for k,v in paired.items()
            if k not in ('source_parts','child_parts','demoted_parts')}
        report['paired_native_partition_preservation']['demoted_component_count']=len(paired['demoted_parts'])
        if paired['preserved']is not True:
            raise ValueError('prior_native_terminal_partition_lost')
        report['all_prior_native_terminal_partitions_preserved'] = True
        report['all_prior_surviving_copper_junctions_preserved'] = True
        with tempfile.TemporaryDirectory(prefix='cec-ordinary-receiving-') as work:
            projected = force._copy_family(source, Path(work)/'projected')
            # Copy the immutable parent and subtract only independently typed
            # requested tracks and separately proved exclusive ordinary vias.
            # No candidate pose/zone/settings are imported.
            basis = pcbnew.LoadBoard(str(projected))
            old_items = [t for t in basis.GetTracks() if force._uid(t) in outgoing]
            discard_items(basis, old_items)
            # Reconstruct source-minus-cut without serializing unrelated
            # footprints. KiCad may reorder a hidden property's children;
            # that is not authority to normalize opaque source records.
            # The independent native deletion still owns the full copper,
            # pad, zone and fill inventory of the literal projection.
            import cec_source_literal_retirement as literal_cut
            import cec_source_retaining_ses_import as raw
            raw.write_raw(projected,literal_cut.subtract(raw.raw_text(source),outgoing))
            if field._field_snapshot_inventory(pcbnew.LoadBoard(str(projected)))!=field._field_snapshot_inventory(basis):
                raise ValueError('literal_retirement_differs_from_independent_native_subtraction')
            _, reconstructed = additive._nodes(projected)
            if (reconstructed.keys() != first.keys() - outgoing or any(
                    sexpr._freeze(reconstructed[u]) != sexpr._freeze(first[u]) for u in reconstructed)):
                raise ValueError('retirement_reconstruction_changed_unrelated_material')
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise ValueError('ordinary_receiving_deadline')
            replay = additive.receive(projected, candidate, timeout_s=min(30., remaining))
            report['exact_subtract_add_ground_rule_replay'] = replay
            if replay.get('ok') is not True or replay.get('complete') is not True:
                raise ValueError('independent_ordinary_delta_replay_refused')
        stable = families == [force._family(p, board_hint) for p in (source, candidate)] and code == force._code_identity()
        report['source_candidate_and_code_unchanged'] = stable
        if not stable or time.monotonic() >= deadline:
            raise ValueError('ordinary_receiving_identity_or_deadline_changed')
        report.update(ok=True, complete=True, retired_track_uuids=sorted(requested),
            retired_via_uuids=sorted(via_ids), locked_via_scope_used=sorted(via_ids & via_unlock),
            added_native_uuids=sorted(incoming), locked_scope_used=sorted(requested & unlock),
            original_power_pair_sense_and_placement_geometry_exact=True)
    except Exception as exc:
        report['errors'].append(type(exc).__name__ + ':' + str(exc))
    report['elapsed_s'] = round(time.monotonic() - started, 6)
    return report
