"""A bounded force attempt cannot starve the actual native contact fallback."""
from unittest import mock
import pytest
import cec_fr
import cec_force_current as force
from test_force_current import _component_family_fixture


@pytest.mark.parametrize('now,deadline,share,expected',[(0.,10.,.5,5.),
    (2.,10.,.5,6.),(2.,10.,.25,4.),(9.,10.,.5,9.5),(11.,10.,.5,10.)])
def test_one_outer_deadline_never_expands(now,deadline,share,expected):
    assert force._preferred_phase_deadline(deadline,now=now,share=share)==expected


@pytest.mark.parametrize('fault',[dict(share=True),dict(share=0),dict(share=1),
    dict(share=float('nan')),dict(share=float('inf')),dict(deadline=-1),
    dict(deadline=True),dict(now=-1),dict(now=float('nan')),dict(now=True)])
def test_invalid_time_or_share_is_not_a_search_authority(fault):
    values=dict(deadline=10.,now=0.,share=.5);values.update(fault)
    with pytest.raises(ValueError,match='bounded_preferred_force_phase'):
        force._preferred_phase_deadline(**values)


@pytest.mark.parametrize('renamed,reverse',[(False,False),(True,True)])
def test_native_contact_fallback_runs_after_a_preferred_timeout(tmp_path,renamed,reverse):
    path=tmp_path/'native_phase.kicad_pcb'
    board,row,domain,contract=_component_family_fixture(path,renamed=renamed,reverse=reverse)
    clock=[0.];calls=[];sampled=[]
    def route(*args,**kwargs):
        calls.append(kwargs['deadline_monotonic'])
        clock[0]=kwargs['deadline_monotonic']+.01
        return None
    def contacts(*args,**kwargs):
        sampled.append((clock[0],kwargs['deadline']))
        return [],dict(rows=[],stop='sampled_portfolio_complete',physical_no_path_proof=False)
    with mock.patch.object(force.time,'monotonic',side_effect=lambda:clock[0]),\
         mock.patch.object(cec_fr,'_guarded_lastmile_legs',side_effect=route),\
         mock.patch.object(force,'_surface_anchors',side_effect=contacts):
        plan=force._construct(board,str(path),row['net'],domain,contract,
            max_pairs=6,max_bridges=4,deadline=10.,allow_maze=True)
    assert calls==[5.,10.]
    assert len(sampled)==1 and 5. < sampled[0][0] < sampled[0][1] < 10.
    assert [r['search_phase'] for r in plan['attempts']]==['center','surface']
    assert all(r['global_deadline_monotonic']==10. for r in plan['attempts'])
    assert not plan['physical_no_path_proof'] and plan['bridge_count']==0
    assert all(r['additional_wall_budget_granted'] is False for r in plan['phase_wall_budgets'])


def test_early_preferred_refusal_reclaims_unused_wall_time(tmp_path):
    path=tmp_path/'quick_refusal.kicad_pcb'
    board,row,domain,contract=_component_family_fixture(path)
    observed=[]
    with mock.patch.object(force.time,'monotonic',return_value=2.),\
         mock.patch.object(cec_fr,'_guarded_lastmile_legs',return_value=None),\
         mock.patch.object(force,'_surface_anchors',side_effect=lambda *a,**k:
             (observed.append(k['deadline']) or [],dict(rows=[],stop='sampled_portfolio_complete',
                 physical_no_path_proof=False))):
        plan=force._construct(board,str(path),row['net'],domain,contract,
            max_pairs=6,max_bridges=4,deadline=10.,allow_maze=True)
    surface=next(r for r in plan['phase_wall_budgets'] if r['phase']=='surface')
    assert surface['start_monotonic']==2. and surface['deadline_monotonic']==10.
    assert observed==[6.] and surface['unused_preferred_time_reclaimed']
