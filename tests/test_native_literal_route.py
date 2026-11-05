"""Literal path control is construction freedom, never a source-rule waiver."""
import copy,math,pytest
import cec_native_literal_route as literal


def case(angle=0,mirror=False,prefix='/renamed/'):
    def xy(point):
        x,y=point
        if mirror:x=-x
        a=math.radians(angle)
        return [round((x*math.cos(a)-y*math.sin(a))*1000000),round((x*math.sin(a)+y*math.cos(a))*1000000)]
    points=list(map(xy,[(1,1),(3,3),(6,3),(8,5)]))
    row=dict(uid='source-owned-branch',net=prefix+'SUPPLY',layer=2,width=1000000,start=list(points[0]),end=list(points[-1]))
    return row,dict(uid=row['uid'],net=row['net'],layer=2,width_nm=row['width'],points_nm=points)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('prefix',['/a/','/another/'])
def test_actual_ports_and_width_survive_explicit_native_path_selection(angle,mirror,prefix):
    row,request=case(angle,mirror,prefix);saved=copy.deepcopy((row,request));seen=[]
    def clear(s,t,w,l):seen.append((s,t,w,l));return True
    result=literal.plan(row,request,native_clear=clear)
    assert result['leg_count']==3 and len(seen)==3 and result['actual_source_ports_width_and_layer_preserved']
    assert result['new_barrels']==0 and not result['release_authority'] and (row,request)==saved


@pytest.mark.parametrize('bad',['uid','net','layer','width_nm','start','end','non45','empty','loop','backtrack','cross','extra'])
def test_explicit_geometry_cannot_change_source_authority_or_emit_bad_paths(bad):
    row,request=case()
    if bad in ('uid','net'):request[bad]+='changed'
    elif bad in ('layer','width_nm'):request[bad]+=1
    elif bad in ('start','end'):request['points_nm'][0 if bad=='start' else -1][0]+=1000
    elif bad=='non45':request['points_nm'][1][0]+=1000
    elif bad=='empty':request['points_nm']=[]
    elif bad=='loop':request['points_nm'].insert(2,request['points_nm'][0])
    elif bad=='backtrack':request['points_nm']=[[1000000,1000000],[4000000,4000000],[2000000,2000000],[8000000,2000000],[8000000,5000000]]
    elif bad=='cross':request['points_nm']=[[1000000,1000000],[6000000,6000000],[1000000,6000000],[6000000,1000000],[8000000,3000000],[8000000,5000000]]
    else:request['ignore_clearance']=True
    with pytest.raises(ValueError):literal.plan(row,request,native_clear=lambda *args:True)


@pytest.mark.parametrize('unknown',[False,None,0,1,'clear'])
def test_failed_or_unknown_native_collision_checks_never_authorize_a_leg(unknown):
    row,request=case()
    with pytest.raises(ValueError,match='native_clearance_refused'):literal.plan(row,request,native_clear=lambda *args:unknown)
