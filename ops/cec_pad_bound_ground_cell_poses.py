"""Pad-bounded, Source-pickup-ranked joint poses; unchanged native gates.

A legal footprint-origin shift does not prove every rotated SMD land stays
within the original macro motion bound. Check integer native pad motion
before offering a pose. Rank the finite region by the actual Source-typed
measurement pickup ports when present, not a board coordinate or refdes.
"""
import types
from pathlib import Path
import cec_force_current as force
import cec_annular_ground_cell_pose_frontier as base

def pad_motion(parent,posed,refs,limit_nm):
    if (type(refs) not in (set,list,tuple) or not 1<=len(refs)<=8 or len(set(refs))!=len(refs)
            or type(limit_nm) is not int or not 0<limit_nm<=32000000):
        raise ValueError('bounded_literal_native_cell_pad_motion_required')
    old={force._uid(p):p for f in parent.GetFootprints() if f.GetReference() in refs for p in f.Pads()}
    new={force._uid(p):p for f in posed.GetFootprints() if f.GetReference() in refs for p in f.Pads()}
    if not old or old.keys()!=new.keys():raise ValueError('exact_source_and_posed_pad_population_required')
    refused=[];maximum=0
    for uid,p in old.items():
        q=new[uid]
        if p.GetNetname()!=q.GetNetname() or p.GetNumber()!=q.GetNumber():raise ValueError('native_cell_pad_identity_changed')
        dx=q.GetPosition().x-p.GetPosition().x;dy=q.GetPosition().y-p.GetPosition().y;squared=dx*dx+dy*dy
        maximum=max(maximum,squared)
        if squared>limit_nm*limit_nm:refused.append(uid)
    return dict(ok=not refused,refused_pad_uuids=sorted(refused),maximum_squared_motion_nm2=maximum,
        bound_nm=limit_nm,exact_integer_native_pad_motion=True,placement_or_routing_authority=False)

_base_path=Path(base.__file__).resolve();_base_hash=force._hash(_base_path)
_self=Path(__file__).resolve();_self_hash=force._hash(_self);text=base.text
def replace(old,new):
    global text
    if text.count(old)!=1:raise ValueError('frozen_pad_bounded_pose_hook_changed')
    text=text.replace(old,new)
replace("    identity=_digest(dict(source_sha256=digest,",
    "    helpers[str(_PAD_BOUND_BASE)]=_PAD_BOUND_BASE_HASH\n"
    "    settings['all_native_smd_pad_motion_bounded']=True\n"
    "    settings['ordering']='actual_source_typed_measurement_ports_then_original_motion'\n"
    "    owner_pad_ids={force._uid(p) for p in parent.FindFootprintByReference(owner_ref).Pads()}\n"
    "    ports=[tuple(q['b']['at_nm']) for q in packet['requests'].values()\n"
    "        if q['kind'] in ('measurement','isolated_measurement') and q['a'].get('pad_uuid') in owner_pad_ids]\n"
    "    settings['source_measurement_pickup_points_nm']=ports\n"
    "    identity=_digest(dict(source_sha256=digest,")
needle='    return dict(source=source,digest=digest,epoch=epoch,family=family,seed=seed,parent=parent,board=board,'
replace(needle,
    "    if ports:lattice.sort(key=lambda p:(sum((p[0]-q[0])**2+(p[1]-q[1])**2 for q in ports),\n"
    "        (p[0]-origin[0])**2+(p[1]-origin[1])**2,p))\n"+needle)
needle="        court=surfaces.courtyard_screen(board,c['refs'])"
replace(needle,
    "        motion=_PAD_MOTION(c['parent'],board,c['refs'],round(c['settings']['radius_mm']*1e6))\n"
    "        if not motion['ok']:return dict(kind='native_smd_pad_motion_refused',diagnostic=motion)\n"+needle)
private=types.ModuleType('cec_private_pad_bounded_source_ranked_ground_cells');private.__file__=str(_self)
private.__dict__.update(_ANNULAR_PARENT=base._parent,_ANNULAR_PARENT_HASH=base._parent_hash,
    _PAD_BOUND_BASE=_base_path,_PAD_BOUND_BASE_HASH=_base_hash,_PAD_MOTION=pad_motion)
exec(compile(text,str(base._parent),'exec'),private.__dict__)
def bound():
    base.bound()
    if force._hash(_base_path)!=_base_hash or force._hash(_self)!=_self_hash:
        raise ValueError('pad_bounded_ground_cell_helpers_changed')
def prepare(*args,**kwargs):
    bound();r=private.prepare(*args,**kwargs);bound();return r
def scan(*args,**kwargs):
    bound();r=private.scan(*args,**kwargs);bound();return r
