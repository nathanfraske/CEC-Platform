"""Ground-tied controls are not manufacturer device-return terminals."""
from unittest import mock

import pcbnew
import pytest

import cec_decoupler_cell as cells
import cec_field_coupling as field


def fixture(*, turn=0, layer=pcbnew.F_Cu, value="TPS2121RUXR",
            ground="12", controls=("3", "4")):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    nets = {}
    for name in ("GND", "/ARBITRARY_RAIL", "/ARBITRARY_RETURN"):
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        nets[name] = net

    def at(x, y):
        dx, dy = x - 20, y - 20
        for _ in range(turn):
            dx, dy = dy, -dx
        return pcbnew.VECTOR2I_MM(20 + dx, 20 + dy)

    def part(ref, selected, rows):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref)
        fp.SetValue(selected)
        fp.SetLayer(layer)
        board.Add(fp)
        for number, net, x, y in rows:
            pad = pcbnew.PAD(fp)
            pad.SetNumber(number)
            pad.SetNet(nets[net])
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.3, .5))
            pad.SetPosition(at(x, y))
            pad.SetOrientationDegrees(turn * 90)
            layers = pcbnew.LSET()
            layers.AddLayer(layer)
            pad.SetLayerSet(layers)
            fp.Add(pad)
        return fp

    owner = part("ANY_DEVICE_" + str(turn), value,
                 [(ground, "GND", 20, 20),
                  ("SUPPLY", "/ARBITRARY_RAIL", 19, 20),
                  ("RAIL_RETURN", "/ARBITRARY_RETURN", 20, 21.5)] +
                 [(pin, "GND", 20, 20.5 + index * .5)
                  for index, pin in enumerate(controls)])
    cap = part("ANY_CERAMIC_" + str(turn), "100nF",
               [("1", "/ARBITRARY_RAIL", 21, 19.5),
                ("2", "GND", 21, 20.5)])
    req = dict(id="source-assigned-cell", ref=owner.GetReference(),
               pin="SUPPLY", pad=owner.FindPadByNumber("SUPPLY"),
               rail="/ARBITRARY_RAIL", return_rail="GND",
               return_pin=None, return_pad=None, kind="100n", max_mm=3.5)
    return board, owner, cap, req


@pytest.mark.parametrize("turn,layer", [(0, pcbnew.F_Cu), (1, pcbnew.F_Cu),
                                      (2, pcbnew.B_Cu), (3, pcbnew.B_Cu)])
@pytest.mark.parametrize("value,ground,controls", [
    ("TPS2121RUXR", "12", ("3", "4")),
    ("INA238", "7", ("1", "2")),
    ("LP5907MFX-3.3/NOPB", "2", ("3", "4")),
    ("TLV7011DBVR", "2", ("3", "4")),
])
def test_only_actual_manufacturer_returns_are_eligible(turn, layer, value, ground, controls):
    board, owner, cap, req = fixture(turn=turn, layer=layer, value=value,
                                    ground=ground, controls=controls)
    before = field._field_snapshot_inventory(board)
    rail, cap_return, returns = cells._cell_return_pads(req, owner, cap)
    assert rail == "GND" and cap_return.GetNumber() == "2"
    assert [pad.GetNumber() for pad in returns] == [ground]
    evidence = cells._owner_return_role_evidence(owner, rail)
    assert evidence["manufacturer_ground_role_qualified"]
    assert evidence["source"].startswith("https://www.ti.com/")
    assert not evidence["current_or_fabrication_qualification"]
    assert field._field_snapshot_inventory(board) == before


@pytest.mark.parametrize("pin", ["3", "4", "MISSING"])
def test_explicit_bad_return_is_refused_not_rebound(pin):
    _, owner, cap, req = fixture()
    req["return_pin"] = pin
    req["return_pad"] = owner.FindPadByNumber(pin)
    assert cells._cell_return_pads(req, owner, cap)[2] == []


def test_foreign_footprint_pad_cannot_satisfy_explicit_return_contract():
    board, owner, cap, req = fixture()
    foreign = pcbnew.FOOTPRINT(board)
    board.Add(foreign)
    pad = pcbnew.PAD(foreign)
    pad.SetNumber("12")
    pad.SetNet(board.FindNet("GND"))
    foreign.Add(pad)
    req["return_pin"], req["return_pad"] = "12", pad
    assert cells._cell_return_pads(req, owner, cap)[2] == []


def test_unknown_manufacturer_keeps_native_contract_explicitly_unqualified():
    _, owner, cap, req = fixture(value="UNQUALIFIED_DEVICE")
    assert len(cells._cell_return_pads(req, owner, cap)[2]) == 3
    evidence = cells._owner_return_role_evidence(owner, "GND")
    assert evidence["scope"] == "native-net-only-unresolved"
    assert evidence["manufacturer_ground_role_qualified"] is False
    assert evidence["source"] is None


def test_package_identity_contradiction_never_becomes_unknown_role_fallback():
    _, owner, cap, req = fixture(value="INA240A1DR", ground="2", controls=("3", "7"))
    owner.SetFPID(pcbnew.LIB_ID("Package_SO", "TSSOP-8_3x3mm_P0.65mm"))
    with pytest.raises(ValueError, match="manufacturer_selected_package_footprint_mismatch"):
        cells._cell_return_pads(req, owner, cap)


def test_rail_to_rail_return_retains_its_explicit_source_endpoint():
    board, owner, cap, req = fixture()
    cap.FindPadByNumber("2").SetNet(board.FindNet("/ARBITRARY_RETURN"))
    req.update(return_rail="/ARBITRARY_RETURN", return_pin="RAIL_RETURN",
               return_pad=owner.FindPadByNumber("RAIL_RETURN"))
    rail, _, pads = cells._cell_return_pads(req, owner, cap)
    assert rail == "/ARBITRARY_RETURN" and [p.GetNumber() for p in pads] == ["RAIL_RETURN"]
    assert cells._owner_return_role_evidence(owner, rail)["scope"] == "explicit-rail-to-rail-contract"
    req["return_pad"] = owner.FindPadByNumber("12")
    assert cells._cell_return_pads(req, owner, cap)[2] == []


def test_control_portal_cannot_preempt_actual_ground_dogbone_construction():
    board, owner, _, _ = fixture()
    target = owner.FindPadByNumber("12")
    probed = []

    def existing(_board, pad, *_args, **_kwargs):
        probed.append(pad.GetNumber())
        assert pad.GetNumber() not in ("3", "4")
        return None

    class ReachedActualGroundConstructor(Exception):
        pass

    with mock.patch.object(cells, "_existing_return", side_effect=existing), \
            mock.patch.object(cells, "_reconnect_existing_ground_via", return_value=None), \
            mock.patch.object(cells, "_add_supply_link") as link, \
            mock.patch.object(cells, "_ground_terminal_layer", side_effect=ReachedActualGroundConstructor):
        with pytest.raises(ReachedActualGroundConstructor):
            cells._add_ground_return(board, target, board_path="arbitrary-board",
                                     reach_mm=1.5, lock=True)
    assert probed == ["12"]
    link.assert_not_called()


def test_cell_audit_does_not_claim_control_pin_portal_as_device_ground():
    board, owner, cap, req = fixture()
    assignment = dict(requirements=[req], missing=[], assigned={req["id"]:
                      dict(requirement=req, cap_ref=cap.GetReference(), distance_mm=1.)})
    via = pcbnew.PCB_VIA(board)

    def existing(_board, pad, *_args, **_kwargs):
        assert pad.GetNumber() not in ("3", "4")
        return (.2, via) if pad.GetParentFootprint().GetReference() == cap.GetReference() else None

    with mock.patch.object(cells.cec_constraints, "_device_bypass_assignment", return_value=assignment), \
            mock.patch.object(cells, "_shortest_track_path_mm", return_value=1.), \
            mock.patch.object(cells, "_existing_return", side_effect=existing), \
            mock.patch.object(cells, "_shared_ground_return", return_value=None):
        result = cells.audit_board(board)
    assert not result["ok"]
    assert result["cells"][0]["owner_ground_pin"] == "12"
    assert "owner GND pin has no connected via" in result["refused"][0]["reason"]
