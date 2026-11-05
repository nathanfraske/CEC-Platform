"""Isolated existing macro engine using complete Source Ground retention.

Original modules are not monkeypatched. Private function namespaces retain
all original cut ownership, fresh packet rederivation, native routing and
independent saved-board gates. Only the zero-Ground-cut lemma is extended.
"""
from pathlib import Path
import types
import cec_force_current as force
import cec_fully_retained_ground_forest as forest
import cec_cell_escape_replan as original_escape
import cec_cell_macro_requests as original_compiler
import cec_complete_macro_cell as original_macro

_helpers={}
_self_path=Path(__file__).resolve();_self_digest=force._hash(_self_path)
def _clone(original,name,replacements):
    path=Path(original.__file__).resolve();digest=force._hash(path);text=path.read_text()
    for old,new in replacements:
        if text.count(old)!=1:raise ValueError('literal_retained_forest_macro_hook_changed:'+old)
        text=text.replace(old,new)
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(text,str(path),'exec'),module.__dict__)
    if force._hash(path)!=digest:raise ValueError('frozen_retained_forest_macro_source_changed')
    _helpers[str(path)]=digest
    return module

escape=_clone(original_escape,'cec_private_retained_forest_escape',[
    ('            import cec_cell_macro_requests as macro',
        '            from cec_retained_forest_macro import compiler as macro')])
compiler=_clone(original_compiler,'cec_private_retained_forest_compiler',[
    ('import cec_cell_escape_replan as escape','from cec_retained_forest_macro import escape'),
    ('    import cec_stationary_ground_forest as forest','    import cec_fully_retained_ground_forest as forest'),
    ('proposal=forest.refine(parent,private,proposal,','proposal=forest.propose_and_restore(parent,private,proposal,')])
macro=_clone(original_macro,'cec_private_retained_forest_macro',[
    ('import cec_cell_escape_replan as escape','from cec_retained_forest_macro import escape'),
    ('import cec_cell_macro_requests as compiler','from cec_retained_forest_macro import compiler')])
_compile=compiler.compile


def compile(*args,**kwargs):
    if force._hash(_self_path)!=_self_digest:raise ValueError('retained_forest_macro_helpers_changed')
    identity=forest.identity();tools={**_helpers,**identity['helper_sha256'],
        str(_self_path):_self_digest}
    board,packet=_compile(*args,**kwargs)
    packet['source_stationary_ground_retention_extension']=dict(policy=identity['policy'],helper_sha256=tools,
        original_global_modules_not_monkeypatched=True,all_original_macro_and_saved_receiving_gates_retained=True)
    if any(force._hash(Path(p))!=h for p,h in tools.items()):raise ValueError('retained_forest_macro_helpers_changed')
    return board,packet


compiler.compile=compile
