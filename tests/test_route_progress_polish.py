"""Incremental finishing cannot grant itself locked/coupled copper ownership."""
import json
import pcbnew
import pytest
import cec_fr
import cec_fab_repair as fab
import cec_route_progress_polish as polish
import cec_route_quality as quality
import cec_local_copper_cell as copper
import cec_full_pipeline as pipeline


def fixture(*, layer=pcbnew.F_Cu, offset=(0,0), locked=False):
    board=pcbnew.CreateEmptyBoard()
    net=pcbnew.NETINFO_ITEM(board,'/GENERIC_SIGNAL'); board.Add(net)
    tracks=[]
    for start,end in [((20,20),(19.5,20.5)),((20,20),(20,20.017787))]:
        t=pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I_MM(start[0]+offset[0],start[1]+offset[1]))
        t.SetEnd(pcbnew.VECTOR2I_MM(end[0]+offset[0],end[1]+offset[1]))
        t.SetNet(net);t.SetLayer(layer);t.SetWidth(200000);t.SetLocked(locked)
        board.Add(t);tracks.append(t)
    return board, tracks


@pytest.mark.parametrize('locked,authorized,expected',[(False,False,1),(True,False,0),(True,True,1)])
@pytest.mark.parametrize('layer,offset',[(pcbnew.F_Cu,(0,0)),(pcbnew.B_Cu,(50,12))])
def test_acute_cleanup_honors_exact_lock_authority_and_native_geometry(locked,authorized,expected,layer,offset):
    board,tracks=fixture(layer=layer,offset=offset,locked=locked)
    before=copper.copper_inventory(board)
    endpoints=[(t.GetEnd().x,t.GetEnd().y) for t in tracks]
    ids=[t.m_Uuid.AsString() for t in tracks]
    assert fab.repair_acute_vertices(board,allow_locked_track_uuids=ids if authorized else ())==expected
    assert [(t.GetEnd().x,t.GetEnd().y) for t in tracks]==endpoints
    assert [t.m_Uuid.AsString() for t in tracks]==ids
    assert all(t.IsLocked()==locked for t in tracks)
    if expected:
        assert quality.analyze_board(board)['issue_count']==0
    else:
        assert copper.copper_inventory(board)==before


@pytest.mark.parametrize('fault',['group','kelvin','coupled','partial_authority'])
def test_specialist_owned_geometry_is_not_general_polish(fault,monkeypatch):
    board,tracks=fixture(locked=fault=='partial_authority')
    if fault=='group':
        group=pcbnew.PCB_GROUP(board);group.SetName('not-an-ownership-grant')
        group.AddItem(tracks[0]);board.Add(group)
    if fault=='kelvin': monkeypatch.setattr(cec_fr,'_board_kelvin_pairs',lambda _: [('/GENERIC_SIGNAL','/RETURN')])
    if fault=='coupled': monkeypatch.setattr(cec_fr,'coupled_pair_nets',lambda _: {'/GENERIC_SIGNAL'})
    before=copper.copper_inventory(board)
    assert fab.repair_acute_vertices(board,allow_locked_track_uuids=[tracks[0].m_Uuid.AsString()])==0
    assert copper.copper_inventory(board)==before


def test_private_native_polish_is_idempotent_and_not_release_authority(tmp_path):
    board,tracks=fixture()
    path=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    first=polish.native_acute_polish(path)
    assert first['changed'] and first['before_issues']==1 and first['after_issues']==0
    assert first['requires_independent_admission'] and not first['release_authority']
    after=path.read_bytes()
    second=polish.native_acute_polish(path)
    assert not second['changed'] and path.read_bytes()==after


@pytest.mark.parametrize('origin',['incumbent_polish','route_residual_resume_polish'])
def test_accepted_polish_keeps_bound_search_cost_hints(tmp_path,origin):
    import cec_certificate_repair as repair
    board=tmp_path/'board.kicad_pcb';board.write_text('verified private board')
    history=repair.route_search_history({},[dict(stage='deep_route_portfolio',net='/A')])
    files=pipeline._persist_route_search_history(dict(routed=str(board),candidate_origin=origin),
        dict(route_search_history=history),tmp_path)
    saved=json.loads(open(files[0]).read())
    assert saved['board_sha256']==pipeline.sha256_file(board)
    assert saved['route_search_history']['stages']['deep_route_portfolio']=={'/A':1}
