"""Unrelated hard routes cannot starve a certified support transaction."""
from copy import deepcopy
import inspect
import pytest
import cec_certificate_repair as repair


@pytest.mark.parametrize('names',[('/A','/B'),('/RENAMED_1','/OTHER_2')])
def test_only_same_net_windows_can_defer_support(names):
    first,second=names
    fp=dict(targets=[dict(ref='X42',target_net=first),dict(ref='X81',target_net=second)])
    negotiation=dict(windows=[dict(net=first,priority=[0])])
    original=deepcopy((fp,negotiation))
    result=repair._support_relocation_schedule(fp,negotiation)
    assert result['eligible']==[fp['targets'][1]]
    assert result['deferred']==[fp['targets'][0]]
    assert not result['release_authority'] and not result['exhaustion_is_no_path_proof']
    assert (fp,negotiation)==original


def test_existing_retry_history_is_evaluated_per_net():
    fp=dict(targets=[dict(ref='C42',target_net='/A'),dict(ref='R1',target_net='/B')])
    negotiation=dict(windows=[dict(net=net,priority=[0]) for net in ('/A','/B')])
    prior=dict(algorithm_revision=repair.REPAIR_ALGORITHM_REVISION,attempts=[
        dict(stage='atomic_negotiation',window=dict(net='/A'),decision='blocked_net_search_timeout',
             phases=dict(close=dict(completion=dict(timed_out=True))))])
    result=repair._support_relocation_schedule(fp,negotiation,prior)
    assert [t['target_net'] for t in result['eligible']]==['/A']
    assert [t['target_net'] for t in result['deferred']]==['/B']


def test_legacy_missing_net_retains_conservative_ordering():
    result=repair._support_relocation_schedule(dict(targets=[dict(ref='UNKNOWN')]),
                                              dict(windows=[dict(net='/ANY')]))
    assert not result['eligible'] and result['deferred']
    assert repair._support_relocation_schedule({}, {})['eligible']==[]


def test_normal_coordinator_consumes_partitioned_targets():
    source=inspect.getsource(repair.repair_board)
    assert 'support_schedule = _support_relocation_schedule(' in source
    assert "footprint_targets = list(support_schedule['eligible'])" in source
    assert 'support_relocation_deferred' not in source


def test_native_support_aperture_preempts_only_certified_matching_support(monkeypatch):
    eligible = dict(ref='EXISTING', target_net='/FREE')
    targets = [dict(ref='CAP_A', target_net='/A'), dict(ref='CAP_B', target_net='/B'),
               dict(ref='CAP_C', target_net='/C')]
    schedule = dict(eligible=[eligible], deferred=targets, release_authority=False)
    original = deepcopy(schedule)
    candidate = dict(dx_mm=.2, dy_mm=-.1, generator='native_support_pin_aperture',
        pin_aperture=dict(remaining_route_proof_required=True, release_authority=False))
    calls = []
    def spawn(fn, args, **kwargs):
        calls.append((args, kwargs))
        assert fn.__module__ == 'cec_support_pin_aperture'
        return [candidate] if args[1]['ref'] == 'CAP_A' else []
    monkeypatch.setattr(repair, '_spawn_apply', spawn)
    updated, proposed = repair._native_support_aperture_schedule('native-board', schedule,
        support_limits={'immutable_refs': ['IMMUTABLE']}, craft_policy={'params': {}},
        generated_locked_uuids=('protected-copper',))
    assert schedule == original
    assert updated['eligible'] == [targets[0], eligible]
    assert updated['deferred'] == targets[1:]
    assert proposed == {('CAP_A', '/A'): [candidate]}
    assert len(calls) == 2 and all(k['timeout_s'] == 10 for _, k in calls)
    assert calls[0][0][-1] == ('protected-copper',)
    assert updated['native_pin_aperture_intake']['promoted'] == 1
    assert not updated['native_pin_aperture_intake']['release_authority']


def test_already_eligible_witness_gets_budget_before_speculative_support(monkeypatch):
    speculative = dict(ref='PASSIVE_ALPHA', target_net='/TARGET')
    witnessed = dict(ref='PASSIVE_BETA', target_net='/TARGET')
    schedule = dict(eligible=[speculative, witnessed], deferred=[])
    candidate = dict(dx_mm=.1, dy_mm=-.2, generator='native_support_pin_aperture',
        pin_aperture=dict(remaining_route_proof_required=True, release_authority=False))
    monkeypatch.setattr(repair, '_spawn_apply', lambda fn, args, **kw:
        [candidate] if args[1] == witnessed else [])
    updated, proposals = repair._native_support_aperture_schedule('board', schedule)
    assert updated['eligible'] == [witnessed, speculative]
    assert schedule['eligible'] == [speculative, witnessed]
    assert proposals == {('PASSIVE_BETA', '/TARGET'): [candidate]}
    assert updated['native_pin_aperture_intake']['promoted'] == 0
    assert updated['native_pin_aperture_intake']['witnessed'] == 1


@pytest.mark.parametrize('response', ['timeout', {'error': 'native failure'},
                                     [{}], [dict(generator='cached_proposal')]])
def test_failed_or_unwitnessed_aperture_probe_keeps_route_first_order(monkeypatch, response):
    schedule = dict(eligible=[], deferred=[dict(ref='BYPASS', target_net='/N')])
    def spawn(*args, **kwargs):
        if response == 'timeout':
            raise TimeoutError('bounded native probe')
        return response
    monkeypatch.setattr(repair, '_spawn_apply', spawn)
    updated, proposed = repair._native_support_aperture_schedule('board', schedule)
    assert updated['eligible'] == [] and updated['deferred'] == schedule['deferred']
    assert not proposed
    assert updated['native_pin_aperture_intake']['targets'][0]['error']


def test_aperture_preemption_obeys_outer_budget_and_normal_transaction():
    from types import SimpleNamespace
    schedule = dict(eligible=[], deferred=[dict(ref='BYPASS', target_net='/N')])
    updated, proposed = repair._native_support_aperture_schedule('board', schedule,
        effort=SimpleNamespace(available=lambda _: True, remaining_wall_s=lambda: 9.))
    assert updated['deferred'] == schedule['deferred'] and not proposed
    source = inspect.getsource(repair.repair_board)
    assert source.index('_native_support_aperture_schedule(') < source.index('token="owner-early-')
    assert 'candidate_override=witnessed_supports.get((' in source


def test_deferred_route_window_only_yields_to_witnessed_owner():
    witnessed=dict(ref='OWNER_ALPHA',target_net='/RENAMED_A')
    other=dict(ref='OWNER_BETA',target_net='/RENAMED_B')
    candidates=[dict(dx_mm=.25,dy_mm=0,mobility_companion_refs=[])]
    plan=dict(targets=[other,witnessed],native_pin_lanes=dict(
        targets=[dict(**witnessed,candidates=candidates)]))
    original=deepcopy(plan)
    assert repair._early_owner_targets(plan,dict(deferred=[dict(ref='REMOTE')])) == [
        (witnessed,candidates)]
    assert repair._early_owner_targets(plan,dict(deferred=[])) == [
        (other,None),(witnessed,candidates)]
    assert plan==original
    # Same owner name on another net is not matching evidence.
    plan['native_pin_lanes']['targets'][0]['target_net']='/UNRELATED'
    assert repair._early_owner_targets(plan,dict(deferred=[{}])) == []
    assert repair._early_owner_targets({},dict(deferred=[])) == []


@pytest.mark.parametrize('angle,back,offset',[(0,False,(0,0)),(90,False,(17,-11)),
                                           (180,True,(-7,29)),(270,True,(11,4))])
@pytest.mark.parametrize('fault',['none','no_obstruction','immutable','no_certificate'])
def test_fresh_native_lane_is_required_to_preempt_routes(tmp_path,angle,back,offset,fault):
    import pcbnew
    import cec_support_motion as motion
    from test_owner_escape_articulation import fixture
    board,owner,support,pin,target=fixture(angle=angle,back=back,offset=offset)
    if fault=='no_obstruction':support.Move(pcbnew.VECTOR2I_MM(10,10))
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    original=source.read_bytes()
    at=pin.GetPosition()
    cert=dict(net=pin.GetNetname(),endpoints=[dict(endpoint='a',kind='pad',
        ref=owner.GetReference(),pad=pin.GetNumber(),x_mm=at.x/1e6,y_mm=at.y/1e6),
        dict(endpoint='b',kind='pad',ref='REMOTE',pad='1',x_mm=at.x/1e6+4,y_mm=at.y/1e6)],
        layers=[dict(layer=board.GetLayerName(owner.GetLayer()),
                     endpoint_escape=[dict(endpoint='a',clear_rays=[])])])
    completion=dict(unconn_nets=[pin.GetNetname()],
        final_completion=dict(refused_details=[dict(certificate=cert,net=pin.GetNetname())]))
    if fault=='no_certificate':completion['final_completion']={}
    limits=motion.limits(immutable_refs=[owner.GetReference()] if fault=='immutable' else [])
    result=repair._endpoint_owner_lane_plan_worker(str(source),completion,4,limits)
    assert source.read_bytes()==original
    selected=repair._early_owner_targets(result,dict(deferred=[dict(ref='REMOTE')]))
    assert bool(selected) is (fault=='none')
    assert result['native_pin_lanes']['release_authority'] is False
    assert result['native_pin_lanes']['exhaustion_is_no_path_proof'] is False
    for target,candidates in selected:
        assert target['ref']==owner.GetReference()
        assert all(row['generator']=='owner_stationary_support_lane' for row in candidates)
        assert all(row['escape_lane']['copper_and_reconnect_proof_required'] for row in candidates)


def test_coordinator_dispatches_lanes_through_normal_admission_before_route_retries():
    source=inspect.getsource(repair.repair_board)
    assert '_endpoint_owner_lane_plan_worker' in source
    assert '_early_owner_targets(early_owner_plan, support_schedule)' in source
    assert 'candidate_override=lane_candidates' in source
    assert 'max_branch_tracks=8 if lane_candidates else 64' in source
    assert source.index('_endpoint_owner_lane_plan_worker') < source.index('variants = [("same_layer"')
