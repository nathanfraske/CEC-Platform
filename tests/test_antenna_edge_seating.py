"""No board identities or coordinates from product layouts in edge-seat tests."""
from unittest import mock
import pytest
import cec_synth_pipeline as synth


@pytest.mark.parametrize("rotation,edge", [(0, "top"), (90, "left"),
                                          (180, "bottom"), (270, "right")])
def test_every_outward_face_has_a_hard_inset_limit(rotation, edge):
    with mock.patch.object(synth, "_courtyard_info", return_value=(0., 0., 2., 2.)):
        poses, rot = synth._seat_mcu_macro(
            {"RADIO_Q": (0., 0., 0.)}, {"RADIO_Q": "synthetic"},
            30., 24., rotations=(rotation,), antenna_ref="RADIO_Q",
            antenna_max_inset_mm=.3, score_points=[(15., 12.)], grid=1.7)
    assert poses is not None
    x, y, _ = poses["RADIO_Q"]
    gap = {"top": y-2., "left": x-2., "bottom": 24.-y-2., "right": 30.-x-2.}[edge]
    assert -.00001 <= gap <= .30001


def test_interior_fit_is_not_a_valid_antenna_fallback():
    # Only the central cavity is free. Old scoring returned a legal-looking
    # interior macro; new edge-band admission must refuse it.
    rim = [(0., 5., 0., 30.), (25., 30., 0., 30.),
           (0., 30., 0., 5.), (0., 30., 25., 30.)]
    with mock.patch.object(synth, "_courtyard_info", return_value=(0., 0., 2., 2.)):
        kw = dict(forbid_boxes=rim, grid=1., antenna_overhang=1.)
        assert synth._seat_mcu_macro({"RADIO_Q": (0., 0., 0.)},
            {"RADIO_Q": "synthetic"}, 30., 30., antenna_ref="RADIO_Q", **kw) == (None, None)
        # An ordinary non-radio macro is still permitted in the same cavity.
        assert synth._seat_mcu_macro({"LOGIC_Q": (0., 0., 0.)},
            {"LOGIC_Q": "synthetic"}, 30., 30., **kw)[0] is not None


def test_narrow_cavity_between_grid_rows_preserves_complete_edge_macro():
    # Legal origin y is 3.3..3.6, missed by lattice 1,2.5,4,5.5,...
    # Both the edge owner AND its local satellite must fit the same cavity.
    offsets = {"MODULE_X": (0., 0., 0.), "LOCAL_Y": (0., 2.5, 0.)}
    components = dict.fromkeys(offsets, "synthetic")
    obstacles = [(0., 10., 0., 2.), (0., 10., 4.9, 10.)]
    with mock.patch.object(synth, "_courtyard_info", return_value=(0., 0., 1., 1.)):
        poses, _ = synth._seat_mcu_macro(offsets, components, 10., 10.,
            rotations=(90.,), antenna_ref="MODULE_X", forbid_boxes=obstacles,
            grid=1.5, margin=.3)
    assert poses is not None and set(poses) == set(offsets)
    assert 3.3 <= poses["MODULE_X"][1] <= 3.6
    assert poses["LOCAL_Y"][1] == pytest.approx(poses["MODULE_X"][1])
    assert poses["LOCAL_Y"][0] - poses["MODULE_X"][0] == pytest.approx(2.5)
    for x, y, _ in poses.values():
        assert synth._box_clear((x-1., x+1., y-1., y+1.), obstacles, .3)


def test_existing_legal_lattice_result_does_not_change():
    with mock.patch.object(synth, "_courtyard_info", return_value=(0., 0., 1., 1.)), \
         mock.patch("cec_cell_packing.contact_translation_sites") as fallback:
        poses, _ = synth._seat_mcu_macro({"MODULE_X": (0., 0., 0.)},
            {"MODULE_X": "synthetic"}, 10., 10., antenna_ref="MODULE_X",
            rotations=(90.,), grid=1.5)
    fallback.assert_not_called()
    assert poses is not None


def test_missing_antenna_owner_cannot_silently_disable_contract():
    with pytest.raises(ValueError, match="missing"):
        synth._seat_mcu_macro({}, {}, 30., 30., antenna_ref="RADIO_Q")


def test_column_constraints_cannot_be_bypassed_by_edge_preference():
    with mock.patch.object(synth, "_courtyard_info", return_value=(0., 0., 2., 2.)):
        assert synth._seat_mcu_macro({"RADIO_Q": (0., 0., 0.)},
            {"RADIO_Q": "synthetic"}, 30., 30., antenna_ref="RADIO_Q",
            rotations=(90.,), x_range=(10., 25.), antenna_edge="left") == (None, None)


def test_native_edge_check_catches_a_later_move_and_respects_shifted_outline():
    import pcbnew
    import cec_antenna_edge as edge
    board = pcbnew.BOARD()
    for start, end in (((10., 20.), (40., 20.)), ((40., 20.), (40., 50.)),
                       ((40., 50.), (10., 50.)), ((10., 50.), (10., 20.))):
        item = pcbnew.PCB_SHAPE()
        item.SetShape(pcbnew.SHAPE_T_SEGMENT); item.SetLayer(pcbnew.Edge_Cuts)
        item.SetStart(pcbnew.VECTOR2I_MM(*start)); item.SetEnd(pcbnew.VECTOR2I_MM(*end))
        board.Add(item)
    fp = pcbnew.FOOTPRINT(board); fp.SetReference("RADIO_Q")
    fp.SetFPID(pcbnew.LIB_ID("fixture", "declared-radio"))
    for start, end in (((-2., -2.), (2., -2.)), ((2., -2.), (2., 2.)),
                       ((2., 2.), (-2., 2.)), ((-2., 2.), (-2., -2.))):
        item = pcbnew.PCB_SHAPE(fp)
        item.SetShape(pcbnew.SHAPE_T_SEGMENT); item.SetLayer(pcbnew.F_CrtYd)
        item.SetStart(pcbnew.VECTOR2I_MM(*start)); item.SetEnd(pcbnew.VECTOR2I_MM(*end))
        fp.Add(item)
    board.Add(fp)
    contract = {"RADIO_Q": {"direction": (-1., 0.)}}
    fp.SetPosition(pcbnew.VECTOR2I_MM(12., 35.))
    assert edge.board_evidence(board, contracts=contract)["ok"]
    fp.SetPosition(pcbnew.VECTOR2I_MM(25., 35.))
    result = edge.board_evidence(board, contracts=contract)
    assert not result["ok"]
    assert result["violations"][0]["ref"] == "RADIO_Q"
    assert result["violations"][0]["signed_gap_mm"] > 12.
    evidence = {"ok": False, "antenna_edge": result, "decoupler": {"violations": [
        ("CAP_Q", "local-cell-access", 1.)]}}
    assert not synth.placement_craft_admission(evidence, allow_route_access_repair=True)["ok"]
    certificate = synth.placement_craft_blocker_certificate(evidence)
    assert "critical_macro_edge_reservation" in certificate["required_stages"]
    assert certificate["module_edge_violations"] == result["violations"]


def test_clearance_measurement_does_not_accept_interior_or_excess_overhang():
    from cec_antenna_edge import face_evidence
    outline = (10., 20., 40., 50.)
    assert face_evidence((10., 25., 14., 30.), outline, (-1., 0.))["ok"]
    assert not face_evidence((20., 25., 24., 30.), outline, (-1., 0.))["ok"]
    assert not face_evidence((0., 25., 4., 30.), outline, (-1., 0.))["ok"]


def test_wired_only_package_measurement_does_not_invent_an_rf_blocker():
    import pcbnew
    import cec_antenna_edge as edge
    from types import SimpleNamespace
    # A native rectangle uses the same path as board truth, with an inferred
    # supported package name but no explicit mechanical edge contract.
    board = mock.Mock()
    box = SimpleNamespace(GetLeft=lambda: 0, GetTop=lambda: 0,
        GetRight=lambda: 30000000, GetBottom=lambda: 30000000)
    body = SimpleNamespace(GetLeft=lambda: 10000000, GetTop=lambda: 10000000,
        GetRight=lambda: 14000000, GetBottom=lambda: 14000000)
    board.GetBoardEdgesBoundingBox.return_value = box
    fp = mock.Mock()
    fp.GetReference.return_value = "RADIO_Q"
    fp.GetFPID.return_value.GetLibItemName.return_value = "ESP32-S3-MINI-1"
    fp.IsFlipped.return_value = False
    fp.GetOrientationDegrees.return_value = 0.
    fp.GetCourtyard.return_value.OutlineCount.return_value = 1
    fp.GetCourtyard.return_value.BBox.return_value = body
    board.GetFootprints.return_value = [fp]
    assert edge.board_evidence(board)["ok"]  # observation, not an RF failure
    result = edge.board_evidence(board, require_edge=True)
    assert not result["ok"] and result["violations"][0]["required"]


def test_rf_opt_out_removes_implicit_edge_only_seating_not_physical_body():
    params = {'respect_antenna_keepout': False, 'antenna_edge': 'left'}
    assert synth._mcu_edge_owner(params, 'RENAMED_MODULE') is None
    assert synth._mcu_edge_owner({'respect_antenna_keepout': True}, 'RENAMED_MODULE') == 'RENAMED_MODULE'
    rim = [(0., 5., 0., 30.), (25., 30., 0., 30.),
           (0., 30., 0., 5.), (0., 30., 25., 30.)]
    with mock.patch.object(synth, '_courtyard_info', return_value=(0., 0., 2., 2.)):
        positions, _ = synth._seat_mcu_macro({'RENAMED_MODULE': (0., 0., 0.)},
            {'RENAMED_MODULE': 'synthetic'}, 30., 30., forbid_boxes=rim,
            antenna_ref=synth._mcu_edge_owner(params, 'RENAMED_MODULE'))
    assert positions is not None
    x, y, _ = positions['RENAMED_MODULE']
    assert synth._box_clear((x-2., x+2., y-2., y+2.), rim, 0.)


def test_rf_opt_out_preserves_explicit_mechanical_edge_contract():
    assert synth._mcu_edge_owner({'respect_antenna_keepout': False,
        'module_edge_attachment_required': True}, 'RENAMED_MODULE') == 'RENAMED_MODULE'
    assert synth._mcu_edge_owner({'respect_antenna_keepout': False,
        'antenna_edge_contracts': {'RENAMED_MODULE': {}}}, 'RENAMED_MODULE') == 'RENAMED_MODULE'


def test_rf_opt_out_does_not_drop_usb_or_port_score_but_removes_antenna_reward():
    from types import SimpleNamespace
    nl = SimpleNamespace(comps={}, nets={})
    positions = {'MODULE': (15.,15.,0.), 'PORT_A': (28.,8.,0.),
                 'PORT_B': (28.,20.,0.), 'J_USB': (28.,25.,0.)}
    footprints = {'MODULE': 'RF_Module:ESP32-S3-MINI-1',
                  'PORT_A': 'connector:RJ45', 'PORT_B': 'connector:RJ45', 'J_USB': 'connector:USB'}
    with mock.patch.object(synth, '_courtyard_info', return_value=(0.,0.,2.,2.)):
        model = synth.build_hub_model(nl, positions, footprints, antenna_required=False)
    score = synth.hub_score(model, positions, 30., 30.)
    assert score['active'] and 'antenna' not in score
    assert 'port_even' in score and 'usb_prox' in score


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
def test_native_body_only_footprint_cannot_be_trimmed_a_second_time(angle):
    import cec_pcb
    name = 'cec-RF_Module:ESP32-S2-MINI-1_NoAntKeepout'
    assert cec_pcb.courtyard_bbox(name, rot=angle, drop_keepout=True) == \
        cec_pcb.courtyard_bbox(name, rot=angle)


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('name', ['fixture:PADLESS_BODY', 'fixture:NoAntKeepout_BODY'])
def test_padless_physical_body_is_not_an_rf_clearance_to_delete(angle, name):
    import cec_pcb
    with mock.patch.object(cec_pcb, '_crtyd_local',
            return_value=([(-2., -10.), (2., -10.), (2., 3.), (-2., 3.)],
                          [(0., -8., 3.)], -2., 2.)), \
         mock.patch.object(cec_pcb, 'local_pad_boxes', return_value=[]):
        ordinary = cec_pcb.courtyard_bbox(name, rot=angle)
        disabled_rf = cec_pcb.courtyard_bbox(name, rot=angle, drop_keepout=True)
    assert disabled_rf == ordinary
    assert sorted((ordinary[1]-ordinary[0], ordinary[3]-ordinary[2])) == [6., 14.]
