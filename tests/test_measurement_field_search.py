"""Measurement search rejects quiet-input/edge-source coupling before save."""
import copy
import math
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_field_search as search
import cec_measurement_terminal_route as route
from test_measurement_terminal_route import fixture,get


def fixture_with_aggressor(quarter=0):
    board,demand,root,pickup=fixture()
    old_code=root.GetNetCode();sense=pcbnew.NETINFO_ITEM(board,'/SENSE_TEST_HI');board.Add(sense)
    for item in[*(p for fp in board.GetFootprints()for p in fp.Pads()),*board.GetTracks()]:
        if item.GetNetCode()==old_code:item.SetNet(sense)
    net=pcbnew.NETINFO_ITEM(board,'/CAN_L');board.Add(net)
    edge=pcbnew.PCB_TRACK(board);edge.SetNet(net);edge.SetWidth(200000);edge.SetLayer(pcbnew.F_Cu)
    edge.SetStart(pcbnew.VECTOR2I_MM(11,10.8));edge.SetEnd(pcbnew.VECTOR2I_MM(19,10.8));board.Add(edge)
    if quarter:
        pivot=pcbnew.VECTOR2I_MM(30,30);angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for item in[*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:item.Rotate(pivot,angle)
    demand=next(d for d in get(board)['requests']if d['pad_uuid']==force._uid(root))
    return board,demand,root,pickup


@pytest.mark.parametrize('quarter',range(4))
def test_legal_copper_parallel_is_pruned_and_an_actual_quiet_detour_is_found(quarter):
    board,demand,root,pickup=fixture_with_aggressor(quarter)
    before=field._field_snapshot_inventory(board)
    direct=[['trk',list(root.GetPosition()),list(pickup.GetPosition()),200000,pcbnew.F_Cu]]
    q=route.assess_path_field(board,direct,net=demand['net'],deadline=time.monotonic()+2)
    assert q['complete']and q['ok']is False and q['new_blockers']
    menu=route.menus(board,demand,width_nm=200000,timeout_s=3.,max_choices=2,max_length_nm=24000000)
    assert menu['ops'],menu
    assert menu['field_search_pruning']['conclusive_same_layer_refusals']>0
    assert menu['complete_path_field']['queries']>0
    assert menu['complete_path_field']['complete_pickup_tail_included']
    for ops in menu['ops']:
        proof=route.assess_path_field(board,ops,net=demand['net'],deadline=time.monotonic()+2)
        assert proof['ok']is True and proof['complete']is True and proof['board_mutated']is False
    assert before==field._field_snapshot_inventory(board)
    assert menu['release_authority']is False and menu['current_authority']is False


@pytest.mark.parametrize('quarter',range(4))
def test_submillimeter_strokes_cannot_hide_one_long_parallel_run(quarter):
    board,demand,root,pickup=fixture_with_aggressor(quarter)
    pruning=search.PlanarSearchGuard(board,demand['net'])
    # Derive the rotated native cardinal direction from the actual lands.
    start=tuple(root.GetPosition());end=tuple(pickup.GetPosition())
    dx,dy=((b-a)//10 for a,b in zip(start,end))
    points=[(start[0]+round(dx*.6*k),start[1]+round(dy*.6*k))for k in range(6)]
    assert all(pruning(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),200000,pcbnew.F_Cu)
        for a,b in zip(points,points[1:]))
    assert route._field_runs_clear(points,200000,pcbnew.F_Cu,pruning)is False


@pytest.mark.parametrize('fault',['ok_false','ok_unknown','ok_numeric','incomplete','complete_numeric',
                                  'mutated','mutation_missing'])
def test_unknown_or_nonliteral_complete_field_evidence_never_funds_a_path(monkeypatch,fault):
    board,demand,root,pickup=fixture();before=field._field_snapshot_inventory(board)
    proof=dict(ok=True,complete=True,board_mutated=False)
    if fault=='ok_false':proof['ok']=False
    elif fault=='ok_unknown':proof['ok']=None
    elif fault=='ok_numeric':proof['ok']=1
    elif fault=='incomplete':proof['complete']=False
    elif fault=='complete_numeric':proof['complete']=1
    elif fault=='mutated':proof['board_mutated']=True
    else:proof.pop('board_mutated')
    monkeypatch.setattr(route,'assess_path_field',lambda *a,**k:copy.deepcopy(proof))
    monkeypatch.setattr(route.fr,'_guarded_profiled_lastmile_legs',lambda *a,**k:None)
    menu=route.menus(board,demand,width_nm=200000,timeout_s=.3,max_choices=1)
    assert not menu['ops']and menu['complete_path_field']['refusals']>0
    assert before==field._field_snapshot_inventory(board)and not menu['no_path_proof']


def test_the_complete_fixed_pickup_tail_is_in_the_field_query(monkeypatch):
    board,demand,root,pickup=fixture();queries=[]
    original=route.assess_path_field
    def capture(owner,ops,**kwargs):
        queries.append(copy.deepcopy(ops));return original(owner,ops,**kwargs)
    monkeypatch.setattr(route,'assess_path_field',capture)
    menu=route.menus(board,demand,width_nm=200000,timeout_s=2.,max_choices=1)
    assert menu['ops']and queries
    # A direct source shunt uses an actual inward land point, not a free
    # target net/centre. Both the outside knee and final tail must be seen.
    assert queries[-1]==menu['ops'][0]
    tail=queries[-1][-1]
    assert pickup.GetEffectiveShape(pcbnew.F_Cu).Collide(pcbnew.VECTOR2I(*tail[2]),0)
    assert math.dist(tail[1],tail[2])>0


@pytest.mark.parametrize('bad',[[],[['via',[1,2],.3,.6]]])
def test_nonplanar_or_empty_proposal_cannot_borrow_planar_field_scope(bad):
    board,demand,root,pickup=fixture()
    with pytest.raises(ValueError):route.assess_path_field(board,bad,net=demand['net'],deadline=time.monotonic()+1)


@pytest.mark.parametrize('bad',[True,{},'',[]])
def test_ambiguous_explicit_design_identity_is_refused(bad):
    board,demand,root,pickup=fixture()
    with pytest.raises(ValueError):route.menus(board,demand,width_nm=200000,board_hint=bad)


def test_maximal_run_query_preserves_real_bends_and_does_not_flatten_reversal():
    calls=[]
    def pruning(a,b,w,l):calls.append((tuple(a),tuple(b)));return True
    points=[[0,0],[100000,0],[200000,0],[200000,100000],[100000,100000],[0,100000]]
    assert route._field_runs_clear(points,200000,pcbnew.F_Cu,pruning)
    assert calls==[((0,0),(200000,0)),((200000,0),(200000,100000)),((200000,100000),(0,100000))]
    calls.clear()
    assert route._field_runs_clear([[0,0],[100000,0],[0,0]],200000,pcbnew.F_Cu,pruning)
    assert calls==[((0,0),(100000,0)),((100000,0),(0,0))]


def test_maze_receives_the_same_active_accumulated_field_run_guard(monkeypatch):
    board,demand,root,pickup=fixture_with_aggressor();seen=[]
    before=field._field_snapshot_inventory(board)
    monkeypatch.setattr(route.fr,'_canonical_45_xy_paths',lambda *a:[])
    monkeypatch.setattr(route.fr,'_offset_manhattan_xy_paths',lambda *a:[])
    def maze(*args,**kwargs):seen.append(kwargs);return None
    monkeypatch.setattr(route.fr,'_guarded_profiled_lastmile_legs',maze)
    menu=route.menus(board,demand,width_nm=200000,timeout_s=2.,max_choices=1)
    assert not menu['ops']and seen
    assert all(callable(row['run_guard'])and callable(row['path_validator'])for row in seen)
    assert all(row['run_guard'](root.GetPosition(),pickup.GetPosition(),200000)is False for row in seen)
    assert before==field._field_snapshot_inventory(board)
