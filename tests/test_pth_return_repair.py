"""Native saved-family return repairs; no product/refdes placement rules."""
import copy
import json
import os
import time
from unittest.mock import patch

import pcbnew
import pytest

import cec_pth_return_repair as repair
import cec_pth_pair_returns as returns
import cec_zone_fill


def fixture(path, *, angle=0, translate=(0,0), renamed=False,
            ground_dimensions=None, ground_clearance=.2):
    import cec_ground_plane
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    props=board.GetProperties();props["CEC_FAB_PROFILE"]="jlcpcb_6l_pofv_signal";board.SetProperties(props)
    names=("/CAN_H_OTHER","/CAN_L_OTHER") if renamed else ("/CAN_H","/CAN_L")
    nets={}
    for name in (*names,"GND","/UNCHANGED_POWER"):
        info=pcbnew.NETINFO_ITEM(board,name);board.Add(info);nets[name]=info
    fps={}
    def pad(ref,number,net,point,pth=False):
        if ref not in fps:
            fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetFPID(pcbnew.LIB_ID("Fixture","Native"))
            board.Add(fp);fps[ref]=fp
        item=pcbnew.PAD(fps[ref]);item.SetNumber(number);item.SetNet(nets[net])
        item.SetAttribute(pcbnew.PAD_ATTRIB_PTH if pth else pcbnew.PAD_ATTRIB_SMD)
        item.SetShape(pcbnew.PAD_SHAPE_CIRCLE if pth else pcbnew.PAD_SHAPE_RECT)
        item.SetLayerSet(pcbnew.PAD.PTHMask() if pth else pcbnew.PAD.SMDMask())
        item.SetSize(pcbnew.VECTOR2I_MM(1.5,1.5) if pth else pcbnew.VECTOR2I_MM(.5,.5))
        if pth:item.SetDrillSize(pcbnew.VECTOR2I_MM(.8,.8))
        item.SetPosition(pcbnew.VECTOR2I_MM(*point));fps[ref].Add(item)
        return item
    pad("SOURCE_A","s",names[0],(5,8));pad("SOURCE_B","s",names[1],(5,8.5))
    pad("PLATED_DEST","a",names[0],(12,8),True);pad("PLATED_DEST","b",names[1],(12,10.54),True)
    pad("POWER_TERMINAL","p","/UNCHANGED_POWER",(16,16))
    pad("GROUND_TERMINAL","g","GND",(2,3.5),True)
    for net,points in ((names[0],[(5,8),(12,8)]),
                       (names[1],[(5,8.5),(7,10.5),(11.96,10.5),(12,10.54)])):
        for a,b in zip(points,points[1:]):
            track=pcbnew.PCB_TRACK(board);track.SetNet(nets[net]);track.SetLayer(pcbnew.F_Cu)
            track.SetWidth(250000);track.SetLocked(True)
            track.SetStart(pcbnew.VECTOR2I_MM(*a));track.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(track)
    ground=pcbnew.PCB_VIA(board);ground.SetViaType(pcbnew.VIATYPE_THROUGH)
    ground.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    gd,gh=ground_dimensions or (.6,.3)
    ground.SetWidth(round(gd*1e6));ground.SetDrill(round(gh*1e6))
    ground.SetPosition(pcbnew.VECTOR2I_MM(2,2));ground.SetNet(nets["GND"]);board.Add(ground)
    zone=pcbnew.ZONE(board);zone.SetNet(nets["/UNCHANGED_POWER"]);zone.SetLayer(pcbnew.F_Cu)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL);zone.SetLocalClearance(200000)
    zone.SetMinThickness(50000);zone.Outline().NewOutline()
    for xy in ((15,15),(18,15),(18,18),(15,18)):
        zone.Outline().Append(*pcbnew.VECTOR2I_MM(*xy))
    board.Add(zone)
    for a,b in (((0,0),(20,0)),((20,0),(20,20)),((20,20),(0,20)),((0,20),(0,0))):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)
    origin=pcbnew.VECTOR2I(0,0);rotation=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T);delta=pcbnew.VECTOR2I(*translate)
    for index,fp in enumerate(board.GetFootprints()):
        if renamed:fp.SetReference("RENAMED_"+str(index))
        fp.Rotate(origin,rotation);fp.SetPosition(fp.GetPosition()+delta)
    for item in [*board.GetTracks(),*board.Zones(),*board.GetDrawings()]:
        item.Rotate(origin,rotation);item.Move(delta)
    classes=[
        {"name":"Default","clearance":.2,"track_width":.25,"via_diameter":.6,"via_drill":.3},
        {"name":"CAN","clearance":.2,"diff_pair_width":.25,"diff_pair_gap":.25,"via_diameter":.6,"via_drill":.3}]
    if ground_dimensions:
        classes.append(dict(name="RenamedGroundAuthority",clearance=ground_clearance,
            track_width=.5,via_diameter=gd,via_drill=gh))
    path.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings":{"classes":classes,
        "netclass_assignments":{"GND":["RenamedGroundAuthority"]}if ground_dimensions else{}}}))
    pcbnew.SaveBoard(str(path),board,True)
    report=cec_ground_plane.fill_board(board,board_path=str(path));assert report["ok"],report
    cec_zone_fill.fill_with_report(board);pcbnew.SaveBoard(str(path),board,True)
    return names


def construct(path,directory):
    board=pcbnew.LoadBoard(str(path))
    selection,before=repair._select(board,path,"/CAN_H",2048,time.monotonic()+30)
    candidate=repair.family._copy(path,directory)
    board=pcbnew.LoadBoard(str(candidate));old={repair._uuid(t)for t in board.GetTracks()}
    report=returns.synthesize(board,selection["pair"])
    assert report["ok"] and report["added_count"],report
    added=[repair._via(t,board)for t in board.GetTracks()if repair._uuid(t)not in old]
    ledger=dict(source_family=repair.family._family(path,"fixture"),source_sha256=repair.force._hash(path),
                selection=selection,added_vias=added)
    pcbnew.SaveBoard(str(candidate),board,True)
    return board,candidate,ledger,before


@pytest.mark.parametrize("angle,translation,renamed",[(0,(0,0),False),(90,(30_000_000,0),True),
                                                     (180,(30_000_000,30_000_000),True)])
def test_native_pair_selection_and_existing_constructor_generalize(tmp_path,angle,translation,renamed):
    source=tmp_path/"board.kicad_pcb";names=fixture(source,angle=angle,translate=translation,renamed=renamed)
    saved=source.read_bytes();board=pcbnew.LoadBoard(str(source))
    selected,before=repair._select(board,source,names[1],160,time.monotonic()+30)
    assert {selected["pair"]["p"],selected["pair"]["n"]}==set(names)
    assert selected["constructor_site_upper_bound"]==160
    report=returns.synthesize(board,selected["pair"])
    assert report["ok"] and report["added_count"]>0,report
    added=[uid for row in report["terminals"]for uid in row["added"]]
    cec_zone_fill.fill_with_report(board)
    contacts=repair._saved_contacts(board,selected,added,time.monotonic()+10)
    assert contacts["ok"]
    network=contacts["retained_ground_network"]
    assert network["complete"] and network["native_queries"]==len(added)
    assert all(row["retained_terminals"]for row in network["witnesses"])
    assert source.read_bytes()==saved


def test_worker_final_saved_native_pair_and_admission(tmp_path):
    source=tmp_path/"board.kicad_pcb";fixture(source)
    saved=source.read_bytes();directory=tmp_path/"proposal";directory.mkdir()
    with patch("cec_score.score",return_value={"bounded_fixture_metric":0}):
        result=repair._worker(source,directory,"/CAN_H",board_hint="fixture",immutable_nets=[])
    assert result["accepted"],result
    assert result["preservation"]["ok"] and result["saved_return_contacts"]["ok"]
    assert result["saved_return_contacts"]["retained_ground_network"]["ok"]
    assert result["pair_admission"]["after"]["reference_coverage_pct"]==100
    assert result["candidate_family_unchanged"] and result["source_unchanged"] and result["code_unchanged"]
    assert result["kelvin_admission"]["checked_legs"]==0
    assert not result["release_authority"] and source.read_bytes()==saved


@pytest.mark.parametrize("fault",["track","pad","power_fill","ground_definition","sidecar",
                                  "settings","missing_uuid","extra_uuid","wrong_geometry","wrong_source"])
def test_exact_saved_delta_preservation_refuses_unowned_changes(tmp_path,fault):
    source=tmp_path/"board.kicad_pcb";fixture(source)
    board,candidate,ledger,_=construct(source,tmp_path/"candidate")
    assert repair.preservation(source,candidate,ledger,board_hint="fixture")["ok"]
    if fault=="track":
        next(t for t in board.GetTracks()if t.GetClass()=="PCB_TRACK").SetLocked(False)
    elif fault=="pad":
        next(p for fp in board.GetFootprints()for p in fp.Pads()).Move(pcbnew.VECTOR2I(1,0))
    elif fault=="power_fill":
        zone=next(z for z in board.Zones()if z.GetNetname()!="GND")
        zone.UnFill()
    elif fault=="ground_definition":
        next(z for z in board.Zones()if z.GetNetname()=="GND").SetLocalClearance(500000)
    elif fault=="sidecar":candidate.with_suffix(".kicad_pro").write_text("{}")
    elif fault=="settings":
        props=board.GetProperties();props["ILLEGAL_CHANGE"]="1";board.SetProperties(props)
    elif fault=="missing_uuid":ledger["added_vias"]=ledger["added_vias"][:-1]
    elif fault=="extra_uuid":ledger["added_vias"].append(copy.deepcopy(ledger["added_vias"][0]))
    elif fault=="wrong_geometry":ledger["added_vias"][0]["drill_nm"]+=1
    elif fault=="wrong_source":ledger["source_sha256"]="0"*64
    pcbnew.SaveBoard(str(candidate),board,True)
    result=repair.preservation(source,candidate,ledger,board_hint="fixture",allow_ground_refill=True)
    assert not result["ok"],result


def test_only_native_post_constructor_ground_fill_permission_is_separate(tmp_path):
    source=tmp_path/"board.kicad_pcb";fixture(source)
    board,candidate,ledger,_=construct(source,tmp_path/"candidate")
    for zone in board.Zones():
        if zone.GetNetname()=="GND":
            for layer in zone.GetLayerSet().CuStack():
                zone.SetFilledPolysList(layer,pcbnew.SHAPE_POLY_SET())
            zone.SetIsFilled(True)
    pcbnew.SaveBoard(str(candidate),board,True)
    assert not repair.preservation(source,candidate,ledger,board_hint="fixture")["ok"]
    allowed=repair.preservation(source,candidate,ledger,board_hint="fixture",allow_ground_refill=True)
    assert allowed["ok"] and allowed["derived_ground_fill_changes"]
    # Fill-only delta permission is not an admission or contact certificate.
    with pytest.raises(repair.Refusal,match="reference_contact_unproved"):
        repair._saved_contacts(board,ledger["selection"],[r["uuid"]for r in ledger["added_vias"]],time.monotonic()+10)


@pytest.mark.parametrize("fault",["wrong_net","moved","missing","blind","remote_terminal"])
def test_saved_actual_return_contact_is_required_not_preview_proximity(tmp_path,fault):
    source=tmp_path/"board.kicad_pcb";fixture(source)
    board,_,ledger,_=construct(source,tmp_path/"candidate")
    added=[r["uuid"]for r in ledger["added_vias"]]
    via=next(t for t in board.GetTracks()if repair._uuid(t)==added[0])
    if fault=="wrong_net":via.SetNet(board.FindNet("/UNCHANGED_POWER"))
    elif fault=="moved":via.SetPosition(pcbnew.VECTOR2I_MM(19,19))
    elif fault=="missing":board.Remove(via)
    elif fault=="blind":
        via.SetViaType(pcbnew.VIATYPE_BLIND);via.SetLayerPair(pcbnew.In1_Cu,pcbnew.In2_Cu)
    else:ledger["selection"]["terminals"][0]["position_nm"][0]+=1
    with pytest.raises(repair.Refusal):
        repair._saved_contacts(board,ledger["selection"],added,time.monotonic()+10)


def test_site_and_deadline_bounds_precede_constructor(tmp_path):
    source=tmp_path/"board.kicad_pcb";fixture(source)
    for kwargs,reason in ((dict(max_sites=159),"site_budget"),(dict(timeout_s=1e-9),"deadline")):
        directory=tmp_path/reason;directory.mkdir()
        with patch.object(returns,"synthesize") as construct_mock:
            result=repair._worker(source,directory,"/CAN_H",board_hint="fixture",immutable_nets=[],**kwargs)
        construct_mock.assert_not_called()
        assert not result["accepted"] and reason in result["reason"] and result["candidate"] is None


def test_native_constructor_site_call_bound_is_conservative(tmp_path):
    import cec_precision_route as precision
    source=tmp_path/"board.kicad_pcb";fixture(source);board=pcbnew.LoadBoard(str(source))
    selection,_=repair._select(board,source,"/CAN_H",160,time.monotonic()+30)
    native=precision.cec_fr._via_spot_clear
    with patch.object(precision.cec_fr,"_via_spot_clear",wraps=native) as calls:
        result=returns.synthesize(board,selection["pair"])
    assert result["ok"] and 0<calls.call_count<=selection["constructor_site_upper_bound"]


@pytest.mark.parametrize("fault",["wholeboard","pair","refill","contact","constructor"])
def test_independent_admission_failures_never_accept(tmp_path,fault):
    source=tmp_path/"board.kicad_pcb";fixture(source);saved=source.read_bytes()
    directory=tmp_path/"proposal";directory.mkdir()
    targets={
        "wholeboard":("cec_stage_admission.evaluate",dict(accepted=False,reasons=["new_drc"])),
        "pair":("cec_pth_return_repair._pair_admission",dict(ok=False)),
        "refill":("cec_zone_fill.fill_with_report",dict(stable=False)),
        "contact":("cec_pth_return_repair._saved_contacts",repair.Refusal("missing_actual_contact")),
        "constructor":("cec_pth_pair_returns.synthesize",dict(ok=False,added_count=0)),
    }
    target,value=targets[fault]
    with patch("cec_score.score",return_value={"bounded_fixture_metric":0}), \
         patch(target,**({"side_effect":value}if isinstance(value,Exception)else{"return_value":value})):
        result=repair._worker(source,directory,"/CAN_H",board_hint="fixture",immutable_nets=[])
    assert not result["accepted"] and not result["changed"] and not result["release_authority"],result
    assert source.read_bytes()==saved


@pytest.mark.parametrize("fault",["unknown","false_identity","missing_leg","wrong_native","departure","unbound"])
def test_nonempty_native_kelvin_inventory_cannot_be_laundered_by_can_scope(tmp_path,fault):
    import cec_force_sense_evidence as evidence
    from test_force_sense_evidence import fixture as sense_fixture
    source=tmp_path/"sense.kicad_pcb";domains=sense_fixture(source,overlap_at_cut=True)
    with patch("cec_current_topology.board_current_domains",return_value=domains):
        before=evidence.audit(pcbnew.LoadBoard(str(source)),board_hint="fixture")
    before["identity_stable"]=True
    assert repair._kelvin_admission(before,before)["checked_legs"]==2
    after=copy.deepcopy(before)
    row=after["clipped_isolation"]["details"][0]
    if fault=="unknown":row["native"]["ok"]=None
    elif fault=="false_identity":row["native"]["exact_linear_identity_verified"]=False
    elif fault=="missing_leg":after["clipped_isolation"]["details"].pop()
    elif fault=="wrong_native":row["native"]["source"]["uuid"]="not-the-declared-terminal"
    elif fault=="departure":after["inner_departure"]["details"][0]["ok"]=False
    elif fault=="unbound":after["identity_stable"]=False
    with pytest.raises(repair.Refusal):repair._kelvin_admission(before,after)


@pytest.mark.parametrize("kind",["GND","/CAN_H","saved_prefix","missing_external"])
def test_frozen_authority_never_becomes_addition_permission(tmp_path,monkeypatch,kind):
    source=tmp_path/"board.kicad_pcb";fixture(source);directory=tmp_path/"proposal";directory.mkdir()
    immutable=[kind]if kind in("GND","/CAN_H")else[]
    if kind=="saved_prefix":source.with_suffix(".power-prefix.json").write_text("{}")
    if kind=="missing_external":monkeypatch.setenv("CEC_POURFIRST_STATE",str(tmp_path/"missing.json"))
    with patch.object(returns,"synthesize")as constructor:
        result=repair._worker(source,directory,"/CAN_H",board_hint="fixture",immutable_nets=immutable)
    assert not result["accepted"] and result["candidate"]is None
    constructor.assert_not_called()


@pytest.mark.parametrize("kind",["symlink","hardlink"])
def test_receipt_alias_cannot_overwrite_source(tmp_path,kind):
    source=tmp_path/"board.kicad_pcb";fixture(source);saved=source.read_bytes()
    directory=tmp_path/"proposal";directory.mkdir()
    destination=directory/("receipt.json.tmp-"+str(os.getpid()))
    if kind=="symlink":destination.symlink_to(source)
    else:destination.hardlink_to(source)
    with pytest.raises(ValueError):
        repair._worker(source,directory,"/CAN_H",board_hint="fixture",immutable_nets=[])
    assert source.read_bytes()==saved


def test_supervisor_timeout_is_refusal_not_retry_or_no_path(tmp_path):
    import cec_operation_budget as budget
    source=tmp_path/"board.kicad_pcb";fixture(source);saved=source.read_bytes()
    failure=budget.OperationFailure(dict(operation="pth_pair_return_repair",status="operation_budget_exhausted",
                                         directory=str(tmp_path/"proposal")))
    with patch.object(budget,"run",side_effect=failure)as run:
        result=repair.propose(source,tmp_path/"proposal","/CAN_H",board_hint="fixture",immutable_nets=[])
    assert run.call_count==1 and not result["accepted"] and not result["retryable"] and not result["no_path_proof"]
    assert source.read_bytes()==saved


@pytest.mark.parametrize("drift",["source","candidate","environment","code"])
def test_late_epoch_drift_revokes_otherwise_successful_proposal(tmp_path,monkeypatch,drift):
    source=tmp_path/"board.kicad_pcb";fixture(source);directory=tmp_path/"proposal";directory.mkdir()
    original=repair._kelvin_admission;calls=0
    def mutate(before,after):
        nonlocal calls
        value=original(before,after);calls+=1
        if calls==2:
            if drift=="source":source.with_suffix(".kicad_prl").write_text("{}")
            elif drift=="candidate":(directory/"candidate"/source.name).with_suffix(".kicad_prl").write_text("{}")
            elif drift=="environment":monkeypatch.setenv("CEC_NATIVE_TEST_EPOCH_DRIFT","changed")
            else:monkeypatch.setattr(repair.force,"_code_identity",lambda:{"changed":"identity"})
        return value
    with patch("cec_score.score",return_value={"bounded_fixture_metric":0}), \
         patch.object(repair,"_kelvin_admission",side_effect=mutate):
        result=repair._worker(source,directory,"/CAN_H",board_hint="fixture",immutable_nets=[])
    assert calls==2 and not result["accepted"] and not result["changed"],result
    assert result["reason"]in("concurrent_source_or_code_change","concurrent_candidate_family_change")


def ground_fixture(*, mode="connected", angle=0, translation=(0,0), renamed=False):
    """Actual native fills, including separate islands under one zone UUID."""
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,"GND");board.Add(net)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference("RENAMED_RETURN"if renamed else"GROUND_PORT");board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNet(net);pad.SetNumber("renamed"if renamed else"1")
    smd=mode in("layer_isolation","terminal_inside_bore")
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD if smd else pcbnew.PAD_ATTRIB_PTH)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT if smd else pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetLayerSet(pcbnew.PAD.SMDMask()if smd else pcbnew.PAD.PTHMask())
    pad.SetSize(pcbnew.VECTOR2I_MM(.05,.05)if mode=="terminal_inside_bore"else pcbnew.VECTOR2I_MM(1.5,1.5))
    if not smd:pad.SetDrillSize(pcbnew.VECTOR2I_MM(.8,.8))
    pad.SetPosition(pcbnew.VECTOR2I_MM(12 if mode=="terminal_inside_bore"else 2,2));fp.Add(pad)
    via=pcbnew.PCB_VIA(board);via.SetNet(net);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetWidth(600000);via.SetDrill(300000)
    via.SetPosition(pcbnew.VECTOR2I_MM(20 if mode=="disconnected_barrel"else 12,2));board.Add(via)
    zone=pcbnew.ZONE(board);zone.SetNet(net)
    layer_set=pcbnew.LSET();layer_set.AddLayer(pcbnew.F_Cu);layer_set.AddLayer(pcbnew.In1_Cu)
    zone.SetLayerSet(layer_set);zone.Outline().NewOutline()
    for x,y in ((0,0),(14,0),(14,4),(0,4)):
        zone.Outline().Append(*pcbnew.VECTOR2I_MM(x,y))
    for layer in (pcbnew.F_Cu,pcbnew.In1_Cu):
        polygons=pcbnew.SHAPE_POLY_SET()
        intervals=([(0,4),(10,14)]if mode=="isolated_fill"else
                   [(0,4)]if mode=="layer_isolation"and layer==pcbnew.F_Cu else
                   [(10,14)]if mode=="layer_isolation"else [(0,14)])
        for lo,hi in intervals:
            polygons.NewOutline()
            for x,y in ((lo,0),(hi,0),(hi,4),(lo,4)):
                polygons.Append(*pcbnew.VECTOR2I_MM(x,y))
        zone.SetFilledPolysList(layer,polygons)
    zone.SetIsFilled(True);board.Add(zone)
    origin=pcbnew.VECTOR2I(0,0);rotation=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
    delta=pcbnew.VECTOR2I(*translation)
    fp.Rotate(origin,rotation);fp.SetPosition(fp.GetPosition()+delta)
    for item in(via,zone):item.Rotate(origin,rotation);item.Move(delta)
    selection=dict(retained_ground_terminals=repair._ground_terminals(board,time.monotonic()+10))
    return board,selection,[repair._uuid(via)],pad,via,zone


@pytest.mark.parametrize("angle,translation",[(0,(0,0)),(90,(-30_000_000,20_000_000)),
                                           (180,(30_000_000,-20_000_000)),(270,(10_000_000,10_000_000))])
def test_native_ground_network_positive_renamed_rotated_saved_epoch(tmp_path,angle,translation):
    board,selection,added,_,_,_=ground_fixture(angle=angle,translation=translation,renamed=True)
    candidate=tmp_path/"saved.kicad_pcb";pcbnew.SaveBoard(str(candidate),board,True)
    result=repair._ground_network(pcbnew.LoadBoard(str(candidate)),selection,added,time.monotonic()+10)
    assert result["ok"] and result["complete"] and result["native_queries"]==1
    assert result["witnesses"][0]["retained_terminals"]==selection["retained_ground_terminals"]
    assert len(result["inventory_uuids"])==3 and len(result["drill_inventory_uuids"])==2


@pytest.mark.parametrize("mode",["isolated_fill","disconnected_barrel","layer_isolation"])
def test_same_named_native_ground_fill_or_zone_uuid_does_not_certify_path(mode):
    board,selection,added,pad,via,zone=ground_fixture(mode=mode)
    # A real local filled-plane collision may exist despite no terminal path.
    if mode!="disconnected_barrel":
        assert zone.GetFilledPolysList(pcbnew.In1_Cu).Collide(via.GetEffectiveShape(pcbnew.In1_Cu),0)
    with pytest.raises(repair.Refusal,match="ground_terminal_path_unproved"):
        repair._ground_network(board,selection,added,time.monotonic()+10)


def test_named_ground_pad_wholly_inside_drill_is_not_physical_terminal():
    board,selection,added,_,_,_=ground_fixture(mode="terminal_inside_bore")
    with pytest.raises(repair.Refusal,match="physical_copper_unproved"):
        repair._ground_network(board,selection,added,time.monotonic()+10)


@pytest.mark.parametrize("fault",["partial_barrel","blind","offset_land","no_annulus","custom_pad",
                                  "multiface_smd","npth_ground","overlapping_bores","foreign_bore"])
def test_ground_native_path_requires_explicit_hole_and_layer_support(fault):
    board,selection,added,pad,via,_=ground_fixture()
    if fault=="partial_barrel":
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);layers.AddLayer(pcbnew.B_Cu)
        pad.SetLayerSet(layers)
    elif fault=="blind":
        via.SetViaType(pcbnew.VIATYPE_BLIND);via.SetLayerPair(pcbnew.F_Cu,pcbnew.In1_Cu)
    elif fault=="offset_land":pad.SetOffset(pcbnew.VECTOR2I_MM(2,0))
    elif fault=="no_annulus":via.SetWidth(via.GetDrillValue())
    elif fault=="custom_pad":pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    elif fault=="multiface_smd":
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetDrillSize(pcbnew.VECTOR2I(0,0))
    elif fault=="npth_ground":pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    elif fault=="overlapping_bores":via.SetPosition(pad.GetPosition())
    else:
        fp=pcbnew.FOOTPRINT(board);board.Add(fp)
        hole=pcbnew.PAD(fp);hole.SetNumber("mechanical");hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE);hole.SetSize(pcbnew.VECTOR2I_MM(1,1))
        hole.SetDrillSize(pcbnew.VECTOR2I_MM(1,1));hole.SetLayerSet(pcbnew.PAD.PTHMask())
        hole.SetPosition(pcbnew.VECTOR2I_MM(7,2));fp.Add(hole)
    with pytest.raises(repair.Refusal):
        repair._ground_network(board,selection,added,time.monotonic()+10)


@pytest.mark.parametrize("fault",["missing_terminal","moved_terminal","omitted_terminal","missing_fill",
                                  "duplicate_item","duplicate_added","unbound_added"])
def test_ground_native_complete_source_bound_inventory_is_mandatory(fault):
    board,selection,added,pad,via,zone=ground_fixture()
    if fault=="missing_terminal":pad.GetParentFootprint().Remove(pad)
    elif fault=="moved_terminal":pad.Move(pcbnew.VECTOR2I(1,0))
    elif fault=="omitted_terminal":selection["retained_ground_terminals"]=[]
    elif fault=="missing_fill":zone.UnFill()
    elif fault=="duplicate_item":board.Add(pcbnew.Cast_to_PCB_VIA(pcbnew.Cast_to_BOARD_ITEM(via.Clone())))
    elif fault=="duplicate_added":added.append(added[0])
    else:added=["not-a-retained-or-new-native-via"]
    with pytest.raises(repair.Refusal):
        repair._ground_network(board,selection,added,time.monotonic()+10)


@pytest.mark.parametrize("bound",["items","vertices","contacts","deadline","native_add","native_query"])
def test_ground_native_bounds_and_missing_evidence_are_unknown_not_admission(monkeypatch,bound):
    import cec_kelvin_copper_cut as cut
    board,selection,added,_,_,_=ground_fixture()
    deadline=time.monotonic()+10
    if bound=="items":monkeypatch.setattr(repair,"MAX_GROUND_ITEMS",2)
    elif bound=="vertices":monkeypatch.setattr(cut,"MAX_VERTICES",1)
    elif bound=="contacts":monkeypatch.setattr(cut,"MAX_CONTACTS",0)
    elif bound=="deadline":deadline=0
    elif bound=="native_add":monkeypatch.setattr(pcbnew.CONNECTIVITY_DATA,"Add",lambda *args:False)
    else:monkeypatch.setattr(pcbnew.CONNECTIVITY_DATA,"GetConnectedItems",lambda *args:[])
    with pytest.raises(repair.Refusal):
        repair._ground_network(board,selection,added,deadline)


def test_source_without_retained_ground_terminal_refuses_before_constructor(tmp_path):
    source=tmp_path/"board.kicad_pcb";fixture(source);board=pcbnew.LoadBoard(str(source))
    for fp in board.GetFootprints():
        for pad in list(fp.Pads()):
            if pad.GetNetname()=="GND":fp.Remove(pad)
    pcbnew.SaveBoard(str(source),board,True)
    directory=tmp_path/"proposal";directory.mkdir()
    with patch.object(returns,"synthesize")as constructor:
        result=repair._worker(source,directory,"/CAN_H",board_hint="fixture",immutable_nets=[])
    constructor.assert_not_called()
    assert not result["accepted"] and result["candidate"]is None
    assert result["reason"]=="complete_retained_physical_ground_terminal_inventory_required"


@pytest.mark.parametrize("angle,translated,renamed",[(0,(0,0),False),
    (90,(30_000_000,0),True),(180,(30_000_000,30_000_000),True)])
def test_ground_owned_vias_use_ground_class_not_signal_pair(tmp_path,angle,translated,renamed):
    import cec_constraints
    source=tmp_path/"board.kicad_pcb"
    names=fixture(source,angle=angle,translate=translated,renamed=renamed,ground_dimensions=(.9,.5))
    board=pcbnew.LoadBoard(str(source));old={repair._uuid(t)for t in board.GetTracks()}
    selection,_=repair._select(board,source,names[0],160,time.monotonic()+20)
    assert (selection["pair"]["via_diameter"],selection["pair"]["via_drill"])==(.6,.3)
    assert selection["ground_return_contract"]["netclass"]=="RenamedGroundAuthority"
    assert (selection["via_diameter_nm"],selection["via_drill_nm"])==(900000,500000)
    built=returns.synthesize(board,selection["pair"],deadline=time.monotonic()+20)
    assert built["ok"] and built["added_count"]==2,built
    added=[repair._uuid(t)for t in board.GetTracks()if repair._uuid(t)not in old]
    for t in board.GetTracks():
        if repair._uuid(t)in added:
            assert t.GetDrillValue()==500000
            assert {t.GetWidth(layer)for layer in board.GetEnabledLayers().CuStack()}=={900000}
    candidate=source.with_name("candidate.kicad_pcb")
    repair.family._copy(source,tmp_path/"saved")
    candidate=tmp_path/"saved"/source.name
    pcbnew.SaveBoard(str(candidate),board,True)
    saved=pcbnew.LoadBoard(str(candidate));cec_zone_fill.fill_with_report(saved)
    pcbnew.SaveBoard(str(candidate),saved,True);saved=pcbnew.LoadBoard(str(candidate))
    assert repair._saved_ground_geometry(saved,selection,added)["ok"]
    assert repair._saved_contacts(saved,selection,added,time.monotonic()+20)["ok"]
    conformance=cec_constraints._chk_netclass_geom(saved,str(candidate),{})
    assert conformance[0] is True,conformance


def test_ground_clearance_cannot_be_replaced_by_smaller_pair_clearance(tmp_path):
    source=tmp_path/"board.kicad_pcb";fixture(source,ground_dimensions=(.9,.5),ground_clearance=.6)
    board=pcbnew.LoadBoard(str(source));before={repair._uuid(t)for t in board.GetTracks()}
    selection,_=repair._select(board,source,"/CAN_H",160,time.monotonic()+20)
    assert selection["clearance_nm"]==600000
    native=returns.synthesize(board,selection["pair"],deadline=time.monotonic()+20)
    assert not native["ok"] and not native["added_count"]
    assert {repair._uuid(t)for t in board.GetTracks()}==before


@pytest.mark.parametrize("forged_contract",[False,True])
def test_receiving_ground_class_rejects_colluding_small_ledger_and_builder(tmp_path,forged_contract):
    source=tmp_path/"board.kicad_pcb";fixture(source,ground_dimensions=(.9,.5))
    board,candidate,ledger,_=construct(source,tmp_path/"candidate")
    added=[row["uuid"]for row in ledger["added_vias"]]
    for t in board.GetTracks():
        if repair._uuid(t)in added:t.SetWidth(600000);t.SetDrill(300000)
    ledger["added_vias"]=[repair._via(t,board)for t in board.GetTracks()if repair._uuid(t)in added]
    ledger["selection"].update(via_diameter_nm=600000,via_drill_nm=300000)
    pcbnew.SaveBoard(str(candidate),board,True)
    exact=pcbnew.LoadBoard(str(candidate))
    if forged_contract:
        fake=copy.deepcopy(ledger["selection"]["ground_return_contract"])
        fake.update(diameter_nm=600000,drill_nm=300000)
        ledger["selection"]["ground_return_contract"]=fake
        with patch.object(returns,"ground_return_contract",return_value=fake):
            with pytest.raises(repair.Refusal,match="independently_resolved_minima"):
                repair._saved_ground_geometry(exact,ledger["selection"],added)
    else:
        result=repair.preservation(source,candidate,ledger,board_hint="fixture")
        assert not result["ok"] and "saved_ground_netclass_geometry_unproved"in result["errors"]


def test_ground_class_must_be_recompiled_from_actual_saved_project(tmp_path):
    source=tmp_path/"board.kicad_pcb";fixture(source,ground_dimensions=(.9,.5))
    board,candidate,ledger,_=construct(source,tmp_path/"candidate")
    data=json.loads(candidate.with_suffix('.kicad_pro').read_text())
    next(row for row in data['net_settings']['classes']if row['name']=='RenamedGroundAuthority')['via_drill']=.55
    candidate.with_suffix('.kicad_pro').write_text(json.dumps(data))
    with pytest.raises(repair.Refusal,match="dimension_authority_changed"):
        repair._saved_ground_geometry(pcbnew.LoadBoard(str(candidate)),ledger['selection'],
                                     [row['uuid']for row in ledger['added_vias']])


def test_stricter_hole_rule_refuses_constructor_without_changing_reach_or_source(tmp_path):
    source=tmp_path/'board.kicad_pcb';fixture(source,ground_dimensions=(.9,.5))
    source.with_suffix('.kicad_dru').write_text(
        '(version 1)(rule "hole floor"(constraint hole_to_hole(min 1.1mm)))')
    before=source.read_bytes();board=pcbnew.LoadBoard(str(source))
    ids={repair._uuid(t)for t in board.GetTracks()}
    selected,_=repair._select(board,source,'/CAN_H',160,time.monotonic()+30)
    result=returns.synthesize(board,selected['pair'])
    assert not result['ok'] and result['added_count']==0
    assert result['site_guard_refusals']['ground_site_native_hole_spacing_refused']>0
    assert selected['return_reach_mm']==1.5
    assert ids=={repair._uuid(t)for t in board.GetTracks()}and source.read_bytes()==before


def test_receiving_native_site_guard_does_not_trust_builder_success(tmp_path):
    source=tmp_path/'board.kicad_pcb';fixture(source,ground_dimensions=(.9,.5))
    source.with_suffix('.kicad_dru').write_text(
        '(version 1)(rule "hole floor"(constraint hole_to_hole(min 1.1mm)))')
    # Deliberately bypass only the builder's site callback; selected authority
    # and saved geometry remain honest, so the receiver must find the defect.
    with patch.object(returns,'ground_site_guard',return_value=dict(ok=True)):
        board,candidate,ledger,_=construct(source,tmp_path/'candidate')
    cec_zone_fill.fill_with_report(board);pcbnew.SaveBoard(str(candidate),board,True)
    exact=pcbnew.LoadBoard(str(candidate))
    with pytest.raises(repair.Refusal,match='saved_ground_via_fabrication_site_refused'):
        repair._saved_contacts(exact,ledger['selection'],[row['uuid']for row in ledger['added_vias']],
                               time.monotonic()+10)
