import copy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import cec_placement_probe_coverage as coverage
import cec_synth_pipeline as synth


def proposals(prefix='PART', offset=0., angle=0.):
    return [dict(ref=prefix + str(owner), kind='measured_exit',
                 position=(offset + float(index), float(owner), angle),
                 budget_priority=0)
            for index in range(4) for owner in range(2)]


def pick(rows, budget, visits):
    return coverage.select(rows, budget, visits=visits,
                           selector=synth._bounded_diverse_move_specs)


@pytest.mark.parametrize('prefix,offset,angle', [
    ('DEVICE', 0., 0.), ('RENAMED', 181.75, 180.), ('BLOCK', -94.5, 90.)])
def test_every_pose_gets_a_turn_before_repeated_rejections(prefix, offset, angle):
    rows = proposals(prefix, offset, angle)
    original = copy.deepcopy(rows)
    visits, selected = {}, []
    for _ in range(4):
        batch = pick(rows, 2, visits)
        assert len(batch) == 2
        assert len({move['ref'] for move in batch}) == 2
        assert coverage.certificate(batch, visits)['untried'] == 2
        selected.extend(coverage.signature(move) for move in batch)
        for move in batch:
            coverage.record(move, visits)
    assert len(set(selected)) == 8
    # Not a no-good exclusion/cache: all poses are eligible again because
    # their external neighbors or copper authority may have changed.
    batch = pick(rows, 2, visits)
    proof = coverage.certificate(batch, visits)
    assert proof['revisited'] == 2 and not proof['cached_admission']
    assert rows == original


def test_first_round_and_uncovered_tier_retain_existing_fair_selector():
    rows = proposals()
    assert pick(rows, 3, {}) == synth._bounded_diverse_move_specs(rows, 3)
    visits = {coverage.signature(move): 1 for move in rows}
    assert pick(rows, 3, visits) == synth._bounded_diverse_move_specs(rows, 3)


def test_distinct_complete_cell_poses_do_not_alias_single_part_moves():
    one = dict(ref='IC', kind='reseat', position=(1., 2., 0.))
    macro = dict(one, placements={'IC': (1., 2., 0.), 'BYPASS': (2., 2., 0.)})
    assert coverage.signature(one) != coverage.signature(macro)
    reordered = dict(macro, placements={'BYPASS': (2., 2., 360.), 'IC': (1., 2., 0.)})
    assert coverage.signature(macro) == coverage.signature(reordered)
    visits = {}; coverage.record(macro, visits)
    macro['placements']['BYPASS'] = (2.1, 2., 0.)
    assert pick([one, macro], 2, visits) == [one, macro]


@pytest.mark.parametrize('pose', [None, (), (1, 2), (float('nan'), 0, 0),
                                  (float('inf'), 0, 0), ('bad', 0, 0)])
def test_unknown_geometry_is_not_a_cached_rejection(pose):
    row = dict(ref='UNKNOWN', kind='move', position=pose)
    visits = {}
    coverage.record(row, visits)
    assert not visits and coverage.signature(row) is None
    assert pick([row], 1, visits) == [row]


@pytest.mark.parametrize('budget', [0, 1, 3, 8, 24])
def test_strict_work_cap_with_mixed_history(budget):
    rows = proposals()
    visits = {coverage.signature(row): index % 3 for index, row in enumerate(rows)}
    chosen = pick(rows, budget, visits)
    assert len(chosen) == min(budget, len(rows))
    levels = [visits[coverage.signature(row)] for row in chosen]
    assert levels == sorted(levels)


def test_history_is_shared_between_epochs_but_not_repair_invocations():
    histories = []
    def epoch(cfg, current, **kwargs):
        visits = kwargs['probe_visits']
        histories.append(visits)
        coverage.record(proposals()[0], visits)
        count = visits[coverage.signature(proposals()[0])]
        return current, dict(changed=True, accepted_count=1, ok=count == 2,
                             result_key=[3-count], rounds=[])
    cfg = SimpleNamespace(params={})
    with patch.object(synth, 'repair_placement_craft', side_effect=epoch):
        for _ in range(2):
            _, report = synth.repair_placement_craft_epochs(cfg, object(), epochs=3)
            assert report['ok'] and report['accepted_count'] == 2
    assert histories[0] is histories[1]
    assert histories[2] is histories[3]
    assert histories[0] is not histories[2]


@pytest.mark.parametrize('prefix,offset,angle', [
    ('DEVICE', 0., 0.), ('RENAMED', 181.75, 180.), ('BLOCK', -94.5, 90.)])
def test_failed_batch_leaves_a_real_frontier_not_a_geometric_plateau(prefix,offset,angle):
    rows=proposals(prefix,offset,angle)
    visits={}
    for move in pick(rows,2,visits):coverage.record(move,visits)
    remaining=coverage.frontier(rows+rows,visits)
    assert remaining['population']==16 and remaining['unique']==8
    assert remaining['visited']==2 and remaining['unvisited']==6
    assert coverage.can_advance(remaining,2)
    assert not remaining['cached_admission'] and not remaining['exhaustion_is_no_path_proof']
    assert not coverage.can_advance(remaining,0)
    assert not coverage.can_advance(remaining,2,evaluation_budget_exhausted=True)
    for move in rows:coverage.record(move,visits)
    assert not coverage.can_advance(coverage.frontier(rows,visits),2)


def test_malformed_or_empty_frontier_cannot_authorize_more_work():
    for rows in ([],[{'ref':'X','position':None}]):
        assert not coverage.can_advance(coverage.frontier(rows,{}),1)


@pytest.mark.parametrize('stop,unvisited,expected_calls', [
    ('proposal_budget_exhausted',3,2),('proposal_budget_exhausted',0,1),
    ('evaluation_budget_exhausted',3,1),('plateau',3,1)])
def test_next_epoch_may_search_unvisited_poses_without_changing_incumbent(stop,unvisited,expected_calls):
    cfg=SimpleNamespace(params={});candidate=object();seen=[]
    def repair(cfg,current,**kwargs):
        seen.append(kwargs['probe_visits'])
        assert current is candidate
        return current,dict(changed=False,accepted_count=0,ok=False,
            result_key=[0,2],rounds=[],stop_reason=stop,
            proposal_frontier={'unvisited':unvisited})
    with patch.object(synth,'repair_placement_craft',side_effect=repair):
        result,report=synth.repair_placement_craft_epochs(cfg,candidate,epochs=2)
    assert result is candidate and not report['changed'] and report['accepted_count']==0
    assert len(seen)==expected_calls
    if expected_calls==2:assert seen[0] is seen[1]


def test_no_batch_receipt_claims_exhaustive_geometry():
    for reason in ('no_monotonic_legal_improvement','sampled_batch_without_improvement'):
        report=synth.placement_craft_blocker_certificate({}, {'reason':reason,
            'proposal_frontier':{'unvisited':0,'exhaustion_is_no_path_proof':False}})
        assert not report['neighborhood_exhausted']
        assert report['proposal_frontier']['unvisited']==0


@pytest.mark.parametrize('mode', ['improves', 'no_gain', 'timeout', 'deadline'])
@pytest.mark.parametrize('ref,offset', [('CELL', 0.), ('RENAMED', 80.)])
@pytest.mark.parametrize('proxy_only_overlap', [False, True])
def test_real_round_loop_visits_new_poses_without_accepting_a_failed_batch(
        monkeypatch, mode, ref, offset, proxy_only_overlap):
    """Exercise the actual repair loop; only native geometry work is stubbed."""
    import cec_operation_budget
    import cec_placement_station_groups as stations
    cfg=SimpleNamespace(params={}, pins={})
    incumbent=SimpleNamespace(P={ref:(offset,0.,0.)}, back_refs=set(), W=200., H=200.)
    before=copy.deepcopy(incumbent.P)
    moves=[dict(ref=ref,kind='measured_exit',position=(offset+x,0.,0.)) for x in (1.,2.,3.)]
    evidence={'ok':False, 'score':1}
    if proxy_only_overlap:
        evidence['native_geometry']={'ok':True,'domains':['assembly'],'violations':[]}
    monkeypatch.setattr(synth,'View',lambda cfg:SimpleNamespace(nl=SimpleNamespace(nets={})))
    monkeypatch.setattr(synth,'_fp_of',lambda nl:{})
    monkeypatch.setattr(synth,'_compact_switch_cell_dependencies',lambda nl:{})
    monkeypatch.setattr(synth,'_declared_blueprint_refs',lambda cfg:set())
    monkeypatch.setattr(synth,'materialize',lambda *a,**k:None)
    monkeypatch.setattr(synth,'placement_craft_evidence',lambda *a,**k:copy.deepcopy(evidence))
    monkeypatch.setattr(synth,'_extend_footprint_map_from_board',lambda *a,**k:{})
    proxy_pairs={('unrelated-envelope','other-envelope')} if proxy_only_overlap else set()
    monkeypatch.setattr(synth,'_overlap_pairs',lambda *a,**k:set(proxy_pairs))
    monkeypatch.setattr(synth,'placement_craft_key',lambda e:(e['score'],))
    monkeypatch.setattr(synth,'placement_craft_repair_key',lambda e,n:(n,e['score']))
    monkeypatch.setattr(synth,'_placement_stranded_refs',lambda e:set())
    monkeypatch.setattr(synth,'_placement_atomic_multirail_primary',lambda *a:False)
    monkeypatch.setattr(synth,'_placement_atomic_multirail_transition',lambda *a:None)
    monkeypatch.setattr(synth,'_courtyard_overlap_move_specs',lambda *a,**k:[])
    monkeypatch.setattr(synth,'_placement_craft_move_specs',lambda *a,**k:copy.deepcopy(moves))
    monkeypatch.setattr(synth,'_placement_incremental_supply_moves',lambda *a,**k:([],{}))
    monkeypatch.setattr(synth,'_placement_stranded_contact_moves',lambda *a,**k:[])
    monkeypatch.setattr(synth,'_expand_topology_coupled_move',lambda move,*a,**k:move)
    monkeypatch.setattr(synth,'_placement_reserved_copper_collisions',lambda *a,**k:[])
    legalization_calls=[]
    monkeypatch.setattr(synth,'_placement_one_step_local_legalizations',
        lambda *a,**k:legalization_calls.append(True) or [])
    monkeypatch.setattr(synth,'_independent_monotonic_finalist_batches',lambda *a,**k:[])
    monkeypatch.setattr(stations,'from_board',lambda *a:{})
    monkeypatch.setattr(stations,'complete_eviction',lambda current,placements,variant,*a,**k:
        dict(ok=True,added_refs=[],placements=variant))
    monkeypatch.setattr(cec_operation_budget,'round_admission',lambda *a,**k:
        dict(start=mode!='deadline'))
    seen=[]
    def evaluate(cfg,payloads,**kwargs):
        rows=[]
        for payload in payloads:
            # The rejected first pose must never mutate the input incumbent.
            assert incumbent.P==before
            pose=payload['candidate'].P[ref]
            seen.append(pose)
            improves=mode=='improves' and pose==moves[1]['position']
            measured=copy.deepcopy(evidence)
            measured.update(ok=improves,score=0 if improves else 1)
            rows.append(dict(ok=True,evidence=measured))
        return rows,dict(budget_exhausted=bool(payloads) and mode=='timeout')
    monkeypatch.setattr(synth,'_evaluate_placement_craft_trials',evaluate)
    monkeypatch.setattr(synth,'_certify_craft_incumbent',lambda cfg,current,evidence,overlap,*a,**k:
        (evidence,overlap))
    result,report=synth.repair_placement_craft(cfg,incumbent,max_trials=1,rounds=2)
    assert incumbent.P==before
    assert len(seen)==(1 if mode in ('timeout','deadline') else 2)
    assert len(set(seen))==len(seen)
    assert not report['rounds'][0]['accepted']
    assert report['rounds'][0]['baseline_overlap']==0
    assert report['rounds'][0]['baseline_proxy_overlap']==int(proxy_only_overlap)
    assert not report['rounds'][0]['rejection_counts'].get('introduced_overlap',0)
    assert not legalization_calls
    assert report['accepted_count']==int(mode=='improves')
    if mode=='improves':
        assert result.P[ref]==moves[1]['position'] and report['ok']
    else:
        assert result is incumbent and not report['changed']
        assert report['stop_reason']==('proposal_budget_exhausted' if mode=='no_gain'
                                      else 'evaluation_budget_exhausted')
