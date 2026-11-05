"""Exact native dead-tip trimming at any nonparallel 0/45 tee.

Extend only the frozen discovery predicate, which previously required a
perpendicular tap. The saved original-current, exact-contact-web, visible
material, source-capsule-subset, immutable metadata and native replay gates
are retained unchanged. This does not own a branch rip-up or a load waiver.
"""
from pathlib import Path
import types
import cec_force_current as force
import cec_full_current_terminal_trim as original

_SELF=Path(__file__).resolve();_SELF_HASH=force._hash(_SELF)
_BASE=Path(original.__file__).resolve();_BASE_HASH=force._hash(_BASE)
_old="if not any(pv) or d[0]*pv[0]+d[1]*pv[1]!=0:continue"
_new="if not any(pv) or d[0]*pv[1]-d[1]*pv[0]==0:continue"
_text=_BASE.read_text()
assert _text.count(_old)==1
_ns=types.ModuleType('cec_private_octilinear_terminal_trim');_ns.__file__=str(_BASE)
exec(compile(_text.replace(_old,_new),str(_BASE),'exec'),_ns.__dict__)

def identity():
    if force._hash(_SELF)!=_SELF_HASH or force._hash(_BASE)!=_BASE_HASH:
        raise ValueError('octilinear_terminal_trim_helpers_changed')
    return {str(_SELF):_SELF_HASH,str(_BASE):_BASE_HASH}

def _call(name,*args,**kwargs):
    identity();result=getattr(_ns,name)(*args,**kwargs);identity();return result

def geometry(*args,**kwargs):return _call('_geometry',*args,**kwargs)
def discover(*args,**kwargs):return _call('discover',*args,**kwargs)
def plan(*args,**kwargs):return _call('plan',*args,**kwargs)
def materialize(*args,**kwargs):return _call('materialize',*args,**kwargs)
def receive(*args,**kwargs):return _call('receive',*args,**kwargs)
