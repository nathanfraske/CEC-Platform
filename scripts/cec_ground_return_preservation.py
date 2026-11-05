"""Read-only physical-return nonregression across source-owned placement.

Observe every populated, unique-surface SMD GND terminal, not just a selected
capacitor.  A known explicit/filled-copper witness must remain known and no
longer.  An unknown source witness stays declared unknown; global connectivity
does not invent a local return.  Pose ownership, native DRC, reference-plane,
process, current, Kelvin and release receiving remain separate requirements.
"""
import math
import time

import cec_cell_row_rebuild as row
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_return_escape as surface


MAX_NATIVE_PADS = 16384
MAX_GROUND_TERMINALS = 2048


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('ground_return_preservation_deadline')


def _observe(board, reach_mm, deadline):
    found = {}; count = 0
    for fp in board.GetFootprints():
        _tick(deadline)
        for pad in fp.Pads():
            count += 1; _tick(deadline)
            if count > MAX_NATIVE_PADS:
                raise ValueError('ground_return_preservation_native_inventory_bound')
            face = surface.smd_surface_layer(pad)
            if (fp.IsDNP() or pad.GetNetname() != 'GND' or pad.HasHole()
                    or face is None):
                continue
            uid = force._uid(pad)
            if uid in found or len(found) >= MAX_GROUND_TERMINALS or pad.GetNetCode() <= 0:
                raise ValueError('ground_return_preservation_unique_native_terminals_required')
            witness = cells._existing_return(board, pad, reach_mm,
                allow_native_track_body=True)
            _tick(deadline)
            distance = None if witness is None else witness[0]
            if distance is not None and (not math.isfinite(distance) or distance < 0):
                raise ValueError('ground_return_preservation_invalid_native_witness')
            found[uid] = dict(pad_uuid=uid, footprint_uuid=force._uid(fp),
                ref=fp.GetReference(), pin=pad.GetNumber(), net=pad.GetNetname(),
                layer_id=int(face), at_nm=list(pad.GetPosition()),
                return_mm=distance, via_uuid=force._uid(witness[1]) if witness else None)
    return found


def receive(source, candidate, *, timeout_s=10., reach_mm=16.):
    """Freshly compare literal pad identities and native local return witnesses.

    No producer-provided measurements, return-pad names, coordinate rules or
    waiver flags. The one-nanometre numerical tolerance is not permission to
    move copper or relax any process rule. This is geometric preservation,
    not a shortest-path, impedance, current or fabrication certificate.
    """
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(reach_mm) not in (int, float)
            or not math.isfinite(reach_mm) or not 0 < reach_mm <= 32):
        raise ValueError('bounded_ground_return_preservation_required')
    started = time.monotonic(); deadline = started + timeout_s
    bindings = [row._source_binding(b) for b in (source, candidate)]
    result = dict(schema=1, scope='all_populated_smd_ground_return_nonregression',
        ok=False, complete=False, errors=[], regressed_terminals=[],
        improved_terminals=[], source_unknown_terminals=[],
        source_known_terminals=0, observed_source_terminals=0,
        measured_return_scope_mm=reach_mm, source_pose_changes_not_authorized=True,
        global_shortest_return_qualified=False, reference_planes_qualified=False,
        current_qualified=False, routing_admitted=False, release_authority=False)
    try:
        old = _observe(source, reach_mm, deadline)
        new = _observe(candidate, reach_mm, deadline)
        result['observed_source_terminals'] = len(old)
        result['source_unknown_terminals'] = [value for value in old.values()
            if value['return_mm'] is None]
        result['source_known_terminals'] = len(old) - len(result['source_unknown_terminals'])
        if old.keys() != new.keys():
            raise ValueError('ground_return_preservation_terminal_inventory_changed')
        identities = ('pad_uuid', 'footprint_uuid', 'pin', 'net', 'layer_id')
        for uid, before in old.items():
            _tick(deadline); after = new[uid]
            if any(before[key] != after[key] for key in identities):
                raise ValueError('ground_return_preservation_terminal_identity_changed')
            first, last = before['return_mm'], after['return_mm']
            observed = dict(pad_uuid=uid, source=before, candidate=after)
            if first is not None and (last is None or last > first + .000001):
                result['regressed_terminals'].append(observed)
            elif first is not None and last is not None and last < first - .000001:
                result['improved_terminals'].append(observed)
        result['complete'] = True
        result['ok'] = not result['regressed_terminals']
        result['all_source_known_return_witnesses_preserved'] = result['ok']
        if not result['ok']:
            result['errors'].append('source_known_ground_return_worsened_or_lost')
    except ValueError as exc:
        result['errors'].append(str(exc))
    finally:
        if bindings != [row._source_binding(b) for b in (source, candidate)]:
            raise ValueError('ground_return_preservation_changed_native_board')
    finished=time.monotonic();exhausted=finished>=deadline
    if exhausted:
        # Final native-binding verification belongs to this SAME lease too.
        # A complete observation followed by a late identity check is not a
        # timely positive receiver. Preserve any measured regressions, while
        # explicitly keeping the overall result inconclusive/refused.
        result.update(ok=False,complete=False,all_source_known_return_witnesses_preserved=False)
        if 'ground_return_preservation_deadline' not in result['errors']:
            result['errors'].append('ground_return_preservation_deadline')
    result.update(elapsed_s=finished-started,
        lease_exhausted=exhausted, native_boards_unchanged=True)
    return result
