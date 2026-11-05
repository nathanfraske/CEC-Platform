"""Literal Source joins compose; arbitrary/internal/foreign ports do not."""
import copy,time
import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_cell_row_rebuild as row
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_macro_boundary_composition as compose
import cec_macro_cut_components as components
from test_cell_escape_replan import fixture as source_fixture
from test_field_proposals import track
from cec_native_items import discard_items


def fixture(tmp_path,monkeypatch,quarter=0,back=False):
    board,unused,owner,cap=source_fixture(monkeypatch,prefix='unrelated_named')
    pad=owner.FindPadByNumber('4');pad.SetSize(pcbnew.VECTOR2I(650000,1117500))
    start=(11.,11.55875);join=(11.,11.86275);end=(12.5,13.36275)
    stub=track(board,'INPUT_N',start,join,width=.2)
    peer=track(board,'INPUT_N',join,end,width=.2)
    via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet('INPUT_N'));via.SetPosition(pcbnew.VECTOR2I_MM(*end))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    if back:
        for fp in board.GetFootprints():
            fp.SetLayer(pcbnew.B_Cu)
            for p in fp.Pads():
                ls=pcbnew.LSET();ls.AddLayer(pcbnew.B_Cu);p.SetLayerSet(ls)
        for t in (stub,peer):t.SetLayer(pcbnew.B_Cu)
    if quarter:
        for i in [*board.GetFootprints(),*board.GetTracks()]:
            i.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    path=tmp_path/'native.kicad_pcb';field._save_field_snapshot(board,path)
    binding=row._source_binding(board);uid=force._uid(stub);other=force._uid(peer);face=int(stub.GetLayer())
    plan=dict(scope='source_typed_complete_cell_escape_proposal',source_native_binding=binding,
        board_hint='opaque',retired_track_uuids=[uid],poses={owner.GetReference():[1,1,0]},
        device_contracts={owner.GetReference():roles.footprint_contract(owner)})
    request=dict(kind='source_boundary',net='INPUT_N',width_nm=200000,
        a=dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),layers=[face]),
        b=dict(native_uuids=[other],at_nm=list(stub.GetEnd()),layers=[face]))
    extra=[dict(change=dict(uuid=other,net='INPUT_N',source_nm=[list(peer.GetStart()),list(peer.GetEnd())]),
        authority=dict(kind='positive_source_ordinary',native_source_uuid=other))]
    monkeypatch.setattr(compose.ordinary,'eligible_nets',lambda *a:{'INPUT_N'})
    return board,path,plan,{'boundary:'+uid:request},extra,uid,other


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_composed_native_component_has_both_real_terminals_not_the_old_bend(tmp_path,monkeypatch,quarter,back):
    board,path,plan,requests,extras,stub,peer=fixture(tmp_path,monkeypatch,quarter,back)
    raw=path.read_bytes();before=row._source_binding(board);old=copy.deepcopy(extras)
    pending,extended,proofs=compose.compose(board,path,plan,requests,extras,deadline=time.monotonic()+10.)
    assert not pending and len(extended)==2 and len(proofs)==1
    assert proofs[0]['source_base_boundary_composition']
    assert proofs[0]['source_base_boundary_uuid']==stub
    assert {r['change']['uuid'] for r in extended}=={stub,peer}
    assert extras==old and row._source_binding(board)==before and path.read_bytes()==raw
    private=pcbnew.LoadBoard(str(path));retired={stub,peer}
    discard_items(private,[t for t in private.GetTracks() if force._uid(t) in retired])
    transport=dict(source_process_barrel_motion=[],explicit_source_typed_ordinary_barrel_motion=[])
    rebuilt,groups=components.requests(board,private,extended,retired,transport,
        project_contacts=compiler._project_contacts,deadline=time.monotonic()+10.)
    assert len(groups)==1 and len(rebuilt)==1
    assert {q['source_class'] for q in groups[0]['surviving_contacts']}=={'PAD','PCB_VIA'}
    assert groups[0]['source_extra_edge_uuids']==sorted(retired)
    assert all(r['every_surviving_source_component_port_mandatory'] for r in rebuilt.values())


@pytest.mark.parametrize('fault',['join','interior','net','width','group','role','stale_source'])
def test_false_source_boundaries_cannot_be_composed(tmp_path,monkeypatch,fault):
    board,path,plan,requests,extras,stub,peer=fixture(tmp_path,monkeypatch)
    request=next(iter(requests.values()))
    if fault=='join':request['b']['at_nm'][0]+=1
    elif fault=='interior':request['b']['at_nm'][1]-=100000
    elif fault=='net':request['net']='GND_other'
    elif fault=='width':request['width_nm']=100000
    elif fault=='group':
        group=pcbnew.PCB_GROUP(board);board.Add(group);group.AddItem(next(t for t in board.GetTracks() if force._uid(t)==stub))
        plan['source_native_binding']=row._source_binding(board)
    elif fault=='role':plan['device_contracts']={}
    else:plan['source_native_binding']='forged'
    before=row._source_binding(board)
    with pytest.raises(ValueError):compose.compose(board,path,plan,requests,extras,deadline=time.monotonic()+10.)
    assert row._source_binding(board)==before


@pytest.mark.parametrize('fault',['not_base','not_extra','unsupported_authority','not_boundary','ground'])
def test_unowned_or_other_contracts_are_left_mandatory_not_acquired(tmp_path,monkeypatch,fault):
    board,path,plan,requests,extras,stub,peer=fixture(tmp_path,monkeypatch)
    if fault=='not_base':plan['retired_track_uuids']=[]
    elif fault=='not_extra':extras=[]
    elif fault=='unsupported_authority':extras[0]['authority']['kind']='unchanged_full_current_source_edge'
    elif fault=='not_boundary':requests={'retained:'+stub:next(iter(requests.values()))}
    else:next(iter(requests.values()))['net']='GND'
    pending,extended,proofs=compose.compose(board,path,plan,requests,extras,deadline=time.monotonic()+10.)
    assert pending==requests and extended==extras and not proofs


def rated_fixture(tmp_path,monkeypatch,quarter=0,back=False,renamed=False):
    import cec_cell_shared_fork as fork
    import cec_full_current_planar_reflow as full
    from test_cell_shared_fork import fixture as native_fork,power_authority
    board,source,root,a,z,edges,xy=native_fork(tmp_path,quarter,back,renamed,power=True)
    for edge in edges:edge.SetLocked(False);edge.SetWidth(500000)
    extra=edges[-1];extra.SetLocked(True)
    field._save_field_snapshot(board,source)
    power_authority(monkeypatch,str(root.GetNetname()),int(extra.GetLayer()))
    fork_plan=fork.plan(board,[force._uid(root)],moving_refs=[root.GetParentFootprint().GetReference()],
        kind='rated_supply',board_hint='synthetic',allow_owned_locked=False,
        allow_full_current_supply_width=True)
    uid=force._uid(extra)
    assert uid not in fork_plan['track_uuids']
    assert uid in {p['native_uuid']for p in fork_plan['retained_native_ports']}
    proposal=dict(scope='source_typed_complete_cell_escape_proposal',
        source_native_binding=row._source_binding(board),board_hint='synthetic',
        retired_track_uuids=fork_plan['track_uuids'],source_owned_shared_supply_forks=[fork_plan])
    extras=[dict(change=dict(uuid=uid,net=str(extra.GetNetname()),
        source_nm=[list(extra.GetStart()),list(extra.GetEnd())]),
        authority=dict(kind='unchanged_full_current_source_edge',native_source_uuid=uid,
            source_plan=full.plan(board,source,board_hint='synthetic',retired_track_uuids=[uid])))]
    return board,source,root,a,z,proposal,extras,set(fork_plan['track_uuids'])|{uid}


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('renamed',[False,True])
@pytest.mark.parametrize('points_as_tuples',[False,True])
def test_rated_fork_and_already_owned_locked_extra_keep_every_actual_contact(tmp_path,monkeypatch,quarter,back,renamed,points_as_tuples):
    board,source,root,a,z,proposal,extras,retired=rated_fixture(tmp_path,monkeypatch,quarter,back,renamed)
    if points_as_tuples:extras[0]['change']['source_nm']=list(map(tuple,extras[0]['change']['source_nm']))
    raw=source.read_bytes();binding=row._source_binding(board)
    original=copy.deepcopy(proposal);old_extras=copy.deepcopy(extras)
    extended,proofs=compose.compose_rated_forks(board,source,proposal,extras,retired,
        deadline=time.monotonic()+10.)
    assert len(proofs)==1 and {q['change']['uuid']for q in extended}==retired
    proof=proofs[0]
    assert proof['retirement_set_unchanged']and proof['no_new_cut_or_current_authority']
    assert sum(q['locked']for q in proof['source_lock_manifest'])==1
    assert proof['original_fork']['allow_owned_locked']is False
    assert proof['original_fork']['source_owned_locked_track_uuids']==[]
    assert proposal==original and extras==old_extras
    private=pcbnew.LoadBoard(str(source));uid=force._uid(root)
    child_root=next(p for fp in private.GetFootprints()for p in fp.Pads()if force._uid(p)==uid)
    child_root.GetParentFootprint().Move(pcbnew.VECTOR2I(500000,500000))
    discard_items(private,[t for t in private.GetTracks()if force._uid(t)in retired])
    transport=dict(source_process_barrel_motion=[],explicit_source_typed_ordinary_barrel_motion=[])
    demands,groups=components.requests(board,private,extended,retired,transport,
        project_contacts=compiler._project_contacts,deadline=time.monotonic()+10.)
    assert len(groups)==1 and len(demands)==2
    assert {q['source_item_uuid']for q in groups[0]['surviving_contacts']}=={
        force._uid(p)for p in(root,a,z)}
    assert all(not set(end.get('native_uuids',[]))&retired
        for demand in demands.values()for end in(demand['a'],demand['b']))
    assert all(demand['width_nm']==500000 and demand['every_surviving_source_component_port_mandatory']
        for demand in demands.values())
    # Strict projection remains strict: the old cut edge is NOT an anchor.
    port=proposal['source_owned_shared_supply_forks'][0]['retained_native_ports']
    old_port=next(p for p in port if p['native_uuid']in retired)
    with pytest.raises(ValueError,match='missing_or_disagreeing_native_projection'):
        compiler._project_port(board,private,dict(native_uuids=[old_port['native_uuid']],
            at_nm=old_port['at_nm'],layers=[old_port['layer_id']]),transport,retired)
    assert row._source_binding(board)==binding and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['stale_binding','extra_kind','extra_current','extra_source_points',
    'extra_float_points','extra_short_points',
    'missing_extra_owner','fork_current','fork_root','fork_port','fork_width',
    'intersecting_forks','grouped_extra','extra_layer','extra_width','extra_lock_changed'])
def test_rated_fork_composition_cannot_invent_or_expand_original_owners(tmp_path,monkeypatch,fault):
    board,source,root,a,z,proposal,extras,retired=rated_fixture(tmp_path,monkeypatch)
    fork=proposal['source_owned_shared_supply_forks'][0]
    if fault=='stale_binding':proposal['source_native_binding']='forged'
    elif fault=='extra_kind':extras[0]['authority']['kind']='positive_source_ordinary'
    elif fault=='extra_current':extras[0]['authority']['source_plan']['contract']['current_authority']['amps']=.75
    elif fault=='extra_source_points':extras[0]['change']['source_nm'][0][0]+=1
    elif fault=='extra_float_points':extras[0]['change']['source_nm'][0][0]=float(extras[0]['change']['source_nm'][0][0])
    elif fault=='extra_short_points':extras[0]['change']['source_nm'].pop()
    elif fault=='missing_extra_owner':retired-=set(q['change']['uuid']for q in extras)
    elif fault=='fork_current':fork['full_current_source_plan']['contract']['current_authority']['amps']=.75
    elif fault=='fork_root':fork['requested_root_pad_uuids']=[force._uid(a)]
    elif fault=='fork_port':fork['retained_native_ports'][0]['at_nm'][0]+=1
    elif fault=='fork_width':fork['width_nm']=200000
    elif fault=='intersecting_forks':proposal['source_owned_shared_supply_forks'].append(copy.deepcopy(fork))
    else:
        edge=next(t for t in board.GetTracks()if force._uid(t)==extras[0]['change']['uuid'])
        if fault=='grouped_extra':
            group=pcbnew.PCB_GROUP(board);board.Add(group);group.AddItem(edge)
        elif fault=='extra_layer':edge.SetLayer(pcbnew.B_Cu)
        elif fault=='extra_width':edge.SetWidth(400000)
        else:edge.SetLocked(False)
        field._save_field_snapshot(board,source)
        proposal['source_native_binding']=row._source_binding(board)
    before=row._source_binding(board);raw=source.read_bytes()
    with pytest.raises(ValueError):compose.compose_rated_forks(board,source,proposal,extras,retired,
        deadline=time.monotonic()+10.)
    assert row._source_binding(board)==before and source.read_bytes()==raw
