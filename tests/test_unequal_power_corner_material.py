"""A power role and both actual saved caps, not a class/name or bounding box."""
from pathlib import Path
import pcbnew,pytest
import cec_force_current as force
import cec_cell_row_rebuild as binding
import cec_unequal_power_corner_material as material


def fixture(monkeypatch,turn=0,back=False):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    for n in ('opaque_power','other'):b.Add(pcbnew.NETINFO_ITEM(b,n))
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    def pt(x,y):
        for _ in range(turn):x,y=-y,x
        return pcbnew.VECTOR2I(x+5000000,y+5000000)
    tracks=[]
    for a,z,w in [((0,3000000),(0,0),2000000),((0,0),(3000000,0),800000)]:
        t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet('opaque_power'));t.SetLayer(face);t.SetWidth(w)
        t.SetStart(pt(*a));t.SetEnd(pt(*z));b.Add(t);tracks.append(t)
    zone=pcbnew.ZONE(b);zone.SetNet(b.FindNet('opaque_power'));zone.SetLayer(face);zone.Outline().NewOutline()
    for p in [(-1200000,-1200000),(1200000,-1200000),(1200000,1200000),(-1200000,1200000)]:
        at=pt(*p);zone.Outline().Append(at.x,at.y)
    zone.SetFilledPolysList(face,zone.Outline());zone.SetIsFilled(True);b.Add(zone)
    monkeypatch.setattr(material.current,'_model',lambda board,source,net,hint:
        ('synthetic_role',None,dict(net=net,current_authority=dict(source='synthetic_not_hardware_rating'))))
    return b,tracks,zone,pt


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_both_unequal_native_caps_have_literal_canonical_and_saved_fill_cover(monkeypatch,turn,back):
    b,tracks,z,pt=fixture(monkeypatch,turn,back);before=binding._source_binding(b)
    r=material.observe(b,Path('fixture'),[force._uid(t) for t in tracks],list(pt(0,0)),board_hint='synthetic')
    assert r['ok'] and r['complete'],r['errors']
    assert r['power_join_not_signal_corner'] and len(r['native_caps'])==2
    assert r['entire_unequal_power_join_inside_canonical_saved_fill'] and before==binding._source_binding(b)
    assert not any(r[k] for k in ('mutation_or_necessity_authority','current_debt_waived',
        'electrical_or_current_or_fabrication_qualified','release_authority'))


@pytest.mark.parametrize('fault',['unfilled','wrong_net','wrong_face','rule_area','saved_fill_gap',
    'bbox_only','equal_width','wrong_endpoint','different_face','masked','no_current_role'])
def test_unsupported_power_or_partial_material_remains_unknown(monkeypatch,fault):
    b,tracks,z,pt=fixture(monkeypatch)
    if fault=='unfilled':z.SetIsFilled(False)
    elif fault=='wrong_net':z.SetNet(b.FindNet('other'))
    elif fault=='wrong_face':z.SetLayer(pcbnew.B_Cu)
    elif fault=='rule_area':z.SetIsRuleArea(True)
    elif fault=='saved_fill_gap':
        p=pcbnew.SHAPE_POLY_SET();p.NewOutline()
        for a in [(4000000,4000000),(4500000,4000000),(4500000,4500000),(4000000,4500000)]:p.Append(*a)
        z.SetFilledPolysList(pcbnew.F_Cu,p)
    elif fault=='bbox_only':
        p=z.Outline();p.RemoveAllContours();p.NewOutline()
        for a in [(3800000,3800000),(6200000,3800000),(6200000,4000000),(4000000,4000000),
                  (4000000,6200000),(3800000,6200000)]:p.Append(*a)
        z.SetFilledPolysList(pcbnew.F_Cu,p)
    elif fault=='equal_width':tracks[1].SetWidth(tracks[0].GetWidth())
    elif fault=='wrong_endpoint':tracks[1].SetStart(pt(1,0))
    elif fault=='different_face':tracks[1].SetLayer(pcbnew.B_Cu)
    elif fault=='masked':tracks[0].SetHasSolderMask(True)
    elif fault=='no_current_role':
        def refuse(*args):raise ValueError('no_positive_existing_role')
        monkeypatch.setattr(material.current,'_model',refuse)
    r=material.observe(b,Path('fixture'),[force._uid(t) for t in tracks],list(pt(0,0)),board_hint='synthetic')
    assert not r['ok'] and not r['exposed_hard90_not_present_by_positive_native_material_evidence'] and r['errors']
