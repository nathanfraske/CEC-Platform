"""Supply layer transitions reuse native PTH contacts without another drill."""
import time
from unittest import mock

import pcbnew
import pytest

import cec_decoupler_cell as cells
import cec_fr as fr


def fixture(*, back=False, angle=0, reference='EDGE_CONNECTOR',
            netname='ARBITRARY_SUPPLY'):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    properties = board.GetProperties()
    properties['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    board.SetProperties(properties)
    net = pcbnew.NETINFO_ITEM(board, netname)
    board.Add(net)
    lands = []
    for index, x in enumerate((10, 14)):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(reference + str(index))
        board.Add(fp)
        pad = pcbnew.PAD(fp)
        pad.SetNumber('1')
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(pcbnew.VECTOR2I_MM(2, 2))
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(1, 1))
        pad.SetLayerSet(pcbnew.PAD.PTHMask())
        pad.SetPosition(pcbnew.VECTOR2I_MM(x, 10))
        pad.SetNet(net)
        fp.Add(pad)
        if back:
            fp.Flip(pad.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if angle:
            fp.Rotate(pad.GetPosition(), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
        lands.append(pad)
    return board, lands


def bridge(board, lands):
    return cells._pofv_supply_bridge_ops(
        board, *lands, 1000000, 200000, lands[0].GetNetCode(),
        [pcbnew.In2_Cu], {'via_dia': .8, 'via_drill': .4},
        deadline_monotonic=time.monotonic() + 2, allow_maze=False)


@pytest.mark.parametrize('back,angle,reference,netname', [
    (False, 0, 'HEADER_A', 'VDD_A'),
    (False, 90, 'CONNECTOR_B', '/sheet/RENAMED_RAIL'),
    (True, 180, 'PART_C', 'SUPPLY_C'),
    (True, 270, 'OTHER_D', '/nested/OTHER_SUPPLY'),
])
def test_two_native_plated_lands_need_only_full_width_inner_copper(
        back, angle, reference, netname):
    board, lands = fixture(back=back, angle=angle,
        reference=reference, netname=netname)
    before = {p.m_Uuid.AsString() for f in board.GetFootprints() for p in f.Pads()}
    ops, evidence = bridge(board, lands)
    assert ops and all(op[0] == 'trk' for op in ops)
    assert all(op[3] == 1000000 and op[4] == pcbnew.In2_Cu for op in ops)
    assert evidence['endpoint_modes'] == ['existing-plated-pad'] * 2
    assert evidence['reused_endpoint_via_uuids'] == []
    assert evidence['diameter_mm'] == evidence['drill_mm'] == 0
    assert not evidence['qualified_process_exception']
    assert not list(board.GetTracks())
    assert before == {p.m_Uuid.AsString() for f in board.GetFootprints() for p in f.Pads()}


def test_native_plated_to_existing_surface_barrel_needs_no_new_vias():
    board, lands = fixture()
    pad = lands[1]
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetDrillSize(pcbnew.VECTOR2I(0, 0))
    pad.SetLayerSet(pcbnew.PAD.SMDMask())
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pad.GetPosition())
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetWidth(800000)
    via.SetDrill(400000)
    via.SetNet(pad.GetNet())
    board.Add(via)
    ops, evidence = bridge(board, lands)
    assert ops and all(op[0] == 'trk' for op in ops)
    assert evidence['endpoint_modes'] == ['existing-plated-pad', 'existing-via']
    assert evidence['reused_endpoint_via_uuids'] == [via.m_Uuid.AsString()]
    assert list(board.GetTracks()) == [via]


@pytest.mark.parametrize('fault', ['npth', 'smd', 'zero_drill', 'partial_stack'])
def test_unplated_or_partial_geometry_never_grants_plated_transition(fault):
    board, lands = fixture()
    pad = lands[0]
    if fault == 'npth':
        pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    elif fault == 'smd':
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetDrillSize(pcbnew.VECTOR2I(0, 0))
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
    elif fault == 'zero_drill':
        pad.SetDrillSize(pcbnew.VECTOR2I(0, 0))
    else:
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
    # Refuse every legitimate fallback. A false PTH fast path would still
    # return inner-layer operations and is caught by this negative control.
    with mock.patch.object(cells, '_existing_supply_column', return_value=None), \
            mock.patch.object(fr, '_via_spot_clear', return_value=False):
        ops, evidence = bridge(board, lands)
    assert ops is None and evidence is None
