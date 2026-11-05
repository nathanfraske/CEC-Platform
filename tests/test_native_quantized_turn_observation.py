"""Exact native-grid observations do not hide real hard90s or raw diagonals."""
from copy import deepcopy
import pcbnew,pytest
import cec_native_quantized_turn_observation as observe

def transform(points,quarter=0,back=False):
    result=[]
    for x,y in points:
        if back:x=-x
        for _ in range(quarter):x,y=-y,x
        result.append([x+12345678,y-87654321])
    return result

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_one_shared_exact_rational_grid_witness_rotates_and_reflects(quarter,back):
    points=transform([[0,-375000],[0,0],[7842,7841]],quarter,back)
    witness=observe.certificate(points)
    assert observe.verify(points,witness)
    assert witness['native_coordinate_unit_nm']==1

@pytest.mark.parametrize('fault',['count','nonint','bool','duplicate','short','raw_angle','hard90','backtrack','already_exact'])
def test_noncanonical_or_malformed_turns_do_not_acquire_a_rounding_disposition(fault):
    points=[[0,-375000],[0,0],[7842,7841]]
    if fault=='count':points.append([9000,9000])
    elif fault=='nonint':points[1][0]=0.
    elif fault=='bool':points[1][0]=False
    elif fault=='duplicate':points[2]=points[1][:]
    elif fault=='short':points[2]=[2,1]
    elif fault=='raw_angle':points[2]=[7842,7800]
    elif fault=='hard90':points[2]=[375000,0]
    elif fault=='backtrack':points[2]=[1,-375000]
    elif fault=='already_exact':points[2]=[7842,7842]
    with pytest.raises(ValueError):observe.certificate(points)

@pytest.mark.parametrize('fault',['schema','unit','heading','hard90','point','denominator','outside_cell','extra_key'])
def test_certificate_checker_rejects_saved_witness_mutations(fault):
    points=[[0,-375000],[0,0],[7842,7841]];w=deepcopy(observe.certificate(points))
    if fault=='schema':w['schema']=True
    elif fault=='unit':w['native_coordinate_unit_nm']=1000
    elif fault=='heading':w['headings'][0]=[2,0]
    elif fault=='hard90':w['headings'][1]=[1,0]
    elif fault=='point':w['ideal_points_twice_nm_rational'][1][0][0]+=1
    elif fault=='denominator':w['ideal_points_twice_nm_rational'][0][0][1]=0
    elif fault=='outside_cell':w['ideal_points_twice_nm_rational'][1][0]=[100,1]
    else:w['angle_waiver']=True
    assert not observe.verify(points,w)

def native(quarter=0,back=False):
    b=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(b,'opaque-net');b.Add(net)
    points=transform([[0,-375000],[0,0],[7842,7841]],quarter,back);tracks=[]
    for a,z in zip(points,points[1:]):
        t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetWidth(200000);t.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu)
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));b.Add(t);tracks.append(t)
    return b,tracks,points

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_observation_retains_every_source_primitive_and_all_qualification_limits(quarter,back):
    b,tracks,points=native(quarter,back)
    frozen=[(list(t.GetStart()),list(t.GetEnd()),t.GetWidth(),t.GetLayer()) for t in tracks]
    r=observe.observe(b,[t.m_Uuid.AsString() for t in tracks],points[1])
    assert r['ok'] and r['complete'] and r['local_native_grid_45_turn_proved']
    assert not r['native_copper_polygon_equality_proved'] and not r['global_literal_octilinear_route_proved']
    assert not r['electrical_current_pair_or_fabrication_qualified'] and not r['acceptance_threshold_changed']
    assert not r['mutation_or_necessity_authority'] and not r['release_authority']
    assert frozen==[(list(t.GetStart()),list(t.GetEnd()),t.GetWidth(),t.GetLayer()) for t in tracks]

@pytest.mark.parametrize('fault',['missing','duplicate','point','layer','width','net','branch','arc','point_type'])
def test_native_scope_and_material_cannot_be_forged(fault):
    b,tracks,points=native();ids=[t.m_Uuid.AsString() for t in tracks];at=points[1][:]
    if fault=='missing':ids[0]='absent'
    elif fault=='duplicate':ids[1]=ids[0]
    elif fault=='point':at[0]+=1
    elif fault=='layer':tracks[0].SetLayer(pcbnew.B_Cu)
    elif fault=='width':tracks[0].SetWidth(200001)
    elif fault=='net':tracks[0].SetNetCode(0)
    elif fault=='branch':
        t=pcbnew.PCB_TRACK(b);t.SetNet(tracks[0].GetNet());t.SetLayer(tracks[0].GetLayer());t.SetWidth(200000)
        t.SetStart(pcbnew.VECTOR2I(*at));t.SetEnd(pcbnew.VECTOR2I(at[0]+100000,at[1]));b.Add(t)
    elif fault=='arc':
        t=pcbnew.PCB_ARC(b);b.Add(t);ids[0]=t.m_Uuid.AsString()
    else:at[0]=False
    r=observe.observe(b,ids,at)
    assert not r['ok'] and r['errors'] and not r['release_authority']
