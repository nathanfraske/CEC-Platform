"""Retire one redundant departure of a uniquely selected local GND bypass.

This is not mesh rip-up authority. The actual manufacturer-typed owner,
one-to-one bypass assignment, two-land ceramic and exact small source edge
are rederived, including its <=4-edge unbranched endpoint tail. Only
subtraction is allowed in this phase. Independent native
partitions and all already-proved <=3.5 mm GND returns must survive without
lengthening. Unknown returns remain debt, never PI/current/release credit.
The full saved-board receiving gates remain mandatory for any subsequent
route which uses the released corridor.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_copper_echo as sexpr
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items


def _budget(timeout_s):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('bounded_redundant_bypass_ground_inventory_required')
    return time.monotonic() + timeout_s


def _plan_source_tail(board, pad_uuid, track_uuid, *, timeout_s=10., require_alternate_departure,
                      source_full_class=False):
    """Shared typed source recognition; retirement and replacement differ.

    A deletion-only transaction needs another actual ground departure.
    Reseating always constructs and independently receives a replacement
    barrel/path, so its source need not already have redundant routing.
    """
    if type(require_alternate_departure) is not bool or type(source_full_class) is not bool:
        raise ValueError('explicit_bypass_source_departure_policy_required')
    # The original small-tail/deletion contract stays unchanged. A distinct
    # replacement owner may retain the EXACT authored full Ground class.
    # This is a finite Source work scope, never caller-selected width,
    # low-current inference, a neckdown, or authority over a power return.
    # All manufacturer/bypass/branch/barrel/partition checks below still run.
    floor=max(int(board.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(board,'GND')['width']))
    if source_full_class and not 0<floor<=1000000:
        raise ValueError('bounded_positive_source_ground_class_required')
    deadline = _budget(timeout_s)
    if any(type(u) is not str or not u for u in (pad_uuid, track_uuid)):
        raise ValueError('exact_source_bypass_land_and_departure_required')
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    found = [p for p in pads if force._uid(p) == pad_uuid]
    if len(found) != 1:
        raise ValueError('redundant_bypass_source_land_unknown')
    pad = found[0]; cap = pad.GetParentFootprint(); lands = list(cap.Pads())
    if (cap.IsDNP() or len(lands) != 2 or str(pad.GetNetname()) != 'GND'
            or any(p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                   or len(list(p.GetLayerSet().CuStack())) != 1 for p in lands)):
        raise ValueError('selected_two_surface_land_ground_bypass_required')
    assignment = constraints._device_bypass_assignment(board, project_max_mm=3.5)
    assigned = [r['requirement'] for r in assignment['assigned'].values()
                if r['cap_ref'] == cap.GetReference()]
    if len(assigned) != 1 or (assigned[0].get('return_rail') or 'GND') != 'GND':
        raise ValueError('uniquely_selected_ground_bypass_required')
    req = assigned[0]; owner = board.FindFootprintByReference(req['ref'])
    model = roles.footprint_contract(owner) if owner is not None else None
    if (owner is None or owner.IsDNP() or not model
            or model['pins'].get(str(req['pin'])) != 'power_input'
            or set(model['pins'].values()) & {'power_output', 'switch', 'power_return'}
            or owner.IsFlipped() != cap.IsFlipped()
            or len([p for p in lands if str(p.GetNetname()) == req['rail']]) != 1):
        raise ValueError('positive_low_power_device_bypass_topology_required')
    layer = next(iter(pad.GetLayerSet().CuStack()))
    tracks = list(board.GetTracks()); matching = [t for t in tracks if force._uid(t) == track_uuid]
    if len(matching) != 1:
        raise ValueError('source_ground_departure_unknown')
    edge = matching[0]
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    if (edge.GetClass() != 'PCB_TRACK' or edge.GetNetCode() != pad.GetNetCode()
            or edge.GetLayer() != layer or force._uid(edge) in grouped
            or (edge.GetWidth()!=floor if source_full_class else not 0 < edge.GetWidth() <= 350000)
            or not 0 < edge.GetLength() <= 12000000
            or tuple(edge.GetStart()) == tuple(edge.GetEnd())):
        raise ValueError('small_ungrouped_source_ground_departure_required')
    ends = [tuple(edge.GetStart()), tuple(edge.GetEnd())]
    if sum(pad.HitTest(pcbnew.VECTOR2I(*p)) for p in ends) != 1:
        raise ValueError('source_departure_must_end_in_exact_bypass_land')
    touching = [t for t in tracks if t.GetClass() == 'PCB_TRACK'
        and t.GetNetCode() == pad.GetNetCode() and t.IsOnLayer(layer)
        and t.GetEffectiveShape(layer).Collide(pad.GetEffectiveShape(layer), 0)]
    if require_alternate_departure and len(touching) < 2:
        raise ValueError('another_actual_bypass_ground_departure_required')
    # Removing only a departure's first segment can leave a source-authored
    # dead-end stub occupying the very corridor being released. Derive (do
    # not accept an arbitrary caller list for) its uniform unbranched tail,
    # stopping at a retained terminal, barrel, saved plane or junction.
    retired = [edge]; length = edge.GetLength()
    point = next(p for p in ends if not pad.HitTest(pcbnew.VECTOR2I(*p)))
    while True:
        if time.monotonic() >= deadline:
            raise ValueError('redundant_bypass_ground_inventory_deadline')
        at = pcbnew.VECTOR2I(*point)
        if any(force._uid(p) != pad_uuid and p.GetNetCode() == pad.GetNetCode()
               and p.IsOnLayer(layer) and p.HitTest(at) for p in pads):
            break
        if any(t.GetClass() == 'PCB_VIA' and t.GetNetCode() == pad.GetNetCode()
               and t.IsOnLayer(layer) and (tuple(t.GetPosition())==point
                   if source_full_class else t.HitTest(at)) for t in tracks):
            break
        if any(not z.GetIsRuleArea() and z.IsOnLayer(layer)
               and z.GetNetCode() == pad.GetNetCode() and z.IsFilled()
               and z.GetFilledPolysList(layer).Contains(at) for z in board.Zones()):
            break
        ids = {force._uid(t) for t in retired}
        neighbours = [t for t in tracks if force._uid(t) not in ids
            and t.GetNetCode() == pad.GetNetCode() and t.IsOnLayer(layer)
            # Wide native capsules can touch their own terminal barrel at
            # an earlier bend. For exact-class REPLACEMENT only, finish the
            # bounded literal track chain to its actual barrel centre.
            # The replacement owner's independent all-contact audit must
            # subsequently prove that this one barrel and these exact edges
            # own EVERY old contact; another barrel/tee still refuses.
            and (not source_full_class or t.GetClass()!='PCB_VIA')
            and t.GetEffectiveShape(layer).Collide(
                pcbnew.SHAPE_SEGMENT(at, at, edge.GetWidth()), 0)]
        if len(neighbours) != 1:
            break
        following = neighbours[0]
        if (following.GetClass() != 'PCB_TRACK' or following.GetWidth() != edge.GetWidth()
                or force._uid(following) in grouped or point not in (
                    tuple(following.GetStart()), tuple(following.GetEnd()))):
            break
        if len(retired) >= 4 or length + following.GetLength() > 12000000:
            raise ValueError('redundant_bypass_unbranched_tail_scope_bound')
        retired.append(following); length += following.GetLength()
        start, end = tuple(following.GetStart()), tuple(following.GetEnd())
        point = end if point == start else start
    if time.monotonic() >= deadline:
        raise ValueError('redundant_bypass_ground_inventory_deadline')
    return dict(schema=1, pad_uuid=pad_uuid, track_uuid=track_uuid,
        requires_alternate_ground_departure=require_alternate_departure,
        capacitor_uuid=force._uid(cap), owner_uuid=force._uid(owner),
        owner_supply_pin=str(req['pin']), rail=req['rail'],
        manufacturer_source=model['source'], selected_bypass_source=req['source'],
        source_locked=bool(edge.IsLocked()), source_length_nm=round(edge.GetLength()),
        source_width_nm=edge.GetWidth(), source_layer=int(layer),
        source_full_class=source_full_class,
        source_points_nm=[list(p) for p in ends],
        retired_track_uuids=[force._uid(t) for t in retired],
        source_departure_and_tail_length_nm=round(length),
        source_binding=field._field_snapshot_inventory(board),
        release_authority=False, current_authority=False)


def plan(board, pad_uuid, track_uuid, *, timeout_s=10.):
    """Deletion-only authority always requires an alternate actual departure."""
    return _plan_source_tail(board, pad_uuid, track_uuid, timeout_s=timeout_s,
                             require_alternate_departure=True)


def subtract(board, proposal):
    """Only a private proposal; downstream receiving must reprove the cut."""
    if field._field_snapshot_inventory(board) != proposal.get('source_binding'):
        raise ValueError('redundant_bypass_source_binding_changed')
    current = plan(board, proposal['pad_uuid'], proposal['track_uuid'])
    if current != proposal:
        raise ValueError('redundant_bypass_source_topology_changed')
    retired = set(proposal['retired_track_uuids'])
    discard_items(board, [t for t in board.GetTracks() if force._uid(t) in retired])


def receive(source, candidate, *, pad_uuid, track_uuid, board_hint, timeout_s=10.):
    result = dict(schema=1, ok=False, complete=False, errors=[],
        release_authority=False, current_authority=False, inherited_debt_qualified=False,
        independently_measured_local_PI_progress=False,
        full_saved_board_receiving_still_required=True)
    started = time.monotonic()
    try:
        deadline = _budget(timeout_s)
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        if source == candidate:
            raise ValueError('distinct_saved_redundant_bypass_candidate_required')
        families = [force._family(p, board_hint) for p in (source, candidate)]
        epoch = force._code_identity()
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        proposal = plan(parent, pad_uuid, track_uuid,
                        timeout_s=min(10., deadline-time.monotonic()))
        _, old = additive._nodes(source); _, new = additive._nodes(candidate)
        retired = set(proposal['retired_track_uuids'])
        if old.keys()-new.keys() != retired or new.keys()-old.keys():
            raise ValueError('exactly_one_source_departure_subtraction_only')
        first = ordinary._partition(parent, deadline, retired_uuids=retired)
        keys = set().union(*first)
        last = ordinary._partition(child, deadline, retained_keys=keys)
        if any(not any(p <= q for q in last) for p in first):
            raise ValueError('redundant_departure_cut_lost_surviving_native_partition')
        oldpads = {force._uid(p):p for fp in parent.GetFootprints() for p in fp.Pads()
                   if str(p.GetNetname()) == 'GND'}
        newpads = {force._uid(p):p for fp in child.GetFootprints() for p in fp.Pads()
                   if str(p.GetNetname()) == 'GND'}
        if oldpads.keys() != newpads.keys():
            raise ValueError('ground_land_population_changed')
        known, unknown = [], []
        for uid, pad in oldpads.items():
            if time.monotonic() >= deadline:
                raise ValueError('redundant_bypass_ground_return_proof_deadline')
            before = cells._existing_return(parent, pad, 3.5)
            if before is None:
                unknown.append(uid); continue
            after = cells._existing_return(child, newpads[uid], 3.5)
            if after is None or after[0] > before[0] + 1e-6:
                raise ValueError('already_proved_short_ground_return_worsened:' + uid)
            known.append(dict(pad_uuid=uid, before_mm=before[0], after_mm=after[0]))
        with tempfile.TemporaryDirectory(prefix='cec-redundant-bypass-replay-') as work:
            projected = force._copy_family(source, Path(work)/'projected')
            basis = pcbnew.LoadBoard(str(projected)); subtract(basis, proposal)
            field._save_field_snapshot(basis, projected)
            _, nodes = additive._nodes(projected)
            if nodes.keys() != old.keys()-retired or any(
                    sexpr._freeze(nodes[u]) != sexpr._freeze(old[u]) for u in nodes):
                raise ValueError('redundant_bypass_subtraction_changed_unowned_material')
            remaining = min(10., deadline-time.monotonic())
            if remaining <= 0:
                raise ValueError('redundant_bypass_exact_replay_deadline')
            proof = additive.receive(projected, candidate, timeout_s=remaining)
            result['independent_source_cut_ground_refill_and_rule_replay'] = proof
            if not proof.get('ok') or not proof.get('complete'):
                raise ValueError('redundant_bypass_exact_replay_refused')
        if (families != [force._family(p, board_hint) for p in (source, candidate)]
                or epoch != force._code_identity() or time.monotonic() >= deadline):
            raise ValueError('redundant_bypass_inputs_or_deadline_changed')
        result.update(ok=True, complete=True, retired_track_uuids=proposal['retired_track_uuids'],
            retired_via_uuids=[], added_native_uuids=[],
            all_surviving_partitions_and_proved_short_returns_preserved=True,
            proved_short_ground_returns=known, unqualified_ground_return_pad_uuids=sorted(unknown),
            source_proposal={k:v for k,v in proposal.items() if k != 'source_binding'},
            main_force_copper_poses_and_power_fills_exact=True,
            source_candidate_and_code_unchanged=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    result['elapsed_s'] = round(time.monotonic()-started, 6)
    return result
