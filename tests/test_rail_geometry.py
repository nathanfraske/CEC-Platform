"""Rail contracts must survive ref renaming, duplicate legs and either face."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cec_rail_geometry as geometry
import cec_force_rails as rails


def facts():
    def pad(ref, number, net, x, y, tht=False):
        return dict(ref=ref, number=number, net=net, x=x, y=y,
                    width=2.0, height=1.2, tht=tht, face="F.Cu")
    return [pad("INPUT", "1", "raw", 8, 0, True),
            pad("INPUT", "1", "raw", 12, 0, True),
            pad("SERIES", "1", "raw", 10, 10),
            pad("SERIES", "2", "load", 10, 13),
            pad("OUTPUT", "1", "load", 8, 25, True),
            pad("OUTPUT", "1", "load", 12, 25, True)]


ROLES = dict(INPUT="source", SERIES="series", OUTPUT="sink")


def test_explicit_roles_allow_arbitrary_reference_and_net_names():
    rows = facts()
    topology = geometry.discover_topology(rows, roles=ROLES)
    result = geometry.compile_rails(topology, rows, {"OUTPUT": (23, 27)},
                                   lambda nets: 7.25)
    assert len(result) == 1
    rail = result[0]
    assert rail["amps"] == 7.25
    assert rail["tb_escape_y"] == 22.25
    assert len(rail["j3"]) == len(rail["tb"]) == 2
    assert rail["source_refs"] == ["INPUT"]
    assert rail["sink_refs"] == ["OUTPUT"]


def test_ambiguous_direction_is_not_chosen_by_reference_order():
    rows = facts()
    rows.extend([dict(rows[0], net="load"), dict(rows[-1], net="raw")])
    with pytest.raises(geometry.RailGeometryError, match="ambiguous"):
        geometry.discover_topology(rows, roles=ROLES)


def test_invalid_explicit_role_cannot_silently_hide_a_rail():
    with pytest.raises(geometry.RailGeometryError, match="invalid terminal roles"):
        geometry.discover_topology(facts(), roles={**ROLES, "INPUT": "soruce"})


@pytest.mark.parametrize("field,value", [("x", float("nan")), ("width", 0),
                                         ("height", -1)])
def test_invalid_physical_geometry_is_rejected(field, value):
    rows = facts()
    topology = geometry.discover_topology(rows, roles=ROLES)
    rows[0][field] = value
    with pytest.raises(geometry.RailGeometryError, match="invalid physical land"):
        geometry.compile_rails(topology, rows, {}, lambda nets: 7.25)


def test_enabled_rail_stage_must_not_pass_an_empty_topology(monkeypatch):
    import cec_synth_pipeline as synth
    monkeypatch.setattr(synth, "View", lambda cfg: SimpleNamespace(nl=object()))
    monkeypatch.setattr(synth, "_shared_bus_topology", lambda nl: [])
    with pytest.raises(ValueError, match="no shared-bus topology"):
        synth._declared_force_rail_topology(object())


def test_missing_declared_terminal_never_becomes_an_origin_fallback():
    rows = facts()
    topology = geometry.discover_topology(rows, roles=ROLES)
    topology[0]["sink_refs"].append("MISSING")
    with pytest.raises(geometry.RailGeometryError, match="MISSING"):
        geometry.compile_rails(topology, rows, {}, lambda nets: 7.25)


@pytest.mark.parametrize("amps", [0, -1, float("nan"), float("inf")])
def test_invalid_current_is_refused(amps):
    rows = facts()
    topology = geometry.discover_topology(rows, roles=ROLES)
    with pytest.raises(ValueError):
        geometry.compile_rails(topology, rows, {}, lambda nets: amps)
    with pytest.raises(ValueError):
        rails.rail_current_contract(["raw"], current_by_net={"raw": amps})


def test_explicit_current_authority_overrides_voltage_heuristics():
    contract = rails.rail_current_contract(
        ["/SENSE5V_HI", "+5V_MAIN"], current_by_net={"+5V_MAIN": 7.25})
    assert contract["amps"] == 7.25
    assert contract["source"] == "declared_current_contract"
    with pytest.raises(ValueError, match="no declared current"):
        rails.rail_current_contract(["/SENSE5V_HI"], current_by_net={})


def test_declared_source_excludes_unrelated_same_net_connector():
    rows = facts()
    topology = geometry.discover_topology(rows, roles=ROLES)
    rows.append(dict(rows[0], ref="UNRELATED", x=100))
    result = geometry.compile_rails(topology, rows, {}, lambda nets: 7.25)
    assert len(result[0]["j3"]) == 2


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
@pytest.mark.parametrize("flipped", [False, True])
def test_placement_reservation_matches_materialized_geometry(tmp_path, rot, flipped):
    pcbnew = pytest.importorskip("pcbnew")
    import cec_pcb
    from test_place_flip import _LAYERS
    comps = {"INPUT": "cec-Connector_Screw:XFCN_T34069_THT_M3_40A",
             "SERIES": "cec-Resistor_SMD:R_2512_6332Metric",
             "OUTPUT": "cec-Connector_Screw:XFCN_T34069_THT_M3_40A"}
    poses = {"INPUT": (20, 10, rot), "SERIES": (30, 30, rot),
             "OUTPUT": (40, 60, rot)}
    nl = SimpleNamespace(nets={"raw": [("INPUT", "1"), ("SERIES", "1")],
                               "load": [("SERIES", "2"), ("OUTPUT", "1")]})
    topo = [{"shunt": "SERIES", "hi": "raw", "lo": "load",
             "source_refs": ["INPUT"], "sink_refs": ["OUTPUT"]}]
    code_of = {"raw": 1, "load": 2}
    padnet = {(ref, num): (code_of[net], net)
              for net, pins in nl.nets.items() for ref, num in pins}
    footprints = [cec_pcb.place(lib, ref, *poses[ref], padnet, code_of, flip=flipped)
                  for ref, lib in comps.items()]
    path = tmp_path / "materialized.kicad_pcb"
    path.write_text('(kicad_pcb (version 20241229) (generator "test") '
                    '(general (thickness 1.6))' + _LAYERS +
                    '(net 0 "") (net 1 "raw") (net 2 "load")' +
                    "".join(footprints) + ")")
    board = pcbnew.LoadBoard(str(path))
    proposed, cy1 = geometry.placement_facts(
        nl, comps, poses.get, topo, back_refs=set(comps) if flipped else ())
    actual, cy2, _ = geometry.board_facts(board)
    def normalize(rows):
        return sorted((p["ref"], p["number"], p["net"],
                       round(p["x"], 5), round(p["y"], 5),
                       p["width"], p["height"], p["tht"], p["face"]) for p in rows)
    assert normalize(proposed) == normalize(actual)
    assert len([p for p in proposed if p["ref"] == "INPUT"]) == 4
    reserved = geometry.compile_rails(topo, proposed, cy1, lambda nets: 7.25)
    laid = geometry.compile_rails(topo, actual, cy2, lambda nets: 7.25)
    assert reserved[0]["tb_escape_y"] == pytest.approx(laid[0]["tb_escape_y"], abs=0.001)
    for key in ("hi", "lo"):
        assert reserved[0][key] == pytest.approx(laid[0][key], abs=0.00001)
    assert reserved[0]["face"] == laid[0]["face"]


def test_actual_copper_is_invariant_under_source_ref_renaming():
    pytest.importorskip("pcbnew")
    from test_force_rails import _mkboard
    def run(name):
        board = _mkboard(src_net="feed", snk_net="return")
        for fp in board.GetFootprints():
            if fp.GetReference() == "J3":
                fp.SetReference(name)
        result = rails.lay_force_rails(
            board, verbose=False, current_by_net={"feed": 7.25})
        tracks = sorted((t.GetNetname(), t.GetLayer(), t.GetWidth(),
                         t.GetStart().x, t.GetStart().y,
                         t.GetEnd().x, t.GetEnd().y) for t in board.GetTracks())
        return result, tracks
    original, renamed = run("J3"), run("J87")
    assert original[1], "must compare real generated copper, not two empty plans"
    assert original == renamed
