"""Whole-current joins may tap an input, never acquire its thin enable leaf."""
import time
from unittest import mock

import pcbnew
import pytest
import cec_current_topology as topology
import cec_control_current_branch as controls
import cec_field_coupling as field
import cec_force_current as force
import cec_native_current_capture as capture
import cec_retained_supply_port as ports
from test_control_current_branch import fixture
from test_retained_supply_port import fixture as column_fixture


def prepared(tmp_path, monkeypatch, angle=0, back=False):
    _, source, board, domains = fixture(tmp_path, monkeypatch, angle=angle,
        back=back, bridge=True, distributed=True)
    monkeypatch.setattr(topology, 'board_current_domains', lambda *a,**k: domains)
    guard = capture.Guard(board, source, net='RAIL_OTHER', board_hint='synthetic')
    assert guard.active and guard.complete and len(guard.scopes) == 1
    return board, source, guard, domains


@pytest.mark.parametrize('angle,back', [(0,False),(90,False),(180,True),(270,True)])
def test_native_control_departures_are_not_power_ports(tmp_path, monkeypatch, angle, back):
    board, source, guard, _ = prepared(tmp_path, monkeypatch, angle, back)
    before = field._field_snapshot_inventory(board); saved = source.read_bytes()
    scope = guard.scopes[0]
    assert all(not guard.allows_endpoint(dict(native_uuids=[u]))
        for u in scope['exclusive_material_uuids'])
    assert all(guard.allows_endpoint(dict(native_uuids=[u]))
        for u in scope['retained_capture_uuids'])
    via = next(guard.native[u] for u in scope['exclusive_material_uuids']
        if guard.native[u].GetClass() == 'PCB_VIA')
    at = tuple(via.GetPosition())
    assert all(not guard(at, (at[0]+1000000,at[1]), 600000, int(layer))
        for layer in board.GetEnabledLayers().CuStack())
    assert source.read_bytes() == saved and field._field_snapshot_inventory(board) == before
    report = guard.report()
    assert report['shared_native_input_taps_only'] and report['complete']
    assert not report['current_budget_or_width_changed'] and not report['release_authority']
    assert not report['admission_authority'] and not report['barrel_capacity_qualified']


@pytest.mark.parametrize('angle,back', [(0,False),(90,False),(180,True),(270,True)])
def test_input_side_capture_preserves_existing_control_classification(tmp_path, monkeypatch, angle, back):
    board, source, guard, domains = prepared(tmp_path, monkeypatch, angle, back)
    scope = guard.scopes[0]; boundary = guard.native[scope['retained_capture_uuids'][0]]
    leaf_via = next(guard.native[u] for u in scope['exclusive_material_uuids']
        if guard.native[u].GetClass() == 'PCB_VIA')
    at = tuple(boundary.GetPosition()); leaf = tuple(leaf_via.GetPosition())
    # Approach outward from the real input boundary, not through the EN leaf.
    dx,dy = at[0]-leaf[0],at[1]-leaf[1]
    scale = max(abs(dx),abs(dy)); end = (at[0]+dx*1000000//scale,at[1]+dy*1000000//scale)
    layer = pcbnew.F_Cu if not back else pcbnew.B_Cu
    assert guard(end, at, 600000, int(layer))
    before = controls.inventory(board, source, domains)['uuids']
    track = pcbnew.PCB_TRACK(board); track.SetStart(pcbnew.VECTOR2I(*end))
    track.SetEnd(pcbnew.VECTOR2I(*at)); track.SetWidth(600000); track.SetLayer(layer)
    track.SetNetCode(board.GetNetcodeFromNetname('RAIL_OTHER')); board.Add(track)
    after = controls.inventory(board, source, domains)
    assert after['complete'] and after['uuids'] == before


def test_new_via_cannot_capture_a_reserved_control_on_an_inner_layer(tmp_path, monkeypatch):
    board, _, guard, _ = prepared(tmp_path, monkeypatch)
    via = next(guard.native[u] for u in guard.exclusive if guard.native[u].GetClass() == 'PCB_VIA')
    assert not guard.allows_ops([('via',via.GetPosition(),.3,.6)])


def test_classification_inventory_must_be_complete(tmp_path, monkeypatch):
    board, source, _, _ = prepared(tmp_path, monkeypatch)
    monkeypatch.setattr(controls, 'inventory', lambda *a,**k:dict(complete=False))
    with pytest.raises(ValueError, match='complete_native_control_capture_inventory_required'):
        capture.Guard(board, source, net='RAIL_OTHER', board_hint='synthetic')


def test_source_guard_expiry_is_not_a_no_path_proof(tmp_path, monkeypatch):
    board, _, guard, _ = prepared(tmp_path, monkeypatch)
    guard.deadline = time.monotonic()-1
    assert not guard((1,2),(3,4),600000,int(pcbnew.F_Cu))
    assert not guard.report()['complete'] and not guard.report()['admission_authority']


@pytest.mark.parametrize('timeout', [0, True, float('nan'), 11])
def test_unknown_or_unbounded_reservation_input_refused(tmp_path, monkeypatch, timeout):
    board, source, _, _ = prepared(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        capture.Guard(board, source, net='RAIL_OTHER', board_hint='synthetic', timeout_s=timeout)


def test_rail_constructor_uses_reservation_before_exposing_native_columns():
    board, roots, columns, _, current = column_fixture()
    rejected = columns[0].m_Uuid.AsString()
    guard = mock.Mock(active=True)
    guard.allows_endpoint.side_effect = lambda q: rejected not in q['native_uuids']
    with mock.patch.object(capture, 'Guard', return_value=guard):
        ops, _ = ports.plan_rail(board, *roots, width_nm=1000000,
            clearance_nm=200000,current_widths=current,spec=dict(width=1000000),
            deadline_monotonic=time.monotonic()+2.)
    assert ops is None and guard.allows_endpoint.call_count >= 2


def test_untyped_columns_do_not_invent_a_control_exemption():
    board, roots, _, _, _ = column_fixture()
    guard = capture.Guard(board, '', net=str(roots[0].GetNetname()))
    assert not guard.active and not guard.scopes
    assert guard((1,2),(3,4),600000,int(pcbnew.F_Cu))
    assert not guard.report()['admission_authority']
