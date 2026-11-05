"""Late constructive failures cannot be hidden behind early seat failures."""
from copy import deepcopy
import pytest
from cec_portal_feedback import retain_rejection_witness


def row(index,reason='copper seat'):
    return dict(reason=reason,score=[float(index),0.,0,0.,1.3],
        portal=dict(p=[index,0],n=[index,.75],side='start',sign=-1),allow_detour=True)


def test_late_field_clear_fanin_failure_survives_thousands_of_cheap_seat_refusals():
    rows=[]
    for index in range(1000):retain_rejection_witness(rows,row(index))
    rare=row(2000,'no clear bounded paired terminal stub');rare['local_search']={'path_pairs_checked':32}
    retain_rejection_witness(rows,rare)
    for index in range(1000,1200):retain_rejection_witness(rows,row(index))
    assert len(rows)==24 and rare in rows
    assert min(r['score'][0] for r in rows if r['reason']=='copper seat')==0
    assert rows[0]['reason']=='copper seat'


@pytest.mark.parametrize('order',((0,1,2),(2,1,0),(1,0,2)))
def test_reasons_get_bounded_nearest_examples_without_aliasing(order):
    rows=[];witnesses=[row(i,'reason '+str(i%3)) for i in range(18)]
    before=deepcopy(witnesses)
    for reason in order:
        for q in witnesses:
            if q['reason']=='reason '+str(reason):retain_rejection_witness(rows,q,limit=6)
    assert len(rows)==6 and {r['reason'] for r in rows}=={'reason 0','reason 1','reason 2'}
    assert [r['score'][0] for r in rows]==[0.,1.,2.,3.,4.,5.]
    rows[0]['portal']['p'][0]=999
    assert witnesses==before


def test_duplicate_same_geometry_reason_and_mode_does_not_spend_another_slot():
    rows=[];a=row(1);retain_rejection_witness(rows,a);retain_rejection_witness(rows,deepcopy(a))
    assert len(rows)==1
    a['allow_detour']=False;retain_rejection_witness(rows,a);assert len(rows)==2


@pytest.mark.parametrize('bad',(True,False,0,25,None,'24'))
def test_invalid_bound_is_not_an_unbounded_log(bad):
    with pytest.raises(ValueError):retain_rejection_witness([],row(0),limit=bad)


@pytest.mark.parametrize('fault',('reason','score','nan','bool','portal','inventory'))
def test_malformed_witness_is_not_silently_stored(fault):
    q=row(0);rows=[]
    if fault=='reason':q['reason']=''
    elif fault=='score':q['score']=[]
    elif fault=='nan':q['score']=[float('nan')]
    elif fault=='bool':q['score']=[True]
    elif fault=='portal':q['portal']=None
    else:rows=[row(i) for i in range(25)]
    with pytest.raises(ValueError):retain_rejection_witness(rows,q)
