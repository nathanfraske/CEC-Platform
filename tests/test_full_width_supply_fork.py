"""Wide supply reconstruction needs a real complete current owner, not a cap."""
import copy,json,time
import pcbnew
import pytest
import cec_cell_shared_fork as fork
import cec_cell_escape_replan as cell
import cec_force_current as force
from cec_native_items import discard_items
from test_cell_shared_fork import fixture,power_authority,proposal


def wide(tmp_path,monkeypatch,*,quarter=0,back=False,width=.5):
    b,source,root,a,z,edges,xy=fixture(tmp_path,quarter,back,renamed=True,power=True)
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    for t in edges:t.SetWidth(round(width*1e6))
    contract,rated=power_authority(monkeypatch,str(root.GetNetname()),face,.5)
    return b,source,root,a,z,edges,xy,contract,rated


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('width',[.5,.7])
def test_actual_uniform_rated_width_and_fixed_ports_survive_all_native_poses(tmp_path,monkeypatch,quarter,back,width):
    b,source,root,a,z,edges,xy,contract,rated=wide(tmp_path,monkeypatch,quarter=quarter,back=back,width=width)
    before=cell.row._source_binding(b)
    with pytest.raises(ValueError,match='no_owned_departures'):proposal(b,root,kind='rated_supply')
    q=proposal(b,root,kind='rated_supply',allow_full_current_supply_width=True)
    assert q['width_nm']==round(width*1e6)
    assert set(q['track_uuids'])=={force._uid(t)for t in edges}
    assert {p['native_uuid']for p in q['retained_native_ports']}=={force._uid(a),force._uid(z)}
    assert q['full_current_source_seed_plan']['contract']==contract
    assert q['full_current_source_plan']['contract']==contract
    assert q['full_current_source_plan']['full_current_floor_nm']==500000
    assert not q['source_vias_zones_wide_tracks_and_groups_never_retired']
    assert q['source_vias_zones_and_groups_never_retired']and q['no_wider_scalar_or_ground_fork_authority']
    assert not q['current_authority']and not q['routing_admitted']and not q['release_authority']
    discard_items(b,edges);requests=fork.connections(b,json.loads(json.dumps(q)))
    assert len(requests)==2 and all(r['width_nm']==round(width*1e6)for r in requests)
    assert all(r['unchanged_full_rail_current_contract']==json.loads(json.dumps(rated))for r in requests)


def test_actual_round_endcap_barrel_contact_is_a_fixed_port_not_an_endpoint_guess(tmp_path,monkeypatch):
    b,source,root,a,z,edges,xy,contract,rated=wide(tmp_path,monkeypatch)
    at=xy((14.4024,9.));via=pcbnew.PCB_VIA(b);via.SetPosition(at);via.SetWidth(600000);via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNetCode(root.GetNetCode());b.Add(via)
    assert all(at!=p for t in edges for p in(t.GetStart(),t.GetEnd()))
    assert any(via.GetEffectiveShape(pcbnew.F_Cu).Collide(t.GetEffectiveShape(pcbnew.F_Cu),0)for t in edges)
    q=proposal(b,root,kind='rated_supply',allow_full_current_supply_width=True)
    assert force._uid(via)not in q['track_uuids']
    ports={p['native_uuid']:p for p in q['retained_native_ports']}
    assert ports[force._uid(via)]['at_nm']==list(at)
    discard_items(b,edges);cohorts=fork.fixed_cohorts(b,q,deadline=time.monotonic()+5.)
    assert any(force._uid(via)in c['native_component_uuids']for c in cohorts)


@pytest.mark.parametrize('fault',['unknown_budget','incomplete_domain','mixed_width','underwidth','wrong_terminal','grouped','source_mutated'])
def test_full_width_tier_cannot_borrow_a_signal_floor_or_incomplete_source_owner(tmp_path,monkeypatch,fault):
    b,source,root,a,z,edges,xy,contract,rated=wide(tmp_path,monkeypatch)
    if fault=='unknown_budget':monkeypatch.setattr(fork.topology,'distributed_supply_contracts',lambda *a,**k:dict(contracts={}))
    elif fault=='incomplete_domain':monkeypatch.setattr(fork.topology,'board_current_domains',lambda *a,**k:{str(root.GetNetname()):dict(complete=False)})
    elif fault=='mixed_width':edges[3].SetWidth(700000)
    elif fault=='underwidth':
        for t in edges:t.SetWidth(490000)
    elif fault=='wrong_terminal':root.SetNumber('4')
    elif fault=='grouped':
        group=pcbnew.PCB_GROUP(b);b.Add(group)
        for t in edges:group.AddItem(t)
    else:
        pcbnew.SaveBoard(str(source),b);edges[0].SetWidth(501000)
        with pytest.raises(ValueError,match='literal_saved_native_source_fork_snapshot'):
            fork.plan(b,[force._uid(root)],moving_refs=[root.GetParentFootprint().GetReference()],
                kind='rated_supply',board_hint='synthetic',allow_owned_locked=True,allow_full_current_supply_width=True)
        return
    before=cell.row._source_binding(b)
    with pytest.raises(ValueError):proposal(b,root,kind='rated_supply',allow_full_current_supply_width=True)
    assert cell.row._source_binding(b)==before


@pytest.mark.parametrize('kind',['scalar_input','ground_return'])
def test_wide_permission_is_not_available_to_other_fork_roles(kind):
    with pytest.raises(ValueError,match='bounded_explicit_source_cell_fork_context'):
        fork.plan(None,['root'],moving_refs=['owner'],kind=kind,board_hint='synthetic',allow_full_current_supply_width=True)


@pytest.mark.parametrize('value',[None,0,1,'yes',{}])
def test_width_scope_requires_explicit_bool_before_native_access(value):
    with pytest.raises(ValueError,match='bounded_explicit_source_cell_fork_context'):
        fork.plan(None,['root'],moving_refs=['owner'],kind='rated_supply',board_hint='synthetic',allow_full_current_supply_width=value)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_complete_saved_cap_only_reanchor_recompiles_whole_current_fork(tmp_path,monkeypatch,quarter,back):
    """A real saved macro, not just a planner's favorable Source inventory."""
    import cec_additive_route_receiving as additive
    import cec_cell_macro_requests as compiler
    import cec_complete_macro_cell as macro
    from test_complete_macro_cell import fixture as macro_fixture
    source,parent,unused,original=macro_fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    cap=next(iter(original['source_plan']['selected_bypasses']))
    poses=copy.deepcopy(original['source_plan']['poses'])
    # Rotate the same local displacement with the actual native geometry.
    # A global +x/+y shift would drive two poses toward the retained feed
    # barrel and would correctly fail the unchanged all-face via guard.
    dx,dy=((-.5,-.5),(-.5,.5),(.5,.5),(.5,-.5))[quarter]
    cf=parent.FindFootprintByReference(cap)
    poses[cap]=[cf.GetPosition().x/1e6+dx,cf.GetPosition().y/1e6+dy,cf.GetOrientationDegrees()]
    stationary=set(poses)-{cap}
    for ref in stationary:
        fp=parent.FindFootprintByReference(ref)
        poses[ref]=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()]
    raw=source.read_bytes()
    private,packet=compiler.compile(source,poses,board_hint='opaque')
    owned=packet['source_plan']['source_owned_shared_supply_forks']
    assert owned and all(q['allow_full_current_supply_width'] for q in owned)
    assert all(q['width_nm']==q['full_current_source_plan']['full_current_floor_nm']==500000 for q in owned)
    assert set(packet['source_plan']['stationary_device_owners'])==stationary
    assert not packet['source_plan']['measurement_leaves']
    prefill=compiler.pre_refill_barrel_screen(private,packet)
    assert prefill['ok'],prefill
    additive._ground_refill(private)
    assert compiler.native_pose_screen(parent,private,packet)['ok']
    proof=macro.screen(source,private,packet,board_hint='opaque')
    assert proof['complete'],(proof.get('errors'),proof.get('empty_obligations'))
    cell.construct_private(private,proof['packet'],proof['selection'])
    additive._ground_refill(private)
    child=force._copy_family(source,tmp_path/'complete-wide-child')
    macro.save_private(private,child,packet)
    received=macro.receive(source,child,board_hint='opaque')
    assert received['ok'] and received['complete'],received['errors']
    assert received['all_original_surviving_native_partitions_preserved']
    assert received['all_original_physical_ground_returns']['ok']
    assert source.read_bytes()==raw
    assert not any(received[k] for k in ('routing_admitted','fab_ready','release_authority','current_qualified'))
