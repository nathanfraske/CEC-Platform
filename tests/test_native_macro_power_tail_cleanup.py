"""New power tails need actual full-load receiving, not ordinary-net waivers."""
from unittest import mock
import pcbnew,pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_native_macro_power_tail_cleanup as cleanup
from test_distributed_loop_retirement import fixture
from test_field_proposals import track


def reports(uid):return dict(violations=[]),dict(violations=[dict(type='track_dangling',items=[dict(uuid=uid)])])


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_new_full_load_power_leaf_is_removed_without_requalifying_macro_prefix(tmp_path,angle,mirror):
    original,b,q,catalog,*rest=fixture(tmp_path,angle,mirror);xy=rest[-1]
    frozen=original.read_bytes()
    item=track(b,q['net'],xy((6,5)),xy((6,4)),width=.2);item.SetLocked(True);uid=force._uid(item)
    prefix=force._copy_family(original,tmp_path/'prefix');field._save_field_snapshot(b,prefix)
    old,new=reports(uid)
    with mock.patch.object(cleanup.topology,'distributed_supply_contracts',return_value=catalog):
        result=cleanup.construct(original,prefix,tmp_path/'cut',board_hint='synthetic',original_native=old,proposed_native=new)
    assert result['ok'] and result['complete'] and result['changed'],result
    assert result['retired_track_uuids']==[uid] and not result['retired_via_uuids']
    assert result['original_macro_source_receiving_still_required'] and not result['current_qualified']
    assert not result['release_authority'] and original.read_bytes()==frozen
    child=pcbnew.LoadBoard(result['candidate']);assert uid not in {force._uid(t) for t in child.GetTracks()}


@pytest.mark.parametrize('mode',['inherited','source_track','no_catalog','force','gnd','pair'])
def test_original_or_untyped_material_is_not_automatically_eligible(tmp_path,mode):
    original,b,q,catalog,*rest=fixture(tmp_path);xy=rest[-1]
    name={'gnd':'GND','pair':'/USB_D_P','force':'/MAIN_FORCE'}.get(mode,q['net'])
    if name!=q['net']:
        b.Add(pcbnew.NETINFO_ITEM(b,name));code=b.GetNetcodeFromNetname(name)
        for native in [*b.GetTracks(),*(p for fp in b.GetFootprints() for p in fp.Pads())]:native.SetNetCode(code)
        field._save_field_snapshot(b,original)
    item=track(b,name,xy((6,5)),xy((6,4)),width=.2);uid=force._uid(item)
    if mode=='source_track':field._save_field_snapshot(b,original)
    prefix=force._copy_family(original,tmp_path/'prefix');field._save_field_snapshot(b,prefix)
    old,new=reports(uid)
    if mode=='inherited':old=new
    if mode=='no_catalog':catalog=dict(contracts={})
    with mock.patch.object(cleanup.topology,'distributed_supply_contracts',return_value=catalog):
        result=cleanup.construct(original,prefix,tmp_path/'unused',board_hint='synthetic',original_native=old,proposed_native=new)
    assert result['ok'] and not result['changed'] and result['candidate'] is None,result


@pytest.mark.parametrize('mode',['narrow','group','necessary','wrong_role','sharing'])
def test_a_warning_cannot_authorize_undersizing_groups_or_a_live_power_branch(tmp_path,mode):
    original,b,q,catalog,*rest=fixture(tmp_path);xy=rest[-1]
    if mode=='necessary':
        from cec_native_items import discard_items
        kept_ids={force._uid(t) for t in rest[0]}
        discard_items(b,[t for t in b.GetTracks() if force._uid(t) not in kept_ids])
        trunk=rest[0][0];trunk.SetEnd(pcbnew.VECTOR2I_MM(*xy((6,5))))
        field._save_field_snapshot(b,original)
        item=track(b,q['net'],xy((6,5)),xy((9,5)),width=.2)
    else:item=track(b,q['net'],xy((6,5)),xy((6,4)),width=.1 if mode=='narrow' else .2)
    uid=force._uid(item)
    if mode=='group':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(item)
    if mode=='wrong_role':catalog['contracts'][q['net']]['role']='inferred'
    if mode=='sharing':catalog['contracts'][q['net']]['branch_sharing_assumed']=True
    prefix=force._copy_family(original,tmp_path/'prefix');field._save_field_snapshot(b,prefix)
    old,new=reports(uid)
    with mock.patch.object(cleanup.topology,'distributed_supply_contracts',return_value=catalog):
        result=cleanup.construct(original,prefix,tmp_path/'refused',board_hint='synthetic',original_native=old,proposed_native=new)
    assert not result['ok'] and result['errors'],result


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_explicit_small_current_domain_has_its_own_independent_receiver(tmp_path,monkeypatch,angle,mirror):
    original,b,q,catalog,*rest=fixture(tmp_path,angle,mirror);xy=rest[-1];net=q['net']
    refs=sorted(fp.GetReference() for fp in b.GetFootprints())
    domain=dict(net=net,amps=.1,complete=True,source_refs=refs[:1],sink_refs=refs[1:],authority_refs=refs)
    contract=dict(catalog['contracts'][net],amps=.1,authority_refs=refs)
    monkeypatch.setattr(cleanup.topology,'distributed_supply_contracts',lambda *a,**kw:dict(contracts={}))
    monkeypatch.setattr(cleanup.topology,'board_current_domains',lambda *a,**kw:{net:domain})
    monkeypatch.setattr(cleanup.topology,'route_width_contracts',lambda *a,**kw:{net:contract})
    item=track(b,net,xy((6,5)),xy((6,4)),width=.2);item.SetLocked(True);uid=force._uid(item)
    prefix=force._copy_family(original,tmp_path/'prefix');field._save_field_snapshot(b,prefix)
    old,new=reports(uid)
    result=cleanup.construct(original,prefix,tmp_path/'small-force-cut',board_hint='synthetic',original_native=old,proposed_native=new)
    assert result['ok'] and result['complete'] and result['changed'],result
    assert result['positive_type']=='source_declared_whole_current_domain'
    assert result['retired_track_uuids']==[uid] and not result['current_qualified'] and not result['release_authority']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_exact_source_supply_tail_opt_in_still_needs_independent_full_load_receiver(tmp_path,angle,mirror):
    original,b,q,catalog,*rest=fixture(tmp_path,angle,mirror);xy=rest[-1]
    item=track(b,q['net'],xy((6,5)),xy((6,4)),width=.2);item.SetLocked(True);uid=force._uid(item)
    field._save_field_snapshot(b,original);raw=original.read_bytes()
    prefix=force._copy_family(original,tmp_path/'posed-prefix');old,new=reports(uid)
    with mock.patch.object(cleanup.topology,'distributed_supply_contracts',return_value=catalog):
        result=cleanup.construct(original,prefix,tmp_path/'original-tail-cut',board_hint='synthetic',
            original_native=old,proposed_native=new,allow_obsolete_source_track_uuids=[uid])
    assert result['ok'] and result['complete'] and result['changed'],result
    assert result['explicitly_requested_original_obsolete_track_uuids']==[uid]
    assert result['independent_exact_full_load_supply_loop_receiving']['ok']
    assert original.read_bytes()==raw and not result['release_authority']


@pytest.mark.parametrize('bad',['missing','duplicate','inherited','changed','untyped'])
def test_source_supply_tail_request_is_not_a_geometry_or_type_waiver(tmp_path,bad):
    original,b,q,catalog,*rest=fixture(tmp_path);xy=rest[-1]
    item=track(b,q['net'],xy((6,5)),xy((6,4)),width=.2);uid=force._uid(item)
    field._save_field_snapshot(b,original);selected=[uid]
    if bad=='changed':item.SetWidth(250000)
    prefix=force._copy_family(original,tmp_path/'posed-prefix');field._save_field_snapshot(b,prefix)
    old,new=reports(uid)
    if bad=='missing':selected=['not-in-source']
    elif bad=='duplicate':selected*=2
    elif bad=='inherited':old=new
    elif bad=='untyped':catalog=dict(contracts={})
    with mock.patch.object(cleanup.topology,'distributed_supply_contracts',return_value=catalog):
        result=cleanup.construct(original,prefix,tmp_path/'refused',board_hint='synthetic',
            original_native=old,proposed_native=new,allow_obsolete_source_track_uuids=selected)
    assert not result['ok'] and result['errors'],result


@pytest.mark.parametrize('whole_scope',[False,True])
def test_whole_source_power_leaf_is_discovered_before_cut_not_warning_chased(tmp_path,whole_scope):
    original,b,q,catalog,*rest=fixture(tmp_path);xy=rest[-1]
    near=track(b,q['net'],xy((6,5)),xy((6,4)),width=.2)
    end=track(b,q['net'],xy((6,4)),xy((6,3)),width=.2)
    for item in (near,end):item.SetLocked(True)
    ids=[force._uid(near),force._uid(end)];field._save_field_snapshot(b,original)
    prefix=force._copy_family(original,tmp_path/'posed-prefix');old,new=reports(ids[1])
    with mock.patch.object(cleanup.topology,'distributed_supply_contracts',return_value=catalog):
        result=cleanup.construct(original,prefix,tmp_path/'whole-tail',board_hint='synthetic',
            original_native=old,proposed_native=new,allow_obsolete_source_track_uuids=ids if whole_scope else ids[1:])
    assert result['ok']==whole_scope,result
    assert set(result['native_whole_supply_leaf_chain_discovery']['proposed_exact_track_uuids'])==set(ids)
    if whole_scope:
        assert set(result['retired_track_uuids'])==set(ids) and result['complete']
    else:assert 'exact_whole_original_tail_scope' in str(result['errors'])
