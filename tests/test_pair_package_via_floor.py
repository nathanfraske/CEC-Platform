"""Package escape uses process AND native floors, with bounded refusal evidence.

These fixtures exercise construction and native geometric guards only. They
do not stand in for whole-pair field, return, impedance or saved-board release
receiving. Production callers keep those independent gates enabled.
"""
import pytest
import pcbnew
import cec_fab_profile as fab
import cec_fr as fr


def package_board(angle=0, *, pad_size=.8, profile='jlcpcb_6l_pofv_signal',
                  minimum_diameter=.5, minimum_drill=.3):
    b=pcbnew.CreateEmptyBoard(); b.SetCopperLayerCount(6)
    props=b.GetProperties(); props['CEC_FAB_PROFILE']=profile; b.SetProperties(props)
    settings=b.GetDesignSettings()
    settings.m_MinClearance=pcbnew.FromMM(.2)
    settings.m_ViasMinSize=pcbnew.FromMM(minimum_diameter)
    settings.m_MinThroughDrill=pcbnew.FromMM(minimum_drill)
    settings.m_ViasMinAnnularWidth=pcbnew.FromMM(.1)
    settings.m_HoleToHoleMin=pcbnew.FromMM(.254)
    for net in ('lane_one','lane_two','obstruction','GND'):
        b.Add(pcbnew.NETINFO_ITEM(b,net))
    for x,y in [((0,0),(40,0)),((40,0),(40,40)),((40,40),(0,40)),((0,40),(0,0))]:
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetStart(pcbnew.VECTOR2I_MM(*x))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*y));b.Add(edge)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('ARBITRARY_PACKAGE');b.Add(fp)
    for index,(net,x,y) in enumerate((('lane_one',15.,15.),('lane_one',17.2,15.),
                                    ('lane_two',15.,17.),('lane_two',17.2,17.))):
        pad=pcbnew.PAD(fp);pad.SetNumber(str(index+1));pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(pad_size,pad_size));pad.SetPosition(pcbnew.VECTOR2I_MM(x,y))
        pad.SetNet(b.FindNet(net));fp.Add(pad)
    obstruction=pcbnew.PCB_TRACK(b);obstruction.SetLayer(pcbnew.F_Cu)
    obstruction.SetNet(b.FindNet('obstruction'));obstruction.SetWidth(pcbnew.FromMM(.2))
    obstruction.SetStart(pcbnew.VECTOR2I_MM(16.1,16.5));obstruction.SetEnd(pcbnew.VECTOR2I_MM(16.1,17.8))
    obstruction.SetLocked(True);b.Add(obstruction)
    fp.Rotate(pcbnew.VECTOR2I_MM(20,20),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    obstruction.Rotate(pcbnew.VECTOR2I_MM(20,20),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    return b,dict(name='arbitrary_declared_pair',p='lane_one',n='lane_two',width=.2,gap=.2,clearance=.2)


def construct(b,pair):
    return fr.synthesize_same_footprint_links(b,include_nets={pair['p'],pair['n']},
        pair_declarations=[pair],field_guard=False)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('profile',['jlcpcb_6l_pofv_signal','jlcpcb_6l_pofv_high_current'])
def test_actual_pair_fallback_clamps_to_native_floors_without_relaxation(angle,profile):
    b,pair=package_board(angle,profile=profile)
    before=(b.GetDesignSettings().m_ViasMinSize,b.GetDesignSettings().m_MinThroughDrill,
            b.GetDesignSettings().m_ViasMinAnnularWidth)
    r=construct(b,pair)
    assert r['pair_linked']==2 and r['pair_refused']==0,r
    rows=[q['pofv_escape'] for q in r['detail'] if q.get('pofv_escape')]
    assert len(rows)==2
    assert all(q['selected_geometry_mm']==[.5,.3] and not q['process_or_native_floors_relaxed'] for q in rows)
    vias=[t for t in b.GetTracks() if t.GetClass()=='PCB_VIA']
    assert sum(t.GetNetname() in (pair['p'],pair['n']) for t in vias)==4
    for via in vias:
        assert via.GetDrillValue()>=before[1]
        assert all(via.GetWidth(layer)>=before[0] and
            via.GetWidth(layer)-via.GetDrillValue()>=2*before[2]
            for layer in b.GetEnabledLayers().CuStack())
    assert before==(b.GetDesignSettings().m_ViasMinSize,b.GetDesignSettings().m_MinThroughDrill,
                    b.GetDesignSettings().m_ViasMinAnnularWidth)


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_process_capability_does_not_override_too_small_native_pad(angle):
    b,pair=package_board(angle,pad_size=.32)
    before={t.m_Uuid.AsString() for t in b.GetTracks()}
    r=construct(b,pair)
    assert r['pair_refused']==2 and not r['pair_linked']
    assert {t.m_Uuid.AsString() for t in b.GetTracks()}==before
    q=next(q['pofv_escape'] for q in r['detail'] if q.get('pofv_escape'))
    assert q['selected_geometry_mm']==[.5,.3]
    assert q['native_via_refusal_counts'].get('pad or hole excludes via land',0)>0
    assert q['native_via_refusals'] and len(q['native_via_refusals'])<=16
    assert all(x['reason']=='pad or hole excludes via land' and x['blockers'] for x in q['native_via_refusals'])
    assert not q['process_or_native_floors_relaxed']


def test_native_drill_above_process_maximum_never_starts_a_via_probe():
    too_large=fab.get_profile('jlcpcb_6l_pofv_signal')['pofv_drill_max_mm']+.1
    b,pair=package_board(minimum_diameter=.9,minimum_drill=too_large)
    before={t.m_Uuid.AsString() for t in b.GetTracks()}
    r=construct(b,pair)
    assert r['pair_refused']==2 and {t.m_Uuid.AsString() for t in b.GetTracks()}==before
    q=next(q['pofv_escape'] for q in r['detail'] if q.get('pofv_escape'))
    assert not q['geometry_candidates_mm'] and q['selected_geometry_mm'] is None
    assert not q['native_via_probe_count'] and 'native board floors' in q['refused']


def test_missing_process_authority_is_a_named_refusal_not_a_floor_override():
    b,pair=package_board(profile='unknown_process')
    r=construct(b,pair)
    assert r['pair_refused']==2 and not [t for t in b.GetTracks() if t.GetClass()=='PCB_VIA']
    q=next(q['pofv_escape'] for q in r['detail'] if q.get('pofv_escape'))
    assert q['selected_geometry_mm'] is None and not q['process_or_native_floors_relaxed']


def test_lower_legal_board_floor_still_uses_exact_process_and_native_guard():
    b,pair=package_board(pad_size=.4,minimum_diameter=.3,minimum_drill=.2)
    b.GetDesignSettings().m_ViasMinAnnularWidth=pcbnew.FromMM(.05)
    r=construct(b,pair)
    assert r['pair_linked']==2,r
    q=next(q['pofv_escape'] for q in r['detail'] if q.get('pofv_escape'))
    assert q['selected_geometry_mm']==[.3,.2]
    assert fab.pofv_dimensions(fab.get_profile('jlcpcb_6l_pofv_signal'),*q['selected_geometry_mm'])[0]


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_return_seat_failure_is_structured_and_rolls_back_both_members(monkeypatch,angle):
    b,pair=package_board(angle)
    prior={t.m_Uuid.AsString() for t in b.GetTracks()}
    original=fr._via_spot_clear
    def no_return(*args,**kwargs):
        if kwargs.get('net_code')==b.FindNet('GND').GetNetCode():
            return False
        return original(*args,**kwargs)
    monkeypatch.setattr(fr,'_via_spot_clear',no_return)
    r=construct(b,pair)
    assert r['pair_refused']==2 and not r['pair_linked']
    assert prior=={t.m_Uuid.AsString() for t in b.GetTracks()}
    q=next(q['pofv_escape'] for q in r['detail'] if q.get('pofv_escape'))
    assert q['native_via_probe_count']>0 and not q['native_via_refusal_counts']
    assert q['construction_refusal_counts']['no bounded native ground-return via seat']>0
    assert any(x['reason']=='no bounded native ground-return via seat' and x['center_nm']
        for x in q['construction_refusals'])
