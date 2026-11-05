"""Current floors survive small netclasses and fine manufacturer supply lands."""
import math
from unittest import mock

import pcbnew
import pytest

import cec_constraints as constraints
import cec_decoupler_cell as cell
import cec_fr as fr
from cec_route_dimensions import current_trace_widths


AUTHORITY = dict(amps=3., geometry_margin=1.25, margin_included=False,
                 source='synthetic_executable_current_contract')
PROFILE = 'jlcpcb_6l_pofv_signal'


def fixture(*, net='RENAMED_SUPPLY', ref='UNRELATED_REFERENCE', pin='6',
            value='INA181A2IDBVR', group=True, length=.8, throat=True,
            back=False, angle=0):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    props = board.GetProperties(); props['CEC_FAB_PROFILE'] = PROFILE
    board.SetProperties(props)
    supply = pcbnew.NETINFO_ITEM(board, net); board.Add(supply)
    fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); fp.SetValue(value)
    fp.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD', 'SOT-23-6'))
    board.Add(fp)
    pad = pcbnew.PAD(fp); pad.SetNumber(pin); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I_MM(1.05, .4))
    pad.SetPosition(pcbnew.VECTOR2I_MM(10, 10)); pad.SetLayerSet(pcbnew.PAD.SMDMask())
    pad.SetNet(supply); fp.Add(pad)
    layer = pcbnew.B_Cu if back else pcbnew.F_Cu
    required = math.ceil(current_trace_widths(AUTHORITY,
        (board.GetLayerName(layer),), PROFILE, rise_c=30.)[board.GetLayerName(layer)] * 1e6)
    def track(a, b, width):
        item = pcbnew.PCB_TRACK(board); item.SetStart(pcbnew.VECTOR2I_MM(*a))
        item.SetEnd(pcbnew.VECTOR2I_MM(*b)); item.SetWidth(width)
        item.SetLayer(pcbnew.F_Cu); item.SetNet(supply); board.Add(item)
        return item
    thin = track((10, 10), (10 + length, 10), 200000)
    if throat:track((10 + length, 10), (13, 10), required)
    if group:
        owned = pcbnew.PCB_GROUP(board); owned.SetName(fr.ENDPOINT_NECKDOWN_GROUP)
        board.Add(owned); owned.AddItem(thin)
    if back:
        fp.Flip(pcbnew.VECTOR2I_MM(10, 10), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for item in board.GetTracks():
            item.Flip(pcbnew.VECTOR2I_MM(10, 10), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if angle:
        for item in [fp, *board.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I_MM(10, 10), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    return board, thin, required


def legal(board, domains=None):
    return constraints._validated_current_supply_escape_uuids(
        board, lambda _net: AUTHORITY, PROFILE, domains or {})


@pytest.mark.parametrize('back,angle,net,ref', [
    (False, 0, 'RENAMED_SUPPLY', 'IC_A'),
    (False, 90, '/deep/OTHER_RAIL', 'DEVICE_B'),
    (True, 180, 'SUPPLY_C', 'NOT_AN_U_REFERENCE'),
    (True, 270, '/different/VDD', 'FOURTH_OWNER'),
])
def test_current_prefix_uses_native_supply_role_and_full_width_throat(back, angle, net, ref):
    board, thin, required = fixture(back=back, angle=angle, net=net, ref=ref)
    assert required > thin.GetWidth()
    assert legal(board) == {thin.m_Uuid.AsString()}


@pytest.mark.parametrize('fault', ['no_group', 'no_throat', 'remote', 'measurement',
    'untyped', 'tht', 'aggregate', 'ground', 'too_many_fragments', 'branch'])
def test_group_label_cannot_waive_arbitrary_thin_power_material(fault):
    board, thin, _ = fixture(group=fault != 'no_group', throat=fault != 'no_throat',
        length=2. if fault == 'remote' else .8, pin='3' if fault == 'measurement' else '6',
        value='UNKNOWN_DEVICE' if fault == 'untyped' else 'INA181A2IDBVR',
        net='/local/GND' if fault == 'ground' else 'RENAMED_SUPPLY')
    if fault == 'tht':
        pad = list(list(board.GetFootprints())[0].Pads())[0]
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH); pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2, .2))
    if fault in ('too_many_fragments', 'branch'):
        from cec_native_items import discard_items
        group = next(iter(board.Groups()))
        discard_items(board, [thin])
        points = [(10 + i * .16, 10) for i in range(6)] if fault == 'too_many_fragments' else [
            (10, 10), (10.4, 10), (10.8, 10)]
        pairs = list(zip(points, points[1:]))
        if fault == 'branch':pairs.append(((10.4, 10), (10.4, 10.2)))
        for a, b in pairs:
            t = pcbnew.PCB_TRACK(board); t.SetStart(pcbnew.VECTOR2I_MM(*a))
            t.SetEnd(pcbnew.VECTOR2I_MM(*b)); t.SetWidth(200000); t.SetLayer(pcbnew.F_Cu)
            t.SetNet(board.FindNet('RENAMED_SUPPLY')); board.Add(t); group.AddItem(t)
    assert not legal(board, {'RENAMED_SUPPLY': {}} if fault == 'aggregate' else None)


def test_supply_constructor_derives_existing_margin_profile_and_layer_widths():
    board, _, _ = fixture(); board.SetFileName('anonymous-worker.kicad_pcb')
    with mock.patch.dict(cell.os.environ, {'CEC_THERMAL_BOARD_HINT': 'design-authority'}), \
            mock.patch('cec_synth_pipeline.spec_net_current_contract', return_value=AUTHORITY) as authority:
        result = cell._supply_current_widths(board, 'RENAMED_SUPPLY')
    # Static/domain reconciliation may independently query the same source
    # twice. Assert the actual design binding and unchanged budget, not an
    # incidental call count which predates that hardening.
    authority.assert_called_with('design-authority', 'RENAMED_SUPPLY')
    assert all(call == mock.call('design-authority', 'RENAMED_SUPPLY')
        for call in authority.call_args_list)
    assert result['current_authority'] == AUTHORITY
    assert result['required_by_layer_nm'][pcbnew.F_Cu] > 200000
    assert result['required_by_layer_nm'][pcbnew.In2_Cu] > result['required_by_layer_nm'][pcbnew.F_Cu]
    assert not result['release_authority'] and not result['barrel_capacity_qualified']


def test_unknown_current_is_not_filled_with_a_guessed_device_load():
    board, _, _ = fixture(); board.SetFileName('unknown-authority.kicad_pcb')
    with mock.patch('cec_synth_pipeline.spec_net_current_contract', return_value=None):
        assert cell._supply_current_widths(board, 'RENAMED_SUPPLY') is None


def test_small_class_cannot_select_an_undersized_inner_supply_bridge():
    board, _, required = fixture(); board.SetFileName('synthetic-current-board.kicad_pcb')
    owner = list(list(board.GetFootprints())[0].Pads())[0]
    fp = pcbnew.FOOTPRINT(board); fp.SetReference('RENAMED_BYPASS'); board.Add(fp)
    cap = pcbnew.PAD(fp); cap.SetNumber('1'); cap.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    cap.SetLayerSet(pcbnew.PAD.SMDMask()); cap.SetShape(pcbnew.PAD_SHAPE_RECT)
    cap.SetSize(pcbnew.VECTOR2I_MM(1, 1)); cap.SetPosition(pcbnew.VECTOR2I_MM(12, 10))
    cap.SetNet(owner.GetNet()); fp.Add(cap)
    from cec_native_items import discard_items
    discard_items(board, list(board.GetTracks()))
    widths = current_trace_widths(AUTHORITY, ('F.Cu', 'B.Cu', 'In2.Cu'), PROFILE, rise_c=30.)
    with mock.patch('cec_synth_pipeline.spec_net_current_contract', return_value=AUTHORITY), \
            mock.patch.object(cell.cec_fr, '_guarded_profiled_lastmile_legs', return_value=None) as planar, \
            mock.patch.object(cell, '_pofv_supply_bridge_ops', return_value=(None, None)), \
            mock.patch.object(cell.cec_fr, '_lastmile_bridge', return_value=None) as bridge, \
            mock.patch.object(cell.cec_fr, '_lastmile_refusal_certificate', return_value={'search': {}}):
        result, error = cell._add_supply_link(board, owner, cap, lock=True)
    assert result is None and error
    assert all(call.args[3] >= required for call in planar.call_args_list)
    assert bridge.call_count and all(call.args[5] >= required for call in bridge.call_args_list)
    assert widths['In2.Cu'] > widths['F.Cu']
    assert all(pcbnew.In2_Cu not in call.args[7] for call in bridge.call_args_list)
    assert all(pcbnew.B_Cu in call.args[7] for call in bridge.call_args_list)
    assert all(call.kwargs['minimum_local_via_web_nm'] >= required
        and pcbnew.FromMM(call.kwargs['dia']) - pcbnew.FromMM(call.kwargs['drill']) >= required
        for call in bridge.call_args_list)


def test_supply_refinement_is_opt_in_and_keeps_one_finite_lease():
    seen = []
    def impl(*args, **kwargs):
        seen.append(kwargs)
        return None, 'no guarded local supply path within locality bound'
    with mock.patch.object(cell, '_add_supply_link_impl', side_effect=impl):
        cell._add_supply_link(None, None, None, lock=True, refine_maze=True, search_timeout_s=1.)
    assert len(seen) == 2 and all(row['refine_maze'] is True for row in seen)
    assert seen[0]['deadline_monotonic'] == seen[1]['deadline_monotonic']
    with pytest.raises(ValueError):
        cell._add_supply_link(None, None, None, lock=True, refine_maze=True, search_timeout_s=None)
    with pytest.raises(ValueError):
        cell._add_supply_link(None, None, None, lock=True, refine_maze='yes')


@pytest.mark.parametrize('first_mode', ['assigned-pofv', 'fallback-pofv'])
def test_no_supply_fallback_can_commit_a_new_undersized_transition(first_mode):
    board, _, required = fixture(); board.SetFileName('synthetic-current-board.kicad_pcb')
    owner = list(list(board.GetFootprints())[0].Pads())[0]
    fp = pcbnew.FOOTPRINT(board); fp.SetReference('OTHER_PASSIVE'); board.Add(fp)
    cap = pcbnew.PAD(fp); cap.SetNumber('1'); cap.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    cap.SetLayerSet(pcbnew.PAD.SMDMask()); cap.SetShape(pcbnew.PAD_SHAPE_RECT)
    cap.SetSize(pcbnew.VECTOR2I_MM(1, 1)); cap.SetPosition(pcbnew.VECTOR2I_MM(12, 10))
    cap.SetNet(owner.GetNet()); fp.Add(cap)
    from cec_native_items import discard_items
    discard_items(board, list(board.GetTracks()))
    undersized = [('trk', owner.GetPosition(), cap.GetPosition(), required, pcbnew.F_Cu),
        ('via', cap.GetPosition(), .25, .5)]
    assigned = (undersized, {}) if first_mode == 'assigned-pofv' else (None, None)
    with mock.patch('cec_synth_pipeline.spec_net_current_contract', return_value=AUTHORITY), \
            mock.patch.object(fr, '_guarded_profiled_lastmile_legs', return_value=None), \
            mock.patch.object(cell, '_pofv_supply_bridge_ops', return_value=assigned), \
            mock.patch.object(fr, '_lastmile_bridge', return_value=undersized), \
            mock.patch.object(fr, '_lastmile_refusal_certificate', return_value={'search': {}}):
        result, error = cell._add_supply_link(board, owner, cap, lock=True)
    assert result is None and error and not list(board.GetTracks())


@pytest.mark.parametrize('seconds', [float('inf'), float('nan'), 0, -1, 10.1, True, '10'])
def test_fine_supply_search_cannot_escape_the_ten_second_wall_bound(seconds):
    with pytest.raises(ValueError, match='bounded_explicit_supply_maze_refinement_required'):
        cell._add_supply_link(None, None, None, lock=True, refine_maze=True, search_timeout_s=seconds)


def test_elongated_supply_land_uses_shared_bounded_native_escape():
    board, _, _ = fixture(); pad = list(list(board.GetFootprints())[0].Pads())[0]
    width = 477370
    result = fr._pad_local_escape(pad, width, 200000, 200000)
    assert result[0] == 200000
    assert result[1] == round(1.05e6 / 2 + 200000 + width / 2)
    pad.SetSize(pcbnew.VECTOR2I_MM(10, .4))
    assert fr._pad_local_escape(pad, width, 200000, 200000)[1] == 1500000
