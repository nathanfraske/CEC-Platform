"""Reseat a source-selected low-power bypass return, without moving its lands.

Retype the actual manufacturer bypass and its endpoint-linear source tail.
Only its ordinary through barrel (or explicitly re-proved local POFV barrel)
may move, by <=1 mm,
with identical geometry and a no-longer return. Complete surviving native
partitions, existing proved short returns, original ground-plane contacts,
exact subtract/add replay and all-layer guards remain mandatory. This is not
bulk, converter, mesh, power-ground, current, thermal or release authority.
An opposite-surface return may stay immutable if its complete full-width
endpoint remains contained by the replacement barrel; it is never ripped up.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_redundant_bypass_ground as bypass
from cec_native_items import discard_items


def plan(board, pad_uuid, track_uuid, *, timeout_s=10.,
         allow_owned_locked=False, allow_qualified_local_vias=False,source_full_class=False,
         source_local_pad_entry=False):
    if any(type(value) is not bool for value in
            (allow_owned_locked, allow_qualified_local_vias,source_full_class,source_local_pad_entry)):
        raise ValueError('explicit_bypass_return_reconstruction_policy_required')
    if source_local_pad_entry and not(source_full_class and allow_qualified_local_vias):
        raise ValueError('source_class_and_saved_process_required_for_local_return_replacement')
    deadline = bypass._budget(timeout_s)
    source = bypass._plan_source_tail(board, pad_uuid, track_uuid, timeout_s=timeout_s,
                                     require_alternate_departure=False,source_full_class=source_full_class)
    tracks = {force._uid(i): i for i in board.GetTracks()}
    tail = [tracks[u] for u in source['retired_track_uuids']]
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    if any(t.IsLocked() for t in tail) and not allow_owned_locked:
        raise ValueError('bypass_return_source_tail_is_protected')
    pads = [p for f in board.GetFootprints() for p in f.Pads()]
    pad = next(p for p in pads if force._uid(p) == pad_uuid)
    cursor = next(tuple(q) for q in source['source_points_nm'] if pad.HitTest(pcbnew.VECTOR2I(*q)))
    start = cursor; points = [list(cursor)]
    for edge in tail:
        if time.monotonic() >= deadline:
            raise ValueError('bypass_return_source_inventory_deadline')
        ends = [tuple(edge.GetStart()), tuple(edge.GetEnd())]
        if cursor not in ends:
            raise ValueError('bypass_return_tail_not_endpoint_linear')
        cursor = ends[1] if cursor == ends[0] else ends[0]
        points.append(list(cursor))
    roots = [t for t in board.GetTracks() if t.GetClass() == 'PCB_VIA'
        and t.GetNetname() == 'GND' and tuple(t.GetPosition()) == cursor]
    if len(roots) != 1:
        raise ValueError('unique_exact_bypass_return_barrel_required')
    via = roots[0]; layers = list(board.GetEnabledLayers().CuStack())
    # The bypass root may also reach its owner's ground at the retained
    # capacitor land. No tee or other land inside the removed tail is owned
    # by this proposal, even if a ground plane would mask the lost branch.
    own_ids = {force._uid(t) for t in tail} | {force._uid(via),pad_uuid}
    root_marker = pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*start),pcbnew.VECTOR2I(*start),source['source_width_nm'])
    others = [*pads,*board.GetTracks(),*[z for z in board.Zones() if not z.GetIsRuleArea()]]
    for index,edge in enumerate(tail):
        for item in others:
            if time.monotonic()>=deadline:raise ValueError('bypass_return_source_inventory_deadline')
            if (force._uid(item) in own_ids or item.GetNetname()!='GND'
                    or not item.IsOnLayer(source['source_layer'])):continue
            shape = item.GetFilledPolysList(source['source_layer']) if item.GetClass()=='ZONE' else item.GetEffectiveShape(source['source_layer'])
            if not shape.Collide(edge.GetEffectiveShape(source['source_layer']),0):continue
            if (index==0 and item.GetClass()=='PCB_TRACK' and shape.Collide(root_marker,0)
                    and any(pad.HitTest(at) for at in (item.GetStart(),item.GetEnd()))):continue
            raise ValueError('bypass_return_tail_has_unowned_contact_or_tee')
    spec = cells._netclass(board, 'GND')
    diameter, drill, _ = fab.board_legal_through_via_geometry(board,
        max(.6, float(spec['via_dia'])), max(.3, float(spec['via_drill'])))
    local_barrel = (via.GetWidth(via.TopLayer()) < round(diameter*1e6)
        or via.GetDrillValue() < round(drill*1e6))
    if local_barrel and (not allow_qualified_local_vias
            or not fab.local_pofv_via_decision(board, via)[0]):
        raise ValueError('source_return_barrel_below_existing_ordinary_floor')
    via_groups = [g for g in board.Groups() if g.ContainsItem(via)]
    # This group is a regenerated factory ownership tag, not protected route
    # intent. Only an actually source-qualified local barrel may leave it;
    # independent saved replay re-proves the replacement's live SMD owner.
    local_factory_tag = (local_barrel and allow_qualified_local_vias
        and len(via_groups) == 1
        and via_groups[0].GetName() == fr.LOCAL_POFV_SIGNAL_VIA_GROUP
        and not via_groups[0].IsLocked())
    if (via.IsLocked() and not allow_owned_locked
            or force._uid(via) in grouped and not local_factory_tag
            or via.GetViaType() != pcbnew.VIATYPE_THROUGH
            or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu):
        raise ValueError('unprotected_ordinary_through_return_barrel_required')
    neighbours = [t for t in board.GetTracks() if force._uid(t) != force._uid(via)
        and t.GetNetname() == 'GND' and any(t.IsOnLayer(l) and
            t.GetEffectiveShape(l).Collide(via.GetEffectiveShape(l), 0) for l in layers)]
    # A full-width capsule may already overlap its final barrel one bend
    # before the literal endpoint. Every independently derived tail edge is
    # in this exact replacement; do not mistake one of those OWNED edges
    # for a surviving mesh branch. The default historical scope is intact.
    owned_barrel_contacts=({force._uid(t)for t in tail}if source_full_class else {force._uid(tail[-1])})
    retained = [i for i in neighbours if force._uid(i)not in owned_barrel_contacts]
    if (not any(force._uid(i)==force._uid(tail[-1]) for i in neighbours) or len(retained)>4
            or any(t.GetClass()!='PCB_TRACK' or t.GetLayer()==source['source_layer']
                or t.GetLayer() not in (pcbnew.F_Cu,pcbnew.B_Cu)
                or t.GetWidth()!=source['source_width_nm']
                or cursor not in (tuple(t.GetStart()),tuple(t.GetEnd())) for t in retained)):
        raise ValueError('bypass_return_barrel_has_unowned_live_branch')
    if any(p.GetNetname() == 'GND' and any(p.IsOnLayer(l) and
        p.GetEffectiveShape(l).Collide(via.GetEffectiveShape(l), 0) for l in layers) for p in pads):
        raise ValueError('bypass_return_barrel_contacts_another_land')
    planes = sorted(force._uid(z) for z in board.Zones() if not z.GetIsRuleArea()
        and z.GetNetname() == 'GND' and z.IsFilled() and any(z.IsOnLayer(l) and
            z.GetFilledPolysList(l).Collide(via.GetEffectiveShape(l), 0) for l in layers))
    if not planes:
        raise ValueError('bypass_return_barrel_has_no_native_filled_ground_contact')
    replacement=None
    if source_local_pad_entry:
        # Distinct from ordinary equal-geometry reseating: ONLY the actual
        # unchanged selected bypass land centre, using its EXISTING native
        # local rule, may replace the old remote barrel. No requested drill,
        # diameter, new rule, smaller setup floor or remote site is accepted.
        import cec_existing_local_pofv_pad_rule as saved_rule
        context=saved_rule.resolve(board,pad)
        groups=[g for g in board.Groups()if g.GetName()==saved_rule.GROUP]
        if (context is None or context.get('all_local_dimensions_at_or_above_ordinary_setup')is not True
                or len(groups)!=1 or groups[0].IsLocked()or retained
                or not 0<math.dist(tuple(pad.GetPosition()),tuple(via.GetPosition()))<=1500000):
            raise ValueError('literal_ordinary_floor_source_local_pad_return_context_required')
        limits=context['minimum_nm'];geometry=saved_rule.geometry(context,
            (limits['via_diameter']/1e6,limits['hole_size']/1e6))
        diameter,hole=[round(v*1e6)for v in geometry]
        if (not fab._pad_contains_circle(pad,pad.GetPosition(),(diameter+1)//2,tolerance_nm=0)
                or source['source_width_nm']>diameter):
            raise ValueError('whole_source_width_and_contained_source_ground_land_required')
        replacement=dict(source_context=context,group_uuid=force._uid(groups[0]),
            at_nm=list(pad.GetPosition()),diameter_nm=diameter,drill_nm=hole,
            maximum_remote_source_entry_distance_nm=1500000,
            exact_source_smd_entry_only=True,new_barrel_capacity_credited=False)
    if time.monotonic() >= deadline:
        raise ValueError('bypass_return_source_inventory_deadline')
    return dict(source, retired_via_uuid=force._uid(via), source_points_nm=points,
        source_local_pad_entry=source_local_pad_entry,replacement_source_local_pad_entry=replacement,
        actual_owned_source_tail_barrel_contact_uuids=sorted(force._uid(t)for t in neighbours
            if force._uid(t)in owned_barrel_contacts),
        allow_owned_locked=allow_owned_locked,
        allow_qualified_local_vias=allow_qualified_local_vias,
        source_local_barrel_independently_qualified=local_barrel,
        source_local_factory_group_uuids=([force._uid(via_groups[0])] if local_factory_tag else []),
        root_nm=list(cursor), root_diameter_nm=int(via.GetWidth(via.TopLayer())),
        root_drill_nm=int(via.GetDrillValue()), root_layers=[int(via.TopLayer()),int(via.BottomLayer())],
        root_width_by_layer_nm={str(int(l)):int(via.GetWidth(l)) for l in layers},
        retained_opposite_surface_contact_uuids=sorted(force._uid(t) for t in retained),
        source_ground_plane_uuids=planes, source_path_mm=sum(t.GetLength()/1e6 for t in tail),
        root_point_nm=list(start))


def subtract(board, proposal):
    if field._field_snapshot_inventory(board) != proposal['source_binding']:
        raise ValueError('bypass_return_source_binding_changed')
    typed_board=board
    if proposal.get('source_local_pad_entry',False):
        # The existing pad rule is bound to its literal immutable Source,
        # not to a later temporary-family pathname. Recompile it THERE;
        # separately require the complete native board and companions here
        # to remain identical. Never rewrite path-bearing proof packets to
        # make an old context look current on a different Source.
        context=proposal['replacement_source_local_pad_entry']['source_context']
        path=Path(context['source']).resolve(strict=True)
        if (force._hash(path)!=context['source_sha256']
                or force._sidecars(path)!=force._sidecars(Path(board.GetFileName()))):
            raise ValueError('literal_source_local_return_context_or_companions_changed')
        typed_board=pcbnew.LoadBoard(str(path))
        if field._field_snapshot_inventory(typed_board)!=proposal['source_binding']:
            raise ValueError('local_return_literal_source_native_scope_changed')
    actual = plan(typed_board, proposal['pad_uuid'], proposal['track_uuid'],
        allow_owned_locked=proposal.get('allow_owned_locked', False),
        allow_qualified_local_vias=proposal.get('allow_qualified_local_vias', False),
        source_full_class=proposal.get('source_full_class',False),
        source_local_pad_entry=proposal.get('source_local_pad_entry',False))
    if actual != proposal:
        raise ValueError('bypass_return_source_topology_changed')
    retired = set(proposal['retired_track_uuids']) | {proposal['retired_via_uuid']}
    discard_items(board, [t for t in board.GetTracks() if force._uid(t) in retired])


def receive(source, candidate, *, pad_uuid, track_uuid, board_hint, timeout_s=10.,
            allow_owned_locked=False, allow_qualified_local_vias=False,source_full_class=False,
            source_local_pad_entry=False):
    result = dict(schema=1, scope='source_selected_low_power_bypass_return_reseat',
        ok=False, complete=False, errors=[], current_authority=False, release_authority=False,
        inherited_debt_qualified=False, full_saved_board_receiving_still_required=True)
    try:
        deadline = bypass._budget(timeout_s)
        source, candidate = map(lambda p:Path(p).resolve(), (source,candidate))
        if source == candidate:
            raise ValueError('distinct_saved_bypass_return_candidates_required')
        families = [force._family(p,board_hint) for p in (source,candidate)]
        epoch = force._code_identity()
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        proposal = plan(parent,pad_uuid,track_uuid,timeout_s=min(10.,deadline-time.monotonic()),
            allow_owned_locked=allow_owned_locked,
            allow_qualified_local_vias=allow_qualified_local_vias,source_full_class=source_full_class,
            source_local_pad_entry=source_local_pad_entry)
        retired = set(proposal['retired_track_uuids']) | {proposal['retired_via_uuid']}
        _,old = additive._nodes(source); _,new = additive._nodes(candidate)
        if old.keys()-new.keys() != retired:
            raise ValueError('saved_bypass_return_retirement_differs_from_exact_source')
        incoming = new.keys()-old.keys()
        material = [t for t in child.GetTracks() if force._uid(t) in incoming]
        vias = [t for t in material if t.GetClass() == 'PCB_VIA']
        tracks = [t for t in material if t.GetClass() == 'PCB_TRACK']
        if (len(vias) != 1 or not 0 <= len(tracks) <= 8 or len(material) != len(incoming)
                or len(vias)+len(tracks) != len(material) or any(t.GetNetname()!='GND' for t in material)):
            raise ValueError('exactly_one_return_entry_and_bounded_ground_tail_required')
        via = vias[0]
        # A fully contained, selected-process via-in-pad needs no artificial
        # zero-length track. This is not authority for a disconnected remote
        # barrel: the exact unchanged selected land must contain its full
        # circular land, and the ordinary all-layer guard/replay still run.
        if not tracks:
            selected_pad = next(p for fp in child.GetFootprints() for p in fp.Pads()
                                if force._uid(p) == pad_uuid)
            if (not allow_qualified_local_vias or selected_pad.GetPosition()!=via.GetPosition()
                    or not fab._pad_contains_circle(selected_pad,via.GetPosition(),
                        (via.GetWidth(via.TopLayer())+1)//2,tolerance_nm=0)
                    or not fab.local_pofv_via_decision(child,via)[0]):
                raise ValueError('trackless_return_requires_exact_contained_qualified_pad_entry')
        layers = list(child.GetEnabledLayers().CuStack())
        local_entry=proposal['replacement_source_local_pad_entry']
        expected_drill=(local_entry['drill_nm']if local_entry else proposal['root_drill_nm'])
        expected_widths=({str(int(l)):local_entry['diameter_nm']for l in layers}
            if local_entry else proposal['root_width_by_layer_nm'])
        maximum_shift=local_entry['maximum_remote_source_entry_distance_nm']if local_entry else 1000000
        if (via.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or [int(via.TopLayer()),int(via.BottomLayer())] != proposal['root_layers']
                or via.GetDrillValue()!=expected_drill
                or {str(int(l)):int(via.GetWidth(l)) for l in layers} != expected_widths
                or not 0 < math.dist(list(via.GetPosition()),proposal['root_nm']) <= maximum_shift):
            raise ValueError('return_reseat_must_preserve_exact_barrel_and_local_scope')
        if local_entry:
            if tracks or list(via.GetPosition())!=local_entry['at_nm']:
                raise ValueError('source_local_replacement_requires_only_exact_contained_pad_entry')
            groups=[g for g in child.Groups()if force._uid(g)==local_entry['group_uuid']]
            if (len(groups)!=1 or groups[0].GetName()!=fr.LOCAL_POFV_SIGNAL_VIA_GROUP
                    or groups[0].IsLocked()or not groups[0].ContainsItem(via)
                    or not fab.local_pofv_via_decision(child,via)[0]):
                raise ValueError('source_local_return_requires_actual_saved_native_process_membership')
        by_uid = {force._uid(t):t for t in child.GetTracks()}
        for uid in proposal['retained_opposite_surface_contact_uuids']:
            entry = by_uid.get(uid)
            if (entry is None or entry.GetClass()!='PCB_TRACK'
                    or tuple(proposal['root_nm']) not in (tuple(entry.GetStart()),tuple(entry.GetEnd()))
                    or math.dist(list(via.GetPosition()),proposal['root_nm'])+
                        entry.GetWidth()/2 > via.GetWidth(entry.GetLayer())/2):
                raise ValueError('retained_full_width_return_endpoint_not_contained')
        minimum = max(child.GetDesignSettings().m_TrackMinWidth,
            round(float((fr._project_netclass_resolver(str(source))('GND') or {}).get('track_width') or .2)*1e6))
        cursor = tuple(proposal['root_point_nm']); target = tuple(via.GetPosition())
        used = set(); length = 0.
        while cursor != target:
            if time.monotonic()>=deadline:raise ValueError('bypass_return_receiving_deadline')
            choices = [t for t in tracks if force._uid(t) not in used
                and cursor in (tuple(t.GetStart()),tuple(t.GetEnd()))]
            if len(choices)!=1:raise ValueError('replacement_bypass_return_not_endpoint_linear')
            edge = choices[0]; used.add(force._uid(edge)); length += edge.GetLength()/1e6
            if (edge.GetWidth()!=proposal['source_width_nm'] or edge.GetWidth()<minimum
                    or edge.GetLayer()!=proposal['source_layer']):
                raise ValueError('replacement_bypass_return_width_or_surface_changed')
            cursor = tuple(edge.GetEnd()) if cursor==tuple(edge.GetStart()) else tuple(edge.GetStart())
        if len(used)!=len(tracks) or length>proposal['source_path_mm']+1e-6:
            raise ValueError('selected_bypass_return_length_worsened_or_extra_material')
        if (proposal['source_local_barrel_independently_qualified']
                and not fab.local_pofv_via_decision(child, via)[0]):
            raise ValueError('replacement_local_return_barrel_lost_native_process_owner')
        if not all(any(force._uid(z)==uid and z.GetNetname()=='GND' and z.IsFilled()
            and any(z.IsOnLayer(l) and z.GetFilledPolysList(l).Collide(via.GetEffectiveShape(l),0)
                    for l in layers) for z in child.Zones()) for uid in proposal['source_ground_plane_uuids']):
            raise ValueError('replacement_bypass_entry_lost_original_ground_plane')
        first = ordinary._partition(parent,deadline,retired_uuids=retired)
        keys = set().union(*first); last = ordinary._partition(child,deadline,retained_keys=keys)
        if any(not any(p<=q for q in last) for p in first):
            raise ValueError('bypass_return_reseat_lost_surviving_native_partition')
        oldpads = {force._uid(p):p for fp in parent.GetFootprints() for p in fp.Pads() if p.GetNetname()=='GND'}
        newpads = {force._uid(p):p for fp in child.GetFootprints() for p in fp.Pads() if p.GetNetname()=='GND'}
        for uid,pad in oldpads.items():
            if time.monotonic()>=deadline:raise ValueError('bypass_return_short_return_receiving_deadline')
            before = cells._existing_return(parent,pad,3.5)
            if before is None:continue
            after = cells._existing_return(child,newpads[uid],3.5)
            if after is None or after[0]>before[0]+1e-6:
                raise ValueError('existing_proved_short_ground_return_worsened:'+uid)
        with tempfile.TemporaryDirectory(prefix='cec-bypass-return-replay-') as work:
            projected = force._copy_family(source,Path(work)/'projected')
            base = pcbnew.LoadBoard(str(projected)); subtract(base,proposal)
            field._save_field_snapshot(base,projected)
            _,nodes = additive._nodes(projected)
            factory_groups=set(proposal['source_local_factory_group_uuids'])
            if nodes.keys()!=old.keys()-retired or any(
                    not exact_factory_group_subtraction(old[u],nodes[u],{proposal['retired_via_uuid']})
                    if u in factory_groups else sexpr._freeze(nodes[u])!=sexpr._freeze(old[u])
                    for u in nodes):
                raise ValueError('bypass_return_subtraction_changed_unowned_material')
            spec = fr._project_netclass_resolver(str(source))('GND') or {}
            gap = max(base.GetDesignSettings().m_MinClearance,round(float(spec.get('clearance') or .2)*1e6))
            # An explicitly allowed, independently re-qualified replacement
            # may use its own unchanged bypass land. Preserve that exact
            # native owner context at the all-layer guard; omitting it made
            # legal in-pad replacements fail the generic pad exclusion.
            local_owner = None
            if allow_qualified_local_vias and fab.local_pofv_via_decision(child, via)[0]:
                import cec_existing_local_pofv_pad_rule as saved_pad_rule
                selected_pad = next(p for fp in base.GetFootprints() for p in fp.Pads()
                                    if force._uid(p) == proposal['pad_uuid'])
                # This narrow saved-rule context applies only at the literal
                # pad centre and only if actually present. Off-centre legal
                # dogbones must use native board floors, not a forged rule.
                if saved_pad_rule.inspect(base,selected_pad,via.GetPosition(),
                        via.GetWidth(via.TopLayer()),via.GetDrillValue(),via.GetNetCode()) is not None:
                    local_owner = selected_pad
            diagnostic={}
            clear=fr._via_spot_clear(base,via.GetPosition(),via.GetWidth(via.TopLayer()),gap,
                {via.GetNetCode()},drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),foreign_cache={},
                local_pofv_pad=local_owner,report=diagnostic)
            result['replacement_barrel_native_clearance']=diagnostic
            if not clear:
                raise ValueError('replacement_bypass_barrel_all_layer_guard_refused')
            if any(not fr._edge_leg_clear(base,t.GetStart(),t.GetEnd(),math.ceil(t.GetWidth()/2+gap))
                or not fr._tap_foreign_clear(base,t.GetStart(),t.GetEnd(),t.GetWidth(),t.GetLayer(),gap,
                    {t.GetNetCode()},foreign_cache={}) for t in tracks):
                raise ValueError('replacement_bypass_tail_native_guard_refused')
            proof = additive.receive(projected,candidate,timeout_s=min(10.,deadline-time.monotonic()))
            result['independent_source_cut_additions_ground_and_rule_replay'] = proof
            if proof.get('ok') is not True or proof.get('complete') is not True:
                raise ValueError('bypass_return_exact_saved_replay_refused')
        if (time.monotonic()>=deadline or families != [force._family(p,board_hint) for p in (source,candidate)]
                or epoch!=force._code_identity()):
            raise ValueError('bypass_return_source_candidate_code_or_deadline_changed')
        result.update(ok=True,complete=True,source_candidate_and_code_unchanged=True,
            retired_track_uuids=proposal['retired_track_uuids'],retired_via_uuids=[proposal['retired_via_uuid']],
            added_native_uuids=sorted(incoming),source_path_mm=proposal['source_path_mm'],new_path_mm=length,
            source_proposal={k:v for k,v in proposal.items() if k!='source_binding'},
            source_barrel_geometry_preserved=local_entry is None,new_barrel_ampacity_credited=False,
            replacement_uses_only_exact_existing_source_pad_rule=local_entry is not None,
            retained_opposite_surface_contacts=proposal['retained_opposite_surface_contact_uuids'],
            source_local_factory_group_uuids=proposal['source_local_factory_group_uuids'],
            all_surviving_partitions_and_proved_short_returns_preserved=True,
            main_force_copper_poses_and_power_fills_exact=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def exact_factory_group_subtraction(before, after, retired_vias):
    """Metadata-only deletion of exactly independently proved native vias.

    Callers must derive the group identity from the retyped source proposal,
    not a received label. Empty/deleted group identities are deliberately
    outside this tier; every other field and surviving member stays exact.
    """
    return bool(before[0]=='group' and after[0]=='group'
        and before[1]=='"'+fr.LOCAL_POFV_SIGNAL_VIA_GROUP+'"'
        and additive._without(before,'members')==additive._without(after,'members')
        and additive._members(after)==additive._members(before)-set(retired_vias)
        and additive._members(after))


def construct_source_local_pad_entry(source,candidate,*,board_hint,pad_uuid,track_uuid,timeout_s=10.):
    """Fresh Source scope, geometry and save, each explicitly <=10 seconds.

    A request supplies identities ONLY. The Source's selected low-power
    bypass, full Ground width, exact local rule and native SMD land derive
    every retired object and every replacement dimension/position. This is
    a private constructor; independent saved and whole-parent receiving are
    still mandatory. No Source or other PCB is selected/overwritten.
    """
    import cec_source_literal_retirement as literal
    import cec_additive_pair_repair as saving
    source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
    if (type(board_hint)is not str or not board_hint or source==candidate
            or force._hash(source)!=force._hash(candidate)
            or force._sidecars(source)!=force._sidecars(candidate)):
        raise ValueError('exact_private_source_copy_and_design_context_required')
    seconds=float(timeout_s)if type(timeout_s)in(int,float)else 0.
    bypass._budget(timeout_s)
    code=force._code_identity();family=force._family(source,board_hint);started=time.monotonic();phases=[]
    board=pcbnew.LoadBoard(str(source))
    with force._thermal_hint(board_hint):
        proposal=plan(board,pad_uuid,track_uuid,timeout_s=seconds,allow_owned_locked=True,
            allow_qualified_local_vias=True,source_full_class=True,source_local_pad_entry=True)
    phases.append(dict(name='source_scope',elapsed_s=time.monotonic()-started))
    at=time.monotonic();subtract(board,proposal)
    pad=next(p for fp in board.GetFootprints()for p in fp.Pads()if force._uid(p)==pad_uuid)
    entry=proposal['replacement_source_local_pad_entry'];spec=fr._project_netclass_resolver(str(source))('GND')or{}
    gap=max(200000,int(board.GetDesignSettings().m_MinClearance),round(float(spec.get('clearance')or .2)*1e6))
    diagnostic={};net=pad.GetNetCode();position=pcbnew.VECTOR2I(*entry['at_nm'])
    if not fr._via_spot_clear(board,position,entry['diameter_nm'],gap,{net},drill_nm=entry['drill_nm'],
            net_code=net,local_pofv_pad=pad,report=diagnostic):
        raise ValueError('fresh_source_local_return_barrel_refused:'+str(diagnostic))
    outgoing=set(proposal['retired_track_uuids'])|{proposal['retired_via_uuid']}
    literal.write_native_projection(source,candidate,outgoing,board)
    before={force._uid(t)for t in board.GetTracks()}
    via=pcbnew.PCB_VIA(board);via.SetPosition(position);via.SetNetCode(net)
    via.SetWidth(entry['diameter_nm']);via.SetDrill(entry['drill_nm'])
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetLocked(True);board.Add(via)
    next(g for g in board.Groups()if force._uid(g)==entry['group_uuid']).AddItem(via)
    phases.append(dict(name='native_geometry_and_literal_cut',elapsed_s=time.monotonic()-at))
    if phases[-1]['elapsed_s']>=seconds:raise ValueError('source_local_return_geometry_phase_deadline')
    at=time.monotonic();saved={};saving.save_native_additions(candidate,board,saved,before,board_hint=board_hint)
    phases.append(dict(name='native_save',elapsed_s=time.monotonic()-at))
    if phases[-1]['elapsed_s']>=seconds:raise ValueError('source_local_return_save_phase_deadline')
    if code!=force._code_identity()or family!=force._family(source,board_hint):
        raise ValueError('local_return_source_or_code_changed')
    return dict(complete=True,candidate=str(candidate),candidate_sha256=force._hash(candidate),
        independently_compiled_source_scope={k:v for k,v in proposal.items()if k!='source_binding'},
        replacement_barrel_native_clearance=diagnostic,save=saved,phases=phases,
        source_and_code_unchanged=True,source_selected=False,current_authority=False,
        release_authority=False,whole_saved_and_parent_receiving_still_required=True)
