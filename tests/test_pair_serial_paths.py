"""Native branched copper must not be mistaken for one series via chain."""
import time

import pcbnew
import pytest

import cec_constraints as constraints
import cec_pair_serial_paths as serial
import cec_precision_route as route


def fixture(*, quarter=0, through=False, series=False, count=3):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    pair=dict(name='CAN',kind='can',p='/BUS/CAN_H',n='/BUS/CAN_L',
              width=.25,gap=.2,clearance=.2)
    for member in ('p','n'):b.Add(pcbnew.NETINFO_ITEM(b,pair[member]))
    def xy(x,y):
        for _ in range(quarter):x,y=-y,x
        return 40+x,40+y
    def track(net,a,z,face):
        t=pcbnew.PCB_TRACK(b);t.SetStart(route._v(*a));t.SetEnd(route._v(*z))
        t.SetWidth(250000);t.SetLayer(face);t.SetNet(b.FindNet(net));b.Add(t);return t
    def via(net,point):
        v=pcbnew.PCB_VIA(b);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetPosition(route._v(*point))
        v.SetWidth(500000);v.SetDrill(250000);v.SetNet(b.FindNet(net));b.Add(v);return v
    pads={member:[] for member in ('p','n')};vias={member:[] for member in ('p','n')}
    for index in range(count):
        f=pcbnew.FOOTPRINT(b);f.SetReference('X'+str(index+1));b.Add(f)
        for offset,member in enumerate(('p','n')):
            p=pcbnew.PAD(f);p.SetNumber(str(offset+1));p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            p.SetAttribute(pcbnew.PAD_ATTRIB_PTH if through else pcbnew.PAD_ATTRIB_SMD)
            layers=pcbnew.LSET.AllCuMask() if through else pcbnew.LSET()
            if not through:layers.AddLayer(pcbnew.F_Cu)
            p.SetLayerSet(layers)
            p.SetPosition(route._v(*xy(offset,10*index)))
            p.SetSize(route._v(.6,.6));p.SetNet(b.FindNet(pair[member]))
            if through:p.SetDrillSize(route._v(.3,.3))
            f.Add(p);pads[member].append(p)
            if not through and not series:
                vias[member].append(via(pair[member],xy(offset,10*index+2)))
                track(pair[member],xy(offset,10*index),xy(offset,10*index+2),pcbnew.F_Cu)
    for offset,member in enumerate(('p','n')):
        if series:
            assert count==3 and not through
            # Three real series barrels between terminal 1 and terminals 2/3.
            for y in (2,5,8):vias[member].append(via(pair[member],xy(offset,y)))
            track(pair[member],xy(offset,0),xy(offset,2),pcbnew.F_Cu)
            track(pair[member],xy(offset,2),xy(offset,5),pcbnew.B_Cu)
            track(pair[member],xy(offset,5),xy(offset,8),pcbnew.In2_Cu)
            track(pair[member],xy(offset,8),xy(offset,20),pcbnew.F_Cu)
        else:
            shift=0 if through else 2
            track(pair[member],xy(offset,shift),xy(offset,10*(count-1)+shift),pcbnew.B_Cu)
    return b,pair,pads,vias,xy,track,via


def analyze(b,pair,vias):
    return serial.analyze(b,pair,p_route_vias=vias['p'],n_route_vias=vias['n'])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('count',[3,4,6])
def test_parallel_taps_keep_the_actual_two_series_barrel_limit(quarter,count):
    b,pair,pads,vias,*_=fixture(quarter=quarter,count=count)
    d=analyze(b,pair,vias)
    assert d['complete'] and d['exact_native_contact_tree']
    assert d['max_route_transition_vias_p']==d['max_route_transition_vias_n']==2
    assert len(d['paths'])==count*(count-1)//2
    assert len(vias['p'])==count and not d['limit_changed']
    assert not d['whole_net_skew_convention_changed'] and not d['release_authority']


@pytest.mark.parametrize('quarter',range(4))
def test_native_plated_pad_layer_access_does_not_invent_signal_barrels(quarter):
    b,pair,pads,vias,*_=fixture(quarter=quarter,through=True)
    d=analyze(b,pair,vias)
    assert d['complete'] and d['exact_native_contact_tree']
    assert d['max_route_transition_vias_p']==d['max_route_transition_vias_n']==0


@pytest.mark.parametrize('quarter',range(4))
def test_three_actual_series_transitions_still_fail_the_unchanged_budget(quarter):
    b,pair,pads,vias,*_=fixture(quarter=quarter,series=True)
    d=analyze(b,pair,vias)
    assert d['complete'] and d['exact_native_contact_tree']
    assert d['max_route_transition_vias_p']==d['max_route_transition_vias_n']==3
    physical=constraints.high_speed_pair_summary('',board=b)
    assert any('more than two route-transition vias per leg P=3 N=3' in x
               for x in physical['pairs'][0]['violations'])


def test_counting_correction_cannot_override_whole_net_skew():
    b,pair,pads,vias,xy,track,_=fixture(count=4)
    physical=constraints.high_speed_pair_summary('',board=b)
    assert physical['pairs'][0]['route_transition_vias_p']==4
    assert not any('more than two route-transition' in x for x in physical['pairs'][0]['violations'])
    track(pair['n'],xy(1,32),xy(1,42),pcbnew.B_Cu)
    changed=constraints.high_speed_pair_summary('',board=b)['pairs'][0]
    assert any('skew 10.00mm exceeds 4.00mm' in x for x in changed['violations'])
    assert changed['serial_transition_paths']['max_route_transition_vias_n']==2


@pytest.mark.parametrize('failure',['cycle','missing_pad','extra_pad','invalid_land','blind',
                                  'plane','arc','floating_track'])
def test_incomplete_ambiguous_or_non_trace_geometry_cannot_grant_counting_authority(failure):
    b,pair,pads,vias,xy,track,_=fixture()
    if failure=='cycle':track(pair['p'],xy(0,0),xy(0,20),pcbnew.F_Cu)
    elif failure=='missing_pad':pads['p'][0].SetNetCode(0)
    elif failure=='extra_pad':
        f=pcbnew.FOOTPRINT(b);f.SetReference('EXTRA');b.Add(f)
        p=pcbnew.PAD(f);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers)
        p.SetPosition(route._v(*xy(0,30)))
        p.SetSize(route._v(.6,.6));p.SetNet(b.FindNet(pair['p']));f.Add(p)
    elif failure=='invalid_land':vias['p'][0].SetWidth(200000)
    elif failure=='blind':vias['p'][0].SetViaType(pcbnew.VIATYPE_BLIND)
    elif failure=='plane':
        z=pcbnew.ZONE(b);z.SetNet(b.FindNet(pair['p']));z.SetLayer(pcbnew.In2_Cu);b.Add(z)
    elif failure=='arc':
        t=pcbnew.PCB_ARC(b);t.SetNet(b.FindNet(pair['p']));t.SetLayer(pcbnew.B_Cu);b.Add(t)
    elif failure=='floating_track':track(pair['p'],xy(10,10),xy(10,12),pcbnew.F_Cu)
    d=analyze(b,pair,vias)
    assert not d['exact_native_contact_tree'] and (d['errors'] or not d['applicable'])
    assert not d['release_authority']


def test_saved_native_tree_is_read_only_and_reproducible(tmp_path):
    b,pair,pads,vias,*_=fixture(count=4)
    path=tmp_path/'arbitrary-native.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    b=pcbnew.LoadBoard(str(path));before=path.read_bytes()
    v={member:[t for t in b.GetTracks() if t.GetClass()=='PCB_VIA'
               and t.GetNetname()==pair[member]] for member in ('p','n')}
    first=analyze(b,pair,v);second=analyze(b,pair,v)
    assert first==second and first['exact_native_contact_tree']
    assert path.read_bytes()==before


def test_native_default_drill_is_measured_without_claiming_factory_qualification():
    b,pair,pads,vias,*_=fixture()
    vias['p'][0].SetDrill(0)
    assert vias['p'][0].GetDrillValue()>0
    d=analyze(b,pair,vias)
    assert d['exact_native_contact_tree']
    assert not d['current_or_fabrication_qualification']


def test_two_terminal_geometry_retains_the_existing_conservative_count():
    b,pair,pads,vias,*_=fixture(count=2)
    d=analyze(b,pair,vias)
    assert not d['applicable'] and d['complete'] and not d['exact_native_contact_tree']


def test_expired_native_path_lease_cannot_be_called_complete():
    graph={('pad','a'):{('via','v'):0},('via','v'):{('pad','a'):0,('pad','b'):0,('pad','c'):0},
           ('pad','b'):{('via','v'):0},('pad','c'):{('via','v'):0}}
    with pytest.raises(ValueError,match='deadline'):
        serial.tree_paths(graph,dict(A=('pad','a'),B=('pad','b'),C=('pad','c')),{'v'},deadline=time.monotonic()-1)
