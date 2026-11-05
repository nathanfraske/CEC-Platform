"""Native constant-width contour trials cannot grant current/release waivers."""
import copy

import pcbnew
import pytest

import cec_rectilinear_copper as owner
from cec_local_copper_cell import copper_inventory


def fixture(*, angle=0, mirror=False, layer=pcbnew.F_Cu, locked=False, grouped=False):
    b = pcbnew.CreateEmptyBoard()
    b.SetCopperLayerCount(6)
    n = pcbnew.NETINFO_ITEM(b, "/ARBITRARY_POWER")
    b.Add(n)
    def p(x, y):
        if mirror:
            x = -x
        for _ in range(angle // 90):
            x, y = -y, x
        return pcbnew.VECTOR2I_MM(x+30, y+30)
    tracks = []
    for a,z in [((0,0),(8,0)), ((8,0),(8,8))]:
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(p(*a)); t.SetEnd(p(*z)); t.SetNet(n)
        t.SetLayer(layer); t.SetWidth(2_000_000); t.SetLocked(locked)
        b.Add(t); tracks.append(t)
    # Actual pads keep the native filled zone from becoming a removed island.
    for at in [(0,0),(8,8)]:
        fp = pcbnew.FOOTPRINT(b); b.Add(fp)
        pad = pcbnew.PAD(fp); fp.Add(pad)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetPosition(p(*at)); pad.SetSize(pcbnew.VECTOR2I_MM(3,3)); pad.SetNet(n)
        layers=pcbnew.LSET(); layers.AddLayer(layer); pad.SetLayerSet(layers)
    for a,z in [((0,0),(60,0)),((60,0),(60,60)),((60,60),(0,60)),((0,60),(0,0))]:
        edge=pcbnew.PCB_SHAPE(b); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*z))
        edge.SetLayer(pcbnew.Edge_Cuts); b.Add(edge)
    if grouped:
        g=pcbnew.PCB_GROUP(b); g.SetName("arbitrary-existing-owner"); b.Add(g)
        for t in tracks:
            g.AddItem(t)
    return b, tracks


def proposal(b, tracks, **kw):
    return owner.plan(b, [t.m_Uuid.AsString() for t in tracks],
        clearance_nm=200_000, min_thickness_nm=100_000,
        required_width_nm=1_500_000, **kw)


@pytest.mark.parametrize("angle", [0,90,180,270])
@pytest.mark.parametrize("mirror", [False,True])
@pytest.mark.parametrize("layer", [pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_saved_refilled_rectilinear_profile_preserves_conductors(tmp_path, angle, mirror, layer):
    b, tracks=fixture(angle=angle,mirror=mirror,layer=layer)
    initial=copper_inventory(b)
    plan=proposal(b,tracks)
    assert copper_inventory(b)==initial and not list(b.Zones())
    assert not plan["new_capacity_credited"] and not plan["release_authority"]
    assert all(a[0]==z[0] or a[1]==z[1] for a,z in zip(plan["polygon_nm"],plan["polygon_nm"][1:]+plan["polygon_nm"][:1]))
    emitted=owner.materialize(b,plan)
    b.BuildConnectivity()
    assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/"private.kicad_pcb"; pcbnew.SaveBoard(str(path),b)
    received=owner.receive(pcbnew.LoadBoard(str(path)),plan,emitted["zone_uuid"])
    assert received["ok"] and received["complete"], received
    assert not received["new_capacity_credited"] and not received["release_authority"]
    assert not received["missing_source_tracks"]
    assert received["verified_track_count"]==2


@pytest.mark.parametrize("locked,grouped", [(True,False),(False,True),(True,True)])
def test_locked_grouped_item_ownership_is_exact_not_a_name_guess(locked, grouped):
    b,tracks=fixture(locked=locked,grouped=grouped)
    before=copper_inventory(b)
    with pytest.raises(owner.Refused): proposal(b,tracks)
    assert copper_inventory(b)==before and not list(b.Zones())
    ids=[t.m_Uuid.AsString() for t in tracks]
    plan=proposal(b,tracks,allow_locked_track_uuids=ids,allow_grouped_track_uuids=ids)
    with pytest.raises(owner.Refused): owner.materialize(b,plan)
    assert copper_inventory(b)==before and not list(b.Zones())
    emitted=owner.materialize(b,plan,allow_locked_track_uuids=ids,allow_grouped_track_uuids=ids)
    if grouped:
        g=list(b.Groups())[0]
        assert {t.m_Uuid.AsString() for t in g.GetItems()}=={emitted["zone_uuid"]}


@pytest.mark.parametrize("fault", ["diagonal","contract","deadline","excluded","duplicate","zero","group_changed","mutated_plan"])
def test_unsupported_or_stale_proposals_do_not_mutate_source(fault):
    b,tracks=fixture()
    if fault=="diagonal": tracks[0].SetEnd(pcbnew.VECTOR2I_MM(38,31))
    if fault=="zero": tracks[0].SetEnd(tracks[0].GetStart())
    before=copper_inventory(b)
    with pytest.raises(owner.Refused):
        if fault=="contract":
            owner.plan(b,[t.m_Uuid.AsString() for t in tracks],clearance_nm=200_000,min_thickness_nm=100_000,required_width_nm=2_000_001)
        elif fault=="deadline": proposal(b,tracks,timeout_s=0)
        elif fault=="excluded": proposal(b,tracks,excluded_nets=[tracks[0].GetNetname()])
        elif fault=="duplicate":
            owner.plan(b,[tracks[0].m_Uuid.AsString()]*2,clearance_nm=200_000,min_thickness_nm=100_000,required_width_nm=1)
        elif fault in ("group_changed","mutated_plan"):
            plan=proposal(b,tracks)
            if fault=="group_changed":
                g=pcbnew.PCB_GROUP(b); b.Add(g); g.AddItem(tracks[0])
            else: plan["polygon_nm"][0][0]+=1
            owner.materialize(b,plan)
        else: proposal(b,tracks)
    assert copper_inventory(b)==before and not list(b.Zones())


@pytest.mark.parametrize("fault", ["unfilled","missing_zone","source_not_retired","tiny_loss","changed_contract","changed_outline"])
def test_receiving_requires_actual_native_fill_and_no_area_waiver(fault):
    b,tracks=fixture(); plan=proposal(b,tracks); rows=copy.deepcopy(plan["source_tracks"])
    emitted=owner.materialize(b,plan); z=list(b.Zones())[0]
    if fault!="unfilled":
        # Exact synthetic fill isolates receiver semantics; actual saved native
        # refill is independently exercised by the orientation matrix above.
        fill=owner._poly(plan["polygon_nm"])
        if fault=="tiny_loss":
            at=rows[0]["start_nm"]
            cut=owner._poly([(at[0],at[1]),(at[0]+1,at[1]),(at[0]+1,at[1]+1),(at[0],at[1]+1)])
            fill.BooleanSubtract(cut)
        z.SetFilledPolysList(plan["layer_id"],fill); z.SetIsFilled(True)
    if fault=="changed_contract": z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    if fault=="changed_outline": z.Outline().SetVertex(0,pcbnew.VECTOR2I(0,0))
    if fault=="source_not_retired":
        r=rows[0]; t=pcbnew.PCB_TRACK(b); t.m_Uuid.Clone(pcbnew.KIID(r["uuid"]))
        t.SetNet(b.FindNet(r["net"])); t.SetLayer(r["layer_id"]); t.SetWidth(r["width_nm"])
        t.SetStart(pcbnew.VECTOR2I(*r["start_nm"])); t.SetEnd(pcbnew.VECTOR2I(*r["end_nm"])); b.Add(t)
    uid="missing" if fault=="missing_zone" else emitted["zone_uuid"]
    received=owner.receive(b,plan,uid)
    assert not received["ok"],received
    assert not received["release_authority"] and not received["new_capacity_credited"]
    if fault=="tiny_loss":
        assert received["complete"] and received["missing_source_tracks"]


def test_receiving_deadline_is_unknown_not_clean():
    b,tracks=fixture();plan=proposal(b,tracks); emitted=owner.materialize(b,plan)
    result=owner.receive(b,plan,emitted["zone_uuid"],timeout_s=0)
    assert not result["ok"] and not result["complete"]


def test_current_witnesses_replay_full_native_fill_and_never_write_virtual_tracks():
    b,tracks=fixture(); plan=proposal(b,tracks); emitted=owner.materialize(b,plan)
    with pytest.raises(owner.Refused): owner.enclosed_track_witnesses(b,plan,emitted['zone_uuid'])
    b.BuildConnectivity(); assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    before=copper_inventory(b)
    ghosts,proof=owner.enclosed_track_witnesses(b,plan,emitted['zone_uuid'])
    assert len(ghosts)==2 and proof['ok'] and not proof['new_capacity_credited']
    assert copper_inventory(b)==before and not list(b.GetTracks())
    assert [t.GetWidth() for t in ghosts]==[2_000_000]*2
    z=list(b.Zones())[0]; z.SetIsFilled(False)
    with pytest.raises(owner.Refused): owner.enclosed_track_witnesses(b,plan,emitted['zone_uuid'])


def test_current_graph_uses_only_replayed_existing_envelopes_at_actual_required_width():
    import cec_force_current as force
    b,tracks=fixture()
    domain=dict(source_refs=[''],sink_refs=[''])
    contract=dict(required_by_layer_mm={'F.Cu':1.5})
    before=force._graph(b,'/ARBITRARY_POWER',domain,contract,{})[0]
    assert before['rated_connectivity']['connected']
    plan=proposal(b,tracks);emitted=owner.materialize(b,plan)
    b.BuildConnectivity(); assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    default=force._graph(b,'/ARBITRARY_POWER',domain,contract,{})[0]
    assert not default['rated_connectivity']['connected']
    request=dict(proposal=plan,zone_uuid=emitted['zone_uuid'],ok=True)
    snapshot=copper_inventory(b)
    witnessed=force._graph(b,'/ARBITRARY_POWER',domain,contract,{},native_enclosure_proposals=[request])[0]
    assert witnessed['rated_connectivity']==before['rated_connectivity']
    assert witnessed['trace_connectivity']==before['trace_connectivity']
    assert witnessed['native_enclosure_evidence'][0]['ok']
    assert not witnessed['native_enclosure_evidence'][0]['new_capacity_credited']
    assert witnessed['excluded_capacity'][0]['reason']=='zone_capacity_not_credited'
    assert copper_inventory(b)==snapshot and not list(b.GetTracks())
    with pytest.raises(ValueError,match='below_current_width'):
        force._graph(b,'/ARBITRARY_POWER',domain,{'required_by_layer_mm':{'F.Cu':2.1}}, {},native_enclosure_proposals=[request])
    list(b.Zones())[0].SetIsFilled(False)
    with pytest.raises(owner.Refused):
        force._graph(b,'/ARBITRARY_POWER',domain,contract,{},native_enclosure_proposals=[request])


def with_supporting_zone():
    b,tracks=fixture()
    z=pcbnew.ZONE(b); z.SetNet(b.FindNet('/ARBITRARY_POWER')); z.SetLayer(pcbnew.F_Cu)
    z.SetAssignedPriority(4); z.SetLocalClearance(200_000); z.SetMinThickness(100_000)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.Outline().NewOutline()
    for x,y in [(28,28),(34,28),(34,41),(28,41)]:z.Outline().Append(int(x*1e6),int(y*1e6))
    b.Add(z); b.BuildConnectivity(); assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    return b,tracks,z


def test_same_net_priority_clipping_is_received_from_actual_bound_native_copper(tmp_path):
    b,tracks,support=with_supporting_zone(); plan=proposal(b,tracks)
    assert [r['uuid'] for r in plan['supporting_zones']]==[support.m_Uuid.AsString()]
    prior=owner._support_row(support,pcbnew.F_Cu,__import__('time').monotonic()+2)
    old=owner._native_capsule(tracks[0]); emitted=owner.materialize(b,plan)
    replacement=next(z for z in b.Zones() if z.m_Uuid.AsString()==emitted['zone_uuid'])
    batch=pcbnew.ZONES(); batch.append(replacement); b.BuildConnectivity()
    assert pcbnew.ZONE_FILLER(b).Fill(batch)
    isolated=old.CloneDropTriangulation();isolated.BooleanSubtract(replacement.GetFilledPolysList(pcbnew.F_Cu))
    assert isolated.OutlineCount()>0  # Higher-priority original same-net fill supplies this.
    assert replacement.GetAssignedPriority()==0 and support.GetAssignedPriority()==4
    assert owner._support_row(support,pcbnew.F_Cu,__import__('time').monotonic()+2)==prior
    path=tmp_path/'bound-native-priority.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    received=owner.receive(pcbnew.LoadBoard(str(path)),plan,emitted['zone_uuid'])
    assert received['complete'] and received['ok'],received
    assert received['supporting_zone_uuids']==[support.m_Uuid.AsString()]
    assert not received['new_capacity_credited'] and not received['release_authority']


@pytest.mark.parametrize('fault',['hole','missing','net','layer','priority','unfilled'])
def test_supporting_native_copper_cannot_be_inferred_from_outline_or_cached_receipt(fault):
    b,tracks,support=with_supporting_zone();plan=proposal(b,tracks);emitted=owner.materialize(b,plan)
    replacement=next(z for z in b.Zones() if z.m_Uuid.AsString()==emitted['zone_uuid'])
    batch=pcbnew.ZONES();batch.append(replacement);b.BuildConnectivity()
    assert pcbnew.ZONE_FILLER(b).Fill(batch)
    assert owner.receive(b,plan,emitted['zone_uuid'])['ok']
    if fault=='hole':
        fill=support.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
        fill.BooleanSubtract(owner._poly([(30_000_000,30_000_000),(30_000_001,30_000_000),(30_000_001,30_000_001),(30_000_000,30_000_001)]))
        support.SetFilledPolysList(pcbnew.F_Cu,fill)
    elif fault=='missing':b.Remove(support)
    elif fault=='net':
        other=pcbnew.NETINFO_ITEM(b,'/OTHER_POWER');b.Add(other);support.SetNet(other)
    elif fault=='layer':support.SetLayer(pcbnew.B_Cu)
    elif fault=='priority':support.SetAssignedPriority(5)
    elif fault=='unfilled':support.SetIsFilled(False)
    received=owner.receive(b,plan,emitted['zone_uuid'])
    assert not received['ok'] and not received['complete'],received
    with pytest.raises(owner.Refused):owner.enclosed_track_witnesses(b,plan,emitted['zone_uuid'])


@pytest.mark.parametrize('key,value',[('priority',1),('clearance_nm',True),('min_thickness_nm',0),('envelope_margin_nm',100_001),('locked','true'),('pad_connection','thermal')])
def test_rehashed_invalid_plan_cannot_change_native_configuration(key,value):
    b,tracks=fixture();plan=proposal(b,tracks);before=copper_inventory(b)
    plan[key]=value;plan.pop('plan_sha256');plan['plan_sha256']=owner._digest(plan)
    with pytest.raises(owner.Refused):owner.materialize(b,plan)
    assert copper_inventory(b)==before and not list(b.Zones())


def add_foreign_corner_pad(b, *, net='/CORNER_OBSTACLE', layer=pcbnew.F_Cu):
    n=pcbnew.NETINFO_ITEM(b,net);b.Add(n)
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);p=pcbnew.PAD(fp);fp.Add(p)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetPosition(pcbnew.VECTOR2I_MM(29.1,29.1));p.SetSize(pcbnew.VECTOR2I_MM(.1,.1));p.SetNet(n)
    layers=pcbnew.LSET();layers.AddLayer(layer);p.SetLayerSet(layers)
    return p


def test_square_corner_foreign_pad_rejected_before_generation_not_hidden_by_fill():
    b,tracks=fixture();p=add_foreign_corner_pad(b)
    old=owner._native_capsule(tracks[0])
    assert not old.Collide(p.GetEffectiveShape(pcbnew.F_Cu),0)
    before=copper_inventory(b)
    with pytest.raises(owner.Refused,match='foreign_native_copper_inside_proposed_outline'):
        proposal(b,tracks)
    assert copper_inventory(b)==before and not list(b.Zones())


def test_obstacle_replayed_at_materialization_and_receiving_not_just_plan_time():
    b,tracks=fixture();plan=proposal(b,tracks);add_foreign_corner_pad(b)
    before=copper_inventory(b)
    with pytest.raises(owner.Refused,match='foreign_native_copper_inside_proposed_outline'):
        owner.materialize(b,plan)
    assert copper_inventory(b)==before and not list(b.Zones())
    b,tracks=fixture();plan=proposal(b,tracks);emitted=owner.materialize(b,plan)
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones());add_foreign_corner_pad(b)
    received=owner.receive(b,plan,emitted['zone_uuid'])
    assert not received['ok'] and not received['complete']
    assert 'foreign_native_copper_inside_proposed_outline' in received['reason']


def test_obstacles_on_other_copper_layer_do_not_require_false_layer_jumps():
    b,tracks=fixture();add_foreign_corner_pad(b,layer=pcbnew.B_Cu)
    assert proposal(b,tracks)['layer_id']==pcbnew.F_Cu
