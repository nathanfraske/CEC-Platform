"""Complete Source layer authority is not an actual new protected-face prefix.

Use real native lands/tracks and the independent whole-current receiver.
The complete contract stays exact; unused power faces grant no new copper,
current allocation, via, planar-prefix or cross-layer throat permission.
"""
import copy
import math
import pcbnew
import pytest

import cec_full_current_supply_prefix as receiver
from test_full_current_supply_prefix import example, check


def complete_contract(*, back=False, angle=0, name='/renamed/RAIL', ref='PART'):
    b,p,v,t,e,c = example(back=back,angle=angle,netname=name,ref=ref)
    assert b.SetLayerName(pcbnew.In3_Cu,'PWR')
    contract=next(iter(c.values()))
    contract['routing_layers']=(*contract['routing_layers'],'In3.Cu')
    from cec_route_dimensions import current_trace_widths
    width=current_trace_widths(contract['current_authority'],('In3.Cu',),
        contract['profile'],rise_c=30.)['In3.Cu']
    contract['required_by_layer_mm']['In3.Cu']=max(1.,width)
    return b,p,v,t,e,c


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_unused_power_face_does_not_invalidate_actual_surface_prefix(back,angle):
    b,p,v,t,e,c=complete_contract(back=back,angle=angle,
        name=f'/other/{back}/{angle}',ref=f'ARBITRARY_{angle}')
    original=copy.deepcopy(c)
    tracks=[(q.m_Uuid.AsString(),q.GetLayer(),list(q.GetStart()),list(q.GetEnd()),q.GetWidth())
        for q in b.GetTracks()]
    r=check(b,v,e,c)
    assert r['complete'] and r['track_uuids']==[e.m_Uuid.AsString()]
    assert not r['refusals']
    proof,=r['proofs']
    assert proof['current_authority']==next(iter(c.values()))['current_authority']
    assert proof['actual_whole_current_floor_nm']<=e.GetWidth()<proof['unchanged_class_width_nm']
    assert proof['full_width_throat_uuids']==[t.m_Uuid.AsString()]
    assert c==original
    assert tracks==[(q.m_Uuid.AsString(),q.GetLayer(),list(q.GetStart()),list(q.GetEnd()),q.GetWidth())
        for q in b.GetTracks()]
    assert not r['current_budget_lowered'] and not r['barrel_capacity_qualified']


@pytest.mark.parametrize('fault',['below_current','no_margin','bool_current','wrong_profile',
    'no_source_refs','missing_unused_width','below_unused_current','disabled_unused_face',
    'ground_plane_contract','no_group','untyped','thin_throat','no_throat','too_long'])
def test_unused_face_fix_cannot_waive_complete_current_source_or_native_scope(fault):
    b,p,v,t,e,c=complete_contract()
    q=next(iter(c.values()))
    if fault=='below_current':e.SetWidth(e.GetWidth()-1)
    elif fault=='no_margin':q['current_authority'].pop('margin_included')
    elif fault=='bool_current':q['current_authority']['amps']=True
    elif fault=='wrong_profile':q['profile']='unsupported'
    elif fault=='no_source_refs':q['authority_refs']=[]
    elif fault=='missing_unused_width':q['required_by_layer_mm'].pop('In3.Cu')
    elif fault=='below_unused_current':q['required_by_layer_mm']['In3.Cu']=0.000001
    elif fault=='disabled_unused_face':
        q['routing_layers']=(*q['routing_layers'],'In15.Cu')
        q['required_by_layer_mm']['In15.Cu']=1.
    elif fault=='ground_plane_contract':
        q['routing_layers']=(*q['routing_layers'],'In1.Cu')
        q['required_by_layer_mm']['In1.Cu']=1.
    elif fault=='no_group':e.GetParentGroup().RemoveItem(e)
    elif fault=='untyped':p.GetParentFootprint().SetValue('UNMODELED')
    elif fault=='thin_throat':t.SetWidth(e.GetWidth())
    elif fault=='no_throat':b.Remove(t)
    elif fault=='too_long':e.SetStart(pcbnew.VECTOR2I_MM(8,10))
    r=check(b,v,e,c)
    assert r['complete'] and not r['track_uuids']


def test_actual_power_face_prefix_is_still_explicitly_refused():
    b,p,v,t,e,c=complete_contract()
    e.SetLayer(pcbnew.In3_Cu)
    r=check(b,v,e,c)
    assert r['complete'] and not r['track_uuids']
    assert r['refusals']==[dict(net=p.GetNetname(),
        reason='actual_prefix_on_protected_routing_face_forbidden',
        track_uuids=[e.m_Uuid.AsString()])]


def test_unused_power_face_cannot_supply_a_retained_cross_layer_throat():
    b,p,v,t,e,c=complete_contract()
    q=next(iter(c.values()))
    t.SetLayer(pcbnew.In3_Cu)
    t.SetWidth(math.ceil(q['required_by_layer_mm']['In3.Cu']*1e6))
    r=check(b,v,e,c)
    assert r['complete'] and not r['track_uuids']


def test_mixed_scope_only_proves_the_actual_permitted_prefix():
    b,p,v,t,e,c=complete_contract()
    rogue=pcbnew.PCB_TRACK(b)
    rogue.SetLayer(pcbnew.In3_Cu);rogue.SetNet(p.GetNet());rogue.SetWidth(e.GetWidth())
    rogue.SetStart(pcbnew.VECTOR2I_MM(10,11));rogue.SetEnd(pcbnew.VECTOR2I_MM(10.2,11))
    b.Add(rogue);e.GetParentGroup().AddItem(rogue)
    r=receiver.receive(b,c,track_uuid_scope=[e.m_Uuid.AsString(),rogue.m_Uuid.AsString()],
        retained_via_uuids=[v.m_Uuid.AsString()])
    assert r['complete'] and r['track_uuids']==[e.m_Uuid.AsString()]
    assert r['refusals']==[dict(net=p.GetNetname(),
        reason='actual_prefix_on_protected_routing_face_forbidden',
        track_uuids=[rogue.m_Uuid.AsString()])]
