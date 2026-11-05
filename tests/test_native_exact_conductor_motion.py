import pcbnew
import pytest
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track
from root_native_exact_conductor_motion_20261013 import apply


def boards():
    a = _board([(10,20,'RENAMED')]); b = _board([(10,20,'RENAMED')])
    t = track(a,'RENAMED',(10,20),(30,20)); t.SetLocked(True)
    clone = pcbnew.Cast_to_PCB_TRACK(pcbnew.Cast_to_BOARD_ITEM(t.Clone()))
    b.Add(clone);clone.SetNet(b.FindNet(t.GetNetname()))
    return a,b,t,clone


@pytest.mark.parametrize('axis',[0,1])
@pytest.mark.parametrize('sign',[-1,1])
def test_literal_axis_translation_retains_real_dimensions_and_source(axis,sign):
    a,b,t,c = boards(); delta=[0,0];delta[axis]=sign*1200000
    source=[tuple(t.GetStart()),tuple(t.GetEnd())]
    r=apply(a,b,[dict(uuid=force._uid(t),endpoint_offsets_nm=[delta,delta],locked_source_requested=True)])
    assert source==[tuple(t.GetStart()),tuple(t.GetEnd())]
    assert c.GetWidth()==t.GetWidth() and c.GetLayer()==t.GetLayer() and c.IsLocked()
    assert force._uid(c)==force._uid(t)
    assert not r['current_qualified'] and not r['routing_admitted'] and not r['release_authority']


@pytest.mark.parametrize('fault',['width','face','net','unrequested_lock','noncanonical','overshift','duplicate','missing'])
def test_invalid_scope_refuses_before_any_motion(fault):
    a,b,t,c=boards();q=dict(uuid=force._uid(t),endpoint_offsets_nm=[[0,-1000000],[0,-1000000]],locked_source_requested=True)
    if fault=='width':c.SetWidth(300000)
    if fault=='face':c.SetLayer(pcbnew.B_Cu)
    if fault=='net':c.SetNetCode(0)
    if fault=='unrequested_lock':q['locked_source_requested']=False
    if fault=='noncanonical':q['endpoint_offsets_nm'][1]=[0,0]
    if fault=='overshift':q['endpoint_offsets_nm'][0]=[0,3100000]
    if fault=='missing':q['uuid']='missing'
    before=[tuple(c.GetStart()),tuple(c.GetEnd())]
    with pytest.raises(ValueError):apply(a,b,[q,q] if fault=='duplicate' else [q])
    assert before==[tuple(c.GetStart()),tuple(c.GetEnd())]


def test_literal_via_motion_retains_drill_faces_net_lock_and_source():
    a=_board([(10,20,'RENAMED')]);b=_board([(10,20,'RENAMED')])
    v=pcbnew.PCB_VIA(a);v.SetPosition(pcbnew.VECTOR2I_MM(10,20));v.SetWidth(900000);v.SetDrill(500000)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetNet(a.FindNet('RENAMED'));v.SetLocked(True);a.Add(v)
    c=pcbnew.Cast_to_PCB_VIA(pcbnew.Cast_to_BOARD_ITEM(v.Clone()));b.Add(c);c.SetNet(b.FindNet('RENAMED'))
    proof=apply(a,b,[dict(uuid=force._uid(v),endpoint_offsets_nm=[[100000,-100000]],locked_source_requested=True)])
    assert tuple(v.GetPosition())==(10000000,20000000) and tuple(c.GetPosition())==(10100000,19900000)
    assert c.GetDrillValue()==500000 and c.GetWidth(c.TopLayer())==900000 and c.IsLocked()
    assert (c.TopLayer(),c.BottomLayer(),c.GetNetname())==(v.TopLayer(),v.BottomLayer(),v.GetNetname())
    assert not proof['routing_admitted'] and not proof['current_qualified']


def test_request_count_remains_bounded_before_mutating_any_item():
    a,b,t,c=boards()
    q=dict(uuid=force._uid(t),endpoint_offsets_nm=[[0,-1000000],[0,-1000000]],locked_source_requested=True)
    old=(tuple(c.GetStart()),tuple(c.GetEnd()))
    with pytest.raises(ValueError):apply(a,b,[q]*33)
    assert old==(tuple(c.GetStart()),tuple(c.GetEnd()))


@pytest.mark.parametrize('limit',[0,65,True,None,1.5])
def test_explicit_complexity_budget_refuses_invalid_values_before_motion(limit):
    a,b,t,c=boards();old=(tuple(c.GetStart()),tuple(c.GetEnd()))
    q=dict(uuid=force._uid(t),endpoint_offsets_nm=[[0,-1000000],[0,-1000000]],locked_source_requested=True)
    with pytest.raises(ValueError):apply(a,b,[q],maximum_items=limit)
    assert old==(tuple(c.GetStart()),tuple(c.GetEnd()))


@pytest.mark.parametrize('count',[33,64])
def test_explicit_larger_cohort_preserves_every_source_dimension_and_identity(count):
    a=_board([(10,20,'RENAMED')]);b=_board([(10,20,'RENAMED')]);requests=[];pairs=[]
    for i in range(count):
        t=track(a,'RENAMED',(10,20+i),(30,20+i));t.SetLocked(True)
        c=pcbnew.Cast_to_PCB_TRACK(pcbnew.Cast_to_BOARD_ITEM(t.Clone()))
        b.Add(c);c.SetNet(b.FindNet(t.GetNetname()));pairs.append((t,c))
        requests.append(dict(uuid=force._uid(t),endpoint_offsets_nm=[[0,-100000],[0,-100000]],locked_source_requested=True))
    source=[(tuple(t.GetStart()),tuple(t.GetEnd())) for t,c in pairs]
    with pytest.raises(ValueError):apply(a,b,requests)
    assert source==[(tuple(c.GetStart()),tuple(c.GetEnd())) for t,c in pairs]
    r=apply(a,b,requests,maximum_items=64)
    assert len(r['changes'])==count and r['maximum_items']==64
    assert source==[(tuple(t.GetStart()),tuple(t.GetEnd())) for t,c in pairs]
    assert all(force._uid(t)==force._uid(c) and c.GetWidth()==t.GetWidth()
        and c.GetLayer()==t.GetLayer() and c.GetNetname()==t.GetNetname() and c.IsLocked() for t,c in pairs)
    assert not r['routing_admitted'] and not r['current_qualified'] and not r['release_authority']


def test_explicit_transient_endpoint_seed_is_not_a_saved_route_permission():
    a,b,t,c=boards();uid=force._uid(t)
    q=dict(uuid=uid,endpoint_offsets_nm=[[0,-1000000],[0,0]],locked_source_requested=True)
    with pytest.raises(ValueError):apply(a,b,[q])
    r=apply(a,b,[q],allow_transient_rebuild_uuids=[uid])
    assert r['transient_rebuild_required_uuids']==[uid]
    assert c.GetWidth()==t.GetWidth() and c.GetLayer()==t.GetLayer() and c.IsLocked()
    assert tuple(t.GetStart())==(10000000,20000000)
    assert not r['routing_admitted'] and not r['current_qualified'] and not r['release_authority']


@pytest.mark.parametrize('scope',[['missing'],[False],['same','same'],'same'])
def test_invalid_transient_scope_is_rejected_before_motion(scope):
    a,b,t,c=boards();old=(tuple(c.GetStart()),tuple(c.GetEnd()))
    q=dict(uuid=force._uid(t),endpoint_offsets_nm=[[0,-1000000],[0,0]],locked_source_requested=True)
    with pytest.raises(ValueError):apply(a,b,[q],allow_transient_rebuild_uuids=scope)
    assert old==(tuple(c.GetStart()),tuple(c.GetEnd()))
