import copy

import pcbnew
import pytest

import cec_explicit_shunt_leaf as shunt
import cec_force_current as force
import cec_measurement_leaf as leaf
from cec_native_items import discard_items


def fixture(monkeypatch, *, quarter=0, alias="renamed_rail", face=pcbnew.F_Cu):
    import cec_decoupler_cell as cell
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    rail = pcbnew.NETINFO_ITEM(board, alias); board.Add(rail)
    gnd = pcbnew.NETINFO_ITEM(board, "return_alias"); board.Add(gnd)
    owner = pcbnew.FOOTPRINT(board); owner.SetReference("arbitrary_device")
    owner.SetValue("TPS2121RUXR"); owner.SetLayer(face); board.Add(owner)
    cap = pcbnew.FOOTPRINT(board); cap.SetReference("renamed_reservoir")
    cap.SetValue("10uF"); cap.SetFPID(pcbnew.LIB_ID("cec-Capacitor_SMD", "C_0805"))
    cap.SetLayer(face); board.Add(cap)
    def pad(fp, pin, at, net):
        p = pcbnew.PAD(fp); p.SetNumber(pin); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetSize(pcbnew.VECTOR2I_MM(.8, .8))
        layers = pcbnew.LSET(); layers.AddLayer(face); p.SetLayerSet(layers)
        p.SetPosition(pcbnew.VECTOR2I_MM(*at)); p.SetNet(net); fp.Add(p)
        return p
    owners = []
    for pin in range(1, 13):
        p = pad(owner, str(pin), (5+pin, 5), rail if pin in (1, 2, 7, 8) else gnd)
        if pin in (1, 8): owners.append(p)
    support = pad(cap, "1", (20, 18), rail)
    pad(cap, "2", (20, 19.5), gnd)
    tracks = []
    for start, end in [((20, 18), (22, 18)), ((22, 18), (24, 18))]:
        t = pcbnew.PCB_TRACK(board); t.SetStart(pcbnew.VECTOR2I_MM(*start))
        t.SetEnd(pcbnew.VECTOR2I_MM(*end)); t.SetWidth(200000)
        t.SetLayer(face); t.SetNet(rail); t.SetLocked(True); board.Add(t); tracks.append(t)
    via = pcbnew.PCB_VIA(board); via.SetPosition(pcbnew.VECTOR2I_MM(24, 18))
    via.SetWidth(600000); via.SetDrill(300000); via.SetNet(rail)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(via)
    if quarter:
        turn = pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(), *board.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I_MM(20, 20), turn)
    binding = dict(support_pad_uuid=force._uid(support),
        owner_pad_uuids=[force._uid(p) for p in owners], return_net="return_alias")
    rating = dict(required_by_layer_nm={face:600000}, unchanged_aggregate_load=True)
    monkeypatch.setattr(cell, "_supply_current_widths", lambda *a, **k: rating)
    return board, cap, owner, support, tracks, via, binding, rating


@pytest.mark.parametrize("quarter", range(4))
@pytest.mark.parametrize("face", [pcbnew.F_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize("alias", ["arbitrary_rail", "/nested/name"])
def test_explicit_far_reservoir_owns_only_thin_old_feed_not_barrel_or_a_smaller_load(
        monkeypatch, quarter, face, alias):
    board, cap, owner, pad, tracks, via, binding, rating = fixture(
        monkeypatch, quarter=quarter, face=face, alias=alias)
    before = leaf._binding(board); original = copy.deepcopy(binding)
    q = shunt.plan_supply(board, binding, board_hint="caller-authority")
    assert q["track_uuids"] == [force._uid(t) for t in tracks]
    assert q["boundary_uuids"] == [force._uid(via)]
    assert force._uid(via) not in q["track_uuids"]
    assert q["required_replacement_width_nm"] == 600000
    assert q["source_width_debt_nm"] == 400000 and q["width_nm"] == 200000
    assert q["unchanged_full_rail_current_contract"] == rating
    assert q["explicit_shunt_contract"]["owner_pins"] == ["1", "8"]
    assert not q["explicit_shunt_contract"]["inferred_ownership"]
    assert not q["current_authority"] and not q["replacement_routing_authorized"]
    assert not q["barrel_ampacity_certified"]
    assert leaf._binding(board) == before and binding == original


@pytest.mark.parametrize("fault", ["incomplete_bank", "wrong_pin", "foreign", "wrong_face",
    "owner_face", "support_face", "owner_dnp", "cap_dnp", "not_capacitor", "missing", "duplicate", "extra_field"])
def test_explicit_scope_never_guesses_a_missing_or_conflicting_native_owner(monkeypatch, fault):
    board, cap, owner, pad, tracks, via, binding, _ = fixture(monkeypatch)
    if fault == "incomplete_bank": binding["owner_pad_uuids"].pop()
    elif fault == "wrong_pin": binding["owner_pad_uuids"] = [force._uid(owner.FindPadByNumber("3"))]
    elif fault == "foreign": owner.FindPadByNumber("8").SetNetCode(cap.FindPadByNumber("2").GetNetCode())
    elif fault == "wrong_face":
        layers=pcbnew.LSET(); layers.AddLayer(pcbnew.B_Cu)
        owner.FindPadByNumber("8").SetLayerSet(layers)
    elif fault == "owner_face": owner.SetLayer(pcbnew.B_Cu)
    elif fault == "support_face": cap.SetLayer(pcbnew.B_Cu)
    elif fault == "owner_dnp": owner.SetDNP(True)
    elif fault == "cap_dnp": cap.SetDNP(True)
    elif fault == "not_capacitor": cap.SetFPID(pcbnew.LIB_ID("Resistor_SMD", "R_0805"))
    elif fault == "missing": binding["owner_pad_uuids"] = ["missing-uuid"]
    elif fault == "duplicate": binding["owner_pad_uuids"] *= 2
    else: binding["assumed_current"] = .001
    before = leaf._binding(board)
    with pytest.raises(ValueError): shunt.plan_supply(board, binding, board_hint="opaque")
    assert leaf._binding(board) == before


@pytest.mark.parametrize("fault", ["group", "wide", "fork", "interior_tap"])
def test_explicit_capacitor_binding_cannot_retire_protected_or_shared_copper(monkeypatch, fault):
    board, _, _, pad, tracks, _, binding, _ = fixture(monkeypatch)
    if fault == "group":
        group=pcbnew.PCB_GROUP(board); group.AddItem(tracks[0]); board.Add(group)
    elif fault == "wide":
        for t in tracks: t.SetWidth(800000)
    else:
        t=pcbnew.PCB_TRACK(board); t.SetNetCode(pad.GetNetCode()); t.SetWidth(200000)
        t.SetLayer(pcbnew.F_Cu); t.SetStart(pcbnew.VECTOR2I_MM(22 if fault=="fork" else 21,18))
        t.SetEnd(pcbnew.VECTOR2I_MM(22 if fault=="fork" else 21,20)); board.Add(t)
    before=leaf._binding(board)
    if fault=="fork":
        q=shunt.plan_supply(board,binding,board_hint="opaque")
        assert q["track_uuids"]==[force._uid(tracks[0])]
        assert force._uid(tracks[1]) in q["boundary_uuids"]
    else:
        with pytest.raises(ValueError): shunt.plan_supply(board,binding,board_hint="opaque")
    assert leaf._binding(board)==before


@pytest.mark.parametrize("width", [None, 0, True, 2000001])
def test_missing_or_unbounded_current_replacement_authority_is_not_guessed(monkeypatch,width):
    import cec_decoupler_cell as cell
    board,*_,binding,rating=fixture(monkeypatch)
    monkeypatch.setattr(cell,"_supply_current_widths",lambda *a,**k:
        None if width is None else dict(required_by_layer_nm={pcbnew.F_Cu:width}))
    with pytest.raises(ValueError): shunt.plan_supply(board,binding,board_hint="opaque")


def test_retirement_packet_cannot_accidentally_rebuild_undersized_copper(monkeypatch):
    board,_,_,pad,tracks,_,binding,_=fixture(monkeypatch)
    q=shunt.plan_supply(board,binding,board_hint="opaque"); discard_items(board,tracks)
    before=leaf._binding(board)
    for operation in (leaf.path_clear,leaf.add_path):
        with pytest.raises(ValueError,match="separate_full_rated_reconstruction"):
            operation(board,q,[q["points_nm"][0],q["points_nm"][-1]])
    assert leaf._binding(board)==before


@pytest.mark.parametrize("fault", [None, "width", "scope", "geometry", "binding"])
def test_receiver_rederives_native_scope_instead_of_trusting_worker_packet(monkeypatch,fault):
    board,_,_,pad,tracks,_,binding,_=fixture(monkeypatch)
    q=shunt.plan_supply(board,binding,board_hint="opaque")
    if fault=="width": q["required_replacement_width_nm"]=100000
    elif fault=="scope": q["track_uuids"].append("another-trunk")
    elif fault=="geometry": tracks[0].SetWidth(210000)
    elif fault=="binding": q["explicit_shunt_contract"]["binding"]["owner_pad_uuids"].pop()
    before=leaf._binding(board)
    if fault is None:
        assert shunt.receive_source_plan(board,q,board_hint="opaque")["ok"]
    else:
        with pytest.raises(ValueError): shunt.receive_source_plan(board,q,board_hint="opaque")
    assert leaf._binding(board)==before
