"""Dispatch uses independently owned connected contexts, never role labels.

The canonical/geometry helper has separate real-Source tests. These fixtures
isolate wiring into existing constructor and saved-prefix consumers.
"""
import copy
import time

import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_connected_address_supply_prefix as connected
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_fr as fr
import cec_full_current_supply_prefix as prefix
from test_source_current_pad_ports import fixture, CURRENT


@pytest.mark.parametrize('back,angle', [(False, 0), (False, 90), (True, 180), (True, 270)])
@pytest.mark.parametrize('context', ['owned', 'absent', 'wrong_pad'])
def test_connected_constructor_only_types_the_exact_fresh_address_throat(monkeypatch, back, angle, context):
    source, board, supply = fixture(monkeypatch, angle=angle, back=back)
    for b in (source, board):
        fp = next(iter(b.GetFootprints()))
        fp.FindPadByNumber('2').SetNet(fp.FindPadByNumber('6').GetNet())
    pad = supply.GetParentFootprint().FindPadByNumber('2')
    face = int(next(iter(pad.GetLayerSet().CuStack())))
    target = pcbnew.PCB_TRACK(board); target.SetNet(pad.GetNet()); target.SetLayer(face)
    target.SetWidth(500000); target.SetStart(pcbnew.VECTOR2I_MM(26, 24))
    target.SetEnd(pcbnew.VECTOR2I_MM(27, 24)); board.Add(target)
    request = dict(kind='source_boundary', net=pad.GetNetname(), width_nm=500000,
        a=dict(pad_uuid=force._uid(pad), at_nm=list(pad.GetPosition()), layers=[face]),
        b=dict(at_nm=list(target.GetStart()), layers=[face], native_uuids=[force._uid(target)]),
        source_supply_pad_contact_lead_restoration={'identity_only_fixture': True})
    original = copy.deepcopy(request); contexts = []; offered = []
    def context_owner(first, posed, received, **kwargs):
        contexts.append((first, posed, copy.deepcopy(received), kwargs))
        return None if context == 'absent' else dict(pad_uuid=force._uid(pad) if context == 'owned' else 'other-pad')
    monkeypatch.setattr(connected, 'endpoint_context', context_owner)
    def observe(*_args, **kwargs):
        offered.append(kwargs['endpoint_pads']); return None
    monkeypatch.setattr(cells, '_canonical_whole_rail_surface', observe)
    monkeypatch.setattr(fr, '_guarded_profiled_lastmile_legs', lambda *_a, **_k: None)
    monkeypatch.setattr(fr, '_lastmile_bridge', lambda *_a, **_k: None)
    import cec_native_component_ports as components
    import cec_native_via_frontier as frontier
    monkeypatch.setattr(components, 'endpoints', lambda _b, _n, endpoint, **_k: [copy.deepcopy(endpoint)])
    monkeypatch.setattr(components, 'surface_maze_pairs', lambda *_a, **_k: [])
    monkeypatch.setattr(frontier, 'sites', lambda *_a, **_k: dict(sites_nm=[]))
    detail = {}
    escape._connection_menu(board, request, board_hint='synthetic', deadline=time.monotonic()+2.,
        layers=[0, 2], append=lambda _ops: None, detail=detail, source_board=source)
    assert request == original and len(contexts) == 1
    assert contexts[0][0] is source and contexts[0][1] is board and contexts[0][2] == original
    assert any(a is not None and force._uid(a) == force._uid(pad) and b is None
        for a, b in offered) == (context == 'owned')
    assert prefix.supply_terminal_role(pad) is None  # never reclassify the address
    assert detail['unchanged_current_contract'] == CURRENT


def receiver_fixture(monkeypatch):
    source, board, supply = fixture(monkeypatch)
    import cec_address_supply_obligations as address
    proposal = dict(scope='source_typed_complete_cell_escape_proposal',
        poses={supply.GetParentFootprint().GetReference(): [20., 20., 0.]}, board_hint='synthetic')
    monkeypatch.setattr(escape, 'recompile_source_proposal', lambda _b, q: copy.deepcopy(q))
    monkeypatch.setattr(address, 'requests', lambda *_a, **_k: {})
    return source, board, supply, proposal


def test_saved_prefix_forwards_actual_incoming_scope_to_independent_role_derivation(monkeypatch):
    source, board, pad, proposal = receiver_fixture(monkeypatch)
    seen = []
    def independent(*args, **kwargs):
        seen.append((args, kwargs)); return {'actual-address-id': 'source_connected_supply_strapped_address'}
    monkeypatch.setattr(connected, 'receiver_roles', independent)
    scope = {'actual-new-copper-id'}
    result = prefix._source_address_roles(board, {}, source, proposal, timeout_s=2., track_uuid_scope=scope)
    assert result == {'actual-address-id': 'source_connected_supply_strapped_address'}
    assert len(seen) == 1 and seen[0][0][:2] == (source, board)
    assert seen[0][0][2] == proposal and seen[0][1]['track_uuid_scope'] == scope


def test_no_incoming_scope_does_not_expand_legacy_unwired_role_inventory(monkeypatch):
    source, board, pad, proposal = receiver_fixture(monkeypatch)
    monkeypatch.setattr(connected, 'receiver_roles', lambda *_a, **_k: pytest.fail('no new copper scope'))
    assert prefix._source_address_roles(board, {}, source, proposal, timeout_s=2.) == {}


def test_saved_roles_refuse_connected_unwired_overlap(monkeypatch):
    source, board, pad, proposal = receiver_fixture(monkeypatch)
    import cec_address_supply_obligations as address
    uid, net = force._uid(pad), pad.GetNetname()
    request = dict(net=net, a=dict(pad_uuid=uid), unchanged_full_rail_current_contract=CURRENT)
    monkeypatch.setattr(address, 'requests', lambda *_a, **_k: {'source-only-fixture': request})
    monkeypatch.setattr(connected, 'receiver_roles', lambda *_a, **_k: {uid: 'conflicting-role'})
    contracts = {net: dict(current_authority=CURRENT['current_authority'], profile=CURRENT['profile'])}
    with pytest.raises(ValueError, match='connected_and_unwired_source_address_role_overlap'):
        prefix._source_address_roles(board, contracts, source, proposal, timeout_s=2., track_uuid_scope={'new'})
