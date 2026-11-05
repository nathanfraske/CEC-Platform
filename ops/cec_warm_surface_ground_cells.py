"""Exact warm stationary-surface checks in the pad-bounded Source-ranked frontier."""
import types
from pathlib import Path
import cec_force_current as force
import cec_pad_bound_ground_cell_poses as original
import cec_stationary_surface_snapshot as surface_cache

_PATH=Path(__file__).resolve();_HASH=force._hash(_PATH)
_BASE=Path(original.__file__).resolve();_BASE_HASH=force._hash(_BASE);text=original.text
needle="surface=surfaces.surface_screen(board,c['refs'],selected_refs=c['refs'],allow_native_ground_refill=True,timeout_s=2.)"
assert text.count(needle)==1
text=text.replace(needle,"surface=c['warm_surface_snapshot'].check(timeout_s=2.)")
private=types.ModuleType('cec_private_warm_surface_ground_cells');private.__file__=str(_PATH)
private.__dict__.update(_ANNULAR_PARENT=original.base._parent,_ANNULAR_PARENT_HASH=original.base._parent_hash,
    _PAD_BOUND_BASE=original._base_path,_PAD_BOUND_BASE_HASH=original._base_hash,_PAD_MOTION=original.pad_motion)
exec(compile(text,str(original.base._parent),'exec'),private.__dict__)
def bound():
    original.bound();surface_cache.identity()
    if force._hash(_PATH)!=_HASH or force._hash(_BASE)!=_BASE_HASH:raise ValueError('warm_surface_ground_cell_helpers_changed')
def prepare(*args,**kwargs):
    bound();c=private.prepare(*args,**kwargs)
    c['warm_surface_snapshot']=surface_cache.Snapshot(c['board'],c['refs'])
    c['helpers'].update(surface_cache.identity());c['helpers'].update({str(_PATH):_HASH,str(_BASE):_BASE_HASH})
    c['settings']['stationary_surface_mode']='exact_warm_snapshot_with_live_binding_and_fresh_moving_lands'
    c['identity']=private._digest(dict(previous=c['identity'],helpers=c['helpers'],settings=c['settings']))
    bound();return c
def scan(*args,**kwargs):
    bound();r=private.scan(*args,**kwargs);bound();return r
