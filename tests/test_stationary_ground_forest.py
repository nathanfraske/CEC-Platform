"""Whole native Source paths survive a neighboring cell move, not net aliases."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_stationary_ground_forest as forest
from cec_native_items import discard_items
from test_ground_return_fork import fixture as fork_fixture,plan
from test_field_proposals import track


def fixture(tmp_path,quarter=0,back=False,split=True):
    board,source,owner,fixed,via,edges=fork_fixture(tmp_path,quarter,back)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    def xy(x,y):
        for _ in range(quarter):x,y=30-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    tail=None
    if split:
        edges[0].SetEnd(xy(12,10))
        tail=track(board,'GND',[v/1e6 for v in xy(12,10)],[v/1e6 for v in xy(14,10)],
            width=.2,layer=pcbnew.B_Cu if back else pcbnew.F_Cu);tail.SetLocked(True)
    profile=fab.get_profile(fab.board_profile_name(board))
    for name,role in zip(fab.COPPER_LAYERS,profile['roles']):
        if role!='GND':continue
        z=pcbnew.ZONE(board);z.SetLayer(board.GetLayerID(name));z.SetNet(board.FindNet('GND'))
        z.SetLocalClearance(200000);z.SetMinThickness(100000);z.Outline().NewOutline()
        for x,y in ((1,1),(39,1),(39,39),(1,39)):z.Outline().Append(pcbnew.VECTOR2I_MM(x,y))
        board.Add(z)
    additive._ground_refill(board);field._save_field_snapshot(board,source)
    owner_ref,fixed_ref=owner.GetReference(),fixed.GetReference()
    via_id=force._uid(via);edge_ids=[force._uid(t) for t in edges]
    tail_id=force._uid(tail) if tail is not None else None
    board=pcbnew.LoadBoard(str(source));native={force._uid(t):t for t in board.GetTracks()}
    owner=board.FindFootprintByReference(owner_ref);fixed=board.FindFootprintByReference(fixed_ref)
    via=native[via_id];edges=[native[u] for u in edge_ids];tail=native[tail_id] if tail_id else None
    q=plan(board,owner);cut=set(q['track_uuids'])
    proposal=dict(scope='source_typed_complete_cell_escape_proposal',source_native_binding=binding._source_binding(board),
        board_hint='opaque_design',row_plan=dict(retired_track_uuids=[]),retired_track_uuids=sorted(cut),
        source_owned_shared_ground_return_forks=[q])
    posed=pcbnew.LoadBoard(str(source));posed.FindFootprintByReference(owner.GetReference()).Move(pcbnew.VECTOR2I_MM(.5,.5))
    return board,posed,source,proposal,owner,fixed,via,edges,tail


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_complete_stationary_branch_not_only_its_incident_stroke_is_preserved(tmp_path,quarter,back):
    board,posed,source,proposal,owner,fixed,via,edges,tail=fixture(tmp_path,quarter,back)
    raw=source.read_bytes();before=[binding._source_binding(b) for b in (board,posed)];unchanged=copy.deepcopy(proposal)
    result=forest.refine(board,posed,proposal)
    assert proposal==unchanged and source.read_bytes()==raw
    assert before==[binding._source_binding(b) for b in (board,posed)]
    assert result['retired_track_uuids']==[force._uid(edges[0])]
    record=result['stationary_ground_path_preservation'][0]
    assert set(record['kept_source_track_uuids'])=={force._uid(edges[1]),force._uid(tail)}
    path=record['paths'][0]
    assert path['pad_uuid']==force._uid(fixed.FindPadByNumber('2')) and path['barrel_uuid']==force._uid(via)
    assert set(path['source_native_path_uuids'])=={force._uid(fixed.FindPadByNumber('2')),
        force._uid(edges[1]),force._uid(tail),force._uid(via)}
    assert path['actual_saved_reference_contacts'] and record['no_new_ground_connection_or_current_authority']
    assert not record['release_authority']


@pytest.mark.parametrize('fault',['moved_root','diameter','drill','root_group','no_ground_fill','moving_fixed_pad',
    'other_owner','unknown_land','same_net_unrelated_barrel'])
def test_identity_aliases_partial_paths_and_independent_cut_ownership_do_not_count(tmp_path,monkeypatch,fault):
    board,posed,source,proposal,owner,fixed,via,edges,tail=fixture(tmp_path)
    root=next(t for t in posed.GetTracks() if force._uid(t)==force._uid(via))
    if fault in ('moved_root','same_net_unrelated_barrel'):
        key=force._item_key(root);root.Move(pcbnew.VECTOR2I(1,0));assert force._item_key(root)==key
        if fault=='same_net_unrelated_barrel':
            v=pcbnew.PCB_VIA(posed);v.SetNet(posed.FindNet('GND'));v.SetPosition(pcbnew.VECTOR2I_MM(30,30))
            v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);posed.Add(v)
    elif fault=='diameter':root.SetWidth(root.GetWidth()+1)
    elif fault=='drill':root.SetDrill(root.GetDrillValue()+1)
    elif fault=='root_group':
        group=pcbnew.PCB_GROUP(posed);group.SetName('unrelated');posed.Add(group);group.AddItem(root)
    elif fault=='no_ground_fill':
        for z in posed.Zones():z.UnFill()
    elif fault=='moving_fixed_pad':posed.FindFootprintByReference(fixed.GetReference()).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='other_owner':proposal['row_plan']['retired_track_uuids']=[force._uid(edges[1])]
    else:monkeypatch.setattr(forest.placement,'_native_stationary_land',lambda *args:None)
    before=[binding._source_binding(b) for b in (board,posed)];raw=source.read_bytes()
    result=forest.refine(board,posed,proposal)
    assert 'stationary_ground_path_preservation' not in result
    assert result['retired_track_uuids']==proposal['retired_track_uuids']
    assert before==[binding._source_binding(b) for b in (board,posed)] and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['tracks','root','role','source'])
def test_fork_source_ownership_is_rederived_not_worker_supplied(tmp_path,fault):
    board,posed,source,proposal,*_=fixture(tmp_path)
    q=proposal['source_owned_shared_ground_return_forks'][0]
    if fault=='tracks':q['track_uuids']=q['track_uuids'][:-1]
    elif fault=='root':q['requested_root_pad_uuids']=['not-a-source-terminal']
    elif fault=='role':q['fixed_ground_terminal_contracts'][0]['role']='pretend'
    else:q['source_sha256']='not-the-source'
    with pytest.raises((ValueError,KeyError)):forest.refine(board,posed,proposal)


@pytest.mark.parametrize('timeout',[0,True,float('nan'),float('inf'),10.001])
def test_native_work_has_an_explicit_ten_second_maximum(tmp_path,timeout):
    board,posed,source,proposal,*_=fixture(tmp_path)
    with pytest.raises(ValueError,match='bounded_exact'):forest.refine(board,posed,proposal,timeout_s=timeout)


def test_no_ground_fork_is_not_a_new_cut_or_new_connection(tmp_path):
    board,posed,source,proposal,*_=fixture(tmp_path)
    proposal.pop('source_owned_shared_ground_return_forks')
    assert forest.refine(board,posed,proposal)==proposal
