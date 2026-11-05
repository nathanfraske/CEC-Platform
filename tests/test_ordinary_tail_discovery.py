"""Synthetic body-contact regressions; no board/reference/coordinate policy."""
import pytest
import cec_ordinary_tail_discovery as operator
import pcbnew


def board(monkeypatch):
    b=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(b,'N');b.Add(net)
    monkeypatch.setattr(operator.ordinary,'eligible_nets',lambda *a:{'N'})
    return b,net


def track(b,n,s,t,layer,width=200000):
    item=pcbnew.PCB_TRACK(b);item.SetStart(pcbnew.VECTOR2I(*s));item.SetEnd(pcbnew.VECTOR2I(*t))
    item.SetLayer(layer);item.SetWidth(width);item.SetNetCode(n.GetNetCode());b.Add(item)
    return item


def via(b,n,at):
    item=pcbnew.PCB_VIA(b);item.SetPosition(pcbnew.VECTOR2I(*at));item.SetDrill(300000)
    item.SetWidth(600000);item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);item.SetViaType(pcbnew.VIATYPE_THROUGH)
    item.SetNetCode(n.GetNetCode());b.Add(item);return item


def run(b,seeds):return operator.discover(b,'source','caller-board',[operator.force._uid(t) for t in seeds])


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,6,8])
@pytest.mark.parametrize('rotation',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_maximal_tail_stops_at_retained_barrel_cluster(monkeypatch,layer,rotation,mirror):
    b,n=board(monkeypatch)
    def pose(at):
        x,y=at
        if mirror:x=-x
        for _ in range(rotation):x,y=-y,x
        return (x+10000000,y+10000000)
    anchor=via(b,n,pose((0,0)));trunk=track(b,n,pose((0,0)),pose((3000000,0)),layer)
    tail=[track(b,n,pose(s),pose(t),layer) for s,t in [((0,0),(-1000000,0)),
        ((-1000000,0),(-2000000,0)),((-2000000,0),(-2000000,2000000))]]
    proof=run(b,[tail[-1]])
    assert set(proof['proposed_exact_track_uuids'])=={operator.force._uid(t) for t in tail}
    assert operator.force._uid(trunk) not in proof['proposed_exact_track_uuids']
    assert operator.force._uid(anchor) not in proof['proposed_exact_track_uuids']
    assert proof['complete'] and not proof['release_authority'] and not proof['routing_admitted']


def test_warning_bridge_between_two_barrels_is_not_a_tail(monkeypatch):
    b,n=board(monkeypatch);t=track(b,n,(0,0),(2000000,0),pcbnew.F_Cu)
    via(b,n,(0,0));via(b,n,(2000000,0))
    assert not run(b,[t])['proposed_exact_track_uuids']


def test_body_tee_cannot_be_inferred_from_centreline_endpoints(monkeypatch):
    b,n=board(monkeypatch);t=track(b,n,(0,0),(2000000,0),pcbnew.F_Cu)
    via(b,n,(0,0));track(b,n,(1000000,0),(1000000,2000000),pcbnew.F_Cu)
    assert not run(b,[t])['proposed_exact_track_uuids']


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,6,8])
@pytest.mark.parametrize('rotation',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_overlapping_overhang_removed_only_with_retained_contact_cluster(monkeypatch,layer,rotation,mirror):
    b,n=board(monkeypatch)
    def pose(at):
        x,y=at
        if mirror:x=-x
        for _ in range(rotation):x,y=-y,x
        return x+12000000,y+17000000
    retained=track(b,n,pose((0,0)),pose((6000000,0)),layer)
    branch=track(b,n,pose((0,0)),pose((0,3000000)),layer)
    overhang=track(b,n,pose((-750000,0)),pose((6000000,0)),layer)
    proof=run(b,[overhang])
    assert proof['proposed_exact_track_uuids']==[operator.force._uid(overhang)]
    assert not {operator.force._uid(retained),operator.force._uid(branch)}&set(proof['proposed_exact_track_uuids'])


@pytest.mark.parametrize('kind',['disconnected','crossing','offset','different_width'])
def test_overlap_does_not_grant_authority_to_cut_a_real_bridge(monkeypatch,kind):
    b,n=board(monkeypatch);seed=track(b,n,(0,0),(6000000,0),pcbnew.F_Cu)
    via(b,n,(0,0))
    if kind in ('offset','different_width'):via(b,n,(6000000,0))
    if kind=='disconnected':track(b,n,(3000000,0),(6000000,0),pcbnew.F_Cu)
    if kind=='crossing':track(b,n,(3000000,0),(3000000,3000000),pcbnew.F_Cu)
    if kind=='offset':track(b,n,(0,100000),(6000000,100000),pcbnew.F_Cu)
    if kind=='different_width':track(b,n,(0,0),(6000000,0),pcbnew.F_Cu,width=150000)
    assert not run(b,[seed])['proposed_exact_track_uuids']


def test_power_not_proposed_even_if_native_warning(monkeypatch):
    b,n=board(monkeypatch);t=track(b,n,(0,0),(2000000,0),pcbnew.F_Cu)
    monkeypatch.setattr(operator.ordinary,'eligible_nets',lambda *a:set())
    assert not run(b,[t])['proposed_exact_track_uuids']


def test_grouped_source_copper_is_not_proposed(monkeypatch):
    b,n=board(monkeypatch);t=track(b,n,(0,0),(2000000,0),pcbnew.F_Cu)
    group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(t)
    assert not run(b,[t])['proposed_exact_track_uuids']


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,6,8])
@pytest.mark.parametrize('bridge',[False,True])
def test_actual_plated_through_pad_is_a_protected_contact(monkeypatch,layer,bridge):
    b,n=board(monkeypatch)
    def pad(at):
        f=pcbnew.FOOTPRINT(b);b.Add(f);p=pcbnew.PAD(f);p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetPosition(pcbnew.VECTOR2I(*at));p.SetSize(pcbnew.VECTOR2I(1600000,1600000))
        p.SetDrillSize(pcbnew.VECTOR2I(800000,800000));p.SetLayerSet(pcbnew.LSET.AllCuMask())
        p.SetNetCode(n.GetNetCode());f.Add(p);return p
    a=pad((0,0));t=track(b,n,(0,0),(3000000,0),layer)
    if bridge:
        pad((3000000,0));assert not run(b,[t])['proposed_exact_track_uuids']
    else:
        trunk=track(b,n,(0,0),(0,3000000),layer)
        proof=run(b,[t]);assert proof['proposed_exact_track_uuids']==[operator.force._uid(t)]
        assert operator.force._uid(a) not in proof['proposed_exact_track_uuids']
        assert operator.force._uid(trunk) not in proof['proposed_exact_track_uuids']


@pytest.mark.parametrize('deadline',[True,float('nan'),float('inf'),'10',0.,11.])
def test_invalid_deadline_types_and_values_refused(monkeypatch,deadline):
    b,n=board(monkeypatch)
    with pytest.raises(ValueError):operator.discover(b,'source','caller',[],timeout_s=deadline)


def test_overlong_whole_tail_scope_is_refused(monkeypatch):
    b,n=board(monkeypatch);tail=[track(b,n,(i*1000000,0),((i+1)*1000000,0),pcbnew.F_Cu) for i in range(33)]
    via(b,n,(0,0));track(b,n,(0,0),(0,3000000),pcbnew.F_Cu)
    with pytest.raises(ValueError,match='scope_bound'):run(b,[tail[-1]])


@pytest.mark.parametrize('kind',['missing','duplicate','oversized','deadline'])
def test_invalid_or_unbounded_hint_is_refused(monkeypatch,kind):
    b,n=board(monkeypatch);t=track(b,n,(0,0),(2000000,0),pcbnew.F_Cu);u=operator.force._uid(t)
    ids={'missing':['not-present'],'duplicate':[u,u],'oversized':[str(i) for i in range(33)],'deadline':[u]}[kind]
    with pytest.raises(ValueError):operator.discover(b,'source','caller',ids,timeout_s=0 if kind=='deadline' else 10)


@pytest.mark.parametrize('rotation',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('width',[220000,500000])
def test_touching_short_hint_capsules_form_one_bounded_retained_contact_cluster(monkeypatch,rotation,mirror,width):
    b,n=board(monkeypatch)
    def pose(p):
        x,y=p
        if mirror:x=-x
        for _ in range(rotation):x,y=-y,x
        scale=width/500000
        return round(x*scale)+10000000,round(y*scale)+10000000
    a=track(b,n,pose((0,0)),pose((0,70000)),pcbnew.F_Cu,width=width)
    z=track(b,n,pose((0,70000)),pose((-300000,370000)),pcbnew.F_Cu,width=width)
    retained=track(b,n,pose((3000000,380000)),pose((0,380000)),pcbnew.F_Cu,width=width)
    # This retained lead bridges two protected contacts; contracting the
    # short lobe cannot retire it as another dead stem.
    via(b,n,pose((3000000,380000)))
    track(b,n,pose((1500000,380000)),pose((1500000,2400000)),pcbnew.F_Cu,width=width)
    ids=[operator.force._uid(t)for t in(a,z)]
    # The legacy individual-tail walk remains strict. Only the explicitly
    # enabled, exact hinted cohort receives the new construction suggestion.
    assert not operator._discover_native_leaf_chains(b,ids,positive_nets={'N'},
        maximum_width_nm=1000000)['proposed_exact_track_uuids']
    result=operator._discover_native_leaf_chains(b,ids,positive_nets={'N'},
        maximum_width_nm=1000000,allow_connected_seed_cohorts=True)
    assert set(result['proposed_exact_track_uuids'])==set(ids)
    assert operator.force._uid(retained)not in result['proposed_exact_track_uuids']
    assert not result['routing_admitted']and not result['release_authority']
    if width<500000:
        typed=operator.discover(b,'source','caller-board',ids,allow_connected_seed_cohorts=True)
        assert set(typed['proposed_exact_track_uuids'])==set(ids)
        assert not operator.discover(b,'source','caller-board',ids)['proposed_exact_track_uuids']


@pytest.mark.parametrize('fault',['second_contact_cluster','unhinted_peer','different_width',
    'different_face','grouped','zone'])
def test_hint_cohorts_do_not_absorb_real_bridges_or_unhinted_material(monkeypatch,fault):
    b,n=board(monkeypatch)
    a=track(b,n,(0,0),(0,70000),pcbnew.F_Cu,width=500000)
    z=track(b,n,(0,70000),(-300000,370000),pcbnew.F_Cu,width=500000)
    track(b,n,(1400000,380000),(0,380000),pcbnew.F_Cu,width=500000)
    if fault=='second_contact_cluster':via(b,n,(-700000,700000))
    if fault=='different_width':z.SetWidth(490000)
    if fault=='different_face':z.SetLayer(pcbnew.B_Cu)
    if fault=='grouped':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(z)
    if fault=='zone':
        zone=pcbnew.ZONE(b);zone.SetNet(n);zone.SetLayer(pcbnew.F_Cu);b.Add(zone)
    ids=[operator.force._uid(t)for t in([a]if fault=='unhinted_peer'else[a,z])]
    result=operator._discover_native_leaf_chains(b,ids,positive_nets={'N'},
        maximum_width_nm=1000000,allow_connected_seed_cohorts=True)
    assert not any(row.get('connected_hinted_seed_cohort')for row in result['attempts'])


@pytest.mark.parametrize('split_retained_cluster',[False,True])
def test_contracted_supply_hint_lobe_includes_old_stem_only_with_one_retained_body_cluster(monkeypatch,split_retained_cluster):
    b,n=board(monkeypatch)
    a=track(b,n,(0,0),(0,70000),pcbnew.F_Cu,width=500000)
    z=track(b,n,(0,70000),(-300000,370000),pcbnew.F_Cu,width=500000)
    stem=track(b,n,(1400000,380000),(380000,380000),pcbnew.F_Cu,width=500000)
    # The first two native bodies meet the stem's distal capsule. Its root
    # overlaps a retained fan junction, not necessarily their centrelines.
    track(b,n,(1980000,-180000),(1400000,380000),pcbnew.F_Cu,width=500000)
    track(b,n,(3800000,380000),(1400000,380000),pcbnew.F_Cu,width=500000)
    if split_retained_cluster:
        # Interior branch at the opposite end does NOT contact that fan.
        via(b,n,(180000,700000))
    ids=[operator.force._uid(t)for t in(a,z)]
    result=operator._discover_native_leaf_chains(b,ids,positive_nets={'N'},
        maximum_width_nm=1000000,allow_connected_seed_cohorts=True)
    # This fixture's positive topology may need a centreline-endpoint route
    # or the Source-cohort body rule, but cannot cut across two root clusters.
    assert (operator.force._uid(stem)in result['proposed_exact_track_uuids'])==(not split_retained_cluster)
    assert not result['routing_admitted']and not result['current_qualified']
