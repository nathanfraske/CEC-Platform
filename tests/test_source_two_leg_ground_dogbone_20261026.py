"""Two real local SMD limbs retain every existing process/physical boundary."""
import copy
import json
import os
from pathlib import Path
from unittest import mock

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_existing_local_pofv_pad_rule as local
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_access_completion as ground
import cec_native_drc_runner as native
import root_receive_local_transaction_20261022 as transaction
from test_saved_local_ground_dogbone_completion import fixture as direct_fixture


def fixture(tmp_path,angle=0,face=pcbnew.F_Cu,mirror=False,isolated=False):
    b,source,pad,args=direct_fixture(tmp_path,angle,face)
    origin=tuple(pad.GetPosition())
    def reflect(point):return pcbnew.VECTOR2I(point.x,2*origin[1]-point.y)
    if mirror:
        for fp in b.GetFootprints():fp.Flip(pcbnew.VECTOR2I(*origin),True)
        for t in b.GetTracks():
            if t.GetClass()=='PCB_TRACK':
                a,z=reflect(t.GetStart()),reflect(t.GetEnd());t.SetStart(a);t.SetEnd(z)
                t.SetLayer(pcbnew.B_Cu if t.GetLayer()==pcbnew.F_Cu else pcbnew.F_Cu)
            else:t.SetPosition(reflect(t.GetPosition()))
    if isolated:
        for t in list(b.GetTracks()):
            if t.GetClass()=='PCB_TRACK':b.Remove(t)
    field._save_field_snapshot(b,source)
    # A mirrored native FP normalizes local pad/field angle phases on save.
    # Test the actual saved Source, not an unfinished pre-writer proxy.
    pad_uid=force._uid(pad);b=pcbnew.LoadBoard(str(source))
    pad=next(p for f in b.GetFootprints()for p in f.Pads()if force._uid(p)==pad_uid)
    points=[]
    for x,y in ((0,0),(0,-400000),(400000,-800000)):
        for _ in range(angle//90):x,y=y,-x
        if mirror:y=-y
        points.append([origin[0]+x,origin[1]+y])
    args.pop('dogbone_position_nm');args['dogbone_points_nm']=points
    return b,source,pad,args


def context(pad,points):
    return dict(pad=pad,points=[pcbnew.VECTOR2I(*p)for p in points],
        layer=int(next(iter(pad.GetLayerSet().CuStack()))))


def seat(b,pad,points,**kw):
    return fr._via_spot_clear(b,pcbnew.VECTOR2I(*points[-1]),300000,200000,{pad.GetNetCode()},
        drill_nm=200000,net_code=pad.GetNetCode(),local_pofv_polyline=context(pad,points),**kw)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('mirror',[False,True])
def test_saved_two_leg_path_replays_on_actual_rotated_and_mirrored_surface_lands(tmp_path,angle,face,mirror):
    b,source,pad,args=fixture(tmp_path,angle,face,mirror)
    raw=source.read_bytes();sides=force._sidecars(source);floors=local._floors(b)
    assert seat(b,pad,args['dogbone_points_nm'])
    assert not fr._via_spot_clear(b,pcbnew.VECTOR2I(*args['dogbone_points_nm'][-1]),
        300000,200000,{pad.GetNetCode()},drill_nm=200000,net_code=pad.GetNetCode())
    proposal=ground.plan(source,**args)
    assert len(proposal['ops'])==3 and [o[0]for o in proposal['ops']]==['trk','trk','via']
    assert all(o[3]==200000 for o in proposal['ops']if o[0]=='trk')
    child=Path(ground.write_private(proposal,tmp_path/'received-two-leg')['candidate'])
    r=ground.receive(source,child,**args)
    assert r['ok']and r['complete'],r['errors']
    assert r['saved_return_witness_mm']==pytest.approx(.4+(.4**2+.4**2)**.5)
    assert r['every_source_native_partition_identical']and r['all_source_known_returns']['ok']
    assert not r['fab_ready']and not r['current_qualified']and not r['release_authority']
    native_child=pcbnew.LoadBoard(str(child));old={force._uid(i)for i in b.GetTracks()}
    via=next(i for i in native_child.GetTracks()if i.GetClass()=='PCB_VIA'and force._uid(i)not in old)
    assert fab.local_pofv_via_decision(native_child,via)==(True,'bounded same-layer two-leg SMD dogbone')
    assert source.read_bytes()==raw and force._sidecars(source)==sides==force._sidecars(child)
    assert local._floors(b)==floors


@pytest.mark.parametrize('fault',['too_many','too_few','boolean','float','offpad','noncanonical',
    'zero_leg','reversal','straight','far','inside_pad','partial_pad','without_rule',
    'without_group','locked_group','mutated_floor','profile_only','wrong_pad','dnp',
    'extra_context_field','mixed_position','no_saved_rule_optin'])
def test_two_leg_request_cannot_supply_process_or_geometric_waivers(tmp_path,fault):
    b,source,pad,args=fixture(tmp_path);points=args['dogbone_points_nm']
    if fault=='too_many':points.insert(1,points[1][:])
    elif fault=='too_few':points.pop(1)
    elif fault=='boolean':points[0][0]=True
    elif fault=='float':points[0][0]=float(points[0][0])
    elif fault=='offpad':points[0][0]+=300000
    elif fault=='noncanonical':points[1][0]+=1
    elif fault=='zero_leg':points[1]=points[0][:]
    elif fault=='reversal':points[2]=[points[0][0]-400000,points[0][1]+400000]
    elif fault=='straight':points[2]=[points[0][0],points[0][1]-800000]
    elif fault=='far':points[2]=[points[0][0]+1000000,points[0][1]-1400000]
    elif fault=='inside_pad':points[1]=[points[0][0],points[0][1]-50000];points[2]=[points[0][0]+50000,points[0][1]-100000]
    elif fault=='partial_pad':points[1]=[points[0][0],points[0][1]-150000];points[2]=[points[0][0]+100000,points[0][1]-250000]
    elif fault=='without_rule':source.with_suffix('.kicad_dru').unlink()
    elif fault=='without_group':
        g=next(g for g in b.Groups()if g.GetName()==local.GROUP)
        for i in list(g.GetItems()):g.RemoveItem(i)
        b.Remove(g);field._save_field_snapshot(b,source)
    elif fault=='locked_group':next(g for g in b.Groups()if g.GetName()==local.GROUP).SetLocked(True);field._save_field_snapshot(b,source)
    elif fault=='mutated_floor':
        b.GetDesignSettings().m_ViasMinSize+=1
        assert not seat(b,pad,points)
        return
    elif fault=='profile_only':source.with_suffix('.kicad_dru').write_text('(version 1)')
    elif fault=='wrong_pad':args['pad_uuid']='00000000-0000-4000-8000-000000000001'
    elif fault=='dnp':pad.GetParentFootprint().SetDNP(True);field._save_field_snapshot(b,source)
    elif fault=='extra_context_field':
        q=context(pad,points);q['waive']=True
        assert local.inspect_polyline(b,q,pcbnew.VECTOR2I(*points[-1]),300000,200000,pad.GetNetCode())is None
        return
    elif fault=='mixed_position':args['dogbone_position_nm']=points[-1][:]
    else:args['use_existing_local_pad_rule']=False
    raw=source.read_bytes()
    with pytest.raises(ValueError):ground.plan(source,**args)
    assert source.read_bytes()==raw


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.In2_Cu,pcbnew.In3_Cu,pcbnew.In4_Cu,pcbnew.B_Cu])
def test_two_leg_barrel_retains_every_enabled_face_foreign_copper_probe(tmp_path,layer):
    b,source,pad,args=fixture(tmp_path);points=args['dogbone_points_nm'];assert seat(b,pad,points)
    at=pcbnew.VECTOR2I(*points[-1]);t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet('obstruction'));t.SetLayer(layer)
    t.SetWidth(200000);t.SetStart(at-pcbnew.VECTOR2I(0,500000));t.SetEnd(at+pcbnew.VECTOR2I(0,500000));b.Add(t)
    detail={};assert not seat(b,pad,points,report=detail)
    assert detail['reason']=='foreign copper excludes via land'


@pytest.mark.parametrize('option',['existing_via_uuid','native_padstack_via','local_pofv_pad',
    'local_pofv_dogbone','local_pofv_contained_pad','local_pofv_source_track_body'])
def test_two_leg_context_is_exclusive(tmp_path,option):
    b,source,pad,args=fixture(tmp_path)
    assert not seat(b,pad,args['dogbone_points_nm'],**{option:pad if option!='existing_via_uuid'else 'not-owned'})


@pytest.mark.parametrize('fault',['width','layer','position','group','missing_leg','extra_track','old_source','rule'])
def test_saved_two_leg_receiver_rejects_every_changed_or_unowned_delta(tmp_path,fault):
    b,source,pad,args=fixture(tmp_path);q=ground.plan(source,**args);child_board=ground.construct(q)
    old={force._uid(i)for i in b.GetTracks()};new=[i for i in child_board.GetTracks()if force._uid(i)not in old]
    via=next(i for i in new if i.GetClass()=='PCB_VIA');edge=next(i for i in new if i.GetClass()=='PCB_TRACK')
    if fault=='width':edge.SetWidth(edge.GetWidth()-1)
    elif fault=='layer':edge.SetLayer(pcbnew.B_Cu)
    elif fault=='position':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='group':next(g for g in child_board.Groups()if g.GetName()==local.GROUP).RemoveItem(via)
    elif fault=='missing_leg':child_board.Remove(edge)
    elif fault=='extra_track':
        t=pcbnew.PCB_TRACK(child_board);t.SetNet(pad.GetNet());t.SetLayer(0);t.SetWidth(200000)
        t.SetStart(pcbnew.VECTOR2I_MM(3,3));t.SetEnd(pcbnew.VECTOR2I_MM(4,3));child_board.Add(t)
    elif fault=='old_source':next(i for i in child_board.GetTracks()if force._uid(i)in old and i.GetClass()=='PCB_TRACK').Move(pcbnew.VECTOR2I(1,0))
    child=force._copy_family(source,tmp_path/'altered');field._save_field_snapshot(child_board,child)
    if fault=='rule':child.with_suffix('.kicad_dru').write_text('(version 1)')
    r=ground.receive(source,child,**args)
    assert not r['ok']and not r['complete']and r['errors']


def test_literal_inside_land_entry_is_not_replaced_by_pad_centre(tmp_path):
    b,source,pad,args=fixture(tmp_path);args['dogbone_points_nm'][0][1]-=100000
    q=ground.plan(source,**args);assert q['ops'][0][1]==args['dogbone_points_nm'][0]
    forged=copy.deepcopy(q);forged['ops'][0][3]-=1
    with pytest.raises(ValueError,match='stale_or_forged'):ground.construct(forged)


def test_only_the_selected_source_ground_island_may_join_the_real_reference(tmp_path):
    b,source,pad,args=fixture(tmp_path,isolated=True);raw=source.read_bytes()
    q=ground.plan(source,**args);assert q['source_return_witness_mm']is None
    child=Path(ground.write_private(q,tmp_path/'joined')['candidate']);r=ground.receive(source,child,**args)
    assert r['ok']and r['complete'],r['errors']
    assert not r['every_source_native_partition_identical']
    assert r['selected_Source_ground_join']['only_selected_ground_Source_islands_joined']
    assert r['selected_Source_ground_join']['joined_Source_ground_partitions']==1
    assert source.read_bytes()==raw


def test_actual_native_rule_requires_existing_membership_for_two_leg_barrel(tmp_path):
    b,source,pad,args=fixture(tmp_path);q=ground.plan(source,**args)
    child=Path(ground.write_private(q,tmp_path/'native-control')['candidate'])
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('explicit native reporting build required')
    fresh=pcbnew.LoadBoard(str(child));old={force._uid(i)for i in b.GetTracks()}
    via=next(i for i in fresh.GetTracks()if i.GetClass()=='PCB_VIA'and force._uid(i)not in old);uid=force._uid(via)
    def faults(path,label):
        out=tmp_path/(label+'.json');r=native.run(path,out,reporting_build=Path(build),timeout_s=10.)
        assert r['ok']and r['complete']and not r['native_inventory']['potentially_truncated']
        return {v['type']for v in json.loads(out.read_text())['violations']
            if v['type']in('via_diameter','drill_out_of_range','annular_width')
            and any(i.get('uuid')==uid for i in v['items'])}
    assert not faults(child,'owned')
    next(g for g in fresh.Groups()if g.GetName()==local.GROUP).RemoveItem(via)
    outside=force._copy_family(child,tmp_path/'outside-group');field._save_field_snapshot(fresh,outside)
    assert faults(outside,'unowned')=={'via_diameter','drill_out_of_range','annular_width'}


def phase(candidate='/literal/child.kicad_pcb'):
    return dict(kind='source_local_ground_polyline',candidate=str(candidate),
        candidate_sha256='a'*64,pad_uuid='actual-source-land',
        points_nm=[[15000000,15000000],[15000000,14600000],[15400000,14200000]])


@pytest.mark.parametrize('fault',['width','drill','current','reach','rule','timeout','waive',
    'missing_pad','empty_pad','missing_points','many_points','few_points','bool_point',
    'float_point','huge_point','tuple_point','repeat'])
def test_strict_transaction_cannot_add_process_current_geometry_or_deadline_authority(fault):
    row=phase();rows=[row]
    if fault in('width','drill','current','reach','rule','timeout','waive'):row[fault]=True
    elif fault=='missing_pad':row.pop('pad_uuid')
    elif fault=='empty_pad':row['pad_uuid']=''
    elif fault=='missing_points':row.pop('points_nm')
    elif fault=='many_points':row['points_nm'].append([0,0])
    elif fault=='few_points':row['points_nm'].pop()
    elif fault=='bool_point':row['points_nm'][1][0]=True
    elif fault=='float_point':row['points_nm'][1][0]=1.0
    elif fault=='huge_point':row['points_nm'][1][0]=2000000001
    elif fault=='tuple_point':row['points_nm'][1]=(1,2)
    else:rows.append(phase('/another/child.kicad_pcb'))
    with pytest.raises(ValueError):transaction.validate_phases(rows)


@pytest.mark.parametrize('proof',[dict(ok=True,complete=True,release_authority=False),
    dict(ok=False,complete=False),dict(ok=True,complete=False),dict(ok=1,complete=True)])
def test_strict_transaction_independently_rederives_only_immediate_saved_parent(tmp_path,proof):
    original,parent,child=[tmp_path/(s+'.kicad_pcb')for s in('original','parent','child')]
    for p in(original,parent,child):p.write_text(p.stem)
    row=phase(child);row['candidate_sha256']=force._hash(child)
    assert transaction.validate_phases([row])==['source_local_ground_polyline']
    with mock.patch.object(transaction.ground_entry,'receive',return_value=proof)as call:
        if proof.get('ok')is True and proof.get('complete')is True:
            target,received=transaction.receive_phase(original,parent,row,'renamed-board')
            assert target==child and not received['release_authority']
        else:
            with pytest.raises(AssertionError):transaction.receive_phase(original,parent,row,'renamed-board')
        call.assert_called_once_with(parent,child,board_hint='renamed-board',
            pad_uuid=row['pad_uuid'],dogbone_points_nm=row['points_nm'],
            use_existing_local_pad_rule=True,timeout_s=10.,
            receiving_phase_timeouts_s=(10.,10.,10.,10.))
        row['candidate_sha256']='0'*64
        with pytest.raises(AssertionError):transaction.receive_phase(original,parent,row,'renamed-board')
        assert call.call_count==1


def test_live_two_leg_proof_requires_both_literal_limbs_and_retains_original_reach(tmp_path):
    b,source,pad,args=fixture(tmp_path);q=ground.plan(source,**args);child=ground.construct(q)
    old={force._uid(i)for i in b.GetTracks()}
    new=[i for i in child.GetTracks()if force._uid(i)not in old]
    via=next(i for i in new if i.GetClass()=='PCB_VIA')
    assert fab.local_pofv_via_decision(child,via,reach_mm=3.)==(True,'bounded same-layer two-leg SMD dogbone')
    first=next(i for i in new if i.GetClass()=='PCB_TRACK'and pad.HitTest(i.GetStart()))
    first.Move(pcbnew.VECTOR2I(1,0))
    assert not fab.local_pofv_via_decision(child,via)[0]
    for reach in(0,1.500001,3.,float('inf')):
        with pytest.raises(ValueError):fab.local_pofv_polyline_matches(pad,
            context(pad,args['dogbone_points_nm'])['points'],0,pad.GetNetCode(),reach_mm=reach)
