"""Real native cross-face dependencies; no routing permission is inferred."""
import math,pytest,pcbnew
import cec_force_current as force
import cec_native_moving_barrel_endpoints as op
from test_lastmile import _board
from test_field_proposals import track


def fixture(angle=0,mirror=False):
    def xy(p):
        x,y=p
        if mirror:x=-x
        a=math.radians(angle)
        return 10+round(x*math.cos(a)-y*math.sin(a),6),10+round(x*math.sin(a)+y*math.cos(a),6)
    name='/RENAMED/SUPPLY';b=_board([(*xy((-2,0)),name),(*xy((2,0)),name)],edge=(0,0,20,20))
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(*xy((0,0))))
    via.SetNetCode(b.GetNetcodeFromNetname(name));via.SetWidth(600000);via.SetDrill(300000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    fronts=track(b,name,xy((-2,0)),xy((0,0)))
    back=track(b,name,xy((0,0)),xy((2,0)),layer=pcbnew.B_Cu)
    return b,via,fronts,back


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_both_faces_follow_the_actual_source_barrel_not_only_the_smd_face(angle,mirror):
    b,v,front,back=fixture(angle,mirror);original=tuple(v.GetPosition())
    r=op.plan(b,[dict(uuid=force._uid(v),offset_nm=[500000,1500000])])
    assert {q['track_uuid'] for q in r['rows']}=={force._uid(front),force._uid(back)}
    assert {q['layer'] for q in r['rows']}=={pcbnew.F_Cu,pcbnew.B_Cu}
    assert all(q['offset_nm']==[500000,1500000] for q in r['rows'])
    assert tuple(v.GetPosition())==original and not r['release_authority']


@pytest.mark.parametrize('bad',['absent','duplicate','not_vector','too_far','zero','wrong_kind','invalid_hole','blank_net'])
def test_unknown_offsets_or_material_refuse(bad):
    b,v,front,back=fixture();request=[dict(uuid=force._uid(v),offset_nm=[1000000,0])]
    if bad=='absent':request[0]['uuid']='absent'
    elif bad=='duplicate':request*=2
    elif bad=='not_vector':request[0]['offset_nm']=[True,0]
    elif bad=='too_far':request[0]['offset_nm']=[17000000,0]
    elif bad=='zero':request[0]['offset_nm']=[0,0]
    elif bad=='wrong_kind':request[0]['uuid']=force._uid(front)
    elif bad=='invalid_hole':v.SetDrill(700000)
    elif bad=='blank_net':v.SetNetCode(0)
    with pytest.raises(ValueError):op.plan(b,request)


def test_touching_a_stationary_barrel_is_not_permission_to_drag_it():
    b,v,front,back=fixture();fixed=pcbnew.PCB_VIA(b)
    fixed.SetPosition(v.GetPosition());fixed.SetNetCode(v.GetNetCode());fixed.SetWidth(600000);fixed.SetDrill(300000)
    fixed.SetViaType(pcbnew.VIATYPE_THROUGH);fixed.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(fixed)
    with pytest.raises(ValueError,match='stationary_native_barrel'):
        op.plan(b,[dict(uuid=force._uid(v),offset_nm=[1000000,0])])


def test_foreign_net_on_another_face_is_not_a_source_motion_dependency():
    b,v,front,back=fixture();foreign=track(b,'/ANOTHER_NET',(10,10),(12,12),layer=pcbnew.B_Cu)
    result=op.plan(b,[dict(uuid=force._uid(v),offset_nm=[1000000,0])])
    assert force._uid(foreign) not in {q['track_uuid'] for q in result['rows']}
