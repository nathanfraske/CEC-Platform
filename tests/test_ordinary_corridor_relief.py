"""Ordinary corridors must supply actionable but electrically honest feedback."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from shapely.geometry import box
from shapely.ops import unary_union
import cec_pour_plan as planner


def fixture(*, fixed=(), mode=True, allowed=None, layers=('F.Cu',), width=1.,
            records=None, approach=None, unguard=0.):
    records = records if records is not None else [dict(owner='cell',kind='footprint_body',
        net='logic',detail='body',geometry=box(14,0,16,20))]
    region=box(0,0,30,20)
    spaces={lay:planner._LayerSpace(region,[r['geometry'] for r in records],width/2,
        f_allow=allowed if lay=='F.Cu' else None,approach=approach,
        half_neck=planner.W_NECK/2,neck_unguard=unguard) for lay in layers}
    st=dict(region=region,layers=list(layers),reqw={lay:width for lay in layers},
        spaces=spaces,obstacle_records={lay:records for lay in layers},
        fixed_authority_refs=fixed,relief_diagnostics=mode,f_allow=allowed)
    cor=SimpleNamespace(ga=SimpleNamespace(gid=2,attach=box(1,9,3,11),spot=None),
        gb=SimpleNamespace(gid=5,attach=box(27,9,29,11),spot=None),cands=[],diag={})
    return cor,st,spaces


def generate(cor,st):
    with patch.object(planner,'_endpoints_for_layer',
            return_value=((2.,10.),False,(),(28.,10.),False,())), \
         patch.object(planner,'_projection_aligned_pairs',return_value=[]):
        planner._make_candidates(cor,st,None)
    return st.get('bottlenecks',{})


def test_ordinary_no_path_names_whole_movable_cell_without_mutating_copper():
    cor,st,spaces=fixture()
    before=spaces['F.Cu'].free.wkb
    evidence=generate(cor,st)['F.Cu:2->5']
    assert evidence['failure']=='no-path'
    assert evidence['relief_sets'][0]['owners']==['cell']
    assert len(evidence['relief_sets'][0]['path_mm'])>=2
    assert evidence['candidate_acceptance_required']
    assert not cor.cands and spaces['F.Cu'].free.wkb==before
    assert cor.ga.spot is None and cor.gb.spot is None


def test_fixed_obstacle_is_not_a_relocation_witness():
    cor,st,_=fixture(fixed=('cell',))
    evidence=generate(cor,st)['F.Cu:2->5']
    assert evidence['immovable_owners']==['cell']
    assert not evidence['relief_sets'] and not evidence['wide_relief_sets']


def test_front_layer_categorical_allowed_region_survives_counterfactual():
    allowed=unary_union([box(0,0,12,20),box(18,0,30,20)])
    cor,st,_=fixture(allowed=allowed)
    evidence=generate(cor,st)['F.Cu:2->5']
    assert not evidence['relief_sets']
    assert evidence['all_movable_removal_tested']
    assert evidence['all_movable_removal_restores_path'] is False


def test_overlong_neck_does_not_become_a_false_relief_success():
    records=[dict(owner=name,kind='footprint',net='other',detail='pad',geometry=shape)
        for name,shape in [('top',box(4,0,26,8)),('bottom',box(4,12,26,20)),
                           ('irrelevant',box(14,17,16,19))]]
    cor,st,_=fixture(width=8.,records=records,approach=box(0,0,30,20),
                     fixed=('top','bottom'))
    evidence=generate(cor,st)['F.Cu:2->5']
    assert evidence['failure']=='neck-too-long'
    assert not evidence['relief_sets'] and not evidence['wide_relief_sets']
    assert evidence['all_movable_removal_restores_path'] is False


def test_successful_other_layer_avoids_unneeded_diagnosis_and_clears_stale_cut():
    cor,st,_=fixture(layers=('F.Cu','B.Cu'))
    st['spaces']['B.Cu']=planner._LayerSpace(st['region'],[],.5)
    st['bottlenecks']={'F.Cu:2->5':{'old':True},'F.Cu:9->10':{'unrelated':True}}
    with patch.object(planner,'_corridor_relief_evidence',side_effect=AssertionError('unneeded')):
        evidence=generate(cor,st)
    assert len(cor.cands)==1 and cor.cands[0]['layer']=='B.Cu'
    assert evidence=={'F.Cu:9->10':{'unrelated':True}}


@pytest.mark.parametrize('mode,expected',[(False,None),('light',(6,0,1)),(True,(18,10,4))])
def test_modes_bound_diagnosis_and_disabled_is_explicitly_unknown(mode,expected):
    cor,st,_=fixture(mode=mode)
    with patch.object(planner,'_corridor_relief_evidence',return_value={'relief_sets':[]}) as probe:
        evidence=generate(cor,st)['F.Cu:2->5']
    if expected is None:
        probe.assert_not_called()
        assert evidence['skipped']=='bounded_candidate_sweep'
        assert not evidence['candidate_acceptance_required']
    else:
        assert tuple(probe.call_args.kwargs[k] for k in ('owner_cap','pair_cap','max_cardinality'))==expected


def test_space_rebuild_preserves_nondefault_raster_guard_and_width():
    cor,st,spaces=fixture(width=3.,approach=box(0,0,10,20),unguard=.375)
    rebuilt=spaces['F.Cu'].rebuild([])
    assert rebuilt._construction==spaces['F.Cu']._construction
    assert rebuilt._construction['half_w']==1.5
    assert rebuilt._construction['neck_unguard']==.375


def bounded_probe(cor,st,space,**budget):
    with patch.object(planner,'_endpoints_for_layer',
            return_value=((2.,10.),False,(),(28.,10.),False,())), \
         patch.object(planner,'_projection_aligned_pairs',return_value=[]):
        return planner._corridor_relief_evidence(cor,st,'F.Cu',space,**budget)


@pytest.mark.parametrize('budget',[dict(max_attempts=0),dict(max_seconds=0.)])
def test_exhausted_budget_does_not_fabricate_no_path_proof(budget):
    cor,st,spaces=fixture()
    result=bounded_probe(cor,st,spaces['F.Cu'],**budget)
    assert result['budget_exhausted']
    assert not result['relief_sets']
    for scope in ('all_ranked','all_movable'):
        assert result[scope+'_removal_tested'] is False
        assert result[scope+'_removal_restores_path'] is None
    assert result['diagnostic_budget']['completed']==0


def test_proven_broad_cut_survives_later_budget_exhaustion():
    records=[dict(owner=name,kind='footprint',net='other',detail='pad',geometry=shape)
        for name,shape in [('wall',box(14,0,16,20)),('far',box(4,17,6,19))]]
    cor,st,spaces=fixture(records=records)
    result=bounded_probe(cor,st,spaces['F.Cu'],max_attempts=1)
    assert result['budget_exhausted']
    assert set(result['relief_sets'][0]['owners'])=={'wall','far'}
    assert result['all_movable_removal_tested'] is True
    assert result['all_movable_removal_restores_path'] is True
    assert result['diagnostic_budget']['completed']==1


def test_pathfinder_deadline_is_not_returned_as_geometric_failure():
    space=planner._LayerSpace(box(0,0,30,20),[],.5)
    with pytest.raises(planner._ReliefBudgetExceeded):
        planner._find_path(space,(2,10),(28,10),deadline=0.)
