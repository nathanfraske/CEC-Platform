"""Explicit outer-region joint-cell search, not skipped inner coverage.

Keep the original finite-menu helper immutable. The annulus is a separately
bound portfolio, with the same native gates and normal macro motion limit.
It does NOT claim that inner states under a different owner-shift bound were
exhausted. No board coordinate, reference or hardware current budget appears.
"""
import types
from pathlib import Path
import cec_force_current as force
import cec_paged_ground_cell_pose_frontier as original

_parent=Path(original.__file__).resolve();_parent_hash=force._hash(_parent)
_self=Path(__file__).resolve();_self_hash=force._hash(_self);text=_parent.read_text()
def replace(old,new):
    global text
    if text.count(old)!=1:raise ValueError('frozen_annular_pose_hook_changed')
    text=text.replace(old,new)
replace('def prepare(frame,*,radius_mm=16.,grid_mm=.5):',
    'def prepare(frame,*,radius_mm=16.,grid_mm=.5,minimum_ground_shift_mm=0.):')
replace('    seed=copy.deepcopy(frame);source=',
    "    if (type(minimum_ground_shift_mm) not in (int,float) or not math.isfinite(minimum_ground_shift_mm)\n"
    "            or not 0<=minimum_ground_shift_mm<radius_mm):raise ValueError('bounded_explicit_annular_region_required')\n"
    '    seed=copy.deepcopy(frame);source=')
replace('    identity=_digest(dict(source_sha256=digest,',
    "    settings['minimum_ground_shift_mm']=minimum_ground_shift_mm\n"
    "    helpers[str(_ANNULAR_PARENT)]=_ANNULAR_PARENT_HASH\n"
    '    identity=_digest(dict(source_sha256=digest,')
replace('    lattice=points(origin,round(radius_mm*1e6),round(grid_mm*1e6))',
    '    lattice=points(origin,round(radius_mm*1e6),round(grid_mm*1e6))\n'
    '    if minimum_ground_shift_mm>0:\n'
    '        inner=round(minimum_ground_shift_mm*1e6)\n'
    '        lattice=[p for p in lattice if (p[0]-origin[0])**2+(p[1]-origin[1])**2>inner**2]')
private=types.ModuleType('cec_private_explicit_annular_ground_cell');private.__file__=str(_self)
private.__dict__.update(_ANNULAR_PARENT=_parent,_ANNULAR_PARENT_HASH=_parent_hash)
exec(compile(text,str(_parent),'exec'),private.__dict__)
def bound():
    if force._hash(_parent)!=_parent_hash or force._hash(_self)!=_self_hash:
        raise ValueError('annular_ground_cell_helpers_changed')
def prepare(*args,**kwargs):
    bound();result=private.prepare(*args,**kwargs);bound();return result
def scan(*args,**kwargs):
    bound();result=private.scan(*args,**kwargs);bound();return result
