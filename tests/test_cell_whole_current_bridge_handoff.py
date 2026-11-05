"""Bridge scheduling must retain source-typed, whole-current pad profiles.

Dispatch mocks observe API composition, never grant copper or admission.
The final test uses the real bridge and native foreign-copper guard.
"""
import copy
import time

import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_connected_address_supply_prefix as connected
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
from test_source_current_pad_ports import fixture, CURRENT


def dispatch(monkeypatch, *, back=False, angle=0, role='power', same_face=True):
    source, board, supply = fixture(monkeypatch, angle=angle, back=back)
    if role in ('address', 'unowned_address'):
        for b in (source, board):
            fp = next(iter(b.GetFootprints()))
            fp.FindPadByNumber('2').SetNet(fp.FindPadByNumber('6').GetNet())
        supply = supply.GetParentFootprint().FindPadByNumber('2')
    face = int(next(iter(supply.GetLayerSet().CuStack())))
    target = pcbnew.PCB_TRACK(board); target.SetNet(supply.GetNet()); target.SetLayer(face)
    target.SetWidth(500000); target.SetStart(pcbnew.VECTOR2I_MM(29, 25))
    target.SetEnd(pcbnew.VECTOR2I_MM(30, 25)); board.Add(target)
    request = dict(kind='source_boundary', net=supply.GetNetname(), width_nm=500000,
        a=dict(pad_uuid=force._uid(supply), at_nm=list(supply.GetPosition()), layers=[face]),
        b=dict(at_nm=list(target.GetStart()), layers=[face], native_uuids=[force._uid(target)]))
    other = None
    if not same_face:
        owner = pcbnew.FOOTPRINT(supply.GetParentFootprint()); board.Add(owner)
        # A second physical package must not retain its clone's UUIDs:
        # actual_pads is deliberately keyed by literal native identity.
        for item in [owner, *owner.Pads(), *owner.GraphicalItems(), *owner.GetFields()]:
            item.m_Uuid.Clone(pcbnew.KIID())
        owner.SetReference('INDEPENDENT_OTHER_SUPPLY')
        owner.SetPosition(pcbnew.VECTOR2I_MM(29, 25))
        owner.Flip(owner.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for pad in owner.Pads():pad.SetNet(board.FindNet(pad.GetNetname()))
        other = owner.FindPadByNumber('6')
        request['b'] = dict(pad_uuid=force._uid(other), at_nm=list(other.GetPosition()),
            layers=list(map(int, other.GetLayerSet().CuStack())))
    if role in ('address', 'unowned_address'):
        request['source_supply_pad_contact_lead_restoration'] = {'dispatch_fixture_only': True}
        monkeypatch.setattr(connected, 'endpoint_context', lambda *_a, **_k:
            dict(pad_uuid=force._uid(supply)) if role == 'address' else None)
    import cec_native_component_ports as ports
    import cec_native_via_frontier as frontier
    monkeypatch.setattr(ports, 'endpoints', lambda _b, _n, endpoint, **_k: [copy.deepcopy(endpoint)])
    monkeypatch.setattr(ports, 'surface_maze_pairs', lambda *_a, **_k: [])
    monkeypatch.setattr(cells, '_canonical_whole_rail_surface', lambda *_a, **_k: None)
    monkeypatch.setattr(fr, '_tap_foreign_clear', lambda *_a, **_k: False)
    monkeypatch.setattr(frontier, 'sites', lambda _b, _c, at, **_k: dict(
        sites_nm=[[at[0]+1000000, at[1]]], drill_mm=.3, diameter_mm=.6))
    bridge_calls, leg_calls = [], []
    def bridge(*args, **kwargs):
        bridge_calls.append((args, kwargs)); return None
    def legs(*args, **kwargs):
        leg_calls.append((args, kwargs)); return None
    monkeypatch.setattr(fr, '_lastmile_bridge', bridge)
    monkeypatch.setattr(fr, '_guarded_profiled_lastmile_legs', legs)
    before = field._field_snapshot_inventory(board)
    detail = {}; deadline = time.monotonic()+2.
    escape._connection_menu(board, request, board_hint='synthetic', deadline=deadline,
        layers=[pcbnew.B_Cu if face == pcbnew.F_Cu else pcbnew.F_Cu],
        append=lambda _ops: pytest.fail('no mocked candidate is admitted'),
        detail=detail, source_board=source)
    assert before == field._field_snapshot_inventory(board)
    return board, supply, other, bridge_calls, leg_calls, detail, deadline


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('role', ['power', 'address', 'unowned_address'])
def test_exact_whole_current_profiles_reach_both_frontier_and_bridge(monkeypatch, back, angle, role):
    board, pad, other, bridges, legs, detail, deadline = dispatch(
        monkeypatch, back=back, angle=angle, role=role)
    assert bridges and legs and other is None
    face = int(next(iter(pad.GetLayerSet().CuStack())))
    expected = cells._whole_current_endpoint_escapes(board, [pad, None], net_code=pad.GetNetCode(),
        layer=face, class_width_nm=500000, clearance_nm=200000, current_widths=CURRENT)[0]
    if role == 'unowned_address':expected = None
    assert all(kw['start_escape'] == expected and kw['end_escape'] is None for _, kw in bridges)
    assert all(kw['deadline_monotonic'] <= deadline for _, kw in bridges+legs)
    assert legs[0][1]['start_escape'] == expected and legs[0][1]['end_escape'] is None
    assert legs[1][1]['start_escape'] is None and legs[1][1]['end_escape'] is None
    assert detail['unchanged_current_contract'] == CURRENT


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('angle', [0, 90, 180, 270])
def test_different_native_endpoint_faces_derive_independent_unchanged_profiles(monkeypatch, back, angle):
    board, first, last, bridges, legs, detail, deadline = dispatch(
        monkeypatch, back=back, angle=angle, same_face=False)
    assert bridges and last is not None
    profiles = []
    for pad in (first, last):
        face = int(next(iter(pad.GetLayerSet().CuStack())))
        profiles.append(cells._whole_current_endpoint_escapes(board, [pad, None],
            net_code=pad.GetNetCode(), layer=face, class_width_nm=500000,
            clearance_nm=200000, current_widths=CURRENT)[0])
    assert all(kw['start_escape'] == profiles[0] and kw['end_escape'] == profiles[1]
        for _, kw in bridges)
    assert legs[0][1]['start_escape'] == profiles[0]
    assert legs[1][1]['start_escape'] == profiles[1]


def test_real_bridge_obeys_actual_escape_floor_foreign_geometry_and_full_width_middle():
    from test_cell_whole_current_launch_search import fixture as physical_fixture
    board, pads, net, face, current, foreign = physical_fixture()
    # Real .25mm minimum and whole-rail authority; a Source class preference
    # of .5mm cannot depart at the first pad, while the typed local escape can.
    profiles = cells._whole_current_endpoint_escapes(board, pads, net_code=net.GetNetCode(),
        layer=face, class_width_nm=500000, clearance_nm=200000, current_widths=current)
    diagnostics = {}
    ops = fr._lastmile_bridge(board, tuple(pads[0].GetPosition()), [face],
        tuple(pads[1].GetPosition()), [face], 500000, net.GetNetCode(), [pcbnew.B_Cu], 200000,
        start_escape=profiles[0], end_escape=profiles[1],
        width_for_layer=lambda _face: 500000, deadline_monotonic=time.monotonic()+3.,
        leg_ok=lambda a,b,h: fr._edge_leg_clear(board,a,b,h+200000),
        refine_stubs=True, foreign_cache={}, diagnostics=diagnostics)
    # This is an actual candidate, not an admitted saved route or via rating.
    assert ops, diagnostics
    tracks = [op for op in ops if op[0] == 'trk']
    assert tracks and all(op[3] >= max(board.GetDesignSettings().m_TrackMinWidth,
        current['required_by_layer_nm'][op[4]]) for op in tracks)
    assert any(op[3] == 500000 for op in tracks)
    assert all(fr._tap_foreign_clear(board, pcbnew.VECTOR2I(*op[1]), pcbnew.VECTOR2I(*op[2]),
        op[3], op[4], 200000, {net.GetNetCode()}, foreign_cache={}) for op in tracks)
