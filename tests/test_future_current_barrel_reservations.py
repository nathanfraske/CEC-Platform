"""Transition lookahead is aggregate-sized, all-face, bounded and disposable."""
import copy
import pcbnew
import pytest
import cec_future_power_reservations as future
import cec_current_topology as topology
import cec_fr as fr
import cec_field_coupling as field
from cec_native_items import discard_items
from test_lastmile import _board

SHA='a'*64


def fixture(monkeypatch):
    b=_board([(10,20,'RENAMED')]);b.SetCopperLayerCount(6)
    contract=dict(current_authority=dict(amps=12.,geometry_margin=1.25,margin_included=False),
        routing_layers=['F.Cu','B.Cu'],required_by_layer_mm={'F.Cu':3.23059146,'B.Cu':3.23059146})
    domain=dict(complete=True,missing_refs=[])
    monkeypatch.setattr(topology,'board_current_domains',lambda *a:{'RENAMED':domain})
    monkeypatch.setattr(topology,'route_width_contracts',lambda *a:{'RENAMED':contract})
    monkeypatch.setattr(fr,'_edge_leg_clear',lambda *a:True)
    return b,contract,domain,dict(source_sha256=SHA,net='RENAMED',at_nm=[20000000,20000000])


@pytest.mark.parametrize('angle',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_native_transition_envelope_uses_full_load_and_all_faces(monkeypatch,angle,mirror):
    b,c,d,q=fixture(monkeypatch);x,y=1500000,3000000
    if mirror:x=-x
    for _ in range(angle):x,y=-y,x
    q['at_nm']=[20000000+x,20000000+y];snapshot=field._field_snapshot_inventory(b)
    ghosts,proof=future.construct_barrels(b,[q],source_sha256=SHA,board_hint='other',blocked_net='ordinary')
    assert len(ghosts)==1 and ghosts[0].GetWidth(pcbnew.F_Cu)==3530592
    assert ghosts[0].GetDrillValue()==300000 and ghosts[0].IsLocked()
    assert all(ghosts[0].IsOnLayer(l) for l in b.GetEnabledLayers().CuStack())
    assert proof['rows'][0]['full_source_outer_web_nm']==3230592
    assert not proof['saved_copper_authority'] and not proof['current_capacity_credited']
    with pytest.raises(ValueError,match='leaked'):future.require_removed(b,proof)
    discard_items(b,ghosts)
    assert future.require_removed(b,proof)['ok'] and field._field_snapshot_inventory(b)==snapshot


@pytest.mark.parametrize('angle',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_inner_lands_keep_full_outer_web_and_complete_drill(monkeypatch,angle,mirror):
    b,c,d,q=fixture(monkeypatch);x,y=1500000,3000000
    if mirror:x=-x
    for _ in range(angle):x,y=-y,x
    q.update(at_nm=[20000000+x,20000000+y],inner_land_diameter_nm=600000)
    snapshot=field._field_snapshot_inventory(b)
    ghosts,proof=future.construct_barrels(b,[q],source_sha256=SHA,board_hint='other',blocked_net='ordinary')
    via=ghosts[0];faces=list(b.GetEnabledLayers().CuStack())
    assert len(faces)==6 and via.GetDrillValue()==300000
    expected={b.GetLayerName(l):3530592 if l in (pcbnew.F_Cu,pcbnew.B_Cu) else 600000 for l in faces}
    assert proof['rows'][0]['actual_land_diameters_nm']==expected
    assert all(via.IsOnLayer(l) and via.GetWidth(l)==expected[b.GetLayerName(l)] for l in faces)
    assert proof['rows'][0]['full_source_outer_web_nm']==3230592
    assert proof['rows'][0]['inner_lands_grant_no_routed_current_or_barrel_capacity']
    assert not proof['current_capacity_credited'] and not proof['equal_current_sharing_assumed']
    with pytest.raises(ValueError,match='leaked'):future.require_removed(b,proof)
    discard_items(b,ghosts)
    assert future.require_removed(b,proof)['ok'] and field._field_snapshot_inventory(b)==snapshot


@pytest.mark.parametrize('inner',[None,True,600000.,0,-1,300000,300001,350000,3530592,4000000])
def test_invalid_inner_padstack_fails_before_any_batch_materialization(monkeypatch,inner):
    b,c,d,q=fixture(monkeypatch)
    other=dict(q,at_nm=[22000000,22000000],inner_land_diameter_nm=inner)
    snapshot=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):
        future.construct_barrels(b,[q,other],source_sha256=SHA,board_hint='other',blocked_net='ordinary')
    assert field._field_snapshot_inventory(b)==snapshot


@pytest.mark.parametrize('fault',['stale','same_net','missing','bad_point','extra_width','duplicate',
    'incomplete','missing_ref','unknown_floor','unpermitted','bad_authority','double_margin','oversized','edge','second_bad'])
def test_invalid_requests_fail_before_any_obstacle_is_installed(monkeypatch,fault):
    b,c,d,q=fixture(monkeypatch);qs=[q]
    if fault=='stale':q['source_sha256']='b'*64
    elif fault=='same_net':q['net']='ordinary'
    elif fault=='missing':q['net']='unknown'
    elif fault=='bad_point':q['at_nm'][0]=True
    elif fault=='extra_width':q['diameter_nm']=600000
    elif fault=='duplicate':qs=[q,copy.deepcopy(q)]
    elif fault=='incomplete':d['complete']=False
    elif fault=='missing_ref':d['missing_refs']=['absent']
    elif fault=='unknown_floor':c['required_by_layer_mm']['B.Cu']=None
    elif fault=='unpermitted':c['routing_layers']=['F.Cu']
    elif fault=='bad_authority':c['current_authority']['amps']=True
    elif fault=='double_margin':c['current_authority']['margin_included']=True
    elif fault=='oversized':c['required_by_layer_mm']['B.Cu']=8.
    elif fault=='edge':monkeypatch.setattr(fr,'_edge_leg_clear',lambda *a:False)
    elif fault=='second_bad':qs=[q,dict(q,at_nm=[True,0])]
    snapshot=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):future.construct_barrels(b,qs,source_sha256=SHA,board_hint='other',blocked_net='ordinary')
    assert field._field_snapshot_inventory(b)==snapshot
