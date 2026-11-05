"""Native shape failures must never acquire routing-clearance authority."""
import pytest

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_fr as fr


class UnavailableShape:
    def Collide(self, *_args):
        raise RuntimeError("synthetic unavailable collision query")


class UnavailableBox:
    def Intersects(self, *_args):
        raise RuntimeError("synthetic unavailable broadphase query")


class ClearShape:
    def Collide(self, *_args):
        return False


@pytest.mark.parametrize("indexed", [False, True])
@pytest.mark.parametrize("material", ["zone", "track", "pad", "npth_hole"])
@pytest.mark.parametrize("failure", ["collision", "broadphase"])
@pytest.mark.parametrize("rotated", [False, True])
def test_unavailable_foreign_geometry_is_refused_and_logged(
        indexed, material, failure, rotated):
    shape = UnavailableShape() if failure == "collision" else ClearShape()
    box = None if failure == "collision" else UnavailableBox()
    identity = dict(kind=material, uuid="synthetic-foreign-identity")
    rows = [(shape, box, identity, pcbnew.FromMM(.3))]
    if indexed:
        rows = fr._bucket_foreign_shapes(rows)
    zones, copper = (rows, []) if material == "zone" else ([], rows)
    start = pcbnew.VECTOR2I_MM(4, 4)
    end = pcbnew.VECTOR2I_MM(4, 9) if rotated else pcbnew.VECTOR2I_MM(9, 4)
    assert fr._snapshot_foreign_clear(start, end, 200000, 200000, zones, copper) is False
    assert fr._snapshot_foreign_blockers(start, end, 200000, 200000, zones, copper) == [
        dict(identity, contact="geometry_unknown", geometry_status="unknown",
             error_type="RuntimeError")]


@pytest.mark.parametrize("indexed", [False, True])
def test_successful_empty_collision_remains_clear(indexed):
    rows = [(ClearShape(), None, dict(kind="track"), 200000)]
    if indexed:
        rows = fr._bucket_foreign_shapes(rows)
    start, end = pcbnew.VECTOR2I_MM(0, 0), pcbnew.VECTOR2I_MM(1, 1)
    assert fr._snapshot_foreign_clear(start, end, 200000, 200000, [], rows)
    assert fr._snapshot_foreign_blockers(start, end, 200000, 200000, [], rows) == []


def test_refusal_certificate_does_not_describe_unknown_geometry_as_clear(monkeypatch):
    board = pcbnew.CreateEmptyBoard()
    net = pcbnew.NETINFO_ITEM(board, "synthetic-renamed-demand")
    board.Add(net)
    rows = [(UnavailableShape(), None, dict(kind="pad", uuid="foreign"), 200000)]
    monkeypatch.setattr(fr, "_identified_foreign_shape_indexes", lambda *_args: ([], rows))
    monkeypatch.setattr(fr, "_edge_leg_clear", lambda *_args: True)
    result = fr._lastmile_refusal_certificate(
        board, pcbnew.VECTOR2I_MM(3, 3), pcbnew.VECTOR2I_MM(4, 3),
        200000, 200000, net.GetNetCode(), [pcbnew.F_Cu])
    layer = result["layers"][0]
    assert layer["direct_geometry_unknown"]
    for endpoint in layer["endpoint_escape"]:
        assert endpoint["clear_rays"] == []
        assert endpoint["foreign_blocked_ray_count"] == 0
        assert endpoint["geometry_unknown_hit_count"] == 8
        assert all(ray["status"] == "geometry_unknown" for ray in endpoint["ray_details"])
    assert result["conclusion"] == "bounded_search_exhausted_not_global_impossibility"
