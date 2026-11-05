"""Native component aliases cannot abandon unchanged source face contacts."""
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_future_pose_clearance as future
import cec_native_component_ports as ports


def fixture(kind,face,angle=0):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6);net=pcbnew.NETINFO_ITEM(b,'/renamed/control');b.Add(net)
    at=pcbnew.VECTOR2I_MM(10,10)
    def point(x,y):
        for _ in range(angle//90):x,y=-y,x
        return pcbnew.VECTOR2I(at.x+round(x*1e6),at.y+round(y*1e6))
    def track(layer,start,end):
        t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetLayer(layer);t.SetWidth(200000)
        t.SetStart(point(*start));t.SetEnd(point(*end));b.Add(t);return t
    if kind in ('tip','tip_with_peer','body','new_tip'):
        track(face,(-2,0),(2,0) if kind=='body' else (0,0))
        if kind=='tip_with_peer':track(face,(0,0),(2,0))
    elif kind in ('via','via_other_face','via_same_face'):
        via=pcbnew.PCB_VIA(b);via.SetNet(net);via.SetPosition(at);via.SetWidth(600000);via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(via)
        if kind!='via':track(face if kind=='via_same_face' else pcbnew.B_Cu if face==pcbnew.F_Cu else pcbnew.F_Cu,(0,0),(2,0))
    else:
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);p=pcbnew.PAD(fp);fp.Add(p);p.SetNet(net);p.SetPosition(at)
        p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH if kind=='pth' else pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET.AllCuMask() if kind=='pth' else pcbnew.LSET()
        if kind=='pth':p.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
        else:layers.AddLayer(face)
        p.SetLayerSet(layers)
    source={force._uid(t) for t in b.GetTracks()} if kind!='new_tip' else set()
    return b,net,at,source


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('angle',[0,90])
@pytest.mark.parametrize('kind,required',[('tip',True),('tip_with_peer',False),('body',False),
    ('new_tip',False),('via',True),('via_other_face',True),('via_same_face',False),('pth',False),('smd',False)])
def test_only_literal_unmet_surviving_native_source_face_contacts_are_pinned(face,angle,kind,required):
    b,net,at,source=fixture(kind,face,angle);before=field._field_snapshot_inventory(b)
    proof=future._source_boundary_face_obligation(b,str(net.GetNetname()),list(at),face,
        source_uuids=source,deadline=time.monotonic()+2.)
    assert proof['required'] is required and bool(proof['witnesses']) is required
    assert proof['layer']==face and proof['at_nm']==list(at)
    assert not proof['connectivity_or_current_credited'] and field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('case,expected',[('proper',True),('wrong_face',False),('near_cap',False),
    ('body',True),('zero_length',False),('via_only',False),('one_required',True),('none_required',True)])
def test_proposed_face_incidence_uses_exact_centrelines_not_cap_or_other_layer_aliases(angle,case,expected):
    def at(x,y):
        for _ in range(angle//90):x,y=-y,x
        return pcbnew.VECTOR2I(10000000+x,10000000+y)
    first,last=at(0,0),at(5000000,0);face=int(pcbnew.F_Cu);required=(True,True)
    a,b=first,last;layer=face
    if case=='wrong_face':layer=int(pcbnew.B_Cu)
    elif case=='near_cap':a=at(1,0)
    elif case=='body':a,b=at(-1000000,0),at(6000000,0)
    elif case=='zero_length':b=a
    elif case=='one_required':required=(True,False);b=at(2000000,0)
    elif case=='none_required':required=(False,False)
    ops=[('via',first,.3,.6)] if case=='via_only' else [('trk',a,b,200000,layer)]
    assert future._ops_restore_literal_source_faces(ops,(list(first),list(last)),face,required) is expected


def test_native_boundary_fallback_does_not_substitute_distant_component_ports_for_required_faces(monkeypatch):
    b,net,first,source=fixture('tip',pcbnew.F_Cu)
    last=pcbnew.VECTOR2I_MM(18,10);via=pcbnew.PCB_VIA(b);via.SetNet(net);via.SetPosition(last)
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(via)
    for a,z in [((0,0),(25,0)),((25,0),(25,25)),((25,25),(0,25)),((0,25),(0,0))]:
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(edge)
    before=field._field_snapshot_inventory(b);diagnostics={}
    def forbidden(*args,**kwargs):raise AssertionError('literal_source_face_cannot_use_component_alias_menu')
    monkeypatch.setattr(ports,'endpoints',forbidden)
    def validate(ops):return future._ops_restore_literal_source_faces(ops,(list(first),list(last)),pcbnew.F_Cu,(True,True))
    ops=future._native_boundary_access(b,str(net.GetNetname()),list(first),list(last),int(pcbnew.F_Cu),200000,
        deadline=time.monotonic()+3.,gap=200000,spec={},maze_margin_mm=4.,
        validate_ops=validate,planar_guard=None,diagnostics=diagnostics)
    assert ops and validate(ops)
    assert len(diagnostics['literal_source_face_obligations'])==2
    assert field._field_snapshot_inventory(b)==before


def test_expired_face_inventory_is_unknown_not_an_absent_obligation():
    b,net,at,source=fixture('tip',pcbnew.F_Cu)
    with pytest.raises(ValueError):future._source_boundary_face_obligation(b,str(net.GetNetname()),list(at),pcbnew.F_Cu,
        source_uuids=source,deadline=time.monotonic()-1.)
