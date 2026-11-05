"""Synthetic required-mount regressions; no production board coordinates."""
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import pcbnew
import cec_synth_pipeline as synth
from cec_mounting_contract import board_evidence

LIB = Path(__file__).resolve().parents[1] / "lib/vendor/MountingHole.pretty"
NAME = "MountingHole_2.2mm_M2_NPTH_6mm_Hardware"
PARAMS = {"mount_holes_required": True, "mount_holes": "4_corner",
          "mount_hardware_diameter_mm": 6., "mount_drill_mm": 2.2,
          "mount_hardware_clearance_mm": .25, "mount_hole_type": "npth",
          "mount_edge_inset_mm": 3.75, "mount_fp": "cec-MountingHole:" + NAME,
          "fiducials": "none"}


def fixture_board():
    board = pcbnew.BOARD()
    for a, b in [((11, 17), (51, 17)), ((51, 17), (51, 47)),
                 ((51, 47), (11, 47)), ((11, 47), (11, 17))]:
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        board.Add(edge)
    pos, _ = synth.place_mechanical(40., 30., PARAMS)
    for ref, (x, y, _) in pos.items():
        fp = pcbnew.FootprintLoad(str(LIB), NAME)
        assert fp is not None
        fp.SetReference(ref); fp.SetPosition(pcbnew.VECTOR2I_MM(x+11, y+17))
        board.Add(fp)
    return board, {r: p[:2] for r, p in pos.items()}


def evidence(board, expected):
    return board_evidence(board, expected, drill_mm=2.2, hardware_diameter_mm=6.)


def test_grounded_mount_reconcile_preserves_positions_and_checks_net_and_solid(tmp_path):
    from cec_mounting_contract import reconcile
    board, pos = fixture_board()
    net = pcbnew.NETINFO_ITEM(board, "RETURN"); board.Add(net)
    name = "cec-MountingHole:MountingHole_2.2mm_M2_Pad_Via_6mm_Hardware"
    result = reconcile(board, {r:name for r in pos}, net_name="RETURN")
    assert len(result["changed"]) == 4
    def check():
        return board_evidence(board, pos, drill_mm=2.2, hardware_diameter_mm=6.,
                              hole_type="pth", net_name="RETURN")
    assert check()["ok"], check()
    assert reconcile(board, {r:name for r in pos}, net_name="RETURN")["changed"] == []
    for fp in board.GetFootprints():
        fp.Reference().SetVisible(True)
    assert len(reconcile(board, {r:name for r in pos}, net_name="RETURN",
                         reference_visible=False)["changed"]) == 4
    assert all(not fp.Reference().IsVisible() for fp in board.GetFootprints())
    assert reconcile(board, {r:name for r in pos}, net_name="RETURN",
                     reference_visible=False)["changed"] == []
    pad = next(iter(next(iter(board.GetFootprints())).Pads()))
    pad.SetNetCode(0)
    assert not check()["ok"]
    pad.SetNet(net); pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    assert not check()["ok"]


def test_native_mount_drill_and_both_face_hardware_on_shifted_outline():
    board, pos = fixture_board()
    result = evidence(board, pos)
    assert result["ok"], result["details"]
    assert result["required_count"] == 4
    assert all(row["matching_holes"] == 1 for row in result["details"])
    for fp in board.GetFootprints():
        assert list(fp.Zones()), "hardware requires native copper keepouts"
        zone = list(fp.Zones())[0]
        assert zone.GetIsRuleArea() and zone.GetDoNotAllowTracks()
        assert zone.GetDoNotAllowVias() and zone.GetDoNotAllowPads()
        assert zone.GetDoNotAllowZoneFills()
        assert zone.GetLayerSet().Contains(pcbnew.F_Cu)
        assert zone.GetLayerSet().Contains(pcbnew.B_Cu)


@pytest.mark.parametrize('defect',[None,'clearance','contact','hardware','net','thermal'])
def test_slim_contact_keeps_full_hardware_protection(defect):
    from cec_mounting_contract import reconcile
    board,pos=fixture_board()
    net=pcbnew.NETINFO_ITEM(board,'RETURN'); board.Add(net)
    name='cec-MountingHole:MountingHole_2.2mm_M2_Pad_Via_Slim_6mm_Hardware'
    reconcile(board,{r:name for r in pos},net_name='RETURN')
    fp=next(iter(board.GetFootprints()))
    pad=next(p for p in fp.Pads() if p.GetDrillSize().x > 1e6)
    if defect=='clearance': pad.SetLocalClearance(pcbnew.FromMM(.2))
    if defect=='contact': pad.SetSize(pcbnew.VECTOR2I_MM(6,6))
    if defect=='hardware': fp.SetPosition(pcbnew.VECTOR2I_MM(12,18))
    if defect=='net': pad.SetNetCode(0)
    if defect=='thermal': pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    result=board_evidence(board,pos,drill_mm=2.2,hardware_diameter_mm=6.,
        hole_type='pth',net_name='RETURN',contact_diameter_mm=4.4)
    assert result['ok'] is (defect is None), result
    if defect is None:
        assert all(row['contact_diameter_mm']==4.4 for row in result['details'])
        assert all(row['foreign_copper_clearance_mm']==1.05 for row in result['details'])
        assert all(len(list(f.Pads()))==9 for f in board.GetFootprints())
        # Legacy policies still require contact covering the whole envelope.
        assert not board_evidence(board,pos,drill_mm=2.2,hardware_diameter_mm=6.,
            hole_type='pth',net_name='RETURN')['ok']


@pytest.mark.parametrize("defect", ["missing", "displaced", "drill", "plated", "keepout"])
def test_required_geometry_never_silently_drops_or_changes(defect):
    board, pos = fixture_board()
    fp = next(iter(board.GetFootprints()))
    if defect == "missing":
        board.Remove(fp)
    elif defect == "displaced":
        fp.SetPosition(pcbnew.VECTOR2I_MM(31., 32.))
    elif defect == "drill":
        next(iter(fp.Pads())).SetDrillSize(pcbnew.VECTOR2I_MM(1., 1.))
    elif defect == "plated":
        next(iter(fp.Pads())).SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    else:
        next(iter(fp.Zones())).SetDoNotAllowZoneFills(False)
    assert not evidence(board, pos)["ok"]


def test_independent_constraint_gate_rechecks_mandatory_holes():
    import cec_constraints
    board, _ = fixture_board()
    with mock.patch("cec_board_policy.params", return_value=PARAMS):
        assert cec_constraints._chk_mounts(board, "fixture", {})[0]
        board.Remove(next(iter(board.GetFootprints())))
        result = cec_constraints._chk_mounts(board, "fixture", {})
        assert not result[0] and "missing_or_duplicate_mount" in result[1]


@pytest.mark.parametrize("layer", [pcbnew.F_CrtYd, pcbnew.B_CrtYd])
def test_hardware_conflict_caught_on_either_face(layer):
    board, pos = fixture_board()
    mount = next(iter(board.GetFootprints()))
    other = pcbnew.FOOTPRINT(board); other.SetReference("DEVICE_X")
    for a, b in [((-1,-1),(1,-1)), ((1,-1),(1,1)), ((1,1),(-1,1)), ((-1,1),(-1,-1))]:
        edge = pcbnew.PCB_SHAPE(other); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(layer); edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        other.Add(edge)
    other.SetPosition(mount.GetPosition()); board.Add(other)
    result = evidence(board, pos)
    assert not result["ok"]
    assert any("hardware_conflict:DEVICE_X" in row["reason"] for row in result["violations"])


def test_hardware_over_board_cutout_cannot_pass_bounding_box_check():
    board, pos = fixture_board()
    for a,b in [((15,21),(16,21)), ((16,21),(16,22)),
                ((16,22),(15,22)), ((15,22),(15,21))]:
        edge = pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts); edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        board.Add(edge)
    result = evidence(board, pos)
    assert not result["ok"]
    assert any(row["reason"] == "hardware_envelope_crosses_edge_or_cutout" for row in result["violations"])


def test_both_legacy_drop_paths_preserve_explicitly_required_mounts(tmp_path):
    board, _ = fixture_board()
    path = tmp_path / "fixture.kicad_pcb"
    pcbnew.SaveBoard(str(path), board)
    before = path.read_bytes()
    dropped = synth._drop_conflicting_mounts(str(path), {
        "violations": ["Footprint H1|Footprint DEVICE_X"]},
        protected=synth._required_mount_refs(PARAMS))
    assert dropped == [] and path.read_bytes() == before
    poses = {"H1": (5.,5.,0.), "DEVICE_X": (5.,5.,0.)}
    with mock.patch("cec_pcb.courtyard_bbox", return_value=(4.,6.,4.,6.)):
        assert not synth._drop_optional_corner_mount_conflicts(
            poses, dict.fromkeys(poses, "fixture"), protected={"H1"})
    assert "H1" in poses


def test_missing_mount_blocks_route_deferral_and_ranks_worse():
    base = {"ok": False, "decoupler": {"violations": [("CAP_X", "local-cell-access", 1)]}}
    bad = {**base, "required_mounts": {"ok": False, "violations": [{"ref":"FASTENER_X", "reason":"missing"}]}}
    assert synth.placement_craft_admission(base, allow_route_access_repair=True)["ok"]
    assert not synth.placement_craft_admission(bad, allow_route_access_repair=True)["ok"]
    assert synth.placement_craft_key(bad) > synth.placement_craft_key(base)
    cert = synth.placement_craft_blocker_certificate(bad)
    assert "mechanical_anchor_reservation" in cert["required_stages"]


def test_opt_in_only_and_invalid_policy_refuses():
    assert not synth._required_mount_refs({})
    assert synth._oracle_required_mounts("missing", SimpleNamespace(params={"mount_holes":"none"}))["ok"]
    for extra in ({"mount_holes":"none"}, {"mount_edge_inset_mm":float("nan")},
                  {"mount_edge_inset_mm":2.}, {"mount_pos_override":{"CUSTOM":(3,3)}}):
        with pytest.raises(ValueError):
            synth.place_mechanical(40.,30., {**PARAMS, **extra})


def test_resolved_mount_land_and_surviving_identity_reach_native_emitter(tmp_path):
    import cec_pcb
    poses = {"H2": (14., 8., 0.)}
    rows = synth._mount_materialization_rows(poses, PARAMS)
    assert rows == [(14., 8., PARAMS["mount_fp"], "H2")]
    assert synth._mount_materialization_rows(poses, {
        **PARAMS, "mount_fp_override": {"H2":"fixture:custom"}})[0][2] == "fixture:custom"
    netlist = tmp_path / "empty.net"
    netlist.write_text('(export (version "E") (components) (nets (net (code "1") (name "GND"))))')
    path = tmp_path / "native.kicad_pcb"
    cec_pcb.build_board(str(path), str(netlist), {}, rows, None, 30.,20.,
                        zones=False, force_argv=False)
    board = pcbnew.LoadBoard(str(path))
    result = board_evidence(board, {"H2":(14.,8.)},
        drill_mm=2.2, hardware_diameter_mm=6.)
    assert result["ok"], result["violations"]
    assert [fp.GetReference() for fp in board.GetFootprints()] == ["H2"]


@pytest.mark.parametrize("rot", [0., 90., 23.])
@pytest.mark.parametrize("flip", [False, True])
def test_emitted_keepout_translation_rotation_and_flip_match_native(tmp_path, rot, flip):
    import cec_pcb
    from test_place_flip import TestPlaceFlip
    native_board = pcbnew.BOARD()
    native = pcbnew.FootprintLoad(str(LIB), NAME)
    native_board.Add(native)
    native.SetPosition(pcbnew.VECTOR2I_MM(14., 8.))
    native.SetOrientationDegrees(rot)
    if flip:
        native.Flip(native.GetPosition(), False)
    emitted = cec_pcb.place(PARAMS["mount_fp"], "FASTENER_X", 14.,8.,rot,{}, {},flip=flip)
    path = tmp_path / "transformed.kicad_pcb"
    path.write_text(TestPlaceFlip()._board_doc(emitted))
    board = pcbnew.LoadBoard(str(path))
    actual = next(iter(board.GetFootprints()))
    def geometry(fp):
        rows = []
        for zone in fp.Zones():
            outline = zone.Outline().Outline(0)
            rows.append((tuple(sorted(int(l) for l in zone.GetLayerSet().CuStack())),
                tuple(sorted((round(outline.CPoint(i).x/1e6,3), round(outline.CPoint(i).y/1e6,3))
                             for i in range(outline.PointCount())))))
        return rows
    assert geometry(actual) == geometry(native)
