"""Bounded, complete supply groups; identities and coordinates are not policy."""
import math
import pytest

import cec_supply_group as group


def test_joint_search_keeps_alternative_to_greedy_first_cap():
    options = {"CAP-LEFT": [{"cost": 0, "seat": 0}, {"cost": 1, "seat": 1}],
               "CAP-RIGHT": [{"cost": 0, "seat": 0}]}
    solutions, report = group.layouts(options, lambda a,b: a["seat"] != b["seat"])
    assert len(solutions) == 1 and report["complete"] == 1
    assert solutions[0]["CAP-LEFT"]["seat"] == 1
    assert set(solutions[0]) == set(options)


@pytest.mark.parametrize("options,budget", [
    ({"A": [], "B": [{"cost": 0}]}, 100),
    ({"A": [{"cost": 0}], "B": [{"cost": 0}]}, 1)])
def test_no_partial_group_on_missing_option_or_budget(options, budget):
    solutions, report = group.layouts(options, lambda a,b: True, max_states=budget)
    assert not solutions and report["states"] <= budget


def test_final_geometry_proof_cannot_be_bypassed():
    solutions, report = group.layouts({"A": [{"cost": 0}], "B": [{"cost": 0}]},
        lambda a,b: True, verify=lambda g: False)
    assert not solutions and report["complete"] == 0


def test_deterministic_and_bounded_with_equal_costs():
    options = {str(i): [{"cost": 0, "seat": j} for j in range(4)] for i in range(3)}
    args = (options, lambda a,b: a["seat"] != b["seat"])
    first = group.layouts(*args, max_states=80, max_solutions=3)
    assert first == group.layouts(*args, max_states=80, max_solutions=3)
    assert len(first[0]) <= 3 and first[1]["states"] <= 80
    assert all(set(g) == set(options) for g in first[0])


def test_owner_sites_preserve_pin_and_obey_radius_translation_and_budget():
    assert group.owner_sites((8,9,90), fixed=True) == [(8.,9.,90.)]
    a = group.owner_sites((0,0,0), radius_mm=3, max_sites=27)
    b = group.owner_sites((8,9,0), radius_mm=3, max_sites=27)
    assert len(a) == len(b) == 27
    assert all(math.hypot(x,y) <= 3+1e-8 for x,y,r in a)
    assert all(r in (0,90,180,270) for x,y,r in a)
    assert all((x+8,y+9,r) == p for (x,y,r),p in zip(a,b))


@pytest.mark.parametrize("kw", [{"radius_mm": -1}, {"radius_mm": float("inf")}, {"max_sites": 0}])
def test_invalid_search_limits_fail_closed(kw):
    with pytest.raises(ValueError):
        group.owner_sites((0,0,0), **kw)


def test_invalid_cost_and_beam_budget_fail_closed():
    with pytest.raises(ValueError):
        group.layouts({"A": [{"cost": float("nan")}]}, lambda a,b: True)
    with pytest.raises(ValueError):
        group.layouts({}, lambda a,b: True, beam_width=0)


@pytest.mark.parametrize("refprefix,offset,blocked,pinned", [
    ("A", (0.,0.), False, False), ("Z", (21.,13.), False, False),
    ("A", (0.,0.), True, False), ("A", (0.,0.), False, True)])
def test_actual_placement_adapter_commits_all_members_or_nothing(refprefix,offset,blocked,pinned):
    """Execute production adapter with synthetic collision and lane predicates."""
    import ast, inspect, sys, copy
    from types import SimpleNamespace
    from unittest import mock
    import cec_pcb
    import cec_synth_pipeline as synth
    tree = ast.parse(inspect.getsource(synth.synth_one))
    stage = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                 and n.name == "_p9b_device_bypass")
    start = next(i for i,n in enumerate(stage.body) if isinstance(n, ast.Import)
                 and any(a.name == "cec_supply_group" for a in n.names))
    end = next(i for i,n in enumerate(stage.body[start:], start) if isinstance(n, ast.For))
    owner, cap_a, cap_b = [refprefix+r for r in ("_IC", "_CAP1", "_CAP2")]
    initial = {r:(offset[0]+x,offset[1]+10.,0.) for r,x in ((owner,10.),(cap_a,3.),(cap_b,20.))}
    reqs = {c:{"owner":owner,"pin":str(i),"rail":"SUPPLY"+str(i),"max_mm":3.5}
            for i,c in enumerate((cap_a,cap_b),1)}
    local = {owner:(0.,0.,0.),cap_a:(-2.,0.,0.),cap_b:(2.,0.,0.)}
    def box(ref,p):
        return (p[0]-.4,p[0]+.4,p[1]-.4,p[1]+.4)
    positions = dict(initial)
    env = {"sys":sys,"math":math,"copy":copy,"cec_pcb":cec_pcb,"cfg":SimpleNamespace(params={}),
           "owner_req_count":{owner:2},"assignments":reqs,"P":positions,
           "locked":{cap_a} if pinned else set(),"anchors":{},"_bp_refs":set(),
           "_pourfirst_locked_refs":set(),"_bounds":{},"_device_bypass_invocations":1,
           "part_box":box,"pads_clear_blueprint_copper":lambda r,p: True,
           "clear":lambda *a,**kw: not blocked,
           "preserves_private_pin_escapes":lambda *a: True,
           "pad_num_on":lambda *a: "1","foreign_pad_boxes":lambda *a: [],
           "blueprint_copper":[],"pad_at":lambda r,p,pos: pos[:2],
           "_pad_box_path_length":lambda a,b,*args,**kw: math.dist(a,b),
           "claim_scarce_space":True,"_bypass_locked":set(),
           "_component_obstacles":lambda *a: [],"avoid_named":[],"_back":(),
           "reservation_owned_by":lambda *a: False,"W":80.,"H":80.,
           "_is_gnd_net":synth._is_gnd_net,
           "boxes":{r:box(r,p) for r,p in positions.items()},"_joint_supply_reservations":{},
           "_joint_supply_reports":[],"refused":[],"nl":None,"comps":{},
           "_qualified_supply_layouts":lambda *a,**kw: ([local],{})}
    # Keep the refusal regression fast while exercising actual all-or-none commit.
    with mock.patch.object(group, "owner_sites", return_value=[initial[owner]]), \
            mock.patch.object(group, "contact_owner_sites", return_value=[]):
        exec(compile(ast.Module(body=stage.body[start:end],type_ignores=[]),"joint-adapter","exec"),env)
    if blocked or pinned:
        assert positions == initial and not env["_bypass_locked"]
        assert not env["_joint_supply_reservations"]
        assert bool(env["_joint_supply_reports"]) == blocked
    else:
        assert positions[owner] == initial[owner]
        assert positions[cap_a][0] == initial[owner][0]-2.
        assert positions[cap_b][0] == initial[owner][0]+2.
        assert env["_bypass_locked"] == set(initial)
        assert set(env["_joint_supply_reservations"][owner]) == set(initial)
        assert env["_joint_supply_reports"][0]["admitted"]


@pytest.mark.parametrize("name", ["U71", "POWER_DEVICE"])
def test_native_land_geometry_finds_complete_ldo_group_with_renamed_topology(name):
    import cec_pcb
    import cec_synth_pipeline as synth
    comps = {name:"cec-Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm",
             "LOCAL_IN":"cec-Capacitor_SMD:C_0603_1608Metric",
             "LOCAL_OUT":"cec-Capacitor_SMD:C_0603_1608Metric"}
    nl = synth.Netlist(comps={}, nets={
        "VIN":[(name,"6"),("LOCAL_IN","1")],
        "VOUT":[(name,"1"),("LOCAL_OUT","1")],
        "GND":[(name,"2"),(name,"7"),("LOCAL_IN","2"),("LOCAL_OUT","2")],
        "EN":[(name,"4")]})
    reqs = {r:{"owner":name,"pin":pin,"rail":rail,"max_mm":3.5}
            for r,pin,rail in (("LOCAL_IN","6","VIN"),("LOCAL_OUT","1","VOUT"))}
    solutions, report = synth._joint_supply_layouts(nl,comps,name,reqs)
    assert solutions and report["states"] <= report["budget"]
    assert report["ground_return_admission"] == "requires_native_board_and_plane_or_via_proof"
    for solution in solutions:
        assert set(solution) == set(comps)
        boxes = [cec_pcb.courtyard_bbox(comps[r],*p) for r,p in solution.items()]
        assert all(synth._box_clear(a,[b],.099) for i,a in enumerate(boxes) for b in boxes[i+1:])


def test_obstacle_derived_group_seats_find_disconnected_cavity_with_every_member():
    layouts = [{"DATUM":(0.,0.,0.),"A":(-2.,0.,0.),"B":(2.,0.,0.)}]
    def bbox(r,p):
        return (p[0]-.5,p[1]-.5,p[0]+.5,p[1]+.5)
    sites = group.contact_owner_sites(layouts,(10.,3.,0.),part_box=bbox,
        bounds=(1.,1.,30.,30.),obstacles=[(1.,1.,29.,20.)],max_sites=5)
    assert sites and len(sites) <= 5
    assert all(y > 20.5 for x,y,r in sites)
    assert sites == group.contact_owner_sites(layouts,(10.,3.,0.),part_box=bbox,
        bounds=(1.,1.,30.,30.),obstacles=[(1.,1.,29.,20.)],max_sites=5)


def test_native_option_admission_occurs_before_cost_shortlisting():
    import cec_synth_pipeline as synth
    from unittest import mock
    # Complete rejection must not fall back to a lower-cost unproved option.
    comps = {"IC":"owner", "CAP":"cap"}
    nl = synth.Netlist(comps={},nets={"POWER":[("IC","1"),("CAP","1")],
                                    "GND":[("IC","2"),("CAP","2")]})
    import cec_pcb
    with mock.patch.object(cec_pcb,"local_pads",return_value={"1":(0.,-.5),"2":(0.,.5)}), \
         mock.patch.object(cec_pcb,"courtyard_bbox",side_effect=lambda fp,x,y,r:(x-.5,x+.5,y-1,y+1)), \
         mock.patch.object(synth,"_courtyard_info",return_value=(0.,0.,.5,1.)):
        solutions,report=synth._joint_supply_layouts(nl,comps,"IC",{
            "CAP":{"pin":"1","rail":"POWER","max_mm":3.5}},option_admit=lambda c,p:False)
    assert not solutions and report["option_admission_rejections"]["CAP"] > 0
