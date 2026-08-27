"""Determinism and physical teeth for incremental future congestion."""

import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_boarddb as boarddb  # noqa: E402
import cec_future_congestion as future  # noqa: E402


def _database(pads, *, layers=("F.Cu", "B.Cu")):
    refs = sorted({row["ref"] for row in pads})
    poses = []
    for ref in refs:
        row = next(pad for pad in pads if pad["ref"] == ref)
        poses.append({"ref": ref, "x": row["x"], "y": row["y"],
                      "rotation": 0})
    normalized = []
    for row in pads:
        item = dict(row)
        item.setdefault("bbox", (row["x"] - 0.2, row["y"] - 0.2,
                                 row["x"] + 0.2, row["y"] + 0.2))
        item.setdefault("layers", layers)
        normalized.append(item)
    return boarddb.BoardDB.from_records(
        routing_layers=layers, edge_bbox=(0, 0, 10, 10),
        footprints=poses, pads=normalized)


def _context(database, nets, *, critical=(), allowed=None,
             reservations=(), reservation_report=None):
    conns = [(net, (0, 0, 0), (0, 0, 1)) for net in nets]
    masks = allowed or [tuple(True for _ in database.routing_layers)
                        for _net in nets]
    stackup = {
        "net_kinds": tuple("signal" for _net in nets),
        "allowed_layers_by_conn": tuple(masks),
    }
    return future.prepare(
        database, conns, stackup, critical_nets=critical,
        reservations=reservations, reservation_report=reservation_report,
        grid_mm=1.0)


def _pad(ref, pad, net, x, y, layers=None):
    row = {"ref": ref, "pad": pad, "net": net, "x": x, "y": y}
    if layers is not None:
        row["layers"] = tuple(layers)
    return row


def _comparable(report):
    report = dict(report)
    report.pop("incremental", None)
    return report


def test_through_hole_terminals_do_not_invent_layer_jumps():
    database = _database([
        _pad("J1", "1", "/A", 1, 1),
        _pad("J2", "1", "/A", 8, 8),
    ])
    report = _context(database, ["/A"]).evaluate()
    assert report["expected_via_count"] == 0
    assert report["via_demand_units"] == 0


def test_opposite_face_smd_terminals_require_one_expected_via():
    database = _database([
        _pad("U1", "1", "/A", 1, 1, ("F.Cu",)),
        _pad("U2", "1", "/A", 8, 8, ("B.Cu",)),
    ])
    report = _context(database, ["/A"]).evaluate()
    assert report["expected_via_count"] == 1
    assert report["via_demand_units"] >= future.DEMAND_SCALE


def test_critical_corridor_ownership_detects_residual_crossing():
    pads = [
        _pad("U1", "1", "/CRIT", 1, 5, ("F.Cu",)),
        _pad("U2", "1", "/CRIT", 9, 5, ("F.Cu",)),
        _pad("R1", "1", "/SIG", 5, 1, ("F.Cu",)),
        _pad("R2", "1", "/SIG", 5, 9, ("F.Cu",)),
    ]
    context = _context(
        _database(pads), ["/CRIT", "/SIG"], critical=("/CRIT",),
        allowed=[(True, False), (True, False)])
    report = context.evaluate()
    assert report["critical_reserved_cells"] >= 9
    assert report["critical_corridor_conflicts"] >= 1
    assert len(report["layers"]) == 2


def test_incremental_delta_is_exact_and_names_only_dependency_closure():
    pads = [
        _pad("U1", "1", "/A", 1, 2, ("F.Cu",)),
        _pad("U2", "1", "/A", 8, 2, ("F.Cu",)),
        _pad("R1", "1", "/B", 1, 8, ("F.Cu",)),
        _pad("R2", "1", "/B", 8, 8, ("F.Cu",)),
    ]
    context = _context(
        _database(pads), ["/A", "/B"], allowed=[
            (True, False), (True, False)])
    move = {"U1": (2.0, 3.0, 0.0)}
    incremental = context.evaluate(move)
    recomputed = context.recompute(move)
    assert _comparable(incremental) == _comparable(recomputed)
    assert 0 < incremental["incremental"]["affected_net_count"] \
        < incremental["incremental"]["total_net_count"]
    assert incremental["incremental"]["changed_cell_count"] > 0


def test_pressure_names_noncritical_part_inside_protected_corridor():
    pads = [
        _pad("U1", "1", "/CRIT", 1, 5, ("F.Cu",)),
        _pad("U2", "1", "/CRIT", 9, 5, ("F.Cu",)),
        _pad("R_BLOCK", "1", "/SIG", 5, 5, ("F.Cu",)),
        _pad("R_END", "1", "/SIG", 5, 8, ("F.Cu",)),
    ]
    report = _context(
        _database(pads), ["/CRIT", "/SIG"], critical=("/CRIT",),
        allowed=[(True, False), (True, False)]).evaluate()
    pressure = {row["ref"]: row["pressure_units"]
                for row in report["pressure_refs"]}
    assert pressure["R_BLOCK"] > 0


def test_policy_shape_mismatch_fails_closed():
    database = _database([
        _pad("U1", "1", "/A", 1, 1),
        _pad("U2", "1", "/A", 2, 2),
    ])
    try:
        future.prepare(database, [("/A", (0, 0, 0), (0, 0, 1))],
                       {"net_kinds": (), "allowed_layers_by_conn": ()})
    except ValueError as exc:
        assert "equal length" in str(exc)
    else:
        raise AssertionError("malformed policy was accepted")


def test_exact_rail_reservation_consumes_capacity_and_names_crossing():
    pads = [
        _pad("R1", "1", "/SIG", 1, 5, ("F.Cu",)),
        _pad("R2", "1", "/SIG", 9, 5, ("F.Cu",)),
    ]
    report = _context(
        _database(pads), ["/SIG"], allowed=[(True, False)],
        reservations=[{"net": "/RAIL", "layer": "F.Cu",
                       "x0": 4.0, "y0": 0.0,
                       "x1": 6.0, "y1": 10.0}],
        reservation_report={"/RAIL": {"reserved": True}}).evaluate()
    assert report["reservation_rect_count"] == 1
    assert report["reservation_cell_count"] > 0
    assert report["reservation_crossings"] > 0
    assert report["overflow_units"] > 0


def test_owned_rail_is_not_forecast_as_a_duplicate_trace():
    pads = [
        _pad("J1", "1", "/RAIL", 1, 5, ("F.Cu",)),
        _pad("J2", "1", "/RAIL", 9, 5, ("F.Cu",)),
    ]
    report = _context(
        _database(pads), ["/RAIL"], allowed=[(True, False)],
        reservations=[{"net": "/RAIL", "layer": "F.Cu",
                       "x0": 1.0, "y0": 4.0,
                       "x1": 10.0, "y1": 6.0}],
        reservation_report={"/RAIL": {"reserved": True}}).evaluate()
    assert report["wire_demand_units"] == 0
    assert report["reservation_crossings"] == 0
    assert report["reservation_owned_nets"] == ["/RAIL"]
    assert report["overflow_units"] == 0
