"""Located physical field refusals must teach the generic power path search."""
import numpy as np
import pytest

import cec_slab_pour as slab


def scene(layers=("F.Cu", "B.Cu"), offset=0):
    shape = (5, 18 + offset)
    passable = {layer: np.ones(shape, dtype=bool) for layer in layers}
    anchors = {layer: np.zeros(shape, dtype=bool) for layer in layers}
    labels = np.zeros(shape, dtype=int)
    labels[2, 2 + offset] = 1
    labels[2, 15 + offset] = 2
    anchors[layers[0]][2, 2 + offset] = True
    anchors[layers[1]][2, 15 + offset] = True
    return layers, passable, anchors, labels, 2


@pytest.mark.parametrize("layers", [("F.Cu", "B.Cu"), ("In2.Cu", "In4.Cu")])
@pytest.mark.parametrize("offset", [0, 7])
def test_refused_field_is_avoided_without_mutating_copper_masks(layers, offset):
    args = scene(layers, offset)
    forbidden = np.zeros(args[3].shape, dtype=bool)
    original = {layer: value.copy() for layer, value in args[1].items()}
    failed = []

    def probe(bridges):
        if not failed:
            failed.append(bridges[0][:2])
            raise slab.BridgeFieldRefused("blocked field", bridges[0], required=2)
        assert all(bridge[:2] not in failed for bridge in bridges)

    paths, bridges, ok, failure, chains, report = slab.route_overunder_with_bridge_feedback(
        *args, bias_fn=lambda *_: 1., bridge_probe=probe,
        bridge_forbidden=forbidden, max_replans=2)
    assert ok and failure is None and chains and paths and bridges
    assert report["searches"] == report["field_probes"] == 2
    assert report["stop_reason"] == "field_set_admitted"
    assert not forbidden.any()
    for layer in layers:
        np.testing.assert_array_equal(args[1][layer], original[layer])


def test_unrealizable_fields_stop_at_budget_without_partial_route():
    args = scene()

    class Grid:
        x0 = y0 = 0.
        nx, ny, cell = 18, 5, 0.5

    def probe(bridges):
        slab.realize_overunder_rects(
            [], bridges, {layer: 1.2 for layer in args[0]}, Grid(),
            via_allow=lambda *_: False, bridge_via_count=2,
            strict_bridges=True, free_masks=args[1])

    paths, bridges, ok, failure, chains, report = slab.route_overunder_with_bridge_feedback(
        *args, bias_fn=lambda *_: 1., bridge_probe=probe, max_replans=2)
    assert not ok and not paths and not bridges and not chains
    assert report["searches"] == 3
    assert report["stop_reason"] == "bridge_replan_budget_exhausted"
    assert len(report["refusals"]) == 3
    assert failure["required_vias"] == 2
    assert failure["available_vias"] == 0


def test_non_bridge_errors_are_not_hidden_as_search_feedback():
    def probe(_):
        raise RuntimeError("unexpected copper problem")

    with pytest.raises(RuntimeError, match="unexpected copper problem"):
        slab.route_overunder_with_bridge_feedback(
            *scene(), bias_fn=lambda *_: 1., bridge_probe=probe)


def test_post_clipping_realization_refusal_replans_the_same_bounded_search():
    rejected = []
    def probe(paths, bridges, chains):
        assert paths and chains
        if not rejected:
            rejected.append(bridges[0][:2])
            raise slab.BridgeFieldRefused('clipped landing', bridges[0], required=3, available=2)
        assert all(b[:2] not in rejected for b in bridges)
    result = slab.route_overunder_with_bridge_feedback(
        *scene(), bias_fn=lambda *_: 1., bridge_probe=lambda fields: None,
        realization_probe=probe, max_replans=1)
    assert result[2] and result[-1]['searches'] == 2
    assert result[-1]['refusals'][0]['available_vias'] == 2


@pytest.mark.parametrize('defect', ['none', 'clipped', 'hole', 'wrong_layer'])
@pytest.mark.parametrize('offset', [0, 23])
def test_complete_lands_not_just_via_centers_must_survive_clipping(defect, offset):
    square = [[offset, 0], [offset+4, 0], [offset+4, 4], [offset, 4]]
    rows = [dict(net='arbitrary', layer=layer, polygon=square)
            for layer in ('F.Cu', 'In3.Cu')]
    vias = [dict(field_index=0, x_mm=offset+1., y_mm=2.),
            dict(field_index=0, x_mm=offset+2.5, y_mm=2.)]
    fields = [(1, 1, 'F.Cu', 'In3.Cu', 1., 0.)]
    if defect == 'clipped':
        rows[1]['polygon'] = [[offset,0],[offset+2.7,0],[offset+2.7,4],[offset,4]]
    elif defect == 'hole':
        rows[1]['holes'] = [[[offset+2.2,1.8],[offset+2.8,1.8],
                              [offset+2.8,2.2],[offset+2.2,2.2]]]
    elif defect == 'wrong_layer':
        rows[1]['layer'] = 'B.Cu'
    if defect == 'none':
        slab.require_bridge_landings(rows, vias, fields)
    else:
        with pytest.raises(slab.BridgeFieldRefused) as error:
            slab.require_bridge_landings(rows, vias, fields)
        assert error.value.evidence['required_vias'] == 2
        assert error.value.evidence['available_vias'] < 2


def test_same_layer_route_needs_no_field_probe():
    args = scene()
    args[2][args[0][0]][2, 15] = True
    args[2][args[0][1]][:] = False
    result = slab.route_overunder_with_bridge_feedback(
        *args, bias_fn=lambda *_: 1., prefer_non_f_anchors=False,
        bridge_probe=lambda _: pytest.fail("unexpected bridge"))
    assert result[2] and not result[1]
    assert result[-1]["field_probes"] == 0


@pytest.mark.parametrize("limit", [-1, 1.5])
def test_invalid_budget_refused(limit):
    with pytest.raises(ValueError, match="nonnegative integer"):
        slab.route_overunder_with_bridge_feedback(
            *scene(), bias_fn=lambda *_: 1., bridge_probe=lambda _: None,
            max_replans=limit)


def test_production_exhaustion_cannot_publish_partial_frozen_authority(monkeypatch):
    args = scene()

    class Net:
        def GetNetname(self):
            return "arbitrary-rail"

    class NetInfo:
        def NetsByNetcode(self):
            return {7: Net()}

    class Board:
        def GetNetInfo(self):
            return NetInfo()

        def GetTracks(self):
            return []

    class Grid:
        x0 = y0 = 0.
        nx, ny, cell = 18, 5, 0.5

    prep = {"layers": args[0], "passable": args[1], "anchors": args[2],
            "clab": args[3], "nclusters": args[4], "bias_fn": lambda *_: 1.,
            "bridge_forbidden": np.zeros(args[3].shape, dtype=bool),
            "rcells": {layer: 1 for layer in args[0]},
            "reqw": {layer: 1.2 for layer in args[0]}, "foreign": {}}

    def fail_fields(chains, fields, *a, **kw):
        raise slab.BridgeFieldRefused("field cannot fit", fields[0], required=2)

    monkeypatch.setattr(slab, "Grid", lambda *a, **kw: Grid())
    monkeypatch.setattr(slab, "_board_thermal_config", lambda *a: None)
    monkeypatch.setattr(slab, "shunt_neighborhoods", lambda *a: [])
    monkeypatch.setattr(slab, "_prep_overunder_net", lambda *a, **kw: (prep, None))
    monkeypatch.setattr(slab, "_overunder_bridge_geometry", lambda *a: {})
    monkeypatch.setattr(slab, "terminal_cluster_members", lambda *a, **kw: [])
    monkeypatch.setattr(slab, "realize_overunder_rects", fail_fields)
    with pytest.raises(slab.BridgeSearchRefused, match="over-under bridge search.*arbitrary-rail") as error:
        slab.synthesize_overunder_pours(
            Board(), [{"net": "arbitrary-rail", "layers": args[0]}],
            bridge_replan_limit=1)
    assert error.value.evidence["net"] == "arbitrary-rail"
    assert error.value.evidence["kind"] == "power_bridge_feasibility"
    assert len(error.value.evidence["bridge_feasibility"]["refusals"]) == 2
