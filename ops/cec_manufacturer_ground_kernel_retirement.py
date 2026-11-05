"""Obsolete generated return kernels for positively typed device Ground pins.

The frozen capacitor rule remains unchanged. Extend its owner predicate to
unique manufacturer Ground/power-return terminals of non-converters, retaining ALL
of its single-land/in-pad-root, generated-hole, native contact, bounded kernel,
actual plane-bridge, exact subtraction and independent saved receiving gates.
No mesh, ordinary stitch, power-output, address strap or anonymous pad waiver.
"""
from pathlib import Path
import types
import cec_force_current as force
import cec_device_power_roles as roles
import cec_redundant_local_ground_return as original

_original_path=Path(original.__file__).resolve();_original_hash=force._hash(_original_path)
_self_path=Path(__file__).resolve();_self_hash=force._hash(_self_path)


def _positive_owner(owner,pad):
    model=roles.footprint_contract(owner)
    if (owner.IsDNP() or model is None
            or model['pins'].get(str(pad.GetNumber())) not in ('ground','power_return')
            or set(model['pins'].values())&{'power_output','switch','feedback'}
            or sum(str(p.GetNumber())==str(pad.GetNumber()) for p in owner.Pads())!=1):
        return None
    return dict(kind='manufacturer_positive_nonconverter_ground_terminal',reference=owner.GetReference(),
        pin=str(pad.GetNumber()),manufacturer_pin_role=model['pins'][str(pad.GetNumber())],
        manufacturer_source=model['source'],source_current_not_invented=True)


_text=_original_path.read_text()
_old="""    if (pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.HasHole()
            or owner.IsDNP() or len(members)!=2
            or not caps.capacitor_identity(owner.GetReference(),owner.GetFPIDAsString())
            or farads is None or not 0<farads<=1e-3
            or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole() for p in members)
            or len([p for p in members if p.GetNetname()=='GND'])!=1):
        raise ValueError('actual_two_land_local_capacitor_ground_owner_required')"""
_new="""    capacitor_owner=(not owner.IsDNP() and len(members)==2
            and caps.capacitor_identity(owner.GetReference(),owner.GetFPIDAsString())
            and farads is not None and 0<farads<=1e-3
            and all(p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not p.HasHole() for p in members)
            and len([p for p in members if p.GetNetname()=='GND'])==1)
    manufacturer_owner=_positive_owner(owner,pad)
    if (pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.HasHole()
            or not capacitor_owner and manufacturer_owner is None):
        raise ValueError('source_capacitor_or_positive_nonconverter_manufacturer_ground_owner_required')"""
assert _text.count(_old)==1;_text=_text.replace(_old,_new)
_old="return dict(schema=1,kind='obsolete_generated_capacitor_ground_return_kernel',"
_new="return dict(schema=1,kind='obsolete_generated_typed_device_ground_return_kernel',owner_authority=(dict(kind='source_two_land_capacitor_ground') if capacitor_owner else manufacturer_owner),"
assert _text.count(_old)==1;_text=_text.replace(_old,_new)
_ns=types.ModuleType('cec_private_manufacturer_ground_kernel');_ns.__file__=str(_original_path)
_ns.__dict__['_positive_owner']=_positive_owner
exec(compile(_text,str(_original_path),'exec'),_ns.__dict__)


def _bound():
    if force._hash(_original_path)!=_original_hash or force._hash(_self_path)!=_self_hash:
        raise ValueError('frozen_manufacturer_ground_kernel_helpers_changed')


def plan(*args,**kwargs):
    _bound();q=_ns.plan(*args,**kwargs);_bound();return q


def subtract(*args,**kwargs):
    _bound();r=_ns.subtract(*args,**kwargs);_bound();return r


def receive(*args,**kwargs):
    _bound();r=_ns.receive(*args,**kwargs);_bound();return r


def identity():
    _bound();return {str(_original_path):_original_hash,str(_self_path):_self_hash}
