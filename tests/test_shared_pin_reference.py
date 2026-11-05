import copy
import math
import random

import pytest
import cec_shared_pin_reference as shared
import cec_synth_pipeline as synth


def fixture():
    def capacitor(name, hx, hy, pad, ideal):
        orientations=[]
        for angle in (0.,90.,180.,270.):
            a=math.radians(angle)
            rotate=lambda p:[round(p[0]*math.cos(a)+p[1]*math.sin(a),10),
                             round(-p[0]*math.sin(a)+p[1]*math.cos(a),10)]
            corners=[rotate((x,y)) for x in (-hx,hx) for y in (-hy,hy)]
            orientations.append(dict(angle_deg=angle,
                box=[min(p[0] for p in corners),max(p[0] for p in corners),min(p[1] for p in corners),max(p[1] for p in corners)],
                supply_offset=rotate((-pad,0)),ground_offset=rotate((pad,0))))
        return dict(id=name,ideal_loop_mm=ideal,orientations=orientations)
    return dict(owner_box=[0.,8.,-8.,8.],supply=[1.,.8],grounds=[[1.,-.8]],
                cells=[capacitor('bulk',1.3,.65,.7,3.5),capacitor('bypass',.85,.4,.45,2.95)])


def metrics(data, poses):
    result=[]
    boxes=[]
    for cell in data['cells']:
        x,y,angle=poses[cell['id']]
        o=next(v for v in cell['orientations'] if v['angle_deg']==angle)
        supply=math.dist([x+o['supply_offset'][0],y+o['supply_offset'][1]],data['supply'])
        ground=min(math.dist([x+o['ground_offset'][0],y+o['ground_offset'][1]],g) for g in data['grounds'])
        result.append(supply+ground-cell['ideal_loop_mm'])
        boxes.append([x+o['box'][0],x+o['box'][1],y+o['box'][2],y+o['box'][3]])
    return result,boxes


def clear(a,b):
    return a[1]<=b[0]+1e-8 or b[1]<=a[0]+1e-8 or a[3]<=b[2]+1e-8 or b[3]<=a[2]+1e-8


def test_continuous_bound_and_witness_not_an_isolated_seat():
    data=fixture()
    result=shared.shared_pin_reference(**data)
    assert result['ok'] and result['lower_bound_mm']>.25
    assert result['bracket_mm']<=2e-5
    values,boxes=metrics(data,result['placements'])
    assert max(values)<=result['upper_bound_mm']+1e-8
    assert max(values)>=result['lower_bound_mm']
    assert clear(*boxes) and all(clear(box,data['owner_box']) for box in boxes)
    assert shared._witness(**{k:data[k] for k in ('owner_box','supply','grounds','cells')},excess=result['lower_bound_mm'],gap=0.) is None
    assert result['interior_placements']
    _,boxes=metrics(data,result['interior_placements'])
    assert clear(*boxes) and all(clear(box,data['owner_box']) for box in boxes)


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_renaming_translation_rotation_preserve_bound(rotation):
    data=fixture(); baseline=shared.shared_pin_reference(**data)
    a=math.radians(rotation)
    def point(p):return [round(p[0]*math.cos(a)+p[1]*math.sin(a)+127.25,10),round(-p[0]*math.sin(a)+p[1]*math.cos(a)-81.125,10)]
    box=data['owner_box']; corners=[point((x,y)) for x in box[:2] for y in box[2:]]
    data['owner_box']=[min(p[0] for p in corners),max(p[0] for p in corners),min(p[1] for p in corners),max(p[1] for p in corners)]
    data['supply']=point(data['supply']);data['grounds']=[point(p) for p in data['grounds']]
    for i,c in enumerate(data['cells']):c['id']='renamed-'+str(i)
    result=shared.shared_pin_reference(**data)
    assert result['lower_bound_mm']==pytest.approx(baseline['lower_bound_mm'],abs=2e-5)
    assert max(metrics(data,result['placements'])[0])<=result['upper_bound_mm']+1e-8


def test_random_legal_samples_cannot_beat_lower_bound():
    data=fixture();result=shared.shared_pin_reference(**data);rng=random.Random(725)
    count=0
    for _ in range(3000):
        poses={c['id']:[rng.uniform(-4,-.4),rng.uniform(-4,4),rng.choice((0.,90.,180.,270.))] for c in data['cells']}
        values,boxes=metrics(data,poses)
        if clear(*boxes) and all(clear(box,data['owner_box']) for box in boxes):
            count+=1
            assert max(values)>=result['lower_bound_mm']-1e-8
    assert count>100


def test_zero_competition_and_unavailable_bound():
    data=fixture()
    for c in data['cells']:c['ideal_loop_mm']=12.
    assert shared.shared_pin_reference(**data)['lower_bound_mm']==0.
    data=fixture()
    for c in data['cells']:c['ideal_loop_mm']=.01
    assert shared.shared_pin_reference(**data,max_excess_mm=.1)['ok'] is False


@pytest.mark.parametrize('fault',['nonfinite','negative_gap','three_cells','duplicate_ids','bad_box','duplicate_angles'])
def test_invalid_or_unsupported_geometry_fails_closed(fault):
    data=fixture()
    if fault=='nonfinite':data['supply'][0]=float('nan')
    if fault=='negative_gap':data['gap_mm']=-1.
    if fault=='three_cells':data['cells'].append(copy.deepcopy(data['cells'][0]))
    if fault=='duplicate_ids':data['cells'][1]['id']=data['cells'][0]['id']
    if fault=='bad_box':data['cells'][0]['orientations'][0]['box'][1]=-20.
    if fault=='duplicate_angles':data['cells'][0]['orientations'][1]['angle_deg']=0.
    with pytest.raises(ValueError):shared.shared_pin_reference(**data)


def test_shared_reference_never_qualifies_unproven_returns_or_distant_loop():
    reference=shared.shared_pin_reference(**fixture())
    tangent={'best_loop':{'supply_mm':1.5,'loop_proxy_mm':3.}}
    proof=dict(ground_return={'status':'via-in-pad'},owner_ground_return={'status':'via-in-pad'})
    def grade(supply,access):return synth._decoupler_proximity_gate('GND',supply,1.5,tangent,access,shared_reference=reference)
    assert not grade(1.5+reference['lower_bound_mm']+.24,proof)['bad']
    assert grade(1.5+reference['lower_bound_mm']+.26,proof)['bad']
    assert grade(1.5+reference['lower_bound_mm']+.24,{})['bad']
    assert grade(8.,proof)['bad']
    assert synth._decoupler_return_gate('GND',1.,3.,tangent)['bad']


def test_native_rectangle_does_not_inflate_pen_width_or_guess_irregular_shape():
    import pcbnew
    fp=pcbnew.FOOTPRINT(None)
    shape=pcbnew.PCB_SHAPE(fp);shape.SetLayer(pcbnew.F_CrtYd);shape.SetShape(pcbnew.SHAPE_T_RECT)
    shape.SetStart(pcbnew.VECTOR2I(-1000000,-500000));shape.SetEnd(pcbnew.VECTOR2I(1000000,500000))
    shape.SetWidth(90000);fp.Add(shape)
    assert shared._authored_rectangle(fp)==[-1.,1.,-.5,.5]
    fp.SetOrientationDegrees(30)
    assert shared._authored_rectangle(fp) is None
    fp.SetOrientationDegrees(0);shape.SetShape(pcbnew.SHAPE_T_CIRCLE)
    assert shared._authored_rectangle(fp) is None


@pytest.mark.parametrize('floor',[float('nan'),float('inf'),-1.])
def test_invalid_reference_floor_cannot_pass_proximity(floor):
    reference={'ok':True,'mode':'two_cap_shared_pin_continuous_minimax','lower_bound_mm':floor}
    with pytest.raises(ValueError):
        synth._decoupler_proximity_gate('GND',1.,1.,{'best_loop':{'supply_mm':1.,'loop_proxy_mm':2.}},
            {'ground_return':{'status':'via-in-pad'},'owner_ground_return':{'status':'via-in-pad'}},shared_reference=reference)
