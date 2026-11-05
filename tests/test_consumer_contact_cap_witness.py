"""Fast witnesses use the unchanged native integer erosion predicate."""
import runpy,time
from pathlib import Path
import pcbnew
import pytest
from test_lastmile import _board
from test_field_proposals import track
import cec_force_current as force

TOOL=Path(__file__).resolve().parents[1]/'ops/cec_consumer_corner_miter.py'


@pytest.mark.parametrize('width',[200000,200001])
def test_noncontained_parallel_contact_can_prove_the_legacy_radius_cap_without_binary_search(monkeypatch,width):
    b=_board([],edge=(-5,-5,15,15));b.Add(pcbnew.NETINFO_ITEM(b,'CONTACT'))
    body=track(b,'CONTACT',(0,0),(10,0),width=4.)
    old=[track(b,'CONTACT',(2,-1),(8,-1),width=width/1e6)]
    new=[track(b,'CONTACT',(2,1),(8,1),width=width/1e6)]
    api=runpy.run_path(str(TOOL));slow=api['contacts'].native_contact_radius
    first=slow(body,old,pcbnew.F_Cu,width,time.monotonic()+10.)
    last=slow(body,new,pcbnew.F_Cu,width,time.monotonic()+10.)
    def forbidden(*a,**k):raise AssertionError('A positive endpoint witness must not binary-search again')
    monkeypatch.setattr(api['contacts'],'native_contact_radius',forbidden)
    proof=api['retained_contact_proof'](body,old,new,pcbnew.F_Cu,width,time.monotonic()+10.)
    assert proof['method']=='exact_native_radius_search_cap_witness'
    assert 0<first<=proof['source_radius_upper_bound_nm']<=proof['candidate_radius_lower_bound_nm']<=last
    assert proof['same_native_erosion_and_integer_radius_domain'] and not proof['current_or_barrel_capacity_qualified']


def test_an_empty_candidate_contact_still_uses_the_original_refusal_guard(monkeypatch):
    b=_board([],edge=(-5,-5,15,15));b.Add(pcbnew.NETINFO_ITEM(b,'CONTACT'))
    body=track(b,'CONTACT',(0,0),(10,0),width=1.)
    old=[track(b,'CONTACT',(2,0),(8,0),width=.2)];new=[track(b,'CONTACT',(2,3),(8,3),width=.2)]
    api=runpy.run_path(str(TOOL));calls=[]
    def radius(*a):calls.append(a);return 99999 if len(calls)==1 else 0
    monkeypatch.setattr(api['contacts'],'native_contact_radius',radius)
    with pytest.raises(ValueError,match='contact_web_would_shrink'):
        api['retained_contact_proof'](body,old,new,pcbnew.F_Cu,200000,time.monotonic()+10.)
    assert len(calls)==2


def test_previous_outer_tool_receipt_cannot_be_used_as_an_inner_owner_baseline(tmp_path):
    source=tmp_path/'source';source.write_text('synthetic source identity only')
    api=runpy.run_path(str(TOOL));epoch=force._code_identity()
    data=dict(code_identity=epoch,tool_kind='source_consumer_corner_miter',ok=True,complete=True,changed=True,
        source_ownership='strict_outer',candidate_sha256=force._hash(source))
    with pytest.raises(ValueError,match='baseline_owner_changed'):
        api['baseline'](data,source,epoch,'planar_nonplane')


def test_a_source_corner_with_a_larger_true_radius_keeps_the_original_rejection(monkeypatch):
    b=_board([],edge=(-5,-5,15,15));b.Add(pcbnew.NETINFO_ITEM(b,'CONTACT'))
    body=track(b,'CONTACT',(0,0),(10,0),width=4.)
    old=[track(b,'CONTACT',(2,0),(5,0),width=.2),track(b,'CONTACT',(5,0),(5,1),width=.2)]
    new=[track(b,'CONTACT',(2,1),(5,1),width=.2)]
    api=runpy.run_path(str(TOOL));slow=api['contacts'].native_contact_radius;calls=[]
    def observed(*args):calls.append(args);return slow(*args)
    monkeypatch.setattr(api['contacts'],'native_contact_radius',observed)
    with pytest.raises(ValueError,match='contact_web_would_shrink'):
        api['retained_contact_proof'](body,old,new,pcbnew.F_Cu,200000,time.monotonic()+10.)
    assert len(calls)==0


def test_expired_optional_cap_witness_preserves_both_original_radius_leases(monkeypatch):
    b=_board([],edge=(-5,-5,15,15));b.Add(pcbnew.NETINFO_ITEM(b,'CONTACT'))
    body=track(b,'CONTACT',(0,0),(10,0),width=4.)
    old=[track(b,'CONTACT',(2,-1),(8,-1),width=.2)];new=[track(b,'CONTACT',(2,1),(8,1),width=.2)]
    api=runpy.run_path(str(TOOL));fn=api['retained_contact_proof'];calls=[]
    def expired(*a):raise ValueError('native_contact_cap_witness_deadline')
    monkeypatch.setitem(fn.__globals__,'native_radius_positive_at',expired)
    def radius(*a):calls.append(a);return 99999
    monkeypatch.setattr(api['contacts'],'native_contact_radius',radius)
    proof=fn(body,old,new,pcbnew.F_Cu,200000,time.monotonic()+10.)
    assert proof['method']=='existing_native_inscribed_radius_fallback' and len(calls)==2
    assert all(0<a[-1]-time.monotonic()<=10. for a in calls)
