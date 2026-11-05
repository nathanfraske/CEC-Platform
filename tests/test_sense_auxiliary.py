"""Auxiliary completion uses part pin roles and live nets, never board recipes."""
import time
import pytest
import pcbnew
import cec_sense_auxiliary as aux
import cec_local_copper_cell as copper
import cec_pair_semantics as semantics


def fixture(value='INA238AIDGSR',*,separate=False,back=False,angle=0.,origin=(21.,34.)):
    b=pcbnew.BOARD();n=pcbnew.NETINFO_ITEM(b,'arbitrary_sheet/renamed_measurement');b.Add(n)
    pnet=pcbnew.NETINFO_ITEM(b,'other_measurement');b.Add(pnet)
    f=pcbnew.FOOTPRINT(b);f.SetReference('MONITOR_ARBITRARY');f.SetValue(value)
    for number,x,net in [('8',0.,n),('9',.5,pnet if separate else n),('10',1.,pnet)]:
        p=pcbnew.PAD(f);p.SetNumber(number);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetSize(pcbnew.VECTOR2I(200000,700000))
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetPosition(pcbnew.VECTOR2I(round(x*1e6),0))
        p.SetNet(net);f.Add(p)
    f.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in origin)))
    f.SetOrientationDegrees(angle);b.Add(f)
    if back:f.Flip(f.GetPosition(),False)
    return b,f,n


@pytest.mark.parametrize('value',['INA238','INA228AIDGSR'])
@pytest.mark.parametrize('angle,back',[(0.,False),(90.,False),(180.,True),(270.,True)])
def test_same_native_net_auxiliary_pins_complete_on_rotated_real_face(value,angle,back):
    b,f,n=fixture(value,angle=angle,back=back);old=copper.copper_inventory(b)
    r=aux.construct(b);assert r['ok'] and r['joins']==1,r
    assert not r['kelvin_isolation_qualified'] and not r['power_authority'] and not r['release_authority']
    assert {t.GetLayer() for t in b.GetTracks()}=={pcbnew.B_Cu if back else pcbnew.F_Cu}
    first=copper.copper_inventory(b);again=aux.construct(b)
    assert again['ok'] and again['joins']==0 and again['terminals'][0]['status']=='covered'
    assert first==copper.copper_inventory(b) and not old


@pytest.mark.parametrize('value',['INA238','INA228'])
def test_distinct_schematic_nets_never_get_strapped(value):
    b,_,_=fixture(value,separate=True);before=copper.copper_inventory(b)
    r=aux.construct(b);assert r['ok'] and r['joins']==0
    assert r['terminals'][0]['status']=='not_applicable'
    assert copper.copper_inventory(b)==before


@pytest.mark.parametrize('value',['unknown INA238-like','INA181','INA240','INA226'])
def test_unknown_or_unqualified_auxiliary_roles_are_not_guessed(value):
    b,_,_=fixture(value);assert aux.construct(b)['generated_item_count']==0
    assert semantics.current_auxiliary_input_contract(value) is None


def test_foreign_native_pad_blocks_strap_and_no_trials_leak():
    b,f,_=fixture();p=pcbnew.PAD(f);p.SetNumber('foreign')
    p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I(300000,300000))
    p.SetPosition(pcbnew.VECTOR2I(21250000,34000000))
    p.SetNet(b.FindNet('other_measurement'));f.Add(p)
    old=copper.copper_inventory(b);r=aux.construct(b)
    assert not r['ok'] and r['joins']==0 and r['refused'],r
    assert old==copper.copper_inventory(b)


def test_future_foreign_power_reservation_is_not_ignored():
    b,f,_=fixture();r=aux.construct(b,avoid=[dict(x0=21.2,y0=33.8,x1=21.3,y1=34.2,
        layer='F.Cu',net='foreign_reserved_net')])
    assert not r['ok'] and not r['generated_items']


def test_graph_refuses_unknown_filled_zone_and_expired_budget():
    b,f,n=fixture();z=pcbnew.ZONE(b);z.SetNet(n);z.SetLayer(pcbnew.F_Cu)
    z.Outline().NewOutline()
    for x,y in [(20,33),(22,33),(22,35),(20,35)]:z.Outline().Append(x*1000000,y*1000000)
    b.Add(z)
    r=aux.construct(b);assert not r['ok'] and not r['generated_items']
    assert 'native_contact_fill_unknown' in r['refused'][0]['reason']
    with pytest.raises(ValueError,match='deadline'):
        # No global connectivity rebuild or implicit refill can cure expiry.
        aux.native_contact_graph(pcbnew.BOARD(),'empty',deadline=time.monotonic()-1)


def test_ambiguous_physical_pin_id_is_a_refusal_not_nearest_choice():
    b,f,n=fixture();p=pcbnew.PAD(f);p.SetNumber('8');p.SetNet(n);f.Add(p)
    r=aux.construct(b);assert not r['ok'] and not r['generated_items']
    assert 'identity_ambiguous' in r['refused'][0]['reason']


def test_partial_auxiliary_prefix_is_locked_geometry_not_whole_net_exclusion():
    import cec_precision_route as precision
    b,f,n=fixture();peer=pcbnew.FOOTPRINT(b);peer.SetReference('DISTANT_SAME_NET_CONSUMER')
    p=pcbnew.PAD(peer);p.SetNumber('renamed_pin');p.SetNet(n)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
    p.SetSize(pcbnew.VECTOR2I(600000,600000));peer.Add(p)
    peer.SetPosition(pcbnew.VECTOR2I(40000000,40000000));b.Add(peer)
    r=precision.precision_route_board(b,do_pairs=False,verbose=False)
    assert r['kelvin']['auxiliary_inputs']['joins']==1
    assert n.GetNetname() not in r['locked_nets']
    assert r['partial_locked_nets']==[n.GetNetname()]
    assert r['whole_net_locked_ownership']['nets'][n.GetNetname()]['complete'] is False
    assert r['locked_item_uuids'] and all(t.IsLocked() for t in b.GetTracks())


def test_complete_auxiliary_locked_subgraph_can_own_whole_small_net():
    import cec_precision_route as precision
    b,f,n=fixture();r=precision.precision_route_board(b,do_pairs=False,verbose=False)
    assert r['kelvin']['auxiliary_inputs']['joins']==1
    assert r['locked_nets']==[n.GetNetname()] and not r['partial_locked_nets']
