"""CPU scheduling stubs never supply admission; positives use fresh processes."""
import json
import os
import threading
import time
from pathlib import Path
import pytest
import cec_force_current as force
import cec_certificate_repair as repair
import cec_native_portal_cpu_portfolio as cpu
from test_native_portal_face_portfolio import plated_fixture
from test_ordinary_native_portals import fixture


@pytest.mark.parametrize('maximum',[True,0,17,1.5])
def test_offer_lane_budget_is_strict(maximum):
    with pytest.raises(ValueError,match='bounded_native_cpu_offer'):
        cpu.offer('/absent',board_hint='synthetic',net='/x',maximum_lanes=maximum)


@pytest.mark.parametrize('value',[0,1,None,'yes'])
def test_contained_tier_requires_explicit_bool_before_source_access(value):
    with pytest.raises(ValueError,match='bounded_native_cpu_offer'):
        cpu.offer('/absent',board_hint='synthetic',net='/x',contained_intervals_only=value)
    with pytest.raises(ValueError,match='bounded_native_cpu_portfolio'):
        cpu.construct('/absent','/also_absent',board_hint='synthetic',net='/x',contained_intervals_only=value)


@pytest.mark.parametrize('kwargs',[
    {'max_workers':True},{'max_workers':0},{'max_workers':5},
    {'search_s':True},{'search_s':0},{'search_s':11},{'search_s':float('nan')},
    {'wall_s':19},{'wall_s':121},{'wall_s':float('inf')},
])
def test_worker_and_aggregate_budget_refuse_before_source_access(kwargs):
    with pytest.raises(ValueError,match='bounded_native_cpu_portfolio'):
        cpu.construct('/absent','/also_absent',board_hint='synthetic',net='/x',**kwargs)


def test_offer_retains_default_and_only_fresh_exact_lanes(tmp_path):
    source,board,net,target=plated_fixture(tmp_path)
    before=force._family(source,'synthetic')
    q=cpu.offer(source,board_hint='synthetic',net=net,maximum_lanes=13)
    assert q['complete'] and q['lanes'][0] is None
    assert 1<len(q['lanes'])<=13 and q['original_default_fallback_retained']
    import cec_native_portal_geometry as geometry
    for lane in q['lanes'][1:]:assert geometry._lane_request(lane)==lane
    assert force._family(source,'synthetic')==before
    assert not q['routing_admitted'] and not q['current_qualified']


def test_common_topology_does_not_discard_later_physical_contacts():
    def endpoint(x):return dict(at_nm=[x,0],layers=[0,2,6])
    pairs=[(endpoint(0),endpoint(x))for x in(10,20,30,40)]
    q=cpu._topology_lanes(pairs,pairs,13)
    assert q[0]is None and len(q)==13
    assert all(r['from_layer']==r['to_layer']for r in q[1:])
    assert {r['pair_index']for r in q[1:]}=={0,1}
    assert {r['reverse']for r in q[1:]}=={False,True}
    assert q==cpu._topology_lanes(pairs,pairs,13)
    assert cpu._topology_lanes(pairs,pairs,1)==[None]


@pytest.mark.parametrize('net',['GND','+3V3','/SENSEP1_HI'])
def test_nonordinary_source_role_cannot_enter_pool(tmp_path,net):
    source,board,net=fixture(tmp_path,net=net)
    q=cpu.offer(source,board_hint='synthetic',net=net)
    assert not q['complete'] and not q['lanes']


def test_serial_fresh_copies_and_four_supervisor_cap(tmp_path,monkeypatch):
    source,board,net,target=plated_fixture(tmp_path)
    before=force._family(source,'synthetic');raw=source.read_bytes()
    active=[0,0];lock=threading.Lock();seen=[]
    def spawn(fn,args,**kw):
        child,target,budget,lane=args
        assert Path(child).read_bytes()==raw
        assert kw['search_budget_arg']==2 and kw['timeout_s']<=20 and budget==2
        with lock:
            active[0]+=1;active[1]=max(active);seen.append((child,lane))
        time.sleep(.03)
        with lock:active[0]-=1
        return {'closed':0,'elapsed_s':.03}
    monkeypatch.setattr(repair,'_spawn_apply',spawn)
    q=cpu.construct(source,tmp_path/'pool',board_hint='synthetic',net=net,
        maximum_lanes=8,max_workers=4,search_s=2,wall_s=30)
    assert len(seen)==8 and 1<active[1]<=4
    assert len({p for p,l in seen})==8 and any(l is None for p,l in seen)
    assert not q['complete'] and not q['received_private_candidates']
    assert force._family(source,'synthetic')==before


def test_forged_worker_success_cannot_replace_saved_receiving(tmp_path,monkeypatch):
    source,board,net,target=plated_fixture(tmp_path)
    monkeypatch.setattr(repair,'_spawn_apply',lambda *a,**kw:dict(closed=1,elapsed_s=0))
    q=cpu.construct(source,tmp_path/'pool',board_hint='synthetic',net=net,
        maximum_lanes=1,max_workers=1,search_s=2,wall_s=30)
    assert not q['complete'] and not q['received_private_candidates']
    assert not q['attempts'][0]['ordinary_saved_receiving']['ok']
    assert not q['routing_admitted']


def test_changed_source_is_not_a_returned_private_candidate(tmp_path,monkeypatch):
    source,board,net,target=plated_fixture(tmp_path)
    def spawn(*a,**kw):
        source.write_bytes(source.read_bytes()+b'\n')
        return dict(closed=0,elapsed_s=0)
    monkeypatch.setattr(repair,'_spawn_apply',spawn)
    with pytest.raises(ValueError,match='native_cpu_portfolio_epoch_changed'):
        cpu.construct(source,tmp_path/'pool',board_hint='synthetic',net=net,
            maximum_lanes=1,max_workers=1,search_s=2,wall_s=30)


def test_existing_output_or_source_child_is_not_overwritten(tmp_path):
    source,board,net,target=plated_fixture(tmp_path)
    for out in (source.parent/'private',tmp_path):
        with pytest.raises(ValueError,match='fresh_private_cpu_portfolio'):
            cpu.construct(source,out,board_hint='synthetic',net=net)


def test_copy_storage_budget_precedes_any_worker_or_family_copy(tmp_path,monkeypatch):
    source,board,net,target=plated_fixture(tmp_path)
    real_offer=cpu.offer;real_stat=Path.stat
    def offered(*a,**kw):
        q=real_offer(*a,**kw)
        def stat(path,*args,**kwargs):
            value=real_stat(path,*args,**kwargs)
            if path==source:
                fields=list(value);fields[6]=40*1024*1024
                return os.stat_result(fields)
            return value
        monkeypatch.setattr(Path,'stat',stat)
        return q
    monkeypatch.setattr(cpu,'offer',offered)
    monkeypatch.setattr(repair,'_spawn_apply',lambda *a,**k:pytest.fail('oversized copy reached worker'))
    with pytest.raises(ValueError,match='native_cpu_copy_storage_budget'):
        cpu.construct(source,tmp_path/'pool',board_hint='synthetic',net=net,maximum_lanes=8)
    assert not list((tmp_path/'pool').glob('UNADMITTED*'))


@pytest.mark.parametrize('elapsed',[True,float('nan'),float('inf'),11,'0'])
def test_unknown_or_late_worker_timing_never_qualifies_candidate(tmp_path,monkeypatch,elapsed):
    source,board,net,target=plated_fixture(tmp_path)
    monkeypatch.setattr(repair,'_spawn_apply',lambda *a,**kw:dict(closed=1,elapsed_s=elapsed))
    q=cpu.construct(source,tmp_path/'pool',board_hint='synthetic',net=net,
        maximum_lanes=1,max_workers=1,search_s=2,wall_s=30)
    assert not q['received_private_candidates'] and not q['complete']
    assert 'ordinary_saved_receiving' not in q['attempts'][0]


@pytest.mark.parametrize('lanes',[1,3])
def test_real_fresh_subprocess_and_independent_saved_receivers(tmp_path,lanes):
    source,board,net,target=plated_fixture(tmp_path)
    before=force._family(source,'synthetic')
    q=cpu.construct(source,tmp_path/'pool',board_hint='synthetic',net=net,
        maximum_lanes=lanes,max_workers=min(lanes,2),search_s=5,wall_s=60)
    assert q['complete'],q
    assert q['source_and_code_unchanged'] and force._family(source,'synthetic')==before
    assert q['whole_original_parent_receiving_still_required'] and not q['admitted']
    saved=json.loads((tmp_path/'pool'/'portfolio.json').read_text())
    assert saved['received_private_candidates']==q['received_private_candidates']
    for candidate in q['received_private_candidates']:
        attempt=next(a for a in q['attempts']if a['index']==candidate['index'])
        assert attempt['ordinary_saved_receiving']['ok']
        assert attempt['source_additive_saved_receiving']['ok']
        assert force._hash(Path(candidate['candidate']))==candidate['candidate_sha256']
