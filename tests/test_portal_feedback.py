"""Exact dead-end feedback is finite, local and never an admission waiver."""
import copy
import math
from unittest import mock

import pytest
import cec_portal_feedback as feedback
import cec_precision_route as precision


def evidence():
    return {"attempts": [{"start": {"p": [0,-.2], "n": [0,.2],
                          "route_heading": [1,0]},
        "grid": {"status": "grid_exhausted", "visited": 20, "max_visited": 1000,
                 "route_start_mm": [0,0], "route_end_mm": [20,0],
                 "nearest_frontier_mm": [1,1],
                 "dominant_blockers": [{"kind": "pad", "ref": "ANY"}]}}]}


@pytest.mark.parametrize("angle", [0,45,90,180,270])
def test_dead_end_observation_is_rigid_transform_invariant(angle):
    e=evidence();grid=e["attempts"][0]["grid"]
    def transform(p):
        ca,sa=math.cos(math.radians(angle)),math.sin(math.radians(angle))
        return [p[0]*ca-p[1]*sa+37,p[0]*sa+p[1]*ca-21]
    for key in ("route_start_mm","route_end_mm","nearest_frontier_mm"):
        grid[key]=transform(grid[key])
    before=copy.deepcopy(e)
    found=feedback.stranded_start_observations(e)
    assert len(found)==1
    assert found[0]["progress_mm"]==round(math.sqrt(2),6)
    assert e==before


@pytest.mark.parametrize("mode", ["timeout","state_limit","progress","missing","nan","small"])
def test_incomplete_or_nonlocal_search_never_excludes_portal(mode):
    e=evidence();g=e["attempts"][0]["grid"]
    if mode=="timeout":g["status"]="deadline_exhausted"
    if mode=="state_limit":g["visited"]=g["max_visited"]
    if mode=="progress":g["nearest_frontier_mm"]=[15,0]
    if mode=="missing":del g["nearest_frontier_mm"]
    if mode=="nan":g["nearest_frontier_mm"]=[float('nan'),0]
    if mode=="small":g["route_end_mm"]=[3,0]
    assert feedback.stranded_start_observations(e)==[]


def test_geometry_key_does_not_confuse_polarity_or_heading():
    row=evidence()["attempts"][0]["start"]
    key=feedback.portal_geometry_key(row)
    assert feedback.portal_geometry_key(dict(row,p=row['n'],n=row['p'])) != key
    assert feedback.portal_geometry_key(dict(row,route_heading=[-1,0])) != key
    assert feedback.portal_geometry_key({}) is None


@pytest.mark.parametrize("row", [
    {"p": [0, 1, 2], "n": [0], "route_heading": [1, 0]},
    {"p": [0, 0], "n": [0, 1], "route_heading": [float("nan"), 0]},
    {"p": None, "n": [0, 1], "route_heading": [1, 0]},
])
def test_malformed_portal_geometry_is_not_excluded(row):
    assert feedback.portal_geometry_key(row) is None
    report = evidence()
    report["attempts"][0]["start"] = row
    assert feedback.stranded_start_observations(report) == []


def test_wrapper_refills_with_witness_and_shared_deadline():
    first={"refused":"no corridor","portal_evidence":evidence()}
    accepted={"route_mode":"admitted-exact-beam"}
    with mock.patch.object(precision,"_route_coupled_via_portal_beam",
                           side_effect=[first,accepted]) as beam, \
            mock.patch.object(precision,"_deadline_expired",return_value=False):
        result=precision._route_coupled_via_portals(object(),{},(),deadline=123.0)
    assert result.get("refused") is None
    assert result["portal_refill"]["selected_round"]==1
    assert beam.call_args_list[1].kwargs["deadline"]==123.0
    assert len(beam.call_args_list[1].kwargs["_excluded_start_portals"])==1


@pytest.mark.parametrize("mode", ["success","timeout","prequalified","zero_limit"])
def test_wrapper_preserves_baseline_and_does_not_loop(mode):
    report={"route_mode":"unchanged"} if mode=='success' else {
        "refused":"no corridor","portal_evidence":evidence()}
    kwargs={"deadline":123.0}
    if mode=='prequalified':kwargs['start_prequalified']={}
    if mode=='zero_limit':kwargs['max_portal_refills']=0
    with mock.patch.object(precision,"_route_coupled_via_portal_beam",return_value=report) as beam, \
            mock.patch.object(precision,"_deadline_expired",return_value=mode=='timeout'):
        result=precision._route_coupled_via_portals(object(),{},(),**kwargs)
    assert beam.call_count==1
    assert result==report


def test_repeated_observation_stops_refill():
    with mock.patch.object(precision,"_route_coupled_via_portal_beam",
        side_effect=lambda *a,**k:{"refused":"no corridor","portal_evidence":evidence()}) as beam, \
        mock.patch.object(precision,"_deadline_expired",return_value=False):
        result=precision._route_coupled_via_portals(object(),{},(),max_portal_refills=20)
    assert beam.call_count==2
    assert result['portal_refill']['excluded_start_portals']==1


def test_distinct_dead_ends_still_obey_refill_limit_and_share_cache():
    def next_dead_end(*args, **kwargs):
        row = evidence()
        x = len(kwargs["_excluded_start_portals"])
        row["attempts"][0]["start"]["p"][0] = x
        row["attempts"][0]["start"]["n"][0] = x
        return {"refused": "no corridor", "portal_evidence": row}

    with mock.patch.object(precision, "_route_coupled_via_portal_beam",
                           side_effect=next_dead_end) as beam, \
            mock.patch.object(precision, "_deadline_expired", return_value=False):
        result = precision._route_coupled_via_portals(
            object(), {}, (), max_portal_refills=2, deadline=123.0)
    assert beam.call_count == 3
    assert result["portal_refill"]["selected_round"] == 2
    assert result["portal_refill"]["excluded_start_portals"] == 2
    cache = beam.call_args_list[0].kwargs["portal_screen_cache"]
    assert all(call.kwargs["portal_screen_cache"] is cache
               and call.kwargs["deadline"] == 123.0
               for call in beam.call_args_list)


def test_exclusions_are_transaction_local_even_with_shared_cache():
    shared_cache = {}
    with mock.patch.object(precision, "_route_coupled_via_portal_beam",
                           side_effect=lambda *a, **k: {
                               "refused": "no corridor",
                               "portal_evidence": evidence()}) as beam, \
            mock.patch.object(precision, "_deadline_expired", return_value=False):
        for _ in range(2):
            precision._route_coupled_via_portals(
                object(), {}, (), portal_screen_cache=shared_cache)
    assert beam.call_count == 4
    assert not beam.call_args_list[0].kwargs["_excluded_start_portals"]
    assert not beam.call_args_list[2].kwargs["_excluded_start_portals"]


@pytest.mark.parametrize("policy", [
    {"max_progress_fraction": -0.1}, {"max_progress_fraction": 0.5},
    {"max_progress_fraction": float("nan")}, {"local_radius_mm": -1},
    {"local_radius_mm": float("inf")},
])
def test_invalid_locality_policy_is_rejected(policy):
    with pytest.raises(ValueError, match="locality policy"):
        feedback.stranded_start_observations(evidence(), **policy)


def negative():
    return {"refused": "no finite paired dogbone", "admission": {
        "direct": {"p": {"ok": False}},
        "detour": {"deadline_exhausted": False, "path_pairs_checked": 32}}}


def test_negative_probe_reuses_only_identical_query_and_copies_evidence():
    cache = feedback.PortalProbeCache()
    solve = mock.Mock(side_effect=negative)
    report = cache.probe(("policy", "exact-geometry"), solve, expired=lambda: False)
    report["admission"]["direct"]["p"]["ok"] = True
    again = cache.probe(("policy", "exact-geometry"), solve, expired=lambda: False)
    assert again == negative()
    assert solve.call_count == 1 and cache.hits == 1
    for key in (("other-policy", "exact-geometry"), ("policy", "other-geometry")):
        cache.probe(key, solve, expired=lambda: False)
    assert solve.call_count == 3


@pytest.mark.parametrize("mode", ["positive", "deadline", "nested_deadline",
                                   "missing_evidence", "expired", "exception"])
def test_incomplete_and_positive_probes_never_poison_cache(mode):
    cache = feedback.PortalProbeCache()
    report = negative()
    if mode == "positive": del report["refused"]
    if mode == "deadline": report["refused"] = "paired search deadline exhausted"
    if mode == "nested_deadline":
        report["admission"]["detour"]["deadline_exhausted"] = True
    if mode == "missing_evidence": report.pop("admission")
    solve = mock.Mock(return_value=report)
    if mode == "exception": solve.side_effect = RuntimeError("failed geometry query")
    for _ in range(2):
        if mode == "exception":
            with pytest.raises(RuntimeError):
                cache.probe("same", solve, expired=lambda: False)
        else:
            cache.probe("same", solve, expired=lambda: mode == "expired")
    assert solve.call_count == 2 and cache.hits == 0 and not cache.rows


def test_negative_probe_storage_bounded_and_deadline_still_authoritative():
    cache = feedback.PortalProbeCache(limit=1)
    solve = mock.Mock(side_effect=negative)
    for key in ("first", "second", "second", "first"):
        cache.probe(key, solve, expired=lambda: False)
    assert len(cache.rows) == 1 and solve.call_count == 3 and cache.hits == 1
    cache.probe("first", solve, expired=lambda: True)
    assert solve.call_count == 4


def test_early_feedback_and_negative_cache_are_bounded_and_transaction_local():
    def dead_end(*args, **kwargs):
        row = evidence()
        x = len(kwargs["_excluded_start_portals"])
        row["attempts"][0]["start"]["p"][0] = x
        return {"refused": "no corridor", "portal_evidence": row}

    with mock.patch.object(precision, "_route_coupled_via_portal_beam", side_effect=dead_end) as beam, \
            mock.patch.object(precision, "_deadline_expired", return_value=False):
        for _ in range(2):
            precision._route_coupled_via_portals(object(), {}, (), max_portal_refills=2)
    calls = beam.call_args_list
    assert [c.kwargs["_yield_stranded_portals"] for c in calls] == [True, True, False]*2
    assert calls[0].kwargs["_negative_probe_cache"] is calls[2].kwargs["_negative_probe_cache"]
    assert calls[0].kwargs["_negative_probe_cache"] is not calls[3].kwargs["_negative_probe_cache"]


@pytest.mark.parametrize("kwargs", [{"start_prequalified": {}},
                                   {"early_portal_feedback": False},
                                   {"max_portal_refills": 0}])
def test_fixed_or_disabled_portals_cannot_yield_early(kwargs):
    with mock.patch.object(precision, "_route_coupled_via_portal_beam",
                           return_value={"refused": "none"}) as beam:
        precision._route_coupled_via_portals(object(), {}, (), **kwargs)
    assert beam.call_args.kwargs["_yield_stranded_portals"] is False


@pytest.mark.parametrize("early", [False, True])
def test_native_beam_yields_before_spending_other_combinations_and_rolls_back(early):
    pcbnew = pytest.importorskip("pcbnew")
    board = pcbnew.BOARD()
    for a, b in (((0,0),(40,0)), ((40,0),(40,25)),
                 ((40,25),(0,25)), ((0,25),(0,0))):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts); board.Add(edge)
    for name in ("P", "N", "GND"):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    pair = {"name":"RENAMED_BUS", "p":"P", "n":"N", "width":.2, "gap":.13}
    endpoints = ((4,9), (34,9), (4,11), (34,11))

    def closed_pocket(*args, **kwargs):
        start, end = kwargs["start_center"], kwargs["end_center"]
        kwargs["diagnostics"].update(status="grid_exhausted", visited=1,
            max_visited=1000, route_start_mm=start, route_end_mm=end,
            nearest_frontier_mm=start)
        return None

    with mock.patch.object(precision, "_grid_coupled_path", side_effect=closed_pocket):
        report = precision._route_coupled_via_portal_beam(
            board, pair, endpoints, max_fanins_per_side=2, max_portal_pairs=8,
            _yield_stranded_portals=early)
    assert report.get("refused")
    attempts = report["portal_evidence"]["attempts"]
    assert len(attempts) == 1 if early else len(attempts) > 1
    assert bool(report["portal_evidence"].get("early_refill")) is early
    # The real local escape solver creates native tracks. None may survive a
    # rejected shared middle, regardless of early feedback being enabled.
    assert list(board.GetTracks()) == []
