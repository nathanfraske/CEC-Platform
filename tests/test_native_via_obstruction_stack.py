"""A first refusal must not masquerade as the only through-hole obstruction."""
from copy import deepcopy
import pcbnew
import pytest
import cec_fr as fr
import cec_native_via_obstruction_stack as stack
import cec_field_coupling as field
import cec_precision_route as route
from test_field_proposals import track,add_net
from test_lastmile import _board


def fixture(angle=0,offset=0):
    b=_board([],edge=(0,0,40,40));b.SetCopperLayerCount(6)
    for name in ('/DATA','/PARTNER','/TOP','/MID','/BOTTOM'):add_net(b,name)
    at=pcbnew.VECTOR2I_MM(10+offset,10)
    for name,layer in (('/TOP',pcbnew.F_Cu),('/MID',pcbnew.In3_Cu),('/BOTTOM',pcbnew.B_Cu)):
        track(b,name,(9+offset,10),(11+offset,10),layer=layer)
    track(b,'/DATA',(9+offset,10),(11+offset,10),layer=pcbnew.In2_Cu)
    if angle:
        pivot=pcbnew.VECTOR2I_MM(20,20);rotation=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
        marker=pcbnew.PCB_TRACK(b);marker.SetStart(at);marker.SetEnd(at);marker.Rotate(pivot,rotation);at=marker.GetStart()
        for t in b.GetTracks():t.Rotate(pivot,rotation)
    return b,at,b.GetNetcodeFromNetname('/DATA')


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('offset',[0,7])
def test_all_native_faces_expose_hidden_foreign_objects_without_mutation(angle,offset):
    b,at,code=fixture(angle,offset);before=field._field_snapshot_inventory(b)
    first={};initial=fr._via_spot_clear(b,at,600000,200000,{code},drill_nm=300000,net_code=code,report=first)
    r=stack.inspect(b,at,600000,200000,int(code))
    assert not initial and first['layer']=='F.Cu'
    assert r['complete'] and len(r['layers'])==6
    names={hit['net'] for row in r['layers'] for hit in row['blockers'] if hit.get('net')}
    assert names=={'/TOP','/MID','/BOTTOM'}
    assert '/DATA' not in names and not r['via_admitted'] and not r['all_guard_categories_complete']
    repeat={};assert not fr._via_spot_clear(b,at,600000,200000,{code},drill_nm=300000,net_code=code,report=repeat)
    assert first==repeat and field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('changes',[dict(diameter_nm=True),dict(diameter_nm=0),dict(clearance_nm=-1),
    dict(net_code=True),dict(timeout_s=0),dict(timeout_s=float('nan')),dict(max_blockers_per_layer=0),
    dict(max_blockers_per_layer=129)])
def test_unknown_or_unbounded_query_does_not_mean_empty_clear_copper(changes):
    b,at,code=fixture();args=dict(diameter_nm=600000,clearance_nm=200000,net_code=int(code));args.update(changes)
    r=stack.inspect(b,at,**args)
    assert not r['complete'] and r['errors'] and not r['via_admitted']


def test_truncated_layer_is_reported_as_incomplete():
    b,at,code=fixture()
    for name in ('/MORE1','/MORE2'):track(b,name,(9,10),(11,10))
    r=stack.inspect(b,at,600000,200000,int(code),max_blockers_per_layer=2)
    assert not r['complete']
    front=next(row for row in r['layers'] if row['layer_id']==pcbnew.F_Cu)
    assert front['truncated'] and not front['complete'] and len(front['blockers'])==2


def test_one_failed_layer_keeps_other_causes_but_never_claims_completeness(monkeypatch):
    b,at,code=fixture();original=fr._identified_foreign_shape_indexes
    def damaged(board,layer,codes):
        if layer==pcbnew.In3_Cu:raise ValueError('native shape unavailable')
        return original(board,layer,codes)
    monkeypatch.setattr(fr,'_identified_foreign_shape_indexes',damaged)
    r=stack.inspect(b,at,600000,200000,int(code))
    assert not r['complete'] and len(r['layers'])==6
    assert any(row['blockers'] for row in r['layers'] if row['layer_id']==pcbnew.B_Cu)
    assert any(row.get('error') for row in r['layers'] if row['layer_id']==pcbnew.In3_Cu)


def test_shape_adapter_which_the_fast_snapshot_skips_is_not_diagnostic_completion(monkeypatch):
    b,at,code=fixture();item=next(t for t in b.GetTracks() if t.GetNetname()=='/MID');uid=item.m_Uuid.AsString()
    original=pcbnew.PCB_TRACK.GetEffectiveShape
    def damaged(track,layer):
        if track.m_Uuid.AsString()==uid:raise RuntimeError('unsupported adapter')
        return original(track,layer)
    monkeypatch.setattr(pcbnew.PCB_TRACK,'GetEffectiveShape',damaged)
    r=stack.inspect(b,at,600000,200000,int(code))
    assert not r['complete']
    row=next(row for row in r['layers'] if row['layer_id']==pcbnew.In3_Cu)
    assert row['unknown_native_shapes'] and row['unknown_native_shapes'][0]['uuid']==uid


def refusal():
    return dict(refused='all candidates refused',portal_evidence=dict(signal_via=dict(diameter_mm=.6),
        screened={'start:+1':dict(reason_diverse_rejected=[dict(portal=dict(p=(10.,10.),n=(10.,11.)),
            transition=dict(ok=False,p_via=dict(reason='first front obstruction')))])}))


def test_failed_route_wrapper_records_parent_layer_stack_without_repairing_or_waiving(monkeypatch):
    b,at,code=fixture();pair=dict(p='/DATA',n='/PARTNER',clearance=.2)
    result=refusal();before=field._field_snapshot_inventory(b)
    monkeypatch.setattr(route,'_route_coupled_via_portal_beam',lambda *a,**kw:deepcopy(result))
    actual=route._route_coupled_via_portals(b,pair,((10,10),(20,10),(10,11),(20,11)),max_portal_refills=0)
    proof=actual['portal_evidence']['matched_transition_native_failure_stacks']
    assert proof['complete'] and proof['sampled_fields_only'] and proof['full_search_domain_not_claimed']
    hits={h['net'] for f in proof['fields'] for m in f['members'] for layer in m['stack']['layers'] for h in layer['blockers'] if h.get('net')}
    assert '/MID' in hits and '/BOTTOM' in hits and actual['refused']==result['refused']
    assert field._field_snapshot_inventory(b)==before


def test_success_path_performs_no_failure_diagnostics(monkeypatch):
    b,at,code=fixture();result=dict(route_mode='already successful')
    monkeypatch.setattr(route,'_route_coupled_via_portal_beam',lambda *a,**kw:result)
    def forbidden(*a,**kw):raise AssertionError('successful route must not be diagnosed')
    monkeypatch.setattr(stack,'enrich_pair_refusal',forbidden)
    assert route._route_coupled_via_portals(b,{},(),max_portal_refills=0) is result


def test_compact_trace_keeps_hidden_layer_causes_and_summary_bounds():
    import cec_probe_evidence
    b,at,code=fixture();result=refusal();stack.enrich_pair_refusal(b,dict(p='/DATA',n='/PARTNER',clearance=.2),result)
    rows=cec_probe_evidence.compact_pair_search_trace(result)
    summary=rows[0]['matched_transition_native_failure_stacks']
    assert summary['complete'] and summary['sampled_fields_only'] and summary['not_via_or_retirement_authority']
    nets={h['net'] for f in summary['fields'] for m in f['members'] for layer in m['layers'] for h in layer['blockers'] if h.get('net')}
    assert '/MID' in nets and '/BOTTOM' in nets
    assert cec_probe_evidence.compact_pair_search_trace({'search_trace':rows})==rows
