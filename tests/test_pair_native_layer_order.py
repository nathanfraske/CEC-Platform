"""Source-native layer reach wins over a hard-coded front-copper first trial."""
import math,time
import pytest
import pcbnew
import cec_field_coupling as field
import cec_pair_native_layer_order as order
import cec_precision_route as route


def fixture(angle=0,mirror=False,barrels=True):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for n in ('arbitrary_p','arbitrary_n','GND'):b.Add(pcbnew.NETINFO_ITEM(b,n))
    pair=dict(name='unit',p='arbitrary_p',n='arbitrary_n',width=.2,gap=.2,clearance=.2)
    c=round(math.cos(math.radians(angle)));s=round(math.sin(math.radians(angle)))
    def point(x,y):
        x=(x-20)*(-1 if mirror else 1);y-=20
        return (20+c*x-s*y,20+s*x+c*y)
    ports=[point(x,y) for x,y in ((10,10),(25,25),(10,10.4),(25,25.4))]
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('renamed');b.Add(fp)
    for index,(net,xy) in enumerate(zip((pair['p'],pair['p'],pair['n'],pair['n']),ports)):
        pad=pcbnew.PAD(fp);pad.SetNumber(str(index));pad.SetNet(b.FindNet(net))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*xy));fp.Add(pad)
        if barrels:
            via=pcbnew.PCB_VIA(b);via.SetPosition(pad.GetPosition());via.SetNet(b.FindNet(net))
            via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
            via.SetWidth(pcbnew.FromMM(.6));via.SetDrill(pcbnew.FromMM(.3));b.Add(via)
        track=pcbnew.PCB_TRACK(b);track.SetStart(pad.GetPosition())
        track.SetEnd(pad.GetPosition()+pcbnew.VECTOR2I_MM(c*.2,s*.2))
        track.SetLayer(pcbnew.B_Cu);track.SetWidth(pcbnew.FromMM(.2));track.SetNet(b.FindNet(net));b.Add(track)
    return b,pair,ports


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_incident_layer_preferred_without_creating_layer_access(angle,mirror):
    b,pair,ports=fixture(angle,mirror);before=field._field_snapshot_inventory(b)
    rows=order.rank(b,pair,ports)
    assert rows[0]['layer']=='B.Cu' and rows[0]['ports_with_existing_access']==4
    assert rows[0]['ports_with_incident_tracks']==4
    assert {r['layer'] for r in rows}<={'F.Cu','B.Cu','In2.Cu'}
    assert not {'In1.Cu','In3.Cu','In4.Cu'} & {r['layer'] for r in rows}
    assert field._field_snapshot_inventory(b)==before


def test_fine_pad_without_barrels_keeps_legacy_entry_not_an_invented_inner_transition():
    b,pair,ports=fixture(barrels=False)
    # The off-surface tracks in this deliberately incomplete fixture are
    # still actual source copper, not electrical access to the F-only pad.
    # Incident track contact is native access at these exact coordinates,
    # so remove those unrelated trial strokes for the pure F-only control.
    from cec_native_items import discard_items
    discard_items(b,list(b.GetTracks()))
    rows=order.rank(b,pair,ports)
    assert len(rows)==1 and rows[0]['layer']=='F.Cu'


def test_nearby_barrel_does_not_claim_exact_port_access():
    b,pair,ports=fixture()
    from cec_native_items import discard_items
    discard_items(b,[t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK'])
    for via in b.GetTracks():via.Move(pcbnew.VECTOR2I(1,0))
    rows=order.rank(b,pair,ports)
    assert len(rows)==1 and rows[0]['layer']=='F.Cu'


@pytest.mark.parametrize('ports',[((),)*4,((float('nan'),0),)*4,((0,0),)*3,((True,0),)*4])
def test_invalid_port_context_never_mutates_source(ports):
    b,pair,_=fixture();before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):order.rank(b,pair,ports)
    assert field._field_snapshot_inventory(b)==before


def test_inline_leg_uses_native_portfolio_and_rolls_back_failed_layer_before_next(monkeypatch):
    b,pair,ports=fixture();base={t.m_Uuid.AsString() for t in b.GetTracks()};calls=[]
    monkeypatch.setattr(route,'_scheduled_flow_legs',lambda *a:[(0,ports,(0,))])
    monkeypatch.setattr(route,'_retained_inline_leg_contact',lambda *a,**kw:dict(complete=True,connected=False))
    def solve(board,pair,**kw):
        layer=kw['layer'];calls.append((layer,kw['deadline']))
        assert {t.m_Uuid.AsString() for t in board.GetTracks()}==base
        t=pcbnew.PCB_VIA(board);t.SetPosition(pcbnew.VECTOR2I_MM(30,30));t.SetNet(board.FindNet('GND'));board.Add(t)
        if layer=='B.Cu':return dict(name=pair['name'],p=pair['p'],n=pair['n'],refused='unit first-layer refusal')
        return dict(name=pair['name'],p=pair['p'],n=pair['n'],segments=0,length_mm=1.,coupled_len_mm=1.)
    monkeypatch.setattr(route,'route_coupled_pair',solve)
    deadline=time.monotonic()+12.
    r=route._route_flow_leg_orders(b,pair,[ports],[],deadline=deadline,max_orders=1)
    assert r.get('route_mode')=='flow-through' and not r.get('refused'),r
    assert calls[0][0]=='B.Cu' and len(calls)==2
    # Alternative primary layers inherit one complete-attempt deadline; a
    # quick finite refusal does not subdivide or replenish that same lease.
    assert calls[0][1]==calls[1][1]<=deadline
    assert r['flow_order_attempts'][0]['alternative_budget_policy']=='complete-attempt'
    assert r['legs'][0]['prior_layer_refusals'][0]['rollback_created_items']


def test_failed_inline_portfolio_removes_all_new_copper(monkeypatch):
    b,pair,ports=fixture();base=field._field_snapshot_inventory(b)
    monkeypatch.setattr(route,'_scheduled_flow_legs',lambda *a:[(0,ports,(0,))])
    monkeypatch.setattr(route,'_retained_inline_leg_contact',lambda *a,**kw:dict(complete=True,connected=False))
    def solve(board,pair,**kw):
        t=pcbnew.PCB_VIA(board);t.SetPosition(pcbnew.VECTOR2I_MM(30,30));t.SetNet(board.FindNet('GND'));board.Add(t)
        return dict(name=pair['name'],p=pair['p'],n=pair['n'],refused='bounded synthetic refusal')
    monkeypatch.setattr(route,'route_coupled_pair',solve)
    r=route._route_flow_leg_orders(b,pair,[ports],[],deadline=time.monotonic()+12.,max_orders=1)
    assert r.get('refused') and len(r['flow_leg_refusal']['layers'])==3
    assert field._field_snapshot_inventory(b)==base
