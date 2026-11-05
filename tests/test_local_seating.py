import copy
import math

import pytest

from cec_local_seating import closure_poses


def cell():
    return {
        "cap_ref": "BYPASS", "owner_ref": "SENSOR",
        "cap_position_mm": [5.2, 41.35], "cap_orientation_deg": 180,
        "cap_supply_position_mm": [5.68, 41.35],
        "cap_ground_position_mm": [4.72, 41.35],
        "owner_supply_position_mm": [5.335, 43.325],
        "owner_ground_positions_mm": [{"pin": "return", "position": [4.065, 43.325]}],
        "pin_proximity_mode": "dual_via_in_pad_complete_loop",
        "pin_proximity_excess_limit_mm": .25,
        "return_gate_mode": "absolute_ground_distance", "return_limit_mm": 2.5,
        "tangent_target": {"best_loop": {"position_mm": [4.855, 41.45],
                                         "loop_proxy_mm": 3.775454, "supply_mm": 1.875}},
    }


def test_small_closure_precedes_wholesale_tangent_move_without_relaxing_limit():
    row = cell()
    before = copy.deepcopy(row)
    poses, report = closure_poses(row)
    assert row == before
    assert poses[0]["position"] == (5.2, 41.4, 180.0)
    assert poses[0]["predicted_proximity_excess_mm"] <= .23
    assert report["checked"] == 2


def test_geometry_rejection_consumes_bounded_checks_not_return_slots():
    poses, report = closure_poses(cell(), feasible=lambda p: p[0] > 5.22)
    assert poses and all(p["position"][0] > 5.22 for p in poses)
    assert report["checked"] > 2
    poses, report = closure_poses(cell(), feasible=lambda p: False, max_checks=3)
    assert poses == [] and report["checked"] == 3


@pytest.mark.parametrize("turn", [0, 90, 180, 270])
def test_translated_rotated_renamed_geometry_obeys_same_contract(turn):
    row = cell()
    def transform(p):
        c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        return [round(p[0] * c + p[1] * s + 17, 6),
                round(-p[0] * s + p[1] * c - 3, 6)]
    for key in ("cap_position_mm", "cap_supply_position_mm",
                "cap_ground_position_mm", "owner_supply_position_mm"):
        row[key] = transform(row[key])
    row["cap_orientation_deg"] += turn
    row["owner_ground_positions_mm"][0]["position"] = transform(
        row["owner_ground_positions_mm"][0]["position"])
    row["tangent_target"]["best_loop"]["position_mm"] = transform(
        row["tangent_target"]["best_loop"]["position_mm"])
    row["cap_ref"], row["owner_ref"] = "OTHER", "PACKAGE"
    poses, _ = closure_poses(row)
    assert poses[0]["position"][:2] == tuple(transform([5.2, 41.4]))
    assert poses[0]["predicted_proximity_excess_mm"] <= .23


def test_missing_or_unqualified_return_contract_cannot_generate_relaxation():
    row = cell()
    row["return_gate_mode"] = "not_qualified"
    assert closure_poses(row)[0] == []
    row = cell()
    del row["cap_ground_position_mm"]
    assert closure_poses(row)[0] == []


@pytest.mark.parametrize("policy", [dict(step_mm=0), dict(radius_mm=100),
                                      dict(max_checks=True), dict(target_margin_mm=-1)])
def test_unbounded_or_invalid_policy_is_rejected(policy):
    with pytest.raises(ValueError):
        closure_poses(cell(), **policy)


def test_native_screen_rejects_foreign_copper_and_restores_borrowed_footprint(monkeypatch):
    import pcbnew
    import cec_pcb
    import cec_local_seating
    import cec_synth_pipeline as synth
    from types import SimpleNamespace

    board = pcbnew.BOARD()
    nets = []
    for name in ("SUPPLY", "RETURN", "PRECISION"):
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        nets.append(net)
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("BYPASS")
    board.Add(fp)
    for index, offset in enumerate((-.5, .5)):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(str(index + 1))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I(400000, 400000))
        layers = pcbnew.LSET()
        layers.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(layers)
        pad.SetPosition(pcbnew.VECTOR2I(int((10 + offset)*1e6), 10000000))
        pad.SetNet(nets[index])
        fp.Add(pad)
    # Keep absolute pad positions while declaring the footprint origin.
    fp.SetPosition(pcbnew.VECTOR2I(10000000, 10000000))
    for index, pad in enumerate(fp.Pads()):
        pad.SetPosition(pcbnew.VECTOR2I(int((9.5 + index)*1e6), 10000000))
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I(12500000, 9000000))
    track.SetEnd(pcbnew.VECTOR2I(12500000, 11000000))
    track.SetWidth(200000)
    track.SetLayer(pcbnew.F_Cu)
    track.SetNet(nets[2])
    board.Add(track)
    original = [(p.GetPosition().x, p.GetPosition().y) for p in fp.Pads()]
    monkeypatch.setattr(pcbnew, "LoadBoard", lambda path: board)
    monkeypatch.setattr(cec_pcb, "courtyard_bbox",
                        lambda comp, x, y, rotation, **kw: (x-.1, x+.1, y-.1, y+.1))
    def proposals(row, *, feasible):
        assert feasible((10, 10, 0))
        assert not feasible((12, 10, 0))
        assert feasible((10, 10, 0))
        return [{"position": (10, 10, 0)}], {"checked": 3}
    monkeypatch.setattr(cec_local_seating, "closure_poses", proposals)
    candidate = SimpleNamespace(P={"BYPASS": (10, 10, 0), "SENSOR": (20, 10, 0)}, back_refs=set())
    row = dict(cell(), actionable=True)
    moves, report = synth._placement_incremental_supply_moves(
        candidate, {"decoupler": {"details": [row]}}, "unused", {"BYPASS": {}, "SENSOR": {}})
    assert len(moves) == 1 and moves[0]["budget_priority"] == 0
    assert report["cells"][0]["checked"] == 3
    assert [(p.GetPosition().x, p.GetPosition().y) for p in fp.Pads()] == original
    assert fp.GetOrientationDegrees() == 0


@pytest.mark.parametrize("complete_loop", [False, True])
def test_collective_search_uses_exact_admission_mode_not_both_leg_and_loop(monkeypatch, complete_loop):
    import cec_synth_pipeline as synth
    from types import SimpleNamespace
    rows = []
    candidate = SimpleNamespace(P={"OWNER": (0, 0, 0), "SMALL": (1, 0, 0),
                                   "LARGE": (1, 2, 0)}, back_refs=())
    for ref in ("SMALL", "LARGE"):
        rows.append({
            "cap_ref": ref, "owner_ref": "OWNER", "actionable": True,
            "cap_position_mm": [1, 0], "cap_orientation_deg": 0,
            "cap_supply_position_mm": [.5, 0], "cap_ground_position_mm": [1.5, 0],
            "owner_supply_position_mm": [0, 0],
            "owner_ground_positions_mm": [{"position": [3, 0]}],
            "pin_proximity_mode": ("dual_via_in_pad_complete_loop" if complete_loop
                                    else "isolated_tangent_supply"),
            "supply_excess_limit_mm": .25, "pin_proximity_excess_limit_mm": .25,
            "return_gate_mode": "absolute_ground_distance", "return_limit_mm": 2.5,
            "tangent_target": {"best_loop": {"position_mm": [1.5, 0],
                "orientation_deg": 0, "supply_mm": 1, "ground_mm": 1, "loop_proxy_mm": 2}},
        })
    captured = []
    def select(candidate, owner, pose, options, comps, **kwargs):
        captured.extend(options["SMALL"])
        return []
    monkeypatch.setattr(synth, "_select_local_cell_placements", select)
    synth._decoupler_owner_move_specs(candidate, rows, comps={}, immovable={"OWNER"},
                                     allow_owner_translation=False, owner_rotation_deltas=(0,))
    # Supply=2 exceeds the isolated 1+.25 budget, but its return=0 gives a
    # complete loop of 2. It is valid only under the certified loop objective.
    expanded = [rank for rank, pose in captured if rank[0] == 0
                and math.dist(pose[:2], (2.5, 0)) < 1e-6 and pose[2] == 0]
    assert bool(expanded) is complete_loop
