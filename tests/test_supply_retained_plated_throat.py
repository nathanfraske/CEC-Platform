"""Existing cross-layer copper can satisfy a full-rated bounded pin escape."""
import time
from unittest import mock
import pcbnew
import pytest
import cec_decoupler_cell as cell
import cec_fr as fr
from cec_route_dimensions import current_trace_widths


AUTHORITY = dict(amps=1.1, geometry_margin=1.25, margin_included=False, source='synthetic')


def fixture(*, back=False, angle=0, netname='/unrelated/SUPPLY', ref='RENAMED_OWNER'):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    props = board.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    board.SetProperties(props)
    board.GetDesignSettings().m_TrackMinWidth = 200000
    net = pcbnew.NETINFO_ITEM(board, netname); board.Add(net)
    def pad(ref, pin, value, pos, size):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); fp.SetValue(value)
        fp.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD', 'SOT-23-6'))
        fp.SetPosition(pcbnew.VECTOR2I_MM(*pos))
        board.Add(fp)
        p = pcbnew.PAD(fp); p.SetNumber(pin); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetSize(pcbnew.VECTOR2I_MM(*size)); p.SetPosition(pcbnew.VECTOR2I_MM(*pos))
        p.SetNet(net); fp.Add(p)
        return p
    launch = pad(ref, '6', 'INA181A2IDBVR', (10, 10), (1.05, .4))
    landing = pad('UNRELATED_PASSIVE', '1', '100nF', (10.8, 10), (.8, .8))
    via = pcbnew.PCB_VIA(board); via.SetPosition(landing.GetPosition())
    via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetWidth(350000); via.SetDrill(250000); via.SetNet(net); board.Add(via)
    group = pcbnew.PCB_GROUP(board); group.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP)
    board.Add(group); group.AddItem(via)
    trunk = pcbnew.PCB_TRACK(board); trunk.SetStart(via.GetPosition())
    trunk.SetEnd(pcbnew.VECTOR2I_MM(13, 10)); trunk.SetWidth(1000000)
    trunk.SetLayer(pcbnew.B_Cu); trunk.SetNet(net); board.Add(trunk)
    for a, b in [((0, 0), (20, 0)), ((20, 0), (20, 20)),
                 ((20, 20), (0, 20)), ((0, 20), (0, 0))]:
        edge = pcbnew.PCB_SHAPE(); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts); board.Add(edge)
    for fp in board.GetFootprints():
        if back: fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if angle: fp.Rotate(pcbnew.VECTOR2I_MM(10, 10), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    if angle:
        via.Rotate(pcbnew.VECTOR2I_MM(10, 10), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
        trunk.Rotate(pcbnew.VECTOR2I_MM(10, 10), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    if back: trunk.SetLayer(pcbnew.F_Cu)
    widths = current_trace_widths(AUTHORITY,
        tuple(board.GetLayerName(l) for l in board.GetEnabledLayers().CuStack()),
        'jlcpcb_6l_pofv_signal', rise_c=30.)
    contract = dict(current_authority=AUTHORITY, required_by_layer_nm={
        board.GetLayerID(k): __import__('math').ceil(v*1e6) for k, v in widths.items()})
    return board, launch, landing, via, trunk, contract


def propose(board, launch, landing, contract):
    layer = pcbnew.B_Cu if launch.IsOnLayer(pcbnew.B_Cu) else pcbnew.F_Cu
    return cell._retained_supply_throat_ops(board, launch, landing, 1000000,
        200000, [layer], dict(via_dia=.8, via_drill=.4), contract,
        deadline_monotonic=time.monotonic()+2, max_length_nm=1500000)


@pytest.mark.parametrize('back,angle,net,ref', [(False, 0, 'RAIL_A', 'PART_A'),
    (False, 90, '/sheet/RAIL_B', 'DEVICE_B'), (True, 180, 'OTHER_C', 'OWNER_C'),
    (True, 270, '/nested/OTHER_D', 'SOMETHING_D')])
def test_retained_full_current_throat_needs_no_new_barrel(back, angle, net, ref):
    board, launch, landing, via, trunk, contract = fixture(back=back, angle=angle, netname=net, ref=ref)
    old = {t.m_Uuid.AsString() for t in board.GetTracks()}
    ops, proof = propose(board, launch, landing, contract)
    assert ops and proof and proof['retained_via_uuid'] == via.m_Uuid.AsString()
    assert all(op[0] == 'trk' and op[3] >= contract['required_by_layer_nm'][op[4]] for op in ops)
    assert sum((op[2]-op[1]).EuclideanNorm() for op in ops) <= 1500000
    assert proof['retained_full_width_track_uuids'] == [trunk.m_Uuid.AsString()]
    assert not proof['barrel_capacity_qualified'] and old == {t.m_Uuid.AsString() for t in board.GetTracks()}


@pytest.mark.parametrize('fault', ['no_current', 'untyped', 'measurement', 'dnp',
    'no_group', 'wrong_via_net', 'no_trunk', 'thin_trunk', 'inner_under_current',
    'off_pad', 'illegal_via', 'remote', 'expired', 'too_much_current'])
def test_no_label_or_retained_barrel_can_waive_current_or_native_geometry(fault):
    board, launch, landing, via, trunk, contract = fixture()
    if fault == 'no_current': contract = None
    if fault == 'untyped': launch.GetParentFootprint().SetValue('UNKNOWN')
    if fault == 'measurement': launch.SetNumber('3')
    if fault == 'dnp': launch.GetParentFootprint().SetDNP(True)
    if fault == 'no_group': via.GetParentGroup().RemoveItem(via)
    if fault == 'wrong_via_net':
        other = pcbnew.NETINFO_ITEM(board, 'OTHER'); board.Add(other); via.SetNet(other)
    if fault == 'no_trunk': board.Remove(trunk)
    if fault == 'thin_trunk': trunk.SetWidth(200000)
    if fault == 'inner_under_current': trunk.SetLayer(pcbnew.In2_Cu)
    if fault == 'off_pad': via.SetPosition(pcbnew.VECTOR2I_MM(11.3, 10))
    if fault == 'illegal_via': via.SetDrill(320000)
    if fault == 'remote': launch.SetPosition(pcbnew.VECTOR2I_MM(8, 10))
    if fault == 'too_much_current':
        contract = dict(contract, required_by_layer_nm={k: max(v, 600000) for k, v in contract['required_by_layer_nm'].items()})
    if fault == 'expired':
        with mock.patch.object(cell.cec_search_budget, 'exhausted', return_value=True):
            assert propose(board, launch, landing, contract) == (None, None)
    else:
        assert propose(board, launch, landing, contract) == (None, None)


def test_new_off_pad_bridge_owes_the_complete_copper_web():
    board, launch, landing, via, trunk, _ = fixture()
    board.Remove(via); board.Remove(trunk)
    observed = []
    def via_clear(_board, _point, diameter, *_args, **_kwargs):
        observed.append(diameter)
        return diameter >= 1400000
    with mock.patch.object(fr, '_via_spot_clear', side_effect=via_clear):
        ops, evidence = cell._pofv_supply_bridge_ops(board, launch, landing,
            1000000, 200000, launch.GetNetCode(), [pcbnew.B_Cu],
            dict(via_dia=.8, via_drill=.4),
            deadline_monotonic=time.monotonic()+2, allow_maze=False)
    assert ops and evidence
    vias = [op for op in ops if op[0] == 'via']
    assert vias and all(op[3] - op[2] >= 1. - 1e-9 for op in vias)
    assert any(d >= 1400000 for d in observed)
