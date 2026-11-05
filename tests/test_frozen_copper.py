"""Native frozen-prefix ECO regressions use synthetic, arbitrary net names."""
import hashlib
from pathlib import Path
from unittest import mock

import pcbnew
import pytest

import cec_cell_extract
import cec_fr
import cec_frozen_copper as frozen
import cec_sync_pcb_from_schematic as sync


def fixture(path):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    nets = {}
    for name in ("/TRUNK", "/SIGNAL", "GND"):
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        nets[name] = net
    for ref, xy, net in (("ANCHOR", (5, 10), "/TRUNK"),
                         ("MOVABLE", (10, 15), "/SIGNAL")):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref)
        fp.SetFPID(pcbnew.LIB_ID("Synthetic", "Pad"))
        fp.SetPosition(pcbnew.VECTOR2I_MM(*xy))
        pad = pcbnew.PAD(fp)
        pad.SetNumber("1")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(0.6, 0.8))
        layers = pcbnew.LSET()
        layers.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(layers)
        pad.SetPosition(fp.GetPosition())
        pad.SetNet(nets[net])
        fp.Add(pad)
        board.Add(fp)
    for name, y, locked in (("/TRUNK", 10, True),
                            ("/TRUNK", 12, False),
                            ("/SIGNAL", 15, True)):
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I_MM(5, y))
        track.SetEnd(pcbnew.VECTOR2I_MM(20, y))
        track.SetWidth(pcbnew.FromMM(1))
        track.SetLayer(pcbnew.F_Cu)
        track.SetNet(nets[name])
        track.SetLocked(locked)
        board.Add(track)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I_MM(15, 10))
    via.SetWidth(pcbnew.FromMM(0.6))
    via.SetDrill(pcbnew.FromMM(0.3))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(nets["/TRUNK"])
    via.SetLocked(True)
    board.Add(via)
    zone = pcbnew.ZONE(board)
    zone.SetLayer(pcbnew.In1_Cu)
    zone.SetNet(nets["GND"])
    zone.Outline().NewOutline()
    for xy in ((1, 1), (29, 1), (29, 19), (1, 19)):
        p = pcbnew.VECTOR2I_MM(*xy)
        zone.Outline().Append(p.x, p.y)
    board.Add(zone)
    pcbnew.SaveBoard(str(path), board)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.kicad_pcb"
    fixture(path)
    return path


def test_layer_specific_collision_and_transaction_rollback(source):
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    ctx = frozen.FrozenCopperContext(source, ["/TRUNK"])
    assert ctx.check({"MOVABLE": (10, 10, 0)})["ok"] is False
    assert ctx.check({"MOVABLE": (10, 10, 0)}, back_refs={"MOVABLE"})["ok"]
    assert not ctx.check({"MOVABLE": (15, 10, 0)}, back_refs={"MOVABLE"})["ok"]
    assert ctx.check({"MOVABLE": (10, 14, 90)})["ok"]
    assert frozen.FrozenCopperContext._pose(ctx.footprints["MOVABLE"]) == ctx.original["MOVABLE"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_through_hole_pad_sees_inner_and_back_copper(source):
    board = pcbnew.LoadBoard(str(source))
    fp = next(fp for fp in board.GetFootprints() if fp.GetReference() == "MOVABLE")
    pad = next(iter(fp.Pads()))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetDrillSize(pcbnew.VECTOR2I_MM(0.3, 0.3))
    pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    for item in board.GetTracks():
        if item.GetNetname() == "/TRUNK" and item.Type() != pcbnew.PCB_VIA_T:
            item.SetLayer(pcbnew.In2_Cu)
    pcbnew.SaveBoard(str(source), board)
    ctx = frozen.FrozenCopperContext(source, ["/TRUNK"])
    assert not ctx.check({"MOVABLE": (10, 10, 0)})["ok"]


def test_frozen_anchor_cannot_move_and_cached_evidence_is_not_mutable(source):
    ctx = frozen.FrozenCopperContext(source, ["/TRUNK"])
    result = ctx.check({"ANCHOR": (6, 10, 0)})
    assert result["violations"][0]["kind"] == "frozen_anchor_moved"
    assert result['violations'][0]['attachments_complete'] is True
    assert {row['copper_net'] for row in result['violations'][0]['attachments']} == {'/TRUNK'}
    result["violations"].clear()
    assert ctx.check({"ANCHOR": (6, 10, 0)})["violations"]
    assert ctx.check({"ANCHOR": (5, 10, 0)})["ok"]


def test_anchor_witness_does_not_stop_after_first_pad_or_hide_power(source):
    board = pcbnew.LoadBoard(str(source))
    fp = next(fp for fp in board.GetFootprints() if fp.GetReference() == 'ANCHOR')
    pad = pcbnew.PAD(fp)
    pad.SetNumber('2')
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(.6,.8))
    layers = pcbnew.LSET()
    layers.AddLayer(pcbnew.F_Cu)
    pad.SetLayerSet(layers)
    pad.SetPosition(pcbnew.VECTOR2I_MM(5,15))
    pad.SetNet(board.FindNet('/SIGNAL'))
    fp.Add(pad)
    pcbnew.SaveBoard(str(source),board,True)
    ctx = frozen.FrozenCopperContext(source, ['/SIGNAL','/TRUNK'])
    row = ctx.check({'ANCHOR':(6,10,0)})['violations'][0]
    assert row['attachments_complete']
    assert {item['copper_net'] for item in row['attachments']} == {'/TRUNK','/SIGNAL'}
    assert {item['pad'] for item in row['attachments']} == {'1','2'}
    assert all(item['copper_uuid'] for item in row['attachments'])


def test_declared_preservation_requires_existing_locked_geometry(source):
    board = pcbnew.LoadBoard(str(source))
    assert frozen.require_present(board, ["/TRUNK"]) == {"/TRUNK": 2}
    with pytest.raises(ValueError, match="absent"):
        frozen.require_present(board, ["GND"])


def test_unattached_same_net_pad_may_gain_a_connection(source):
    board = pcbnew.LoadBoard(str(source))
    fp = next(fp for fp in board.GetFootprints() if fp.GetReference() == "MOVABLE")
    fp.SetPosition(pcbnew.VECTOR2I_MM(10, 17))
    next(iter(fp.Pads())).SetNet(board.FindNet("/TRUNK"))
    pcbnew.SaveBoard(str(source), board)
    ctx = frozen.FrozenCopperContext(source, ["/TRUNK"])
    assert "MOVABLE" not in ctx.anchor_refs
    assert ctx.check({"MOVABLE": (10, 10, 0)})["ok"]


def run_sync(source, *, preserve=True, assignments=None, package="Synthetic:Pad", uuids=()):
    pad_nets = assignments or {("ANCHOR", "1"): "/TRUNK", ("MOVABLE", "1"): "/SIGNAL"}
    # A ground-only annotation supplies the legitimate reference-plane net.
    pad_nets = dict(pad_nets)
    pad_nets[("PWR", "1")] = "GND"
    inventory = {ref: {"footprint": package if ref == "ANCHOR" else "Synthetic:Pad"}
                 for ref in ("ANCHOR", "MOVABLE")}
    with mock.patch.object(sync, "_schematic_pad_nets", return_value=(pad_nets, set(inventory))), \
            mock.patch.object(sync.cec_sch_gates, "inventory", return_value=inventory):
        return sync.synchronize("synthetic.kicad_sch", str(source), rip_all_copper=True,
                                preserve_locked_nets=["/TRUNK"] if preserve else (),
                                preserve_locked_uuids=uuids)


def test_selective_sync_preserves_exact_prefix_and_zone_outline(source):
    contract = cec_fr.copper_geometry_prefix_contract(str(source), ["/TRUNK"])
    report = run_sync(source)
    assert report["tracks_after"] == report["preserved_locked_tracks"] == 2
    assert report["zones_after"] == 1
    assert cec_fr.check_copper_geometry_prefix(str(source), contract)["ok"]
    board = pcbnew.LoadBoard(str(source))
    assert all(item.IsLocked() and item.GetNetname() == "/TRUNK" for item in board.GetTracks())


@pytest.mark.parametrize("mode", ["assignment", "package", "added_interface"])
def test_stale_frozen_topology_fails_without_editing_source(source, mode):
    before = source.read_bytes()
    kwargs = {}
    if mode == "assignment":
        kwargs["assignments"] = {("ANCHOR", "1"): "/SIGNAL", ("MOVABLE", "1"): "/SIGNAL"}
    elif mode == "package":
        kwargs["package"] = "Synthetic:Different"
    else:
        kwargs["assignments"] = {("ANCHOR", "1"): "/TRUNK", ("MOVABLE", "1"): "/SIGNAL",
                                 ("NEW", "1"): "/TRUNK"}
    with pytest.raises(ValueError, match="frozen copper topology changed"):
        run_sync(source, **kwargs)
    assert source.read_bytes() == before


def test_explicit_destructive_replacement_without_prefix_still_strips_copper(source):
    report = run_sync(source, preserve=False)
    assert report["tracks_after"] == report["zones_after"] == 0


def test_failed_frozen_materialization_does_not_overwrite_incumbent(source):
    from types import SimpleNamespace
    import cec_synth_pipeline as synth
    before = source.read_bytes()
    candidate = SimpleNamespace(source_board=str(source), protected_power_prefix={"items": 1})

    def failed_materializer(_candidate, _cfg, out):
        Path(out).write_text("unfinished replacement")
        raise RuntimeError("injected post-write failure")

    with mock.patch.object(synth, "_materialize_rehydrated_board", side_effect=failed_materializer):
        with pytest.raises(RuntimeError, match="injected"):
            synth.materialize(candidate, None, str(source))
    assert source.read_bytes() == before


def test_blueprint_regenerates_only_mutable_nets_including_unique_hierarchy_alias(source):
    template = {"parts": {}, "net_roles": {"power": "TRUNK", "signal": "/SIGNAL"},
                "internal_tracks": [
                    {"net_role": role, "start_rel_mm": [0, y], "end_rel_mm": [1, y],
                     "layer": "F.Cu", "width_mm": .2}
                    for role, y in (("power", 0), ("signal", 2))],
                "vias": [{"net_role": "power", "at_rel_mm": [1, 0],
                          "drill_mm": .3, "dia_mm": .6, "layers": ["F.Cu", "B.Cu"]}]}
    board = pcbnew.LoadBoard(str(source))
    _, copper = cec_cell_extract.stamp(template, board=board, at_mm=(5, 10),
                                      ref_map={}, lay_tracks=True, preserved_nets=["/TRUNK"])
    assert [row["net"] for row in copper["tracks"]] == ["/SIGNAL"]
    assert copper["vias"] == []
    assert copper["excluded_from_regeneration"] == 2
