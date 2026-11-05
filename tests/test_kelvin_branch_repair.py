"""Private typed-branch replacement without product coordinates or current waivers."""
import copy
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

import pcbnew
import pytest

import cec_force_current as force
import cec_force_sense_evidence as evidence
import cec_kelvin_branch_repair as repair
import cec_zone_fill


def fixture(path, *, angle=0, translated=False, renamed=False, boundary=False,
            grouped=False, source_shape=None):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    props = board.GetProperties(); props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
    board.SetProperties(props)
    feed, peer, foreign = (("CABLE_X", "CABLE_Y", "OTHER") if renamed else
                           ("ARBITRARY_FORCE", "ARBITRARY_OTHER_FORCE", "FOREIGN"))
    src, monitor, supply, load = (("R_MEASURE_77", "U_FRONTEND_41", "J_INPUT_8", "J_OUTPUT_9")
                                  if renamed else ("ANCHOR", "SENSOR", "FEED", "LOAD"))
    nets = {}
    for name in (feed, peer, foreign):
        net = pcbnew.NETINFO_ITEM(board, name); board.Add(net); nets[name] = net
    footprints = {}
    def pad(ref, number, net, x, y, size, value="", resistor=False):
        fp = footprints.get(ref)
        if fp is None:
            fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); fp.SetValue(value)
            fp.SetFPID(pcbnew.LIB_ID("Resistor_SMD" if resistor else "Fixture", "Native"))
            board.Add(fp); footprints[ref] = fp
        item = pcbnew.PAD(fp); item.SetNumber(number); item.SetNet(nets[net])
        item.SetAttribute(pcbnew.PAD_ATTRIB_SMD); item.SetShape(pcbnew.PAD_SHAPE_RECT)
        item.SetLayerSet(pcbnew.PAD.SMDMask()); item.SetSize(pcbnew.VECTOR2I_MM(*size))
        item.SetPosition(pcbnew.VECTOR2I_MM(x,y)); fp.Add(item)
        return item
    def track(net, a, b, width=.25):
        item = pcbnew.PCB_TRACK(board); item.SetNet(nets[net]); item.SetLayer(pcbnew.F_Cu)
        item.SetWidth(pcbnew.FromMM(width)); item.SetLocked(True)
        item.SetStart(pcbnew.VECTOR2I_MM(*a)); item.SetEnd(pcbnew.VECTOR2I_MM(*b)); board.Add(item)
        return item
    anchor = pad(src,"a",feed,20,30,(3,1),resistor=True)
    if source_shape is not None:
        anchor.SetShape(source_shape)
    pad(src,"b",peer,20,24,(3,1),resistor=True)
    pad(supply,"in",feed,20,37,(2,2)); pad(load,"out",peer,20,18,(2,2))
    pad(monitor,"8",feed,15,27,(.3,1.45),value="INA240A3")
    pad(monitor,"1",peer,15,25,(.3,1.45),value="INA240A3")
    pad("OBSTACLE","1",foreign,16,27,(.3,1.45))
    bad = track(feed,(20,29.8),(15,29.8))
    stem = track(feed,(15,29.8),(15,27))
    spine = track(feed,(20,29.8),(20,28.3))
    track(peer,(20,18),(20,23.7),.6)
    track(peer,(20,24),(20,25)); track(peer,(20,25),(15,25))
    zone = pcbnew.ZONE(board); zone.SetNet(nets[feed]); zone.SetLayer(pcbnew.F_Cu)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL); zone.SetLocalClearance(pcbnew.FromMM(.2))
    zone.SetMinThickness(pcbnew.FromMM(.05)); zone.Outline().NewOutline()
    for xy in ((17,29.5 if boundary else 29.7),(23,29.5 if boundary else 29.7),(23,39),(17,39)):
        zone.Outline().Append(pcbnew.FromMM(xy[0]),pcbnew.FromMM(xy[1]))
    board.Add(zone)
    for a,b in (((0,0),(50,0)),((50,0),(50,50)),((50,50),(0,50)),((0,50),(0,0))):
        edge=pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_SEGMENT); edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b)); board.Add(edge)
    if grouped:
        group=pcbnew.PCB_GROUP(board); group.SetName("retained-owned-branch"); board.Add(group); group.AddItem(bad)
    origin=pcbnew.VECTOR2I(0,0); rotation=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
    delta=pcbnew.VECTOR2I_MM(80,70) if translated else pcbnew.VECTOR2I(0,0)
    for fp in board.GetFootprints():
        fp.Rotate(origin,rotation); fp.SetPosition(fp.GetPosition()+delta)
    for item in [*board.GetTracks(),*board.Zones(),*board.GetDrawings()]:
        item.Rotate(origin,rotation); item.Move(delta)
    cec_zone_fill.fill_with_report(board)
    pcbnew.SaveBoard(str(path),board,True)
    path.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings":{"classes":[
        {"name":"Default","clearance":.2,"track_width":.25,"via_diameter":.6,"via_drill":.3}]}}))
    path.with_suffix(".kicad_prl").write_text('{"retained_ui":true}\n')
    domains={}
    for name,a,b in ((feed,supply,src),(peer,src,load)):
        domains[name]=dict(net=name,source_refs=[a],sink_refs=[b],authority_refs=[a,b],
                           complete=True,source="synthetic_terminal_authority_no_current_budget")
    return dict(net=feed,peer=peer,domains=domains,removed={repair._uuid(bad),repair._uuid(stem)},
                spine=repair._uuid(spine),zone=repair._uuid(zone),input_ref=monitor)


def select(path,row):
    with patch("cec_current_topology.board_current_domains",return_value=row["domains"]):
        report=evidence.replay(path,board_hint="explicit-fixture")
    board=pcbnew.LoadBoard(str(path))
    return board,report,repair._select(board,report,row["net"],time.monotonic()+20)


def construct(path,row):
    board,report,selection=select(path,row)
    plan=repair._construct(board,selection,200000,time.monotonic()+20,64)
    return board,report,selection,plan


@pytest.mark.parametrize("angle,translated,renamed",[(0,False,False),(0,True,True),(90,True,True),(180,False,True)])
def test_native_selection_and_obstacle_derived_construction_generalize(tmp_path,angle,translated,renamed):
    source=tmp_path/"board.kicad_pcb"
    row=fixture(source,angle=angle,translated=translated,renamed=renamed)
    original=source.read_bytes()
    board,before,selection,plan=construct(source,row)
    assert {r["uuid"] for r in selection["removed"]} == row["removed"]
    assert selection["definite_source_zone_overlap"]
    assert plan["constructed"], plan
    assert plan["retained_legs"] and any(r["uuid"]==row["spine"] for r in plan["retained_legs"])
    assert all(r["width_nm"]==250000 and r["locked"] for r in plan["added"])
    assert source.read_bytes()==original
    candidate=repair._copy(source,tmp_path/"candidate")
    pcbnew.SaveBoard(str(candidate),board,True)
    replacement=dict(selection,added=plan["added"],retained_legs=plan["retained_legs"],
        path_nm=plan["path_nm"],source_family=repair._family(source,"explicit-fixture"),source_sha256=force._hash(source))
    assert repair.preservation(source,candidate,replacement,board_hint="explicit-fixture")["ok"]
    with patch("cec_current_topology.board_current_domains",return_value=row["domains"]):
        after=evidence.replay(candidate,board_hint="explicit-fixture")
    assert evidence.admit_changed_net(before,after,row["net"])["ok"], after["clipped_isolation"]


def test_unsupported_boundary_uncertainty_is_improvement_not_accepted_isolation(tmp_path):
    source=tmp_path/"board.kicad_pcb"
    row=fixture(source,boundary=True,source_shape=pcbnew.PAD_SHAPE_OVAL)
    board,before,selection,plan=construct(source,row)
    assert plan["constructed"],plan
    candidate=repair._copy(source,tmp_path/"candidate"); pcbnew.SaveBoard(str(candidate),board,True)
    with patch("cec_current_topology.board_current_domains",return_value=row["domains"]):
        after=evidence.replay(candidate,board_hint="explicit-fixture")
    old=next(r for r in before["clipped_isolation"]["details"] if r["net"]==row["net"])
    new=next(r for r in after["clipped_isolation"]["details"] if r["net"]==row["net"])
    assert old["native"]["physical_bypass_proved"]
    assert new["ok"] is None and not new["native"]["lower"]["reached_authority"]
    assert not evidence.admit_changed_net(before,after,row["net"])["ok"]


@pytest.mark.parametrize("angle,translated,renamed",[(0,False,False),(90,True,True),
                                                   (180,False,True),(270,True,False)])
def test_certified_linear_boundary_repair_has_absolute_postchange_isolation(
        tmp_path,angle,translated,renamed):
    source=tmp_path/"board.kicad_pcb"
    row=fixture(source,boundary=True,angle=angle,translated=translated,renamed=renamed)
    board,before,selection,plan=construct(source,row)
    assert plan["constructed"],plan
    candidate=repair._copy(source,tmp_path/"candidate")
    pcbnew.SaveBoard(str(candidate),board,True)
    with patch("cec_current_topology.board_current_domains",return_value=row["domains"]):
        after=evidence.replay(candidate,board_hint="explicit-fixture")
    old=next(r for r in before["clipped_isolation"]["details"] if r["net"]==row["net"])
    new=next(r for r in after["clipped_isolation"]["details"] if r["net"]==row["net"])
    assert old["native"]["physical_bypass_proved"]
    assert new["ok"] is True and not new["native"]["upper"]["reached_authority"]
    assert evidence.admit_changed_net(before,after,row["net"])["ok"]


@pytest.mark.parametrize("fault",["grouped","nonuniform","branch","noncardinal","stale"])
def test_scope_or_identity_ambiguity_refuses_without_mutation(tmp_path,fault):
    source=tmp_path/"board.kicad_pcb"; row=fixture(source,grouped=fault=="grouped",angle=37 if fault=="noncardinal" else 0)
    with patch("cec_current_topology.board_current_domains",return_value=row["domains"]):
        report=evidence.replay(source,board_hint="explicit-fixture")
    board=pcbnew.LoadBoard(str(source)); original=source.read_bytes()
    if fault=="nonuniform":
        next(t for t in board.GetTracks() if repair._uuid(t) in row["removed"]).SetWidth(200000)
    if fault=="branch":
        branch=pcbnew.PCB_TRACK(board); branch.SetNet(board.FindNet(row["net"])); branch.SetLayer(pcbnew.F_Cu)
        branch.SetWidth(250000); branch.SetStart(pcbnew.VECTOR2I_MM(15,28)); branch.SetEnd(pcbnew.VECTOR2I_MM(13,28)); board.Add(branch)
    if fault=="stale":
        report["identity_stable"]=False
    with pytest.raises(repair.Refusal):
        selected=repair._select(board,report,row["net"],time.monotonic()+20)
        list(repair._paths(board,selected,200000,time.monotonic()+20,64))
    assert source.read_bytes()==original


def test_exact_capsule_containment_does_not_skip_parallel_crossing_or_longer_legs():
    board=pcbnew.BOARD(); track=pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I(0,0)); track.SetEnd(pcbnew.VECTOR2I(1000,0)); track.SetWidth(100)
    assert repair._covered((0,0),(900,0),100,[track])==repair._uuid(track)
    for a,b,width in [((0,1),(900,1),100),((0,0),(1001,0),100),((500,-100),(500,100),100),((0,0),(900,0),101)]:
        assert repair._covered(a,b,width,[track]) is None


@pytest.mark.parametrize("kind",["caller","saved","external","missing_external","prefix"])
def test_frozen_ownership_has_no_implicit_locked_branch_waiver(tmp_path,monkeypatch,kind):
    source=tmp_path/"board.kicad_pcb"; row=fixture(source)
    immutable=[row["net"]] if kind=="caller" else []
    if kind in ("saved","external"):
        state=source.with_suffix(".pourfirst-state.json") if kind=="saved" else tmp_path/"enclosing.json"
        state.write_text(json.dumps({"frozen_nets":[row["net"]]}))
        if kind=="external": monkeypatch.setenv("CEC_POURFIRST_STATE",str(state))
    if kind=="missing_external": monkeypatch.setenv("CEC_POURFIRST_STATE",str(tmp_path/"absent.json"))
    if kind=="prefix": source.with_suffix(".authored-prefix.json").write_text("{}")
    with pytest.raises((repair.Refusal,ValueError)):
        repair._ownership(source,row["net"],immutable)


@pytest.mark.parametrize("mutation",["force_zone","source_pad","retained_track","settings","sidecar","ledger"])
def test_saved_delta_receipt_rejects_any_unowned_change(tmp_path,mutation):
    source=tmp_path/"board.kicad_pcb"; row=fixture(source)
    board,_,selection,plan=construct(source,row)
    candidate=repair._copy(source,tmp_path/"candidate")
    receipt=dict(selection,added=plan["added"],retained_legs=plan["retained_legs"],path_nm=plan["path_nm"],
                 source_family=repair._family(source,"explicit-fixture"),source_sha256=force._hash(source))
    if mutation=="force_zone": next(iter(board.Zones())).SetLocalClearance(300000)
    if mutation=="source_pad":
        next(p for fp in board.GetFootprints() for p in fp.Pads() if repair._uuid(p)==selection["source_pad"]["uuid"]).SetSize(pcbnew.VECTOR2I_MM(4,1))
    if mutation=="retained_track": next(t for t in board.GetTracks() if repair._uuid(t)==row["spine"]).SetLocked(False)
    if mutation=="settings":
        props=board.GetProperties(); props["unexpected"]="changed"; board.SetProperties(props)
    if mutation=="sidecar": candidate.with_suffix(".kicad_prl").write_text("{}")
    if mutation=="ledger": receipt["added"]=receipt["added"][:-1]
    pcbnew.SaveBoard(str(candidate),board,True)
    result=repair.preservation(source,candidate,receipt,board_hint="explicit-fixture")
    assert not result["ok"],result


def test_deadline_exhaustion_precedes_native_branch_work(tmp_path):
    source=tmp_path/"board.kicad_pcb"; row=fixture(source)
    board,report,selection=select(source,row)
    before={repair._uuid(t) for t in board.GetTracks()}
    with pytest.raises(repair.Refusal):
        repair._construct(board,selection,200000,time.monotonic()-1,64)
    assert {repair._uuid(t) for t in board.GetTracks()}==before


def test_unknown_separation_never_constructs_and_search_stays_bounded(tmp_path):
    source=tmp_path/"board.kicad_pcb"; row=fixture(source)
    board,_,selection=select(source,row)
    before={repair._uuid(t) for t in board.GetTracks()}
    with patch("cec_kelvin_force_separation.audit_path",return_value={"ok":None,"complete":False}):
        plan=repair._construct(board,selection,200000,time.monotonic()+20,3)
    assert not plan["constructed"] and len(plan["attempts"])<=3
    assert {repair._uuid(t) for t in board.GetTracks()}==before


@pytest.mark.parametrize("metric_ok",[True,False])
def test_worker_saved_native_admission_and_metrics_gate(tmp_path,metric_ok):
    source=tmp_path/"board.kicad_pcb"; row=fixture(source)
    original=source.read_bytes(); directory=tmp_path/"operation"; directory.mkdir()
    with patch("cec_current_topology.board_current_domains",return_value=row["domains"]), \
         patch("cec_score.score",return_value={"bounded_test_metric":0}), \
         patch("cec_stage_admission.evaluate",return_value={"accepted":metric_ok}):
        result=repair._worker(source,directory,row["net"],board_hint="explicit-fixture",immutable_nets=[])
    assert result["accepted"] is metric_ok,result
    assert result["preservation"]["ok"] and result["scoped_kelvin"]["ok"]
    assert result["exact_refill"]["stable"]
    assert source.read_bytes()==original and result["source_unchanged"]
    assert not result["release_authority"] and not result["full_kelvin_qualification"]


def test_output_alias_cannot_target_source_or_authority_tree(tmp_path):
    source=tmp_path/"board.kicad_pcb"; row=fixture(source)
    original=source.read_bytes()
    with pytest.raises(ValueError):
        repair.propose(source,tmp_path,row["net"],board_hint="explicit-fixture",immutable_nets=[])
    assert source.read_bytes()==original


def test_worker_unsupported_boundary_unknown_reports_improvement_but_refuses(tmp_path):
    source=tmp_path/"board.kicad_pcb"
    row=fixture(source,boundary=True,source_shape=pcbnew.PAD_SHAPE_OVAL)
    directory=tmp_path/"operation"; directory.mkdir()
    with patch("cec_current_topology.board_current_domains",return_value=row["domains"]), \
         patch("cec_score.score",return_value={}), \
         patch("cec_stage_admission.evaluate",return_value={"accepted":True}):
        result=repair._worker(source,directory,row["net"],board_hint="explicit-fixture",immutable_nets=[])
    assert result["geometric_improvement"] and not result["accepted"],result
    assert not result["changed"] and result["candidate_changed"]
    assert result["preservation"]["ok"] and not result["scoped_kelvin"]["ok"]


@pytest.mark.parametrize("drift",["source","candidate","code","environment"])
def test_lifecycle_drift_revokes_proposal(tmp_path,monkeypatch,drift):
    source=tmp_path/"board.kicad_pcb"; row=fixture(source)
    directory=tmp_path/"operation"; directory.mkdir()
    real_replay=evidence.replay
    def replay(path,**kwargs):
        result=real_replay(path,**kwargs)
        if Path(path)!=source:
            if drift=="source": source.with_suffix(".kicad_prl").write_text('{"external_change":true}')
            if drift=="candidate": Path(path).with_suffix(".kicad_prl").write_text('{"external_change":true}')
            if drift=="environment": monkeypatch.setenv("CEC_BRANCH_TEST_POLICY","changed")
        return result
    counter=[0]
    real_identity=force._code_identity
    def identity():
        counter[0]+=1
        if drift=="code": return {"controlled_test_identity":"old" if counter[0]<=3 else "new"}
        return real_identity()
    with patch("cec_current_topology.board_current_domains",return_value=row["domains"]), \
         patch("cec_score.score",return_value={}), \
         patch("cec_stage_admission.evaluate",return_value={"accepted":True}), \
         patch.object(evidence,"replay",side_effect=replay), patch.object(force,"_code_identity",side_effect=identity):
        result=repair._worker(source,directory,row["net"],board_hint="explicit-fixture",immutable_nets=[])
    assert not result["accepted"] and not result["changed"],result
    assert result["reason"] in ("concurrent_candidate_family_change","concurrent_source_or_code_change"),result


def test_receipt_path_cannot_omit_a_serialized_new_leg(tmp_path):
    source=tmp_path/"board.kicad_pcb"; row=fixture(source)
    board,_,selection,plan=construct(source,row)
    candidate=repair._copy(source,tmp_path/"candidate"); pcbnew.SaveBoard(str(candidate),board,True)
    receipt=dict(selection,added=plan["added"],retained_legs=plan["retained_legs"],
                 path_nm=[plan["path_nm"][0],plan["path_nm"][-1]],
                 source_family=repair._family(source,"explicit-fixture"),source_sha256=force._hash(source))
    result=repair.preservation(source,candidate,receipt,board_hint="explicit-fixture")
    assert not result["ok"] and "saved_additions_do_not_exactly_cover_declared_branch_chain" in result["errors"]


@pytest.mark.parametrize("kind",["symlink","hardlink"])
def test_worker_receipt_temporary_alias_cannot_overwrite_source(tmp_path,kind):
    source=tmp_path/"board.kicad_pcb"; row=fixture(source)
    original=source.read_bytes(); directory=tmp_path/"operation"; directory.mkdir()
    temporary=directory/("receipt.json.tmp-"+str(os.getpid()))
    if kind=="symlink": temporary.symlink_to(source)
    else: temporary.hardlink_to(source)
    with pytest.raises(ValueError):
        repair._worker(source,directory,row["net"],board_hint="explicit-fixture",immutable_nets=[])
    assert source.read_bytes()==original


def test_supervisor_timeout_is_not_success_or_a_retry(tmp_path):
    import cec_operation_budget as budget
    source=tmp_path/"board.kicad_pcb"; row=fixture(source)
    original=source.read_bytes()
    failure=budget.OperationFailure(dict(operation="kelvin_branch_repair",status="operation_budget_exhausted",
                                         directory=str(tmp_path/"operation")))
    with patch.object(budget,"run",side_effect=failure) as run:
        result=repair.propose(source,tmp_path/"operation",row["net"],board_hint="explicit-fixture",immutable_nets=[])
    assert run.call_count==1 and not result["accepted"] and result["retryable"] is False
    assert source.read_bytes()==original


@pytest.mark.parametrize("fault",["missing_source_sha","wrong_source_sha","missing_retained_leg"])
def test_source_and_retained_spine_receipt_fields_are_mandatory(tmp_path,fault):
    source=tmp_path/"board.kicad_pcb"; row=fixture(source)
    board,_,selection,plan=construct(source,row)
    candidate=repair._copy(source,tmp_path/"candidate"); pcbnew.SaveBoard(str(candidate),board,True)
    receipt=dict(selection,added=plan["added"],retained_legs=plan["retained_legs"],path_nm=plan["path_nm"],
                 source_family=repair._family(source,"explicit-fixture"),source_sha256=force._hash(source))
    if fault=="missing_source_sha": del receipt["source_sha256"]
    if fault=="wrong_source_sha": receipt["source_sha256"]="0"*64
    if fault=="missing_retained_leg": receipt["retained_legs"]=[]
    assert not repair.preservation(source,candidate,receipt,board_hint="explicit-fixture")["ok"]


def test_native_foreign_obstacle_at_target_refuses_every_bounded_path(tmp_path):
    source=tmp_path/"board.kicad_pcb"; row=fixture(source)
    board,_,selection=select(source,row)
    obstacle=next(p for fp in board.GetFootprints() if fp.GetReference()=="OBSTACLE" for p in fp.Pads())
    obstacle.SetPosition(pcbnew.VECTOR2I(*selection["points_nm"][-1]))
    original_ids={repair._uuid(t) for t in board.GetTracks()}
    plan=repair._construct(board,selection,200000,time.monotonic()+20,8)
    assert not plan["constructed"] and len(plan["attempts"])<=8
    assert {repair._uuid(t) for t in board.GetTracks()}==original_ids
