"""Widened local roadmaps require actual authorized transition barrels."""
import math

import pcbnew
import pytest
import cec_endpoint_roadmap as roadmap
import cec_precision_route as route
from test_native_terminal_roadmap import cell


def fixture(quarter=0,face='F.Cu'):
    b,pair,ends,pads=cell(quarter,face,through=True)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    def xy(p):
        x,y=p
        for _ in range(quarter):x,y=-y,x
        return 40+x,40+y
    ends=(ends[0],xy((1,-.375)),ends[2],xy((1,.375)))
    vias=[]
    for net,xy in zip((pair['p'],pair['n']),(ends[1],ends[3])):
        v=pcbnew.PCB_VIA(b);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetPosition(route._v(*xy))
        v.SetWidth(500000);v.SetDrill(300000);v.SetNet(b.FindNet(net));b.Add(v);vias.append(v)
    return b,pair,ends,pads,vias


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('face',['F.Cu','B.Cu'])
def test_saved_native_barrels_bind_wide_throat_without_emitting_copper(tmp_path,quarter,face):
    b,pair,ends,pads,vias=fixture(quarter,face)
    path=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    b=pcbnew.LoadBoard(str(path));before=path.read_bytes()
    c=roadmap.terminal_context(b,pair,ends,layer=face)
    assert c and math.isclose(c['target_pitch_mm'],.75)
    assert c['native_pad_uuids']==[p.m_Uuid.AsString() for p in pads]
    assert c['native_transition_via_uuids']==[v.m_Uuid.AsString() for v in vias]
    assert c['whole_pair_qualification_required'] and not c['new_signal_vias_authorized']
    assert not c['release_authority'] and len(list(b.GetTracks()))==2
    assert path.read_bytes()==before
    reverse=(ends[1],ends[0],ends[3],ends[2])
    assert roadmap.terminal_context(b,pair,reverse,layer=face)


@pytest.mark.parametrize('failure',['missing','wrong_net','offset','duplicate','no_drill',
    'undersize','oversize','wrong_drill','wrong_type','disabled_face',
    'no_profile','plane','unbound_pitch','missing_terminal'])
def test_wider_virtual_split_cannot_invent_transition_authority(failure):
    b,pair,ends,pads,vias=fixture();ends=list(ends);face='F.Cu'
    v=vias[0]
    if failure=='missing':b.Remove(v)
    elif failure=='wrong_net':v.SetNet(b.FindNet('other'))
    elif failure=='offset':v.SetPosition(route._v(41,39.626))
    elif failure=='duplicate':
        q=pcbnew.PCB_VIA(b);q.SetViaType(pcbnew.VIATYPE_THROUGH)
        q.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);q.SetPosition(v.GetPosition())
        q.SetWidth(v.GetWidth());q.SetDrill(v.GetDrill());q.SetNet(v.GetNet());b.Add(q)
    elif failure=='no_drill':v.SetDrill(0)
    elif failure=='undersize':v.SetWidth(350000)
    elif failure=='oversize':v.SetWidth(800000)
    elif failure=='wrong_drill':v.SetDrill(200000)
    elif failure=='wrong_type':v.SetViaType(pcbnew.VIATYPE_BLIND)
    elif failure=='disabled_face':face='In6.Cu'
    elif failure=='no_profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='';b.SetProperties(props)
    elif failure=='plane':face='In1.Cu'
    elif failure=='unbound_pitch':
        ends[3]=(ends[3][0],ends[3][1]+.2);vias[1].SetPosition(route._v(*ends[3]))
    elif failure=='missing_terminal':ends[0]=(ends[0][0]+.1,ends[0][1])
    assert roadmap.terminal_context(b,pair,ends,layer=face) is None


def test_nominal_virtual_throat_still_needs_no_new_barrel():
    b,pair,ends,_=cell()
    c=roadmap.terminal_context(b,pair,ends,layer='F.Cu')
    assert c and c['native_transition_via_uuids']==[]
    assert not list(b.GetTracks())


def test_native_through_layer_normalization_does_not_authorize_a_disabled_face():
    b,pair,ends,_,vias=fixture()
    vias[0].SetLayerPair(pcbnew.In2_Cu,pcbnew.B_Cu)
    # KiCad canonicalizes through barrels to the two outer layers. Test the
    # actual native object, not an impossible hypothetical layer-pair state.
    assert vias[0].TopLayer()==pcbnew.F_Cu and vias[0].BottomLayer()==pcbnew.B_Cu
    assert roadmap.terminal_context(b,pair,ends,layer='F.Cu')
    assert roadmap.terminal_context(b,pair,ends,layer='In6.Cu') is None
