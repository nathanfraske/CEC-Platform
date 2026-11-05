"""Proposal rejection uses the saved receiver's actual native capsules.

Only this geometric necessary condition is tested here, not Source routing
authority. Native renaming/rotations/reflections cannot hide a short mesh.
"""
import time
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest
import cec_measurement_quiet_fanout as fan
import cec_cell_row_rebuild as row


def case(quarter=0, reflected=False):
    board=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(board,'/RENAMED_NONLOAD');board.Add(net)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('RENAMED_OWNER');board.Add(fp)
    root=pcbnew.PAD(fp);root.SetNumber('47');root.SetNet(net)
    root.SetAttribute(pcbnew.PAD_ATTRIB_SMD);root.SetLayerSet(pcbnew.PAD.SMDMask())
    root.SetSize(pcbnew.VECTOR2I_MM(.8,.8));fp.Add(root)
    def transform(point):
        x,y=[round(v*1e6) for v in point]
        if reflected:x=-x
        for _ in range(quarter):x,y=-y,x
        return [x+40000000,y+40000000]
    root.SetPosition(pcbnew.VECTOR2I(*transform((10,10))))
    return board,root,transform


def ops(points,transform):
    return [['trk',transform(a),transform(b),200000,int(pcbnew.F_Cu)]
        for a,b in zip(points,points[1:])]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('reflected',[False,True])
@pytest.mark.parametrize('tiny', [.031,.167])
def test_tiny_canonical_self_contact_is_rejected_before_save(quarter,reflected,tiny):
    board,root,transform=case(quarter,reflected)
    # All endpoints are unique and every edge is cardinal/45 degrees, yet
    # the returning third capsule physically contacts the first one.
    points=[(10,10),(12,10),(12+.5*tiny,10+.5*tiny),(12-.5*tiny,10+1.5*tiny),
        (14,12+2*tiny)]
    before=row._source_binding(board)
    with pytest.raises(ValueError,match='nonadjacent_native_copper_contact'):
        fan._ordered_proposal(board,ops(points,transform),root,width_nm=200000,
            endpoint=transform(points[-1]),deadline=time.monotonic()+2.)
    assert row._source_binding(board)==before and not list(board.GetTracks())


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('reflected',[False,True])
def test_clear_native_simple_branch_is_not_mutated_or_given_authority(quarter,reflected):
    board,root,transform=case(quarter,reflected)
    points=[(10,10),(12,10),(13,11),(13,12),(14,12)]
    proposed=ops(points,transform);before=row._source_binding(board)
    ordered,end=fan._ordered_proposal(board,proposed,root,width_nm=200000,
        endpoint=transform(points[-1]),deadline=time.monotonic()+2.)
    assert ordered==proposed and end==tuple(transform(points[-1]))
    assert row._source_binding(board)==before and not list(board.GetTracks())


@pytest.mark.parametrize('fault',['back','thin','wrong_endpoint','fork','cycle','non45','float','via'])
def test_proposal_cannot_borrow_scope_from_an_unrelated_or_malformed_path(fault):
    board,root,transform=case();points=[(10,10),(12,10),(14,12)]
    proposed=ops(points,transform);endpoint=transform(points[-1])
    if fault=='back':proposed[0][4]=int(pcbnew.B_Cu)
    elif fault=='thin':proposed[0][3]=100000
    elif fault=='wrong_endpoint':endpoint[0]+=1
    elif fault=='fork':proposed.append(['trk',transform((12,10)),transform((12,12)),200000,int(pcbnew.F_Cu)])
    elif fault=='cycle':proposed.append(['trk',transform((14,12)),transform((10,10)),200000,int(pcbnew.F_Cu)])
    elif fault=='non45':proposed[1][2][0]+=1
    elif fault=='float':proposed[0][1][0]=float(proposed[0][1][0])
    else:proposed[0][0]='via'
    before=row._source_binding(board)
    with pytest.raises(ValueError):
        fan._ordered_proposal(board,proposed,root,width_nm=200000,endpoint=endpoint,deadline=time.monotonic()+2.)
    assert row._source_binding(board)==before and not list(board.GetTracks())


@pytest.mark.parametrize('quarter',range(4))
def test_actual_Source_search_skips_self_contacting_proposal_before_return(tmp_path,monkeypatch,quarter):
    from test_source_quiet_fanout import fixture,proposal
    source,root_uid,_target,peer_uid,_quiet=fixture(tmp_path,monkeypatch,quarter)
    q=proposal(source,root_uid,peer_uid);assert q['complete']
    q['selected_port']=next(p for p in q['ports'] if p['kind']=='actual_quiet_input_land')
    board=pcbnew.LoadBoard(str(source));before=row._source_binding(board)
    def turn(point):
        x,y=[round(v*1e6)-30000000 for v in point]
        # Native KiCad positive angle uses the board's downward Y axis.
        for _ in range(quarter):x,y=y,-x
        return [x+30000000,y+30000000]
    bad=[turn(p) for p in [(10,10),(12,10),(12.0155,10.0155),
        (11.9845,10.0465),(13.969,12.031),(14,12)]]
    canonical=fan.fr._canonical_45_xy_paths
    def offered(a,b):
        valid=list(canonical(a,b))
        return [bad,*valid] if tuple(a)==tuple(bad[0]) and tuple(b)==tuple(bad[-1]) else valid
    predicate=fan._ordered_proposal;refused=[]
    def observed(*args,**kw):
        try:return predicate(*args,**kw)
        except ValueError as exc:
            refused.append(str(exc));raise
    monkeypatch.setattr(fan.fr,'_canonical_45_xy_paths',offered)
    monkeypatch.setattr(fan,'_ordered_proposal',observed)
    result=fan.geometry(board,q,board_hint='RENAMED_SOURCE',timeout_s=8.)
    assert result['complete'] and result['source_unchanged']
    assert 'quiet_branch_has_nonadjacent_native_copper_contact' in refused
    assert [result['ops'][0][1],*[p[2] for p in result['ops']]] != bad
    assert row._source_binding(board)==before
