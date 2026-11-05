"""Explicit profile recovery never supplies a channel/current/plane waiver.

Native saved candidates use the real Source compiler and physical receiver.
Dispatch-only mocks below test arguments, not hardware admission.
"""
import copy
from contextlib import nullcontext
from pathlib import Path
import time

import pcbnew
import pytest

import cec_additive_pair_repair as save
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_source_connector_feedthrough as op
import root_receive_local_transaction_20261022 as transaction
import root_received_goal_scope_20261024 as scopes
from test_source_connector_feedthrough import fixture
from test_source_sideband_phase_dispatch import row, saved_row, report, FRONTIER, TAP, DIRECT


PROFILE='jlcpcb_6l_pofv_signal'


def recovery_fixture(tmp_path, monkeypatch, *, frontier=False, quarter=0,
        profile=PROFILE, face=8, fault=None):
    source, hint, ids, _ = fixture(tmp_path, monkeypatch, quarter=quarter)
    board=pcbnew.LoadBoard(str(source))
    if profile is not None:
        props=board.GetProperties();props['CEC_FAB_PROFILE']=profile;board.SetProperties(props)
    pads={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
    a,z=[pads[uid].GetPosition() for uid in ids]
    access=list(ids)
    if frontier:
        tail=pcbnew.PCB_TRACK(board);tail.SetNet(pads[ids[1]].GetNet())
        tail.SetStart(z);tail.SetEnd(z+pcbnew.VECTOR2I(round((a.x-z.x)/3),round((a.y-z.y)/3)))
        tail.SetWidth(200000);tail.SetLayer(face);tail.SetLocked(True);board.Add(tail)
        z=tail.GetEnd();access[1]=force._uid(tail)
    if fault=='plane':
        zone=pcbnew.ZONE(board);zone.SetLayer(face)
        zone.SetNet(board.FindFootprintByReference('unreached_tap').FindPadByNumber('2').GetNet())
        poly=zone.Outline();poly.NewOutline()
        for x,y in ((0,0),(40,0),(40,40),(0,40)):poly.Append(x*1000000,y*1000000)
        board.Add(zone)
    field._save_field_snapshot(board,source)
    child=force._copy_family(source,tmp_path/'recovery-child')
    board=pcbnew.LoadBoard(str(child));old={force._uid(t) for t in board.GetTracks()}
    pads={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
    track=pcbnew.PCB_TRACK(board);track.SetNet(pads[ids[0]].GetNet())
    track.SetStart(a);track.SetEnd(z);track.SetWidth(200000);track.SetLayer(face);board.Add(track)
    if fault=='candidate_profile':
        props=board.GetProperties();props['CEC_FAB_PROFILE']=PROFILE;board.SetProperties(props)
    elif fault=='new_via':
        via=pcbnew.PCB_VIA(board);via.SetNet(track.GetNet());via.SetPosition(a)
        via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    elif fault=='Source_cut':
        from cec_native_items import discard_items
        discard_items(board,[next(t for t in board.GetTracks() if force._uid(t)==access[1])])
    elif fault=='third_island':
        extra=pcbnew.PCB_TRACK(board);extra.SetNet(track.GetNet());extra.SetStart(z)
        extra.SetEnd(board.FindFootprintByReference('unreached_tap').FindPadByNumber('1').GetPosition())
        extra.SetWidth(200000);extra.SetLayer(face);board.Add(extra)
    if fault:
        field._save_field_snapshot(board,child)
    else:
        save.save_native_additions(child,board,{},old,board_hint='synthetic')
    return source,hint,ids,child,access


def receive(data,frontier=False,**kwargs):
    source,hint,ids,child,access=data
    if frontier:
        return op.receive_native_frontier(source,child,board_hint=str(hint),pad_uuids=ids,
            access_uuids=access,**kwargs)
    return op.receive(source,child,board_hint=str(hint),pad_uuids=ids,**kwargs)


@pytest.mark.parametrize('frontier',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_exact_saved_source_recovery_is_explicit_and_rotates(tmp_path,monkeypatch,frontier,quarter):
    data=recovery_fixture(tmp_path,monkeypatch,frontier=frontier,quarter=quarter)
    before=[p.read_bytes() for p in(data[0],data[3])]
    for kwargs in ({},{'allow_nonplane_power_role':False}):
        old=receive(data,frontier,**kwargs)
        assert not old['ok'] and any('authored_actual_channel' in e for e in old['errors']),old
    value=receive(data,frontier,allow_nonplane_power_role=True)
    assert value['ok'] and value['complete'],value['errors']
    policy=value['Source_routing_layer_policy']
    assert policy['allow_nonplane_power_role'] is True
    assert policy['saved_Source_profile']==PROFILE and policy['used_layer_ids']==[8]
    assert 8 in policy['allowed_layer_ids'] and not {4,10}&set(policy['allowed_layer_ids'])
    assert policy['current_or_plane_reference_or_barrel_qualified'] is False
    assert (value['source_components'],value['candidate_components'])==(3,2)
    if frontier:
        assert value['retained_native_frontier_contacts']['Source_routing_layer_policy']==policy
    assert before==[p.read_bytes() for p in(data[0],data[3])]


@pytest.mark.parametrize('frontier',[False,True])
@pytest.mark.parametrize('profile',[None,'unknown-unqualified-profile'])
def test_unknown_source_cannot_borrow_environment_or_candidate_profile(tmp_path,monkeypatch,frontier,profile):
    data=recovery_fixture(tmp_path,monkeypatch,frontier=frontier,profile=profile,
        fault='candidate_profile')
    monkeypatch.setenv('CEC_FAB_PROFILE',PROFILE)
    value=receive(data,frontier,allow_nonplane_power_role=True)
    assert not value['ok'] and any('known_saved_Source_profile' in e for e in value['errors']),value


@pytest.mark.parametrize('frontier',[False,True])
@pytest.mark.parametrize('face',[4,10])
def test_ground_roles_never_become_connector_recovery_faces(tmp_path,monkeypatch,frontier,face):
    value=receive(recovery_fixture(tmp_path,monkeypatch,frontier=frontier,face=face),
        frontier,allow_nonplane_power_role=True)
    assert not value['ok'] and value['errors'],value


@pytest.mark.parametrize('frontier',[False,True])
def test_actual_board_scale_plane_is_not_a_recovery_face(tmp_path,monkeypatch,frontier):
    value=receive(recovery_fixture(tmp_path,monkeypatch,frontier=frontier,fault='plane'),
        frontier,allow_nonplane_power_role=True)
    assert not value['ok'] and any('authored_actual_channel' in e for e in value['errors']),value


@pytest.mark.parametrize('name',['USB_DP','USB_DM','PCIe_signal','CAN_H','/receiver_P','/receiver_N'])
def test_existing_coupled_layer_portfolio_remains_excluded(tmp_path,monkeypatch,name):
    source,_,_,_=fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(source));props=board.GetProperties()
    props['CEC_FAB_PROFILE']=PROFILE;board.SetProperties(props)
    policy=op._routing_layers(board,name,lambda _:dict(name='Default'),allow_nonplane_power_role=True)
    assert 8 not in policy['allowed_layer_ids'] and not {4,10}&set(policy['allowed_layer_ids'])


def test_disabled_power_face_cannot_be_reintroduced(tmp_path,monkeypatch):
    source,_,_,_=fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(source));props=board.GetProperties()
    props['CEC_FAB_PROFILE']=PROFILE;board.SetProperties(props);board.SetCopperLayerCount(2)
    policy=op._routing_layers(board,'/status',lambda _:dict(name='Default'),allow_nonplane_power_role=True)
    assert set(policy['allowed_layer_ids'])<={0,2} and 8 not in policy['allowed_layer_ids']


@pytest.mark.parametrize('bad',[0,1,None,'true',[],{},object()])
@pytest.mark.parametrize('frontier',[False,True])
def test_receiver_rejects_nonboolean_recovery_before_opening_files(bad,frontier):
    with pytest.raises(ValueError,match='boolean_Source_nonplane'):
        receive((Path('missing'),'missing',['a','b'],Path('missing'),['a','b']),frontier,
            allow_nonplane_power_role=bad)


@pytest.mark.parametrize('fault',['new_via','Source_cut','third_island'])
def test_recovery_does_not_fund_other_source_edits_or_material(tmp_path,monkeypatch,fault):
    value=receive(recovery_fixture(tmp_path,monkeypatch,frontier=True,fault=fault),True,
        allow_nonplane_power_role=True)
    assert not value['ok'] and value['errors'],value


@pytest.mark.parametrize('kind',[DIRECT,FRONTIER])
@pytest.mark.parametrize('flag',[False,True])
def test_explicit_phase_policy_is_forwarded_only_to_its_saved_owner(tmp_path,monkeypatch,kind,flag):
    source,child,value=saved_row(tmp_path,kind);value['allow_nonplane_power_role']=flag;calls=[]
    def invoked(*args,**kwargs):
        calls.append((args,kwargs));return dict(ok=True,complete=True)
    monkeypatch.setattr(transaction.connector_feedthrough,
        'receive' if kind==DIRECT else 'receive_native_frontier',invoked)
    transaction.validate_phases([value]);actual,_=transaction.receive_phase(source,source,value,'synthetic')
    assert actual==child and calls[0][1]['allow_nonplane_power_role'] is flag
    assert calls[0][1]['timeout_s']==10. and len(calls)==1


@pytest.mark.parametrize('bad',[0,1,None,'true',[],{}])
@pytest.mark.parametrize('kind',[DIRECT,FRONTIER])
def test_phase_policy_requires_a_boolean(kind,bad):
    with pytest.raises(ValueError,match='boolean_Source_nonplane'):
        transaction.validate_phases([row(kind,allow_nonplane_power_role=bad)])


@pytest.mark.parametrize('kind',[TAP,'ordinary_join'])
def test_phase_flag_does_not_leak_into_other_roles(kind):
    value=(row(TAP) if kind==TAP else dict(kind='ordinary_join',net='/status',
        candidate='/actual/child',candidate_sha256='a'*64))
    value['allow_nonplane_power_role']=True
    with pytest.raises(ValueError,match='exact_typed_local_phase_schema'):
        transaction.validate_phases([value])


def layer_policy():
    return dict(scope='Source_profile_nonplane_search_menu_not_reference_authority',
        allow_nonplane_power_role=True,saved_Source_profile=PROFILE,
        allowed_layer_ids=[6,2,0,8],used_layer_ids=[8],
        actual_planes_and_disabled_layers_excluded=True,
        current_or_plane_reference_or_barrel_qualified=False)


@pytest.mark.parametrize('fault',['unknown_profile','no_profile','nonboolean','no_layers','ground',
    'disabled','used_not_allowed','qualified','not_plane_checked','frontier_disagrees'])
def test_reporting_cannot_forge_recovery_or_reference_qualification(fault):
    value=report();proof=value['phases'][0]['receiving'];policy=layer_policy()
    proof['Source_routing_layer_policy']=policy
    proof['retained_native_frontier_contacts']['Source_routing_layer_policy']=copy.deepcopy(policy)
    if fault=='unknown_profile':policy['saved_Source_profile']='invented'
    elif fault=='no_profile':policy['saved_Source_profile']=None
    elif fault=='nonboolean':policy['allow_nonplane_power_role']=1
    elif fault=='no_layers':policy['allowed_layer_ids']=[]
    elif fault=='ground':policy['allowed_layer_ids'].append(4)
    elif fault=='disabled':policy['allowed_layer_ids'].append(999)
    elif fault=='used_not_allowed':policy['used_layer_ids']=[10]
    elif fault=='qualified':policy['current_or_plane_reference_or_barrel_qualified']=True
    elif fault=='not_plane_checked':policy['actual_planes_and_disabled_layers_excluded']=False
    else:proof['retained_native_frontier_contacts']['Source_routing_layer_policy']['allow_nonplane_power_role']=False
    with pytest.raises(ValueError):scopes.received_repair_scope(value)


def test_report_echoes_policy_without_relabelling_a_plane_or_load_qualification():
    value=report();proof=value['phases'][0]['receiving'];policy=layer_policy()
    proof['Source_routing_layer_policy']=policy
    proof['retained_native_frontier_contacts']['Source_routing_layer_policy']=copy.deepcopy(policy)
    described=scopes.received_repair_scope(value)
    assert described['exact_received_Source_boundaries'][0]['Source_routing_layer_policy']==policy
    assert described['new_current_or_Kelvin_or_barrel_or_voltage_qualification'] is False


@pytest.mark.parametrize('wrapped',[False,True])
def test_actual_native_recovery_phase_and_reporting_use_the_same_policy(tmp_path,monkeypatch,wrapped):
    import root_ordinary_preclear_measurement_phase_20261028 as wrapper
    source,hint,ids,child,access=recovery_fixture(tmp_path,monkeypatch,frontier=True)
    value=row(FRONTIER,pad_uuids=ids,access_uuids=access,candidate=str(child),
        candidate_sha256=force._hash(child),allow_nonplane_power_role=True)
    with wrapper.installed() if wrapped else nullcontext():
        transaction.validate_phases([value])
        _,proof=transaction.receive_phase(source,source,value,str(hint))
    received=report();received['phases'][0]=dict(kind=FRONTIER,receiving=proof)
    described=scopes.received_repair_scope(received)
    policy=described['exact_received_Source_boundaries'][0]['Source_routing_layer_policy']
    assert policy['used_layer_ids']==[8] and policy['allow_nonplane_power_role'] is True


@pytest.mark.parametrize('fault',['manufacturer','Source_pin','current_class'])
@pytest.mark.parametrize('frontier',[False,True])
def test_explicit_recovery_cannot_replace_positive_source_channel_ownership(tmp_path,monkeypatch,fault,frontier):
    data=recovery_fixture(tmp_path,monkeypatch,frontier=frontier)
    source,hint,_,_,_=data
    if fault=='manufacturer':
        hint.write_text(hint.read_text().replace('(property "Manufacturer" "Molex")',
            '(property "Manufacturer" "unqualified")',1))
    elif fault=='Source_pin':
        hint.write_text(hint.read_text().replace('(name "SENSE")','(name "GND")'))
    else:
        source.with_suffix('.kicad_pro').write_text('{"net_settings":{"classes":'
            '[{"name":"Power","track_width":0.2,"clearance":0.2}],'
            '"netclass_patterns":[{"netclass":"Power","pattern":"*"}]}}')
    value=receive(data,frontier,allow_nonplane_power_role=True)
    assert not value['ok'] and value['errors'],value


def test_source_mutation_during_recovery_is_not_a_new_live_receipt(tmp_path,monkeypatch):
    import cec_additive_route_receiving as additive
    data=recovery_fixture(tmp_path,monkeypatch)
    original=additive.receive
    def changed(*args,**kwargs):
        value=original(*args,**kwargs)
        data[1].write_text(data[1].read_text()+'\n; mutated during actual receiving\n')
        return value
    monkeypatch.setattr(additive,'receive',changed)
    value=receive(data,allow_nonplane_power_role=True)
    assert not value['ok'] and any('changed' in error for error in value['errors']),value


def test_code_mutation_during_recovery_cannot_preserve_an_approval(tmp_path,monkeypatch):
    data=recovery_fixture(tmp_path,monkeypatch)
    original=force._code_identity;calls=[]
    def changing():
        value=original();calls.append(True);value['actual-policy-epoch']=str(len(calls));return value
    monkeypatch.setattr(force,'_code_identity',changing)
    value=receive(data,allow_nonplane_power_role=True)
    assert not value['ok'] and value['errors'],value


def test_direct_reporting_checks_the_same_explicit_policy():
    from test_source_sideband_phase_dispatch import channel
    value=report();proof=value['phases'][0]['receiving']
    value['phases'][0]['kind']=DIRECT
    proof.update(scope='Source_canonical_existing_plated_sideband_feedthrough',
        actual_flashed_annular_contacts=[dict(pad_uuid='first',layer=8),dict(pad_uuid='last',layer=8)],
        independently_compiled_Source_scope=channel(('first','last')),
        Source_routing_layer_policy=layer_policy())
    described=scopes.received_repair_scope(value)
    assert described['Source_connector_routing_layer_policies'][0]['allow_nonplane_power_role'] is True
    proof['Source_routing_layer_policy']['used_layer_ids']=[10]
    with pytest.raises(ValueError):scopes.received_repair_scope(value)
