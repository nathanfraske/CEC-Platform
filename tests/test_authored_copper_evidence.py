"""A clean local cell cannot hide omitted required power copper."""
import ast
import inspect
import json
from types import SimpleNamespace

import pytest
import cec_synth_pipeline as synth


@pytest.mark.parametrize("rows,expected", [({},False),
    ({"PATH-A":{"vias":3},"PATH-B":"REFUSED: foreign pad"},False),
    ({"RENAMED":{"vias":2}},True)])
def test_every_required_constructor_result_is_admitted(rows,expected):
    result=synth._authored_copper_build_evidence(rows)
    assert result["ok"] is expected and result["total"]==len(rows)
    assert set(result["results"])==set(rows)


@pytest.mark.parametrize("mode", ["missing","empty","refused","complete"])
def test_blueprint_success_cannot_mask_required_force_failure(tmp_path,mode):
    board=tmp_path/"board.kicad_pcb"; board.write_text("test board")
    report={"schema":1,"board":board.name,"total":2,"laid":2,"refused":[],"locked_segments":10,
            "ground_portals":{"reservations":{"portals":[]},"replan":{"changed":2}}}
    if mode!="missing":
        rows=({} if mode=="empty" else {"COPPER_A":{}} if mode=="complete"
              else {"COPPER_A":{},"COPPER_B":"REFUSED: footprint pad"})
        report["force_lanes"]=synth._authored_copper_build_evidence(rows)
    with open(synth._blueprint_cell_report_path(board),"w") as handle: json.dump(report,handle)
    cfg=SimpleNamespace(params={"blueprint_cells":[{},{}],"force_lanes":True})
    result=synth._blueprint_cell_craft_evidence(board,cfg)
    assert result["ground_portals"]==report["ground_portals"]
    assert result["ok"] is (mode=="complete")
    if mode!="complete": assert "required force-lane" in result["error"]
    cfg.params["force_lanes"]=False
    assert synth._blueprint_cell_craft_evidence(board,cfg)["ok"]


def test_both_native_materialization_paths_persist_constructor_evidence():
    for fn in (synth.materialize,synth._lay_declared_blueprint_cells):
        tree=ast.parse(inspect.getsource(fn))
        assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
                   and n.func.id=="_authored_copper_build_evidence" for n in ast.walk(tree))
        assert any(isinstance(n,ast.Dict) and any(isinstance(k,ast.Constant)
                   and k.value=="force_lanes" for k in n.keys) for n in ast.walk(tree))


def test_force_lanes_without_blueprints_cannot_silently_be_not_applicable(tmp_path):
    board=tmp_path/"board.kicad_pcb"; board.write_text("board")
    cfg=SimpleNamespace(params={"force_lanes":True})
    result=synth._blueprint_cell_craft_evidence(board,cfg)
    assert result["applicable"] and not result["ok"]
