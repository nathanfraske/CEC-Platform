"""Atomic free-tee corridor planning for independently typed ordinary nets.

The current-owned operator stays immutable. This private constructor reuses
only its geometric window walk, with the original ordinary receiver owning
the saved source cut. Power, Ground, pairs, sensitive and unresolved nets are
never reclassified. Every actual retained contact web is rechecked.
"""
from pathlib import Path
import types,time
import pcbnew
import cec_force_current as force
import cec_native_tee_corridor_reflow as original
import cec_ordinary_route_receiving as ordinary
import cec_octilinear_terminal_trim as tips
import cec_full_current_terminal_trim as tip_geometry
import cec_consumer_corner_miter as contact_web
import cec_consumer_path_reflow as native_contacts

_SELF=Path(__file__).resolve();_SELF_HASH=force._hash(_SELF)
_BASE=Path(original.__file__).resolve();_BASE_HASH=force._hash(_BASE)

def identity():
    result={str(_SELF):_SELF_HASH,str(_BASE):_BASE_HASH,**tips.identity()}
    if any(force._hash(Path(p))!=h for p,h in result.items()):raise ValueError('ordinary_tee_helpers_changed')
    return result

def _menu(board,source,hint):
    nets=ordinary.eligible_nets(board,source,hint)
    rows=tips.geometry(board,source,True,time.monotonic()+10.)
    return dict(requests=[row for row in rows if row['net'] in nets],
        excluded_source_nets=sorted({row['net'] for row in rows if row['net'] not in nets}),
        positive_source_ordinary_types=True,power_current_authority_granted=False)

def _tip(board,source,request,hint):
    if request not in _menu(board,source,hint)['requests']:raise ValueError('actual_positive_ordinary_native_tee_required')
    live={force._uid(t):t for t in board.GetTracks()};old=live[request['source_track_uuid']]
    new=tip_geometry._replacement(old,request)
    contacts=tip_geometry._contacts(board,old,new,request,time.monotonic()+10.)
    return dict(request=request,native_contacts=contacts,source_typed_ordinary=True,
        current_or_firmware_mode_assumed=False,release_authority=False)

def _contacts(board,cut,points,deadline):
    new=[]
    for a,z in zip(points,points[1:]):
        t=cut[0].Duplicate();t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));new.append(t)
    return [contact_web.retained_contact_proof(peer,cut,new,int(cut[0].GetLayer()),cut[0].GetWidth(),deadline)
        for peer in native_contacts.contacts(board,cut)]

def _authority(board,source,hint,ids):
    live={force._uid(t):t for t in board.GetTracks()};nets={live[u].GetNetname() for u in ids}
    if len(nets)!=1 or not nets<=ordinary.eligible_nets(board,source,hint):
        raise ValueError('only_one_positive_ordinary_source_corridor_required')
    return dict(net=next(iter(nets)),source_typed_ordinary=True,current_budget_invented=False)

def _receive(source,child,hint,ids):
    b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    return ordinary.receive(source,child,board_hint=hint,retired_track_uuids=ids,
        allow_locked_track_uuids=[u for u in ids if live[u].IsLocked()],timeout_s=10.)

text=_BASE.read_text()
changes={
    "(t.GetNetname(),int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked()))==\n        (seed.GetNetname(),int(seed.GetLayer()),seed.GetWidth(),bool(seed.IsLocked()))}":"(t.GetNetname(),int(t.GetLayer()),t.GetWidth())==\n        (seed.GetNetname(),int(seed.GetLayer()),seed.GetWidth())}",
    "menu=tips.discover(board,source,board_hint=board_hint,allow_locked_source=True)":"menu=_menu(board,source,board_hint)",
    "tip=tips.plan(board,source,request,board_hint=board_hint,allow_locked_source=True)":"tip=_tip(board,source,request,board_hint)",
    "authority=full.plan(board,source,board_hint=board_hint,retired_track_uuids=ids)":"authority=_authority(board,source,board_hint,ids)",
    "contacts=paths._contacts(board,cut,points,deadline)":"contacts=_contacts(board,cut,points,deadline)",
    "proof=full.receive(source,child,board_hint=a.hint,retired_track_uuids=ids)":"proof=_receive(source,child,a.hint,ids)",
    "independent_original_current_receiving":"independent_original_ordinary_receiving",
    "str(Path(__file__).resolve()):force._hash(Path(__file__).resolve()),**tips.identity()":"**identity()",
    "plan=dict(retired_track_uuids=ids)":"plan=dict(retired_track_uuids=ids,retired_via_uuids=[],allow_locked_track_uuids=[u for u in ids if live[u].IsLocked()],allow_locked_via_uuids=[])",
    "source_current_proposal=authority":"source_ordinary_proposal=authority",
}
for old,new in changes.items():
    assert text.count(old)==1,old
    text=text.replace(old,new)
# Removed native objects cannot be queried after discard_items. Capture the
# exact source lock scope before the native cut, like its length witness.
old="source_length=sum(live[u].GetLength() for u in ids)"
assert text.count(old)==1;text=text.replace(old,old+"\n        source_locks=[u for u in ids if live[u].IsLocked()]")
text=text.replace("allow_locked_track_uuids=[u for u in ids if live[u].IsLocked()]","allow_locked_track_uuids=source_locks")
text=text.replace("source_locks=[u for u in ids if live[u].IsLocked()]",
    "source_locks=[u for u in ids if live[u].IsLocked()]\n        if source_locks:prototype.SetLocked(True)")
private=types.ModuleType('cec_private_ordinary_tee_corridor');private.__file__=str(_SELF)
private.__dict__.update(_menu=_menu,_tip=_tip,_contacts=_contacts,_authority=_authority,_receive=_receive,identity=identity)
exec(compile(text,str(_BASE),'exec'),private.__dict__)

def discover(*args,**kwargs):
    identity();result=private.discover(*args,**kwargs);identity();return result

if __name__=='__main__':private.main()
