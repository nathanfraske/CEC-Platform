"""Frozen terminal stage, private any-0/45-tap owner and bound dependencies."""
from pathlib import Path
import types
import cec_force_current as force
import cec_full_current_terminal_trim_stage as original
import cec_octilinear_terminal_trim as owner

_SELF=Path(__file__).resolve();_SELF_HASH=force._hash(_SELF)
_BASE=Path(original.__file__).resolve();_BASE_HASH=force._hash(_BASE)
_text=_BASE.read_text();_old='import cec_full_current_terminal_trim as owner'
assert _text.count(_old)==1
_text=_text.replace(_old,'import cec_octilinear_terminal_trim as owner')
_old="    force._write(outdir/'stage.json',result);return result"
_new="""    result['input_sha256']={**owner.identity(),str(_BASE):_BASE_HASH,str(_SELF):_SELF_HASH}
    if any(force._hash(Path(path))!=digest for path,digest in result['input_sha256'].items()):
        raise ValueError('octilinear_terminal_stage_dependencies_changed')
    result['geometry_scope']='any_nonparallel_exact_native_octilinear_tap'
    force._write(outdir/'stage.json',result);return result"""
assert _text.count(_old)==1;_text=_text.replace(_old,_new)
_ns=types.ModuleType('cec_private_octilinear_terminal_stage');_ns.__file__=str(_BASE)
_ns.__dict__.update(_BASE=_BASE,_BASE_HASH=_BASE_HASH,_SELF=_SELF,_SELF_HASH=_SELF_HASH)
exec(compile(_text,str(_BASE),'exec'),_ns.__dict__)

def run(*args,**kwargs):return _ns.run(*args,**kwargs)

if __name__=='__main__':_ns.main()
