"""Private complete macro retaining all existing gates and fixed Source Ground roots."""
import types
from pathlib import Path
import cec_force_current as force
import cec_fully_retained_ground_forest as forest
import cec_stationary_ground_boundary_roots as roots
import cec_cell_escape_replan as original_escape
import cec_cell_macro_requests as original_compiler
import cec_complete_macro_cell as original_macro

_SELF=Path(__file__).resolve();_HASH=force._hash(_SELF);helpers={}
def clone(original,name,changes):
    path=Path(original.__file__).resolve();digest=force._hash(path);text=path.read_text()
    for old,new in changes:
        if text.count(old)!=1:raise ValueError('frozen_fixed_ground_macro_hook_changed:'+old)
        text=text.replace(old,new)
    module=types.ModuleType(name);module.__file__=str(path);exec(compile(text,str(path),'exec'),module.__dict__)
    helpers[str(path)]=digest;return module
escape=clone(original_escape,'cec_private_fixed_ground_root_escape',[
    ('            import cec_cell_macro_requests as macro','            from cec_fixed_ground_root_macro import compiler as macro'),
    ('    import cec_cell_ground_cut_boundaries as ground_boundaries','    import cec_stationary_ground_boundary_roots as ground_boundaries')])
compiler=clone(original_compiler,'cec_private_fixed_ground_root_compiler',[
    ('import cec_cell_escape_replan as escape','from cec_fixed_ground_root_macro import escape'),
    ('import cec_cell_ground_cut_boundaries as ground','import cec_stationary_ground_boundary_roots as ground'),
    ('    import cec_stationary_ground_forest as forest','    import cec_fully_retained_ground_forest as forest'),
    ('proposal=forest.refine(parent,private,proposal,','proposal=forest.propose_and_restore(parent,private,proposal,')])
macro=clone(original_macro,'cec_private_fixed_ground_root_macro',[
    ('import cec_cell_escape_replan as escape','from cec_fixed_ground_root_macro import escape'),
    ('import cec_cell_macro_requests as compiler','from cec_fixed_ground_root_macro import compiler')])
_compile=compiler.compile
def compile(*args,**kwargs):
    if force._hash(_SELF)!=_HASH:raise ValueError('fixed_ground_root_macro_helpers_changed')
    tools={**helpers,**forest.identity()['helper_sha256'],**roots.identity(),str(_SELF):_HASH}
    board,packet=_compile(*args,**kwargs)
    packet['source_stationary_ground_retention_extension']=dict(policy=forest.POLICY,helper_sha256=tools,
        original_global_modules_not_monkeypatched=True,all_original_macro_and_saved_receiving_gates_retained=True)
    packet['stationary_ground_boundary_root_extension']=dict(helper_sha256=tools,
        source_cuts_current_and_all_partition_return_gates_unchanged=True)
    if any(force._hash(Path(path))!=digest for path,digest in tools.items()):raise ValueError('fixed_ground_root_macro_helpers_changed')
    return board,packet
compiler.compile=compile
