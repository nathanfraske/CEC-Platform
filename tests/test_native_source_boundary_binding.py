import copy
import pytest
from cec_native_ordinary_chain_scope import chain, boundary_attachment_pairs
from cec_rated_corridor_intent import segments


def source_scope(quarter=0, mirrored=False):
    def pose(point):
        x,y=point
        if mirrored:x=-x
        for _ in range(quarter):x,y=-y,x
        return [x+20_000_000,y+20_000_000]
    rows=[dict(uuid='native-edge',kind='PCB_TRACK',net='STATUS',layer=2,
        width_nm=200_000,locked=False,grouped=False,
        start_nm=pose([0,0]),end_nm=pose([0,8_000_000]))]
    return chain(rows,['native-edge'],{'STATUS'})


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirrored',[False,True])
@pytest.mark.parametrize('migration',[False,True])
def test_future_current_reservation_cannot_rebind_source_endpoints(quarter,mirrored,migration):
    scope=source_scope(quarter,mirrored)
    before=copy.deepcopy(scope)
    request=dict(schema=1,source_sha256='a'*64,net='POWER',layer='B.Cu',
        paths_nm=[[[55_000_000,10_000_000],[55_000_000,30_000_000]]])
    contract=dict(routing_layers=['B.Cu'],required_by_layer_mm={'B.Cu':3.2})
    domain=dict(net='POWER',complete=True,amps=12.,source_refs=['SOURCE'],sink_refs=['LOAD'])
    # Reproduce the actual old constructor's shadowing loop. These planning
    # variables must never become signal attachment authority afterwards.
    for left,right,width,face in segments(request,source_sha256='a'*64,
            blocked_net='STATUS',contract=contract,domain=domain):
        assert width==3_200_000 and face=='B.Cu'
    proof=None if not migration else dict(endpoints=[
        dict(at_nm=list(point),target_layers=[6,0]) for point in scope['endpoints_nm']])
    pair=boundary_attachment_pairs(scope,proof)[0]
    assert [pair[0]['at_nm'],pair[1]['at_nm']]==before['endpoints_nm']
    assert [pair[0]['at_nm'],pair[1]['at_nm']]!=[list(left),list(right)]
    assert all(p['layers']==([6,0] if migration else [2]) for p in pair)
    pair[0]['at_nm'][0]+=100
    pair[0]['layers'].append(10)
    assert scope==before
    if proof is not None:assert proof['endpoints'][0]['target_layers']==[6,0]


@pytest.mark.parametrize('defect',['coordinate','order','duplicate_face','bool_face','authority','float_axis'])
def test_stale_or_retyped_boundary_is_refused(defect):
    scope=source_scope()
    proof=dict(endpoints=[dict(at_nm=list(point),target_layers=[6])
        for point in scope['endpoints_nm']])
    if defect=='coordinate':proof['endpoints'][0]['at_nm'][0]+=1
    elif defect=='order':proof['endpoints'].reverse()
    elif defect=='duplicate_face':proof['endpoints'][0]['target_layers']=[6,6]
    elif defect=='bool_face':proof['endpoints'][0]['target_layers']=[True]
    elif defect=='authority':scope['release_authority']=True
    elif defect=='float_axis':scope['endpoints_nm'][0][0]=float(scope['endpoints_nm'][0][0])
    with pytest.raises(ValueError):boundary_attachment_pairs(scope,proof)
