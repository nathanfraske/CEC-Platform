"""Live local-via ownership cannot be inferred from dimensions or proximity."""
import hashlib

import pytest

pcbnew = pytest.importorskip("pcbnew")
import cec_fab_profile as fab
import cec_fr
import cec_constraints
import cec_certificate_repair as repair


def fixture(*, offset=(0.625, 0), size=(0.8, 0.8), diameter=0.35,
            drill=0.25, layer=None, connected=True, angle=0):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    props = board.GetProperties()
    props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
    board.SetProperties(props)
    net = pcbnew.NETINFO_ITEM(board, "/ARBITRARY")
    board.Add(net)
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("TEST_OWNER")
    pad = pcbnew.PAD(fp)
    pad.SetPadName("arbitrary")
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(*size))
    pad.SetPosition(pcbnew.VECTOR2I_MM(20, 30))
    pad.SetOrientationDegrees(angle)
    pad.SetLayerSet(pcbnew.PAD.SMDMask())
    pad.SetNet(net)
    fp.Add(pad)
    board.Add(fp)
    via = pcbnew.PCB_VIA(board)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetPosition(pcbnew.VECTOR2I_MM(20 + offset[0], 30 + offset[1]))
    via.SetWidth(pcbnew.FromMM(diameter))
    via.SetDrill(pcbnew.FromMM(drill))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net)
    board.Add(via)
    if connected:
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pad.GetPosition())
        track.SetEnd(via.GetPosition())
        track.SetLayer(pcbnew.F_Cu if layer is None else layer)
        track.SetWidth(pcbnew.FromMM(0.2))
        track.SetNet(net)
        board.Add(track)
    return board, via


@pytest.mark.parametrize("kwargs,expected", [
    ({}, True),
    ({"offset": (0, 0), "connected": False}, True),
    ({"connected": False}, False),
    ({"layer": pcbnew.B_Cu}, False),
    ({"offset": (2, 0)}, False),
    ({"offset": (0.4, 0), "size": (0.7, 0.7)}, False),
    ({"offset": (0, 0.05), "size": (0.8, 0.4),
      "diameter": 0.6, "drill": 0.3}, False),
    ({"offset": (0.05, 0), "size": (0.8, 0.4), "angle": 90,
      "diameter": 0.3, "drill": 0.2}, True),
])
def test_intake_and_independent_reproof_agree(kwargs, expected):
    board, via = fixture(**kwargs)
    assert fab.local_pofv_via_decision(board, via)[0] is expected
    evidence = cec_fr.group_local_pofv_signal_vias(board, [via])
    assert bool(evidence) is expected
    assert via.IsLocked() is expected
    # Even a copied group cannot bypass the independent geometry proof.
    if not expected:
        group = pcbnew.PCB_GROUP(board)
        group.SetName(cec_fr.LOCAL_POFV_SIGNAL_VIA_GROUP)
        board.Add(group)
        group.AddItem(via)
    valid = cec_constraints._validated_local_pofv_signal_uuids(
        board, "synthetic.kicad_pcb", {})
    assert (via.m_Uuid.AsString() in valid) is expected


def test_owned_via_from_another_cell_is_not_adopted():
    board, via = fixture()
    group = pcbnew.PCB_GROUP(board)
    group.SetName("ANOTHER_CELL_OWNER")
    board.Add(group)
    group.AddItem(via)
    assert cec_fr.group_local_pofv_signal_vias(board, [via]) is None
    assert not via.IsLocked()


def test_dogbone_normalizer_refuses_partial_pad_overlap_without_writing(tmp_path):
    board, via = fixture(offset=(0.4, 0), size=(0.7, 0.7),
                         diameter=0.6, drill=0.3)
    path = str(tmp_path / "overlap.kicad_pcb")
    pcbnew.SaveBoard(path, board)
    before = hashlib.sha256(open(path, "rb").read()).hexdigest()
    changed, _ = repair._normalize_pad_owned_via_to_profile_worker(
        path, via.m_Uuid.AsString())
    assert not changed
    assert hashlib.sha256(open(path, "rb").read()).hexdigest() == before
    assert not (tmp_path / "overlap.kicad_dru").exists()
