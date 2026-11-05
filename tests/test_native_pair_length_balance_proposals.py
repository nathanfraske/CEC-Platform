"""Geometry is a proposal, not a PCB or electrical qualification."""
import math
import pytest
from cec_pair_length_match import offset_path
from cec_pair_length_match import compact_window_leads


@pytest.mark.parametrize('heading',[(1,0),(0,1),(-1,0),(0,-1)])
@pytest.mark.parametrize('side',[-1,1])
def test_minimal_monotone_offset_has_only_forty_five_bends(heading,side):
    start=(100000000,-200000000)
    end=tuple(start[i]+heading[i]*12000000 for i in (0,1))
    path=offset_path(start,end,2000000,side)
    assert path[0]==start and path[-1]==end
    vectors=[(z[0]-a[0],z[1]-a[1]) for a,z in zip(path,path[1:])]
    assert all((x==0 or y==0 or abs(x)==abs(y)) and (x or y) for x,y in vectors)
    assert all(v[0]*heading[0]+v[1]*heading[1]>0 for v in vectors)
    assert all(math.isclose((a[0]*z[0]+a[1]*z[1])/(math.hypot(*a)*math.hypot(*z)),math.sqrt(.5))
        for a,z in zip(vectors,vectors[1:]))
    delta=sum(math.hypot(*v) for v in vectors)-12000000
    assert math.isclose(delta,4000000*(math.sqrt(2)-1),abs_tol=.001)


def test_cannot_force_offset_into_a_short_segment():
    assert offset_path((0,0),(2000000,0),1000000,1) is None


@pytest.mark.parametrize('leads',[(500000,4500000),(4500000,500000),(2500000,2500000)])
def test_matching_window_slides_without_changing_contact_or_added_length(leads):
    path=offset_path((0,0),(16000000,0),2400000,1,lead_nm=leads[0],end_lead_nm=leads[1])
    assert path[0]==(0,0) and path[-1]==(16000000,0)
    assert path[1]==(leads[0],0) and path[-2]==(16000000-leads[1],0)
    assert math.isclose(sum(math.dist(a,z) for a,z in zip(path,path[1:]))-16000000,
                        4800000*(math.sqrt(2)-1),abs_tol=.001)


@pytest.mark.parametrize('length',[7000000,16000000,50000000])
def test_compact_matching_windows_are_short_and_finitely_positioned(length):
    windows=compact_window_leads(length,2400000)
    assert 1<=len(windows)<=8 and len(windows)==len(set(windows))
    for first,last in windows:
        assert first>=500000 and last>=500000
        path=offset_path((0,0),(length,0),2400000,1,lead_nm=first,end_lead_nm=last)
        assert path[3][0]-path[2][0]==500000
        assert path[4][0]-path[1][0]==5300000


def test_short_or_unknown_compact_matching_windows_refuse():
    assert compact_window_leads(5000000,2400000)==[]
    for args in [(True,10),(10,False),(0,1),(1,-1),(1,float('nan'))]:
        with pytest.raises(ValueError):compact_window_leads(*args)


@pytest.mark.parametrize('args',[
    ((0,0),(0,0),1000000,1),((0,0),(1000000,1000000),1000000,1),
    ((0.,0),(5000000,0),1000000,1),((0,0),(5000000,0),0,1),
    ((0,0),(5000000,0),True,1),((0,0),(5000000,0),1000000,True),
    ((0,0),(5000000,0),1000000,0),((0,0),(5000000,0),float('nan'),1)])
def test_invalid_or_noncardinal_source_refuses(args):
    with pytest.raises(ValueError):offset_path(*args)


def native_fixture():
    import pcbnew as pcb
    from test_pair_member_obstacles import fixture
    b,nets,_=fixture()
    pair=dict(kind='can',p=nets[0].GetNetname(),n=nets[1].GetNetname(),
              width=.25,gap=.2,clearance=.2)
    p_items=[];n_items=[]
    for net,points,items in ((nets[0],[(6,20),(8,20),(34,20),(38,20)],p_items),
                             (nets[1],[(6,10),(8,10),(18,10),(28,10),(30,10)],n_items)):
        for a,z in zip(points,points[1:]):
            t=pcb.PCB_TRACK(b);t.SetStart(pcb.VECTOR2I_MM(*a));t.SetEnd(pcb.VECTOR2I_MM(*z))
            t.SetWidth(pcb.FromMM(.25));t.SetLayer(pcb.In2_Cu);t.SetNet(net);b.Add(t);items.append(t)
    return b,nets,pair,p_items,n_items


def test_native_proposal_only_replaces_explicit_owned_track_and_preserves_source_rules():
    import time
    import pcbnew as pcb
    from cec_pair_length_match import balance
    from cec_field_coupling import _field_snapshot_inventory
    b,nets,pair,p_items,n_items=native_fixture()
    retained={t.m_Uuid.AsString() for t in (*p_items,n_items[0],n_items[3])}
    before=_field_snapshot_inventory(b)
    original={n_items[1].m_Uuid.AsString(),n_items[2].m_Uuid.AsString()}
    result=balance(b,pair,original,deadline=time.monotonic()+2,max_changes=4)
    assert result['changes'] and result['after']['ok']
    assert result['after']['limit_mm']==result['before']['limit_mm']==4.
    assert not result['retained_source_geometry_editable'] and not result['release_authority']
    assert result['one_window_per_owned_original_track']
    assert all(c['retired_new_track_uuid'] in original for c in result['changes'])
    after=_field_snapshot_inventory(b)
    assert all(before[('track',key)]==after[('track',key)] for key in retained)
    assert all(t.GetWidth()==pcb.FromMM(.25) and t.GetLayer()==pcb.In2_Cu for t in b.GetTracks())


@pytest.mark.parametrize('condition',['unowned','expired','foreign','same_member_cycle'])
def test_native_blocker_or_absent_edit_authority_does_not_mutate_board(condition):
    import time
    import pcbnew as pcb
    from cec_pair_length_match import balance
    from cec_field_coupling import _field_snapshot_inventory
    b,nets,pair,p_items,n_items=native_fixture()
    if condition=='foreign':
        for y in (9.5,10.5):
            t=pcb.PCB_TRACK(b);t.SetStart(pcb.VECTOR2I_MM(8,y));t.SetEnd(pcb.VECTOR2I_MM(28,y))
            t.SetWidth(pcb.FromMM(.5));t.SetLayer(pcb.In2_Cu)
            t.SetNet(nets[0]);b.Add(t)
    if condition=='same_member_cycle':
        t=pcb.PCB_TRACK(b);t.SetStart(pcb.VECTOR2I_MM(9,9.2));t.SetEnd(pcb.VECTOR2I_MM(9,10.8))
        t.SetWidth(pcb.FromMM(.3));t.SetLayer(pcb.In2_Cu);t.SetNet(nets[1]);b.Add(t)
    editable=[] if condition=='unowned' else [n_items[1].m_Uuid.AsString()]
    before=_field_snapshot_inventory(b)
    result=balance(b,pair,editable,deadline=time.monotonic()+(-1 if condition=='expired' else 2),
                   max_proposals=2 if condition=='same_member_cycle' else 24,max_changes=4)
    assert result['changes']==[] and _field_snapshot_inventory(b)==before


def test_actual_via_contact_is_preserved_with_unchanged_straight_lead():
    import time
    import pcbnew as pcb
    from cec_pair_length_match import balance
    from cec_field_coupling import _field_snapshot_inventory
    from cec_native_items import discard_items
    b,nets,pair,p_items,n_items=native_fixture()
    discard_items(b,[n_items[0]])
    via=pcb.PCB_VIA(b);via.SetViaType(pcb.VIATYPE_THROUGH);via.SetLayerPair(pcb.F_Cu,pcb.B_Cu)
    via.SetPosition(pcb.VECTOR2I_MM(8,10));via.SetWidth(pcb.FromMM(.5))
    via.SetDrill(pcb.FromMM(.25));via.SetNet(nets[1]);b.Add(via)
    uid=via.m_Uuid.AsString();before=_field_snapshot_inventory(b)
    result=balance(b,pair,[n_items[1].m_Uuid.AsString()],deadline=time.monotonic()+2,max_changes=4)
    assert result['changes'] and uid in result['changes'][0]['unchanged_terminal_anchor_uuids']
    assert before[('track',uid)]==_field_snapshot_inventory(b)[('track',uid)]
    for change in result['changes']:
        a,z=change['points_nm'][:2]
        assert z[1]==a[1] and z[0]-a[0]==500000


@pytest.mark.parametrize('condition',['partial','expired','complete','unowned'])
def test_automatic_completed_transaction_boundary_requires_actual_native_completion(monkeypatch,condition):
    import time
    import cec_precision_route as route
    from cec_field_coupling import _field_snapshot_inventory
    b,nets,pair,p_items,n_items=native_fixture()
    owned={n_items[1].m_Uuid.AsString(),n_items[2].m_Uuid.AsString()}
    before_ids={t.m_Uuid.AsString() for t in b.GetTracks()}-(owned if condition!='unowned' else set())
    monkeypatch.setattr(route,'_native_pair_completion',lambda b,p:dict(complete=True,connected=condition!='partial'))
    before=_field_snapshot_inventory(b)
    result=route._match_completed_new_pair(b,pair,before_ids,
        time.monotonic()+(-1 if condition=='expired' else 2))
    if condition=='complete':
        assert result['attempted'] and result['after']['ok']
        assert all(c['retired_new_track_uuid'] in owned for c in result['changes'])
    else:
        assert not result['attempted'] and before==_field_snapshot_inventory(b)
