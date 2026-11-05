"""Explicit load authority and conservative additive native supply geometry."""
from contextlib import contextmanager
import hashlib
import json
import os
import time
from pathlib import Path
from unittest import mock

import pcbnew
import pytest

import cec_current_topology as topology
import cec_distributed_supply as supply
import cec_fab_profile as fab
import cec_force_current as force


def fixture(tmp_path, *, name="/arbitrary/distribution", turn=0, count=3, layer=pcbnew.F_Cu):
    board = pcbnew.BOARD()
    board.SetFileName(str(tmp_path/"anonymous.kicad_pcb"))
    board.SetCopperLayerCount(6)
    props = board.GetProperties(); props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
    board.SetProperties(props)
    board.GetDesignSettings().m_TrackMinWidth = pcbnew.FromMM(.2)
    board.GetDesignSettings().m_MinClearance = pcbnew.FromMM(.2)
    info = pcbnew.NETINFO_ITEM(board, name); board.Add(info)
    def position(x, y):
        for _ in range(turn):
            x, y = 40-y, x
        return pcbnew.VECTOR2I_MM(x, y)
    for index in range(count):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference("LOAD_"+str(count-index))
        pad = pcbnew.PAD(fp); pad.SetNumber(str(index+1))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.5, 1.5)); pad.SetNet(info)
        layers = pcbnew.LSET(); layers.AddLayer(layer); pad.SetLayerSet(layers)
        pad.SetPosition(position(8+index*8, 20)); fp.Add(pad); board.Add(fp)
    for a, b in [((0,0),(40,0)),((40,0),(40,40)),((40,40),(0,40)),((0,40),(0,0))]:
        item = pcbnew.PCB_SHAPE(board); item.SetShape(pcbnew.SHAPE_T_SEGMENT)
        item.SetStart(pcbnew.VECTOR2I_MM(*a)); item.SetEnd(pcbnew.VECTOR2I_MM(*b))
        item.SetLayer(pcbnew.Edge_Cuts); board.Add(item)
    return board, name


def resolver(_net):
    return dict(name="Default", track_width=.2, clearance=.2)


@contextmanager
def authority(net, contract=None, *, domains=None):
    if contract is None:
        contract = dict(amps=.5, margin_included=False, geometry_margin=1.25, source="board_design_basis")
    with mock.patch("cec_synth_pipeline.spec_net_current_contract", side_effect=lambda hint, n: contract if n == net else None), \
         mock.patch.object(topology, "board_current_domains", return_value=domains or {}):
        yield contract


def run(board, net, **kwargs):
    return supply.construct(board, board_hint="arbitrary-bound-design", include_nets=[net],
                            netclass_resolver=resolver, timeout_s=5, **kwargs)


@pytest.mark.parametrize("turn,name,layer", [(0,"/arbitrary/A",pcbnew.F_Cu),
    (1,"/renamed/B",pcbnew.F_Cu),(2,"plain_unusual",pcbnew.B_Cu),(3,"/nested/nominal",pcbnew.B_Cu)])
def test_native_arbitrary_rotated_planar_completion_replays(tmp_path, turn, name, layer):
    board, net = fixture(tmp_path, name=name, turn=turn, layer=layer)
    with authority(net):
        result = run(board, net)
        assert result["stage_complete"], result
        assert result["joins"] == 2 and result["new_vias"] == result["neckdowns"] == 0
        assert len(result["after"][net]["planar_full_width_components"]) == 1
        assert result["whole_power_qualified"] is False and result["release_authority"] is False
        assert result['native_graph_cache']['accepted_join_invalidations'] == 2
        assert len({a['native_epoch'] for a in result['attempts'] if a['accepted']}) == 2
        for attempt in result['attempts']:
            assert supply.attempt_anchor_inventory(result, attempt) is not None
        assert all(item.GetClass() == "PCB_TRACK" and item.GetWidth() == 200000 for item in board.GetTracks())
        path = tmp_path/"replay.kicad_pcb"; pcbnew.SaveBoard(str(path), board)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        replay = run(pcbnew.LoadBoard(str(path)), net)
        assert replay["joins"] == 0 and replay["stage_complete"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize('turn,layer', [(0, pcbnew.F_Cu), (1, pcbnew.B_Cu)])
def test_rejected_pairs_reuse_only_unchanged_graph_and_share_epoch_evidence(tmp_path, turn, layer):
    board, net = fixture(tmp_path, count=4, turn=turn, layer=layer)
    before = [(str(p.m_Uuid.AsString()), p.GetNetCode(), list(p.GetPosition()))
        for fp in board.GetFootprints() for p in fp.Pads()]
    import cec_fr as fr
    with authority(net), mock.patch.object(supply, '_graph', wraps=supply._graph) as graphs, \
            mock.patch.object(fr, '_guarded_profiled_lastmile_legs', return_value=[]):
        result = run(board, net, max_attempts=12)
    assert len(result['attempts']) == 12 and result['joins'] == 0
    assert graphs.call_count == 3  # independent before, one search epoch, after
    assert result['native_graph_cache'] == dict(search_builds=1,
        unchanged_epoch_hits=11, accepted_join_invalidations=0)
    assert all('anchor_inventory' not in row for row in result['attempts'])
    assert len(result['anchor_inventory_epochs']) == 1
    assert all(supply.attempt_anchor_inventory(result, row)
        == result['anchor_inventory'][net] for row in result['attempts'])
    # Reconstruct the historical duplicated layout only to measure its size;
    # the new on-disk report retains every evidence row exactly once per epoch.
    legacy = dict(result, attempts=[dict(row,
        anchor_inventory=supply.attempt_anchor_inventory(result, row)) for row in result['attempts']])
    assert len(json.dumps(result)) < len(json.dumps(legacy)) / 2
    assert not list(board.GetTracks())
    assert before == [(str(p.m_Uuid.AsString()), p.GetNetCode(), list(p.GetPosition()))
        for fp in board.GetFootprints() for p in fp.Pads()]


def test_anchor_evidence_lookup_never_substitutes_latest_net_epoch():
    first, latest = {'marker': 'before'}, {'marker': 'after'}
    report = dict(anchor_inventory={'rail': latest}, anchor_inventory_epochs=[
        dict(id=0, net='rail', native_epoch=0, inventory=first),
        dict(id=1, net='rail', native_epoch=1, inventory=latest)])
    attempt = dict(net='rail', native_epoch=0, anchor_inventory_id=0)
    assert supply.attempt_anchor_inventory(report, attempt) == first
    assert supply.attempt_anchor_inventory({}, dict(anchor_inventory=first)) == first
    for fault in (dict(anchor_inventory_id=True), dict(anchor_inventory_id=2),
                  dict(native_epoch=1), dict(net='other')):
        with pytest.raises(ValueError):
            supply.attempt_anchor_inventory(report, dict(attempt, **fault))


@pytest.mark.parametrize("bad", [dict(amps=0),dict(amps=-2),dict(amps=True),dict(amps=float("nan")),
    dict(geometry_margin=.8),dict(margin_included="yes"),dict(source="inferred"),
    dict(margin_included=True, geometry_margin=1.25)])
def test_invalid_contract_never_falls_back_to_default(tmp_path, bad):
    board, net = fixture(tmp_path)
    contract = dict(amps=.5, margin_included=False, geometry_margin=1.25, source="board_design_basis", **{})
    contract.update(bad)
    with authority(net, contract):
        result = run(board, net)
    assert not result["stage_complete"] and result["refusals"][net]["retryable"] is False
    assert not list(board.GetTracks())


def test_missing_contract_refuses_but_eligible_partial_prefix_survives(tmp_path):
    board, net = fixture(tmp_path)
    board.Add(pcbnew.NETINFO_ITEM(board, "/unrated/rail"))
    with authority(net):
        result = supply.construct(board, board_hint="design", include_nets=[net,"/unrated/rail"],
            netclass_resolver=resolver, timeout_s=5)
    assert result["joins"] == 2 and result["completed_nets"] == [net]
    assert result["stage_complete"] is False
    assert result["refusals"]["/unrated/rail"]["reason"] == "current_contract_missing"


@pytest.mark.parametrize("domain", [{"complete":True},{"complete":False}])
def test_any_aggregate_domain_keeps_existing_owner(tmp_path, domain):
    board, net = fixture(tmp_path)
    with authority(net, domains={net:domain}):
        result = run(board, net)
    assert result["refusals"][net]["reason"] == "aggregate_current_domain_owned"
    assert result["created_uuids"] == []


def test_aggregate_twenty_amp_width_is_not_demoted_or_divided(tmp_path):
    board, net = fixture(tmp_path)
    with authority(net, dict(amps=20.,margin_included=False,geometry_margin=1.25,source="board_design_basis")):
        result = topology.distributed_supply_contracts(board, "design", include_nets=[net], netclass_resolver=resolver)
    contract = result["contracts"][net]
    expected = fab.ipc2221_required_width_mm(20, "F.Cu", profile_name=contract["profile"], rise_c=30, margin=1.25)
    assert contract["required_by_layer_mm"]["F.Cu"] == pytest.approx(expected)
    assert contract["branch_sharing_assumed"] is False


def test_included_component_margin_not_applied_again(tmp_path):
    board, net = fixture(tmp_path)
    with authority(net, dict(amps=.2048376,margin_included=True,geometry_margin=1.,source="component_power_budget")):
        result = topology.distributed_supply_contracts(board, "design", include_nets=[net], netclass_resolver=resolver)
    assert result["contracts"][net]["current_authority"]["amps"] == .2048376
    assert result["contracts"][net]["required_by_layer_mm"]["F.Cu"] == .2


@pytest.mark.parametrize('turn',range(4))
def test_actual_current_authority_not_default_class_or_net_name_unlocks_profile_power_role(tmp_path,turn):
    board,net=fixture(tmp_path,name='/unrelated/renamed_supply',turn=turn)
    import cec_fr as fr
    before=[(force._uid(p),list(p.GetPosition()),p.GetNetCode()) for fp in board.GetFootprints() for p in fp.Pads()]
    assert 'In3.Cu' not in {fab.COPPER_LAYER_IDS[l] for l in fr._lastmile_route_layers(
        board,net_name=net,spec=resolver(net),exclude_front=False)}
    with authority(net,dict(amps=.2048376,margin_included=True,geometry_margin=1.,source='component_power_budget')):
        result=topology.distributed_supply_contracts(board,'declared',include_nets=[net],netclass_resolver=resolver)
    row=result['contracts'][net]
    assert set(row['routing_layers'])=={'F.Cu','In2.Cu','In3.Cu','B.Cu'}
    assert row['current_authority']['amps']==.2048376 and row['required_by_layer_mm']['In3.Cu']==.2
    assert not row['terminal_barrel_zone_rating_qualified'] and not row['branch_sharing_assumed']
    assert before==[(force._uid(p),list(p.GetPosition()),p.GetNetCode()) for fp in board.GetFootprints() for p in fp.Pads()]


def test_declared_supply_does_not_acquire_a_board_scale_power_plane(tmp_path):
    board,net=fixture(tmp_path)
    foreign=pcbnew.NETINFO_ITEM(board,'existing_plane');board.Add(foreign)
    zone=pcbnew.ZONE(board);zone.SetNet(foreign);zone.SetLayer(pcbnew.In3_Cu);zone.Outline().NewOutline()
    for x,y in [(0,0),(40,0),(40,40),(0,40)]:zone.Outline().Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
    board.Add(zone)
    with authority(net):
        result=topology.distributed_supply_contracts(board,'declared',include_nets=[net],netclass_resolver=resolver)
    assert set(result['contracts'][net]['routing_layers'])=={'F.Cu','In2.Cu','B.Cu'}


def test_coupled_measurement_and_unknown_nets_do_not_get_power_layer_from_an_invented_budget(tmp_path):
    board,net=fixture(tmp_path,name='/USB_D_P')
    board.Add(pcbnew.NETINFO_ITEM(board,'/USB_D_N'))
    with authority(net):
        result=topology.distributed_supply_contracts(board,'declared',include_nets=[net],netclass_resolver=resolver)
    assert net not in result['contracts'] and result['refusals'][net]['reason']=='specialized_topology_owned'


def test_plated_terminal_can_join_one_face_without_barrel_capacity(tmp_path):
    board, net = fixture(tmp_path)
    pad = next(iter(next(iter(board.GetFootprints())).Pads()))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH); pad.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
    layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); layers.AddLayer(pcbnew.B_Cu); pad.SetLayerSet(layers)
    with authority(net): result = run(board, net)
    assert result["joins"] == 2 and result["stage_complete"], result
    assert result["after"][net]["single_surface_layer_id"] == pcbnew.F_Cu
    assert not result["after"][net]["terminal_barrel_zone_rating_qualified"]
    assert all(t.GetLayer() == pcbnew.F_Cu for t in board.GetTracks())
    assert supply._saved_anchor_contacts(board, result)["ok"]
    assert pad.HasHole() and pad.IsOnLayer(pcbnew.B_Cu)  # source PAD unchanged


def test_plated_vertex_cannot_bridge_two_surface_only_paths(tmp_path):
    board, net = fixture(tmp_path)
    pads = sorted(supply._pads(board, net), key=lambda p:p.GetPosition().x)
    middle = pads[1]; middle.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    middle.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
    layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); layers.AddLayer(pcbnew.B_Cu)
    middle.SetLayerSet(layers)
    back = pcbnew.LSET(); back.AddLayer(pcbnew.B_Cu); pads[2].SetLayerSet(back)
    with authority(net): result = run(board, net)
    assert result["joins"] == 0
    assert result["after"][net]["planar_full_width_components"] is None
    assert result["refusals"][net]["reason"] == "unsupported_nonplanar_terminal_capacity"


@pytest.mark.parametrize("attribute,drill", [(pcbnew.PAD_ATTRIB_NPTH,.4),
    (pcbnew.PAD_ATTRIB_PTH,2.)])
def test_npth_or_clipped_drill_never_becomes_surface_vertex(tmp_path, attribute, drill):
    board, net = fixture(tmp_path)
    pad = supply._pads(board, net)[0]; pad.SetAttribute(attribute)
    pad.SetDrillSize(pcbnew.VECTOR2I_MM(drill,drill))
    layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); layers.AddLayer(pcbnew.B_Cu)
    pad.SetLayerSet(layers)
    with authority(net):
        contract = topology.distributed_supply_contracts(board, "design", include_nets=[net],
            netclass_resolver=resolver)["contracts"][net]
        assert supply._surface_layer(board,[pad],contract) is None
        result = run(board, net)
    if attribute == pcbnew.PAD_ATTRIB_NPTH:
        # KiCad removes the net assignment when a pad becomes NPTH. The
        # remaining real terminals can join, but NPTH never gets a witness.
        assert all(anchor["uuid"] != supply._uid(pad) for attempt in result["attempts"]
                   for anchor in (attempt["start"],attempt["end"]))
    else:
        assert result["joins"] == 0 and not result["stage_complete"]
        assert result["after"][net]["single_surface_layer_id"] is None


def test_single_face_projection_preserves_native_geometry_and_source_uuid(tmp_path):
    board, net = fixture(tmp_path)
    pads = supply._pads(board, net)
    pad = pads[0]; pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
    layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); layers.AddLayer(pcbnew.B_Cu)
    pad.SetLayerSet(layers)
    source_ids = [supply._uid(p) for p in pads]
    copies, originals = supply._face_copies(pads, pcbnew.F_Cu)
    assert set(originals.values()) == set(source_ids)
    assert all(set(p.GetLayerSet().CuStack()) == {pcbnew.F_Cu} for p in copies)
    assert [supply._uid(p) for p in supply._pads(board, net)] == source_ids
    assert pad.HasHole() and pad.IsOnLayer(pcbnew.B_Cu)


def test_surface_contact_replay_rejects_hole_and_changed_width(tmp_path):
    board, net = fixture(tmp_path)
    pad = supply._pads(board, net)[0]; pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
    layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); pad.SetLayerSet(layers)
    with authority(net):
        contract = topology.distributed_supply_contracts(board, "design", include_nets=[net],
            netclass_resolver=resolver)["contracts"][net]
    anchor = dict(kind="pad_surface",uuid=supply._uid(pad),layer=pcbnew.F_Cu,
        point_nm=list(pad.GetPosition()))
    assert not supply._anchor_contact(board,anchor,contract)["ok"]
    anchor.update(kind="pad_cap", contact_width_nm=199999,
        contact_point_nm=[pad.GetPosition().x+400000,pad.GetPosition().y])
    assert supply._anchor_contact(board,anchor,contract)["reason"] == "full_current_cap_width_changed"


def test_existing_via_path_is_read_only_not_planar_rating(tmp_path):
    board, net = fixture(tmp_path, count=2)
    pads = sorted(supply._pads(board, net), key=lambda p:p.GetPosition().x)
    layers = pcbnew.LSET(); layers.AddLayer(pcbnew.B_Cu); pads[1].SetLayerSet(layers)
    for start,end,layer in [((8,20),(12,20),pcbnew.F_Cu),((12,20),(16,20),pcbnew.B_Cu)]:
        track = pcbnew.PCB_TRACK(board); track.SetNetCode(pads[0].GetNetCode()); track.SetWidth(200000)
        track.SetLayer(layer); track.SetStart(pcbnew.VECTOR2I_MM(*start)); track.SetEnd(pcbnew.VECTOR2I_MM(*end)); board.Add(track)
    via = pcbnew.PCB_VIA(board); via.SetPosition(pcbnew.VECTOR2I_MM(12,20)); via.SetWidth(600000)
    via.SetDrill(300000); via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu); via.SetNetCode(pads[0].GetNetCode()); board.Add(via)
    ids = [supply._uid(item) for item in board.GetTracks()]
    with authority(net): result = run(board, net)
    assert result["before"][net]["native_connected"] and result["joins"] == 0
    assert not result["stage_complete"] and not result["after"][net]["planar_full_width_connected"]
    assert result["refusals"][net]["reason"] == "already_native_connected"
    assert ids == [supply._uid(item) for item in board.GetTracks()]


def test_keepout_is_native_blocker_not_no_path_proof(tmp_path):
    board, net = fixture(tmp_path, count=2)
    zone = pcbnew.ZONE(board); zone.SetIsRuleArea(True); zone.SetDoNotAllowTracks(True)
    zone.SetLayer(pcbnew.F_Cu); poly=zone.Outline(); poly.NewOutline()
    for x,y in [(0,0),(40,0),(40,40),(0,40)]: poly.Append(round(x*1e6),round(y*1e6))
    board.Add(zone)
    with authority(net): result = run(board, net)
    assert not result["stage_complete"] and not result["created_uuids"]
    assert (sum(a["blockers"].get("native_track_rule_area",0) for a in result["attempts"])
            + result["anchor_inventory"][net]["launch_refusals"].get("native_track_rule_area",0)) > 0
    assert result["no_path_proof"] is False


def test_field_unknown_cannot_be_accepted(tmp_path):
    board, net = fixture(tmp_path, count=2)
    with authority(net), mock.patch("cec_field_coupling.assess_proposed_tracks",return_value={
            "ok":None,"reason":"unsupported_reference","complete":False,"new_blockers":[]}):
        result = run(board, net)
    assert result["joins"] == 0 and result["no_path_proof"] is False


def test_dense_short_frontier_cannot_starve_a_distant_component():
    import time
    anchors=[dict(uuid='main'+str(i),layer=0,component=0,point_nm=[i,0]) for i in range(80)]
    anchors += [dict(uuid='blocked',layer=0,component=1,point_nm=[100,0]),
                dict(uuid='accessible',layer=0,component=2,point_nm=[10000,0])]
    menu,proof=supply._fair_anchor_pair_menu('arbitrary',anchors,set(),
        layer_names={0:'F.Cu'},deadline=time.monotonic()+5)
    first_round=list(menu)[:3]
    assert proof['frontier_count']==3 and proof['pair_inventory_complete']
    assert {tuple(sorted((row[2]['component'],row[3]['component']))) for row in first_round}=={(0,1),(0,2),(1,2)}
    assert first_round[0][0]==21  # historical cheapest proposal remains first


@pytest.mark.parametrize('shift,sign', [(0,1),(27000000,-1)])
def test_actual_native_open_precedes_short_already_connected_rating_debt(shift,sign):
    anchors=[dict(uuid=str(i),layer=0,component=i,point_nm=[shift+sign*x,0])
        for i,x in enumerate((0,100,10000))]
    menu,proof=supply._fair_anchor_pair_menu('anonymous',anchors,set(),
        layer_names={0:'F.Cu'},deadline=time.monotonic()+5,
        native_components={0:0,1:0,2:1})
    pairs=[tuple(sorted((r[2]['component'],r[3]['component']))) for r in menu]
    assert pairs[:2]==[(1,2),(0,2)] and pairs[-1]==(0,1)
    assert proof['pair_inventory_complete'] and not any(r[2]['layer']!=r[3]['layer'] for r in menu)


def test_distributed_ground_refill_only_accepts_independently_replayed_delta(tmp_path):
    from test_force_current import force_ground_refill_fixture
    source,candidate=force_ground_refill_fixture(tmp_path)
    old=force._preservation_snapshot(source)[0];new=force._preservation_snapshot(candidate)[0]
    created=list(new.keys()-old.keys())
    assert not supply._saved_preservation(source,candidate,{'/CONTROL'},created)['ok']
    result=supply._saved_preservation(source,candidate,{'/CONTROL'},created,allow_ground_refill=True)
    assert result['ok'] and result['allowed_ground_fill_uuids'] and not result['forbidden_modified_uuids']
    assert result['ground_refill_receiving']['existing_ground_fill_matches_independent_native_replay']
    # A same-net new segment with a different ledger does not acquire scope.
    assert not supply._saved_preservation(source,candidate,{'/CONTROL'},[],allow_ground_refill=True)['ok']


def test_frontier_menu_is_deterministic_and_does_not_cross_layers():
    import time
    anchors=[dict(uuid=str(i),layer=layer,component=i%2,point_nm=[i,0])
             for i,layer in enumerate([0,0,2,2])]
    kwargs=dict(layer_names={0:'F.Cu',2:'B.Cu'},deadline=time.monotonic()+5)
    a,proof=supply._fair_anchor_pair_menu('renamed',anchors,set(),**kwargs)
    b,_=supply._fair_anchor_pair_menu('renamed',list(reversed(anchors)),set(),**kwargs)
    assert [r[:2] for r in a]==[r[:2] for r in b]
    assert all(row[2]['layer']==row[3]['layer'] for row in a)
    assert proof['pair_inventory_complete']


def test_bounded_out_menu_is_not_exhaustive_proof():
    import time
    anchors=[dict(uuid=str(i),layer=0,component=i,point_nm=[i,0]) for i in range(5)]
    _,proof=supply._fair_anchor_pair_menu('rail',anchors,set(),layer_names={0:'F.Cu'},
        deadline=time.monotonic()+5,max_checks=2)
    assert not proof['pair_inventory_complete']
    assert proof['pair_checks']==2


def test_same_island_and_wrong_layer_pairs_cannot_exhaust_frontier_budget():
    anchors=[dict(uuid='same'+str(i),layer=0,component=0,point_nm=[i,0]) for i in range(510)]
    anchors+=[dict(uuid='other-layer'+str(i),layer=2,component=2,point_nm=[i,100])
              for i in range(40)]
    anchors.append(dict(uuid='isolated',layer=0,component=1,point_nm=[1000,0]))
    kwargs=dict(layer_names={0:'F.Cu',2:'B.Cu'},deadline=time.monotonic()+5,max_checks=512)
    menu,proof=supply._fair_anchor_pair_menu('unusual-net',anchors,set(),**kwargs)
    reverse,replay=supply._fair_anchor_pair_menu('unusual-net',list(reversed(anchors)),set(),**kwargs)
    assert proof['pair_inventory_complete'] and proof['pair_checks']==510
    assert proof['pair_visits']>65536
    assert len(menu)==510 and all(row[3]['uuid']=='isolated' for row in menu)
    assert [r[:2] for r in menu]==[r[:2] for r in reverse]
    assert replay['pair_inventory_complete']


def test_internal_pair_traversal_still_obeys_deadline():
    anchors=[dict(uuid=str(i),layer=0,component=0,point_nm=[i,0]) for i in range(510)]
    menu,proof=supply._fair_anchor_pair_menu('island',anchors,set(),layer_names={0:'F.Cu'},
        deadline=time.monotonic()-1,max_checks=512)
    assert not menu and not proof['pair_inventory_complete']
    assert proof['pair_checks']==0 and proof['pair_visits']==1


def test_deadline_and_fixed_join_budget(tmp_path):
    board, net = fixture(tmp_path)
    with authority(net):
        empty = supply.construct(board, board_hint="design", include_nets=[net], netclass_resolver=resolver,timeout_s=0)
        partial = run(board, net, max_joins=1)
    assert empty["stop"] == "deadline" and empty["joins"] == 0
    assert partial["stop"] == "join_budget" and partial["joins"] == 1 and not partial["stage_complete"]


def test_preservation_rejects_modified_retained_track(tmp_path):
    board, net = fixture(tmp_path)
    source = tmp_path/"original.kicad_pcb"; pcbnew.SaveBoard(str(source),board)
    # Native new-project initialization is not a routing delta. Establish the
    # saved fixture (including its native project sheet list) before copying.
    board = pcbnew.LoadBoard(str(source)); pcbnew.SaveBoard(str(source),board)
    project = source.with_suffix(".kicad_pro")
    data = json.loads(project.read_text())
    data["schematic"]["top_level_sheets"] = [dict(filename="original.kicad_sch",
        name="original", uuid="00000000-0000-0000-0000-000000000000")]
    project.write_text(json.dumps(data, indent=2, sort_keys=True)+"\n")
    candidate = force._copy_family(source,tmp_path/"private")
    board = pcbnew.LoadBoard(str(candidate))
    with authority(net): result = run(board, net)
    pcbnew.SaveBoard(str(candidate),board)
    assert supply._saved_preservation(source,candidate,{net},result["created_uuids"])["ok"]
    prior = force._copy_family(candidate,tmp_path/"prior")
    next(iter(board.GetTracks())).SetWidth(300000); pcbnew.SaveBoard(str(candidate),board)
    assert not supply._saved_preservation(prior,candidate,{net},[])["ok"]


def test_production_stage_calls_guarded_adapter_and_stops_on_unknown():
    source = Path(__file__).parents[1]/"scripts"/"cec_synth_pipeline.py"
    text = source.read_text(); start=text.index("# ORDINARY POWER DISTRIBUTION PRECEDES")
    block=text[start:text.index("# COMPILE ROUTED POWER",start)]
    assert "cec_distributed_supply.propose(" in block and "cec_staged_fr.route_tiered(" not in block
    assert 'return _fail("priority_power_distribution"' in block
    assert 'get("prefix_accepted")' in block and 'get("accepted")' in block


@pytest.mark.parametrize("kwargs", [dict(timeout_s=-1),dict(timeout_s=float("inf")),
    dict(max_joins=True),dict(max_attempts=5000),dict(max_pair_s=9),dict(allow_maze=1)])
def test_parameter_bounds_fail_before_mutation(tmp_path, kwargs):
    board, net = fixture(tmp_path)
    with authority(net), pytest.raises(ValueError):
        supply.construct(board,board_hint="design",include_nets=[net],netclass_resolver=resolver,**kwargs)
    assert not list(board.GetTracks())


@pytest.mark.parametrize("selection", ["rail",[None],["rail",2]])
def test_malformed_selection_is_not_an_implicit_contract(tmp_path, selection):
    board, net = fixture(tmp_path)
    with authority(net), pytest.raises(ValueError):
        topology.distributed_supply_contracts(board,"design",include_nets=selection,netclass_resolver=resolver)


def test_saved_track_ledger_detects_one_nm_width_drift(tmp_path):
    board, net = fixture(tmp_path)
    with authority(net): result = run(board,net)
    assert supply._track_records(board,result["created_uuids"]) == result["created_tracks"]
    track = next(iter(board.GetTracks())); track.SetWidth(track.GetWidth()-1)
    assert supply._track_records(board,result["created_uuids"]) != result["created_tracks"]


def test_project_and_process_floor_are_not_reduced(tmp_path):
    board, net = fixture(tmp_path)
    with authority(net):
        report = topology.distributed_supply_contracts(board,"design",include_nets=[net],
            netclass_resolver=lambda _n:dict(name="Supply",track_width=.8,clearance=.4,
                track_width_by_layer_mm={"F.Cu":1.2}))
    assert report["contracts"][net]["required_by_layer_mm"]["F.Cu"] == 1.2
    assert report["contracts"][net]["required_by_layer_mm"]["B.Cu"] == .8
    assert report["contracts"][net]["clearance_mm"] == .4


def test_sidecar_drift_is_not_a_cosmetic_exception(tmp_path):
    board, net = fixture(tmp_path)
    source=tmp_path/"source.kicad_pcb";pcbnew.SaveBoard(str(source),board)
    candidate=force._copy_family(source,tmp_path/"child")
    candidate.with_suffix(".unfamiliar-proof.json").write_text("{}")
    assert not supply._saved_preservation(source,candidate,{net},[])["ok"]


def test_output_namespace_guard_precedes_worker(tmp_path):
    board, net = fixture(tmp_path)
    source=tmp_path/"source.kicad_pcb";pcbnew.SaveBoard(str(source),board)
    before=force._hash(source)
    with pytest.raises(ValueError,match="protected saved-family namespace"):
        supply.propose(source,tmp_path/"source.report",board_hint="design",include_nets=[net])
    assert force._hash(source) == before


@pytest.mark.parametrize("unknown,regression", [(False,False),(True,False),(False,True)])
def test_saved_worker_receives_only_strict_private_prefix(tmp_path, unknown, regression):
    board, net = fixture(tmp_path)
    if unknown:
        info=pcbnew.NETINFO_ITEM(board,"/unknown_supply");board.Add(info)
        fp=pcbnew.FOOTPRINT(board);fp.SetReference("UNRATED")
        pad=pcbnew.PAD(fp);pad.SetNumber("1");pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
        pad.SetPosition(pcbnew.VECTOR2I_MM(5,5));layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(layers);pad.SetNet(info);fp.Add(pad);board.Add(fp)
    source=tmp_path/"source.kicad_pcb";pcbnew.SaveBoard(str(source),board)
    # Author the fixture's declared project sheet identity before the trial.
    project=source.with_suffix(".kicad_pro");data=json.loads(project.read_text())
    data["schematic"]["top_level_sheets"]=[dict(filename="source.kicad_sch",name="source",
        uuid="00000000-0000-0000-0000-000000000000")]
    project.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    old=dict(drc=0,unconnected=2,kelvin_ok=True,diffpair_ok=True)
    new=dict(drc=1 if regression else 0,unconnected=0,kelvin_ok=True,diffpair_ok=True)
    before=force._family(source,"design")
    with authority(net), mock.patch("cec_score.score",side_effect=[old,new]), \
         mock.patch.object(force,"_code_identity",return_value={"unit":"fixed"}):
        result=supply._worker(source,tmp_path/"operation",board_hint="design",
            include_nets=[net]+(["/unknown_supply"] if unknown else []),timeout_s=5)
    assert result["prefix_accepted"] is (not regression), {
        k:result.get(k) for k in ("preservation","saved_replay_exact","admission","source_unchanged")}
    assert result["accepted"] is (not unknown and not regression)
    assert result["source_unchanged"] and force._family(source,"design") == before
    assert result["whole_power_qualified"] is False and result["release_authority"] is False
    if unknown:
        assert result["refusals"]["/unknown_supply"]["reason"] == "current_contract_missing"
    if regression:
        assert result["selected"] is None and Path(result["candidate"]).is_file()


@pytest.mark.parametrize("reject_craft", [False, True])
def test_success_and_post_addition_refusal_never_rebuild_or_relabel(tmp_path, reject_craft):
    board, net = fixture(tmp_path)
    # Retain an unrelated authored short and an unassigned touching segment.
    # A global BuildConnectivity may propagate labels here; this operator has
    # no authority to repair or relabel any of them.
    for name, start, end in [("/OTHER_A",(28,30),(31,30)),
                              ("/OTHER_B",(31,30),(34,30)),
                              ("",(34,30),(35,30))]:
        if name:
            board.Add(pcbnew.NETINFO_ITEM(board,name))
        track=pcbnew.PCB_TRACK(board);track.SetWidth(200000);track.SetLayer(pcbnew.F_Cu)
        track.SetStart(pcbnew.VECTOR2I_MM(*start));track.SetEnd(pcbnew.VECTOR2I_MM(*end))
        track.SetNetCode(board.GetNetcodeFromNetname(name) if name else 0);board.Add(track)
    zone=pcbnew.ZONE(board);zone.SetLayer(pcbnew.F_Cu)
    zone.SetNetCode(board.GetNetcodeFromNetname("/OTHER_A"))
    poly=zone.Outline();poly.NewOutline()
    for point in ((27,29),(29,29),(29,32),(27,32)):
        poly.Append(pcbnew.VECTOR2I_MM(*point))
    board.Add(zone)
    def assignments():
        objects=[p for fp in board.GetFootprints() for p in fp.Pads()]
        objects.extend(board.GetTracks());objects.extend(board.Zones())
        return {supply._uid(item):(int(item.GetNetCode()),str(item.GetNetname())) for item in objects}
    before=assignments()
    original_quality=__import__("cec_route_quality").analyze_board
    def quality(*args,**kwargs):
        result=original_quality(*args,**kwargs)
        if reject_craft:
            result["craft_ok"]=False
        return result
    with authority(net), mock.patch.object(pcbnew.BOARD,"BuildConnectivity",
            side_effect=AssertionError("global native net propagation forbidden")), \
         mock.patch("cec_route_quality.analyze_board",side_effect=quality):
        result=run(board,net)
    after=assignments()
    assert {uid:after[uid] for uid in before} == before
    assert result["joins"] == (0 if reject_craft else 2)
    assert len(after)-len(before) == len(result["created_uuids"])
    if reject_craft:
        assert any(row.get("created_uuids") and not row["accepted"] for row in result["attempts"])
    else:
        assert all(after[uid] == (board.GetNetcodeFromNetname(net),net) for uid in result["created_uuids"])


@pytest.mark.parametrize("operation_left,job_left,expected", [(70,200,10),(200,64,4),(45,200,0)])
def test_search_inherits_earliest_lease_and_reserves_receiving(tmp_path,operation_left,job_left,expected):
    board,net=fixture(tmp_path)
    now=time.time()
    with authority(net), mock.patch.dict(os.environ,{
            "CEC_OPERATION_DEADLINE_EPOCH":str(now+operation_left),
            "CEC_JOB_DEADLINE_EPOCH":str(now+job_left)}), \
         mock.patch("cec_operation_budget.time.time",return_value=now):
        result=supply.construct(board,board_hint="design",include_nets=[net],
            netclass_resolver=resolver,timeout_s=60)
    assert result["bounds"]["effective_search_timeout_s"] == expected
    assert result["bounds"]["receiving_reserve_s"] == 60
    assert result["bounds"]["timeout_s"] == 60
    if not expected:
        assert result["stop"] == "deadline" and not result["created_uuids"]


def partly_filled_zone(board, *, name, layer, turn=0, entire_separator=False, own_net=None):
    """A real native outline with a copper-free center crossing; no rating."""
    foreign=own_net or "/unknown_current_authority/retained_copper"
    if foreign not in board.GetNetsByName():
        board.Add(pcbnew.NETINFO_ITEM(board,foreign))
    item=pcbnew.ZONE(board);item.SetNet(board.FindNet(foreign));item.SetLayer(layer)
    item.SetZoneName(name);item.SetLocalClearance(200000)
    def point(x,y):
        for _ in range(turn):x,y=40-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    y0,y1=(0,40) if entire_separator else (19,21)
    item.Outline().NewOutline()
    for x,y in ((11,y0),(13,y0),(13,y1),(11,y1)):
        item.Outline().Append(point(x,y))
    fill=pcbnew.SHAPE_POLY_SET();fill.NewOutline()
    for x,y in ((11,y0),(13,y0),(13,y0+.2),(11,y0+.2)):
        fill.Append(point(x,y))
    item.SetFilledPolysList(layer,fill);item.SetIsFilled(True);board.Add(item)
    return item


@pytest.mark.parametrize("name", ["manual_unknown_origin", "", "custom-power-area:renamed"])
@pytest.mark.parametrize("turn,layer", [(0,pcbnew.F_Cu),(1,pcbnew.B_Cu),(2,pcbnew.F_Cu),(3,pcbnew.B_Cu)])
def test_arbitrary_partly_filled_outline_requires_native_legal_detour(tmp_path,name,turn,layer):
    board,net=fixture(tmp_path,count=2,turn=turn,layer=layer)
    zone=partly_filled_zone(board,name=name,layer=layer,turn=turn)
    pads=supply._pads(board,net)
    chord=pcbnew.SHAPE_SEGMENT(pads[0].GetPosition(),pads[1].GetPosition(),200000)
    # A fill-only check would approve this chord. The unchanged owner rule is
    # the actual outlined reservation, including its presently empty region.
    assert zone.Outline().Collide(chord,0)
    assert not zone.GetFilledPolysList(layer).Collide(chord,200000)
    outline_before=zone.Outline().Format();fill_before=zone.GetFilledPolysList(layer).Format()
    with authority(net):result=run(board,net)
    assert result["stage_complete"] and result["joins"]==1
    assert len(result["created_uuids"])>=3, "direct crossing through the reserved void was accepted"
    assert all(not zone.Outline().Collide(track.GetEffectiveShape(layer),0) for track in board.GetTracks())
    assert all(track.GetWidth()==200000 and track.GetLayer()==layer for track in board.GetTracks())
    assert zone.Outline().Format()==outline_before and zone.GetFilledPolysList(layer).Format()==fill_before
    assert result["new_vias"]==0 and result["no_path_proof"] is False


@pytest.mark.parametrize("name", ["foreign_landing_without_pipeline_prefix", ""])
def test_reserved_void_with_no_planar_menu_is_typed_refusal_not_current_waiver(tmp_path,name):
    board,net=fixture(tmp_path,count=2)
    zone=partly_filled_zone(board,name=name,layer=pcbnew.F_Cu,entire_separator=True)
    outline_before=zone.Outline().Format();fill_before=zone.GetFilledPolysList(pcbnew.F_Cu).Format()
    with authority(net):result=run(board,net,max_attempts=8)
    assert not result["stage_complete"] and result["joins"]==0 and not list(board.GetTracks())
    assert result["refusals"][net]["reason"] in (
        "bounded_planar_anchor_menu_exhausted", "bounded_search_incomplete")
    if result["refusals"][net]["reason"] == "bounded_search_incomplete":
        assert result["stop"] == "attempt_budget" and len(result["attempts"]) == 8
    assert result["refusals"][net]["physical_feasibility"]=="unknown"
    assert result["no_path_proof"] is False and result["whole_power_qualified"] is False
    assert result["contracts"][net]["current_authority"]["amps"]==.5
    assert zone.Outline().Format()==outline_before and zone.GetFilledPolysList(pcbnew.F_Cu).Format()==fill_before


def test_own_net_zone_does_not_forbid_full_width_planar_join(tmp_path):
    board,net=fixture(tmp_path,count=2)
    partly_filled_zone(board,name="same_net_authored_area",layer=pcbnew.F_Cu,own_net=net)
    with authority(net):result=run(board,net)
    assert result["stage_complete"] and result["joins"]==1 and len(result["created_uuids"])==1
    assert result["contracts"][net]["terminal_barrel_zone_rating_qualified"] is False
    assert result["whole_power_qualified"] is False


def anchored_fixture(tmp_path, *, turn=0, layer=pcbnew.F_Cu, width=200000):
    board, net = fixture(tmp_path, count=2, name="/renamed/branch_supply", turn=turn, layer=layer)
    def point(x, y):
        for _ in range(turn):
            x, y = 40-y, x
        return pcbnew.VECTOR2I_MM(x, y)
    retained = pcbnew.PCB_TRACK(board)
    retained.SetStart(point(8,20)); retained.SetEnd(point(8,12))
    retained.SetNetCode(board.GetNetcodeFromNetname(net)); retained.SetLayer(layer)
    retained.SetWidth(width); retained.SetLocked(True); board.Add(retained)
    # The old pad-center launch is blocked by an actual authored rule area.
    # The source track already reaches out of it and must not be moved.
    zone = pcbnew.ZONE(board); zone.SetIsRuleArea(True)
    zone.SetDoNotAllowTracks(True); zone.SetLayer(layer)
    zone.Outline().NewOutline()
    for x,y in ((6.5,18.5),(9.5,18.5),(9.5,21.5),(6.5,21.5)):
        zone.Outline().Append(point(x,y))
    board.Add(zone)
    return board, net, retained


@pytest.mark.parametrize("turn,layer", [(0,pcbnew.F_Cu),(1,pcbnew.B_Cu),
                                       (2,pcbnew.F_Cu),(3,pcbnew.B_Cu)])
def test_branch_attaches_to_retained_rated_track_without_moving_it(tmp_path, turn, layer):
    board, net, retained = anchored_fixture(tmp_path, turn=turn, layer=layer)
    old = supply._track_records(board,[supply._uid(retained)])
    with authority(net):
        result = run(board,net,max_attempts=12)
        assert result["stage_complete"] and result["joins"] == 1
        assert any(anchor["kind"] == "rated_track" for attempt in result["attempts"]
            if attempt["accepted"] for anchor in (attempt["start"],attempt["end"]))
        assert supply._saved_anchor_contacts(board,result)["ok"]
    assert old == supply._track_records(board,[supply._uid(retained)])
    assert result["new_vias"] == result["new_zones"] == result["neckdowns"] == 0
    assert result["whole_power_qualified"] is False and result["release_authority"] is False
    assert all(item.GetWidth() == 200000 for item in board.GetTracks())


def test_undersized_retained_branch_is_not_a_rated_anchor(tmp_path):
    board, net, retained = anchored_fixture(tmp_path,width=199999)
    with authority(net):
        result = run(board,net,max_attempts=12)
    assert result["joins"] == 0
    assert all(a["kind"] != "rated_track" for attempt in result["attempts"]
        for a in (attempt["start"],attempt["end"]))
    assert retained.GetWidth() == 199999


@pytest.mark.parametrize("fault", ["width","point","layer","net","kind"])
def test_saved_rated_anchor_replay_refuses_identity_or_geometry_drift(tmp_path, fault):
    board, net, retained = anchored_fixture(tmp_path)
    with authority(net):
        result = run(board,net,max_attempts=12)
        assert result["joins"] == 1
        accepted = next(a for a in result["attempts"] if a["accepted"])
        anchor = next(a for a in (accepted["start"],accepted["end"]) if a["kind"] == "rated_track")
        if fault == "width": retained.SetWidth(199999)
        elif fault == "point": anchor["point_nm"][0] += 1
        elif fault == "layer": anchor["layer"] = pcbnew.B_Cu
        elif fault == "net": retained.SetNetCode(0)
        else: anchor["kind"] = "zone"
        assert not supply._saved_anchor_contacts(board,result)["ok"]


def test_track_anchor_contact_requires_actual_material_outside_drill(tmp_path):
    board, net, retained = anchored_fixture(tmp_path)
    with authority(net):
        contract = supply.audit(board,board_hint="design",include_nets=[net],
                                netclass_resolver=resolver)["contracts"][net]
    anchor = dict(kind="rated_track",uuid=supply._uid(retained),layer=pcbnew.F_Cu,
                  point_nm=[8000000,16000000])
    assert supply._anchor_contact(board,anchor,contract)["ok"]
    fp=pcbnew.FOOTPRINT(board);pad=pcbnew.PAD(fp)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH);pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetLayerSet(pcbnew.PAD.UnplatedHoleMask())
    pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6));pad.SetDrillSize(pcbnew.VECTOR2I_MM(.6,.6))
    pad.SetPosition(pcbnew.VECTOR2I_MM(8,16));fp.Add(pad);board.Add(fp)
    proof=supply._anchor_contact(board,anchor,contract)
    assert not proof["ok"] and proof["reason"] == "track_contact_disk_intersects_actual_drill"


def test_isolated_full_width_copper_cannot_supply_component_anchor(tmp_path):
    board,net=fixture(tmp_path,count=2)
    isolated=pcbnew.PCB_TRACK(board);isolated.SetNetCode(board.GetNetcodeFromNetname(net))
    isolated.SetLayer(pcbnew.F_Cu);isolated.SetWidth(200000)
    isolated.SetStart(pcbnew.VECTOR2I_MM(10,12));isolated.SetEnd(pcbnew.VECTOR2I_MM(15,12))
    board.Add(isolated)
    with authority(net):
        report=supply.audit(board,board_hint="design",include_nets=[net],netclass_resolver=resolver)
        anchors,proof=supply._routing_anchors(board,net,report["nets"][net]["planar_full_width_components"],
                                            report["contracts"][net],deadline=time.monotonic()+5)
    assert proof["complete"]
    assert all(row["uuid"] != supply._uid(isolated) for row in anchors)


def test_bounded_anchor_inventory_never_claims_no_path(tmp_path):
    board,net,_retained=anchored_fixture(tmp_path)
    with authority(net),mock.patch.object(supply,"MAX_ROUTING_ANCHORS",2):
        result=run(board,net,max_attempts=12)
    assert result["joins"] == 0 and result["no_path_proof"] is False
    assert result["anchor_inventory"][net]["stop"] == "anchor_budget"


def test_isolated_worker_forwards_bounded_maze_effort(tmp_path):
    board,net=fixture(tmp_path)
    source=tmp_path/"source.kicad_pcb";pcbnew.SaveBoard(str(source),board)
    payload=dict(created_uuids=[],stage_complete=False)
    with mock.patch.object(supply,"construct",return_value=payload) as construct:
        result=supply._worker(source,tmp_path/"private",board_hint="design",include_nets=[net],
            allow_maze=True,max_pair_s=.125)
    assert construct.call_args.kwargs["allow_maze"] is True
    assert construct.call_args.kwargs["max_pair_s"] == .125
    assert not result["prefix_accepted"] and result["code_unchanged"] and result["source_unchanged"]


@pytest.mark.parametrize("options", [dict(allow_maze=1),dict(allow_maze="false"),
    dict(max_pair_s=0),dict(max_pair_s=True),dict(max_pair_s=float("nan")),dict(max_pair_s=6)])
def test_proposal_effort_validation_precedes_any_output_or_worker(tmp_path,options):
    target=tmp_path/"must_not_be_created"
    with pytest.raises(ValueError),mock.patch("cec_operation_budget.run") as worker:
        supply.propose(tmp_path/"absent.kicad_pcb",target,board_hint="design",include_nets=["/rail"],**options)
    assert not target.exists() and not worker.called


def test_production_stage_exposes_maze_without_default_width_fallback():
    source=(Path(__file__).parents[1]/"scripts"/"cec_synth_pipeline.py").read_text()
    start=source.index("# ORDINARY POWER DISTRIBUTION PRECEDES")
    block=source[start:source.index("# COMPILE ROUTED POWER",start)]
    assert '"power_distribution_allow_maze", True' in block
    assert '"power_distribution_max_pair_s", .25' in block
    assert 'allow_maze=priority_distribution_route["effort"]["allow_maze"]' in block
    assert 'max_pair_s=priority_distribution_route["effort"]["max_pair_s"]' in block
    assert "cec_staged_fr.route_tiered(" not in block
