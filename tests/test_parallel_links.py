import copy
from types import SimpleNamespace
from unittest import mock

import pytest
import cec_parallel_links as links
import cec_synth_pipeline as synth


@pytest.mark.parametrize("value", ["0", "0R", "0Ω", "0.00 ohms", " 000.0 r "])
def test_zero_link_exact_values(value):
    assert links.is_zero_link(value)


@pytest.mark.parametrize("value", ["0.01Ω", "0uF", "0Ω DNP", "0DIODE", "", "100R"])
def test_not_a_populated_zero_link_value(value):
    assert not links.is_zero_link(value)


def topology():
    return {"OWNER": {"a": "NET1", "b": "NET2", "c": "NET3", "d": "NET4"},
            "X8": {"1": "NET1", "2": "NET3"},
            "X9": {"1": "NET2", "2": "NET4"}}


def test_unique_owner_and_both_pin_maps_are_source_derived():
    source = topology(); before = copy.deepcopy(source)
    groups, errors = links.derive(source, ["X8", "X9"])
    assert not errors and len(groups) == 1
    assert source == before
    assert groups[0]["owner_ref"] == "OWNER"
    assert groups[0]["members"][0]["pins"] == [
        {"follower_pin": "1", "owner_pin": "a", "net": "NET1"},
        {"follower_pin": "2", "owner_pin": "c", "net": "NET3"}]


def test_no_guessing_between_parallel_devices():
    source=topology();source["OTHER"]=dict(source["OWNER"])
    groups, errors=links.derive(source,["X8","X9"])
    assert not groups and errors[0]["reason"] == "parallel_link_owner_ambiguous"


def test_shared_rail_and_single_link_do_not_make_a_paired_group():
    source=topology()
    assert links.derive(source,["X8"])[0] == []
    source["X9"]["1"]="NET1"
    assert links.derive(source,["X8","X9"])[0] == []


@pytest.mark.parametrize("props,expected", [({"dnp":""}, True),
    ({"__dnp__":True},True), ({"dnp":"yes"},True), ({"dnp":"false"},False),
    ({"dnp":False},False), ({"dnp":0},False), ({},False)])
def test_source_bare_dnp_is_not_treated_as_populated(props, expected):
    assert links.source_dnp(props) == expected


def test_roles_do_not_depend_on_reference_or_net_spelling():
    original=topology()
    renamed={"item_"+ref:{"pin_"+pin:"/nested/"+net for pin,net in pins.items()}
             for ref,pins in original.items()}
    groups,errors=links.derive(renamed,["item_X9","item_X8"])
    assert not errors and len(groups)==1
    assert groups[0]["owner_ref"]=="item_OWNER"


def fixture():
    source=topology()
    nl=synth.Netlist(comps={ref:synth.Comp(ref, "0Ω" if ref != "OWNER" else "optional")
                           for ref in source}, nets={})
    for ref,pins in source.items():
        for pin,net in pins.items():
            nl.nets.setdefault(net,[]).append((ref,pin))
    local={"OWNER":{"a":(-1,-1.5),"b":(1,-1.5),"c":(-1,1.5),"d":(1,1.5)},
           "X8":{"1":(-.5,0),"2":(.5,0)},"X9":{"1":(-.5,0),"2":(.5,0)}}
    candidate=SimpleNamespace(P={"OWNER":(20,20,0),"X8":(2,2,0),"X9":(35,35,180)},
                              W=40,H=40,back_refs=())
    return nl,local,candidate


def test_empty_critical_selector_still_gates_both_link_ends_and_joint_moves():
    import cec_pcb
    nl,local,candidate=fixture();comps={ref:ref for ref in nl.comps}
    def pad_at(nl, ref, pin, placements, comps):
        x,y,rot=placements[ref];dx,dy=cec_pcb._rot(*local[ref][pin],rot)
        return x+dx,y+dy
    def box(ref,x,y,rot):
        return (x-1.5,x+1.5,y-2,y+2) if ref=="OWNER" else (x-.7,x+.7,y-.5,y+.5)
    with mock.patch.object(synth,"_pad_xy_global",side_effect=pad_at), \
         mock.patch.object(cec_pcb,"local_pads",side_effect=lambda ref:local[ref]), \
         mock.patch.object(cec_pcb,"courtyard_bbox",side_effect=box):
        evidence=synth._critical_control_follower_evidence_from_topology(nl,comps,candidate.P,())
        assert not evidence["ok"] and len(evidence["violations"]) == 2
        extended={ref:pose+(3.0,4.0) for ref,pose in candidate.P.items()}
        native_form=synth._critical_control_follower_evidence_from_topology(nl,comps,extended,())
        assert native_form==evidence
        assert all(len(row["pins"])==2 for row in evidence["details"])
        moves=synth._parallel_link_move_specs(candidate,evidence["details"],comps,max_specs=8)
        assert moves and len(moves)<=8
        for move in moves:
            assert set(move["placements"])=={"X8","X9"}
            changed=dict(candidate.P,**move["placements"])
            after=synth._critical_control_follower_evidence_from_topology(nl,comps,changed,())
            assert after["ok"] and changed["OWNER"]==candidate.P["OWNER"]
        assert not synth._parallel_link_move_specs(candidate,evidence["details"],comps,
                                                   immovable={"X8"})
        certificate=synth.placement_craft_blocker_certificate({"critical_control_follower":evidence})
        assert "critical_control_follower_placement" in certificate["required_stages"]


def test_joint_selection_filters_retained_support_before_single_slot_cap():
    import cec_pcb
    nl,local,candidate=fixture();comps={ref:ref for ref in nl.comps}
    def pad_at(nl,ref,pin,placements,comps):
        x,y,rot=placements[ref];dx,dy=cec_pcb._rot(*local[ref][pin],rot)
        return x+dx,y+dy
    def box(ref,x,y,rot):
        return (x-1.5,x+1.5,y-2,y+2) if ref=='OWNER' else (x-.7,x+.7,y-.5,y+.5)
    with mock.patch.object(synth,'_pad_xy_global',side_effect=pad_at), \
            mock.patch.object(cec_pcb,'local_pads',side_effect=lambda ref:local[ref]), \
            mock.patch.object(cec_pcb,'courtyard_bbox',side_effect=box):
        evidence=synth._critical_control_follower_evidence_from_topology(nl,comps,candidate.P,())
        ordinary=synth._parallel_link_move_specs(candidate,evidence['details'],comps,max_specs=2)
        assert len(ordinary)==2
        stats=[]
        result=synth._parallel_link_move_specs(candidate,evidence['details'],comps,max_specs=1,
            placement_predicate=lambda p:p!=ordinary[0]['placements'],support_diagnostics=stats)
        assert result[0]['placements']==ordinary[1]['placements']
        assert stats[0]['checked']==2 and stats[0]['rejected']==1
        assert stats[0]['selected']==1


def test_missing_real_pad_is_an_error_not_a_footprint_origin_fallback():
    import cec_pcb
    nl,local,candidate=fixture();comps={ref:ref for ref in nl.comps}
    del local["X8"]["2"]
    with mock.patch.object(cec_pcb,"local_pads",side_effect=lambda ref:local[ref]):
        evidence=synth._critical_control_follower_evidence_from_topology(nl,comps,candidate.P,())
    assert not evidence["ok"]
    assert any(row["reason"]=="parallel_link_copper_land_unresolved" for row in evidence["errors"])


def test_exact_route_refusal_reopens_locally_clean_source_owned_group():
    rows = [dict(kind='parallel_link', ref=ref, group_refs=['X8', 'X9'],
                 owner_ref='OWNER', actionable=False) for ref in ('X8', 'X9')]
    craft = {'critical_control_follower': {'ok': True, 'details': rows}}
    route = {'critical_pair_refused': [{'name': 'ANY', 'refused': 'exact junction failure',
        'endpoint_stations': [{'physical_refs': ['X8', 'X9']}]}]}
    before = copy.deepcopy(craft)
    move = {'refs': ['X8', 'X9'], 'kind': 'parallel_link_group_reseat'}
    with mock.patch.object(synth, '_parallel_link_move_specs', return_value=[move]) as solver:
        result = synth._route_feedback_parallel_link_moves(
            'candidate', craft, route, 'comps', immovable={'LOCKED'}, max_specs=7)
    assert craft == before
    assert all(row['actionable'] for row in solver.call_args.args[1])
    assert solver.call_args.kwargs == {'immovable': {'LOCKED'}, 'max_specs': 7,
        'placement_predicate': None, 'max_support_checks': 256, 'support_diagnostics': None}
    assert result[0]['route_feedback'][0]['pair'] == 'ANY'
    assert result[0]['budget_group'] == 'pair-link-reseat:X8|X9'


@pytest.mark.parametrize('mode', ['no_refusal', 'unrelated', 'no_owner', 'source_error'])
def test_route_feedback_does_not_invent_ownership_or_reseat_unrelated_groups(mode):
    craft = {'critical_control_follower': {'details': [dict(kind='parallel_link',
        ref='X8', group_refs=['X8', 'X9'], owner_ref='OWNER', actionable=False)]}}
    route = {'critical_pair_refused': [{'refused': 'exact failed',
        'endpoint_stations': [{'physical_refs': ['X8', 'X9']}]}]}
    if mode == 'no_refusal': route['critical_pair_refused'][0]['refused'] = ''
    if mode == 'unrelated': route['critical_pair_refused'][0]['endpoint_stations'][0]['physical_refs'] = ['REMOTE']
    if mode == 'no_owner': craft['critical_control_follower']['details'] = []
    if mode == 'source_error': craft['critical_control_follower']['errors'] = ['ambiguous']
    with mock.patch.object(synth, '_parallel_link_move_specs') as solver:
        assert not synth._route_feedback_parallel_link_moves(None, craft, route, {})
    solver.assert_not_called()


_native_boards=[]


def test_native_route_feedback_uses_same_owner_even_when_links_are_far_apart():
    import pcbnew
    import cec_precision_route as route
    board=pcbnew.CreateEmptyBoard();_native_boards.append(board)
    for net in ("P", "N", "PX", "NX"):
        board.Add(pcbnew.NETINFO_ITEM(board,net))
    def add(ref,value,rows):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue(value)
        for pin,net,x,y in rows:
            pad=pcbnew.PAD(fp);pad.SetNumber(pin)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x,y));pad.SetNet(board.FindNet(net));fp.Add(pad)
        board.Add(fp)
        return fp
    add("A","optional",[("1","P",10,10),("2","N",11,10),
                         ("3","PX",10,13),("4","NX",11,13)])
    add("B","endpoint",[("1","P",20,10),("2","N",21,10)])
    add("X8","0R",[("1","P",9,9),("2","PX",9,10)])
    add("Y9","0Ω",[("1","N",39,9),("2","NX",39,10)])
    owners=route._parallel_link_owner_map(board)
    assert owners["X8"]==owners["Y9"]
    stations=route._pair_endpoint_stations(board,{"p":"P","n":"N"})
    paired=next(row for row in stations if row["id"]=="X8|Y9")
    assert paired["topology_owner"]=="A" and not paired["locality_ok"]
    # Identifying a far-away station for placement feedback does not waive
    # the router's existing physical split-terminal fanout bound.
    assert route._multidrop_pair_plan(board,{"p":"P","n":"N"}) is None
