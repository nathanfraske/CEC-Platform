"""A literal entire chain is proposed; actual terminal boundaries are retained."""
import math
import pcbnew
import pytest
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track
from test_native_pending_joint_cohort import row
from root_native_whole_pending_linear_cohort_20261013 import plan


def fixture(quarter=0,shift=(0,0),fault=None):
    specs=[(10,20,'RENAMED'),(20,20,'RENAMED')]
    if fault=='pad':specs.append((15,20,'RENAMED'))
    b=_board(specs)
    points=[(10,20),(14.9,20),(15,20),(15.1,20),(20,20)]
    edges=[track(b,'RENAMED',a,z) for a,z in zip(points,points[1:])]
    if fault=='barrel':
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(15,20));v.SetWidth(600000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetNet(b.FindNet('RENAMED'));b.Add(v)
    if fault=='body':track(b,'RENAMED',(14.95,20),(14.95,16))
    if fault=='width':edges[1].SetWidth(250000)
    if fault=='face':edges[1].SetLayer(pcbnew.B_Cu)
    if fault=='locked':edges[1].SetLocked(True)
    if fault=='typed':
        g=pcbnew.PCB_GROUP(b);g.SetName('CEC_LOCAL_SUPPLY_ALLOCATION_V1|opaque');b.Add(g)
        for edge in edges:g.AddItem(edge)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        item.Move(pcbnew.VECTOR2I_MM(*shift))
    rows=[row(t) for t in edges]
    for r in rows:r['groups']=[g for g in b.Groups() if g.ContainsItem(r['item'])]
    return b,edges,rows


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('shift',[(0,0),(3,-2)])
def test_endcap_overlap_does_not_make_a_literal_whole_chain_into_branches(quarter,shift):
    b,edges,rows=fixture(quarter,shift)
    old=[(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth()) for t in edges]
    merged,retired,proof=plan(b,rows)
    assert len(merged)==1 and len(retired)==3 and len(proof['joins'])==1
    assert set(merged[0]['pending_member_uuids'])=={force._uid(t) for t in edges}
    assert old==[(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth()) for t in edges]
    assert not proof['native_geometry_mutated'] and not proof['current_qualified']
    assert not proof['automatic_retirement_authorized'] and not proof['release_authority']


@pytest.mark.parametrize('fault',['pad','barrel','body','width','face','locked','typed'])
def test_real_terminal_body_owner_face_and_width_boundaries_are_not_consumed(fault):
    b,edges,rows=fixture(fault=fault)
    merged,retired,proof=plan(b,rows)
    if fault in ('width','face','locked'):
        boundary=force._uid(edges[1])
        assert boundary not in retired
        assert any(r['uid']==boundary for r in merged)
        assert all(boundary not in j['member_uuids'] for j in proof['joins'])
        # A homogeneous subchain may still be proposed on either side; the
        # different-width/face/lock member itself cannot be consumed.
    else:
        assert not retired and not proof['joins'] and len(merged)==len(edges)


@pytest.mark.parametrize('fault',['net','group','coords','width','missing','zero'])
def test_nonliteral_source_rows_fail_before_geometry_can_be_changed(fault):
    b,edges,rows=fixture()
    if fault=='net':rows[0]['net']='WRONG'
    if fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('REAL_OWNER');b.Add(g);g.AddItem(edges[0])
    if fault=='coords':rows[0]['start']=(100,100)
    if fault=='width':rows[0]['width']+=1
    if fault=='missing':rows[0]['uid']='missing'
    if fault=='zero':edges[0].SetEnd(edges[0].GetStart());rows[0]=row(edges[0])
    old=[(tuple(t.GetStart()),tuple(t.GetEnd())) for t in edges]
    with pytest.raises(ValueError):plan(b,rows)
    assert old==[(tuple(t.GetStart()),tuple(t.GetEnd())) for t in edges]


@pytest.mark.parametrize('bad',[True,0,-1,math.nan,math.inf,10.1])
def test_only_bounded_finite_work_is_accepted(bad):
    b,edges,rows=fixture()
    with pytest.raises(ValueError):plan(b,rows,timeout_s=bad)


@pytest.mark.parametrize('kind',['linear','branch','joint','envelope'])
def test_explicit_input_budget_reaches_every_planner_without_expanding_a_cut(kind):
    b=_board([(0,0,'UNRELATED')]);edges=[]
    net=pcbnew.NETINFO_ITEM(b,'RENAMED');b.Add(net)
    for i in range(70):edges.append(track(b,'RENAMED',(10+i*3,10),(11+i*3,10)))
    rows=[row(t) for t in edges];old=[(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth()) for t in edges]
    if kind=='linear':call=lambda **kw:plan(b,rows,**kw)
    elif kind=='joint':
        from root_native_pending_joint_cohort_20261013 import coalesce
        call=lambda **kw:coalesce(b,rows,**kw)
    elif kind=='branch':
        from root_native_pending_branch_forest_20261013 import plan as branch
        call=lambda **kw:branch(b,rows,clearance_for=lambda n:200000,**kw)
    else:
        from root_free_junction_boundary_envelope_20261013 import expand
        call=lambda **kw:expand(b,rows,clearance_for=lambda n:200000,**kw)
    with pytest.raises(ValueError):call()
    result=call(maximum_input_edges=128)
    assert len(result[0])==70 and not result[1]
    assert old==[(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth()) for t in edges]
    with pytest.raises(ValueError):call(maximum_input_edges=129)
    with pytest.raises(ValueError):call(maximum_input_edges=True)
