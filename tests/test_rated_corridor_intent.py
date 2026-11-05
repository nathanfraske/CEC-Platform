"""Future demand uses actual full-load widths and cannot leak into saved copper."""
import copy
import math
from contextlib import contextmanager
from unittest import mock

import pcbnew
import pytest
import cec_rated_corridor_intent as intent
import cec_current_topology as topology
import cec_force_current as force
import cec_field_coupling as field
import cec_rated_supply_detour as detour
from cec_native_items import discard_items
from test_lastmile import _board
from test_rated_supply_detour import fixture as detour_fixture,authority as supply_authority


def data(turn=0,net='/renamed_power',layer='B.Cu'):
    def rotate(point):
        x,y=point
        for _ in range(turn):x,y=-y,x
        return [x,y]
    return (dict(schema=1,source_sha256='a'*64,net=net,layer=layer,
                 paths_nm=[[rotate(p) for p in [[0,0],[1000000,1000000],[3000000,1000000]]]]),
            dict(net=net,complete=True,amps=12.,source_refs=['input'],sink_refs=['load']),
            dict(routing_layers=['F.Cu','B.Cu'],required_by_layer_mm={'F.Cu':3.2305912,'B.Cu':3.2305912}))


def call(request,domain,contract):
    return intent.segments(request,source_sha256='a'*64,blocked_net='/ordinary',domain=domain,contract=contract)


@pytest.mark.parametrize('turn',range(4))
def test_complete_source_floor_is_rounded_up_at_every_rotation_without_mutation(turn):
    args=data(turn);before=copy.deepcopy(args);rows=call(*args)
    assert len(rows)==2 and all(r[2]==3230592 for r in rows) and args==before


@pytest.mark.parametrize('key,value',[
    ('schema',True),('schema',2),('source_sha256','b'*64),('net','/ordinary'),
    ('layer','GND'),('paths_nm',[]),('paths_nm',[[[0,0],[0,0]]]),
    ('paths_nm',[[[0,0],[1,2]]]),('paths_nm',[[[0,0],[True,0]]]),
    ('paths_nm',[[[0,0],[math.nan,0]]]),('paths_nm',[[[0,0],[100000001,0]]]),
    ('paths_nm',[[[0,0],[2000000001,0]]]),
    ('paths_nm',[[[i*1000,0] for i in range(66)]]),('paths_nm',[[[0,0],[1000,0]]]*9)])
def test_malformed_or_unbounded_intent_refused(key,value):
    request,domain,contract=data();request[key]=value
    with pytest.raises(ValueError):call(request,domain,contract)


@pytest.mark.parametrize('key,value',[
    ('complete',False),('complete',1),('amps',True),('amps',0),('amps',math.inf),
    ('net','other-rail'),('source_refs',[]),('sink_refs',[])])
def test_incomplete_or_unknown_current_domain_is_not_future_capacity(key,value):
    request,domain,contract=data();domain[key]=value
    with pytest.raises(ValueError):call(request,domain,contract)


@pytest.mark.parametrize('floor',[None,True,0,-1,math.nan,math.inf,20.000001])
def test_unknown_actual_layer_floor_refused(floor):
    request,domain,contract=data();contract['required_by_layer_mm']['B.Cu']=floor
    with pytest.raises(ValueError):call(request,domain,contract)


@pytest.mark.parametrize('extra',['width_nm','current_share','qualified','retire'])
def test_spatial_request_cannot_supply_geometry_or_admission_authority(extra):
    request,domain,contract=data();request[extra]=100000
    with pytest.raises(ValueError):call(request,domain,contract)


@contextmanager
def authority(net,domain,contract):
    with mock.patch.object(topology,'board_current_domains',return_value={net:domain}), \
            mock.patch.object(topology,'route_width_contracts',return_value={net:contract}):
        yield


def saved(tmp_path,net='/renamed_power',layer='B.Cu'):
    b=_board([(10,10,net)],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    request,domain,contract=data(net=net,layer=layer);request['source_sha256']=force._hash(source)
    return b,source,request,domain,contract


@pytest.mark.parametrize('net',['/renamed_power','/OTHER_POWER'])
@pytest.mark.parametrize('layer',['F.Cu','B.Cu'])
def test_installer_rederives_source_width_and_removal_restores_exact_native_inventory(tmp_path,net,layer):
    b,source,request,domain,contract=saved(tmp_path,net,layer);before=field._field_snapshot_inventory(b)
    with authority(net,domain,contract):items,proofs=intent.install(b,source,[request],board_hint='synthetic',blocked_net='/ordinary')
    assert len(items)==2 and all(t.GetWidth()==3230592 and t.GetNetname()==net for t in items)
    assert proofs[0]['source_sha256']==force._hash(source) and not proofs[0]['release_authority']
    assert not proofs[0]['current_or_sharing_qualified']
    discard_items(b,items);assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['stale','extra_width','unknown_net','wrong_layer','incomplete','missing_floor','later_request','source_race'])
def test_partial_installation_is_rolled_back_on_every_refusal(tmp_path,fault):
    b,source,request,domain,contract=saved(tmp_path);net=request['net'];before=field._field_snapshot_inventory(b)
    requests=[request]
    if fault=='stale':request['source_sha256']='b'*64
    elif fault=='extra_width':request['width_nm']=100000
    elif fault=='unknown_net':
        request['net']=domain['net']='/absent';net='/absent'
    elif fault=='wrong_layer':
        request['layer']='In30.Cu';contract['routing_layers'].append('In30.Cu');contract['required_by_layer_mm']['In30.Cu']=1.
    elif fault=='incomplete':domain['complete']=False
    elif fault=='missing_floor':contract['required_by_layer_mm'].pop('B.Cu')
    elif fault=='later_request':requests.append(dict(request,width_nm=100000))
    with authority(net,domain,contract):
        context=(mock.patch.object(force,'_hash',side_effect=[request['source_sha256'],'c'*64])
                 if fault=='source_race' else mock.patch.object(force,'_hash',wraps=force._hash))
        with context,pytest.raises(ValueError):intent.install(b,source,requests,board_hint='synthetic',blocked_net='/ordinary')
    assert before==field._field_snapshot_inventory(b)


def test_actual_board_scale_plane_is_not_available_to_future_power_reservation(tmp_path):
    b,source,request,domain,contract=saved(tmp_path,layer='F.Cu')
    z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);poly=z.Outline();poly.NewOutline()
    for x,y in ((0,0),(30,0),(30,30),(0,30)):poly.Append(round(x*1e6),round(y*1e6))
    b.Add(z);before=field._field_snapshot_inventory(b)
    with authority(request['net'],domain,contract),pytest.raises(ValueError,match='enabled_nonplane'):
        intent.install(b,source,[request],board_hint='synthetic',blocked_net='/ordinary')
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('bad',[None,True,{},'',[],[{}]*5])
def test_installer_requires_bounded_nonempty_intent(tmp_path,bad):
    b,source,_,_,_=saved(tmp_path)
    with pytest.raises(ValueError):intent.install(b,source,bad,board_hint='synthetic',blocked_net='/ordinary')


@pytest.mark.parametrize('bad',[None,False,{},'', [dict()]*5])
def test_supply_preclear_cannot_silently_ignore_malformed_falsy_intent(tmp_path,bad):
    b,source,poses,_=detour_fixture(tmp_path)
    with pytest.raises(ValueError,match='bounded_source_current_intent'):
        detour.run(source,tmp_path/'prefix',poses,board_hint='synthetic',source_sha256=force._hash(source),future_current_paths=bad)
    assert not (tmp_path/'prefix').exists()


def test_full_current_reservation_is_used_during_search_but_never_saved(tmp_path,monkeypatch):
    b,source,poses,_=detour_fixture(tmp_path)
    power=pcbnew.NETINFO_ITEM(b,'/future_power');b.Add(power)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('RENAMED_FUTURE_TERMINAL')
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(power);pad.SetPosition(pcbnew.VECTOR2I_MM(24,24))
    pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8));pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
    fp.Add(pad);b.Add(fp);field._save_field_snapshot(b,source)
    request,domain,contract=data(net='/future_power',layer='F.Cu')
    request.update(source_sha256=force._hash(source),paths_nm=[[[20000000,20000000],[22000000,20000000]]])
    import cec_fr as fr
    original=fr._guarded_profiled_lastmile_legs;seen=[]
    def search(board,*args,**kwargs):
        actual=[t for t in board.GetTracks() if t.GetNetname()=='/future_power']
        assert len(actual)==1 and actual[0].GetWidth()==3230592
        seen.append(force._uid(actual[0]));return original(board,*args,**kwargs)
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',search)
    with supply_authority('/CONTROL'),authority('/future_power',domain,contract):
        # The supply authority needs only its independent scalar load; the
        # future domain remains a foreign obstacle, not construction scope.
        result=detour.run(source,tmp_path/'prefix',poses,board_hint='synthetic',source_sha256=force._hash(source),future_current_paths=[request])
    assert result['ok'],result.get('errors',result.get('receiving',{}).get('errors'))
    assert seen and result['future_full_current_reservations']
    child=pcbnew.LoadBoard(result['board'])
    assert not any(force._uid(t) in seen or t.GetNetname()=='/future_power' for t in child.GetTracks())
    assert result['receiving']['exact_retirement_and_additive_replay']['ok']
    assert not result['routing_admitted'] and not result['release_authority']
