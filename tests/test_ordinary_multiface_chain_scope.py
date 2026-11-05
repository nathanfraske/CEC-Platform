"""Multiface routing scope is topology and source authority, not board identity."""
import copy
import pytest
from cec_native_ordinary_chain_scope import multiface_chain


def fixture(net='control', offset=0, faces=(0,6,8)):
    rows=[]
    for i,face in enumerate(faces):
        rows.append(dict(uuid='t'+str(i),kind='PCB_TRACK',net=net,layer=face,
            width_nm=200000,locked=True,grouped=False,
            start_nm=[offset+i*1000000,offset],end_nm=[offset+(i+1)*1000000,offset]))
    vias=[dict(uuid='v'+str(i),kind='PCB_VIA',net=net,through=True,
        locked=True,grouped=False,at_nm=[offset+(i+1)*1000000,offset]) for i in range(2)]
    return rows,vias


def run(rows,vias,nets=None):
    return multiface_chain(rows,vias,[r['uuid'] for r in rows],[r['uuid'] for r in vias],
        [rows[0]['net']] if nets is None else nets,
        allow_locked_track_uuids=[r['uuid'] for r in rows if r['locked'] is True],
        allow_locked_via_uuids=[r['uuid'] for r in vias if r['locked'] is True])


@pytest.mark.parametrize('net,offset,faces',[
    ('control',0,(0,6,8)),('/other/sheet',32000000,(2,8,6)),
    ('renamed',-41000000,(8,0,2)),('third',14000000,(6,2,8))])
def test_exact_layer_crossing_chain_has_only_two_real_boundaries(net,offset,faces):
    rows,vias=fixture(net,offset,faces);before=copy.deepcopy((rows,vias))
    r=run(rows,vias)
    assert r['retired_via_uuids']==['v0','v1']
    assert sorted(q['at_nm'][0] for q in r['endpoints'])==[offset,offset+3000000]
    assert r['source_layer_ids']==sorted(faces)
    assert r['native_exclusive_barrel_and_saved_boundary_receiving_required']
    assert not r['current_or_pair_or_ground_authority'] and not r['release_authority']
    assert (rows,vias)==before


@pytest.mark.parametrize('fault',['power','pair','ground','group_track','group_via',
    'wrong_net','wrong_via_net','not_through','bool_through','bool_point','bool_face',
    'wide','bool_width','mixed_width','duplicate_track','duplicate_via','same_axis',
    'missing_axis','zero_track','disconnected','same_face_jump','branch','loop'])
def test_rejects_unowned_or_non_chain_material_without_mutation(fault):
    rows,vias=fixture();nets=None
    if fault in ('power','pair','ground'):nets=[]
    elif fault=='group_track':rows[0]['grouped']=True
    elif fault=='group_via':vias[0]['grouped']=True
    elif fault=='wrong_net':rows[-1]['net']='other'
    elif fault=='wrong_via_net':vias[0]['net']='other'
    elif fault=='not_through':vias[0]['through']=False
    elif fault=='bool_through':vias[0]['through']=1
    elif fault=='bool_point':rows[0]['start_nm'][0]=True
    elif fault=='bool_face':rows[0]['layer']=True
    elif fault=='wide':rows[0]['width_nm']=500000
    elif fault=='bool_width':rows[0]['width_nm']=True
    elif fault=='mixed_width':rows[0]['width_nm']=250000
    elif fault=='duplicate_track':rows.append(copy.deepcopy(rows[0]))
    elif fault=='duplicate_via':vias.append(copy.deepcopy(vias[0]))
    elif fault=='same_axis':vias[1]['at_nm']=vias[0]['at_nm'][:]
    elif fault=='missing_axis':vias[0]['at_nm'][0]+=1
    elif fault=='zero_track':rows[0]['end_nm']=rows[0]['start_nm'][:]
    elif fault=='disconnected':rows[0]['start_nm']=[10000000,0];rows[0]['end_nm']=[11000000,0]
    elif fault=='same_face_jump':rows[1]['layer']=rows[0]['layer']
    elif fault=='branch':
        r=copy.deepcopy(rows[1]);r['uuid']='branch';r['end_nm']=[1000000,1000000];rows.append(r)
    elif fault=='loop':rows[-1]['end_nm']=rows[0]['start_nm'][:];rows[-1]['layer']=rows[0]['layer']
    before=copy.deepcopy((rows,vias))
    with pytest.raises(ValueError):run(rows,vias,nets)
    assert (rows,vias)==before


def test_xy_coincidence_cannot_replace_an_owned_barrel_or_lock_permission():
    rows,vias=fixture()
    with pytest.raises(ValueError):multiface_chain(rows,vias,['t0','t1','t2'],['v0'],['control'])
    with pytest.raises(ValueError):multiface_chain(rows,vias,['t0','t1','t2'],['v0','v1'],['control'])


def test_unlocked_native_source_requires_no_artificial_lock_scope():
    rows,vias=fixture()
    for r in rows+vias:r['locked']=False
    assert not run(rows,vias)['locked_scope_used']
