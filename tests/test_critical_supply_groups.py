"""Pre-lock supply envelopes are all-or-nothing, independent of board identity."""
import ast
import inspect
import math
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

import cec_supply_group as group
import cec_synth_pipeline as synth


@pytest.mark.parametrize("prefix,offset", [("A", (0.,0.)), ("RENAMED", (31.,17.))])
@pytest.mark.parametrize("refuse,fixed", [(False,False), (True,False), (False,True)])
def test_whole_group_seat_respects_obstacles_and_admission(prefix,offset,refuse,fixed):
    layout={prefix:(0.,0.,0.),prefix+"_C1":(-2.,0.,0.),prefix+"_C2":(2.,0.,0.)}
    dx,dy=offset
    def box(ref,p): return p[0]-.5,p[1]-.5,p[0]+.5,p[1]+.5
    proposal,report=group.seat([layout],(dx+10.,dy+3.,0.),part_box=box,
        bounds=(dx+1.,dy+1.,dx+30.,dy+30.),
        obstacles=[(dx+1.,dy+1.,dx+29.,dy+20.)],
        fixed=fixed,admit=lambda p:not refuse,max_sites=12)
    assert report["proposals"]<=24
    if refuse or fixed:
        assert proposal is None and not report["ok"]
    else:
        assert set(proposal)==set(layout) and report["ok"]
        assert all(box(r,p)[1] > dy+20. for r,p in proposal.items())
    assert layout[prefix]==(0.,0.,0.)


@pytest.mark.parametrize("prefix,offset", [("DEVICE", (0.,0.)), ("Q78", (17.,23.))])
@pytest.mark.parametrize("mode", ["admit", "refuse", "owner_pin", "cap_pin", "blueprint", "back_side"])
def test_actual_prelock_adapter_and_anneal_exclusions(prefix,offset,mode):
    """Execute the production hook, including failure's downstream mobility."""
    import cec_pcb
    tree=ast.parse(inspect.getsource(synth.synth_one))
    stage=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)
               and n.name=="_p3_critical_seats")
    start=next(i for i,n in enumerate(stage.body) if isinstance(n,ast.If)
               and "critical_supply_groups" in ast.unparse(n.test))
    owner=prefix; ca=prefix+"_IN"; cb=prefix+"_OUT"
    origin=(10.+offset[0],10.+offset[1],0.)
    members={owner,ca,cb}
    reqs={ca:{"owner":owner},cb:{"owner":owner}}
    layout={owner:(0.,0.,0.),ca:(-2.,0.,0.),cb:(2.,0.,0.)}
    initial={owner:origin}
    locked={}
    if mode=="owner_pin": locked[owner]=origin
    if mode=="cap_pin":
        initial[ca]=(origin[0]-6.,origin[1],0.)
        locked[ca]=initial[ca]
    bp=members.copy() if mode=="blueprint" else set()
    env={"cfg":SimpleNamespace(params={},pins={}),"_state":SimpleNamespace(locked=locked),
         "_pourfirst_locked_refs":set(),"_bp_refs":bp,"_supply_macro_reservations":{},
         "_critical_supply_reports":[],"anchors":dict(initial),"_bounds":{},
         "_env3":[],"_back":(ca,) if mode=="back_side" else (),"nl":None,"passives":[ca,cb],"ics":[owner],
         "comps":dict.fromkeys(members,"land"),"cec_pcb":cec_pcb,
         "_device_bypass_specs":lambda *a:reqs,
         "_qualified_supply_layouts":lambda *a,**kw: ([] if mode=="refuse" else [layout],{}),
         "_component_obstacles":lambda *a:[],"W":80.,"H":80.,"sys":sys,
         "_can_seated":[owner],"seated_inas":[owner],"_sw_seated":[owner],
         "_esp":owner,"_esp_pos":origin,"free_shunts":[]}
    with mock.patch.object(cec_pcb,"courtyard_bbox",
            side_effect=lambda fp,x,y,r:(x-.5,x+.5,y-.5,y+.5)):
        exec(compile(ast.Module(body=stage.body[start:],type_ignores=[]),"prelock","exec"),env)
    if mode=="admit":
        assert set(env["anchors"])==members
        assert set(env["_supply_macro_reservations"][owner])==members
        assert members<=env["_bp_refs"] and owner not in env["anneal_units"]
    elif mode in ("refuse","cap_pin","back_side"):
        assert owner not in env["anchors"] and owner in env["anneal_units"]
        assert not env["_supply_macro_reservations"] and not env["_bp_refs"]
        if mode=="cap_pin": assert env["anchors"][ca]==initial[ca]
    else:
        assert env["anchors"]==initial and not env["_supply_macro_reservations"]


def test_new_lock_cannot_bypass_native_check_and_late_proposals_have_final_gate():
    source=inspect.getsource(synth.synth_one)
    tree=ast.parse(source)
    stage=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)
               and n.name=="_p3_critical_seats")
    calls=[n for n in ast.walk(stage) if isinstance(n,ast.Call)
           and isinstance(n.func,ast.Name) and n.func.id=="_qualified_supply_layouts"]
    assert len(calls)==1
    assert any(k.arg=="native_required" and k.value.value is True for k in calls[0].keywords)
