"""Release route-oracle must not accept advisory-only retained-copper defects."""
import copy
import ast
from pathlib import Path
import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_synth_pipeline as oracle
import test_route_reverse_diagonal_jog as fixtures


@pytest.mark.parametrize('face',[0,4,6,8,10,2])
@pytest.mark.parametrize('split',[False,True])
def test_whole_saved_ordinary_locked_jog_is_blocking_in_standalone_route_oracle(tmp_path,face,split):
    points=[(0,0),(300000,300000),(100000,500000),(2100000,2500000)]
    if split:points=[(0,0),(300000,300000),(200000,400000),(100000,500000),(2100000,2500000)]
    board,tracks=fixtures.ReverseDiagonalJogTests().board(points,layer=face,net_name='/renamed_unprotected')
    board.SetCopperLayerCount(6)
    path=tmp_path/'literal.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    raw=path.read_bytes()
    sanity=oracle._oracle_route_sanity(str(path))
    assert sanity['ok'] is True  # Detour heuristic is a different predicate.
    assert sanity['craft_ok'] is False
    terms={name:True for name in oracle._ROUTE_ORACLE_GATE_TERMS}
    terms.update(oracle._oracle_route_craft_gate_terms(sanity))
    assert terms['route_geometry_ok'] is False
    assert oracle._route_oracle_accepts(terms) is False
    assert path.read_bytes()==raw


@pytest.mark.parametrize('key',['route_geometry_ok','power_contour_review_ok'])
def test_neither_whole_copper_release_predicate_can_be_missing_or_false(key):
    terms={name:True for name in oracle._ROUTE_ORACLE_GATE_TERMS}
    assert key in terms
    assert oracle._route_oracle_accepts(terms)
    terms[key]=False
    assert not oracle._route_oracle_accepts(terms)
    terms.pop(key)
    with pytest.raises(ValueError,match='gate term mismatch'):oracle._route_oracle_accepts(terms)


@pytest.mark.parametrize('value',[None,0,1,'true',[],{},False])
@pytest.mark.parametrize('predicate',['craft_ok','power_contour_review_ok'])
def test_missing_checker_error_or_truthy_nonbool_never_becomes_craft_release_pass(value,predicate):
    result={'craft_ok':True,'power_contour_review_ok':True}
    result[predicate]=value
    before=copy.deepcopy(result)
    actual=oracle._oracle_route_craft_gate_terms(result)
    key='route_geometry_ok' if predicate=='craft_ok' else predicate
    assert actual[key] is False
    assert result==before
    result.pop(predicate)
    assert oracle._oracle_route_craft_gate_terms(result)[key] is False


def test_clean_canonical_saved_route_can_pass_but_not_from_heuristic_ok_alone(tmp_path):
    board,_=fixtures.ReverseDiagonalJogTests().board([(0,0),(300000,0),(1300000,1000000)])
    path=tmp_path/'clean.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    sanity=oracle._oracle_route_sanity(str(path))
    actual=oracle._oracle_route_craft_gate_terms(sanity)
    assert actual=={'route_geometry_ok':True,'power_contour_review_ok':True}
    assert oracle._route_oracle_accepts({name:actual.get(name,True)
        for name in oracle._ROUTE_ORACLE_GATE_TERMS})
    assert oracle._oracle_route_craft_gate_terms({'ok':True})=={
        'route_geometry_ok':False,'power_contour_review_ok':False}


def test_actual_prethermal_conjunction_consumes_whole_board_terms_without_policy_bypass():
    # Wiring teeth complement native geometry tests: a helper used only by a
    # standalone test must not masquerade as a production release predicate.
    text=Path(oracle.__file__).read_text();tree=ast.parse(text)
    dictionaries=[node.value for node in ast.walk(tree)
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name)
            and t.id=='prethermal_gate_terms' for t in node.targets)]
    assert len(dictionaries)==1
    gate=dictionaries[0]
    expansions=[v for k,v in zip(gate.keys,gate.values) if k is None]
    assert any(isinstance(v,ast.Call) and isinstance(v.func,ast.Name)
        and v.func.id=='_oracle_route_craft_gate_terms'
        and len(v.args)==1 and isinstance(v.args[0],ast.Name) and v.args[0].id=='rsan'
        for v in expansions)


def test_final_signoff_cache_binds_transitive_native_geometry_implementation():
    import cec_full_pipeline as pipeline
    tree=ast.parse(Path(pipeline.__file__).read_text())
    calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call)
        and isinstance(node.func,ast.Attribute) and node.func.attr=='run'
        and node.args and isinstance(node.args[0],ast.Constant)
        and node.args[0].value=='independent_signoff']
    assert len(calls)==1
    dependencies=[node for node in ast.walk(calls[0].args[1])
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
        and node.func.id=='_code_closure_signature']
    assert any(any(isinstance(arg,ast.Constant) and arg.value=='cec_route_quality.py'
        for arg in node.args) for node in dependencies)
