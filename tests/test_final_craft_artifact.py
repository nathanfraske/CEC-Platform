"""Final copper-dependent gates must measure the emitted PCB, not placement."""
import ast
from pathlib import Path
import cec_synth_pipeline as pipeline


def test_final_copper_craft_checks_share_the_routed_artifact():
    tree = ast.parse(Path(pipeline.__file__).read_text())
    oracle = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'route_oracle_grade')
    required = {'_oracle_decoupler_adjacency','_oracle_bodies_in_pours',
                '_oracle_pour_uniformity'}
    calls = [node for node in ast.walk(oracle) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id in required]
    assert {node.func.id for node in calls} == required
    assert all(isinstance(node.args[0], ast.Name) and node.args[0].id == 'routed'
               for node in calls)


def test_local_via_assembly_repair_precedes_certificate_search():
    tree = ast.parse(Path(pipeline.__file__).read_text())
    oracle = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'route_oracle_grade')
    local = [node for node in ast.walk(oracle) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr == 'repair_local_pofv_admitted']
    certificate = [node for node in ast.walk(oracle) if isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Name)
                   and node.func.id == '_route_oracle_certificate_repair']
    assert len(local) == len(certificate) == 1
    assert local[0].lineno < certificate[0].lineno
    assert local[0].args[0].id == 'routed'
