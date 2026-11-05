"""Native off-pad transition reuse is distinct from pad-centre via creation."""
import math
import time
from unittest import mock

import pcbnew
import pytest

import cec_fr as fr
import cec_retained_supply_port as ports
import cec_decoupler_cell as cells
from cec_route_dimensions import current_trace_widths


def fixture(*, angle=0, back=False, netname='/other/SERVICE', ref='RENAMED_A', pth=False):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    props = board.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    board.SetProperties(props); board.GetDesignSettings().m_TrackMinWidth = 200000
    net = pcbnew.NETINFO_ITEM(board, netname); board.Add(net)
    roots, columns, tails = [], [], []
    for idx, x in enumerate((10., 14.)):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref + str(idx))
        fp.SetPosition(pcbnew.VECTOR2I_MM(x, 10)); board.Add(fp)
        pad = pcbnew.PAD(fp); pad.SetNumber('1'); pad.SetNet(net)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetLayerSet(pcbnew.PAD.SMDMask()); pad.SetSize(pcbnew.VECTOR2I_MM(1.05, .4))
        pad.SetPosition(pcbnew.VECTOR2I_MM(x, 10)); fp.Add(pad); roots.append(pad)
        if pth:
            column = pcbnew.PAD(fp); column.SetNumber('2'); column.SetNet(net)
            column.SetAttribute(pcbnew.PAD_ATTRIB_PTH); column.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            column.SetLayerSet(pcbnew.LSET.AllCuMask()); column.SetDrillSize(pcbnew.VECTOR2I_MM(.8, .8))
            column.SetSize(pcbnew.VECTOR2I_MM(2, 2)); fp.Add(column)
        else:
            column = pcbnew.PCB_VIA(board); column.SetNet(net)
            column.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); column.SetViaType(pcbnew.VIATYPE_THROUGH)
            column.SetWidth(800000); column.SetDrill(400000); board.Add(column)
        column.SetPosition(pcbnew.VECTOR2I_MM(x + 1.2, 10)); columns.append(column)
        tail = pcbnew.PCB_TRACK(board); tail.SetStart(pad.GetPosition()); tail.SetEnd(column.GetPosition())
        tail.SetLayer(pcbnew.F_Cu); tail.SetWidth(250000); tail.SetNet(net); board.Add(tail); tails.append(tail)
    for a, b in [((0, 0), (20, 0)), ((20, 0), (20, 20)), ((20, 20), (0, 20)), ((0, 20), (0, 0))]:
        edge = pcbnew.PCB_SHAPE(); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts); board.Add(edge)
    for fp in board.GetFootprints():
        if back: fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if angle: fp.Rotate(pcbnew.VECTOR2I_MM(10, 10), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    if not pth:
        for column in columns:
            if angle: column.Rotate(pcbnew.VECTOR2I_MM(10, 10), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    for tail in tails:
        if back: tail.SetLayer(pcbnew.B_Cu)
        if angle: tail.Rotate(pcbnew.VECTOR2I_MM(10, 10), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    authority = dict(amps=1.1, geometry_margin=1.25, margin_included=False, source='synthetic')
    widths = current_trace_widths(authority, tuple(board.GetLayerName(l)
        for l in board.GetEnabledLayers().CuStack()), 'jlcpcb_6l_pofv_signal', rise_c=30.)
    current = dict(current_authority=authority, profile='jlcpcb_6l_pofv_signal',
        required_by_layer_nm={board.GetLayerID(n): math.ceil(w * 1e6) for n, w in widths.items()})
    return board, roots, columns, tails, current


def propose(board, roots, current):
    return ports.plan(board, *roots, width_nm=1000000, clearance_nm=200000,
        current_widths=current, spec=dict(width=1000000),
        deadline_monotonic=time.monotonic() + 2., max_length_nm=10000000)


@pytest.mark.parametrize('angle,back,netname,ref', [(0, False, '/x/RAIL_A', 'A'),
    (90, False, 'RAIL_B', 'B'), (180, True, '/another/RAIL_C', 'C'), (270, True, 'RAIL_D', 'D')])
def test_native_off_pad_columns_expose_full_current_layer_ports(angle, back, netname, ref):
    board, roots, columns, _, current = fixture(angle=angle, back=back, netname=netname, ref=ref)
    before = {t.m_Uuid.AsString() for t in board.GetTracks()}
    ops, proof = propose(board, roots, current)
    assert ops and proof and proof['retained_column_uuids'] == [c.m_Uuid.AsString() for c in columns]
    assert all(op[0] == 'trk' and op[3] >= max(1000000, current['required_by_layer_nm'][op[4]]) for op in ops)
    assert proof['new_vias'] == 0 and not proof['barrel_capacity_qualified']
    assert before == {t.m_Uuid.AsString() for t in board.GetTracks()}


def test_current_floor_is_derived_on_the_actual_selected_inner_layer():
    board, roots, _, _, current = fixture()
    original = fr._guarded_profiled_lastmile_legs
    with mock.patch.object(fr, '_guarded_profiled_lastmile_legs', side_effect=lambda *a, **k:
            original(*a, **k) if a[4] == pcbnew.In2_Cu else None):
        ops, proof = propose(board, roots, current)
    assert ops and all(op[4] == pcbnew.In2_Cu
        and op[3] == current['required_by_layer_nm'][pcbnew.In2_Cu] for op in ops)
    assert proof['width_nm'] > 1000000


def test_real_plated_pad_is_reused_without_another_drill():
    board, roots, columns, _, current = fixture(pth=True)
    ops, proof = propose(board, roots, current)
    assert ops and proof and not any(op[0] == 'via' for op in ops)
    assert proof['retained_column_uuids'] == [c.m_Uuid.AsString() for c in columns]


@pytest.mark.parametrize('fault', ['no_authority', 'false_floor', 'bool_current',
    'wrong_profile', 'thin_source', 'remote_port', 'partial_stack', 'invalid_drill',
    'no_columns', 'dnp', 'wrong_net', 'blocked', 'expired'])
def test_no_source_column_name_can_invent_access_or_derate_current(fault):
    board, roots, columns, tails, current = fixture()
    if fault == 'no_authority': current = None
    if fault == 'false_floor': current['required_by_layer_nm'][pcbnew.F_Cu] -= 1
    if fault == 'bool_current': current['current_authority']['amps'] = True
    if fault == 'wrong_profile': current['profile'] = 'other'
    if fault == 'thin_source': tails[0].SetWidth(200000)
    if fault == 'remote_port':
        columns[0].SetPosition(pcbnew.VECTOR2I_MM(11.6, 10)); tails[0].SetEnd(columns[0].GetPosition())
    if fault == 'partial_stack':
        columns[0].SetViaType(pcbnew.VIATYPE_BLIND); columns[0].SetLayerPair(pcbnew.In1_Cu, pcbnew.B_Cu)
    if fault == 'invalid_drill': columns[0].SetDrill(900000)
    if fault == 'no_columns':
        for c in columns: board.Remove(c)
    if fault == 'dnp': roots[0].GetParentFootprint().SetDNP(True)
    if fault == 'wrong_net':
        foreign = pcbnew.NETINFO_ITEM(board, 'FOREIGN'); board.Add(foreign); roots[1].SetNet(foreign)
    if fault == 'blocked':
        with mock.patch.object(fr, '_guarded_profiled_lastmile_legs', return_value=None):
            assert propose(board, roots, current) == (None, None)
    elif fault == 'expired':
        with mock.patch.object(ports.budget, 'exhausted', return_value=True):
            assert propose(board, roots, current) == (None, None)
    else:
        assert propose(board, roots, current) == (None, None)


@pytest.mark.parametrize('limit', [None, 0., True, float('inf'), -1.])
def test_unbounded_or_invalid_port_length_is_not_an_admission(limit):
    board, roots, _, _, current = fixture()
    with pytest.raises(ValueError):
        ports.plan(board, *roots, width_nm=1000000, clearance_nm=200000,
            current_widths=current, spec=dict(width=1000000),
            deadline_monotonic=time.monotonic() + 2., max_length_nm=limit)


def test_native_rail_completion_has_a_separate_bounded_detour_not_a_bypass_waiver():
    board, roots, _, _, current = fixture()
    native_guard = fr._guarded_profiled_lastmile_legs
    def detour(*args, **kwargs):
        a, b, w = args[1:4]
        middle = pcbnew.VECTOR2I(a.x, a.y + 2000000)
        other = pcbnew.VECTOR2I(b.x, middle.y)
        legs = [(a, middle, w), (middle, other, w), (other, b, w)]
        assert kwargs['max_length_nm'] == 8000000
        assert all(fr._edge_leg_clear(board, x, y, z // 2) for x, y, z in legs)
        return legs
    local = cells._local_supply_limit_mm(4., 1., .2)
    assert local < 8.
    with mock.patch.object(fr, '_guarded_profiled_lastmile_legs', side_effect=detour):
        ops, proof = ports.plan_rail(board, *roots, width_nm=1000000,
            clearance_nm=200000, current_widths=current, spec=dict(width=1000000),
            deadline_monotonic=time.monotonic() + 2.)
    assert ops and proof['max_rail_length_nm'] == 8000000
    assert not proof['capacitor_locality_waived'] and proof['old_native_islands_distinct']
    assert fr._guarded_profiled_lastmile_legs is native_guard


def test_already_native_connected_thin_source_is_not_a_fake_rail_open():
    board, roots, _, _, current = fixture()
    track = pcbnew.PCB_TRACK(board); track.SetNetCode(roots[0].GetNetCode())
    track.SetStart(roots[0].GetPosition()); track.SetEnd(roots[1].GetPosition())
    track.SetLayer(pcbnew.F_Cu); track.SetWidth(200000); board.Add(track)
    with mock.patch.object(ports, 'plan', side_effect=AssertionError('fake open')):
        assert ports.plan_rail(board, *roots, width_nm=1000000, clearance_nm=200000,
            current_widths=current, spec=dict(width=1000000),
            deadline_monotonic=time.monotonic() + 2.) == (None, None)


@pytest.mark.parametrize('flag,role', [(1, 'supply'), ('yes', 'supply'),
    (True, 'ground'), (True, 'shared-ground-entry')])
def test_local_cell_cannot_silently_opt_into_rail_context(flag, role):
    board, roots, _, _, _ = fixture()
    with pytest.raises(ValueError):
        cells._add_supply_link(board, *roots, lock=True,
            rail_completion=flag, link_role=role)


def test_unknown_current_does_not_unlock_whole_rail_geometry():
    board, roots, _, _, _ = fixture()
    with mock.patch.object(cells, '_supply_current_widths', return_value=None):
        result, error = cells._add_supply_link(board, *roots, lock=True,
            rail_completion=True)
    assert result is None and 'current authority' in error


@pytest.mark.parametrize('seconds', [None, 0., True, float('inf'), 11.])
def test_rail_context_cannot_request_an_unbounded_or_invalid_wall_lease(seconds):
    board, roots, _, _, _ = fixture()
    with pytest.raises(ValueError):
        cells._add_supply_link(board, *roots, lock=True,
            rail_completion=True, search_timeout_s=seconds)


@pytest.mark.parametrize('angle,back', [(0, False), (90, False), (180, True), (270, True)])
def test_integrated_rail_link_retains_source_columns_and_full_current_width(angle, back):
    board, roots, columns, _, current = fixture(angle=angle, back=back)
    old_vias = {c.m_Uuid.AsString() for c in columns}
    with mock.patch.object(cells, '_supply_current_widths', return_value=current), \
            mock.patch.object(cells, '_netclass', return_value=dict(
                width=1000000, clearance=200000, via_dia=.8, via_drill=.4)):
        result, error = cells._add_supply_link(board, *roots, lock=True,
            rail_completion=True, search_timeout_s=2., search_work_limit=8192)
    # Clear full-width surface copper needs no transition; blocked surfaces
    # may still use the independently guarded retained-column alternative.
    assert error is None and result['status'] in (
        'linked-full-current-surface', 'linked-retained-plated-ports')
    assert result['route_context'] == 'rail-island'
    assert all(t.GetClass() == 'PCB_TRACK' and t.GetWidth() >= max(1000000,
        current['required_by_layer_nm'][t.GetLayer()]) for t in result['items'])
    assert {t.m_Uuid.AsString() for t in board.GetTracks()
        if t.GetClass() == 'PCB_VIA'} == old_vias


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
def test_whole_rail_can_use_remote_source_current_column_but_local_bypass_cannot(angle):
    board, roots, columns, tails, current = fixture()
    columns[0].SetPosition(pcbnew.VECTOR2I_MM(12.4, 10))
    tails[0].SetEnd(columns[0].GetPosition())
    for fp in board.GetFootprints():
        fp.Rotate(pcbnew.VECTOR2I_MM(10, 10), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    for item in [*columns, *tails]:
        item.Rotate(pcbnew.VECTOR2I_MM(10, 10), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    assert propose(board, roots, current) == (None, None)
    ops, proof = ports.plan_rail(board, *roots, width_nm=1000000,
        clearance_nm=200000, current_widths=current, spec=dict(width=1000000),
        deadline_monotonic=time.monotonic() + 2.)
    assert ops and proof['terminal_scope'] == 'native-current-island'
    assert proof['retained_column_uuids'] == [c.m_Uuid.AsString() for c in columns]
    assert proof['native_source_current_sized_contact_graph']
    assert not proof['capacitor_locality_waived'] and not proof['barrel_capacity_qualified']


@pytest.mark.parametrize('angle,back', [(0, False), (90, False), (180, True), (270, True)])
def test_whole_rail_reuses_one_native_column_to_a_truly_isolated_land(angle, back):
    board, roots, columns, tails, current = fixture(angle=angle, back=back,
        netname='/renamed/ONE_SIDED_SERVICE', ref='OTHER_PACKAGE')
    board.Remove(tails[0]); board.Remove(columns[0])
    ops, proof = ports.plan_rail(board, *roots, width_nm=1000000,
        clearance_nm=200000, current_widths=current, spec=dict(width=1000000),
        deadline_monotonic=time.monotonic() + 2.)
    assert ops and proof['new_vias'] == 0 and not proof['barrel_capacity_qualified']
    assert proof['retained_column_uuids'] == [columns[1].m_Uuid.AsString()]
    assert proof['isolated_source_land_uuids'] == [roots[0].m_Uuid.AsString()]
    assert proof['isolated_source_lands_checked_in_raw_native_graph']
    native_faces = [l for l in board.GetEnabledLayers().CuStack() if roots[0].IsOnLayer(l)]
    assert len(native_faces) == 1 and all(op[4] == native_faces[0] for op in ops)
    assert max(op[3] for op in ops) >= max(1000000, current['required_by_layer_nm'][native_faces[0]])
    assert not proof['capacitor_locality_waived']
    # Local bypass semantics still do not acquire this whole-rail scope.
    assert propose(board, roots, current) == (None, None)


@pytest.mark.parametrize('fault', ['thin_source', 'nonisolated_land', 'foreign_blocker'])
def test_one_sided_port_does_not_invent_native_isolation_or_current_access(fault):
    board, roots, columns, tails, current = fixture()
    board.Remove(columns[0])
    if fault == 'nonisolated_land':
        # A real thin native twig must not disappear from the isolation proof.
        tails[0].SetWidth(200000)
    else:
        board.Remove(tails[0])
    if fault == 'thin_source': tails[1].SetWidth(200000)
    if fault == 'foreign_blocker':
        foreign = pcbnew.NETINFO_ITEM(board, '/NOT_THE_RAIL'); board.Add(foreign)
        fp = pcbnew.FOOTPRINT(board); board.Add(fp)
        obstacle = pcbnew.PAD(fp); obstacle.SetNet(foreign)
        obstacle.SetAttribute(pcbnew.PAD_ATTRIB_SMD); obstacle.SetLayerSet(pcbnew.PAD.SMDMask())
        obstacle.SetShape(pcbnew.PAD_SHAPE_RECT); obstacle.SetSize(pcbnew.VECTOR2I_MM(3, 3))
        obstacle.SetPosition(roots[0].GetPosition()); fp.Add(obstacle)
    ops, proof = ports.plan_rail(board, *roots, width_nm=1000000,
        clearance_nm=200000, current_widths=current, spec=dict(width=1000000),
        deadline_monotonic=time.monotonic() + 2.)
    assert ops is proof is None


@pytest.mark.parametrize('fault', ['thin_source', 'budgeted_source', 'invalid_column'])
def test_remote_rail_exit_cannot_cross_undersized_or_allocated_source_copper(fault):
    board, roots, columns, tails, current = fixture()
    columns[0].SetPosition(pcbnew.VECTOR2I_MM(12.4, 10))
    tails[0].SetEnd(columns[0].GetPosition())
    if fault == 'thin_source': tails[0].SetWidth(200000)
    if fault == 'budgeted_source':
        group = pcbnew.PCB_GROUP(board); group.SetName('CEC_CONTROL_CURRENT_SYNTHETIC')
        board.Add(group); group.AddItem(tails[0])
    if fault == 'invalid_column': columns[0].SetDrill(900000)
    assert ports.plan_rail(board, *roots, width_nm=1000000, clearance_nm=200000,
        current_widths=current, spec=dict(width=1000000),
        deadline_monotonic=time.monotonic() + 2.) == (None, None)
