"""Generic native same-layer field pruning; final receiving stays mandatory."""
import math
import pcbnew
import pytest
import cec_field_coupling as field
import cec_field_search as search
import cec_fr as fr


def fixture(*, turn=0, offset=(0, 0), back=False, mirror=False, victim='renamed-SENSE-input'):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6)
    def point(x,y):
        if mirror:x=-x
        for _ in range(turn):x,y=-y,x
        return pcbnew.VECTOR2I_MM(x+offset[0],y+offset[1])
    nets={}
    for net in ('renamed-PWM-control',victim):
        nets[net]=pcbnew.NETINFO_ITEM(b,net);b.Add(nets[net])
    layer=pcbnew.B_Cu if back else pcbnew.F_Cu
    t=pcbnew.PCB_TRACK(b);t.SetStart(point(10,10.8));t.SetEnd(point(14,10.8))
    t.SetWidth(pcbnew.FromMM(.2));t.SetNet(nets[victim]);t.SetLayer(layer);b.Add(t)
    return b,point,nets,layer,t


@pytest.mark.parametrize('turn',[0,1,2,3])
@pytest.mark.parametrize('back,mirror',[(False,False),(True,False),(False,True)])
@pytest.mark.parametrize('offset',[(0,0),(37,-19)])
def test_pruning_matches_native_same_layer_authority_without_mutation(turn,back,mirror,offset):
    b,point,nets,layer,t=fixture(turn=turn,back=back,mirror=mirror,offset=offset)
    before=(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth(),str(t.m_Uuid.AsString()))
    guard=search.PlanarSearchGuard(b,'renamed-PWM-control')
    for a,z,blocked in [((10,10),(14,10),True),((10,8),(14,8),False),
                        ((10,10),(10,14),False),((10,10),(10.8,10),False)]:
        start,end=point(*a),point(*z)
        assert guard(start,end,200000,layer) is not blocked
        item=pcbnew.PCB_TRACK(b);item.SetNet(nets['renamed-PWM-control'])
        item.SetStart(start);item.SetEnd(end);item.SetLayer(layer);item.SetWidth(200000);b.Add(item)
        summary=field.field_coupling_summary('',board=b)
        assert summary['ok'] is not blocked
        b.Remove(item)
    assert before==(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth(),str(t.m_Uuid.AsString()))
    assert len(list(b.GetTracks()))==1
    report=guard.report()
    assert report['conclusive_same_layer_refusals']==1 and report['retained_relation_segments']==1
    assert not report['shielding_qualified'] and not report['release_authority'] and not report['no_path_proof']


def test_other_layers_and_point_barrels_are_not_claimed_field_passes():
    b,point,_nets,layer,_t=fixture()
    guard=search.PlanarSearchGuard(b,'renamed-PWM-control')
    assert guard(point(10,10),point(14,10),200000,pcbnew.In2_Cu)
    assert guard(point(10,10),point(10,10),200000,layer)
    assert not guard.report()['shielding_qualified']


@pytest.mark.parametrize('turn', [0,1,2,3])
def test_declared_adjacent_layers_prune_bad_crossings_without_assuming_a_plane(turn):
    b,point,nets,_layer,victim=fixture(turn=turn, offset=(17,-4))
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    victim.SetLayer(pcbnew.In3_Cu)
    guard=search.PlanarSearchGuard(b,'renamed-PWM-control')
    for first,last,blocked in [((10,10.8),(14,10.8),True),
                              ((10,10),(14,12),True),
                              ((12,9),(12,13),False),
                              ((10,6),(14,6),False)]:
        start,end=point(*first),point(*last)
        assert guard(start,end,200000,pcbnew.In2_Cu) is not blocked
        track=pcbnew.PCB_TRACK(b);track.SetNet(nets['renamed-PWM-control'])
        track.SetStart(start);track.SetEnd(end);track.SetWidth(200000);track.SetLayer(pcbnew.In2_Cu);b.Add(track)
        assert field.field_coupling_summary('',board=b)['ok'] is not blocked
        b.Delete(track)
    report=guard.report()
    assert report['conclusive_unreferenced_layer_refusals']==2
    assert not report['shielding_qualified'] and not report['release_authority']


def test_declared_ground_role_is_not_borrowed_as_actual_filled_ground_proof():
    b,point,nets,_layer,victim=fixture()
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    victim.SetLayer(pcbnew.In2_Cu)
    guard=search.PlanarSearchGuard(b,'renamed-PWM-control')
    start,end=point(10,10.8),point(14,10.8)
    # In4 is a declared GND role between In2 and B, but this synthetic
    # board deliberately has no GND copper. Fast search cannot refuse based
    # on absent shielding proof OR call that role a completed shielding pass.
    assert guard(start,end,200000,pcbnew.B_Cu)
    track=pcbnew.PCB_TRACK(b);track.SetNet(nets['renamed-PWM-control'])
    track.SetStart(start);track.SetEnd(end);track.SetWidth(200000);track.SetLayer(pcbnew.B_Cu);b.Add(track)
    assert field.field_coupling_summary('',board=b)['ok'] is False
    assert not guard.report()['shielding_qualified']


@pytest.mark.parametrize('turn',[0,1,2,3])
@pytest.mark.parametrize('back,mirror',[(False,False),(True,False),(False,True)])
def test_conservative_cross_layer_fallback_is_only_an_opt_in_proposal_exclusion(turn,back,mirror):
    b,point,nets,victim_layer,victim=fixture(turn=turn,offset=(29,-11),back=back,mirror=mirror)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    own_layer=pcbnew.F_Cu if back else pcbnew.B_Cu
    original=(tuple(victim.GetStart()),tuple(victim.GetEnd()),victim.GetWidth(),victim.GetLayer(),len(list(b.GetTracks())))
    default=search.PlanarSearchGuard(b,'renamed-PWM-control')
    guarded=search.PlanarSearchGuard(b,'renamed-PWM-control',conservative_cross_layer_proposals=True)
    assert default(point(10,10.8),point(14,10.8),200000,own_layer)
    for start,end,allowed in [((10,10.8),(14,10.8),False),((10,10),(14,12),False),
                              ((12,9),(12,13),True),((10,7),(14,7),True)]:
        assert guarded(point(*start),point(*end),200000,own_layer) is allowed
    evidence=guarded.report()
    assert evidence['conservative_cross_layer_proposal_refusals']==2
    assert evidence['conclusive_unreferenced_layer_refusals']==0
    assert not evidence['shielding_qualified'] and not evidence['no_path_proof'] and not evidence['release_authority']
    assert original==(tuple(victim.GetStart()),tuple(victim.GetEnd()),victim.GetWidth(),victim.GetLayer(),len(list(b.GetTracks())))
    assert default.report()['conservative_cross_layer_proposal_refusals']==0


@pytest.mark.parametrize('invalid',[None,0,1,'yes',[],{}])
def test_conservative_cross_layer_proposal_mode_requires_literal_boolean(invalid):
    b,*_=fixture()
    with pytest.raises(ValueError,match='explicit_conservative_cross_layer_proposal_policy_required'):
        search.PlanarSearchGuard(b,'renamed-PWM-control',conservative_cross_layer_proposals=invalid)


def test_dc_and_same_net_or_pair_mates_do_not_create_spurious_field_obstacles():
    for own in ('renamed-SENSE-input','+5V','/USB_D_P'):
        b,point,_nets,layer,_t=fixture(victim='/USB_D_N' if own=='/USB_D_P' else 'renamed-SENSE-input')
        guard=search.PlanarSearchGuard(b,own)
        assert guard(point(10,10),point(14,10),200000,layer)
        assert guard.report()['retained_relation_segments']==0


def test_snapshot_and_invalid_leg_budgets_fail_closed():
    b,point,_nets,layer,t=fixture()
    peer=pcbnew.PCB_TRACK(b);peer.SetStart(point(10,12));peer.SetEnd(point(14,12))
    peer.SetNet(t.GetNet());peer.SetWidth(200000);peer.SetLayer(layer);b.Add(peer)
    with pytest.raises(ValueError,match='snapshot_budget'):
        search.PlanarSearchGuard(b,'renamed-PWM-control',max_segments=1)
    guard=search.PlanarSearchGuard(b,'renamed-PWM-control')
    for width in (0,-1,True,float('nan')):
        with pytest.raises(ValueError,match='invalid_field_search_leg'):
            guard(point(10,10),point(14,10),width,layer)


def test_netclass_intent_not_board_or_reference_name_selects_relations():
    b,point,nets,layer,t=fixture(victim='anonymous-victim')
    resolve=lambda name: 'analog' if name=='anonymous-victim' else 'clock'
    guard=search.PlanarSearchGuard(b,'anonymous-control',netclass_resolver=resolve)
    assert not guard(point(10,10),point(14,10),200000,layer)


def test_structured_default_dimensions_never_create_field_relations():
    b,point,_nets,layer,_t=fixture(victim='anonymous-victim')
    resolve=lambda name: dict(name='Default', diff_pair_width=.2,
        diff_pair_gap=.25, diff_pair_via_gap=.25,
        provenance='/USB/ADC/CLOCK/old-board', dimension_contract={'role':'branch'})
    guard=search.PlanarSearchGuard(b,'anonymous-control',netclass_resolver=resolve)
    assert guard(point(10,10),point(14,10),200000,layer)
    assert guard.report()['retained_relation_segments']==0
    actual=lambda name: dict(resolve(name), name=(
        'Analog' if name=='anonymous-victim' else 'Clock'))
    protected=search.PlanarSearchGuard(b,'anonymous-control',netclass_resolver=actual)
    assert not protected(point(10,10),point(14,10),200000,layer)
    assert protected.report()['retained_relation_segments']==1


def test_production_path_search_uses_prediction_but_keeps_final_field_receiver(monkeypatch):
    from test_lastmile import _board
    b=_board([(10,10,'/PWM'),(14,10,'/PWM')],edge=(5,5,20,20))
    peer=pcbnew.NETINFO_ITEM(b,'/SENSE');b.Add(peer)
    t=pcbnew.PCB_TRACK(b);t.SetNet(peer);t.SetStart(pcbnew.VECTOR2I_MM(10,10.8))
    t.SetEnd(pcbnew.VECTOR2I_MM(14,10.8));t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);b.Add(t)
    prior=str(t.m_Uuid.AsString());checked=[]
    receiver=field.assess_proposed_route
    def observed(*args,**kwargs):
        result=receiver(*args,**kwargs);checked.append(result);return result
    monkeypatch.setattr(field,'assess_proposed_route',observed)
    result=fr.synthesize_lastmile(b,max_mm=10,min_w=.2,clearance=.2,
        include_nets=['/PWM'],maze_max_mm=10,maze_margin_mm=3,attempts_per_pair=3,
        field_guard=True,wall_timeout_s=3)
    assert result['field_search_preflight'][0]['conclusive_same_layer_refusals']>0
    assert result['closed']==1, result
    assert checked and any(r['ok'] is True and r['complete'] is True for r in checked)
    assert field.field_coupling_summary('',board=b)['ok']
    assert any(str(track.m_Uuid.AsString())==prior for track in b.GetTracks())
    assert not result['bridge_search_diagnostics'] or all(not row['detail']['no_path_proof']
                                                        for row in result['bridge_search_diagnostics'])


@pytest.mark.parametrize('turn', [0, 1, 2, 3])
@pytest.mark.parametrize('mirror', [False, True])
def test_spatial_broad_phase_and_memo_match_unindexed_exact_predicate(turn, mirror):
    import random
    class FullScan(search.PlanarSearchGuard):
        def _nearby(self, rows, start, end, width_mm):
            self.spatial_candidates += len(rows)
            return rows
    b, point, nets, layer, _ = fixture(turn=turn, mirror=mirror, offset=(37, -19))
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    rng=random.Random(271828)
    for i in range(40):
        x, y=rng.uniform(-30, 40), rng.uniform(-30, 40)
        t=pcbnew.PCB_TRACK(b);t.SetNet(nets['renamed-SENSE-input'])
        t.SetStart(point(x,y));t.SetEnd(point(x+rng.uniform(1,15),y))
        t.SetWidth(pcbnew.FromMM(rng.choice([.1,.2,.6,2.,8.])))
        t.SetLayer(layer if i % 2 else pcbnew.In3_Cu);b.Add(t)
    indexed=search.PlanarSearchGuard(b,'renamed-PWM-control')
    reference=FullScan(b,'renamed-PWM-control')
    for i in range(180):
        x,y=rng.uniform(-40,50),rng.uniform(-40,50)
        dx,dy=rng.choice([(8,0),(0,8),(6,6),(-6,6)])
        a,z=point(x,y),point(x+dx,y+dy)
        width=pcbnew.FromMM(rng.choice([.1,.2,.6,2.,8.]))
        copper=rng.choice([layer,pcbnew.In2_Cu,pcbnew.In3_Cu])
        expected=reference(a,z,width,copper)
        assert indexed(a,z,width,copper) is expected
        # Actual integer geometry and width/layer, not a rounded location,
        # bind the memo. Repeat answers must not run another narrow phase.
        before=indexed.spatial_candidates
        assert indexed(a,z,width,copper) is expected
        assert indexed.spatial_candidates==before
    assert indexed.memo_hits>=180
    assert indexed.spatial_candidates < reference.spatial_candidates
    assert indexed._spatial


def test_field_memo_is_bounded_and_does_not_survive_native_snapshot_changes():
    b,point,_nets,layer,t=fixture()
    guard=search.PlanarSearchGuard(b,'renamed-PWM-control')
    a,z=point(10,10),point(14,10)
    assert not guard(a,z,200000,layer)
    t.SetStart(point(10,20));t.SetEnd(point(14,20))
    fresh=search.PlanarSearchGuard(b,'renamed-PWM-control')
    assert fresh(a,z,200000,layer)
    # The old immutable snapshot is deliberately not retargeted in place.
    assert not guard(a,z,200000,layer)
    for i in range(16400):
        assert fresh(pcbnew.VECTOR2I(i,0),pcbnew.VECTOR2I(i+1,0),200000,layer)
    assert len(fresh._memo)==16384
    assert (tuple(a),tuple(z),200000,int(layer)) not in fresh._memo


def test_neutral_production_search_has_no_accumulated_field_state_but_is_received(monkeypatch):
    from test_lastmile import _board
    b=_board([(10,10,'/renamed-neutral'),(14,10,'/renamed-neutral')],edge=(5,5,20,20))
    seen=[];received=[]
    guarded=fr._guarded_profiled_lastmile_legs
    receiver=field.assess_proposed_route
    def observe_search(*args,**kwargs):
        seen.append(kwargs.get('planar_guard'))
        return guarded(*args,**kwargs)
    def observe_receiving(*args,**kwargs):
        result=receiver(*args,**kwargs);received.append(result);return result
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',observe_search)
    monkeypatch.setattr(field,'assess_proposed_route',observe_receiving)
    result=fr.synthesize_lastmile(b,max_mm=10,min_w=.2,clearance=.2,
        include_nets=['/renamed-neutral'],field_guard=True,wall_timeout_s=3)
    assert result['closed']==1, result
    assert seen and all(g is None for g in seen)
    assert received and all(r['complete'] and r['ok'] for r in received)
