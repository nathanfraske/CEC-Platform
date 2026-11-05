"""The exact-identity relation is confined to a fresh print-only receiver."""
import ast
from pathlib import Path
import cec_force_sense_evidence as sense


def test_print_only_identity_relation_does_not_replace_material_changing_receivers():
    root=Path(__file__).resolve().parents[1]
    text=(root/'build/root_receive_print_context_20261023.py').read_text()
    tree=ast.parse(text)
    calls=[ast.unparse(n.func)for n in ast.walk(tree)if isinstance(n,ast.Call)]
    assert 'transition.receive_row'in calls and 'material_identity.receive'in calls
    assert "g['typed_scope_identity']is True"in text
    assert "contact.get('same_material')is True"in text
    assert "contact.get('full_kelvin_qualification')is False"in text
    assert 'unchanged_not_evaluated'in text
    generic=(root/'build/root_receive_local_transaction_20261022.py').read_text()
    assert 'sense.replay(path,board_hint=a.board,timeout_s=10.)'in generic
    assert 'sense.compare_contour_preservation'in generic
    # A strictly separate pure-reference branch now re-receives the saved
    # operation and proves COMPLETE raw/native query inputs unchanged. No
    # macro, placement, hole, copper or merely print-only phase enters it.
    helper=next(n for n in ast.parse(generic).body if isinstance(n,ast.FunctionDef)
        and n.name=='reference_query_input_identity')
    helper_text=ast.unparse(helper)
    assert "['reference_fields', 'print_context']"in helper_text
    assert 'receive_phase('in helper_text
    assert 'reference_identity.receive('in helper_text
    assert "proof.get('same_material') is True"in helper_text
    assert "proof.get('mutation_authority') is False"in helper_text
    assert "proof.get('full_kelvin_qualification') is False"in helper_text
    # The generic transaction now has an independently scoped PRINT-only
    # relation too. It must re-receive literal body/library ownership first,
    # retain complete raw AND native input equality and claim no authority.
    print_helper=next(n for n in ast.parse(generic).body if isinstance(n,ast.FunctionDef)
        and n.name=='print_query_input_identity')
    pure=ast.unparse(print_helper)
    assert "validate_phases(phases) != ['print_context']"in pure
    assert 'print_op.receive('in pure and 'material_identity.receive('in pure
    assert pure.index('print_op.receive(')<pure.index('material_identity.receive(')
    for token in ("proof.get('same_material') is True","proof.get('comparison_complete') is True",
                  "proof.get('ink_authority') is False","proof.get('new_route_authority') is False",
                  "proof.get('full_kelvin_qualification') is False"):
        assert token in pure
    material_calls=[n for n in ast.walk(ast.parse(generic))if isinstance(n,ast.Call)
        and ast.unparse(n.func)=='material_identity.receive']
    assert len(material_calls)==1


def test_incomplete_absolute_sense_reports_still_refuse_normal_comparison():
    proof=sense.compare_contact_preservation({'complete':False},{'complete':False})
    assert proof.get('same_evidence')is not True
    assert proof.get('comparison_complete')is not True


def test_suite_print_replay_uses_parent_instance_but_final_intake_uses_selected_pair():
    root=Path(__file__).resolve().parents[1]
    tree=ast.parse((root/'build/parallel-review-suite-receive-nine-20261021-a.py').read_text())
    calls=[n for n in ast.walk(tree)if isinstance(n,ast.Call)]
    # The suite now dispatches three explicit provenance kinds. Check the
    # delegated parent rewind too, not the former inline implementation shape.
    dispatch=ast.parse((root/'scripts/cec_suite_annotation_transition.py').read_text())
    matching=[n for n in ast.walk(dispatch)if isinstance(n,ast.Call)
        and ast.unparse(n.func)=='stage.matched_instance']
    assert sorted([ast.unparse(a)for a in n.args]for n in matching)==[
        ["row.get('assembly_instance')", "Path(declaration['source']['path'])"],
        ["row.get('assembly_instance')", 'endpoints[1]']]
    receivers=[n for n in calls if ast.unparse(n.func)=='annotations.receive_row']
    # Three in-process checks precede a fourth SAME receiver in a fresh
    # native process. Verify its actual request and literal worker body;
    # counting only the outer AST would silently omit that final boundary.
    assert len(receivers)==3
    assert all([ast.unparse(a)for a in n.args]==['path','row']for n in receivers)
    final=next(n for n in calls if ast.unparse(n.func)=='isolated_final_typed')
    assert [ast.unparse(a)for a in final.args[:3]]==['path','key','row']
    helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
        and n.name=='isolated_final_typed')
    worker=next(n.value.value for n in ast.walk(helper)if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name)and t.id=='worker'for t in n.targets))
    worker_tree=ast.parse(worker)
    isolated=[n for n in ast.walk(worker_tree)if isinstance(n,ast.Call)
        and ast.unparse(n.func)=='annotations.receive_row']
    assert len(isolated)==1
    assert [ast.unparse(a)for a in isolated[0].args]==['path','row']
    assert {k.arg:ast.unparse(k.value)for k in isolated[0].keywords}=={
        'board_hint':'key','timeout_s':'10.0'}
    assert any(isinstance(n,ast.Assert)and ast.unparse(n.test)==
        "path == Path(row['path']) and force._hash(path) == row['sha256']"
        for n in ast.walk(worker_tree))
    intake=next(n for n in calls if ast.unparse(n.func)=='pipeline._source_intake')
    selected=next(k.value for k in intake.keywords if k.arg=='assembly_instance')
    assert ast.unparse(selected)=="row.get('assembly_instance')"
    assert any(isinstance(n,ast.Compare)and ast.unparse(n)==
        "stage.stable(context['authority']) == stage.stable(typed['new_library_context'])"
        for n in ast.walk(tree))
