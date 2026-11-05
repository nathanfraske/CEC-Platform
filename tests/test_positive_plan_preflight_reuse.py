"""Reuse only exact positives in one unchanged native/source/policy plan."""
import json
import time
import pcbnew
import pytest
import cec_route_proposal_guard as gate
from test_lastmile import _board
from test_field_proposals import add_net,track,signature
from test_negotiation_route_preflight import op


def fixture(tmp_path,monkeypatch):
    b=_board([(5,5,'/N'),(12,5,'/N')],edge=(0,0,30,30))
    track(b,'/OTHER',(5,15),(15,15));source=tmp_path/'source.kicad_pcb'
    pcbnew.SaveBoard(str(source),b)
    spec={'name':'Default'}
    counts=[];real=gate.field.assess_proposed_route
    def counted(*args,**kwargs):counts.append(1);return real(*args,**kwargs)
    monkeypatch.setattr(gate.field,'assess_proposed_route',counted)
    g=gate.RouteProposalGuard(b,'/N',board_path=str(source),
        netclass_resolver=lambda n:dict(spec),memoize_exact_positive=True)
    return b,source,g,counts,spec


def test_real_complete_preflight_reused_for_identical_scalar_material_only(tmp_path,monkeypatch):
    b,source,g,counts,spec=fixture(tmp_path,monkeypatch);raw=source.read_bytes();before=signature(b)
    first=g.prepare([op((5,5),(12,5))]);assert first
    second=g.prepare([op((5,5),(12,5))]);assert second==first
    assert len(counts)==1 and g.report()['identical_positive_plan_preflight_hits']==1
    assert not g.report()['saved_native_or_whole_board_receiving_cached']
    assert not g.report()['release_authority']and not g.report()['current_qualified']
    assert source.read_bytes()==raw and signature(b)==before
    assert g.prepare([op((5,5),(12,5),width=.25)])
    assert len(counts)==2 # geometrically different proposals are never hits


@pytest.mark.parametrize('mutation',['track','pad_shape','pad_rotation','pad_net','footprint_field',
    'edge','zone','native_rule','source_bytes','project','new_rules','resolver','context','runtime_receiver',
    'target_net','preflight_policy'])
def test_any_live_epoch_change_refuses_old_positive_without_a_field_shortcut(tmp_path,monkeypatch,mutation):
    b,source,g,counts,spec=fixture(tmp_path,monkeypatch)
    route=[op((5,5),(12,5))];assert g.prepare(route)
    pad=next(iter(next(iter(b.GetFootprints())).Pads()))
    if mutation=='track':next(iter(b.GetTracks())).SetWidth(300000)
    elif mutation=='pad_shape':pad.SetShape(pcbnew.PAD_SHAPE_OVAL)
    elif mutation=='pad_rotation':pad.SetOrientationDegrees(17)
    elif mutation=='pad_net':pad.SetNet(b.FindNet('/OTHER'))
    elif mutation=='footprint_field':next(iter(b.GetFootprints())).SetField('MPN','changed selected package')
    elif mutation=='edge':next(iter(b.GetDrawings())).Move(pcbnew.VECTOR2I_MM(.1,0))
    elif mutation=='zone':
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetNet(b.FindNet('/OTHER'))
        z.Outline().NewOutline()
        for x,y in [(20,20),(25,20),(25,25),(20,25)]:z.Outline().Append(x*1000000,y*1000000)
        b.Add(z)
    elif mutation=='native_rule':b.GetDesignSettings().m_ViasMinAnnularWidth+=10000
    elif mutation=='source_bytes':source.write_bytes(source.read_bytes()+b'\n')
    elif mutation=='project':source.with_suffix('.kicad_pro').write_text(json.dumps({'changed':True}))
    elif mutation=='new_rules':source.with_suffix('.kicad_dru').write_text('(version 1)')
    elif mutation=='resolver':spec['name']='Sense'
    elif mutation=='context':monkeypatch.setenv('CEC_EXACT_PLAN_TEST_CONTEXT','new')
    elif mutation=='target_net':g.net='/OTHER'
    elif mutation=='preflight_policy':g.preflight_s=2.5
    else:monkeypatch.setattr(gate.field,'assess_proposed_route',lambda *a,**k:pytest.fail('epochchanged'))
    assert g.prepare(route)is None
    assert g.report()['details'][-1]['reason']=='plan_source_or_policy_epoch_changed'
    assert g.report()['identical_positive_plan_preflight_hits']==0 and len(counts)==1


def test_unknown_result_is_not_cached_as_positive_or_permanent_negative(tmp_path,monkeypatch):
    b,source,g,counts,spec=fixture(tmp_path,monkeypatch)
    real=gate.field.assess_proposed_route;state=[False]
    def unresolved(*a,**k):
        if not state[0]:return {'complete':False,'ok':None,'reason':'bounded_test_refusal'}
        return real(*a,**k)
    monkeypatch.setattr(gate.field,'assess_proposed_route',unresolved)
    # Fresh guard binds this receiver identity before any assessment.
    g=gate.RouteProposalGuard(b,'/N',board_path=str(source),memoize_exact_positive=True)
    route=[op((5,5),(12,5))];assert g.prepare(route)is None
    state[0]=True;assert g.prepare(route)
    assert g.report()['identical_positive_plan_preflight_hits']==0


def test_expired_parent_still_refuses_an_identical_previously_positive_plan(tmp_path,monkeypatch):
    b,source,g,counts,spec=fixture(tmp_path,monkeypatch)
    route=[op((5,5),(12,5))];assert g.prepare(route)
    g.deadline=time.monotonic()-1
    assert g.prepare(route)is None and g.report()['identical_positive_plan_preflight_hits']==0


def test_returned_ops_are_fresh_points_not_borrowed_cached_vectors(tmp_path,monkeypatch):
    b,source,g,counts,spec=fixture(tmp_path,monkeypatch)
    route=[op((5,5),(12,5))];first=g.prepare(route);assert first
    first[0][1].x+=1000000
    second=g.prepare([op((5,5),(12,5))])
    assert tuple(second[0][1])==(5000000,5000000)and len(counts)==1


def test_live_epoch_checked_again_after_unpack_before_a_hit_returns(tmp_path,monkeypatch):
    b,source,g,counts,spec=fixture(tmp_path,monkeypatch)
    route=[op((5,5),(12,5))];assert g.prepare(route)
    real=g._unpack
    def concurrent_change(rows):
        result=real(rows);next(iter(b.GetTracks())).SetWidth(300000);return result
    monkeypatch.setattr(g,'_unpack',concurrent_change)
    assert g.prepare(route)is None and g.report()['identical_positive_plan_preflight_hits']==0


@pytest.mark.parametrize('flag',[1,'yes',None])
def test_reuse_is_literal_optin_not_truthy(flag):
    with pytest.raises(ValueError,match='positive_preflight_reuse'):
        gate.RouteProposalGuard(pcbnew.BOARD(),'/N',memoize_exact_positive=flag)


def test_unsaved_caller_cannot_supply_reusable_positive_context():
    with pytest.raises(ValueError,match='saved_source_context'):
        gate.RouteProposalGuard(pcbnew.BOARD(),'/N',memoize_exact_positive=True)


@pytest.mark.parametrize('seconds',[True,0,-1,11,float('nan'),float('inf')])
def test_preflight_lease_is_finite_explicit_and_never_unbounded(seconds):
    with pytest.raises(ValueError,match='bounded_explicit_proposal_preflight_lease'):
        gate.RouteProposalGuard(pcbnew.BOARD(),'/N',preflight_s=seconds)


def test_funded_preflight_still_clamps_to_outer_plan_deadline(tmp_path,monkeypatch):
    b,source,original,counts,spec=fixture(tmp_path,monkeypatch)
    real=gate.field.assess_proposed_route;seen=[];outer=time.monotonic()+3.
    def observed(*args,**kwargs):
        seen.append(kwargs['deadline']);return real(*args,**kwargs)
    monkeypatch.setattr(gate.field,'assess_proposed_route',observed)
    g=gate.RouteProposalGuard(b,'/N',board_path=str(source),deadline=outer,preflight_s=4.)
    assert g.prepare([op((5,5),(12,5))])and seen==[outer]
    assert g.report()['per_proposal_preflight_cap_s']==4.
