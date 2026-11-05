"""Read-only permission for ADDITIVE completion of an incomplete saved prefix.

The frozen copper stays frozen. This separates a physical prefix from a
whole-net routing exclusion, without modifying its sidecar or relaxing any
current, contact, field, DRC, Kelvin or preservation checks. Caller-declared
whole-net ownership and external freezes never receive this permission.
"""
import json
from pathlib import Path


def allowance(board, source, net, owners):
    import cec_force_current as force
    import cec_field_coupling as field
    import cec_locked_net_ownership as ownership
    source = Path(source).resolve()
    result = dict(eligible=False, net=net, scope='additive_incomplete_prelaid_prefix_only',
        original_copper_mutation_authorized=False, state_mutation_authorized=False,
        original_state_geometry_requalified=False, current_qualified=False,
        release_authority=False)
    if (type(net) is not str or not net or not isinstance(owners, (list, tuple))
            or not 1 <= len(owners) <= 8 or any(type(owner) is not str for owner in owners)):
        result['reason'] = 'explicit_bounded_frozen_owner_inventory_required'
        return result
    expected = source.with_suffix('.pourfirst-state.json')
    if any(owner != 'pour_first:'+str(expected) for owner in owners):
        result['reason'] = 'caller_or_external_whole_net_ownership_remains_immutable'
        return result
    if Path(board.GetFileName()).resolve() != source:
        result['reason'] = 'native_board_not_bound_to_saved_source'
        return result
    before = force._family(source)
    state = json.loads(expected.read_text())
    if (state.get('prelaid') is not True or state.get('placement_scope') != 'complete'
            or net not in state.get('frozen_nets', ())):
        result['reason'] = 'complete_prelaid_physical_prefix_required'
        return result
    zones = [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == net]
    if any(not z.IsFilled() or any(not z.HasFilledPolysForLayer(int(layer))
            for layer in z.GetLayerSet().CuStack()) for z in zones):
        result['reason'] = 'unfilled_frozen_native_copper_is_not_a_saved_prefix'
        return result
    copper = [t for t in board.GetTracks() if t.GetNetname() == net] + zones
    if not copper:
        result['reason'] = 'actual_saved_native_prefix_required'
        return result
    snapshot = field._field_snapshot_inventory(board)
    proof = ownership.revalidate_completed(board, [net])
    if snapshot != field._field_snapshot_inventory(board) or before != force._family(source):
        result['reason'] = 'source_changed_during_native_completion_proof'
        return result
    row = proof['proof']['nets'][net]
    result.update(native_completion=proof, native_copper_count=len(copper),
        source_sha256=force._hash(source), state_sha256=force._hash(expected),
        source_family_unchanged=True, native_geometry_unchanged=True)
    if row['complete'] or row['pad_count'] < 2:
        result['reason'] = 'native_whole_net_completion_is_not_missing'
        return result
    result.update(eligible=True, reason='incomplete_physical_prefix_accepts_only_preserved_full_width_additions')
    return result
