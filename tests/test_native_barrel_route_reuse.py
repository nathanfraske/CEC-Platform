"""Actual retained drill/annulus evidence, no new-via or current waiver."""
import math
import time

import pcbnew
import pytest

import cec_fr as fr
import cec_native_barrel_portals as portals
import cec_measurement_leaf as leaf
from test_lastmile import _board


def fixture(quarter=0, mirror=False, reverse=False, kind='pad'):
    b = _board([], edge=(0, 0, 20, 20)); b.SetCopperLayerCount(6)
    net = pcbnew.NETINFO_ITEM(b, '/renamed/%s/%s/path' % (quarter, mirror)); b.Add(net)
    def pose(x, y):
        x, y = x-10, y-10
        if mirror: x = -x
        for _ in range(quarter): x, y = -y, x
        return pcbnew.VECTOR2I_MM(10+x, 10+y)
    start, end, at = pose(5, 10), pose(15, 10), pose(10.13, 10)
    if kind == 'via':
        item = pcbnew.PCB_VIA(b); item.SetPosition(at); item.SetWidth(1000000); item.SetDrill(500000)
        item.SetViaType(pcbnew.VIATYPE_THROUGH); item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        item.SetNet(net); b.Add(item)
    else:
        fp = pcbnew.FOOTPRINT(b); fp.SetReference('UNRELATED'); fp.SetPosition(at)
        item = pcbnew.PAD(fp); item.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        item.SetShape(pcbnew.PAD_SHAPE_CIRCLE); item.SetSize(pcbnew.VECTOR2I_MM(1., 1.))
        item.SetDrillSize(pcbnew.VECTOR2I_MM(.5, .5)); item.SetLayerSet(pcbnew.LSET.AllCuMask())
        item.SetPosition(at); item.SetNet(net); fp.Add(item); b.Add(fp)
    first, last = (pcbnew.B_Cu, pcbnew.F_Cu) if reverse else (pcbnew.F_Cu, pcbnew.B_Cu)
    dx, dy = end.x-start.x, end.y-start.y
    def along(pt): return (pt.x-at.x)*dx+(pt.y-at.y)*dy
    def corridor(a, z, _width, _gap, layer, _copper):
        if any((p.x-start.x)*dy != (p.y-start.y)*dx for p in (a, z)): return False
        return max(along(a), along(z)) <= 0 if layer == first else min(along(a), along(z)) >= 0
    return b, net, start, end, at, item, first, last, corridor


def search(b, net, start, end, first, last, *, enabled=True, guard=None, planar_guard=None):
    detail = {}
    ops = fr._multilayer_maze_lastmile_ops(b, start, end, net.GetNetCode(), [first, last], 200000,
        lambda *a: True, width_for_layer=lambda l: 250000, start_layers=[first], end_layers=[last],
        grid_mm=.5, margin_mm=1., max_vias=0, max_length_nm=16000000,
        deadline_monotonic=time.monotonic()+3., diagnostics=detail, canonical_turns_only=True,
        neutral_state_dominance=True, field_state_dominance=True,
        reuse_retained_barrels=enabled, retained_barrel_guard=guard, planar_guard=planar_guard)
    return ops, detail


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('kind', ['pad', 'via'])
def test_actual_off_grid_retained_barrel_changes_face_without_a_new_drill(
        quarter, mirror, reverse, kind, monkeypatch):
    b,n,s,t,at,item,first,last,corridor = fixture(quarter,mirror,reverse,kind)
    before = leaf._binding(b)
    monkeypatch.setattr(fr, '_foreign_shape_indexes', lambda b,l,*a,**k: (l, []))
    monkeypatch.setattr(fr, '_snapshot_foreign_clear', corridor)
    monkeypatch.setattr(fr, '_guarded_power_reservations', lambda: [])
    monkeypatch.setattr(fr, '_via_spot_clear', lambda *a,**k: pytest.fail('No new via is authorized'))
    ops,detail = search(b,n,s,t,first,last)
    assert ops and all(op[0]=='trk' for op in ops), detail
    assert sum(math.dist(op[1],op[2]) for op in ops) == 10000000
    assert {int(op[4]) for op in ops} == {first,last}
    assert len(detail['retained_barrel_transitions']) == 1
    proof = detail['retained_barrel_transitions'][0]
    assert proof['uuid']==item.m_Uuid.AsString() and proof['at_nm']==list(at)
    assert proof['finite_new_incident_copper_verified'] and not proof['new_barrel']
    assert not proof['barrel_capacity_qualified'] and not detail['release_authority']
    assert before == leaf._binding(b)
    legacy,legacy_detail = search(b,n,s,t,first,last,enabled=False)
    assert legacy is None and legacy_detail['stop']=='bounded_graph_exhausted'


@pytest.mark.parametrize('fault', ['npth','smd_multiface','wrong_net','partial_drill','no_hole'])
def test_only_actual_same_net_complete_plated_barrels_propose_layer_access(fault):
    b,n,s,t,at,item,first,last,_ = fixture()
    if fault=='npth': item.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    elif fault=='smd_multiface': item.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    elif fault=='wrong_net':
        other=pcbnew.NETINFO_ITEM(b,'different');b.Add(other);item.SetNet(other)
    elif fault=='partial_drill':item.SetPrimaryDrillEndLayer(pcbnew.In2_Cu)
    else:item.SetDrillSize(pcbnew.VECTOR2I(0,0))
    before=leaf._binding(b)
    rows=portals.inventory(b,n.GetNetCode(),[first,last],(0,0,20000000,20000000),deadline=time.monotonic()+2.)
    assert not rows and before==leaf._binding(b)


@pytest.mark.parametrize('refusal', ['caller','field','native'])
def test_existing_barrel_does_not_waive_source_field_native_or_caller_guard(refusal,monkeypatch):
    b,n,s,t,at,item,first,last,corridor=fixture()
    monkeypatch.setattr(fr,'_foreign_shape_indexes',lambda b,l,*a,**k:(l,[]))
    monkeypatch.setattr(fr,'_snapshot_foreign_clear',lambda a,z,w,g,l,c:
        corridor(a,z,w,g,l,c) and not (refusal=='native' and a==z==at and l==last))
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[])
    before=leaf._binding(b)
    ops,detail=search(b,n,s,t,first,last,guard=(lambda *a:False) if refusal=='caller' else None,
        planar_guard=(lambda a,z,w,l:not(a==z==at and l==last)) if refusal=='field' else None)
    assert ops is None and not detail['no_path_proof']
    assert not detail['retained_barrel_transitions'] and before==leaf._binding(b)


def test_track_coincidence_inside_a_drill_void_is_not_finite_contact():
    b,n,s,t,at,item,first,last,_=fixture()
    row=portals.inventory(b,n.GetNetCode(),[first,last],(0,0,20000000,20000000),deadline=time.monotonic()+2.)[tuple(at)][0]
    ops=[('trk',at-pcbnew.VECTOR2I(10000,0),at,50000,first),
         ('trk',at,at+pcbnew.VECTOR2I(10000,0),50000,last)]
    before=leaf._binding(b)
    with pytest.raises(ValueError,match='finite_incident_copper'):
        portals.receive_operations(b,ops,[(row,first,last)],deadline=time.monotonic()+2.)
    assert before==leaf._binding(b)


@pytest.mark.parametrize('kwargs', [dict(reuse_retained_barrels=1),
    dict(reuse_retained_barrels='yes'),dict(retained_barrel_guard=True),
    dict(retained_barrel_guard=lambda *a:True),dict(reuse_retained_barrels=True)])
def test_retained_barrel_search_requires_explicit_bounded_policy(kwargs):
    b,n,s,t,at,item,first,last,_=fixture()
    with pytest.raises(ValueError):
        fr._multilayer_maze_lastmile_ops(b,s,t,n.GetNetCode(),[first,last],200000,
            lambda *a:True,width_for_layer=lambda l:250000,max_vias=0,**kwargs)


def test_retained_barrel_long_deadline_is_bound_at_test_invocation_not_collection():
    # Collection can precede this test by tens of seconds in a parallel full
    # replay. An import-time deadline stops testing the intended >10 s lease.
    b,n,s,t,at,item,first,last,_=fixture()
    with pytest.raises(ValueError,match='explicit_short_lease'):
        fr._multilayer_maze_lastmile_ops(b,s,t,n.GetNetCode(),[first,last],200000,
            lambda *a:True,width_for_layer=lambda l:250000,max_vias=0,
            reuse_retained_barrels=True,deadline_monotonic=time.monotonic()+30.)
