"""Physical renamed pin-bank roadmaps are proposals, not whole-bus waivers."""
import math
import time
from unittest.mock import patch

import pcbnew
import pytest
import cec_endpoint_roadmap as roadmap
import cec_precision_route as route


def cell(quarter=0,face='F.Cu',through=False):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6)
    pair=dict(name='renamed-bus',p='arbitrary-plus',n='arbitrary-minus',
              kind='can',width=.25,gap=.25)
    for name in (pair['p'],pair['n'],'other'):
        b.Add(pcbnew.NETINFO_ITEM(b,name))
    def xy(p):
        x,y=p
        for _ in range(quarter):x,y=-y,x
        return 40+x,40+y
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('CHANGED_NAME');b.Add(fp)
    pads=[]
    for net,pos in ((pair['p'],(-5,-1)),(pair['n'],(-5,1))):
        pad=pcbnew.PAD(fp);pad.SetNumber(net)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE);pad.SetSize(pcbnew.VECTOR2I_MM(1.4,1.4))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH if through else pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET.AllCuMask() if through else pcbnew.LSET()
        if not through:layers.AddLayer(b.GetLayerID(face))
        pad.SetLayerSet(layers)
        if through:pad.SetDrillSize(pcbnew.VECTOR2I_MM(.8,.8))
        pad.SetNet(b.FindNet(net));pad.SetPosition(pcbnew.VECTOR2I_MM(*xy(pos)))
        fp.Add(pad);pads.append(pad)
    ends=tuple(xy(p) for p in ((-5,-1),(1,-.25),(-5,1),(1,.25)))
    return b,pair,ends,pads


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('face',['F.Cu','B.Cu'])
@pytest.mark.parametrize('through',[False,True])
def test_context_binds_only_two_native_pads_and_never_rates_the_complete_bus(tmp_path,quarter,face,through):
    b,pair,ends,pads=cell(quarter,face,through)
    path=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    b=pcbnew.LoadBoard(str(path))
    c=roadmap.terminal_context(b,pair,ends,layer=face)
    assert c and c['scope']=='native_terminal_fanin'
    assert c['native_pad_uuids']==[p.m_Uuid.AsString() for p in pads]
    assert c['whole_pair_qualification_required'] and not c['new_signal_vias_authorized']
    assert not c['release_authority'] and not list(b.GetTracks())
    reverse=(ends[1],ends[0],ends[3],ends[2])
    assert roadmap.terminal_context(b,pair,reverse,layer=face)


@pytest.mark.parametrize('failure',['plane','disabled','wrong_face','no_hole','npth',
    'wrong_net','ambiguous_pad','missing_owner','oversized_domain','wrong_pitch','virtual_end_on_pad'])
def test_context_cannot_infer_native_ownership_or_legalize_a_plane(failure):
    b,pair,ends,pads=cell(through=True);ends=list(ends);face='F.Cu'
    if failure=='plane':face='In1.Cu'
    elif failure=='disabled':face='In6.Cu'
    elif failure=='wrong_face':
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu)
        pads[0].SetAttribute(pcbnew.PAD_ATTRIB_SMD);pads[0].SetLayerSet(layers)
    elif failure=='no_hole':pads[0].SetDrillSize(pcbnew.VECTOR2I(0,0))
    elif failure=='npth':pads[0].SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    elif failure=='wrong_net':pads[0].SetNet(b.FindNet('other'))
    elif failure=='ambiguous_pad':
        duplicate=pcbnew.PAD(pads[0].GetParentFootprint());duplicate.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        duplicate.SetDrillSize(pcbnew.VECTOR2I_MM(.8,.8));duplicate.SetPosition(pads[0].GetPosition())
        duplicate.SetNet(b.FindNet(pair['p']));pads[0].GetParentFootprint().Add(duplicate)
    elif failure=='missing_owner':ends[0]=(ends[0][0]+.1,ends[0][1])
    elif failure=='oversized_domain':
        ends[1]=(ends[1][0]+20,ends[1][1]);ends[3]=(ends[3][0]+20,ends[3][1])
    elif failure=='wrong_pitch':ends[3]=(ends[3][0],ends[3][1]+.2)
    elif failure=='virtual_end_on_pad':
        pad=pcbnew.PAD(pads[0].GetParentFootprint());pad.SetPosition(pcbnew.VECTOR2I_MM(*ends[1]))
        pad.SetNet(b.FindNet('other'));pads[0].GetParentFootprint().Add(pad)
    assert roadmap.terminal_context(b,pair,ends,layer=face) is None


@pytest.mark.parametrize('value',[True,0,-1,13,float('inf'),float('nan')])
def test_context_search_bounds_are_explicit(value):
    b,pair,ends,_=cell()
    with pytest.raises(ValueError):roadmap.terminal_context(b,pair,ends,layer='F.Cu',max_span_mm=value)


@pytest.mark.parametrize('quarter',range(4))
def test_visibility_shortcuts_remove_squiggles_without_arbitrary_angles(quarter):
    def xy(p):
        x,y=p
        for _ in range(quarter):x,y=-y,x
        return x+40,y+40
    source=list(map(xy,[(0,0),(1,0),(1.2,.2),(1.4,.2),(1.6,.4),(2,.4),(2.4,0),(4,0)]))
    result=roadmap._visibility_shortcuts(source,lambda a,b:True)
    assert result==[source[0],source[-1]]
    assert route._polyline_is_octilinear(result)


def test_visibility_shortcuts_do_not_cross_an_exact_obstacle_or_sibling():
    source=[(0,0),(1,0),(2,1),(3,1),(4,0),(5,0)]
    clear=lambda a,b:route._seg_seg_dist(a,b,(2.5,-.25),(2.5,.4))>.2
    result=roadmap._visibility_shortcuts(source,clear)
    assert result[0]==source[0] and result[-1]==source[-1]
    assert all(clear(a,b) for a,b in zip(result,result[1:]))
    assert route._polyline_is_octilinear(result)
    assert not route._polyline_has_reverse_bend(result)


def test_terminal_local_contract_cannot_substitute_for_a_whole_pair_contract():
    b,pair,ends,_=cell();c=roadmap.terminal_context(b,pair,ends,layer='F.Cu')
    p=[ends[0],ends[1]];n=[ends[2],ends[3]]
    options=dict(p_span=math.dist(*p),n_span=math.dist(*n),width=.25,gap=.25,
        max_skew=4.,existing_signed_skew_mm=0.)
    with patch.object(route,'_pair_coupling_contract',side_effect=AssertionError('whole contract misapplied')):
        proof=roadmap._contract(p,n,c,options)
    assert proof['ok'] and c['whole_pair_qualification_required']


def test_expired_terminal_query_does_not_emit_or_search():
    b,pair,ends,_=cell();c=roadmap.terminal_context(b,pair,ends,layer='F.Cu')
    before=[t.m_Uuid.AsString() for t in b.GetTracks()]
    with patch.object(roadmap,'search',side_effect=AssertionError('expired')):
        result=route._joint_endpoint_escape(ends[0],ends[2],ends[1],ends[3],width=.25,gap=.25,
            segment_clear=lambda a,b:True,strict_pair_gap=True,complete_pair_context=c,
            deadline=time.monotonic()-1.,diagnostics={})
    assert result is None and before==[t.m_Uuid.AsString() for t in b.GetTracks()]
