"""Tail-frontier scheduling cannot create new material or deletion authority."""
import copy
import pytest
import cec_native_logged_tail_scope as scope


def raw(heads=(),vias=(),opens=0):
    return dict(violations=[dict(type=kind,items=[dict(uuid=u)]) for kind,ids in
        [('track_dangling',heads),('via_dangling',vias)] for u in ids],unconnected_items=[{}]*opens)


def inventory(prefix='/renamed/',locked=False):
    return [dict(uuid=str(i),kind='PCB_TRACK',net=prefix+'CONTROL',width_nm=200000,
        locked=locked,grouped=False) for i in range(4)]+[
        dict(uuid='via',kind='PCB_VIA',net=prefix+'CONTROL',width_nm=600000,locked=True,grouped=False)]


@pytest.mark.parametrize('prefix',['/a/','/unrelated/'])
@pytest.mark.parametrize('locked',[False,True])
@pytest.mark.parametrize('seed_order',[['0','2'],['2','0']])
def test_grows_only_new_native_original_heads_before_whole_receiving(prefix,locked,seed_order):
    rows=inventory(prefix,locked);saved=copy.deepcopy(rows);calls=[]
    def probe(ids):
        calls.append(ids);return raw(['1'] if len(calls)==1 else ['3'] if len(calls)==2 else [])
    result=scope.extend(rows,raw(['0','2']),seed_order,{prefix+'CONTROL'},probe,
        allow_locked_track_uuids=[r['uuid'] for r in rows if r['kind']=='PCB_TRACK'] if locked else [])
    assert result['frontier_exhausted'] and result['retired_track_uuids']==['0','1','2','3']
    assert calls==[('0','2'),('0','1','2'),('0','1','2','3')]
    assert rows==saved and not result['mutation_or_owner_authority'] and not result['release_authority']


@pytest.mark.parametrize('fault',['unreported_seed','power','grouped','locked','wide','nontrack','missing','duplicate',
    'stale_probe','foreign_probe','malformed_probe','wrong_new_net','zero_budget','oversize_scope'])
def test_invalid_or_protected_source_scope_never_becomes_a_cut(fault):
    rows=inventory();seeds=['0'];initial=raw(['0']);answer=raw(['1']);kwargs={}
    if fault=='unreported_seed':seeds=['1']
    elif fault=='power':rows[0]['net']='+5V'
    elif fault=='grouped':rows[0]['grouped']=True
    elif fault=='locked':rows[0]['locked']=True
    elif fault=='wide':rows[0]['width_nm']=500000
    elif fault=='nontrack':rows[0]['kind']='PAD'
    elif fault=='missing':rows=rows[1:]
    elif fault=='duplicate':rows.append(dict(rows[0]))
    elif fault=='stale_probe':answer=raw(['0'])
    elif fault=='foreign_probe':answer=raw(['not-original'])
    elif fault=='malformed_probe':answer={'violations':[]}
    elif fault=='wrong_new_net':rows[1]['net']='/OTHER'
    elif fault=='zero_budget':kwargs['timeout_s']=0
    elif fault=='oversize_scope':kwargs['maximum_tracks']=33
    if fault=='wrong_new_net':
        result=scope.extend(rows,initial,seeds,{'/renamed/CONTROL'},lambda ids:answer,**kwargs)
        assert not result['frontier_exhausted'] and result['retired_track_uuids']==['0']
    else:
        with pytest.raises(ValueError):scope.extend(rows,initial,seeds,{'/renamed/CONTROL'},lambda ids:answer,**kwargs)


def test_new_barrel_obligation_is_reported_not_deleted_or_silently_accepted():
    result=scope.extend(inventory(),raw(['0']),['0'],{'/renamed/CONTROL'},lambda ids:raw(vias=['via']))
    assert result['frontier_exhausted'] and result['requires_typed_barrel_phase']
    assert result['retired_track_uuids']==['0'] and result['barrel_obligations']==['via']
    assert result['independently_received_whole_source_cut_still_required']


@pytest.mark.parametrize('bound',[1,2])
def test_probe_and_inventory_budgets_cannot_become_unbounded_retry_loops(bound):
    calls=[]
    def probe(ids):calls.append(ids);return raw([str(len(calls))])
    result=scope.extend(inventory(),raw(['0']),['0'],{'/renamed/CONTROL'},probe,maximum_probes=bound)
    assert len(calls)==bound and not result['frontier_exhausted']
    assert result['stop']=='native_tail_probe_work_bound'
