"""Generated input-pad corners are optional; actual source copper is not."""
import copy
import pcbnew
import pytest
import cec_measurement_launch_pruning as subject
import cec_field_coupling as field
import cec_force_current as force
from test_measurement_terminal_route import fixture


def example(back=False,quarter=0):
    b,demand,root,target=fixture()
    root.SetSize(pcbnew.VECTOR2I_MM(1.45,.3))
    points=[(10,10),(10.15,10),(10.15,10.121),(15,10.121),(15,10),(20,10)]
    vectors=[pcbnew.VECTOR2I_MM(*p) for p in points]
    if back:
        for f in b.GetFootprints():f.Flip(pcbnew.VECTOR2I_MM(30,30),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        vectors=[pcbnew.VECTOR2I(60000000-v.x,v.y) for v in vectors]
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for f in b.GetFootprints():f.Rotate(pcbnew.VECTOR2I_MM(30,30),angle)
        # Native VECTOR2I rotation helper via unattached tracks avoids a
        # duplicate Python angle convention in the fixture.
        moved=[]
        for v in vectors:
            t=pcbnew.PCB_TRACK(b);t.SetStart(v);t.SetEnd(v)
            t.Rotate(pcbnew.VECTOR2I_MM(30,30),angle)
            moved.append(pcbnew.VECTOR2I(*tuple(t.GetStart())))
        vectors=moved
    face=int(next(iter(root.GetLayerSet().CuStack())))
    ops=[['trk',list(a),list(z),200000,face] for a,z in zip(vectors,vectors[1:])]
    return b,root,ops


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_only_new_buried_centreline_prefix_is_pruned(back,quarter):
    b,root,ops=example(back,quarter);original=copy.deepcopy(ops)
    before=field._field_snapshot_inventory(b)
    result=subject.prune(b,force._uid(root),ops)
    assert result==ops[2:] and ops==original
    assert root.GetEffectiveShape(result[0][4]).Collide(pcbnew.VECTOR2I(*result[0][1]),0)
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['unknown_pad','wrong_role','dnp','hole','not_rooted',
    'disjoint','other_face','width_change','outside_prefix','barrel','too_many'])
def test_no_new_terminal_or_current_or_retirement_authority(fault):
    b,root,ops=example();uid=force._uid(root)
    if fault=='unknown_pad':uid='not-a-source-pad'
    elif fault=='wrong_role':root.SetNumber('6')
    elif fault=='dnp':root.GetParentFootprint().SetDNP(True)
    elif fault=='hole':root.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='not_rooted':ops[0][1][0]+=1
    elif fault=='disjoint':ops[1][1][0]+=1
    elif fault=='other_face':ops[0][4]=int(pcbnew.B_Cu)
    elif fault=='width_change':ops[0][3]+=1
    elif fault=='outside_prefix':ops[0][2]=[12000000,10000000];ops[1][1]=ops[0][2]
    elif fault=='barrel':ops.insert(0,['via',ops[0][1],.3,.5])
    else:ops*=8
    before=copy.deepcopy(ops)
    assert subject.prune(b,uid,ops)==before and ops==before


@pytest.mark.parametrize('seconds',[0,-1,True,float('nan'),11])
def test_bounded_work_required(seconds):
    b,root,ops=example()
    with pytest.raises(ValueError):subject.prune(b,force._uid(root),ops,timeout_s=seconds)
