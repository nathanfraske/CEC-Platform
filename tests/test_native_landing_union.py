"""Native zone/link unions preserve intentional notches and source evidence."""
import copy
import time

import pcbnew
import pytest
from shapely.geometry import Point, Polygon

import cec_rectilinear_copper as owner
from cec_local_copper_cell import copper_inventory
from test_rectilinear_copper import fixture


def native_setup(angle=0,mirror=False,layer=pcbnew.F_Cu,foreign=True):
    b,ts=fixture();net=ts[0].GetNet()
    for t in ts:b.Remove(t)
    for fp in list(b.GetFootprints()):b.Remove(fp)
    def at(x,y):
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return pcbnew.VECTOR2I_MM(30+x,30+y)
    def pad(n,x,y,size):
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);p=pcbnew.PAD(fp);fp.Add(p)
        p.SetNet(n);p.SetPosition(at(x,y));p.SetSize(pcbnew.VECTOR2I_MM(size,size))
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET();layers.AddLayer(layer);p.SetLayerSet(layers)
        return p
    t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetLayer(layer);t.SetWidth(1000000)
    t.SetStart(at(4,-2));t.SetEnd(at(2,0));b.Add(t)
    pad(net,4,-2,2);pad(net,1.5,5,1.2)
    z=pcbnew.ZONE(b);z.SetNet(net);z.SetLayer(layer);z.SetLocalClearance(200000)
    z.SetMinThickness(100000);z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetAssignedPriority(1)
    z.SetZoneName('RENAMED_NOTCHED_NATIVE_LANDING');z.Outline().NewOutline()
    for x,y in [(0,6),(2.4,6),(2.4,5.8),(2.6,5.8),(2.6,0),(1.2,0),(1.2,3),(0,3)]:
        p=at(x,y);z.Outline().Append(p.x,p.y)
    b.Add(z)
    if foreign:
        n=pcbnew.NETINFO_ITEM(b,'/RENAMED_FOREIGN');b.Add(n);pad(n,.85,1,.15)
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    return b,t,z,at


def plan(b,t,z,**kwargs):
    return owner.plan(b,[t.m_Uuid.AsString()],required_width_nm=1000000,
        clearance_nm=200000,min_thickness_nm=100000,contour_style='chamfer45',
        contour_grid_nm=1000,fill_envelope_margin_nm=4,retire_source_tracks=False,
        enclosing_native_zone_uuids=[z.m_Uuid.AsString()],**kwargs)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_native_notched_landing_union_cleans_only_small_safe_steps(
        tmp_path,angle,mirror,layer):
    b,t,z,at=native_setup(angle,mirror,layer);before=copper_inventory(b)
    native=owner._support_row(z,int(layer),time.monotonic()+2)
    p=plan(b,t,z,landing_enclosure_mode='canonical_outline',landing_max_jog_nm=250000)
    assert copper_inventory(b)==before
    profile=Polygon(p['polygon_nm']);outside=at(.85,1);closure=at(2.5,5.9)
    assert not profile.covers(Point(outside.x,outside.y))
    assert profile.covers(Point(closure.x,closure.y))
    e=owner.materialize(b,p);new=next(z for z in b.Zones() if z.m_Uuid.AsString()==e['zone_uuid'])
    batch=pcbnew.ZONES();batch.append(new);b.BuildConnectivity()
    assert pcbnew.ZONE_FILLER(b).Fill(batch)
    path=tmp_path/'saved-native-union.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    saved=pcbnew.LoadBoard(str(path));r=owner.receive(saved,p,e['zone_uuid'])
    assert r['ok'] and r['complete'],r
    old=next(z for z in saved.Zones() if z.m_Uuid.AsString()==native['uuid'])
    assert owner._support_row(old,int(layer),time.monotonic()+2)==native
    assert not r['new_capacity_credited'] and not r['release_authority']


@pytest.mark.parametrize('convex',[False,True])
def test_explicit_convex_native_fill_union_is_reconstructed_not_guessed(convex,tmp_path):
    b,t,z,_=native_setup(foreign=False)
    p=plan(b,t,z,convex_support_cover=convex)
    e=owner.materialize(b,p);new=next(z for z in b.Zones() if z.m_Uuid.AsString()==e['zone_uuid'])
    batch=pcbnew.ZONES();batch.append(new);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(batch)
    path=tmp_path/'convex-native.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    r=owner.receive(pcbnew.LoadBoard(str(path)),p,e['zone_uuid'])
    assert r['complete'] and r['ok'],r


def test_full_convex_cover_is_refused_when_it_erases_a_real_foreign_pad_notch():
    b,t,z,_=native_setup();before=copper_inventory(b)
    with pytest.raises(owner.Refused,match='foreign_native'):
        plan(b,t,z)
    assert copper_inventory(b)==before


def test_small_step_inside_actual_foreign_clearance_stays_unclosed():
    b,t,z,at=native_setup();net=b.FindNet('/RENAMED_FOREIGN')
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);pad=pcbnew.PAD(fp);fp.Add(pad)
    pad.SetNet(net);pad.SetPosition(at(2.5,5.9));pad.SetSize(pcbnew.VECTOR2I_MM(.05,.05))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
    p=plan(b,t,z,landing_enclosure_mode='canonical_outline',landing_max_jog_nm=250000)
    assert not Polygon(p['polygon_nm']).covers(Point(pad.GetPosition().x,pad.GetPosition().y))


@pytest.mark.parametrize('fault',['rehashed_profile','rehashed_mode','changed_source_outline',
    'changed_source_fill','unfilled','wrong_net','wrong_layer','missing','duplicate','invalid_mode',
    'unbound_jog','jog_bound','convex_with_notch'])
def test_landing_union_requires_exact_native_source_and_policy_before_mutation(fault):
    b,t,z,_=native_setup();p=plan(b,t,z,landing_enclosure_mode='canonical_outline',landing_max_jog_nm=250000)
    if fault=='duplicate':
        with pytest.raises(owner.Refused):
            owner.plan(b,[t.m_Uuid.AsString()],required_width_nm=1000000,clearance_nm=200000,
                min_thickness_nm=100000,enclosing_native_zone_uuids=[z.m_Uuid.AsString()]*2)
        return
    if fault=='rehashed_profile':p['polygon_nm'][0][0]+=1
    elif fault=='rehashed_mode':p['landing_enclosure_mode']='convex_fill';p['landing_max_jog_nm']=0
    elif fault=='changed_source_outline':z.Outline().Append(30300000,30300000)
    elif fault=='changed_source_fill':z.SetFilledPolysList(pcbnew.F_Cu,owner._poly([(0,0),(1,0),(1,1),(0,1)]))
    elif fault=='unfilled':z.SetIsFilled(False)
    elif fault=='wrong_net':z.SetNet(b.FindNet('/RENAMED_FOREIGN'))
    elif fault=='wrong_layer':z.SetLayer(pcbnew.B_Cu)
    elif fault=='missing':b.Remove(z)
    elif fault=='invalid_mode':p['landing_enclosure_mode']='cosmetic_mask'
    elif fault=='unbound_jog':p['enclosing_native_zone_uuids']=[]
    elif fault=='jog_bound':p['landing_max_jog_nm']=1000001
    else:p['convex_support_cover']=True
    p=copy.deepcopy(p);p.pop('plan_sha256');p['plan_sha256']=owner._digest(p)
    before=copper_inventory(b)
    with pytest.raises(owner.Refused):owner.materialize(b,p)
    assert copper_inventory(b)==before


def test_foreign_actual_filled_zone_is_not_hidden_by_a_plausible_outline():
    b,t,z,_=native_setup(foreign=False);p=plan(b,t,z,landing_enclosure_mode='canonical_outline')
    net=pcbnew.NETINFO_ITEM(b,'/ANOTHER_NATIVE_NET');b.Add(net)
    other=pcbnew.ZONE(b);other.SetNet(net);other.SetLayer(pcbnew.F_Cu);other.Outline().NewOutline()
    fill=owner._poly([(34000000,28000000),(34100000,28000000),(34100000,28100000),(34000000,28100000)])
    for x,y in [(0,0),(1000000,0),(1000000,1000000),(0,1000000)]:other.Outline().Append(x,y)
    other.SetFilledPolysList(pcbnew.F_Cu,fill);other.SetIsFilled(True);b.Add(other)
    before=copper_inventory(b)
    with pytest.raises(owner.Refused,match='foreign_native_zone'):
        owner.materialize(b,p)
    assert copper_inventory(b)==before


def test_same_priority_native_owner_requests_consolidation_not_priority_escalation():
    b,t,z,_=native_setup();z.SetAssignedPriority(0);before=copper_inventory(b)
    with pytest.raises(owner.Refused,match='same_priority_native_zone_requires_consolidation'):
        plan(b,t,z,landing_enclosure_mode='canonical_outline')
    assert copper_inventory(b)==before and z.GetAssignedPriority()==0


@pytest.mark.parametrize('receiving_only',[False,True])
def test_rehashed_extra_native_slab_is_not_construction_or_saved_receiving_authority(receiving_only):
    b,ts=fixture();ids=[t.m_Uuid.AsString() for t in ts]
    p=owner.plan(b,ids,required_width_nm=1500000,clearance_nm=200000,
        min_thickness_nm=100000,retire_source_tracks=False)
    emitted=owner.materialize(b,p) if receiving_only else None
    forged=copy.deepcopy(p)
    forged['polygon_nm']=[[28000000,28000000],[41000000,28000000],
        [41000000,41000000],[28000000,41000000]]
    forged.pop('plan_sha256');forged['plan_sha256']=owner._digest(forged)
    if not receiving_only:
        before=copper_inventory(b)
        with pytest.raises(owner.Refused,match='derived'):
            owner.materialize(b,forged)
        assert copper_inventory(b)==before
    else:
        z=next(z for z in b.Zones() if z.m_Uuid.AsString()==emitted['zone_uuid'])
        z.Outline().RemoveAllContours();z.Outline().NewOutline()
        for x,y in forged['polygon_nm']:z.Outline().Append(x,y)
        z.SetFilledPolysList(pcbnew.F_Cu,owner._poly(forged['polygon_nm']));z.SetIsFilled(True)
        r=owner.receive(b,forged,emitted['zone_uuid'])
        assert not r['ok'] and 'derived' in r['reason'],r


def test_multinet_prefix_needs_actual_native_fill_before_the_next_obstacle_check():
    b,ts=fixture();n=pcbnew.NETINFO_ITEM(b,'/SECOND_UNRELATED_DOMAIN');b.Add(n)
    extra=pcbnew.PCB_TRACK(b);extra.SetNet(n);extra.SetLayer(pcbnew.F_Cu)
    extra.SetStart(pcbnew.VECTOR2I_MM(10,10));extra.SetEnd(pcbnew.VECTOR2I_MM(18,10))
    extra.SetWidth(2000000);b.Add(extra)
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);pad=pcbnew.PAD(fp);fp.Add(pad)
    pad.SetNet(n);pad.SetPosition(extra.GetStart());pad.SetSize(pcbnew.VECTOR2I_MM(2,2))
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
    plans=[owner.plan(b,ids,required_width_nm=1500000,clearance_nm=200000,
        min_thickness_nm=100000,retire_source_tracks=False)
        for ids in ([t.m_Uuid.AsString() for t in ts],[extra.m_Uuid.AsString()])]
    first=owner.materialize(b,plans[0]);before=copper_inventory(b)
    with pytest.raises(owner.Refused,match='foreign_native_zone_fill_unknown'):
        owner.materialize(b,plans[1])
    assert copper_inventory(b)==before
    batch=pcbnew.ZONES();batch.append(next(z for z in b.Zones() if z.m_Uuid.AsString()==first['zone_uuid']))
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(batch)
    assert owner.receive(b,plans[0],first['zone_uuid'])['ok']
    second=owner.materialize(b,plans[1]);batch=pcbnew.ZONES()
    batch.append(next(z for z in b.Zones() if z.m_Uuid.AsString()==second['zone_uuid']))
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(batch)
    assert owner.receive(b,plans[1],second['zone_uuid'])['ok']


def keeper_setup(**kwargs):
    b,t,z,at=native_setup(**kwargs);z.SetZoneName(owner.ZONE_NAME);z.SetAssignedPriority(0)
    return b,t,z,at


def keeper_plan(b,t,z,**kwargs):
    return plan(b,t,z,landing_enclosure_mode='canonical_outline',landing_max_jog_nm=250000,
        replace_native_zone_uuid=z.m_Uuid.AsString(),**kwargs)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_native_keeper_consolidation_retains_uuid_configuration_and_old_fill(
        tmp_path,angle,mirror,layer):
    from cec_rounded_landing import _configuration
    b,t,z,_=keeper_setup(angle=angle,mirror=mirror,layer=layer)
    config=_configuration(z);old=z.GetFilledPolysList(layer).CloneDropTriangulation()
    p=keeper_plan(b,t,z);assert p['replacement_source_zone']['configuration']==config
    e=owner.materialize(b,p);assert e['modified_zone_uuids']==[config['uuid']]
    assert len(list(b.Zones()))==1 and _configuration(z)==config
    batch=pcbnew.ZONES();batch.append(z);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(batch)
    path=tmp_path/'saved-native-keeper.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    saved=pcbnew.LoadBoard(str(path));r=owner.receive(saved,p,e['zone_uuid'])
    assert r['complete'] and r['ok'] and r['original_native_keeper_fill_preserved'],r
    actual=next(z for z in saved.Zones() if z.m_Uuid.AsString()==config['uuid'])
    assert _configuration(actual)==config
    old.BooleanSubtract(actual.GetFilledPolysList(layer));assert not old.OutlineCount()
    assert not r['release_authority'] and not r['new_capacity_credited']


def test_locked_native_keeper_needs_its_own_identity_authority_not_just_track_permission():
    b,t,z,_=keeper_setup();t.SetLocked(True);z.SetLocked(True)
    tuid=t.m_Uuid.AsString();zuid=z.m_Uuid.AsString();before=copper_inventory(b)
    with pytest.raises(owner.Refused,match='keeper_lock_group_authority'):
        keeper_plan(b,t,z,allow_locked_track_uuids=[tuid])
    p=keeper_plan(b,t,z,allow_locked_track_uuids=[tuid],allow_locked_zone_uuids=[zuid])
    with pytest.raises(owner.Refused,match='keeper_authority'):
        owner.materialize(b,p,allow_locked_track_uuids=[tuid])
    assert copper_inventory(b)==before
    owner.materialize(b,p,allow_locked_track_uuids=[tuid],allow_locked_zone_uuids=[zuid])


@pytest.mark.parametrize('fault',['changed_source','rehashed_source','rehashed_extra_slab',
    'changed_priority','changed_clearance','source_loss','unfilled'])
def test_keeper_identity_process_and_every_old_native_fill_point_remain_gates(fault):
    b,t,z,_=keeper_setup();p=keeper_plan(b,t,z)
    if fault in ('changed_source','rehashed_source','rehashed_extra_slab'):
        if fault=='changed_source':z.SetAssignedPriority(1)
        elif fault=='rehashed_source':p['replacement_source_zone']['fill_nm'][0][0]+=1
        else:p['polygon_nm'][0][0]+=1
        if fault.startswith('rehashed'):
            p.pop('plan_sha256');p['plan_sha256']=owner._digest(p)
        before=copper_inventory(b)
        with pytest.raises(owner.Refused):owner.materialize(b,p)
        assert copper_inventory(b)==before
        return
    e=owner.materialize(b,p)
    fill=owner._poly(p['polygon_nm']);z.SetFilledPolysList(pcbnew.F_Cu,fill);z.SetIsFilled(True)
    if fault=='changed_priority':z.SetAssignedPriority(1)
    elif fault=='changed_clearance':z.SetLocalClearance(z.GetLocalClearance()-1)
    elif fault=='unfilled':z.SetIsFilled(False)
    else:
        # This point lies in the old landing but not the selected incoming
        # stroke. Source-landing loss must be checked independently of caps.
        fill.BooleanSubtract(owner._poly([(31500000,35000000),(31500001,35000000),
            (31500001,35000001),(31500000,35000001)]))
        z.SetFilledPolysList(pcbnew.F_Cu,fill)
    r=owner.receive(b,p,e['zone_uuid']);assert not r['ok'],r
    if fault=='source_loss':assert r['reason']=='native_keeper_source_fill_loss'


def high_priority_setup(angle=0,mirror=False,layer=pcbnew.F_Cu):
    b,t,z,at=keeper_setup(angle=angle,mirror=mirror,layer=layer)
    n=b.FindNet('/RENAMED_FOREIGN')
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);pad=pcbnew.PAD(fp);fp.Add(pad)
    pad.SetNet(n);pad.SetPosition(at(3.9,3.8));pad.SetSize(pcbnew.VECTOR2I_MM(.1,.1))
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    layers=pcbnew.LSET();layers.AddLayer(layer);pad.SetLayerSet(layers)
    high=pcbnew.ZONE(b);high.SetNet(t.GetNet());high.SetLayer(layer)
    high.SetZoneName('UNCHANGED_HIGHER_PRIORITY_OWNER');high.SetAssignedPriority(3)
    high.SetLocalClearance(500000);high.SetMinThickness(100000)
    high.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL);high.Outline().NewOutline()
    for x,y in [(2.6,3),(3.6,3),(3.6,4.5),(2.6,4.5)]:
        v=at(x,y);high.Outline().Append(v.x,v.y)
    b.Add(high)
    anchor_fp=pcbnew.FOOTPRINT(b);b.Add(anchor_fp);anchor=pcbnew.PAD(anchor_fp);anchor_fp.Add(anchor)
    anchor.SetNet(t.GetNet());anchor.SetPosition(at(2.9,3.4))
    anchor.SetSize(pcbnew.VECTOR2I_MM(.3,.3));anchor.SetShape(pcbnew.PAD_SHAPE_RECT)
    anchor.SetAttribute(pcbnew.PAD_ATTRIB_SMD);anchor.SetLayerSet(layers)
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    return b,t,z,high


def test_native_same_net_refill_that_softens_higher_priority_source_clearance_is_refused():
    b,t,z,high=high_priority_setup()
    p=owner.plan(b,[t.m_Uuid.AsString()],required_width_nm=1000000,
        clearance_nm=200000,min_thickness_nm=100000,contour_style='chamfer45',
        contour_grid_nm=1000,fill_envelope_margin_nm=4,retire_source_tracks=False,
        enclosing_native_zone_uuids=[z.m_Uuid.AsString(),high.m_Uuid.AsString()],
        landing_enclosure_mode='canonical_outline',replace_native_zone_uuid=z.m_Uuid.AsString())
    e=owner.materialize(b,p);batch=pcbnew.ZONES();batch.append(z);b.BuildConnectivity()
    assert pcbnew.ZONE_FILLER(b).Fill(batch)
    r=owner.receive(b,p,e['zone_uuid'])
    # This is real native fill, not a synthetic bad-fill injection: KiCad's
    # same-net lower-priority pour can fill the higher-priority owner's larger
    # clearance void. A whole-board minimum alone would miss the lost regional
    # constraint. The owner must reject it, not simply trust the filler.
    assert not r['ok'] and r['reason']=='higher_priority_native_landing_void_changed',r
