"""Late pose proposals must preserve actual constructor and placement evidence."""
import ast
import dataclasses
import inspect
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest

import cec_placement_commit as commit


@pytest.mark.parametrize("prefix,offset", [("ITEM",0.),("RENAMED",37.)])
def test_failed_batch_keeps_only_cumulatively_proved_rotations(prefix,offset):
    a,b,c=[prefix+str(i) for i in range(3)]
    before={r:[offset+i,offset+2.,0.] for i,r in enumerate((a,b,c))}
    proposed={r:(p[0],p[1],180.) for r,p in before.items()}
    seen=[]
    def prove(poses):
        seen.append(poses)
        # A and B can each rotate alone, but not together. C is always safe.
        return {"ok":not (poses[a][2] and poses[b][2]),"constructor":"synthetic"}
    accepted,report=commit.admit_changes(before,proposed,prove)
    assert report["accepted"]==[a,c] and report["rejected"]==[b]
    assert accepted[a][2]==accepted[c][2]==180. and accepted[b][2]==0.
    assert all(p[2]==0. for p in before.values())
    assert seen[-1]==accepted and len(seen)==5
    assert not report["budget_exhausted"]


@pytest.mark.parametrize("mode", ["pass","refuse_baseline","exception","nonboolean"])
def test_fast_path_and_unknown_proof_fail_closed(mode):
    before={"PART":(4.,7.,0.)}; proposed={"PART":(4.,7.,90.)}
    def prove(poses):
        if mode=="exception": raise RuntimeError("native constructor failed")
        return {"ok": True if mode=="pass" else 1 if mode=="nonboolean" else False}
    actual,report=commit.admit_changes(before,proposed,prove)
    assert actual==(proposed if mode=="pass" else before)
    assert report["ok"] is (mode=="pass")
    assert len(report["probes"])==(2 if mode=="pass" else 1)


def test_budget_exhaustion_never_applies_unproved_proposals():
    before={r:(1.,1.,0.) for r in ("A","B","C")}
    proposed={r:(1.,1.,90.) for r in before}
    def prove(p): return {"ok":sum(bool(x[2]) for x in p.values())<2}
    actual,report=commit.admit_changes(before,proposed,prove,max_probes=3)
    assert actual==dict(before,A=proposed["A"])
    assert report["accepted"]==["A"] and report["rejected"]==["B","C"]
    assert report["unproved"]==["B","C"] and report["budget_exhausted"]
    assert len(report["probes"])==3


def test_no_changes_does_not_start_a_proof():
    prove=mock.Mock()
    actual,report=commit.admit_changes({"X":(0,0,0)},{"X":(0,0,0)},prove)
    prove.assert_not_called()
    assert report["reason"]=="no_changes"


@pytest.mark.parametrize("proposed,budget", [({"OTHER":(1,1,0)},3),
    ({"X":(float("nan"),1,0)},3),({"X":(1,1,90)},0),({"X":(1,1,90)},1.5)])
def test_invalid_transactions_are_not_admitted(proposed,budget):
    with pytest.raises(ValueError):
        commit.admit_changes({"X":(1,1,0)},proposed,lambda p:{"ok":True},max_probes=budget)


@dataclasses.dataclass
class FakeConfig:
    net: str = "stale.net"
    params: dict = dataclasses.field(default_factory=dict)


@pytest.mark.parametrize("mode", ["timeout","crash","missing","bad_json","arbitrary_pose",
                                 "accounting","good"])
def test_worker_boundary_is_fail_closed_and_forces_fresh_source(mode):
    before={"X":(1.,1.,0.)}; proposed={"X":(1.,1.,90.)}
    def worker(command,timeout):
        payload=json.loads(Path(command[-2]).read_text())
        assert payload["cfg"]["net"] is None
        if mode=="timeout": raise subprocess.TimeoutExpired(command,timeout)
        if mode=="crash": return subprocess.CompletedProcess(command,1,"","crashed")
        if mode=="bad_json": Path(command[-1]).write_text("bad json")
        elif mode!="missing":
            report={"schema":1,"requested":["X"],"accepted":["X"],"rejected":[],"ok":True}
            if mode=="accounting": report["accepted"]=[]
            positions={"X":(1.,1.,45.)} if mode=="arbitrary_pose" else proposed
            Path(command[-1]).write_text(json.dumps({"positions":positions,"report":report}))
        return subprocess.CompletedProcess(command,0,"","")
    with mock.patch.object(commit,"_run_worker",side_effect=worker):
        actual,report=commit.native_admit(FakeConfig(),before,proposed,width=20,height=20)
    assert actual==(proposed if mode=="good" else before)
    assert report["accepted"]==(["X"] if mode=="good" else [])


def test_timeout_stops_the_worker_process_group():
    proc=mock.MagicMock(pid=123,returncode=-9)
    proc.__enter__.return_value=proc
    proc.communicate.side_effect=[subprocess.TimeoutExpired("worker",.1),("","")]
    with mock.patch.object(commit.subprocess,"Popen",return_value=proc) as popen, \
         mock.patch.object(commit.os,"killpg",create=True) as killpg, \
         mock.patch.object(commit.os,"name","posix"):
        with pytest.raises(subprocess.TimeoutExpired): commit._run_worker(["worker"],.1)
    assert popen.call_args.kwargs["start_new_session"] is True
    killpg.assert_called_once_with(123,commit.signal.SIGKILL)


def test_native_commit_worker_is_in_the_placement_cache_dependency_closure():
    import cec_full_pipeline as pipeline
    paths={p.name for p in pipeline._local_code_closure("cec_synth_pipeline.py")}
    assert "cec_placement_commit.py" in paths


@pytest.mark.parametrize("bad_term", [None,"blueprints","rails","pads","courtyards"])
def test_native_adapter_uses_all_authoritative_terms_and_fresh_trials(tmp_path,bad_term):
    import cec_synth_pipeline as synth
    net=tmp_path/"owned.net"; net.write_text("net")
    before={"ANY":(5.,5.,0.)}; proposed={"ANY":(5.,5.,180.)}
    paths=[]
    def materialize(cand,cfg,path):
        assert not Path(path).exists() and not list(Path(path).parent.iterdir())
        paths.append(path)
        Path(path).write_text("trial")
    payload={"cfg":{"net":None,"params":{}},"before":before,"proposed":proposed,
             "width":20,"height":20,"back_refs":[],"blueprint_stamps":[],"max_probes":3}
    with mock.patch.object(synth,"Config",FakeConfig), \
         mock.patch.object(synth,"_ensure_netlist_path",return_value=str(net)), \
         mock.patch.object(synth,"materialize",side_effect=materialize), \
         mock.patch.object(synth,"_blueprint_cell_craft_evidence",return_value={"ok":bad_term!="blueprints"}), \
         mock.patch.object(synth,"_force_rail_craft_evidence",return_value={"ok":bad_term!="rails"}), \
         mock.patch.object(synth,"_oracle_pads_in_bounds",return_value={"ok":bad_term!="pads"}), \
         mock.patch.object(synth,"_oracle_courtyard_overlaps",return_value={"ok":bad_term!="courtyards"}):
        commit._worker(payload,tmp_path/"response.json")
    result=json.loads((tmp_path/"response.json").read_text())
    assert result["report"]["ok"] is (bad_term is None)
    assert len(paths)==len(set(paths))==(2 if bad_term is None else 1)
    assert not net.exists() and all(not Path(p).exists() for p in paths)


@pytest.mark.parametrize("policy", ["blueprint_cells","force_lanes","force_rails",None])
def test_actual_orientation_stage_filters_both_scorers_before_ratification(policy):
    import cec_synth_pipeline as synth
    tree=ast.parse(inspect.getsource(synth.synth_one))
    stage=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)
               and n.name=="_p10b_pin_orient")
    stage.body=[ast.copy_location(ast.Global(names=n.names),n) if isinstance(n,ast.Nonlocal)
                else n for n in stage.body]
    before={"PASSIVE":(5.,5.,0.),"FLOW":(10.,5.,0.),"OWNED":(15.,5.,0.)}
    def two(nl,comps,p,refs,*args,**kw):
        assert "OWNED" not in refs
        p["PASSIVE"]=(5.,5.,90.)
        return {"PASSIVE":(0.,90.)}
    def flow(nl,comps,p,*args,**kw):
        assert "OWNED" in kw["protected_refs"]
        p["FLOW"]=(10.,5.,180.)
        return {"FLOW":(0.,180.)}
    def admit(cfg,old,proposal,**kwargs):
        assert old==before
        return commit.admit_changes(old,proposal,lambda p:{"ok":p["FLOW"][2]==0.})
    state=SimpleNamespace(locked={"OWNED":before["OWNED"]})
    env=dict(vars(synth))
    env.update(P=dict(before),_pin_orient_changes={},_pin_orient_admission={},
        cfg=SimpleNamespace(params={policy:True} if policy else {},pins={}),
        _state=state,nl=None,comps={},passives=list(before),_pourfirst_locked_refs=set(),
        _anchor_local_refs=set(),anchors={},_back=(),drop_antenna=False,
        _blueprint_stamps=[],W=30,H=30,_pin_aware_two_terminal_orientations=two,
        _flow_through_pair_orientations=flow)
    with mock.patch.object(commit,"native_admit",side_effect=admit) as native:
        exec(compile(ast.fix_missing_locations(ast.Module(body=[stage],type_ignores=[])),
                     "orientation-stage","exec"),env)
        env["_p10b_pin_orient"](state)
    assert env["P"]["PASSIVE"][2]==90.
    assert env["P"]["FLOW"][2]==(0. if policy else 180.)
    assert state.locked=={"OWNED":before["OWNED"]}
    if policy:
        native.assert_called_once()
        assert env["_pin_orient_admission"]["rejected"]==["FLOW"]
        assert env["_pin_orient_changes"]=={"PASSIVE":(0.,90.)}
    else:
        native.assert_not_called()
