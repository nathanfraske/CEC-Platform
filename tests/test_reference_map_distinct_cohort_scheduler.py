"""Pure scheduling tests: no boards, source grades, native jobs or source edits."""
import ast
from pathlib import Path
import pytest

DRIVER=Path(__file__).resolve().parents[1]/'build/root_received_reference_map_batch_20261022.py'
TREE=ast.parse(DRIVER.read_text())
NS={}
exec(compile(ast.Module(body=[n for n in TREE.body if isinstance(n,ast.FunctionDef)and n.name in('fair_cohort_seeds','smaller_cohort_limits')],type_ignores=[]),str(DRIVER),'exec'),NS)
fair=NS['fair_cohort_seeds']
smaller=NS['smaller_cohort_limits']

def rows(*cohorts):return [dict(seed_index=i,ordered_owner_uuids=list(c))for i,c in enumerate(cohorts)]

def test_distinct_neighborhoods_before_greedy_order_alternates():
    assert fair(rows('abc','bca','de','fg','cab'),8)==[0,2,3,1,4]

def test_no_ordered_domain_retired_or_claimed_negative():
    q=rows('ab','ba');before=repr(q)
    assert fair(q,8)==[0,1]and repr(q)==before

def test_bounded_first_eight_distinct_before_caged_aliases():
    q=rows(*(['abc']*8+['de','fg','hi','jk','lm','no','pq','rs']))
    assert fair(q,8)==[0,8,9,10,11,12,13,14]

def test_source_acceptance_rebind_changes_rank_no_stale_seed_authority():
    assert fair(rows('ab','ba','cd'),8)==[0,2,1]
    assert fair(rows('cd','ef','fe'),8)==[0,1,2]

@pytest.mark.parametrize('limit',[0,9,True,False,1.0,None])
def test_invalid_limits(limit):
    with pytest.raises(ValueError):fair(rows('a'),limit)

@pytest.mark.parametrize('q',[
    [dict(seed_index=32,ordered_owner_uuids=['a'])],
    [dict(seed_index=True,ordered_owner_uuids=['a'])],
    [dict(seed_index=0,ordered_owner_uuids=[])],
    [dict(seed_index=0,ordered_owner_uuids=['a','a'])],
    [dict(seed_index=0,ordered_owner_uuids=[''])],
    [dict(seed_index=0,ordered_owner_uuids=[1])],
    [dict(seed_index=0,ordered_owner_uuids=list('abcdefghi'))],
    [dict(seed_index=0,ordered_owner_uuids=['a']),dict(seed_index=0,ordered_owner_uuids=['b'])],
])
def test_bad_inventory_refuses(q):
    with pytest.raises(ValueError):fair(q,8)

def test_empty_frontier_finitely_stops():assert fair([],8)==[]

def test_live_source_grade_and_whole_native_gates_remain_wired():
    text=DRIVER.read_text()
    for term in ('dense.source_context(source,grade,board_hint)',
        "if queue_sha!=sha:","grade_sha256=force._hash(grade)",
        "source=child;sha=r['candidate_sha256']", "if not accepted and not wide:break",
        'for turn in range(a.distinct_cohorts if wide else a.passes)',
        "introduced=list((current-known).elements())", "not introduced and r['source_opens']==r['candidate_opens']",
        "maps.receive(source,child,proposal)","source_partitions==partitions(child,deadline)",
        "force._code_identity()==epoch and(not wide or time.monotonic()<=deadline)"):
        assert term in text

def test_legacy_order_and_limits_still_explicit():
    text=DRIVER.read_text()
    assert "else:seeds=range(a.seeds)"in text
    assert '1<=a.passes<=3 and 1<=a.seeds<=4'in text
    assert "default=None"in text and '0<a.wall_s<=120.'in text


@pytest.mark.parametrize('actual,current,expected',[(8,8,[4,2,1]),(8,4,[2,1]),(8,2,[1]),(8,1,[]),(3,8,[2,1]),(2,8,[1]),(1,8,[]),(4,8,[2,1])])
def test_smaller_prefixes_are_actual_distinct_same_seed_domains(actual,current,expected):
    assert smaller(actual,current)==expected


@pytest.mark.parametrize('actual,current',[(0,8),(9,8),(True,8),(8,False),(8,0),(8,9),(2.0,8)])
def test_smaller_prefix_invalid_bounds_refuse(actual,current):
    with pytest.raises(ValueError):smaller(actual,current)


def test_smaller_fallback_shares_attempt_and_wall_budget_and_rebinds():
    text=DRIVER.read_text()
    assert 'assert not a.smaller_cohorts or a.distinct_cohorts is not None'in text
    assert 'for turn in range(a.distinct_cohorts if wide else a.passes)'in text
    assert "queue.insert(0,(seed,sizes[0]))"in text
    assert "str(exc)=='no_readable_clear_opposite_face_mapping_in_bounded_domain'"in text
    assert 'maximum_components=maximum_components'in text
    assert 'queue_sha!=sha'in text
    assert 'time.monotonic()<=deadline'in text


def test_fallback_prefix_does_not_drop_owner_or_alter_actual_order():
    owners=list('abcdefgh');current=8;tried=[]
    for _ in range(8):
        tried.append(owners[:current]);options=smaller(len(owners),current)
        if not options:break
        current=options[0]
    assert [len(r)for r in tried]==[8,4,2,1]
    assert all(r[0]=='a'for r in tried)and owners==list('abcdefgh')
