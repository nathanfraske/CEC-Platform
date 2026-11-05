"""A portal-context refusal is not an attempted geometry producer."""
import ast
from pathlib import Path
import cec_joint_route_negotiation as subject


def test_portal_context_must_resolve_before_target_is_marked_attempted():
    tree=ast.parse(Path(subject.__file__).read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='propose')
    blocks=[n for n in ast.walk(fn)if isinstance(n,ast.If)
        and ast.unparse(n.test)=='missing_portal is not None']
    assert len(blocks)==1
    branch=blocks[0]
    assert "evidence['producer_attempted'] = False"in ast.unparse(branch)
    assert any(isinstance(n,ast.Break)for n in branch.body)
    attempts=[n for n in ast.walk(fn)if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Subscript)and ast.unparse(t)=='attempted[key]'for t in n.targets)]
    calls=[n for n in ast.walk(fn)if isinstance(n,ast.Call)and ast.unparse(n.func)=='escape.menus']
    assert len(attempts)==len(calls)==1
    assert branch.end_lineno<attempts[0].lineno<calls[0].lineno
    # Declining a context still consumes the bounded diagnostic action;
    # this ordering must not grant extra unaccounted producer work.
    assert any(isinstance(n,ast.Call)and ast.unparse(n.func)=='actions.append'for n in ast.walk(branch))
